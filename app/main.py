"""
FastAPI application — OSINT Face Search v2.

Routes
------
GET  /                        UI
GET  /api/system              system + engine diagnostics
GET  /api/stats               aggregate DB stats
POST /api/jobs                create search job (multipart image + options)
GET  /api/jobs                list jobs
GET  /api/jobs/{id}           job + results
GET  /api/jobs/{id}/results   results only
GET  /api/jobs/{id}/events    SSE progress stream
DELETE /api/jobs/{id}         cancel (running) or delete (finished)
GET  /api/jobs/{id}/export    json | csv | html evidence report
POST /api/verify              1:1 face verification (two images)
GET/POST /api/gallery         gallery identities
POST /api/gallery/{id}/images add reference image to identity
DELETE /api/gallery/images/{image_id}
POST /api/feedback
POST /api/demo                seed demo gallery + run demo search
"""
from __future__ import annotations

import asyncio
import csv
import html as html_mod
import io
import json
import logging
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import config
from app.database import Database
from app.engines import get_engine, registry_info
from app.face_engine import FaceEngine
from app.jobs import JobManager
from app.models import model_status
from app.pipeline import Pipeline
from app.utils import hashing as h
from app.utils.images import decode_image_bytes, draw_face_overlay, media_url, thumbnail_bytes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("osint")

app = FastAPI(title="OSINT Face Search", version="2.1.0")

db = Database(config.DB_PATH)
face_engine = FaceEngine()
jobs = JobManager(db)
pipeline = Pipeline(db, face_engine, jobs)

# Set by desktop_app.py so the UI "Shut down server" button can stop the
# hidden background server gracefully (None when run via run.py/uvicorn).
DESKTOP_SERVER = None


def set_desktop_server(server) -> None:
    global DESKTOP_SERVER
    DESKTOP_SERVER = server

# ------------------------------------------------------------------- mounts
for url, directory in (
    ("/static", config.STATIC_DIR),
    ("/media/uploads", config.UPLOAD_DIR),
    ("/media/candidates", config.CANDIDATE_DIR),
    ("/media/gallery", config.DATA_DIR / "gallery"),
    ("/media/demo", config.DEMO_DIR),
    ("/media/cache", config.CACHE_DIR),
):
    directory.mkdir(parents=True, exist_ok=True)
    app.mount(url, StaticFiles(directory=str(directory)), name=url.strip("/").replace("/", "_"))


