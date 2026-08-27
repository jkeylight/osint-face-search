# AETHER-STREAM Production Release Pipeline

This is the production-only build and distribution procedure for the current AETHER-STREAM stack:

- Tauri 2 desktop shell
- Rust workspace with `aether-core`
- Svelte 5 + Vite + Tailwind frontend
- Manifest V3 TypeScript browser extension
- Optional TypeScript WebTorrent adapter

There is no server, Docker image, Next.js deployment, Flutter target, or Python runtime involved in the AETHER-STREAM desktop release. The native application is packaged by Tauri; the browser extension is distributed as a separate extension bundle.

## Release status of this checkout

The repository currently contains the desktop packaging configuration and frontend release surface, but this exact sandbox cannot produce a native installer because the host has no Cargo/Rust toolchain and is missing Tauri's Linux system libraries. The failed preflight is recorded in the repository-root `ERROR_LOG.md` as `ERR-001` and in `TTD_LOG.md`.

Do not label a release `production-ready` until a native build completes on each target runner, signing succeeds, and the artifact verification checklist below passes.

## 1. Production configuration

### Tracked configuration files

| File | Production responsibility |
| --- | --- |
| `package.json` | Pins pnpm through `packageManager: pnpm@10.15.0`; root scripts use `corepack pnpm`. |
| `pnpm-lock.yaml` | Locks the JavaScript dependency graph. Release installs must use `--frozen-lockfile`. |
| `apps/desktop/vite.config.ts` | Uses the Tauri WebView target, esbuild JavaScript minification, CSS minification, and no production source maps. Only `VITE_` variables can be exposed to frontend code. |
| `apps/desktop/src-tauri/tauri.conf.json` | Points Tauri at `../dist`, runs the production Vite build through `corepack pnpm build`, enables desktop bundles, configures CSP, and references the generated icon set. |
| `Cargo.toml` | Defines the Rust workspace and conservative release optimization: thin LTO, one codegen unit, and symbol stripping. |
| `.cargo/config.toml` | Retains the required `reqwest_unstable` cfg for the current HTTP/3 implementation. |
| `apps/desktop/src-tauri/Cargo.toml` | Declares the native Tauri shell, SQLCipher core, OS keychain, and biometric plugin dependencies. |
| `apps/extension/manifest.json` | Defines the MV3 production extension entry points and permissions. |
| `.env.example` | Documents the Prisma schema-contract URL and optional future sync relay. It is not a secret store and is not copied into a release. |

The effective release settings are already in the tracked files. The important portions are:

```json
// apps/desktop/src-tauri/tauri.conf.json
{
  "build": {
    "beforeBuildCommand": "corepack pnpm build",
    "frontendDist": "../dist"
  },
  "bundle": {
    "active": true,
    "targets": "all",
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/128x128@2x.png",
      "icons/icon.icns",
      "icons/icon.ico"
    ]
  }
}
```

```toml
# Cargo.toml
[profile.release]
lto = "thin"
codegen-units = 1
strip = "symbols"
```

```ts
// apps/desktop/vite.config.ts
build: {
  target: "chrome105" on Windows and "safari13" on macOS/Linux,
  minify: "esbuild",
  cssMinify: true,
  sourcemap: false
}
```

### Environment variables

No application secret belongs in Vite or in a checked-in `.env` file.

- `DATABASE_URL` is a Prisma compatibility-contract value only. The native runtime opens SQLCipher through `rusqlite`; it does not use Prisma to open the encrypted runtime database.
- `AETHER_SYNC_RELAY_URL` is currently an optional contract placeholder. It is not required for local-only operation.
- Do not use `VITE_DATABASE_URL`, `VITE_*PASSWORD*`, `VITE_*KEY*`, or any database/keychain value. Vite would embed `VITE_` variables into the frontend bundle.
- Signing credentials are injected only by the build host or CI secret store. They are never committed to Tauri configuration.

### Version gate

The current version is `0.1.0`. Before a release, keep these values identical:

