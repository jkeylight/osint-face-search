use std::sync::{Arc, Mutex};

use aether_core::{
    AuthController, AuthStatus, DownloadConfig, DownloadEvent,
    DownloadManager, DownloadSpec, DownloadState, QueueStore,
};
use keyring::Entry;
use serde::Serialize;
use tauri::{async_runtime, AppHandle, Emitter, Manager, State, WebviewWindow};
use tauri_plugin_biometry::{AuthOptions as BiometricOptions, BiometryExt};
use url::Url;
use uuid::Uuid;
use zeroize::Zeroizing;

const KEYCHAIN_SERVICE: &str = "com.aether.stream";
const KEYCHAIN_DATABASE_KEY: &str = "sqlcipher-database-key";

pub struct AppState {
    pub manager: DownloadManager,
    pub store: Arc<QueueStore>,
    pub auth: Mutex<AuthController>,
}

#[derive(Debug, Serialize)]
pub struct SystemInfo {
    transport: &'static str,
    telemetry: bool,
    persistence: &'static str,
    encryption: &'static str,
}

#[tauri::command]
async fn auth_status(state: State<'_, AppState>) -> Result<AuthStatus, String> {
    let mut auth = state.auth.lock().map_err(|_| "auth mutex poisoned".to_owned())?;
    Ok(auth.status())
}

#[tauri::command]
async fn enroll_password(
    state: State<'_, AppState>,
    password: String,
) -> Result<AuthStatus, String> {
    let password = Zeroizing::new(password);
    let mut auth = state.auth.lock().map_err(|_| "auth mutex poisoned".to_owned())?;
    let hash = auth
        .enroll_password(password.as_str())
        .map_err(|error| error.to_string())?;

    if let Err(error) = state.store.set_password_hash(&hash) {
        // Never leave an in-memory vault unlocked if its verifier did not make
        // it into the encrypted database.
        auth.lock();
        return Err(error.to_string());
    }
    Ok(auth.status())
}

#[tauri::command]
async fn unlock_with_password(
    state: State<'_, AppState>,
    password: String,
) -> Result<AuthStatus, String> {
    let password = Zeroizing::new(password);
    let mut auth = state.auth.lock().map_err(|_| "auth mutex poisoned".to_owned())?;
    auth.verify_password(password.as_str())
        .map_err(|error| error.to_string())
}

/// The platform prompt is supplied by a Tauri plugin; the core receives only
/// a success/failure result. Linux falls back to the passphrase path until a
/// desktop-portal or PAM adapter is selected for the target distribution.
#[tauri::command]
async fn unlock_with_biometric(
    app: AppHandle,
    window: WebviewWindow,
    state: State<'_, AppState>,
) -> Result<AuthStatus, String> {
    let options = BiometricOptions {
        allow_device_credential: Some(false),
        cancel_title: Some("Keep vault locked".to_owned()),
        fallback_title: None,
        title: Some("Unlock AETHER-STREAM".to_owned()),
        subtitle: Some("Authenticate to open your local vault".to_owned()),
        confirmation_required: Some(false),
    };
    app.biometry()
        .authenticate(window, "Unlock the AETHER-STREAM vault".to_owned(), options)
        .map_err(|error| error.to_string())?;

    let mut auth = state.auth.lock().map_err(|_| "auth mutex poisoned".to_owned())?;
    auth.mark_biometric_authenticated()
        .map_err(|error| error.to_string())
}

#[tauri::command]
async fn lock_app(state: State<'_, AppState>) -> Result<AuthStatus, String> {
    let mut auth = state.auth.lock().map_err(|_| "auth mutex poisoned".to_owned())?;
    auth.lock();
    Ok(auth.status())
}

#[tauri::command]
async fn enqueue_download(
    state: State<'_, AppState>,
    url: String,
    destination: String,
) -> Result<String, String> {
    ensure_unlocked(&state)?;
    let url = Url::parse(&url).map_err(|error| format!("invalid URL: {error}"))?;
    let spec = DownloadSpec::new(url, destination);
    let id = spec.id;

    state
        .store
        .insert_download(id, spec.url.as_str(), &spec.destination, None)
        .map_err(|error| error.to_string())?;

    let manager = state.manager.clone();
    async_runtime::spawn(async move {
        if let Err(error) = manager.download(spec).await {
            tracing::error!(%error, %id, "download failed");
        }
    });

    Ok(id.to_string())
}

#[tauri::command]
async fn system_info() -> SystemInfo {
    SystemInfo {
        transport: "HTTP/3 → HTTP/2 → HTTP/1.1",
        telemetry: false,
        persistence: "SQLite / rusqlite",
        encryption: "SQLCipher + OS keychain",
    }
}

