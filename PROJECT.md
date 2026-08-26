# OSINT Face Search Tool

**Reverse Image Search + Local Face Verification**

A powerful, free, open-source OSINT tool that aggregates results from 17 search engines and social media platforms, then verifies matches locally using face recognition.

---

## What It Does

1. **Upload a face photo** → tool searches 17 engines simultaneously
2. **Downloads candidate images** → verifies each with InsightFace (99.86% accuracy)
3. **Returns ranked results** → sorted by similarity with source URLs
4. **Everything runs locally** → no data sent to external servers (except search queries)

## Engines Supported

### Search Engines (8)
| Engine | Method | Cost |
|--------|--------|------|
| Google Lens | Playwright | Free |
| Yandex Images | Playwright | Free |
| Bing Visual Search | Playwright | Free |
| TinEye | Playwright | Free |
| DuckDuckGo | Playwright | Free |
| Baidu | Playwright | Free |
| Qwant | Playwright | Free |
| SauceNAO | Playwright | Free |

### Social Media (8)
| Platform | Method | Cost |
|----------|--------|------|
| Twitter/X | snscrape | Free |
| Instagram | instagrapi | Free |
| Reddit | JSON API | Free |
| Facebook | facebook-scraper | Free |
| LinkedIn | Playwright | Free |
| TikTok | Playwright | Free |
| Snapchat | HTTP scraping | Free |
| Threads | HTTP scraping | Free |

### Forums (1)
| Platform | Method | Cost |
|----------|--------|------|
| 4chan | JSON API | Free |

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| Face Recognition | InsightFace (ArcFace buffalo_l) |
| Face Detection | SCRFD |
| Web Scraping | Playwright + aiohttp |
| API | FastAPI |
| Database | SQLite |
| UI | Vanilla HTML/CSS/JS (Dark Theme) |
| Vector Search | FAISS |

## Features

- **Multi-region face extraction** (tight, loose, upper body, full head)
- **Adaptive confidence thresholds** (quality-based dynamic filtering)
- **pHash deduplication** (removes near-duplicate results)
- **Source weighting** (news > social > forums > unknown)
- **Audit trail** (SHA-256 hashing, timestamped logs)
- **Result caching** (avoids re-querying same image)
- **Side-by-side comparison** (visual verification)
- **Feedback loop** (mark correct/incorrect to improve)
- **Export** (JSON, CSV)

## Setup

### Prerequisites
- Python 3.10+
- pip

### Installation

```bash
# Clone repository
git clone https://github.com/jkeylight/osint-face-search.git
cd osint-face-search

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Run the application
python run.py
```

The app opens at **http://localhost:8000**

### Windows Quick Start

```cmd
git clone https://github.com/jkeylight/osint-face-search.git
cd osint-face-search
pip install -r requirements.txt
playwright install chromium
python run.py
```

## Usage

1. **Open** http://localhost:8000 in your browser
2. **Upload** a face photo (drag & drop or click)
3. **Click Search** → tool queries all 17 engines
4. **View Results** → browse verified matches with confidence scores
5. **Compare** → click any result for side-by-side comparison
6. **Feedback** → mark results as correct/incorrect

## Project Structure

```
osint-face-search/
├── app/
│   ├── main.py              # FastAPI server + search pipeline
│   ├── config.py            # Settings and configuration
│   └── database.py          # SQLite operations
├── engine/
│   ├── face_engine.py       # InsightFace integration
│   └── preprocessor.py      # Multi-region extraction + augmentation
├── scrapers/
│   ├── base.py              # Abstract scraper adapter
│   ├── google_lens.py       # Google Lens (Playwright)
│   ├── yandex.py            # Yandex Images (Playwright)
│   ├── bing.py              # Bing Visual Search (Playwright)
│   ├── tineye.py            # TinEye (Playwright)
│   ├── duckduckgo.py        # DuckDuckGo (Playwright)
│   ├── baidu.py             # Baidu (Playwright)
│   ├── qwant.py             # Qwant (Playwright)
│   ├── saucenao.py          # SauceNAO (Playwright)
│   ├── twitter.py           # Twitter/X (snscrape)
│   ├── instagram.py         # Instagram (instagrapi)
│   ├── reddit.py            # Reddit (JSON API)
│   ├── facebook.py          # Facebook (facebook-scraper)
│   ├── linkedin.py          # LinkedIn (Playwright)
│   ├── tiktok.py            # TikTok (Playwright)
│   ├── snapchat.py          # Snapchat (HTTP)
│   ├── threads.py           # Threads (HTTP)
│   └── fourchan.py          # 4chan (JSON API)
├── static/
│   ├── index.html           # UI
│   ├── style.css            # Dark theme CSS
│   └── app.js               # Frontend JavaScript
├── uploads/                 # Uploaded images
├── cache/                   # Engine response cache
├── data/                    # SQLite database
├── requirements.txt         # Python dependencies
├── run.py                   # Entry point
└── README.md
```

## Configuration

Edit `app/config.py` to customize:

| Setting | Default | Description |
|---------|---------|-------------|
| `THRESHOLD_HIGH` | 0.75 | Strict matching for high-quality queries |
| `THRESHOLD_MEDIUM` | 0.65 | Standard matching |
| `THRESHOLD_LOW` | 0.50 | Loose matching for low-quality queries |
| `MAX_CONCURRENT_DOWNLOADS` | 15 | Parallel image downloads |
| `RESULTS_PER_ENGINE` | 20 | Max results per engine |
| `MAX_STORAGE_GB` | 10.0 | Storage quota |

## Cost

**$0/month** - All open-source tools, runs locally on your machine.

## Privacy

- All processing happens on your machine
- No data sent to external servers (except search queries to engines)
- No API keys required
- No accounts or subscriptions
- Images are not stored permanently (auto-pruned)

## Legal Notice

This tool is for **personal research and educational purposes only**:
- Scraping may violate website Terms of Service
- Respect rate limits and don't abuse engines
- Check local laws regarding automated data collection
- Do not use for stalking, harassment, or illegal purposes

## License

MIT License - Free to use, modify, and distribute.

## Credits

- [InsightFace](https://github.com/deepinsight/insightface) - Face recognition
- [Playwright](https://playwright.dev/) - Browser automation
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [snscrape](https://github.com/JustAnotherArchiworker/snscrape) - Twitter scraping
- [instagrapi](https://github.com/subzeroid/instagrapi) - Instagram API
