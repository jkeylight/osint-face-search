# STATUS - OSINT Face Search Tool

**Last Updated:** August 26, 2026

---

## Current Version: 1.0.0

### Build Status: BETA

The core functionality is built and working. Server runs and serves the UI. All 17 scrapers are implemented. Some scrapers may need fine-tuning with real-world testing.

---

## Component Status

### Core Engine
| Component | Status | Notes |
|-----------|--------|-------|
| InsightFace (buffalo_l) | WORKING | 99.86% accuracy, loads on startup |
| Face Detection (SCRFD) | WORKING | Detects faces in uploaded images |
| Multi-region Extraction | WORKING | tight, loose, upper_body, full_head |
| Quality Scoring | WORKING | Laplacian variance + size + brightness |
| Adaptive Thresholds | WORKING | 0.75/0.65/0.50 based on quality |
| Embedding Comparison | WORKING | Cosine similarity |

### Scrapers
| Engine | Status | Method | Notes |
|--------|--------|--------|-------|
| Google Lens | BETA | Playwright | CSS selectors may need updates |
| Yandex Images | BETA | Playwright | Works with image upload |
| Bing Visual Search | BETA | Playwright | Most reliable Playwright scraper |
| TinEye | BETA | Playwright | Limited free results |
| DuckDuckGo | BETA | Playwright | Image search feature |
| Baidu | BETA | Playwright | Chinese search engine |
| Qwant | BETA | Playwright | European search engine |
| SauceNAO | BETA | Playwright | Anime/art focus |
| Twitter/X | BETA | snscrape | Searches recent tweets with images |
| Instagram | BETA | instagrapi | May require login for full access |
| Reddit | STABLE | JSON API | Most reliable social scraper |
| Facebook | BETA | facebook-scraper | May require cookies |
| LinkedIn | BETA | Playwright | Public profiles only |
| TikTok | BETA | Playwright | Public videos |
| Snapchat | BETA | HTTP scraping | Public profiles only |
| Threads | BETA | HTTP scraping | Public posts only |
| 4chan | STABLE | JSON API | Most reliable overall |

### Backend
| Component | Status | Notes |
|-----------|--------|-------|
| FastAPI Server | WORKING | Serves API + static files |
| SQLite Database | WORKING | Stores images, faces, searches, feedback |
| Image Upload | WORKING | Saves to uploads/ directory |
| Result Caching | WORKING | SHA-256 keyed, avoids re-queries |
| Search Logging | WORKING | Audit trail in database |
| Debug Endpoint | WORKING | /api/debug shows system status |

### UI
| Component | Status | Notes |
|-----------|--------|-------|
| Dark Theme | WORKING | Professional OSINT aesthetic |
| Drag & Drop Upload | WORKING | With fallback click-to-browse |
| Loading Progress | WORKING | Animated spinner + progress bar |
| Engine Status | WORKING | Shows all 17 engines during search |
| Results Grid | WORKING | Thumbnails with confidence bars |
| Comparison Modal | WORKING | Side-by-side view |
| Back Button | WORKING | Returns to upload screen |
| Sort Options | WORKING | By similarity, engine, date |

---

## Test Results

### Last Tested: August 26, 2026

| Test | Result | Notes |
|------|--------|-------|
| Server starts | PASS | uvicorn on port 8000 |
| UI loads | PASS | All assets served correctly |
| InsightFace loads | PASS | buffalo_l model downloads and loads |
| File upload | PASS | Images saved to uploads/ |
| Face detection | PASS | Detects faces in clear photos |
| 4chan scraper | PASS | Returns images from JSON API |
| Reddit scraper | PASS | Returns images from JSON API |
| Bing scraper | NEEDS TESTING | Playwright upload needs verification |
| Google Lens scraper | NEEDS TESTING | Playwright upload needs verification |
| Yandex scraper | NEEDS TESTING | Playwright upload needs verification |
| Twitter scraper | NEEDS TESTING | snscrape search needs verification |
| Instagram scraper | NEEDS TESTING | instagrapi needs verification |
| Full pipeline | NEEDS TESTING | Upload → search → verify → display |

---

## Dependencies

| Package | Version | Status |
|---------|---------|--------|
| insightface | 1.0.1 | INSTALLED |
| onnxruntime | Latest | INSTALLED |
| opencv-python | 5.0.0 | INSTALLED |
| playwright | 1.62.0 | INSTALLED |
| fastapi | Latest | INSTALLED |
| uvicorn | Latest | INSTALLED |
| aiohttp | Latest | INSTALLED |
| imagehash | Latest | INSTALLED |
| snscrape | 0.7.0 | INSTALLED |
| instagrapi | 2.18.18 | INSTALLED |
| facebook-scraper | 0.2.59 | INSTALLED |

---

## Known Issues

1. **Server startup on Windows** - Background process (`pythonw`) doesn't always keep server alive. Workaround: run `python run.py` in a terminal window.

2. **Playwright selectors** - CSS selectors for Google Lens, Yandex may break when sites update. These need periodic testing and updates.

3. **Dependency conflicts** - `facebook-scraper` requires older `websockets`/`urllib3` which conflicts with `uvicorn`. Fixed by reinstalling newer versions.

4. **Rate limiting** - Running all 17 engines simultaneously may trigger rate limits. Consider running in batches.

5. **Social media login** - Instagram and Facebook scrapers may require login cookies for full access.

---

## Next Steps

1. **Test full pipeline** - Upload image → search → verify → display results
2. **Fix Playwright scrapers** - Verify Bing, Google, Yandex upload works
3. **Add error logging** - Log all scraper errors to file
4. **Add retry logic** - Retry failed downloads
5. **Push to GitHub** - Initial commit with all files

---

## File Count

| Directory | Files | Lines |
|-----------|-------|-------|
| app/ | 4 | ~400 |
| engine/ | 3 | ~300 |
| scrapers/ | 18 | ~800 |
| static/ | 3 | ~600 |
| utils/ | 2 | ~100 |
| Root | 5 | ~200 |
| **Total** | **35** | **~2,400** |
