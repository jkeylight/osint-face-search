"""
SQLite persistence (WAL mode) — jobs, results, gallery, feedback.

All access is funneled through an asyncio-friendly wrapper that runs
blocking sqlite calls in a thread executor behind a single connection
guarded by a lock.  Sufficient for a single-user local tool.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from app.config import config

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    created_at    REAL NOT NULL,
    finished_at   REAL,
    status        TEXT NOT NULL,             -- queued|running|done|error|cancelled
    query_path    TEXT NOT NULL,
    query_thumb   TEXT NOT NULL DEFAULT '',
    query_hash    TEXT NOT NULL,
    face_backend  TEXT NOT NULL DEFAULT '',
    face_count    INTEGER NOT NULL DEFAULT 0,
    quality       REAL NOT NULL DEFAULT 0,
    options       TEXT NOT NULL DEFAULT '{}',
    stats         TEXT NOT NULL DEFAULT '{}',
    error         TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS results (
    id            TEXT PRIMARY KEY,
    job_id        TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    url           TEXT NOT NULL,
    source_url    TEXT NOT NULL DEFAULT '',
    domain        TEXT NOT NULL DEFAULT '',
    title         TEXT NOT NULL DEFAULT '',
    engines       TEXT NOT NULL DEFAULT '[]',
    image_path    TEXT NOT NULL DEFAULT '',
    thumb_path    TEXT NOT NULL DEFAULT '',
    similarity    REAL,
    confidence    REAL NOT NULL DEFAULT 0,
    verdict       TEXT NOT NULL DEFAULT 'unknown',
    face_count    INTEGER NOT NULL DEFAULT 0,
    bbox          TEXT,
    width         INTEGER NOT NULL DEFAULT 0,
    height        INTEGER NOT NULL DEFAULT 0,
    phash         TEXT NOT NULL DEFAULT '',
    is_query_dup  INTEGER NOT NULL DEFAULT 0,
    source_kind   TEXT NOT NULL DEFAULT 'unknown',
    rank_score    REAL NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL,
    UNIQUE (job_id, url)
);
CREATE INDEX IF NOT EXISTS idx_results_job ON results(job_id);

CREATE TABLE IF NOT EXISTS gallery (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    notes       TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS gallery_images (
    id          TEXT PRIMARY KEY,
    gallery_id  TEXT NOT NULL REFERENCES gallery(id) ON DELETE CASCADE,
    path        TEXT NOT NULL,
    thumb_path  TEXT NOT NULL DEFAULT '',
    sha256      TEXT NOT NULL DEFAULT '',
    phash       TEXT NOT NULL DEFAULT '',
    embedding   BLOB,
    face_count  INTEGER NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gallery_images ON gallery_images(gallery_id);

CREATE TABLE IF NOT EXISTS feedback (
    id          TEXT PRIMARY KEY,
    job_id      TEXT NOT NULL,
    result_url  TEXT NOT NULL,
    is_correct  INTEGER NOT NULL,
    comment     TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);
"""