@app.on_event("shutdown")
async def _shutdown() -> None:
    db.close()


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    path = config.STATIC_DIR / "index.html"
    if not path.exists():
        return HTMLResponse("<h1>OSINT Face Search</h1><p>static/index.html missing</p>", 500)
    return HTMLResponse(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------- system
_probe_cache: dict = {"ts": 0.0, "data": None}


@app.get("/api/system")
async def system_info() -> dict:
    engines = registry_info()
    now = time.time()
    if _probe_cache["data"] is None or now - _probe_cache["ts"] > 60:
        async def probe_one(meta):
            try:
                eng = get_engine(meta["key"])
                res = await asyncio.wait_for(eng.probe(), timeout=config.PROBE_TIMEOUT_S + 4)
                return {**meta, "available": res.available, "reason": res.reason}
            except Exception as e:  # noqa: BLE001
                return {**meta, "available": False, "reason": f"probe error: {e}"}
        _probe_cache["data"] = await asyncio.gather(*(probe_one(m) for m in engines))
        _probe_cache["ts"] = now
    return {
        "app": {"name": "OSINT Face Search", "version": "2.1.0"},
        "face": face_engine.info(),
        "verdict_bands": {
            "strong": config.VERDICT_STRONG,
            "possible": config.VERDICT_POSSIBLE,
            "weak": config.VERDICT_WEAK,
        },
        "models": model_status(config.MODEL_DIR),
        "engines": _probe_cache["data"],
        "limits": {
            "max_upload_mb": config.MAX_UPLOAD_MB,
            "max_candidates": config.MAX_CANDIDATES,
            "results_per_engine": config.MAX_RESULTS_PER_ENGINE,
            "download_concurrency": config.DOWNLOAD_CONCURRENCY,
        },
        "storage": _storage_stats(),
    }


def _storage_stats() -> dict:
    def dir_size(p: Path) -> int:
        total = 0
        if p.exists():
            for f in p.rglob("*"):
                if f.is_file():
                    try:
                        total += f.stat().st_size
                    except OSError:
                        pass
        return total

    return {
        "uploads_bytes": dir_size(config.UPLOAD_DIR),
        "candidates_bytes": dir_size(config.CANDIDATE_DIR),
        "gallery_bytes": dir_size(config.DATA_DIR / "gallery"),
        "quota_gb": config.MAX_STORAGE_GB,
    }


@app.get("/api/stats")
async def stats() -> dict:
    return db.stats()


@app.post("/api/system/shutdown")
async def shutdown_server():
    """Graceful shutdown for desktop mode (UI → System → Shut down server)."""
    if DESKTOP_SERVER is None:
        raise HTTPException(
            503, "Not running in desktop mode — stop the server with Ctrl+C"
        )
    loop = asyncio.get_running_loop()
    # small delay so the HTTP response is flushed before the server stops
    loop.call_later(0.6, setattr, DESKTOP_SERVER, "should_exit", True)
    return {"status": "shutting down", "note": "you can close this browser tab"}


# ------------------------------------------------------------------- analyze
@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)) -> dict:
    """Face analysis for the upload preview (count, quality, annotated thumb)."""
    data = await file.read()
    if len(data) > config.max_upload_bytes:
        raise HTTPException(413, f"Image larger than {config.MAX_UPLOAD_MB} MB")
    img = decode_image_bytes(data)
    if img is None:
        raise HTTPException(400, "Not a recognised image file")

    def process():
        faces = face_engine.detect(img)
        annotated = draw_face_overlay(img, [f.bbox for f in faces]) if faces else img
        tb = thumbnail_bytes(annotated, max_edge=config.THUMB_SIZE)
        url = ""
        if tb:
            p = config.CACHE_DIR / f"analyze_{int(time.time() * 1000)}.jpg"
            p.write_bytes(tb)
            url = f"/media/cache/{p.name}"
        best = max(faces, key=lambda f: f.quality) if faces else None
        return {
            "face_count": len(faces),
            "quality": round(best.quality, 3) if best else 0.0,
            "backend": face_engine.backend_name,
            "width": img.shape[1], "height": img.shape[0],
            "thumb": url,
            "faces": [
                {"bbox": list(f.bbox), "det": round(min(1.0, f.det_score), 3),
                 "quality": round(f.quality, 3)} for f in faces
            ],
        }

    return await asyncio.to_thread(process)


# --------------------------------------------------------------------- jobs
async def _create_job(query_bytes: bytes, filename: str, options: dict) -> dict:
    if not query_bytes:
        raise HTTPException(400, "Empty upload")
    if len(query_bytes) > config.max_upload_bytes:
        raise HTTPException(413, f"Image larger than {config.MAX_UPLOAD_MB} MB")
    if h.sniff_image_format(query_bytes) is None:
        raise HTTPException(400, "File is not a recognised image (jpeg/png/webp/gif/bmp)")
    try:
        return await jobs.create(query_bytes, filename, options, pipeline)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("job creation failed")
        raise HTTPException(500, f"Failed to create job: {e}") from e


@app.post("/api/jobs")
async def create_job(
    file: UploadFile = File(...),
    options: str = Form(""),
) -> dict:
    try:
        opts = json.loads(options) if options else {}
    except json.JSONDecodeError:
        raise HTTPException(400, "options must be valid JSON")
    if not isinstance(opts, dict):
        raise HTTPException(400, "options must be a JSON object")
    data = await file.read()
    return await _create_job(data, file.filename or "upload.jpg", opts)


