# STATUS — OSINT Face Search

**Last updated:** 2026-08-26 · **Version:** 2.1.0 · **Build:** STABLE

## Component status

| Component | Status | Notes |
|-----------|--------|-------|
| Desktop launcher (`npm run setup-desktop`) | ✅ WORKING | Windows .lnk / macOS .app / Linux .desktop; hidden window; custom icon |
| `Install Desktop Icon.bat` (Windows double-click install) | ✅ WORKING | finds Python itself; no npm needed |
| Hidden desktop launcher (`desktop_app.py`) | ✅ WORKING | tested: start → browser → single-instance → UI shutdown |
| UI "Shut down server" + `POST /api/system/shutdown` | ✅ WORKING | graceful uvicorn stop, tested |
| Face engine (YuNet + SFace) | ✅ WORKING | 0.4 s cold load, 128-d embeddings, verified on demo set |
| Face engine (InsightFace) | ✅ OPTIONAL | auto-detected if `pip install insightface onnxruntime` |
| Model auto-download | ✅ WORKING | GitHub release + codeload fallback |
| Search pipeline (jobs + SSE) | ✅ WORKING | live progress, per-engine status/reasons |
| Dedup (URL + pHash) | ✅ WORKING | unit-tested merge logic |
| Ranking | ✅ WORKING | confidence + consensus + source weight |
| Gallery / watchlist | ✅ WORKING | CRUD + matched in every search |
| Verify 1:1 | ✅ WORKING | API-tested |
| Exports (JSON/CSV/HTML) | ✅ WORKING | HTML report embeds thumbnails |
| History | ✅ WORKING | SQLite persistence |
| Demo case | ✅ WORKING | bundled synthetic faces, offline-capable |
| Tests | ✅ 63 PASSING | unit + in-process API integration |

## Engine status

Browser engines (Google Lens, Yandex, Bing, TinEye, Baidu, SauceNAO-web) need
`pip install playwright && playwright install chromium`. Selectors for Google
Lens and Baidu are best-effort and may break when those sites ship UI changes —
they degrade to an `error` status with the reason instead of failing the search.

HTTP engines (Reddit feed, 4chan feed, SauceNAO API) need plain outbound
network access.

## Known limitations

1. Reverse-image engines are scraper-based and inherently fragile; site UI
   changes will require selector updates in `app/engines/`.
2. Feed engines (Reddit/4chan) harvest public posts and verify faces against
   them — coverage is luck-of-the-feed, not true reverse search.
3. Cosine similarity is probabilistic; verdict bands are defaults, not truth.
4. Single-user, local tool by design: SQLite + in-memory job state are not
   multi-worker safe.
