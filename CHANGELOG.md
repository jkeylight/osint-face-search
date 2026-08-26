# Changelog

## 2.1.0 — desktop app (one double-click icon)

- **`npm run setup-desktop`** (or `python scripts/setup_desktop.py`) creates a
  desktop shortcut **fully automatically**: installs missing dependencies,
  downloads face models, builds `.ico`/`.icns` icons from the bundled custom
  `assets/icon.png`, and creates the platform launcher — no manual shortcut
  or VBS editing.
- Windows: real `.lnk` via the Windows shell API (PowerShell + WScript.Shell
  COM), resolves OneDrive-redirected Desktop folders, launches through
  `pythonw.exe` so **no console window ever appears** (VBS hidden-launcher
  fallback when `pythonw` is unavailable).
- macOS: proper `.app` bundle with a generated `.icns` icon.
- Linux: `.desktop` entry in the application menu + desktop (marked trusted).
- New `desktop_app.py` hidden launcher: starts uvicorn in a background thread
  (file logging for `pythonw`), waits for readiness, opens the browser,
  single-instance aware (busy port → open a tab instead of double-starting),
  auto-picks a free port when 8000 is taken.
- Stop the app from the UI: new `POST /api/system/shutdown` endpoint +
  "Shut down server" button in the System view (graceful uvicorn shutdown,
  with a "server stopped" overlay).
- `--console` option for a debugging shortcut that runs `run.py` visibly.
- Shortcut name configurable (`--name`, default "MyApp").
- 12 new tests: icon builders (ICO/ICNS structure), Windows shortcut/VBS
  generators, desktop-entry contents, launcher port helpers, shutdown
  endpoint behaviour (61 total).

## 2.0.0 — architecture rewrite

The v1 codebase looked feature-rich on paper (17 "scrapers", InsightFace, FAISS)
but much of it never verifiably worked: dead dependencies (snscrape,
facebook-scraper), adapters that scraped hardcoded profile pages, a synchronous
search endpoint that could hang for minutes with no progress, no tests, and a
UI that showed a spinner for a minute with zero feedback.

v2 is a ground-up rebuild focused on **working end-to-end**.

### Face recognition (real, local, always-on)
- New multi-backend `FaceEngine`: **YuNet + SFace** (OpenCV Zoo, 38 MB) as the
  zero-config default; InsightFace/ArcFace auto-detected when installed.
- Fixed OpenCV 5 YuNet row layout bug (`[x,y,w,h,landmarks,score]` — score is
  the *last* column), which previously produced garbage bboxes/scores.
- Calibrated verdict bands from empirical same/different-person separation.
- Model auto-download with two mirror strategies (GitHub releases + codeload
  streaming for restricted networks).

### Search pipeline
- **Job-based architecture**: `POST /api/jobs` returns instantly; the pipeline
  runs in the background and streams **SSE progress events** (phase, per-engine
  status, download/verify counters) to the UI. Polling fallback if SSE drops.
- Every engine failure is a *status with a reason*, never a crash.
- Bounded concurrency (downloads, engines), per-engine timeouts, HTTP content
  sniffing (magic bytes, not extensions), size limits.
- URL-level merge across engines (consensus) + DCT perceptual-hash clustering
  of near-duplicate images (dependency-free pHash implementation).
- Query-duplicate detection (flag results that are the query image itself).
- Relevance ranking: confidence + engine consensus + source-class weight.
- Local **gallery/watchlist** identities are matched in every search.

### Engines
- Kept and hardened: Google Lens, Yandex, Bing Visual, TinEye, Baidu,
  SauceNAO (API key support + browser fallback), Reddit feed, 4chan feed.
- Shared stealth browser manager (one Chromium, isolated contexts).
- **Removed**: Twitter (snscrape dead), Instagram (instagrapi needs login),
  Facebook (dead scraper), LinkedIn, TikTok, Snapchat, Threads — see README.
- Reachability probing (real HTTPS request, catches TLS-level blocks) surfaced
  in the UI *before* you search.

### API
- New endpoints: `/api/jobs` (+ `/events` SSE, `/export`), `/api/analyze`,
  `/api/verify` (1:1), full `/api/gallery` CRUD, `/api/demo`, `/api/system`
  diagnostics with probe cache.
- SQLite with WAL, forward column migrations, cascade deletes, storage pruning.
- Exports: JSON, CSV, and a portable **HTML evidence report** with embedded
  thumbnails and query SHA-256.

### UI
- Complete redesign: dark OSINT workstation theme, six views (Search, Results,
  Gallery, Verify 1:1, History, System), live pipeline console with engine
  status grid, results grid with verdict badges/confidence bars, compare modal,
  filters (verdict/min-confidence/sort), toasts, drag&drop + paste upload.

### Quality
- 49 pytest tests (unit + full API integration), `node --check` clean frontend.
- Old dead code and fake adapters deleted; docs rewritten to match reality.

## 1.0.0 — initial release
- Initial FastAPI + InsightFace + 17 scrapers + basic dark UI.