@app.get("/api/jobs")
async def list_jobs(limit: int = Query(50, ge=1, le=200)) -> dict:
    return {"jobs": db.list_jobs(limit)}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    state = jobs.state(job_id)
    results = db.job_results(job_id)
    for r in results:
        r["thumb_url_media"] = _media_url(r.get("thumb_path") or r.get("image_path"))
        r["image_url_media"] = _media_url(r.get("image_path"))
    job["results"] = results
    job["live"] = bool(state and state.status in ("queued", "running"))
    if state:
        job["error"] = state.error or job.get("error", "")
    return job


def _media_url(rel: str) -> str:
    if not rel:
        return ""
    return media_url(rel)


@app.get("/api/jobs/{job_id}/results")
async def job_results(job_id: str) -> dict:
    if db.get_job(job_id) is None:
        raise HTTPException(404, "job not found")
    results = db.job_results(job_id)
    for r in results:
        r["thumb_url_media"] = _media_url(r.get("thumb_path") or r.get("image_path"))
        r["image_url_media"] = _media_url(r.get("image_path"))
    return {"job_id": job_id, "results": results}


@app.delete("/api/jobs/{job_id}")
async def cancel_or_delete(job_id: str) -> dict:
    state = jobs.state(job_id)
    if state and state.status in ("queued", "running"):
        ok = await jobs.cancel(job_id)
        return {"cancelled": ok}
    if db.get_job(job_id) is None:
        raise HTTPException(404, "job not found")
    db.delete_job(job_id)
    jobs.jobs.pop(job_id, None)
    return {"deleted": True}


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    gen = await jobs.subscribe(job_id)
    if gen is None:
        # job not in memory (server restarted?) — emit synthetic terminal event
        job = db.get_job(job_id)
        if job is None:
            raise HTTPException(404, "job not found")
        payload = {
            "ts": time.time(), "seq": 0, "type": "done",
            "data": {"status": job["status"], "note": "replayed from database"},
        }

        async def replay():
            yield f"data: {json.dumps(payload)}\n\n"

        return StreamingResponse(replay(), media_type="text/event-stream")

    async def stream():
        async for ev in gen:
            if ev is None:
                yield ": keepalive\n\n"
            else:
                yield f"data: {json.dumps(ev, default=str)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ------------------------------------------------------------------- export
@app.get("/api/jobs/{job_id}/export")
async def export_job(job_id: str, fmt: str = Query("json", pattern="^(json|csv|html)$")):
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    results = db.job_results(job_id)
    for r in results:
        r["thumb_url_media"] = _media_url(r.get("thumb_path") or r.get("image_path"))
    stamp = time.strftime("%Y%m%d_%H%M%S")

    if fmt == "json":
        payload = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "job": {k: v for k, v in job.items() if k != "results"},
            "results": results,
        }
        return JSONResponse(
            payload,
            headers={"Content-Disposition": f'attachment; filename="osint_job_{job_id}_{stamp}.json"'},
        )

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "rank", "url", "source_url", "domain", "title", "engines",
            "similarity", "confidence", "verdict", "faces", "query_duplicate",
            "source_kind",
        ])
        for i, r in enumerate(results, 1):
            writer.writerow([
                i, r["url"], r["source_url"], r["domain"], r["title"],
                "|".join(r["engines"]), r.get("similarity") if r.get("similarity") is not None else "",
                r["confidence"], r["verdict"], r["face_count"],
                "yes" if r["is_query_dup"] else "no", r["source_kind"],
            ])
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="osint_job_{job_id}_{stamp}.csv"'},
        )

    # HTML evidence report with embedded thumbnails (portable single file)
    def b64_thumb(r: dict) -> str:
        import base64
        p = config.BASE_DIR / (r.get("thumb_path") or r.get("image_path") or "")
        try:
            if p.exists():
                return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()
        except Exception:
            pass
        return ""

    rows_html = []
    for i, r in enumerate(results, 1):
        thumb = b64_thumb(r)
        img_tag = f'<img src="{thumb}" alt="">' if thumb else '<div class="noimg">no image</div>'
        sim = f"{(r.get('similarity') or 0):.3f}" if r.get("similarity") is not None else "—"
        rows_html.append(f"""
        <div class="card verdict-{r['verdict']}">
          <div class="thumb">{img_tag}</div>
          <div class="meta">
            <div class="rank">#{i} · <span class="badge">{r['verdict'].upper()}</span>
              · {r['confidence']}% · cos {sim}</div>
            <div class="title">{html_mod.escape(r['title'] or r['domain'] or r['url'])}</div>
            <div class="url">{html_mod.escape(r['url'][:160])}</div>
            <div class="engines">{', '.join(r['engines'])} · {html_mod.escape(r['domain'])}</div>
          </div>
        </div>""")

    qb64 = ""
    try:
        import base64
        qp = config.BASE_DIR / job["query_thumb"]
        if qp.exists():
            qb64 = "data:image/jpeg;base64," + base64.b64encode(qp.read_bytes()).decode()
    except Exception:
        pass

    stats = job.get("stats", {})
    html_doc = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>OSINT report {job_id}</title>
