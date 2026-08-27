<script lang="ts">
  import { onMount } from "svelte";
  import CinematicDownloadCard from "./lib/CinematicDownloadCard.svelte";
  import type { DownloadSnapshot } from "./lib/types";

  type Filter = "all" | "active" | "complete";
  type CoreEvent = {
    type: "state" | "chunk" | "progress" | "finished" | "failed";
    id: string;
    state?: string;
    chunk_index?: number;
    completed_bytes?: number;
    expected_bytes?: number;
    total_bytes?: number | null;
    speed_bps?: number;
    bytes_written?: number;
  };

  let activeFilter = $state<Filter>("all");
  let commandOpen = $state(false);
  let downloads = $state<DownloadSnapshot[]>([
    {
      id: "aurora-01",
      name: "aurora-observatory-4k.mov",
      source: "cdn.aether-labs.net",
      destination: "~/Movies/Research",
      totalBytes: 8_410_000_000,
      completedBytes: 5_637_000_000,
      speedBps: 38_400_000,
      etaSeconds: 72,
      status: "downloading",
      protocol: "HTTP/3",
      encrypted: true,
      chunks: Array.from({ length: 12 }, (_, index) => ({
        index,
        state: index < 7 ? "complete" : index === 7 || index === 8 ? "active" : "pending",
        progress: index < 7 ? 1 : index === 7 ? 0.72 : index === 8 ? 0.38 : 0,
        throughputBps: index === 7 ? 16_400_000 : index === 8 ? 12_100_000 : 0
      }))
    },
    {
      id: "dataset-02",
      name: "open-astronomy-dataset.tar.zst",
      source: "mirror.publicdata.org",
      destination: "~/Datasets/Astronomy",
      totalBytes: 2_840_000_000,
      completedBytes: 2_840_000_000,
      speedBps: 0,
      etaSeconds: null,
      status: "complete",
      protocol: "HTTP/2",
      encrypted: false,
      chunks: Array.from({ length: 8 }, (_, index) => ({
        index,
        state: "complete",
        progress: 1,
        throughputBps: 0
      }))
    },
    {
      id: "field-notes-03",
      name: "field-notes-august.pdf",
      source: "archive.example.org",
      destination: "~/Documents/Field notes",
      totalBytes: 180_000_000,
      completedBytes: 62_000_000,
      speedBps: 8_700_000,
      etaSeconds: 14,
      status: "paused",
      protocol: "HTTP/1.1",
      encrypted: true,
      chunks: Array.from({ length: 4 }, (_, index) => ({
        index,
        state: index < 1 ? "complete" : index === 1 ? "active" : "pending",
        progress: index < 1 ? 1 : index === 1 ? 0.48 : 0,
        throughputBps: 0
      }))
    }
  ]);

  let visibleDownloads = $derived(
    downloads.filter((download) => {
      if (activeFilter === "active") return download.status === "downloading" || download.status === "paused";
      if (activeFilter === "complete") return download.status === "complete";
      return true;
    })
  );
  let activeDownloads = $derived(downloads.filter((download) => download.status === "downloading").length);
  let completedBytes = $derived(downloads.reduce((sum, download) => sum + download.completedBytes, 0));
  let totalBytes = $derived(downloads.reduce((sum, download) => sum + download.totalBytes, 0));

  const formatBytes = (bytes: number) => {
    if (bytes >= 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(1)} GB`;
    if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(0)} MB`;
    return `${(bytes / 1_000).toFixed(0)} KB`;
  };

  function patchDownload(id: string, patch: Partial<DownloadSnapshot>) {
    downloads = downloads.map((download) => (download.id === id ? { ...download, ...patch } : download));
  }

  function toggleDownload(id: string) {
    const item = downloads.find((download) => download.id === id);
    if (!item || item.status === "complete") return;
    patchDownload(id, { status: item.status === "downloading" ? "paused" : "downloading" });
  }

  function cancelDownload(id: string) {
    patchDownload(id, { status: "failed", speedBps: 0, etaSeconds: null });
  }

  function applyCoreEvent(event: CoreEvent) {
    const item = downloads.find((download) => download.id === event.id);
    if (!item) return;

    if (event.type === "progress") {
      const completed = event.completed_bytes ?? item.completedBytes;
      const speed = event.speed_bps ?? item.speedBps;
      patchDownload(event.id, {
        completedBytes: completed,
        speedBps: speed,
        etaSeconds: speed > 0 ? Math.ceil((item.totalBytes - completed) / speed) : item.etaSeconds
      });
      return;
    }

    if (event.type === "chunk" && event.chunk_index !== undefined) {
      const index = event.chunk_index;
      const expected = event.expected_bytes ?? 1;
      const done = event.completed_bytes ?? 0;
      const state = event.state === "complete" ? "complete" : "active";
      patchDownload(event.id, {
        chunks: item.chunks.map((chunk, chunkIndex) =>
          chunkIndex === index ? { ...chunk, state, progress: Math.min(1, done / expected) } : chunk
        )
      });
      return;
    }

    const stateMap: Record<string, DownloadSnapshot["status"]> = {
      queued: "queued",
      downloading: "downloading",
      complete: "complete",
      cancelled: "paused",
      failed: "failed"
    };
    if (event.type === "finished") patchDownload(event.id, { status: "complete", speedBps: 0, etaSeconds: null });
    else if (event.state && stateMap[event.state]) patchDownload(event.id, { status: stateMap[event.state] });
    if (event.type === "failed") patchDownload(event.id, { status: "failed", speedBps: 0, etaSeconds: null });
  }

  onMount(() => {
    let disposeBridge: (() => void) | undefined;
    if ("__TAURI_INTERNALS__" in window) {
      void import("@tauri-apps/api/event").then(async ({ listen }) => {
        disposeBridge = await listen<CoreEvent>("download://event", ({ payload }) => applyCoreEvent(payload));
      });
    }


    const keydown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        commandOpen = !commandOpen;
      }
      if (event.key === "Escape") commandOpen = false;
    };
    window.addEventListener("keydown", keydown);

    // Demo telemetry keeps the scaffold alive when launched without a Tauri
    // backend. Real values will arrive from `download://event`.
    const ticker = window.setInterval(() => {
      const item = downloads.find((download) => download.status === "downloading");
      if (!item || item.completedBytes >= item.totalBytes) return;
      const next = Math.min(item.totalBytes, item.completedBytes + item.speedBps * 0.5);
      patchDownload(item.id, { completedBytes: next, etaSeconds: Math.ceil((item.totalBytes - next) / item.speedBps) });
    }, 500);

    return () => {
      window.removeEventListener("keydown", keydown);
      window.clearInterval(ticker);
      disposeBridge?.();
    };
  });
