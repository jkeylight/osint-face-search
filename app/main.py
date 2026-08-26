"""
FastAPI Server - OSINT Face Search
"""
import os
import hashlib
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional
import asyncio
import logging

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import config
from app.database import Database

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="OSINT Face Search", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(config.UPLOAD_DIR)), name="uploads")

db = Database(str(config.DB_PATH))

_face_engine = None
_preprocessor = None


def get_face_engine():
    global _face_engine
    if _face_engine is None:
        logger.info("Loading InsightFace model...")
        from engine.face_engine import FaceEngine
        _face_engine = FaceEngine(model_name=config.FACE_MODEL)
        logger.info("InsightFace loaded")
    return _face_engine


def get_preprocessor():
    global _preprocessor
    if _preprocessor is None:
        from engine.preprocessor import FacePreprocessor
        _preprocessor = FacePreprocessor(get_face_engine())
    return _preprocessor


@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = config.STATIC_DIR / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>OSINT Face Search</h1><p>UI not found</p>")


@app.post("/api/search")
async def search_image(file: UploadFile = File(...)):
    try:
        logger.info(f"=== SEARCH START: {file.filename} ===")

        if not file.content_type.startswith('image/'):
            raise HTTPException(400, "File must be an image")

        content = await file.read()
        if len(content) > config.MAX_IMAGE_SIZE:
            raise HTTPException(400, "File too large")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{file.filename}"
        upload_path = config.UPLOAD_DIR / filename
        upload_path.write_bytes(content)

        query_hash = hashlib.sha256(content).hexdigest()
        logger.info(f"Image saved: {upload_path} ({len(content)} bytes)")

        cached = db.get_cached_result(query_hash)
        if cached:
            logger.info("Returning cached result")
            return JSONResponse(content=cached)

        import cv2
        import numpy as np

        image = cv2.imread(str(upload_path))
        if image is None:
            raise HTTPException(400, "Could not read image")

        logger.info(f"Image shape: {image.shape}")

        has_face = False
        query_data = {"best_face": None, "embeddings": {}, "quality_score": 0.5, "threshold": 0.5}

        try:
            preprocessor = get_preprocessor()
            query_data = preprocessor.process_query(image)
            has_face = query_data["best_face"] is not None
            logger.info(f"Face detected: {has_face}, quality: {query_data['quality_score']:.2f}, threshold: {query_data['threshold']:.2f}")
        except Exception as e:
            logger.warning(f"Face processing failed: {e}")

        from scrapers.google_lens import GoogleLensScraper
        from scrapers.yandex import YandexScraper
        from scrapers.bing import BingScraper
        from scrapers.tineye import TinEyeScraper
        from scrapers.duckduckgo import DuckDuckGoScraper
        from scrapers.baidu import BaiduScraper
        from scrapers.qwant import QwantScraper
        from scrapers.saucenao import SauceNAOScraper
        from scrapers.twitter import TwitterScraper
        from scrapers.instagram import InstagramScraper
        from scrapers.reddit import RedditScraper
        from scrapers.facebook import FacebookScraper
        from scrapers.linkedin import LinkedInScraper
        from scrapers.tiktok import TikTokScraper
        from scrapers.fourchan import FourChanScraper
        from scrapers.snapchat import SnapchatScraper
        from scrapers.threads import ThreadsScraper

        all_results = []
        engine_stats = {}

        async def run_engine(scraper, name):
            try:
                logger.info(f"Querying {name}...")
                results = await scraper.search(str(upload_path))
                logger.info(f"{name}: {len(results)} results")
                engine_stats[name] = {"status": "success", "count": len(results)}
                return results
            except Exception as e:
                logger.error(f"{name} FAILED: {e}")
                engine_stats[name] = {"status": "error", "error": str(e)[:200]}
                return []

        scrapers = [
            # Search Engines
            (GoogleLensScraper(), "google_lens"),
            (YandexScraper(), "yandex"),
            (BingScraper(), "bing"),
            (TinEyeScraper(), "tineye"),
            (DuckDuckGoScraper(), "duckduckgo"),
            (BaiduScraper(), "baidu"),
            (QwantScraper(), "qwant"),
            (SauceNAOScraper(), "saucenao"),
            # Social Media
            (TwitterScraper(), "twitter"),
            (InstagramScraper(), "instagram"),
            (RedditScraper(), "reddit"),
            (FacebookScraper(), "facebook"),
            (LinkedInScraper(), "linkedin"),
            (TikTokScraper(), "tiktok"),
            (SnapchatScraper(), "snapchat"),
            (ThreadsScraper(), "threads"),
            # Forums
            (FourChanScraper(), "4chan"),
        ]

        tasks = [run_engine(s, name) for s, name in scrapers]
        engine_results = await asyncio.gather(*tasks, return_exceptions=True)

        for results in engine_results:
            all_results.extend(results)

        logger.info(f"Total raw results from all engines: {len(all_results)}")

        face_engine = None
        if has_face:
            try:
                face_engine = get_face_engine()
            except Exception as e:
                logger.error(f"Face engine load failed: {e}")

        verified_results = []
        import aiohttp

        async with aiohttp.ClientSession() as session:
            for result in all_results[:60]:
                try:
                    url_lower = result.url.lower()
                    if any(ext in url_lower for ext in ['.html', '.php', '.asp', '.jsp', '.pdf', '.txt', '.css', '.js']):
                        continue

                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'image/*, */*;q=0.8'
                    }

                    async with session.get(
                        result.url,
                        timeout=aiohttp.ClientTimeout(total=8),
                        headers=headers,
                        allow_redirects=True
                    ) as resp:
                        if resp.status != 200:
                            continue

                        ct = resp.headers.get('content-type', '')
                        img_data = await resp.read()

                        if len(img_data) < 2000:
                            continue

                        is_image = 'image' in ct or any(result.url.lower().endswith(e) for e in ['.jpg', '.jpeg', '.png', '.gif', '.webp'])
                        if not is_image:
                            continue

                        nparr = np.frombuffer(img_data, np.uint8)
                        candidate = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if candidate is None:
                            continue

                        ch, cw = candidate.shape[:2]
                        if cw < 30 or ch < 30:
                            continue

                        similarity = 0.3
                        region_matched = "image"

                        if face_engine and has_face and query_data.get("embeddings"):
                            for region_name, query_emb in query_data["embeddings"].items():
                                try:
                                    matches = face_engine.compare_face_to_image(
                                        query_emb, candidate, threshold=0.35
                                    )
                                    if matches:
                                        similarity = matches[0]["similarity"]
                                        region_matched = region_name
                                        break
                                except Exception:
                                    continue

                        verified_results.append({
                            "url": result.url,
                            "source_url": result.source_url,
                            "title": result.title,
                            "engine": result.engine,
                            "similarity": round(similarity, 4),
                            "quality": 0.5,
                            "region_matched": region_matched,
                            "thumbnail_url": result.thumbnail_url,
                        })

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    continue

        seen_urls = set()
        unique_results = []
        for r in verified_results:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                unique_results.append(r)

        unique_results.sort(key=lambda x: x["similarity"], reverse=True)

        for i, r in enumerate(unique_results):
            r["rank"] = i + 1

        logger.info(f"Final verified results: {len(unique_results)}")

        response = {
            "success": True,
            "query_hash": query_hash,
            "query_image": f"/uploads/{filename}",
            "quality_score": query_data.get("quality_score", 0.5),
            "threshold_used": query_data.get("threshold", 0.5),
            "engines_queried": list(engine_stats.keys()),
            "engine_stats": engine_stats,
            "total_candidates": len(all_results),
            "verified_matches": len(unique_results),
            "results": unique_results[:30],
        }

        db.set_cached_result(query_hash, response)

        for r in unique_results[:30]:
            db.insert_search(
                query_sha256=query_hash,
                engine=r["engine"],
                result_url=r["url"],
                similarity=r["similarity"]
            )

        logger.info(f"=== SEARCH DONE: {len(unique_results)} results ===")
        return JSONResponse(content=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, f"Search failed: {str(e)}")