fn ensure_unlocked(state: &State<'_, AppState>) -> Result<(), String> {
    let mut auth = state.auth.lock().map_err(|_| "auth mutex poisoned".to_owned())?;
    if auth.is_unlocked() {
        Ok(())
    } else {
        Err("vault is locked".to_owned())
    }
}

fn start_event_forwarder(
    app: &AppHandle,
    manager: &DownloadManager,
    store: Arc<QueueStore>,
) {
    let mut events = manager.subscribe();
    let app = app.clone();
    async_runtime::spawn(async move {
        loop {
            match events.recv().await {
                Ok(event) => {
                    persist_event(&store, &event);
                    let _ = app.emit("download://event", &event);
                }
                Err(tokio::sync::broadcast::error::RecvError::Lagged(_)) => continue,
                Err(tokio::sync::broadcast::error::RecvError::Closed) => break,
            }
        }
    });
}

fn persist_event(store: &QueueStore, event: &DownloadEvent) {
    let result = match event {
        DownloadEvent::State { id, state } => store.update_status(*id, state_name(*state)),
        DownloadEvent::Progress {
            id,
            completed_bytes,
            ..
        } => store.update_progress(*id, *completed_bytes, "downloading"),
        DownloadEvent::Finished {
            id,
            bytes_written,
            ..
        } => store.update_progress(*id, *bytes_written, "complete"),
        DownloadEvent::Failed { id, .. } => store.update_status(*id, "failed"),
        DownloadEvent::Chunk { .. } => Ok(()),
    };
    if let Err(error) = result {
        tracing::error!(%error, "could not persist download event");
    }
}

fn state_name(state: DownloadState) -> &'static str {
    match state {
        DownloadState::Queued => "queued",
        DownloadState::Probing => "probing",
        DownloadState::Downloading => "downloading",
        DownloadState::Assembling => "assembling",
        DownloadState::Complete => "complete",
        DownloadState::Cancelled => "cancelled",
        DownloadState::Failed => "failed",
    }
}

fn load_or_create_database_key() -> Result<Zeroizing<Vec<u8>>, String> {
    let entry = Entry::new(KEYCHAIN_SERVICE, KEYCHAIN_DATABASE_KEY)
        .map_err(|error| format!("keychain entry unavailable: {error}"))?;

    match entry.get_secret() {
        Ok(secret) if secret.len() == 32 => Ok(Zeroizing::new(secret)),
        Ok(_) => Err("keychain database key has an invalid length".to_owned()),
        Err(keyring::Error::NoEntry) => {
            let first = Uuid::new_v4();
            let second = Uuid::new_v4();
            let mut secret = Zeroizing::new(Vec::with_capacity(32));
            secret.extend_from_slice(first.as_bytes());
            secret.extend_from_slice(second.as_bytes());
            entry
                .set_secret(&secret)
                .map_err(|error| format!("could not persist database key: {error}"))?;
            Ok(secret)
        }
        Err(error) => Err(format!("could not read database key: {error}")),
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_biometry::init())
        .setup(|app| {
            let data_dir = app
                .path()
                .app_data_dir()
                .map_err(|error| std::io::Error::other(error.to_string()))?;
            let database = data_dir.join("aether.sqlite3");
            let database_key = load_or_create_database_key()
                .map_err(std::io::Error::other)?;
            let store = Arc::new(
                QueueStore::open(database, database_key.as_slice())
                    .map_err(|error| std::io::Error::other(error.to_string()))?,
            );
            let password_hash = store
                .password_hash()
                .map_err(|error| std::io::Error::other(error.to_string()))?;
            let mut auth = AuthController::from_hash(password_hash)
                .map_err(|error| std::io::Error::other(error.to_string()))?;
            let biometric_available = app
                .biometry()
                .status()
                .map(|status| status.is_available)
                .unwrap_or(false);
            auth.set_biometric_available(biometric_available);
            let manager = DownloadManager::new(DownloadConfig::default())
                .map_err(|error| std::io::Error::other(error.to_string()))?;

            start_event_forwarder(app.handle(), &manager, store.clone());
            app.manage(AppState {
                manager,
                store,
                auth: Mutex::new(auth),
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            auth_status,
            enroll_password,
            unlock_with_password,
            unlock_with_biometric,
            lock_app,
            enqueue_download,
            system_info
        ])
        .run(tauri::generate_context!())
        .expect("error while running AETHER-STREAM");
}