</script>

<svelte:head>
  <title>AETHER-STREAM · Ingest at the speed of thought</title>
  <meta
    name="description"
    content="AETHER-STREAM is a privacy-first, cinematic download and data-ingestion engine."
  />
</svelte:head>

<div class="min-h-screen overflow-hidden bg-[#080a0f] text-[#f5f7fb] selection:bg-cyan-300/20">
  <div class="pointer-events-none fixed inset-0 opacity-70 [background-image:linear-gradient(rgba(255,255,255,0.025)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.025)_1px,transparent_1px)] [background-size:72px_72px] [mask-image:radial-gradient(ellipse_at_top,black,transparent_75%)]"></div>
  <div class="pointer-events-none fixed -left-40 -top-44 h-[34rem] w-[34rem] rounded-full bg-cyan-400/10 blur-[130px]"></div>
  <div class="pointer-events-none fixed -right-40 top-1/3 h-[30rem] w-[30rem] rounded-full bg-violet-500/10 blur-[140px]"></div>

  <header class="relative z-10 border-b border-white/[0.07] bg-[#080a0f]/75 backdrop-blur-2xl">
    <div class="mx-auto flex h-[4.5rem] max-w-[1440px] items-center justify-between px-6 lg:px-10">
      <div class="flex items-center gap-3">
        <div class="relative grid h-10 w-10 place-items-center overflow-hidden rounded-xl border border-cyan-200/20 bg-cyan-200/[0.08] shadow-[0_0_32px_rgba(34,211,238,0.12)]">
          <div class="absolute inset-0 bg-[conic-gradient(from_180deg,transparent,rgba(103,232,249,0.22),transparent)]"></div>
          <span class="relative font-mono text-sm font-bold tracking-[-0.15em] text-cyan-200">A_</span>
        </div>
        <div>
          <div class="text-[0.8rem] font-semibold tracking-[0.28em] text-white">AETHER-STREAM</div>
          <div class="mt-0.5 font-mono text-[0.58rem] uppercase tracking-[0.24em] text-slate-500">local / unbounded / private</div>
        </div>
      </div>

      <nav class="hidden items-center gap-1 rounded-full border border-white/[0.07] bg-white/[0.025] p-1 md:flex" aria-label="Primary navigation">
        <button class="rounded-full bg-white/[0.09] px-4 py-2 text-xs font-medium text-white" type="button">Mission control</button>
        <button class="rounded-full px-4 py-2 text-xs font-medium text-slate-500 transition hover:text-white" type="button">Archive</button>
        <button class="rounded-full px-4 py-2 text-xs font-medium text-slate-500 transition hover:text-white" type="button">Automations</button>
      </nav>

      <div class="flex items-center gap-3">
        <button
          class="hidden items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 font-mono text-[0.65rem] text-slate-400 transition hover:border-cyan-300/30 hover:text-cyan-100 sm:flex"
          type="button"
          onclick={() => (commandOpen = true)}
          aria-label="Open command palette"
        >
          <span class="text-slate-600">⌘</span>K
        </button>
        <div class="flex items-center gap-2 rounded-full border border-emerald-300/15 bg-emerald-300/[0.06] px-3 py-1.5 font-mono text-[0.62rem] uppercase tracking-[0.18em] text-emerald-200">
          <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-300 shadow-[0_0_12px_#6ee7b7]"></span>
          offline core
        </div>
      </div>
    </div>
  </header>

  <main class="relative z-10 mx-auto max-w-[1440px] px-6 pb-16 pt-12 lg:px-10 lg:pt-16">
    <section class="mb-12 flex flex-col justify-between gap-8 lg:flex-row lg:items-end">
      <div class="max-w-2xl">
        <div class="mb-5 flex items-center gap-3 font-mono text-[0.65rem] uppercase tracking-[0.22em] text-cyan-200/70">
          <span class="h-px w-8 bg-cyan-300/60"></span>
          transport / zero telemetry
        </div>
        <h1 class="max-w-xl text-4xl font-medium leading-[1.02] tracking-[-0.055em] text-white sm:text-6xl">
          Ingest at the
          <span class="bg-gradient-to-r from-cyan-100 via-white to-violet-200 bg-clip-text text-transparent"> speed of thought.</span>
        </h1>
        <p class="mt-6 max-w-xl text-sm leading-7 text-slate-400 sm:text-base">
          A quiet, adaptive transfer plane for files that matter. QUIC-first transport, 64-way continuity, and a queue that stays yours.
        </p>
      </div>
      <div class="flex items-center gap-3">
        <button class="rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm font-medium text-slate-200 transition hover:border-cyan-200/30 hover:bg-cyan-200/[0.08]" type="button">
          Import queue
        </button>
        <button class="group flex items-center gap-3 rounded-xl bg-cyan-200 px-4 py-3 text-sm font-semibold text-[#071014] shadow-[0_12px_40px_-14px_rgba(103,232,249,0.85)] transition hover:-translate-y-0.5 hover:bg-cyan-100" type="button">
          <span class="grid h-5 w-5 place-items-center rounded-full bg-[#071014]/10 text-lg leading-none">+</span>
          New transfer
        </button>
      </div>
    </section>

    <section class="mb-10 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-white/[0.07] bg-white/[0.07] lg:grid-cols-4" aria-label="Queue summary">
      <div class="bg-[#0d1017]/90 px-5 py-5 sm:px-6">
        <div class="font-mono text-[0.6rem] uppercase tracking-[0.2em] text-slate-600">Active lanes</div>
        <div class="mt-3 text-2xl font-light tracking-[-0.04em] text-white">{String(activeDownloads).padStart(2, "0")}</div>
      </div>
      <div class="bg-[#0d1017]/90 px-5 py-5 sm:px-6">
        <div class="font-mono text-[0.6rem] uppercase tracking-[0.2em] text-slate-600">In flight</div>
        <div class="mt-3 text-2xl font-light tracking-[-0.04em] text-white">{formatBytes(completedBytes)} <span class="text-sm text-slate-600">/ {formatBytes(totalBytes)}</span></div>
      </div>
      <div class="bg-[#0d1017]/90 px-5 py-5 sm:px-6">
        <div class="font-mono text-[0.6rem] uppercase tracking-[0.2em] text-slate-600">Transport</div>
        <div class="mt-3 flex items-center gap-2 text-2xl font-light tracking-[-0.04em] text-white">QUIC <span class="rounded bg-cyan-300/10 px-1.5 py-0.5 font-mono text-[0.58rem] tracking-[0.15em] text-cyan-200">H3</span></div>
      </div>
      <div class="bg-[#0d1017]/90 px-5 py-5 sm:px-6">
        <div class="font-mono text-[0.6rem] uppercase tracking-[0.2em] text-slate-600">Privacy state</div>
        <div class="mt-3 flex items-center gap-2 text-sm font-medium text-emerald-200"><span class="h-2 w-2 rounded-full bg-emerald-300"></span> Nothing leaves device</div>
      </div>
    </section>

    <section>
      <div class="mb-5 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <div class="font-mono text-[0.62rem] uppercase tracking-[0.22em] text-slate-600">Queue / live telemetry</div>
          <h2 class="mt-2 text-xl font-medium tracking-[-0.03em] text-white">Current transfers</h2>
        </div>
        <div class="flex items-center gap-1 rounded-lg border border-white/[0.07] bg-white/[0.025] p-1" role="tablist" aria-label="Filter transfers">
          {#each [["all", "All"], ["active", "In flight"], ["complete", "Complete"]] as [value, label]}
            <button
              class={`rounded-md px-3 py-1.5 text-xs transition hover:text-slate-200 ${activeFilter === value ? "bg-white/10 text-white" : "text-slate-500"}`}
              type="button"
              role="tab"
              aria-selected={activeFilter === value}
              onclick={() => (activeFilter = value as Filter)}
            >{label}</button>
          {/each}
        </div>
      </div>

      <div class="grid gap-4 xl:grid-cols-2">
        {#each visibleDownloads as download (download.id)}
          <CinematicDownloadCard
            {download}
            onPause={toggleDownload}
            onCancel={cancelDownload}
          />
        {/each}
      </div>
    </section>

    <footer class="mt-14 flex flex-col justify-between gap-3 border-t border-white/[0.06] pt-5 font-mono text-[0.6rem] uppercase tracking-[0.18em] text-slate-700 sm:flex-row">
      <span>AETHER-STREAM / open-core transfer plane</span>
      <span>engine v0.1 · sqlite local · telemetry disabled</span>
    </footer>
  </main>
</div>

{#if commandOpen}
  <div class="fixed inset-0 z-50 flex items-start justify-center bg-[#030406]/70 px-5 pt-[16vh] backdrop-blur-md" role="presentation" onclick={(event) => event.currentTarget === event.target && (commandOpen = false)}>
    <div class="w-full max-w-xl overflow-hidden rounded-2xl border border-white/10 bg-[#10141d] shadow-2xl" role="dialog" aria-modal="true" aria-label="Command palette">
      <div class="flex items-center gap-3 border-b border-white/[0.07] px-5 py-4">
        <span class="font-mono text-cyan-200">⌘</span>
        <input class="w-full bg-transparent text-sm text-white outline-none placeholder:text-slate-600" placeholder="Search commands..." />
        <kbd class="rounded border border-white/10 px-1.5 py-0.5 font-mono text-[0.6rem] text-slate-500">ESC</kbd>
      </div>
      <div class="p-2">
        <button class="flex w-full items-center justify-between rounded-xl bg-white/[0.06] px-4 py-3 text-left text-sm text-white" type="button" onclick={() => (commandOpen = false)}>
          <span>Start a new transfer</span><span class="font-mono text-[0.62rem] text-slate-600">↵</span>
        </button>
        <button class="flex w-full items-center justify-between rounded-xl px-4 py-3 text-left text-sm text-slate-400 hover:bg-white/[0.04] hover:text-white" type="button" onclick={() => (commandOpen = false)}>
          <span>Open privacy settings</span><span class="font-mono text-[0.62rem] text-slate-600">P</span>
        </button>
      </div>
    </div>
  </div>
{/if}