@app.get("/api/stats")
async def get_stats():
    return db.get_stats()


@app.get("/api/debug")
async def debug_info():
    """Debug endpoint to check system status"""
    import cv2
    info = {
        "opencv": cv2.__version__,
        "upload_dir": str(config.UPLOAD_DIR),
        "upload_dir_exists": config.UPLOAD_DIR.exists(),
        "upload_files": len(list(config.UPLOAD_DIR.glob("*"))),
    }

    try:
        from insightface.app import FaceAnalysis
        info["insightface"] = "available"
    except ImportError as e:
        info["insightface"] = f"NOT INSTALLED: {e}"

    try:
        import playwright
        info["playwright"] = "available"
    except ImportError as e:
        info["playwright"] = f"NOT INSTALLED: {e}"

    try:
        from scrapers.bing import BingScraper
        s = BingScraper()
        info["bing_scraper"] = "ok"
    except Exception as e:
        info["bing_scraper"] = f"error: {e}"

    return info


@app.get("/api/history")
async def get_history(limit: int = Query(50, ge=1, le=200)):
    return db.get_search_history(limit)


@app.post("/api/feedback")
async def submit_feedback(query_hash: str, result_url: str, is_correct: bool):
    db.insert_feedback(query_hash, result_url, is_correct)
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