- `aether-stream/package.json`
- `aether-stream/apps/desktop/package.json`
- `aether-stream/apps/desktop/src-tauri/Cargo.toml`
- `aether-stream/apps/desktop/src-tauri/tauri.conf.json`
- `aether-stream/apps/extension/manifest.json`

Do not publish an artifact if the Tauri, Cargo, npm, and extension versions disagree.

## 2. Builder prerequisites

Run the production build on the target operating system or on a CI runner for that operating system. Do not cross-compile as the primary release path.

### All builders

```bash
cd /absolute/path/to/osint-face-search/aether-stream

corepack enable
corepack pnpm install --frozen-lockfile

node --version
corepack pnpm --version
rustc --version
cargo --version
corepack pnpm --filter @aether-stream/desktop exec tauri --version
```

Rust must be the stable toolchain. The native build must have a committed workspace `Cargo.lock` before enabling a locked release gate. The current repository snapshot does not yet contain that generated lockfile because Cargo is unavailable in the capture environment.

### Linux x86_64 release runner

Use Debian 12 or Ubuntu 22.04 as the compatibility baseline for glibc and WebKitGTK 4.1:

```bash
sudo apt-get update
sudo apt-get install -y \
  libwebkit2gtk-4.1-dev \
  build-essential \
  curl \
  wget \
  file \
  libxdo-dev \
  libssl-dev \
  libayatana-appindicator3-dev \
  librsvg2-dev \
  patchelf \
  libfuse2
```

Install Rust with the official Rust installer on the release runner, then verify `rustc --version` and `cargo --version`. Build AppImage on the oldest supported Linux baseline; a newer glibc can make the AppImage unusable on older systems.

### Windows x64 release runner

Install on a native Windows runner:

- Visual Studio 2022 Build Tools with the Desktop C++ workload
- Windows 10/11 SDK
- WebView2 runtime
- WiX Toolset v3 for `.msi` output
- NSIS for `-setup.exe` output
- Node.js with Corepack
- Rust stable with the MSVC toolchain

The native Windows runner is the required path for MSI. Tauri documents NSIS cross-compilation, but it is not the primary release path for this project.

### macOS release runner

Install on a native macOS runner:

- Xcode and Xcode Command Line Tools
- Rust stable
- Node.js with Corepack
- Apple Developer ID Application certificate for direct distribution
- Apple notarization credentials for DMG/App bundle distribution

Verify the signing identity:

```bash
security find-identity -v -p codesigning
```

## 3. Icon and production asset generation

The single tracked source is:

```text
apps/desktop/assets/aether-stream-icon.svg
```

Generate the complete Tauri icon set before packaging:

```bash
cd /absolute/path/to/osint-face-search/aether-stream/apps/desktop
corepack pnpm icons:generate
```

Equivalent direct command:

```bash
corepack pnpm exec tauri icon \
  assets/aether-stream-icon.svg \
  --output src-tauri/icons \
  --ios-color "#080a0f"
```

The Tauri CLI generates the platform-specific icon formats and sizes under `apps/desktop/src-tauri/icons`. When mobile projects have been initialized, the CLI also writes the Android and iOS icon assets into their generated native projects. This checkout currently has no initialized `gen/android` or `gen/apple` project, so no Android APK/AAB or iOS IPA is a current deliverable.

The extension manifest currently does not declare toolbar icons, so no extension icon files are required for its current contract. If store icons are added later, they must be generated from the same SVG source and the manifest update must be recorded in `PROJECT_UPDATES.md` and `TTD_LOG.md` before implementation.

## 4. Production build commands

All commands below are release commands. None starts a development server.

### Desktop application: native host architecture

From `aether-stream/`:

```bash
export CARGO_TARGET_DIR="$PWD/target"
corepack pnpm --filter @aether-stream/desktop exec tauri build --ci
```

On PowerShell:

```powershell
$env:CARGO_TARGET_DIR = "$pwd\target"
corepack pnpm --filter @aether-stream/desktop exec tauri build --ci
```

`tauri build` invokes the configured `corepack pnpm build` first, which runs `vite build --mode production`, then compiles Rust with Cargo and creates the platform installers.

