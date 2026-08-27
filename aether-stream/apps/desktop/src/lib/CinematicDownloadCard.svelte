<script lang="ts">
  import { motion } from "@humanspeak/svelte-motion";
  import type { DownloadSnapshot } from "./types";

  type Props = {
    download: DownloadSnapshot;
    onPause?: (id: string) => void;
    onCancel?: (id: string) => void;
  };

  let { download, onPause = () => {}, onCancel = () => {} }: Props = $props();

  const ringRadius = 46;
  const ringCircumference = 2 * Math.PI * ringRadius;
  let progress = $derived(
    download.totalBytes > 0 ? Math.min(100, (download.completedBytes / download.totalBytes) * 100) : 0
  );
  let dashOffset = $derived(ringCircumference - (progress / 100) * ringCircumference);
  let activeChunkCount = $derived(download.chunks.filter((chunk) => chunk.state === "active").length);
  let completeChunkCount = $derived(download.chunks.filter((chunk) => chunk.state === "complete").length);

  const formatBytes = (bytes: number) => {
    if (bytes >= 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(2)} GB`;
    if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
    if (bytes >= 1_000) return `${(bytes / 1_000).toFixed(0)} KB`;
    return `${Math.round(bytes)} B`;
  };

  const formatSpeed = (bytes: number) => (bytes <= 0 ? "—" : `${formatBytes(bytes)}/s`);

  const formatEta = (seconds: number | null) => {
    if (seconds === null || !Number.isFinite(seconds)) return "—";
    if (seconds < 60) return `${seconds}s left`;
    return `${Math.floor(seconds / 60)}m ${seconds % 60}s left`;
  };

  const statusLabel = (status: DownloadSnapshot["status"]) => {
    if (status === "downloading") return "Transferring";
    if (status === "complete") return "Sealed";
    if (status === "paused") return "On hold";
    if (status === "failed") return "Needs attention";
    return "Queued";
  };

  const chunkClass = (state: DownloadSnapshot["chunks"][number]["state"]) => {
    if (state === "complete") return "bg-cyan-200 shadow-[0_0_10px_rgba(165,243,252,0.58)]";
    if (state === "active") return "bg-violet-300 shadow-[0_0_12px_rgba(196,181,253,0.6)] chunk-active";
    if (state === "error") return "bg-rose-300 shadow-[0_0_10px_rgba(253,164,175,0.5)]";
    return "bg-slate-700/80";
  };
</script>

<motion.div
  initial={{ opacity: 0, y: 16, scale: 0.985 }}
  animate={{ opacity: 1, y: 0, scale: 1 }}
  whileHover={{ y: -3 }}
  transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
  class="group relative overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0d1119]/90 p-5 shadow-[0_18px_70px_-35px_rgba(0,0,0,0.9)] backdrop-blur-xl sm:p-6"
>
  <div class="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_100%_0%,rgba(103,232,249,0.09),transparent_36%),radial-gradient(circle_at_0%_100%,rgba(167,139,250,0.07),transparent_32%)] opacity-80"></div>
  <div class="pointer-events-none absolute -right-20 -top-20 h-44 w-44 rounded-full border border-cyan-200/[0.05] transition duration-700 group-hover:scale-125"></div>

  <div class="relative flex items-start justify-between gap-4">
    <div class="min-w-0">
      <div class="mb-2 flex flex-wrap items-center gap-2 font-mono text-[0.58rem] uppercase tracking-[0.18em] text-slate-500">
        <span class="inline-flex items-center gap-1.5 rounded-full border border-cyan-200/15 bg-cyan-200/[0.06] px-2 py-1 text-cyan-100/80">
          <span class="h-1.5 w-1.5 rounded-full {download.status === 'downloading' ? 'animate-pulse bg-cyan-200' : 'bg-slate-500'}"></span>
          {statusLabel(download.status)}
        </span>
        <span>{download.protocol}</span>
        {#if download.encrypted}
          <span class="text-emerald-300/70">sealed</span>
        {/if}
      </div>
      <h3 class="truncate text-base font-medium tracking-[-0.02em] text-white sm:text-lg" title={download.name}>{download.name}</h3>
      <div class="mt-1 flex max-w-full items-center gap-2 truncate font-mono text-[0.65rem] text-slate-600">
        <span class="truncate">{download.source}</span>
        <span class="text-slate-800">→</span>
        <span class="truncate">{download.destination}</span>
      </div>
    </div>

    <motion.div
      animate={download.status === "complete" ? { scale: [1, 1.035, 1] } : { scale: 1 }}
      transition={{ type: "spring", stiffness: 260, damping: 18 }}
      class="relative h-[7.25rem] w-[7.25rem] shrink-0"
    >
      <svg class="h-full w-full -rotate-90" viewBox="0 0 112 112" role="img" aria-label={`${Math.round(progress)} percent complete`}>
        <circle cx="56" cy="56" r={ringRadius} fill="none" stroke="rgba(255,255,255,0.07)" stroke-width="5" />
        <circle
          cx="56"
          cy="56"
          r={ringRadius}
          fill="none"
          stroke={download.status === "complete" ? "#86efac" : `url(#ring-gradient-${download.id})`}
          stroke-width="5"
          stroke-linecap="round"
          stroke-dasharray={ringCircumference}
          style={`stroke-dashoffset: ${dashOffset}px`}
          class="ring-progress"
        />
        <defs>
          <linearGradient id={`ring-gradient-${download.id}`} x1="0" x2="1" y1="0" y2="1">
            <stop offset="0" stop-color="#67e8f9" />
            <stop offset="1" stop-color="#c4b5fd" />
          </linearGradient>
        </defs>
      </svg>
      <div class="absolute inset-0 grid place-items-center text-center">
        <div>
          <div class="font-mono text-xl tracking-[-0.08em] text-white">{Math.round(progress)}<span class="text-xs text-slate-500">%</span></div>
          <div class="mt-0.5 font-mono text-[0.52rem] uppercase tracking-[0.16em] text-slate-600">{completeChunkCount}/{download.chunks.length} sealed</div>
        </div>
      </div>
    </motion.div>
  </div>

  <div class="relative mt-6 grid grid-cols-3 gap-3 border-y border-white/[0.06] py-4">
    <div>
      <div class="font-mono text-[0.56rem] uppercase tracking-[0.18em] text-slate-600">velocity</div>
      <div class="mt-1 text-sm font-medium text-cyan-100">{formatSpeed(download.speedBps)}</div>
    </div>
    <div>
      <div class="font-mono text-[0.56rem] uppercase tracking-[0.18em] text-slate-600">remaining</div>
      <div class="mt-1 text-sm font-medium text-white">{formatEta(download.etaSeconds)}</div>
    </div>
    <div>
      <div class="font-mono text-[0.56rem] uppercase tracking-[0.18em] text-slate-600">payload</div>
      <div class="mt-1 text-sm font-medium text-white">{formatBytes(download.completedBytes)} <span class="text-slate-600">/ {formatBytes(download.totalBytes)}</span></div>
    </div>
  </div>

  <div class="relative mt-5">
    <div class="mb-2 flex items-center justify-between">
      <div class="flex items-center gap-2 font-mono text-[0.58rem] uppercase tracking-[0.18em] text-slate-600">
        <span>segment topology</span>
        <span class="text-violet-200/70">{activeChunkCount} live</span>
      </div>
      <div class="font-mono text-[0.58rem] text-slate-700">adaptive / max 64</div>
    </div>
    <div class="flex h-12 items-end gap-1 rounded-lg border border-white/[0.05] bg-black/20 px-2 py-2" aria-label={`${download.chunks.length} download segments`}>
      {#each download.chunks as chunk (chunk.index)}
        <div class="flex h-full min-w-0 flex-1 items-end" title={`Segment ${chunk.index + 1}: ${Math.round(chunk.progress * 100)}%`}>
          <div
            class="w-full min-w-[3px] rounded-sm transition-[height] duration-500 {chunkClass(chunk.state)}"
            style={`height: ${Math.max(8, chunk.progress * 100)}%`}
          ></div>
        </div>
      {/each}
    </div>
  </div>

  <div class="relative mt-5 flex items-center justify-between gap-3">
    <div class="flex items-center gap-2 font-mono text-[0.58rem] uppercase tracking-[0.16em] text-slate-700">
      <span class="h-1.5 w-1.5 rounded-full {download.status === 'complete' ? 'bg-emerald-300' : 'bg-cyan-200'}"></span>
      {download.status === "complete" ? "checksum verified" : "local event stream"}
    </div>
    <div class="flex items-center gap-2">
      {#if download.status !== "complete"}
        <button
          class="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-cyan-200/30 hover:text-white"
          type="button"
          onclick={() => onPause(download.id)}
        >{download.status === "downloading" ? "Pause" : "Resume"}</button>
        <button
          class="rounded-lg px-2 py-2 text-xs text-slate-600 transition hover:text-rose-200"
          type="button"
          aria-label={`Cancel ${download.name}`}
          onclick={() => onCancel(download.id)}
        >Cancel</button>
      {:else}
        <button class="rounded-lg border border-emerald-300/15 bg-emerald-300/[0.06] px-3 py-2 text-xs font-medium text-emerald-200" type="button">Reveal file</button>
      {/if}
    </div>
  </div>
</motion.div>

<style>
  .ring-progress {
    transition: stroke-dashoffset 800ms cubic-bezier(0.22, 1, 0.36, 1);
  }

  .chunk-active {
    animation: breathe 1.6s ease-in-out infinite;
  }

  @keyframes breathe {
    0%,
    100% { opacity: 0.55; }
    50% { opacity: 1; }
  }

  @media (prefers-reduced-motion: reduce) {
    .ring-progress { transition: none; }
    .chunk-active { animation: none; }
  }
</style>