<style>
 body{{background:#0b0e14;color:#dbe2ee;font-family:system-ui,Segoe UI,sans-serif;margin:32px;}}
 h1{{font-size:20px}} .sub{{color:#8b95a7;font-size:13px;margin-bottom:24px}}
 .query{{display:flex;gap:20px;align-items:center;background:#11151d;padding:16px;border-radius:12px;margin-bottom:24px}}
 .query img{{width:180px;border-radius:8px}}
 .card{{display:flex;gap:14px;background:#11151d;border:1px solid #1e2530;border-radius:12px;padding:12px;margin-bottom:10px}}
 .thumb img{{width:140px;height:140px;object-fit:cover;border-radius:8px}}
 .noimg{{width:140px;height:140px;display:flex;align-items:center;justify-content:center;color:#556;border-radius:8px;background:#0d1117}}
 .badge{{padding:2px 8px;border-radius:99px;font-size:11px;background:#1e2a3a}}
 .verdict-strong .badge{{background:#14532d;color:#86efac}}
 .verdict-possible .badge{{background:#713f12;color:#fde047}}
 .meta{{font-size:13px}} .title{{font-weight:600;margin:6px 0 2px}}
 .url{{color:#8b95a7;word-break:break-all;font-family:ui-monospace,monospace;font-size:11px}}
 .engines{{color:#8b95a7;margin-top:4px;font-size:12px}}
 .stats span{{display:inline-block;background:#11151d;border-radius:8px;padding:6px 12px;margin:0 8px 8px 0;font-size:12px}}
</style></head><body>
<h1>OSINT Face Search — Evidence Report</h1>
<div class="sub">Job {job_id} · generated {time.strftime('%Y-%m-%d %H:%M:%S')} ·
 backend {job.get('face_backend') or 'n/a'}</div>
<div class="query">{f'<img src="{qb64}">' if qb64 else ''}
 <div><b>Query image</b><br>faces detected: {job['face_count']} · quality {job['quality']}<br>
 SHA-256: <span class="url">{job['query_hash']}</span></div></div>
<div class="stats"><span>engines queried: {len(stats.get('engines', {}))}</span>
 <span>candidates: {stats.get('candidates_found', 0)}</span>
 <span>downloaded: {stats.get('downloaded', 0)}</span>
 <span>results: {len(results)}</span>
 <span>strong: {stats.get('strong', 0)}</span>
 <span>possible: {stats.get('possible', 0)}</span></div>
{''.join(rows_html) or '<p>No results.</p>'}
<p style="color:#8b95a7;font-size:11px;margin-top:32px">Generated locally by OSINT Face Search.
 Similarity scores are cosine distances between face embeddings and are probabilistic indicators,
 not proof of identity.</p>
</body></html>"""
    return HTMLResponse(
        html_doc,
        headers={"Content-Disposition": f'attachment; filename="osint_job_{job_id}_{stamp}.html"'},
    )


# ------------------------------------------------------------------- verify
@app.post("/api/verify")
async def verify_two(file1: UploadFile = File(...), file2: UploadFile = File(...)) -> dict:
    if not face_engine.available:
        raise HTTPException(503, "Face engine unavailable: " + (face_engine.info().get("error") or ""))
    out = {}
    thumbs = []
    for i, f in enumerate((file1, file2), 1):
        data = await f.read()
        if len(data) > config.max_upload_bytes:
            raise HTTPException(413, f"Image {i} too large")
        img = decode_image_bytes(data)
        if img is None:
            raise HTTPException(400, f"Image {i} is not a valid image")
        face = await asyncio.to_thread(face_engine.best_face, img)
        entry = {
            "face_found": face is not None,
            "det_score": round(face.det_score, 3) if face else None,
            "quality": round(face.quality, 3) if face else 0.0,
            "bbox": list(face.bbox) if face else None,
        }
        annotated = draw_face_overlay(img, [face.bbox], labels=[f"face {i}"]) if face else img
        tb = await asyncio.to_thread(thumbnail_bytes, annotated, 420)
        if tb:
            p = config.CACHE_DIR / f"verify_{int(time.time())}_{i}.jpg"
            p.write_bytes(tb)
            entry["thumb"] = f"/media/cache/{p.name}"
            thumbs.append(p.name)
        out[f"image{i}"] = entry
        if face is not None:
            out[f"emb{i}"] = face.embedding

    sim = None
    if "emb1" in out and "emb2" in out:
        sim = FaceEngine.similarity(out.pop("emb1"), out.pop("emb2"))
    out.pop("emb1", None)
    out.pop("emb2", None)
    out["similarity"] = round(sim, 4) if sim is not None else None
    out["verdict"] = FaceEngine.verdict_for(sim)
    out["confidence"] = FaceEngine.confidence(sim)
    return out


# ------------------------------------------------------------------ gallery
@app.get("/api/gallery")
async def gallery_list() -> dict:
    items = db.gallery_list()
    for ident in items:
        for img in ident["images"]:
            img["thumb"] = _media_url(img.get("thumb_path") or img.get("path"))
    return {"gallery": items}


@app.post("/api/gallery")
async def gallery_create(name: str = Form(...), notes: str = Form("")) -> dict:
    name = (name or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    return db.gallery_add_identity(name[:80], (notes or "")[:500])


@app.post("/api/gallery/{gallery_id}/images")
async def gallery_add_image(gallery_id: str, file: UploadFile = File(...)) -> dict:
    if not any(g["id"] == gallery_id for g in db.gallery_list()):
        raise HTTPException(404, "gallery identity not found")
    data = await file.read()
    if len(data) > config.max_upload_bytes:
        raise HTTPException(413, "Image too large")
    img = decode_image_bytes(data)
    if img is None:
        raise HTTPException(400, "Not a valid image")

    def process():
        import hashlib
        from app.utils.images import normalize_image
        gid_dir = config.DATA_DIR / "gallery" / gallery_id
        gid_dir.mkdir(parents=True, exist_ok=True)
        cid = hashlib.sha1(data).hexdigest()[:12]
        path = gid_dir / f"{cid}.jpg"
        path.write_bytes(normalize_image(img, max_edge=1280))

        face = face_engine.best_face(img)
        annotated = draw_face_overlay(img, [face.bbox]) if face else img
        tb = thumbnail_bytes(annotated, max_edge=config.THUMB_SIZE)
        thumb_path = gid_dir / f"{cid}_t.jpg"
        if tb:
            thumb_path.write_bytes(tb)
        else:
            thumb_path = path
        return {
            "path": str(path.relative_to(config.BASE_DIR)),
            "thumb_path": str(thumb_path.relative_to(config.BASE_DIR)),
            "sha256": hashlib.sha256(data).hexdigest(),
            "phash": h.phash_from_array(img) or "",
            "embedding": face.embedding if face else None,
            "face_count": 1 if face else 0,
            "face_found": face is not None,
            "quality": round(face.quality, 3) if face else 0.0,
        }

    info = await asyncio.to_thread(process)
    if not info["face_found"]:
        # still store (embedding may come later) but flag it
        logger.info("gallery image without face: %s", file.filename)
    image_id = db.gallery_add_image(
        gallery_id, info["path"], info["thumb_path"], info["sha256"],
        info["phash"], info["embedding"], info["face_count"],
    )
    return {
        "image_id": image_id, "face_found": info["face_found"],
        "quality": info["quality"],
        "thumb": _media_url(info["thumb_path"]),
    }


@app.delete("/api/gallery/{gallery_id}")
async def gallery_delete(gallery_id: str) -> dict:
    db.gallery_delete_identity(gallery_id)
    return {"deleted": True}


@app.delete("/api/gallery/images/{image_id}")
async def gallery_image_delete(image_id: str) -> dict:
    db.gallery_delete_image(image_id)
    return {"deleted": True}


# ------------------------------------------------------------------ feedback
@app.post("/api/feedback")
async def feedback(job_id: str = Form(...), result_url: str = Form(...),
                   is_correct: bool = Form(...), comment: str = Form("")) -> dict:
    db.add_feedback(job_id, result_url, is_correct, comment[:500])
    return {"status": "ok"}


# ---------------------------------------------------------------------- demo
DEMO_QUERY = "subject_a_base.jpg"
DEMO_VARIANTS = ["subject_a_variant_1.jpg", "subject_a_variant_2.jpg"]
DEMO_DISTRACTORS = {
    "subject_b_1.jpg": "Demo · Person B",
    "subject_c_1.jpg": "Demo · Person C",
    "subject_d_1.jpg": "Demo · Person D",
    "subject_e_1.jpg": "Demo · Person E",
}


@app.get("/api/demo/available")
async def demo_available() -> dict:
    return {"available": (config.DEMO_DIR / DEMO_QUERY).exists()}


@app.post("/api/demo")
async def run_demo() -> dict:
    qpath = config.DEMO_DIR / DEMO_QUERY
    if not qpath.exists():
        raise HTTPException(404, "Demo images not bundled")
    data = qpath.read_bytes()

    # seed gallery once
    existing = {g["name"] for g in db.gallery_list()}
    if "Demo · Subject A" not in existing:
        ident = db.gallery_add_identity("Demo · Subject A", "Auto-seeded demo identity")
        for v in DEMO_VARIANTS:
            vp = config.DEMO_DIR / v
            if vp.exists():
                await _gallery_add_path(ident["id"], vp)
    for fname, name in DEMO_DISTRACTORS.items():
        if name not in existing and (config.DEMO_DIR / fname).exists():
            ident = db.gallery_add_identity(name, "Auto-seeded demo distractor")
            await _gallery_add_path(ident["id"], config.DEMO_DIR / fname)

    return await _create_job(data, DEMO_QUERY, {
        "engines": [e["key"] for e in registry_info()],
        "include_gallery": True,
        "demo": True,
    })


async def _gallery_add_path(gallery_id: str, path: Path) -> None:
    data = path.read_bytes()
    img = decode_image_bytes(data)
    if img is None:
        return

    def process():
        import hashlib
        from app.utils.images import normalize_image
        gid_dir = config.DATA_DIR / "gallery" / gallery_id
        gid_dir.mkdir(parents=True, exist_ok=True)
        cid = hashlib.sha1(data).hexdigest()[:12]
        p = gid_dir / f"{cid}.jpg"
        p.write_bytes(normalize_image(img, max_edge=1280))
        face = face_engine.best_face(img)
        annotated = draw_face_overlay(img, [face.bbox]) if face else img
        tb = thumbnail_bytes(annotated, max_edge=config.THUMB_SIZE)
        tp = gid_dir / f"{cid}_t.jpg"
        if tb:
            tp.write_bytes(tb)
        else:
            tp = p
        return p, tp, face

    p, tp, face = await asyncio.to_thread(process)
    db.gallery_add_image(
        gallery_id, str(p.relative_to(config.BASE_DIR)), str(tp.relative_to(config.BASE_DIR)),
        h.sha256_bytes(data), h.phash_from_array(img) or "",
        face.embedding if face else None, 1 if face else 0,
    )
