"""
Search pipeline — orchestrates engines, downloads, face verification,
ranking, and persistence for a single job.

Design goals:
  * every stage emits progress events (SSE)
  * every failure is recorded as status, never crashes the job
  * blocking CV work runs in a thread pool; IO is async
  * results are deduplicated by URL and by perceptual hash
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from app.config import config
from app.database import Database
from app.engines import get_engine, registry_info
from app.engines.base import Candidate, SearchContext
from app.engines.browser import browser_manager
from app.face_engine import FaceEngine, Face
from app.utils import domains as dom
from app.utils import hashing as h
from app.utils.images import (
    clamp_bbox, crop_bbox, draw_face_overlay, media_url, normalize_image,
    thumbnail_bytes,
)

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, db: Database, face_engine: FaceEngine, jobs):
        self.db = db
        self.faces = face_engine
        self.jobs = jobs

    # ================================================================ prepare
    async def prepare_query(self, job_id: str, data: bytes, filename: str,
                            options: Dict[str, Any]) -> Dict[str, Any]:
        """Decode, normalise, detect faces; persist query artefacts."""
        def blocking() -> Dict[str, Any]:
            from app.utils.images import decode_image_bytes
            img = decode_image_bytes(data)
            if img is None:
                raise ValueError("Unsupported or corrupt image file")
            h_, w_ = img.shape[:2]
            if min(h_, w_) < 40:
                raise ValueError("Image too small (min 40px)")

            qpath = config.UPLOAD_DIR / f"{job_id}.jpg"
            qpath.write_bytes(normalize_image(img, max_edge=1600, jpeg_quality=92))

            faces: List[Face] = self.faces.detect(img)
            best = self.faces.best_face(img) if faces else None

            thumb = draw_face_overlay(
                img, [f.bbox for f in faces[: config.MAX_FACES_PER_IMAGE]],
                labels=None,
            ) if faces else img
            tpath = config.UPLOAD_DIR / f"{job_id}_thumb.jpg"
            tb = thumbnail_bytes(thumb, max_edge=config.THUMB_SIZE)
            if tb:
                tpath.write_bytes(tb)

            face_path = ""
            if best is not None:
                crop = crop_bbox(img, best.bbox, pad=0.35)
                fb = normalize_image(crop, max_edge=800, jpeg_quality=92)
                fpath = config.UPLOAD_DIR / f"{job_id}_face.jpg"
                fpath.write_bytes(fb)
                face_path = str(fpath.relative_to(config.BASE_DIR))

            return {
                "query_path": str(qpath.relative_to(config.BASE_DIR)),
                "query_thumb": str(tpath.relative_to(config.BASE_DIR)),
                "face_path": face_path,
                "query_hash": hashlib.sha256(data).hexdigest(),
                "phash": h.phash_from_bytes(data) or "",
                "face_count": len(faces),
                "quality": round(best.quality, 3) if best else 0.0,
                "face_backend": self.faces.backend_name,
                "embedding": best.embedding if best is not None else None,
                "bbox": list(best.bbox) if best is not None else None,
                "width": w_, "height": h_,
                "bytes": len(data),
                "filename": filename,
                "public": {
                    "job_id": job_id,
                    "query_thumb": media_url(str(tpath.relative_to(config.BASE_DIR))),
                    "face_count": len(faces),
                    "quality": round(best.quality, 3) if best else 0.0,
                    "face_backend": self.faces.backend_name,
                    "width": w_, "height": h_,
                },
            }

        prepared = await asyncio.to_thread(blocking)
        prepared["event"] = None
        return prepared

    # ==================================================================== run
    async def run(self, state, prepared: Dict[str, Any], options: Dict[str, Any]) -> None:
        job_id = state.job_id
        emit = lambda type_, data=None: self.jobs.emit(job_id, type_, data or {})  # noqa: E731
        t0 = time.time()
        selected = options.get("engines") or [e["key"] for e in registry_info()]
        include_gallery = options.get("include_gallery", True)

        emit("phase", {"phase": "engines", "status": "start",
                       "engines": selected, "query": prepared["public"]})

        # ---------------------------------------------------------------- engines
        import aiohttp

        conn = aiohttp.TCPConnector(limit=config.DOWNLOAD_CONCURRENCY + 8, ttl_dns_cache=300)
        session = aiohttp.ClientSession(
            connector=conn,
            headers={"User-Agent": config.USER_AGENTS[0]},
            timeout=aiohttp.ClientTimeout(total=config.DOWNLOAD_TIMEOUT_S),
        )

        candidates: List[Candidate] = []
        engine_states: Dict[str, Dict[str, Any]] = {}
        engine_sem = asyncio.Semaphore(config.ENGINE_CONCURRENCY)

        async def run_engine(key: str) -> None:
            engine = get_engine(key)
            if engine is None:
                engine_states[key] = {"status": "skipped", "reason": "unknown engine"}
                emit("engine", {"engine": key, "status": "skipped",
                                "reason": "unknown engine"})
                return
            async with engine_sem:
                t = time.time()
                emit("engine", {"engine": key, "status": "running"})
                try:
                    probe = await engine.probe()
                    if not probe.available:
                        engine_states[key] = {"status": "unavailable",
                                              "reason": probe.reason, "ms": int((time.time() - t) * 1000)}
                        emit("engine", {"engine": key, "status": "unavailable",
                                        "reason": probe.reason})
                        return
                    ctx = SearchContext(
                        query_path=prepared["query_path"],
                        face_path=prepared["face_path"] or prepared["query_path"],
                        face_bbox=prepared.get("bbox"),
                        session=session,
                        browser=browser_manager,
                        emit=lambda k, d: emit("engine_log", {"engine": key, **d}),
                        max_results=config.MAX_RESULTS_PER_ENGINE,
                    )
                    found = await asyncio.wait_for(engine.search(ctx), timeout=config.ENGINE_TIMEOUT_S)
                    candidates.extend(found)
                    ms = int((time.time() - t) * 1000)
                    engine_states[key] = {"status": "done", "count": len(found), "ms": ms}
                    emit("engine", {"engine": key, "status": "done",
                                    "count": len(found), "ms": ms})
                except asyncio.TimeoutError:
                    engine_states[key] = {"status": "error", "reason": "timeout"}
                    emit("engine", {"engine": key, "status": "error", "reason": "timeout"})
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001
                    engine_states[key] = {"status": "error", "reason": str(e)[:200]}
                    emit("engine", {"engine": key, "status": "error",
                                    "reason": str(e)[:200]})

        await asyncio.gather(*(run_engine(k) for k in selected))

        emit("phase", {"phase": "engines", "status": "done",
                       "found": len(candidates),
                       "engines": engine_states})

        # ------------------------------------------------------ merge/dedupe urls
        merged: Dict[str, Dict[str, Any]] = {}
        for c in candidates:
            url = (c.image_url or "").strip()
            if not url.startswith("http"):
                continue
            entry = merged.setdefault(url, {
                "url": url, "source_url": c.source_url or "", "title": c.title or "",
                "engines": [], "thumb_url": c.thumb_url or "",
                "engine_score": 0.0,
            })
            if c.engine and c.engine not in entry["engines"]:
                entry["engines"].append(c.engine)
            if c.source_url and not entry["source_url"]:
                entry["source_url"] = c.source_url
            if c.title and not entry["title"]:
                entry["title"] = c.title
            entry["engine_score"] = max(entry["engine_score"], c.score)

        url_list = list(merged.values())
        url_list.sort(key=lambda e: (len(e["engines"]), e["engine_score"]), reverse=True)
        url_list = url_list[: config.MAX_CANDIDATES]

        emit("phase", {"phase": "download", "status": "start", "count": len(url_list)})

        # ---------------------------------------------------------------- download
        dl_sem = asyncio.Semaphore(config.DOWNLOAD_CONCURRENCY)
        downloaded: List[Dict[str, Any]] = []
        done_count = 0

        async def fetch(entry: Dict[str, Any]) -> None:
            nonlocal done_count
            async with dl_sem:
                url = entry["url"]
                try:
                    headers = {
                        "User-Agent": random.choice(config.USER_AGENTS),
                        "Accept": "image/*,*/*;q=0.8",
                        "Referer": f"https://{dom.domain_of(url)}/",
                    }
                    async with session.get(url, headers=headers, allow_redirects=True) as resp:
                        if resp.status != 200:
                            return
                        ctype = resp.headers.get("content-type", "")
                        if ctype and "image/" not in ctype and "octet-stream" not in ctype:
                            return
                        data = await resp.read()
                    if len(data) < 1500 or len(data) > 25 * 1024 * 1024:
                        return
                    if h.sniff_image_format(data) is None:
                        return
                    entry["data"] = data
                    downloaded.append(entry)
                except Exception:
                    return
                finally:
                    done_count += 1
                    if done_count % 10 == 0 or done_count == len(url_list):
                        emit("progress", {"stage": "download", "done": done_count,
                                          "total": len(url_list)})

        await asyncio.gather(*(fetch(e) for e in url_list))
        emit("phase", {"phase": "download", "status": "done", "count": len(downloaded)})

        # ---------------------------------------------------------------- verify
        emit("phase", {"phase": "verify", "status": "start", "count": len(downloaded)})

        query_emb = prepared.get("embedding")
        query_phash = prepared.get("phash") or ""

        def verify_one(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            from app.utils.images import decode_image_bytes
            data = entry.get("data")
            if not data:
                return None
            img = decode_image_bytes(data)
            if img is None:
                return None
            ih, iw = img.shape[:2]
            if min(ih, iw) < config.MIN_CANDIDATE_EDGE:
                return None

            faces: List[Face] = self.faces.detect(img)
            best_sim: Optional[float] = None
            best_bbox = None
            if query_emb is not None:
                for f in faces:
                    if f.embedding is None:
                        continue
                    sim = self.faces.similarity(query_emb, f.embedding)
                    if sim is not None and (best_sim is None or sim > best_sim):
                        best_sim = sim
                        best_bbox = list(f.bbox)

            phash = h.phash_from_array(img) or ""
            is_dup = bool(query_phash and phash and
                          h.phash_distance(query_phash, phash) is not None and
                          h.phash_distance(query_phash, phash) <= 6)

            # persist normalised candidate + thumbnail
            cid = hashlib.sha1(urllib.parse.quote(entry["url"], safe="").encode()).hexdigest()[:12]
            cdir = config.CANDIDATE_DIR / job_id
            cpath = cdir / f"{cid}.jpg"
            thumb_path = cdir / f"{cid}_t.jpg"
            try:
                cpath.write_bytes(normalize_image(img, max_edge=config.CANDIDATE_MAX_EDGE))
                overlay = draw_face_overlay(img, [best_bbox]) if best_bbox else img
                tb = thumbnail_bytes(overlay, max_edge=config.THUMB_SIZE)
                if tb:
                    thumb_path.write_bytes(tb)
                else:
                    thumb_path = cpath
            except Exception:
                return None

            domain = dom.domain_of(entry["source_url"] or entry["url"])
            return {
                "id": cid,
                "url": entry["url"],
                "source_url": entry["source_url"] or "",
                "domain": domain,
                "title": entry["title"][:250],
                "engines": entry["engines"],
                "image_path": str(cpath.relative_to(config.BASE_DIR)),
                "thumb_path": str(thumb_path.relative_to(config.BASE_DIR)),
                "similarity": best_sim,
                "confidence": FaceEngine.confidence(best_sim),
                "verdict": FaceEngine.verdict_for(best_sim),
                "face_count": len(faces),
                "bbox": best_bbox,
                "width": iw, "height": ih,
                "phash": phash,
                "is_query_dup": is_dup,
                "source_kind": dom.classify_domain(domain),
            }

        # run verification in a bounded thread pool
        loop = asyncio.get_running_loop()
        verify_sem = asyncio.Semaphore(max(1, config.DOWNLOAD_CONCURRENCY // 2))

        async def verify_async(entry):
            async with verify_sem:
                return await asyncio.to_thread(verify_one, entry)

        verified = []
        tasks = [asyncio.create_task(verify_async(e)) for e in downloaded]
        for i, task in enumerate(asyncio.as_completed(tasks)):
            res = await task
            if res is not None:
                verified.append(res)
            if (i + 1) % 10 == 0 or i + 1 == len(tasks):
                emit("progress", {"stage": "verify", "done": i + 1, "total": len(tasks)})

        # perceptual-hash merge of near duplicates
        verified = self._merge_near_duplicates(verified)

        emit("phase", {"phase": "verify", "status": "done", "count": len(verified)})

        # ---------------------------------------------------------------- gallery
        gallery_results: List[Dict[str, Any]] = []
        if include_gallery and query_emb is not None:
            emit("phase", {"phase": "gallery", "status": "start"})
            gallery_results = await self._match_gallery(job_id, query_emb)
            emit("phase", {"phase": "gallery", "status": "done",
                           "count": len(gallery_results)})

        # ---------------------------------------------------------------- rank
        emit("phase", {"phase": "rank", "status": "start"})
        all_results = verified + gallery_results
        for r in all_results:
            r["rank_score"] = self._rank_score(r)
        all_results.sort(key=lambda r: r["rank_score"], reverse=True)

        await asyncio.to_thread(self.db.insert_results, job_id, all_results)
        stats = {
            "engines": engine_states,
            "candidates_found": len(candidates),
            "urls_merged": len(url_list),
            "downloaded": len(downloaded),
            "verified": len(verified),
            "gallery_matches": len(gallery_results),
            "strong": sum(1 for r in all_results if r["verdict"] == "strong"),
            "possible": sum(1 for r in all_results if r["verdict"] == "possible"),
            "duration_s": round(time.time() - t0, 2),
        }
        await asyncio.to_thread(
            self.db.update_job, job_id,
            stats=json.dumps(stats), finished_at=time.time(),
        )
        emit("phase", {"phase": "rank", "status": "done"})
        emit("summary", stats)

        await session.close()

    # ------------------------------------------------------------- gallery match
    async def _match_gallery(self, job_id: str, query_emb: np.ndarray) -> List[Dict[str, Any]]:
        rows = await asyncio.to_thread(self.db.gallery_embeddings)
        out: List[Dict[str, Any]] = []
        for row in rows:
            sims = []
            if query_emb is not None:
                sim = self.faces.similarity(query_emb, row["embedding"])
                if sim is not None:
                    sims.append(sim)
            if not sims:
                continue
            sim = max(sims)
            thumb = row["thumb_path"] or row["path"]
            thumb_media = media_url(thumb)
            out.append({
                "id": f"gal-{row['image_id'][:8]}",
                "url": f"gallery://{row['image_id']}",
                "source_url": "",
                "domain": "local gallery",
                "title": row["identity"],
                "engines": ["gallery"],
                "image_path": row["path"],
                "thumb_path": thumb,
                "similarity": round(sim, 4),
                "confidence": FaceEngine.confidence(sim),
                "verdict": FaceEngine.verdict_for(sim),
                "face_count": 1,
                "bbox": None,
                "width": 0, "height": 0,
                "phash": "",
                "is_query_dup": False,
                "source_kind": "gallery",
                "identity": row["identity"],
                "gallery_id": row["gallery_id"],
            })
        out.sort(key=lambda r: r["similarity"], reverse=True)
        return out

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _rank_score(r: Dict[str, Any]) -> float:
        conf = (r.get("confidence") or 0.0) / 100.0
        consensus = min(1.0, len(r.get("engines") or []) / 3.0)
        weight = config.SOURCE_WEIGHTS.get(r.get("source_kind", "unknown"), 0.4)
        has_face = 1.0 if (r.get("face_count") or 0) > 0 else 0.0
        dup_penalty = 0.15 if r.get("is_query_dup") else 0.0
        return round(
            0.60 * conf + 0.15 * consensus + 0.10 * weight + 0.05 * has_face - dup_penalty,
            4,
        )

    @staticmethod
    def _merge_near_duplicates(results: List[Dict[str, Any]],
                               threshold: int = 10) -> List[Dict[str, Any]]:
        """Cluster results with close perceptual hashes, merging engine lists."""
        kept: List[Dict[str, Any]] = []
        for r in results:
            ph = r.get("phash") or ""
            target_idx = None
            for i, k in enumerate(kept):
                d = h.phash_distance(ph, k.get("phash") or "")
                if d is not None and d <= threshold:
                    target_idx = i
                    break
            if target_idx is None:
                kept.append(r)
                continue

            target = kept[target_idx]
            # the row with the higher similarity becomes the primary record
            if (r.get("similarity") or -1) > (target.get("similarity") or -1):
                primary, secondary = r, target
                kept[target_idx] = r
            else:
                primary, secondary = target, r

            primary["engines"] = list(dict.fromkeys(
                (primary.get("engines") or []) + (secondary.get("engines") or [])
            ))
            if secondary.get("source_url") and not primary.get("source_url"):
                primary["source_url"] = secondary["source_url"]
            if secondary.get("title") and not primary.get("title"):
                primary["title"] = secondary["title"]
        return kept
