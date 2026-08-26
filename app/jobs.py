"""
Job manager — in-memory job state, background execution, event bus for SSE.

A job is created by POST /api/jobs; the pipeline then runs as a background
asyncio task emitting structured events.  Subscribers (the UI) receive the
full event history plus live updates via GET /api/jobs/{id}/events.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from app.config import config
from app.database import Database

logger = logging.getLogger(__name__)

MAX_EVENTS_PER_JOB = 800


@dataclass
class JobState:
    job_id: str
    status: str = "queued"           # queued|running|done|error|cancelled
    created: float = field(default_factory=time.time)
    events: List[Dict[str, Any]] = field(default_factory=list)
    subscribers: List[asyncio.Queue] = field(default_factory=list)
    task: Optional[asyncio.Task] = None
    error: str = ""
    cancel_requested: bool = False

    def snapshot(self) -> Dict[str, Any]:
        return {"job_id": self.job_id, "status": self.status,
                "created": self.created, "error": self.error}


class JobManager:
    def __init__(self, db: Database):
        self.db = db
        self.jobs: Dict[str, JobState] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------- lifecycle
    async def create(self, query_bytes: bytes, filename: str, options: Dict[str, Any],
                     pipeline) -> Dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        state = JobState(job_id=job_id)
        async with self._lock:
            self.jobs[job_id] = state

        # Prepare query (blocking parts in a thread) — pipeline does the work
        prepared = await pipeline.prepare_query(job_id, query_bytes, filename, options)

        self.db.create_job({
            "id": job_id,
            "created_at": state.created,
            "status": "queued",
            "query_path": prepared["query_path"],
            "query_thumb": prepared["query_thumb"],
            "query_hash": prepared["query_hash"],
            "face_backend": prepared["face_backend"],
            "face_count": prepared["face_count"],
            "quality": prepared["quality"],
            "options": options,
        })

        state.status = "running"
        self.db.update_job(job_id, status="running")
        state.task = asyncio.create_task(self._run(state, pipeline, prepared, options))
        return {
            "job_id": job_id,
            "status": "running",
            "query": prepared["public"],
        }

    async def _run(self, state: JobState, pipeline, prepared, options) -> None:
        try:
            await pipeline.run(state, prepared, options)
            if state.cancel_requested:
                state.status = "cancelled"
                self.db.update_job(state.job_id, status="cancelled", finished_at=time.time())
            else:
                state.status = "done"
                self.db.update_job(state.job_id, status="done", finished_at=time.time())
            self.emit(state.job_id, "done", {"status": state.status})
        except asyncio.CancelledError:
            state.status = "cancelled"
            self.db.update_job(state.job_id, status="cancelled", finished_at=time.time())
            self.emit(state.job_id, "done", {"status": "cancelled"})
        except Exception as e:  # noqa: BLE001
            logger.exception("Job %s failed", state.job_id)
            state.status = "error"
            state.error = str(e)[:500]
            self.db.update_job(state.job_id, status="error", error=state.error,
                               finished_at=time.time())
            self.emit(state.job_id, "error", {"message": state.error})
        finally:
            await self._drain_subscribers(state.job_id)

    async def cancel(self, job_id: str) -> bool:
        state = self.jobs.get(job_id)
        if not state or state.status not in ("queued", "running"):
            return False
        state.cancel_requested = True
        if state.task:
            state.task.cancel()
        return True

    # ----------------------------------------------------------------- events
    def emit(self, job_id: str, type_: str, data: Dict[str, Any]) -> None:
        state = self.jobs.get(job_id)
        if state is None:
            return
        event = {
            "ts": round(time.time(), 3),
            "seq": len(state.events),
            "type": type_,
            "data": data,
        }
        state.events.append(event)
        if len(state.events) > MAX_EVENTS_PER_JOB:
            state.events = state.events[-MAX_EVENTS_PER_JOB:]
        for q in list(state.subscribers):
            try:
                q.put_nowait(event)
            except Exception:
                pass

    async def subscribe(self, job_id: str) -> Optional[AsyncIterator[Dict[str, Any]]]:
        state = self.jobs.get(job_id)
        if state is None:
            return None
        q: asyncio.Queue = asyncio.Queue()
        # replay history so late subscribers see everything
        for ev in list(state.events):
            q.put_nowait(ev)
        async with self._lock:
            state.subscribers.append(q)

        async def gen():
            try:
                idle = 0.0
                while True:
                    try:
                        ev = await asyncio.wait_for(q.get(), timeout=15.0)
                        idle = 0.0
                        yield ev
                        if ev["type"] in ("done", "error"):
                            return
                    except asyncio.TimeoutError:
                        idle += 15.0
                        # keepalive comment; close when job finished
                        if state.status in ("done", "error", "cancelled"):
                            return
                        yield None  # sentinel -> converted to keepalive by route
            finally:
                if q in state.subscribers:
                    state.subscribers.remove(q)

        return gen()

    async def _drain_subscribers(self, job_id: str) -> None:
        # ensure subscriber generators terminate: final event already emitted
        state = self.jobs.get(job_id)
        if not state:
            return
        await asyncio.sleep(0)

    # ------------------------------------------------------------------ reads
    def state(self, job_id: str) -> Optional[JobState]:
        return self.jobs.get(job_id)

    def active_count(self) -> int:
        return sum(1 for s in self.jobs.values() if s.status in ("queued", "running"))

    def cleanup_finished(self, older_than_s: float = 3600) -> None:
        now = time.time()
        for jid in list(self.jobs.keys()):
            s = self.jobs[jid]
            if s.status in ("done", "error", "cancelled") and now - s.created > older_than_s:
                self.jobs.pop(jid, None)
