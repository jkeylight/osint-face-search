# TODO - OSINT Face Search Tool

## Completed

### Core Engine
- [x] InsightFace integration (buffalo_l model)
- [x] Multi-region face extraction (tight, loose, upper body, full head)
- [x] Face quality scoring (blur, size, brightness)
- [x] Adaptive confidence thresholds (quality-based)
- [x] Cosine similarity comparison

### Scrapers - Search Engines
- [x] Google Lens (Playwright)
- [x] Yandex Images (Playwright)
- [x] Bing Visual Search (Playwright)
- [x] TinEye (Playwright)
- [x] DuckDuckGo (Playwright)
- [x] Baidu (Playwright)
- [x] Qwant (Playwright)
- [x] SauceNAO (Playwright)

### Scrapers - Social Media
- [x] Twitter/X (snscrape)
- [x] Instagram (instagrapi)
- [x] Reddit (JSON API)
- [x] Facebook (facebook-scraper)
- [x] LinkedIn (Playwright)
- [x] TikTok (Playwright)
- [x] Snapchat (HTTP scraping)
- [x] Threads (HTTP scraping)

### Scrapers - Forums
- [x] 4chan (JSON API)

### Backend
- [x] FastAPI server
- [x] SQLite database
- [x] Image upload pipeline
- [x] Result caching (SHA-256)
- [x] Search history logging
- [x] Feedback storage
- [x] Debug endpoint

### UI
- [x] Dark theme design
- [x] Drag & drop upload
- [x] Loading progress bar
- [x] Engine status indicators (17 engines)
- [x] Results grid with thumbnails
- [x] Confidence score bars
- [x] Side-by-side comparison modal
- [x] Back to home button
- [x] Sort by similarity/engine
- [x] Export button

### Documentation
- [x] README.md
- [x] PROJECT.md
- [x] TODO.md
- [x] STATUS.md

---

## In Progress

### Server Stability
- [ ] Fix background server startup on Windows
- [ ] Add proper error logging to file
- [ ] Add graceful shutdown handling

### Scraper Reliability
- [ ] Test all Playwright scrapers with real images
- [ ] Add retry logic for failed downloads
- [ ] Add proxy rotation support
- [ ] Add user-agent rotation per request

---

## Planned - Phase 2

### Enhanced Search
- [ ] Multi-region face crop queries (search with tight + loose + upper body)
- [ ] Augmented image queries (brightness, contrast, grayscale variations)
- [ ] OCR text extraction from results (Tesseract)
- [ ] Contextual search (clothing colors, scene type)
- [ ] Hybrid search (face + text combined)

### Result Processing
- [ ] Result clustering by pHash
- [ ] Temporal ranking (recent first)
- [ ] Source domain weighting (news=1.0, social=0.7, forums=0.5)
- [ ] Consensus boost (appeared in multiple engines)

### Monitoring
- [ ] Scheduled re-runs (APScheduler)
- [ ] Desktop notifications on new matches
- [ ] Watchlist system

### Export
- [ ] CSV export with thumbnails
- [ ] PDF report generation
- [ ] Evidence package (ZIP with images + hashes + logs)

### Browser Extension
- [ ] Chrome extension (right-click → search)
- [ ] Firefox extension
- [ ] Bookmarklet

---

## Planned - Phase 3

### Advanced Features
- [ ] Face clustering (group unknown faces)
- [ ] Timeline visualization
- [ ] Geolocation mapping
- [ ] Cross-platform identity correlation
- [ ] Username pivot from face matches

### Performance
- [ ] FAISS on-disk index for large galleries
- [ ] Parallel browser instances
- [ ] Result pagination
- [ ] Image thumbnail caching

### Integration
- [ ] REST API documentation (OpenAPI)
- [ ] Webhook support
- [ ] MCP server for AI agents
- [ ] Jupyter notebook integration

---

## Known Issues

1. **Windows background server** - `pythonw` doesn't always keep server alive
2. **Playwright selectors** - Some CSS selectors may break when sites update
3. **Rate limiting** - Aggressive scraping may get IP blocked
4. **Instagram login** - instagrapi may require login for some features
5. **Facebook login** - facebook-scraper may require cookies for some pages