### Linux packages

```bash
export CARGO_TARGET_DIR="$PWD/target"
corepack pnpm --filter @aether-stream/desktop exec tauri build --ci --bundles deb,appimage
```

For RPM on an RPM-based release runner with the RPM bundler installed:

```bash
export CARGO_TARGET_DIR="$PWD/target"
corepack pnpm --filter @aether-stream/desktop exec tauri build --ci --bundles rpm
```

### Windows installers

Run on the native Windows x64 release runner:

```powershell
$env:CARGO_TARGET_DIR = "$pwd\target"
corepack pnpm --filter @aether-stream/desktop exec tauri build --ci
```

With `targets: "all"`, Tauri produces the NSIS setup executable and MSI when the corresponding Windows bundlers are available. Do not pass `--no-sign` for a public release.

### macOS direct distribution

For a universal Intel + Apple Silicon build, both Apple targets must be installed:

```bash
rustup target add aarch64-apple-darwin x86_64-apple-darwin

export APPLE_SIGNING_IDENTITY="Developer ID Application: YOUR ORGANIZATION (TEAMID)"
export CARGO_TARGET_DIR="$PWD/target"
corepack pnpm --filter @aether-stream/desktop exec tauri build \
  --ci \
  --target universal-apple-darwin \
  --bundles app,dmg
```

For a single native architecture, replace the target with `aarch64-apple-darwin` or `x86_64-apple-darwin`.

After the signed DMG is produced, notarize and staple it using Apple credentials held outside the repository:

```bash
xcrun notarytool submit \
  target/universal-apple-darwin/release/bundle/dmg/AETHER-STREAM_0.1.0_universal.dmg \
  --key "$APPLE_API_KEY_PATH" \
  --key-id "$APPLE_API_KEY" \
  --issuer "$APPLE_API_ISSUER" \
  --wait

xcrun stapler staple \
  target/universal-apple-darwin/release/bundle/macos/AETHER-STREAM.app

spctl --assess --type open --context context:primary-signature \
  target/universal-apple-darwin/release/bundle/macos/AETHER-STREAM.app
```

The exact DMG filename is emitted by Tauri and should be selected from the `bundle/dmg` directory if the platform appends a different architecture suffix. Never substitute a guessed filename in an automated release job.

### Browser extension

The extension is a separate MV3 artifact:

```bash
cd /absolute/path/to/osint-face-search/aether-stream
corepack pnpm --filter @aether-stream/extension build
```

The unpacked extension directory is:

```text
apps/extension/dist/
```

To create a distributable archive with `manifest.json` at the archive root and its referenced `dist/` files beneath it:

```bash
mkdir -p artifacts
cd apps/extension
zip -r ../../artifacts/aether-stream-capture-v0.1.0.zip manifest.json dist
```

The browser extension has a native-messaging permission, but this checkout does not yet ship a browser-specific native-host registration installer. Do not claim one-click extension-to-Tauri integration until that host registration and its tests are implemented.

## 5. Output locations and artifact inventory

With `CARGO_TARGET_DIR="$PWD/target"`, the final artifacts are under `aether-stream/target/`:

```text
target/release/aether-stream                         Native release executable

target/release/bundle/deb/AETHER-STREAM_*.deb        Debian installer
target/release/bundle/rpm/AETHER-STREAM_*.rpm        RPM installer
target/release/bundle/appimage/AETHER-STREAM_*.AppImage  Portable Linux bundle

target/release/bundle/nsis/AETHER-STREAM-*-setup.exe Windows NSIS installer
target/release/bundle/msi/AETHER-STREAM_*.msi        Windows MSI installer
target/release/bundle/macos/AETHER-STREAM.app       macOS application bundle
target/release/bundle/dmg/AETHER-STREAM_*.dmg       macOS DMG installer
```

For the universal macOS build, replace `target/release/` with `target/universal-apple-darwin/release/`.

Tauri may normalize the product name and add architecture/version suffixes. The directory and artifact class are stable; the release job must enumerate and checksum the files instead of hard-coding an unverified filename.

