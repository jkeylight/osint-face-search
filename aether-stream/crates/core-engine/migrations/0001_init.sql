CREATE TABLE IF NOT EXISTS downloads (
    id              TEXT PRIMARY KEY NOT NULL,
    url             TEXT NOT NULL,
    destination     TEXT NOT NULL,
    total_bytes     INTEGER,
    completed_bytes INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'queued',
    created_at      INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at      INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS chunks (
    download_id     TEXT NOT NULL REFERENCES downloads(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    start_byte      INTEGER NOT NULL,
    end_byte        INTEGER NOT NULL,
    completed_bytes INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending',
    updated_at      INTEGER NOT NULL DEFAULT (unixepoch()),
    PRIMARY KEY (download_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status);
CREATE INDEX IF NOT EXISTS idx_chunks_download ON chunks(download_id);
