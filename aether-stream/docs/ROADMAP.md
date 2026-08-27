# AETHER-STREAM execution roadmap

The critical path is deliberately transport-first. The UI can be cinematic only when the state model is truthful under failure, pause, resume, and offline transitions.

## Phase 1 — Core Engine & Auth

**Outcome:** a deterministic, local-first Rust engine that can safely pause, resume, verify, assemble, and deny access to an unopened vault.

- [x] Cargo workspace and `aether-core` crate.
- [x] HTTP/3-first reqwest client with HTTP/2/1.1 fallback.
- [x] Range capability probe and 1–64 segment planner.
- [x] Concurrent chunk workers with cancellation and progress events.
- [x] Private staging directory and atomic final assembly.
- [x] SQLCipher storage boundary via `rusqlite`.
- [x] Argon2id PHC verifier, zeroized password input, lockout, and re-lock state.
- [x] OS keychain boundary for the random SQLCipher database key.
- [x] Explicit WebTorrent fallback package for user-supplied authorized magnets.
- [ ] Durable checkpoint manifest and restart-safe byte-range resume.
- [ ] Network empathy adapter: OS network interface / active-call signals, with explicit user override.
- [ ] Criterion benchmarks for single-stream vs. segmented downloads across local test origins.

**Exit gate:** fault-injection tests prove that a killed worker cannot publish a corrupt destination, a non-range origin is streamed exactly once, and a wrong vault credential never exposes queue metadata.

## Phase 2 — Tauri UI & Lock Screen

**Outcome:** a desktop and mobile-capable shell that projects engine state at 120 fps without inventing progress and never renders private queue data before unlock.

- [x] Tauri 2 + Svelte 5 + Tailwind workspace scaffold.
- [x] Cinematic app lock screen with first-run passphrase enrollment and biometric trigger.
- [x] Cinematic download card with progress ring, chunk equalizer, speed, and reduced-motion handling.
- [x] Typed auth/download command and event bridge skeleton.
- [x] Tauri biometry plugin path for Windows Hello, macOS Touch ID, iOS, and Android.
- [ ] Linux desktop-portal/PAM biometric adapter.
- [ ] Queue list, keyboard command palette, pause/resume/cancel actions.
- [ ] Real bandwidth history graph backed by event timestamps rather than animation time.
- [ ] Native save panel, notifications, haptic hooks on supported mobile targets.
- [ ] Accessibility audit: focus order, screen-reader labels, contrast, reduced motion.

**Exit gate:** every visible byte, speed, ETA, and status is sourced from a core event or persisted record; no optimistic UI can claim a completed file.

## Phase 3 — Browser Extension

**Outcome:** a low-privilege, SPA-safe capture path from the page to a user-confirmed queue action.

- [x] Manifest V3 package and TypeScript media observer scaffold.
- [x] MutationObserver + history transition hooks for modern SPAs.
- [x] HLS, DASH, direct media, `blob:`, and download-link candidate classification.
- [ ] Page-context blob materialization with explicit user confirmation.
- [ ] Authenticated native-messaging / Tauri protocol transport with per-install nonce.
- [ ] Context-menu and media-overlay affordances with origin confirmation.
- [ ] Test fixtures for React, Vue, Next, video.js, hls.js, and lazy-loaded media.
- [ ] No-DRM / no-access-control-bypass review and browser-store documentation.

**Exit gate:** extension stays dormant unless the user invokes it, does not exfiltrate page data, and survives five SPA route changes without duplicate observers.

## Phase 4 — WASM Plugins & Cloud Sync

**Outcome:** safe automation and cross-device continuity without turning the relay into a surveillance service.

- [ ] Wasmtime/WASI host with memory, fuel, wall-clock, and output-size limits.
- [ ] Capability manifests for rename, unzip, ClamAV socket, and S3 upload.
- [ ] Plugin signing / trust UI and an offline local registry.
- [ ] Operation-based queue CRDT with deterministic conflict rules for pause, priority, destination, and deletion.
- [ ] Client-side encryption envelope and OS-keychain key wrapping.
- [ ] Opaque relay that stores encrypted operations and never raw URLs by default.
- [ ] Mobile transport policy: Wi-Fi-only, battery budget, metered-network guardrails.
- [ ] Disaster recovery export: encrypted queue manifest plus checksummed local state.

**Exit gate:** a second trusted device can reconcile queue intent and resume from a verified checkpoint, while the relay cannot read filenames, URLs, or credentials.
