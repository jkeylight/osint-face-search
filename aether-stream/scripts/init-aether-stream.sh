#!/usr/bin/env bash
# Bootstrap a fresh AETHER-STREAM checkout.
# Usage: bash scripts/init-aether-stream.sh [target-directory]
set -Eeuo pipefail

TARGET="${1:-aether-stream}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'Missing prerequisite: %s\n' "$1" >&2
    exit 1
  }
}

need node
need pnpm
need cargo

if [[ -e "$TARGET" && -n "$(find "$TARGET" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  printf 'Refusing to overwrite non-empty directory: %s\n' "$TARGET" >&2
  exit 1
fi

mkdir -p "$TARGET"

# Tauri 2 + Svelte 5 + TypeScript. The CLI keeps the frontend and src-tauri
# projects wired for the current platform.
pnpm create tauri-app@latest "$TARGET/apps/desktop" \
  --template svelte-ts \
  --identifier com.aether.stream

# Make the native engine an explicit Cargo workspace member.
mkdir -p "$TARGET/crates" "$TARGET/apps/extension/src" "$TARGET/packages/data/prisma" "$TARGET/docs"
cargo new "$TARGET/crates/core-engine" --lib --name aether-core

cat > "$TARGET/pnpm-workspace.yaml" <<'YAML'
packages:
  - apps/*
  - packages/*
YAML

cat > "$TARGET/Cargo.toml" <<'TOML'
[workspace]
members = [
  "crates/core-engine",
  "apps/desktop/src-tauri",
]
resolver = "2"
TOML

# Tailwind v4 is Vite-native. Svelte Motion is the Svelte 5 / Framer Motion
# compatible layer; React's framer-motion package is intentionally not pulled
# into a Svelte runtime.
pnpm --dir "$TARGET" install
pnpm --dir "$TARGET" --filter desktop add @tauri-apps/api @humanspeak/svelte-motion
pnpm --dir "$TARGET" --filter desktop add -D tailwindcss @tailwindcss/vite

# Enable reqwest's current HTTP/3 gate for the workspace.
mkdir -p "$TARGET/.cargo"
cat > "$TARGET/.cargo/config.toml" <<'TOML'
[build]
rustflags = ["--cfg", "reqwest_unstable"]
TOML

# Pull Rust dependencies and validate the empty engine before adding product code.
(
  cd "$TARGET"
  cargo fetch
  cargo test --workspace
)

printf '\nAETHER-STREAM bootstrap complete at %s\n' "$TARGET"
printf 'Next: copy the scaffold files into the generated workspace, then run pnpm dev.\n'
printf 'Reference architecture: %s/docs/ARCHITECTURE.md\n' "$ROOT"
