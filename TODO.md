# TODO — OSINT Face Search

## Done in 2.0.0
- [x] Multi-backend face engine (YuNet+SFace default, InsightFace optional)
- [x] Job-based async pipeline with SSE live progress
- [x] Engine registry with reachability probes + honest status reporting
- [x] URL + perceptual-hash deduplication, consensus merging
- [x] Relevance ranking (confidence, consensus, source class)
- [x] Gallery / watchlist identities
- [x] Verify 1:1 endpoint + UI
- [x] JSON / CSV / HTML evidence exports
- [x] Search history
- [x] Full UI redesign (six views)
- [x] 49-test pytest suite
- [x] Model auto-download with mirrors

## Next (candidates)
- [ ] Scheduled re-runs of saved searches (watchlist monitoring)
- [ ] Timeline / domain distribution visualisations in results view
- [ ] Result clustering by identity across a whole job
- [ ] Username pivot: extract usernames/handles from matched source pages
- [ ] OCR (Tesseract) on result pages for context extraction
- [ ] Optional hosted-thumbnail proxy to avoid hotlinking candidate images
- [ ] Dockerfile + docker-compose packaging
- [ ] Dark/light theme toggle
- [ ] Keyboard shortcuts & command palette
