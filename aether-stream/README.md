# AETHER-STREAM

A privacy-first, open-core download and data-ingestion engine designed to make the old download-manager model feel obsolete: resumable transport, adaptive segmentation, native HTTP/3, a local-first queue, and a cinematic Tauri surface.

> **Scope note:** AETHER-STREAM is an infrastructure scaffold. It is designed for content the operator is authorised to fetch. It does not bypass authentication, DRM, paywalls, or access controls. Media detection is intentionally limited to URLs exposed to the current browser page.

## Vision

- **No telemetry by default.** No analytics SDK, remote logging, or background account is required.
- **Fortress local security.** The Tauri shell fails closed behind a cinematic lock screen; Argon2id verifies the local passphrase, SQLCipher encrypts queue/history/intercepted-media/auth metadata, and the SQLCipher key lives in the OS keychain.
- **Rust-first transport.** The queue, HTTP client, segmentation policy, persistence boundary, and plugin host belong in native code.
- **Protocol agility.** Attempt HTTP/3 over QUIC first, then fall back to the normal reqwest transport when the origin or network does not support it.
- **Continuity.** Queue records are designed to be replicated as CRDT operations later; the local encrypted SQLite database remains authoritative while offline.
- **Safe extensibility.** Post-processing runs behind an explicit WASM/WASI capability boundary instead of arbitrary native scripts.

## Repository layout

```text
aether-stream/
├── apps/
│   ├── desktop/                 # Tauri 2 + Svelte 5 + Tailwind UI
│   │   ├── src/lib/             # Cinematic UI components
│   │   └── src-tauri/           # Native commands and event bridge
│   └── extension/               # Manifest V3 TypeScript bridge/media observer
├── crates/
│   └── core-engine/             # DownloadManager and SQLite storage boundary
├── packages/
│   ├── data/prisma/             # Shared queue schema contract
│   └── p2p-adapter/             # Explicit WebTorrent fallback boundary
├── docs/
│   ├── ARCHITECTURE.md
│   └── ROADMAP.md
├── scripts/init-aether-stream.sh
├── Cargo.toml                   # Rust workspace
├── pnpm-workspace.yaml
└── package.json
```

## Bootstrap a fresh checkout

The exact, repeatable commands are captured in [`scripts/init-aether-stream.sh`](scripts/init-aether-stream.sh). From the `aether-stream` directory:

```bash
corepack enable
pnpm install
cargo fetch
pnpm --filter @aether-stream/desktop check
pnpm --filter @aether-stream/extension check
pnpm --filter @aether-stream/p2p-adapter check
cargo test -p aether-core
```

HTTP/3 in reqwest is an opt-in unstable surface at the time of this scaffold. The workspace `.cargo/config.toml` enables the required `reqwest_unstable` cfg for local builds. If a future reqwest release removes that gate, delete the cfg and retain the `http3` feature.

## Run the desktop shell

```bash
pnpm --filter @aether-stream/desktop tauri dev
```

The current UI ships with deterministic demo queue data so the visual system can be reviewed without a backend or network. The browser preview intentionally opens at the lock screen; use any four characters to inspect the demo interface. A real Tauri launch reads the SQLCipher key from the OS keychain and requires a first-run Argon2id passphrase enrollment. The Tauri bridge uses the biometry plugin for supported macOS, Windows, iOS, and Android targets; Linux remains an explicit desktop-portal/PAM adapter boundary.

## Engineering contracts

1. **The UI never talks to a public localhost HTTP server.** Tauri `invoke` and an authenticated native bridge are the only desktop transports.
2. **A ranged response must be `206 Partial Content`.** If an origin ignores a range request, the manager abandons segmentation and streams the file once rather than corrupting it.
3. **Temporary chunks are private and atomic.** Parts are written beneath a per-download staging directory and assembled only after every part validates.
4. **Every optional capability is observable locally.** Protocol choice, chunk progress, plugin execution, and sync state are emitted as local events; nothing is uploaded implicitly.
5. **Plugins receive capabilities, not ambient authority.** The WASM host will grant explicit filesystem/network/time permissions per job.

## Deliverables in this scaffold

- Mermaid system architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Initialization commands: [`scripts/init-aether-stream.sh`](scripts/init-aether-stream.sh) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- HTTP/3 + multi-segment Rust engine: [`crates/core-engine/src/lib.rs`](crates/core-engine/src/lib.rs)
- Svelte 5 cinematic app lock: [`apps/desktop/src/lib/CinematicLockScreen.svelte`](apps/desktop/src/lib/CinematicLockScreen.svelte)
- Svelte 5 cinematic download card: [`apps/desktop/src/lib/CinematicDownloadCard.svelte`](apps/desktop/src/lib/CinematicDownloadCard.svelte)
- Rust Argon2id auth controller: [`crates/core-engine/src/auth.rs`](crates/core-engine/src/auth.rs)
- Explicit WebTorrent fallback boundary: [`packages/p2p-adapter/`](packages/p2p-adapter/)
- Four-phase execution plan: [`docs/ROADMAP.md`](docs/ROADMAP.md)
