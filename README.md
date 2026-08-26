# OSINT Face Search

**Reverse image search aggregation + local face verification** — an OSINT workbench
that queries image search engines with a face photo, downloads the candidates, and
verifies every hit **on your machine** with real face recognition.

```
upload face ──▶ engines (Google Lens · Yandex · Bing · TinEye · Baidu · SauceNAO)
                        │            + public feeds (Reddit · 4chan)
                        ▼
              download → dedupe (URL + perceptual hash)
                        ▼
              local face verification (YuNet + SFace / InsightFace)
                        ▼
              ranked results · verdicts · evidence export
```

---

## Quick start

```bash
git clone https://github.com/jkeylight/osint-face-search.git
cd osint-face-search

# 1. install dependencies (Python 3.10+)
pip install -r requirements.txt

# 2. fetch the face models (~38 MB, one time)
python scripts/download_models.py

# 3. run
python run.py          # → http://localhost:8000
```

Want the browser-based engines (Google Lens, Yandex, Bing, TinEye, Baidu, SauceNAO)?

```bash
./scripts/setup.sh full        # or:
pip install playwright && playwright install chromium
```

Without Playwright the app still runs — browser engines simply report
`unavailable` and the rest of the pipeline (gallery matching, verification,
1:1 compare) works.

### Try it in 10 seconds

Click **Run demo case** on the home screen. It seeds a gallery with bundled
*synthetic* faces (two photos of one person + four distractors), runs the full
pipeline and shows real verification scores — no internet needed.

---

## Features

| Area | What you get |
|------|--------------|
| **Search** | Job-based pipeline with live SSE progress — every engine, download and verification step streamed to the UI |
| **Verification** | YuNet detection + SFace embeddings (OpenCV Zoo) by default; InsightFace/ArcFace auto-detected if installed |
| **Verdicts** | Calibrated cosine bands: `strong / possible / weak / none` with confidence scores |
| **Deduplication** | URL merge across engines + DCT perceptual-hash clustering of near-identical images |
| **Ranking** | Confidence + engine consensus + source-class weighting (news > official > social > forum) |
| **Gallery** | Reference identities compared in every search (watchlist-style) |
| **Verify 1:1** | Side-by-side comparison of any two photos with verdict ring |
| **History** | Every job persisted in SQLite with results, stats and engine diagnostics |
| **Export** | JSON, CSV, and a portable HTML evidence report with embedded thumbnails and SHA-256 of the query |
| **Diagnostics** | System view: backend, models, engine reachability probes, storage usage |
| **Robustness** | Per-engine timeouts, bounded concurrency, magic-byte sniffing, graceful degradation everywhere |

## Search engines

| Engine | Type | Needs | Notes |
|--------|------|-------|-------|
| Google Lens | reverse image | Playwright | Best web coverage; selectors can break when Google ships changes |
| Yandex Images | reverse image | Playwright | Consistently the strongest for faces |
| Bing Visual | reverse image | Playwright | Most automation-tolerant |
| TinEye | reverse image | Playwright | Exact + modified matches with first-seen dates |
| Baidu Image | reverse image | Playwright | Coverage skewed to the Chinese web |
| SauceNAO | reverse image | API key (free) or Playwright | Anime/art focus; set `SAUCENAO_API_KEY` |
| Reddit feed | public feed | – | Scans recent image posts on selected subreddits |
| 4chan feed | public feed | – | Scans public board catalogs |

The v1 "17 scrapers" set was consolidated: Twitter/snscrape, Instagram/instagrapi,
Facebook, LinkedIn, TikTok, Snapchat and Threads adapters were removed — those
libraries are unmaintained or require login credentials and were never verifiably
working. Every engine that ships now is honestly implemented and reports its own
availability. (See `CHANGELOG.md`.)

## How verification works

1. Query image is analysed locally: faces detected (YuNet), best face selected by
   quality (size/sharpness/exposure heuristic), embedding computed (SFace).
2. Engines are queried with an enlarged face crop; candidate image URLs are
   merged and downloaded with content sniffing.
3. Every candidate image is scanned for faces; each face embedding is compared to
   the query embedding with **cosine similarity**.
4. Verdict bands (defaults, tunable via env):
   - `strong` ≥ 0.55 — likely the same person
   - `possible` ≥ 0.45 — worth a human look
   - `weak` ≥ 0.30 / `none` below — different person or no face found
5. Near-duplicates of the query image itself are flagged (`DUP`).

> Face embeddings are probabilistic. This tool surfaces *leads*, not proof of
> identity — verify before acting on any result.

## Configuration

All settings are environment-overridable with the `OSINT_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `OSINT_HOST` / `OSINT_PORT` | `0.0.0.0` / `8000` | Bind address |
| `OSINT_FACE_BACKENDS` | `insightface,opencv` | Backend preference order |
| `OSINT_AUTO_DOWNLOAD_MODELS` | `true` | Fetch missing models at startup |
| `OSINT_VERDICT_STRONG` | `0.55` | Strong-match cosine threshold |
| `OSINT_VERDICT_POSSIBLE` | `0.45` | Possible-match threshold |
| `OSINT_MAX_CANDIDATES` | `120` | Max candidates downloaded per search |
| `OSINT_RESULTS_PER_ENGINE` | `25` | Results requested per engine |
| `OSINT_DOWNLOAD_CONCURRENCY` | `12` | Parallel downloads |
| `OSINT_ENGINE_TIMEOUT_S` | `90` | Per-engine timeout |
| `OSINT_PROXY_URL` | – | Outbound proxy for all HTTP |
| `SAUCENAO_API_KEY` | – | Free SauceNAO API key |

## Project structure

```
osint-face-search/
├── app/
│   ├── main.py            # FastAPI routes
│   ├── config.py          # env-configurable settings
│   ├── database.py        # SQLite (WAL) + migrations
│   ├── jobs.py            # job manager + SSE event bus
│   ├── pipeline.py        # orchestration: engines → download → verify → rank
│   ├── face_engine.py     # multi-backend face recognition
│   ├── models.py          # model download/management
│   ├── engines/           # search engine adapters + registry
│   └── utils/             # hashing (SHA-256/pHash), images, domains
├── static/                # single-page UI (no build step)
├── scripts/               # setup.sh, download_models.py
├── tests/                 # pytest suite (unit + API integration)
├── demo/                  # bundled synthetic demo faces
├── models/                # ONNX models (gitignored, auto-downloaded)
└── data/, uploads/, cache/, logs/   # runtime state (gitignored)
```

## Testing

```bash
pip install pytest httpx
python -m pytest tests/ -q
```

49 tests cover hashing, ranking, dedup merge, domain classification, the face
engine (gated on models), and the full HTTP API (in-process TestClient).

## Legal & ethics

- For **personal research and educational use**.
- Scraping may violate websites' Terms of Service; respect rate limits.
- Check your local laws on automated data collection.
- **Do not** use for stalking, harassment, or any purpose that harms people.
- Public-content scraping ≠ consent: be thoughtful about what you do with results.

## License

MIT
