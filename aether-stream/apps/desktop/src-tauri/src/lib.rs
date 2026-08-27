use std::sync::Arc;

use aether_core::{
    DownloadConfig, DownloadEvent, DownloadManager, DownloadSpec, DownloadState, QueueStore,
};
use serde::Serialize;
use tauri::{
    async_runtime,
    AppHandle,
    Emitter,
    Manager,
    State,
};
use url::Url;

pub struct AppState {
    pub manager: DownloadManager,
    pub store: Arc<QueueStore>,
}

#[derive(Debug, Serialize)]
pub struct SystemInfo {
    transport: &'static str,
    telemetry: bool,
    persistence: &'static str,
}

#[tauri::command]
async fn enqueue_download(
    state: State<'_, AppState>,
    url: String,
    destination: String,
) -> Result<String, String> {
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
fn system_info() -> SystemInfo {
    SystemInfo {
        transport: "HTTP/3 → HTTP/2 → HTTP/1.1",
        telemetry: false,
        persistence: "SQLite / rusqlite",
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

pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let data_dir = app
                .path()
                .app_data_dir()
                .map_err(|error| std::io::Error::other(error.to_string()))?;
            let database = data_dir.join("aether.sqlite3");
            let store = Arc::new(
                QueueStore::open(database)
                    .map_err(|error| std::io::Error::other(error.to_string()))?,
            );
            let manager = DownloadManager::new(DownloadConfig::default())
                .map_err(|error| std::io::Error::other(error.to_string()))?;

            start_event_forwarder(app.handle(), &manager, store.clone());
            app.manage(AppState { manager, store });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![enqueue_download, system_info])
        .run(tauri::generate_context!())
        .expect("error while running AETHER-STREAM");
}