def _row_to_result(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["engines"] = json.loads(d.get("engines") or "[]")
    d["similarity"] = round(d["similarity"], 4) if d.get("similarity") is not None else None
    if d.get("bbox"):
        try:
            d["bbox"] = json.loads(d["bbox"])
        except Exception:
            d["bbox"] = None
    return d


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._aio_lock = asyncio.Lock()
        self._init()

    # ------------------------------------------------------------------ setup
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False, timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init(self) -> None:
        with self._lock:
            self._conn = self._connect()
            self._conn.executescript(SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        """Lightweight forward migration: add columns introduced after v2.0."""
        migrations = {
            "results": {
                "rank_score": "REAL NOT NULL DEFAULT 0",
                "source_kind": "TEXT NOT NULL DEFAULT 'unknown'",
                "is_query_dup": "INTEGER NOT NULL DEFAULT 0",
            },
            "jobs": {"face_backend": "TEXT NOT NULL DEFAULT ''"},
        }
        for table, cols in migrations.items():
            try:
                rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
                existing = {r[1] for r in rows}
                for col, ddl in cols.items():
                    if col not in existing:
                        self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
                        logger.info("migrated: added %s.%s", table, col)
            except Exception as e:  # noqa: BLE001
                logger.warning("migration check failed for %s: %s", table, e)

    def close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    # ------------------------------------------------------------- sync core
    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _query(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    async def run(self, fn, *args):
        """Run a blocking DB function in the executor."""
        async with self._aio_lock:
            return await asyncio.to_thread(fn, *args)

    # ------------------------------------------------------------------ jobs
    def create_job(self, job: Dict[str, Any]) -> None:
        self._execute(
            """INSERT INTO jobs (id, created_at, status, query_path, query_thumb,
               query_hash, face_backend, face_count, quality, options)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                job["id"], job["created_at"], job.get("status", "queued"),
                job["query_path"], job.get("query_thumb", ""), job["query_hash"],
                job.get("face_backend", ""), job.get("face_count", 0),
                job.get("quality", 0.0), json.dumps(job.get("options", {})),
            ),
        )

    def update_job(self, job_id: str, **fields) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        self._execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id))

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        rows = self._query("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not rows:
            return None
        d = dict(rows[0])
        d["options"] = json.loads(d.get("options") or "{}")
        d["stats"] = json.loads(d.get("stats") or "{}")
        return d

    def list_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self._query(
            "SELECT j.*, COUNT(r.id) AS result_count FROM jobs j "
            "LEFT JOIN results r ON r.job_id=j.id "
            "GROUP BY j.id ORDER BY j.created_at DESC LIMIT ?", (limit,)
        )
        out = []
        for r in rows:
            d = dict(r)
            d["options"] = json.loads(d.get("options") or "{}")
            d["stats"] = json.loads(d.get("stats") or "{}")
            out.append(d)
        return out

    def delete_job(self, job_id: str) -> None:
        rows = self._query("SELECT query_path FROM jobs WHERE id=?", (job_id,))
        self._execute("DELETE FROM jobs WHERE id=?", (job_id,))  # cascade results
        for r in rows:
            try:
                Path(r["query_path"]).unlink(missing_ok=True)
            except Exception:
                pass
        import shutil
        try:
            shutil.rmtree(config.CANDIDATE_DIR / job_id, ignore_errors=True)
        except Exception:
            pass

    # --------------------------------------------------------------- results
    def insert_results(self, job_id: str, results: List[Dict[str, Any]]) -> None:
        now = time.time()
        rows = []
        for r in results:
            rows.append((
                f"{job_id[:6]}-{uuid.uuid4().hex[:10]}", job_id, r["url"],
                r.get("source_url", ""), r.get("domain", ""), r.get("title", ""),
                json.dumps(r.get("engines", [])), r.get("image_path", ""),
                r.get("thumb_path", ""), r.get("similarity"), r.get("confidence", 0.0),
                r.get("verdict", "unknown"), r.get("face_count", 0),
                json.dumps(r["bbox"]) if r.get("bbox") else None,
                r.get("width", 0), r.get("height", 0), r.get("phash", ""),
                1 if r.get("is_query_dup") else 0, r.get("source_kind", "unknown"),
                r.get("rank_score", 0.0), now,
            ))
        with self._lock:
            self._conn.executemany(
                """INSERT OR IGNORE INTO results (id, job_id, url, source_url, domain, title,
                   engines, image_path, thumb_path, similarity, confidence, verdict, face_count,
                   bbox, width, height, phash, is_query_dup, source_kind, rank_score, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                rows,
            )
            self._conn.commit()

    def job_results(self, job_id: str) -> List[Dict[str, Any]]:
        rows = self._query(
            "SELECT * FROM results WHERE job_id=? ORDER BY similarity DESC", (job_id,)
        )
        return [_row_to_result(r) for r in rows]

    # --------------------------------------------------------------- gallery
    def gallery_add_identity(self, name: str, notes: str = "") -> Dict[str, Any]:
        gid = uuid.uuid4().hex[:12]
        self._execute(
            "INSERT INTO gallery (id, name, notes, created_at) VALUES (?,?,?,?)",
            (gid, name, notes, time.time()),
        )
        return {"id": gid, "name": name, "notes": notes, "images": []}

    def gallery_add_image(
        self, gallery_id: str, path: str, thumb_path: str, sha256: str,
        phash: str, embedding: Optional[np.ndarray], face_count: int,
    ) -> str:
        img_id = uuid.uuid4().hex[:12]
        emb_blob = embedding.astype(np.float32).tobytes() if embedding is not None else None
        self._execute(
            """INSERT INTO gallery_images (id, gallery_id, path, thumb_path, sha256, phash,
               embedding, face_count, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (img_id, gallery_id, path, thumb_path, sha256, phash, emb_blob,
             face_count, time.time()),
        )
        return img_id

    def gallery_list(self) -> List[Dict[str, Any]]:
        identities = [dict(r) for r in self._query(
            "SELECT * FROM gallery ORDER BY created_at DESC"
        )]
        images = self._query(
            "SELECT id, gallery_id, path, thumb_path, phash, face_count, created_at "
            "FROM gallery_images"
        )
        by_id: Dict[str, List[Dict[str, Any]]] = {i["id"]: [] for i in identities}
        for r in images:
            d = dict(r)
            d["has_embedding"] = True
            if d["gallery_id"] in by_id:
                by_id[d["gallery_id"]].append(d)
        for ident in identities:
            ident["images"] = by_id.get(ident["id"], [])
        return identities

    def gallery_delete_identity(self, gallery_id: str) -> None:
        rows = self._query("SELECT path, thumb_path FROM gallery_images WHERE gallery_id=?", (gallery_id,))
        self._execute("DELETE FROM gallery WHERE id=?", (gallery_id,))
        import shutil
        for r in rows:
            for p in ("path", "thumb_path"):
                try:
                    if r[p]:
                        Path(r[p]).unlink(missing_ok=True)
                except Exception:
                    pass
        # remove now-orphaned gallery image dirs
        try:
            base = config.DATA_DIR / "gallery"
            shutil.rmtree(base / gallery_id, ignore_errors=True)
        except Exception:
            pass

    def gallery_delete_image(self, image_id: str) -> None:
        rows = self._query("SELECT path, thumb_path FROM gallery_images WHERE id=?", (image_id,))
        self._execute("DELETE FROM gallery_images WHERE id=?", (image_id,))
        for r in rows:
            for p in ("path", "thumb_path"):
                try:
                    if r[p]:
                        Path(r[p]).unlink(missing_ok=True)
                except Exception:
                    pass

    def gallery_embeddings(self) -> List[Dict[str, Any]]:
        """Flattened (embedding, identity, image) rows for the verifier."""
        rows = self._query(
            """SELECT gi.id AS image_id, gi.gallery_id, g.name, gi.path, gi.thumb_path,
                      gi.embedding, gi.face_count
               FROM gallery_images gi JOIN gallery g ON g.id = gi.gallery_id"""
        )
        out = []
        for r in rows:
            emb = None
            if r["embedding"] is not None:
                try:
                    emb = np.frombuffer(r["embedding"], dtype=np.float32)
                except Exception:
                    emb = None
            if emb is None or emb.size == 0:
                continue
            out.append({
                "image_id": r["image_id"], "gallery_id": r["gallery_id"],
                "identity": r["name"], "path": r["path"], "thumb_path": r["thumb_path"],
                "embedding": emb,
            })
        return out

    # -------------------------------------------------------------- feedback
    def add_feedback(self, job_id: str, result_url: str, is_correct: bool, comment: str = "") -> None:
        self._execute(
            "INSERT INTO feedback (id, job_id, result_url, is_correct, comment, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (uuid.uuid4().hex[:12], job_id, result_url, 1 if is_correct else 0,
             comment, time.time()),
        )

    # ------------------------------------------------------------------ stats
    def stats(self) -> Dict[str, Any]:
        jobs = self._query("SELECT COUNT(*) c FROM jobs")[0]["c"]
        results = self._query("SELECT COUNT(*) c FROM results")[0]["c"]
        matches = self._query(
            "SELECT COUNT(*) c FROM results WHERE verdict IN ('strong','possible')"
        )[0]["c"]
        gallery = self._query("SELECT COUNT(*) c FROM gallery")[0]["c"]
        feedback = self._query("SELECT COUNT(*) c FROM feedback")[0]["c"]
        return {
            "jobs": jobs, "results": results, "matches": matches,
            "gallery_identities": gallery, "feedback": feedback,
        }

    def prune_old_jobs(self, days: int) -> int:
        cutoff = time.time() - days * 86400
        old = self._query("SELECT id FROM jobs WHERE created_at < ?", (cutoff,))
        for r in old:
            self.delete_job(r["id"])
        return len(old)
