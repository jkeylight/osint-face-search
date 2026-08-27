//! SQLCipher-backed SQLite persistence kept beside the Rust engine.
//!
//! Prisma's schema in `packages/data/prisma/schema.prisma` is the shared
//! contract for TypeScript tooling. Runtime queue writes stay here so the
//! native engine does not cross a process boundary for every progress event.
//! Production opens the database only after the Tauri shell obtains a 256-bit
//! key from the platform keychain.

use std::{path::Path, sync::Mutex};

use rusqlite::{params, Connection, OptionalExtension};
use thiserror::Error;
use uuid::Uuid;

#[derive(Debug, Error)]
pub enum StoreError {
    #[error("sqlite error: {0}")]
    Sqlite(#[from] rusqlite::Error),
    #[error("filesystem error: {0}")]
    Io(#[from] std::io::Error),
    #[error("database key cannot be empty")]
    EmptyKey,
    #[error("sqlite mutex was poisoned")]
    Poisoned,
}

/// Thread-safe, single-process SQLCipher store.
///
/// The connection is intentionally serialized behind a mutex. Progress events
/// are emitted from the hot path and should be coalesced by the caller before
/// persisting; the store is a durable checkpoint boundary, not an event log.
pub struct QueueStore {
    connection: Mutex<Connection>,
}

impl QueueStore {
    /// Open or create an encrypted SQLCipher database.
    ///
    /// `key` is supplied by the platform keychain adapter and is never written
    /// to SQLite. The SQLCipher passphrase is a deterministic encoding of the
    /// random key so no password or auth material is exposed to SQL text.
    pub fn open(path: impl AsRef<Path>, key: &[u8]) -> Result<Self, StoreError> {
        if key.is_empty() {
            return Err(StoreError::EmptyKey);
        }
        let path = path.as_ref();
        if let Some(parent) = path.parent() {
            if !parent.as_os_str().is_empty() {
                std::fs::create_dir_all(parent)?;
            }
        }

        let connection = Connection::open(path)?;
        let sqlcipher_passphrase = encode_key(key);
        connection.pragma_update(None, "key", sqlcipher_passphrase)?;
        connection.pragma_update(None, "cipher_memory_security", "ON")?;
        // Forces SQLCipher to authenticate the key before migrations run. A
        // wrong key fails here instead of producing a misleading empty schema.
        connection.query_row("SELECT count(*) FROM sqlite_master", [], |_| Ok(()))?;
        connection.pragma_update(None, "journal_mode", "WAL")?;
        connection.pragma_update(None, "foreign_keys", "ON")?;
        connection.execute_batch(include_str!("../migrations/0001_init.sql"))?;

        Ok(Self {
            connection: Mutex::new(connection),
        })
    }

    pub fn password_hash(&self) -> Result<Option<String>, StoreError> {
        let connection = self.connection.lock().map_err(|_| StoreError::Poisoned)?;
        connection
            .query_row(
                "SELECT password_hash FROM auth_metadata WHERE id = 1",
                [],
                |row| row.get(0),
            )
            .optional()
            .map_err(StoreError::from)
    }

    pub fn set_password_hash(&self, password_hash: &str) -> Result<(), StoreError> {
        let connection = self.connection.lock().map_err(|_| StoreError::Poisoned)?;
        connection.execute(
            "INSERT INTO auth_metadata (id, password_hash) VALUES (1, ?1)\
             ON CONFLICT(id) DO UPDATE SET\
               password_hash = excluded.password_hash,\
               updated_at = unixepoch()",
            params![password_hash],
        )?;
        Ok(())
    }

    pub fn insert_download(
        &self,
        id: Uuid,
        url: &str,
        destination: &Path,
        total_bytes: Option<u64>,
    ) -> Result<(), StoreError> {
        let connection = self.connection.lock().map_err(|_| StoreError::Poisoned)?;
        connection.execute(
            "INSERT INTO downloads (id, url, destination, total_bytes, status)\
             VALUES (?1, ?2, ?3, ?4, 'queued')\
             ON CONFLICT(id) DO UPDATE SET\
               url = excluded.url,\
               destination = excluded.destination,\
               total_bytes = excluded.total_bytes",
            params![
                id.to_string(),
                url,
                destination.to_string_lossy().to_string(),
                total_bytes.map(|value| value as i64),
            ],
        )?;
        Ok(())
    }

    pub fn update_progress(
        &self,
        id: Uuid,
        completed_bytes: u64,
        status: &str,
    ) -> Result<(), StoreError> {
        let connection = self.connection.lock().map_err(|_| StoreError::Poisoned)?;
        connection.execute(
            "UPDATE downloads\
             SET completed_bytes = ?2, status = ?3, updated_at = unixepoch()\
             WHERE id = ?1",
            params![id.to_string(), completed_bytes as i64, status],
        )?;
        Ok(())
    }

    pub fn update_status(&self, id: Uuid, status: &str) -> Result<(), StoreError> {
        let connection = self.connection.lock().map_err(|_| StoreError::Poisoned)?;
        connection.execute(
            "UPDATE downloads SET status = ?2, updated_at = unixepoch() WHERE id = ?1",
            params![id.to_string(), status],
        )?;
        Ok(())
    }

    pub fn record_chunk(
        &self,
        download_id: Uuid,
        chunk_index: usize,
        start_byte: u64,
        end_byte: u64,
        completed_bytes: u64,
        status: &str,
    ) -> Result<(), StoreError> {
        let connection = self.connection.lock().map_err(|_| StoreError::Poisoned)?;
        connection.execute(
            "INSERT INTO chunks\
             (download_id, chunk_index, start_byte, end_byte, completed_bytes, status)\
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)\
             ON CONFLICT(download_id, chunk_index) DO UPDATE SET\
               completed_bytes = excluded.completed_bytes,\
               status = excluded.status,\
               updated_at = unixepoch()",
            params![
                download_id.to_string(),
                chunk_index as i64,
                start_byte as i64,
                end_byte as i64,
                completed_bytes as i64,
                status,
            ],
        )?;
        Ok(())
    }
}

fn encode_key(key: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut encoded = String::with_capacity(key.len() * 2);
    for byte in key {
        encoded.push(HEX[(byte >> 4) as usize] as char);
        encoded.push(HEX[(byte & 0x0f) as usize] as char);
    }
    encoded
}