Create the release checksum manifest after the build:

```bash
mkdir -p artifacts
find target/release/bundle -type f -print0 \
  | sort -z \
  | xargs -0 sha256sum > artifacts/SHA256SUMS
```

For a universal macOS build, use `target/universal-apple-darwin/release/bundle` in the same command.

## 6. Signing and distribution

### Windows

Configure the certificate thumbprint, SHA-256 digest algorithm, and timestamp URL in the private release configuration or CI secret-backed configuration. The Tauri Windows signing fields are:

```json
{
  "bundle": {
    "windows": {
      "certificateThumbprint": "RELEASE_CERTIFICATE_THUMBPRINT",
      "digestAlgorithm": "sha256",
      "timestampUrl": "https://YOUR_TIMESTAMP_AUTHORITY"
    }
  }
}
```

Do not commit real certificate details or private keys to the repository. Verify the resulting installer with Microsoft `signtool`, then upload the signed `.msi` and `-setup.exe` to the project release page or the organization's HTTPS download endpoint.

### macOS

Use `APPLE_SIGNING_IDENTITY` for the Developer ID certificate. For CI, inject `APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID`, or the App Store Connect API key variables through the CI secret store. Upload only the notarized and stapled DMG/app artifacts.

### Linux

Publish the `.deb`, `.rpm`, and AppImage together with `SHA256SUMS` and a detached signature from the project's authenticated release channel. End-user installation commands are:

```bash
sudo apt install ./AETHER-STREAM_0.1.0_amd64.deb
sudo dnf install ./AETHER-STREAM-0.1.0-1.x86_64.rpm
chmod +x AETHER-STREAM_0.1.0_amd64.AppImage
./AETHER-STREAM_0.1.0_amd64.AppImage
```

### Browser extension

- For local enterprise distribution, distribute `artifacts/aether-stream-capture-v0.1.0.zip` through the organization's signed software channel.
- For Chrome/Edge/Firefox stores, upload the built extension according to each store's review and signing process.
- For unpacked QA installation, select `apps/extension/dist/` in the browser's extension developer UI. This is a QA installation path, not the end-user distribution artifact.

## 7. Release acceptance gate

A release is publishable only when all of the following are recorded:

- [ ] `corepack pnpm install --frozen-lockfile` completed.
- [ ] Frontend production build completed with no errors or warnings that affect correctness.
- [ ] Extension build completed and the generated manifest points to existing files.
- [ ] `cargo test --workspace` completed on the release toolchain.
- [ ] Native Tauri build completed on Windows, macOS, and Linux target runners.
- [ ] Installer signatures and macOS notarization verified.
- [ ] SQLCipher first-run database creation and OS-keychain bootstrap tested on a clean user profile.
- [ ] Locked UI rejects queue/history/media access before authentication.
- [ ] Password enrollment, Argon2id verification, lockout, biometric success, biometric cancellation, and relock tested.
- [ ] No telemetry, private key, database key, password, or relay secret appears in the bundle or logs.
- [ ] SHA-256 checksums generated and independently verified.
- [ ] `PROJECT_UPDATES.md`, `TTD_LOG.md`, and `ERROR_LOG.md` updated with the release decision and exact command output.

## Official Tauri references

- [Tauri distribution overview](https://v2.tauri.app/distribute/)
- [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/)
- [Tauri app icon generation](https://v2.tauri.app/develop/icons/)
- [Tauri Windows installers](https://v2.tauri.app/distribute/windows-installer/)
- [Tauri macOS application bundles](https://v2.tauri.app/distribute/macos-application-bundle/)
- [Tauri Debian packages](https://v2.tauri.app/distribute/debian/)
- [Tauri AppImage](https://v2.tauri.app/distribute/appimage/)
- [Tauri GitHub build pipelines](https://v2.tauri.app/distribute/pipelines/github/)
- [Tauri macOS code signing](https://v2.tauri.app/distribute/sign/macos/)
- [Tauri Windows code signing](https://v2.tauri.app/distribute/sign/windows/)
