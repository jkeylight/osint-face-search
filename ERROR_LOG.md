# Error Log

Forensic record of every build failure, lint issue, runtime panic, warning that affects correctness, or tooling error. Do not omit an error because it was later fixed; append the resolution and prevention details.

## Error ID: INIT-000 | 2026-08-27 14:06 IST
- **Component:** Documentation Control Plane
- **Severity:** Low
- **Error Message / Stack Trace:**
  ```text
  No product error. This entry records initialization of the mandatory error log.
  ```
- **Root Cause Analysis:** No failure was observed during creation. A baseline entry is required so future failures have a stable, searchable log from the first session onward.
- **Resolution / Workaround:** Created `ERROR_LOG.md` with a structured schema and an explicit no-silent-failures policy.
- **Prevention:** Append an exact command output, root-cause deduction, fix, and prevention step for every future error; never replace or delete historical entries.

## Error ID: ERR-001 | 2026-08-27 14:10 IST
- **Component:** Release Pipeline / Toolchain Discovery
- **Severity:** Low
- **Error Message / Stack Trace:**
  ```text
  /bin/bash: line 1: pnpm: command not found
  ```
- **Root Cause Analysis:** The repository declares `pnpm@10.15.0` through the `packageManager` field, but the standalone `pnpm` executable is not installed on this build host. Corepack can still resolve and execute the pinned package manager through `corepack pnpm`.
- **Resolution / Workaround:** No product workaround was introduced. The verified release commands will invoke the repository-pinned package manager as `corepack pnpm`; `corepack pnpm --version` and the Tauri CLI version check succeeded afterward.
- **Prevention:** Release documentation and CI commands will use `corepack pnpm` (or an explicitly provisioned pnpm binary), never assume a globally installed pnpm executable. A release preflight will check Node, Corepack, Rust/Cargo, and platform bundler prerequisites before attempting compilation.

## Error ID: ERR-002 | 2026-08-27 14:15 IST
- **Component:** Tauri Native Production Build / Rust Toolchain
- **Severity:** High
- **Error Message / Stack Trace:**
  ```text
  failed to run 'cargo metadata' command to get workspace directory: failed to run command cargo metadata --no-deps --format-version 1: No such file or directory (os error 2)
         Error failed to run 'cargo metadata' command to get workspace directory: failed to run command cargo metadata --no-deps --format-version 1: No such file or directory (os error 2)
  undefined
  /home/user/osint-face-search/aether-stream/apps/desktop:
   ERR_PNPM_RECURSIVE_EXEC_FIRST_FAIL  Command failed with exit code 1: tauri build --ci
  ```
- **Root Cause Analysis:** The official Tauri release command reached the Tauri CLI but the build host has no `cargo` executable. Tauri cannot resolve the Cargo workspace or compile the Rust/SQLCipher native shell without the Rust stable toolchain.
- **Resolution / Workaround:** No temporary runtime workaround was used and no artifact was falsely reported. The required resolution is to run the same release command on a provisioned native/CI runner with Rust stable, Cargo, and the platform-specific Tauri prerequisites installed.
- **Prevention:** The production release document now includes a hard preflight for `rustc`, `cargo`, Tauri CLI, and platform libraries. The release gate forbids publishing until `tauri build --ci` exits zero and the bundle directories contain verified artifacts.

## Error ID: ERR-003 | 2026-08-27 14:17 IST
- **Component:** Tauri Environment Inspection / pnpm Workspace Resolution
- **Severity:** Low
- **Error Message / Stack Trace:**
  ```text
  [-] Packages
      - @tauri-apps/api  ⱼₛ: not installed!
  ```
- **Root Cause Analysis:** `tauri info` did not resolve the pnpm workspace symlink for `@tauri-apps/api` during its package inspection. The package is declared in `apps/desktop/package.json`, present in `pnpm-lock.yaml`, and linked under `apps/desktop/node_modules/@tauri-apps/api`.
- **Resolution / Workaround:** No dependency change was made. The desktop Svelte check and production Vite build both completed successfully, confirming the package is resolvable by the actual build toolchain. The warning is isolated to the diagnostic command's package inspection.
- **Prevention:** Treat `tauri info` as a diagnostic signal rather than the dependency resolver; retain the frozen pnpm install, lockfile, TypeScript check, and production Vite build as the authoritative JavaScript dependency gates.

## Error ID: ERR-004 | 2026-08-27 15:13 IST
- **Component:** Windows Production Release Preflight / Rust Toolchain
- **Severity:** High
- **Error Message / Stack Trace:**
  ```text
  $ rustc --version
  bash: rustc: command not found
  ```
- **Root Cause Analysis:** The Windows build machine has Node.js/Corepack/pnpm available, but Rust stable and Cargo are not installed or are not on the Git Bash `PATH`. Tauri cannot compile the native desktop shell without them.
- **Resolution / Workaround:** No development-server workaround is applicable. Install the official Rust stable MSVC toolchain on the Windows release machine, reopen Git Bash so the Rust path is loaded, and verify `rustc --version` and `cargo --version` before invoking `tauri build --ci`.
- **Prevention:** Keep `rustc --version` and `cargo --version` as hard release preflight gates; never publish a native artifact after a missing-toolchain result.

## Error ID: ERR-005 | 2026-08-27 15:14 IST
- **Component:** JavaScript Dependency Installation / pnpm Lifecycle Policy
- **Severity:** Medium
- **Error Message / Stack Trace:**
  ```text
  Ignored build scripts: @prisma/client, @prisma/engines, bufferutil,
  esbuild, ip-set, node-datachannel, prisma, utf-8-validate, utp-native.
  Run "pnpm approve-builds" to pick which dependencies should be allowed to run scripts.
  ```
- **Root Cause Analysis:** pnpm 10 intentionally blocks dependency lifecycle scripts by default. The install completed, but packages that need postinstall/native preparation were not allowed to run their scripts.
- **Resolution / Workaround:** No global package-manager upgrade was used. Before the production frontend/native build, approve only the dependencies required by the selected artifact: `esbuild` is required for the Vite release bundle; Prisma packages are not required by the native runtime; the P2P native packages are only required if the optional P2P runtime is shipped. Use the pinned command `corepack pnpm approve-builds` and select the required packages.
- **Prevention:** Record the approved build-dependency allowlist in the release environment and review it whenever dependencies change. Keep pnpm pinned at `10.15.0`; do not broadly enable every lifecycle script without review.
