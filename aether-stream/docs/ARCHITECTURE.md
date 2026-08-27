# AETHER-STREAM architecture

AETHER-STREAM inverts the legacy download-manager assumptions: the native core owns transport and state, the UI is a replaceable projection, and the browser integration is a narrow, authenticated intent source.

## Reproducible initialization

For a new checkout, these are the exact non-interactive setup commands (the
scripted equivalent is `scripts/init-aether-stream.sh`):

```bash
corepack enable
mkdir -p aether-stream/apps aether-stream/crates aether-stream/packages
cd aether-stream

pnpm create tauri-app@latest apps/desktop \
  --template svelte-ts \
  --identifier com.aether.stream
cargo new crates/core-engine --lib --name aether-core

cat > pnpm-workspace.yaml <<'YAML'
packages:
  - apps/*
  - packages/*
YAML

# Add the native/web dependencies after the generated package exists.
pnpm install
# The generated package is named `desktop`; rename it to
# `@aether-stream/desktop` when adopting the committed package metadata.
pnpm --filter desktop add @tauri-apps/api @humanspeak/svelte-motion
pnpm --filter desktop add -D tailwindcss @tailwindcss/vite
# After adding packages/data/package.json from the scaffold:
pnpm --filter @aether-stream/data add @prisma/client
pnpm --filter @aether-stream/data add -D prisma

# reqwest's current H3 surface is gated behind this cfg.
mkdir -p .cargo
printf '[build]\\nrustflags = ["--cfg", "reqwest_unstable"]\\n' > .cargo/config.toml
cargo fetch
cargo test --workspace
pnpm --filter @aether-stream/desktop check
```

The committed workspace already contains the generated files plus the product
scaffold; the commands above are the clean-room recipe rather than a command
to run over the populated directory.

## System diagram

```mermaid
flowchart LR
    subgraph Browser[User browser]
        Extension["Manifest V3 extension\nTypeScript\nSPA-safe route observer"]
        Page["Current page\nDOM + Performance entries"]
        Page --> Extension
    end

    subgraph Desktop[Local device · Tauri 2]
        UI["Svelte 5 UI\nTailwind + Framer-compatible motion\n120 fps intent"]
        Bridge["Tauri invoke / event bridge\ncapability-scoped commands"]
        Core["Rust core engine\nDownloadManager\nQUIC / HTTP·1.1 fallback"]
        Store["SQLite\nrusqlite runtime\nPrisma schema contract"]
        Plugin["WASM/WASI plugin host\nexplicit capabilities"]
        Secrets["OS keychain\noptional queue-key envelope"]

        UI <-->|typed commands + local events| Bridge
        Bridge <-->|in-process calls + event bus| Core
        Core <-->|queue, chunks, history| Store
        Core -->|post-download job| Plugin
        Core -->|URLs, auth headers, queue keys| Secrets
    end

    subgraph Network[External surfaces · opt-in per operation]
        Origin["HTTP origins / CDNs\nHTTP/3 QUIC → HTTP/2/1.1"]
        Sync["Optional sync relay\nopaque encrypted CRDT ops"]
        ClamAV["Optional local ClamAV daemon"]
        Cloud["Optional S3-compatible target"]
    end

    Extension -->|signed download intent\n(native messaging / Tauri bridge)| Bridge
    Core -->|range requests + H3| Origin
    Core <-->|encrypted CRDT operations\nnever raw queue files| Sync
    Plugin -->|local socket, explicit permission| ClamAV
    Plugin -->|explicit upload capability| Cloud
```

## Boundaries and invariants

### Tauri frontend

- Renders state; it does not own sockets, file handles, or queue truth.
- Uses `invoke` for commands and a typed event stream for progress.
- The browser-facing code uses relative Tauri IPC, never `localhost` or `127.0.0.1`.
- Reduced-motion preferences and keyboard navigation are first-class, not polish added later.

### Rust core

`DownloadManager` owns a pair of reqwest clients:

1. an HTTP/3-prior-knowledge client, compiled with the `http3` feature;
2. a normal rustls client that negotiates HTTP/2 or HTTP/1.1.

A request is attempted through the H3 client first. Only transport errors fall back; an HTTP response such as `403`, `404`, or `416` is not silently retried with a different protocol. This keeps server semantics intact while making QUIC opportunistic rather than brittle.

A remote resource is segmented only when all of the following are true:

- a total size is known;
- the origin advertises byte ranges or answers a `bytes=0-0` probe with `206`;
- every ranged response validates as `206 Partial Content` and matches its expected byte count.

The segment planner caps at 64 parts and uses a minimum part size to avoid turning small files into coordination overhead. Parts are downloaded concurrently into a private staging directory and assembled in index order after validation. A failed or cancelled job never publishes a partially assembled destination.

### Persistence

`rusqlite` is the runtime storage driver because the queue lives beside the Rust engine and must remain available offline. `packages/data/prisma/schema.prisma` is the shared schema contract for TypeScript tooling, migrations, and future sync services; it points at the same SQLite file. The two layers must share migration IDs and schema tests—Prisma must not silently create a second database.

### Browser extension

The extension reports media candidates visible to the current page:

- `<video>`, `<audio>`, `<source>`, and download anchors;
- resource URLs surfaced by `performance.getEntriesByType('resource')`;
- HLS (`.m3u8`) and DASH (`.mpd`) manifests when the page exposes those URLs.

It observes DOM mutations and SPA history transitions without monkey-patching framework internals. It does not defeat DRM, extract protected media keys, or send page content to a remote service. The bridge should use native messaging or a signed Tauri protocol with an origin allowlist and a per-install nonce.

### Optional sync

A future sync relay receives only encrypted CRDT operations. The device generates an identity key, wraps an optional queue key in the OS keychain, and encrypts operation payloads before they leave the device. The relay cannot resume a file by itself; it only reconciles queue intent, byte checkpoints, and metadata between trusted devices.

## Threat model

| Asset / boundary | Threat | Design response |
|---|---|---|
| Queue URLs and filenames | Telemetry or accidental exfiltration | No analytics; local-only defaults; explicit encrypted sync opt-in |
| Downloaded file | Malicious content or path traversal | Canonical destination checks, staging directory, optional ClamAV pipeline |
| Browser bridge | Arbitrary websites invoking native actions | Native-messaging allowlist, signed request envelope, nonce, user confirmation for new origins |
| WASM post-processing | Plugin escape / ambient file access | WASI capability set, memory/fuel limits, no ambient network, audited host functions |
| Partial chunks | Corruption after cancellation | Per-part byte validation, atomic final assembly, resumable manifest |
| Credentials | Key leakage in logs or sync | OS keychain, redacted events, no headers in UI telemetry or CRDT payloads |

## Deliberate stack correction

Framer Motion is React-specific. A Svelte 5 app cannot import React's `framer-motion` package without pulling in an incompatible rendering model. The scaffold uses [`@humanspeak/svelte-motion`](https://github.com/humanspeak/svelte-motion), a Svelte 5, Framer Motion-compatible implementation with the same declarative `motion.*` vocabulary. This preserves the requested interaction model without shipping React or violating Svelte's runtime boundary.
