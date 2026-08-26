# PROJECT — OSINT Face Search v2

## Goal

A local-first OSINT workbench: give it a face photo, get back *verified* hits
from reverse image engines — with all face recognition running on your machine.

## Architecture

```
┌───────────── static/ (SPA) ─────────────┐
│  Search · Job/Results · Gallery ·       │
│  Verify 1:1 · History · System          │
└──────────────┬──────────────────────────┘
               │ REST + SSE
┌──────────────▼──────────────────────────┐
│ app/main.py  (FastAPI routes)           │
│ app/jobs.py  (job manager + event bus)  │
│ app/pipeline.py (orchestrator)          │
│    │              │               │     │
│    │         app/engines/    app/face_engine.py
│    │         (adapters:      (YuNet+SFace │ InsightFace)
│    │          browser/HTTP)  app/models.py (download/mirrors)
│    ▼                                   │
│ app/database.py (SQLite WAL)  ◀─────────┘
└─────────────────────────────────────────┘
```

### Request flow (one search)

1. `POST /api/jobs` — image uploaded, decoded, normalised; faces detected;
   query + face-crop + annotated thumbnail persisted; job row created.
2. Background task per job:
   - **engines** — probe + search each enabled engine (bounded concurrency,
     hard timeout); candidates merged by URL with engine consensus.
   - **download** — bounded parallel fetch with magic-byte sniffing.
   - **verify** — face detection + embedding cosine vs query (thread pool);
     pHash near-duplicate clustering; verdict + confidence per result.
   - **gallery** — query embedding vs all gallery identities.
   - **rank & persist** — relevance score, SQLite insert, stats JSON.
3. Every step emits events; `GET /api/jobs/{id}/events` streams them (SSE)
   with full history replay for late subscribers.

### Key design rules

- **Degrade, never crash**: every engine/dependency/network failure becomes a
  visible status with a reason.
- **Blocking work off the event loop**: cv2 calls run via `asyncio.to_thread`
  with semaphores.
- **No fake features**: engines that cannot work are not shipped.
- **Local by default**: only the enabled engines see the query crop; nothing
  else leaves the machine.

## Testing

- `tests/test_hashing.py`, `tests/test_utils.py` — pure logic.
- `tests/test_face_engine.py` — gated on bundled models + demo images.
- `tests/test_api.py` — full API via in-process TestClient, including an
  end-to-end gallery-match job.

Run: `python -m pytest tests/ -q`
