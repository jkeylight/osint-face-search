/* ═══════════════════════════════════════════════════════════════════════
   OSINT Face Search — frontend application (vanilla JS, no build step)
   ═══════════════════════════════════════════════════════════════════════ */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const S = {
  view: "search",
  system: null,
  enginesSel: new Set(),
  engineStatus: {},        // key -> {status, count, reason, ms}
  queryFile: null,
  analyze: null,
  job: null,               // current job (with results)
  jobResults: [],
  filters: { verdict: "all", minConf: 0, sort: "rank" },
  verify: { a: null, b: null },
  compareResult: null,
  es: null,                // EventSource
};

/* ─────────────────────────── api helper ─────────────────────────── */

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try { const j = await res.json(); if (j.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* noop */ }
    throw new Error(msg);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("json") ? res.json() : res.text();
}

function toast(msg, kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = msg;
  $("#toasts").appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .3s"; }, 3600);
  setTimeout(() => el.remove(), 4000);
}

const fmtTime = ts => new Date(ts * 1000).toLocaleString();
const fmtBytes = b => {
  if (b > 1e9) return (b / 1e9).toFixed(1) + " GB";
  if (b > 1e6) return (b / 1e6).toFixed(1) + " MB";
  if (b > 1e3) return (b / 1e3).toFixed(0) + " KB";
  return b + " B";
};
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ─────────────────────────── router ─────────────────────────── */

function navigate(view, param) {
  if (view !== "job") { teardownSSE(); stopJobPolling(); }
  S.view = view;
  $$(".view").forEach(v => v.hidden = v.id !== `view-${view}`);
  $$(".tab").forEach(t => t.classList.toggle("active", t.dataset.nav === view));
  $("#tab-job").hidden = view !== "job";
  if (view === "job" && param) loadJob(param);
  if (view === "gallery") loadGallery();
  if (view === "history") loadHistory();
  if (view === "system") loadSystem();
  if (view === "verify") resetVerifyUI();
  window.scrollTo({ top: 0 });
}

$$(".tab, .brand").forEach(el => el.addEventListener("click", () => navigate(el.dataset.nav)));

/* ═══════════════════════ system / backend ═══════════════════════ */

async function loadSystemInfo() {
  try {
    S.system = await api("/api/system");
  } catch (e) {
    toast("System info failed: " + e.message, "err");
    return;
  }
  const pill = $("#backend-pill");
  const face = S.system.face;
  $("#backend-name").textContent = face.active_backend === "none" ? "no face backend" : `face: ${face.active_backend}`;
  pill.classList.toggle("ok", face.available);
  pill.classList.toggle("warn", !face.available);
  pill.title = face.error || `embedding dim ${face.dim}`;
  renderEngines();
  if (!face.available) {
    const note = $("#face-err-note");
    note.hidden = false;
    note.textContent = "⚠ Face verification is unavailable: " + (face.error || "unknown error") +
      " — run scripts/download_models.py";
  }
}

function renderEngines() {
  const grid = $("#engine-grid");
  grid.innerHTML = "";
  const engines = S.system?.engines || [];
  if (!S.enginesSel.size) engines.forEach(e => S.enginesSel.add(e.key));
  for (const e of engines) {
    const row = document.createElement("div");
    row.className = "engine-row";
    const on = S.enginesSel.has(e.key);
    if (on) row.classList.add("on");
    row.innerHTML = `
      <div class="eng-check">✓</div>
      <div class="eng-info">
        <div class="eng-name">${esc(e.label)}</div>
        <div class="eng-desc">${esc(e.description)}</div>
      </div>
      <span class="eng-cat">${esc(e.category)}</span>
      <div class="eng-status">
        <span class="eng-dot ${e.available ? "ok" : "bad"}"
              title="${esc(e.available ? "reachable" : e.reason)}"></span>
        ${e.available ? "" : `<span class="est-info err" title="${esc(e.reason)}">n/a</span>`}
      </div>`;
    row.addEventListener("click", ev => {
      ev.stopPropagation();
      if (S.enginesSel.has(e.key)) S.enginesSel.delete(e.key); else S.enginesSel.add(e.key);
      row.classList.toggle("on", S.enginesSel.has(e.key));
    });
    grid.appendChild(row);
  }
  const unreachable = engines.filter(e => !e.available).length;
  const note = $("#engine-note");
  if (unreachable === engines.length && engines.length) {
    note.innerHTML = `⚠ None of the remote engines are reachable from this machine — the search will
      still run (gallery verification, local analysis). Check connectivity / proxy if you expect web engines to work.`;
  } else if (unreachable > 0) {
    note.textContent = `${unreachable} of ${engines.length} engines currently unreachable (hover the red dots for reasons).`;
  } else {
    note.textContent = "All engines reachable.";
  }
}

$("#eng-all").addEventListener("click", () => { (S.system?.engines || []).forEach(e => S.enginesSel.add(e.key)); renderEngines(); });
$("#eng-none").addEventListener("click", () => { S.enginesSel.clear(); renderEngines(); });

async function loadStats() {
  try {
    const s = await api("/api/stats");
    $("#st-jobs").textContent = s.jobs;
    $("#st-results").textContent = s.results;
    $("#st-matches").textContent = s.matches;
    $("#st-gallery").textContent = s.gallery_identities;
    const gc = $("#gallery-count");
    gc.hidden = !(s.gallery_identities > 0);
    gc.textContent = s.gallery_identities;
  } catch { /* noop */ }
}

/* ═══════════════════════ upload / analyze ═══════════════════════ */

const dz = $("#dropzone");
dz.addEventListener("click", () => $("#file-input").click());
dz.addEventListener("dragover", ev => { ev.preventDefault(); dz.classList.add("drag"); });
dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
dz.addEventListener("drop", ev => {
  ev.preventDefault(); dz.classList.remove("drag");
  const f = [...ev.dataTransfer.files].find(f => f.type.startsWith("image/"));
  if (f) setQueryFile(f);
});
$("#file-input").addEventListener("change", ev => {
  if (ev.target.files[0]) setQueryFile(ev.target.files[0]);
  ev.target.value = "";
});
document.addEventListener("paste", ev => {
  if (S.view !== "search") return;
  const item = [...(ev.clipboardData?.items || [])].find(i => i.type.startsWith("image/"));
  if (item) setQueryFile(item.getAsFile());
});

async function setQueryFile(file) {
  if (!file) return;
  if (file.size > 15 * 1024 * 1024) { toast("Image larger than 15 MB", "err"); return; }
  S.queryFile = file;
  $("#no-face-note").hidden = true;
  $("#face-err-note").hidden = true;
  $("#dz-idle").hidden = true;
  $("#dz-preview").hidden = false;
  const url = URL.createObjectURL(file);
  $("#preview-img").src = url;
  $("#pm-faces").textContent = "analyzing…";
  $("#pm-quality").textContent = "";
  $("#pm-dims").textContent = "";
  $("#pm-file").textContent = file.name || "pasted image";

  try {
    const fd = new FormData();
    fd.append("file", file, file.name || "query.jpg");
    const a = await api("/api/analyze", { method: "POST", body: fd });
    S.analyze = a;
    if (a.thumb) $("#preview-img").src = a.thumb; // annotated
    const fb = $("#pm-faces");
    fb.textContent = a.face_count === 0 ? "no face found" :
      a.face_count === 1 ? "1 face detected" : `${a.face_count} faces detected`;
    fb.className = "pm-badge" + (a.face_count === 0 ? " zero" : a.face_count > 1 ? " multi" : "");
    $("#pm-quality").textContent = `quality ${Math.round(a.quality * 100)}%`;
    $("#pm-dims").textContent = `${a.width}×${a.height}px`;
    $("#no-face-note").hidden = a.face_count > 0;
  } catch (e) {
    $("#pm-faces").textContent = "analysis failed";
    $("#pm-faces").className = "pm-badge zero";
    toast("Analyze failed: " + e.message, "err");
  }
}

$("#btn-clear").addEventListener("click", ev => {
  ev.stopPropagation();
  S.queryFile = null; S.analyze = null;
  $("#dz-preview").hidden = true;
  $("#dz-idle").hidden = false;
  $("#no-face-note").hidden = true;
});

$("#btn-search").addEventListener("click", async ev => {
  ev.stopPropagation();
  if (!S.queryFile) return;
  const engines = [...S.enginesSel];
  if (!engines.length && !$("#opt-gallery").checked) {
    toast("Select at least one engine or enable gallery matching", "err");
    return;
  }
  const btn = $("#btn-search");
  btn.disabled = true;
  try {
    const fd = new FormData();
    fd.append("file", S.queryFile, S.queryFile.name || "query.jpg");
    fd.append("options", JSON.stringify({
      engines,
      include_gallery: $("#opt-gallery").checked,
    }));
    const res = await api("/api/jobs", { method: "POST", body: fd });
    navigate("job", res.job_id);
  } catch (e) {
    toast("Search failed: " + e.message, "err");
  } finally {
    btn.disabled = false;
  }
});

$("#btn-demo").addEventListener("click", async ev => {
  ev.stopPropagation();
  const btn = ev.currentTarget;
  btn.disabled = true;
  try {
    const res = await api("/api/demo", { method: "POST" });
    toast("Demo search started — synthetic faces, seeded gallery", "ok");
    navigate("job", res.job_id);
  } catch (e) {
    toast("Demo failed: " + e.message, "err");
  } finally { btn.disabled = false; }
});

/* ═══════════════════════ job view ═══════════════════════ */

async function loadJob(jobId) {
  teardownSSE();
  stopJobPolling();
  S.job = null; S.jobResults = [];
  S.engineStatus = {};
  renderEngineStatusGrid();
  $("#pipeline-log").innerHTML = "";
  $("#results-grid").innerHTML = "";
  $("#results-empty").hidden = false;
  $("#results-empty-text").textContent = "Waiting for pipeline…";
  $("#btn-cancel-job").hidden = false;
  setPhase(null);

  try {
    S.job = await api(`/api/jobs/${jobId}`);
  } catch (e) {
    toast("Job not found", "err");
    navigate("history");
    return;
  }
  renderJobHead();
  $("#btn-cancel-job").textContent = S.job.live ? "Cancel" : "Delete";

  if (S.job.live) {
    subscribeJob(jobId);
  } else {
    // finished job: render from stored stats
    const stats = S.job.stats || {};
    for (const [k, v] of Object.entries(stats.engines || {})) {
      S.engineStatus[k] = v;
    }
    renderEngineStatusGrid();
    Object.keys(stats).length && applyStats(stats);
    setPhase("done");
    S.jobResults = S.job.results || [];
    renderResults();
  }
}

function renderJobHead() {
  const j = S.job;
  $("#job-query-thumb").src = j.query_thumb ? `/media/${j.query_thumb}` : "";
  $("#job-title").textContent = j.options?.demo ? "Demo search" : `Search ${j.id}`;
  $("#job-when").textContent = fmtTime(j.created_at);
  $("#job-backend").textContent = j.face_backend ? `backend: ${j.face_backend}` : "backend: none";
  $("#job-faces").textContent = `${j.face_count} face(s) · quality ${Math.round((j.quality || 0) * 100)}%`;
}

function teardownSSE() {
  if (S.es) { S.es.close(); S.es = null; }
}

function subscribeJob(jobId) {
  teardownSSE();
  const es = new EventSource(`/api/jobs/${jobId}/events`);
  S.es = es;
  es.onmessage = ev => {
    let m; try { m = JSON.parse(ev.data); } catch { return; }
    handleJobEvent(m);
  };
  es.onerror = () => {
    // If the stream drops mid-job (proxy timeout etc.), fall back to polling.
    if (!S.es || S.es !== es) return;
    teardownSSE();
    if (S.job && S.job.live) startJobPolling(jobId);
  };
}

let pollTimer = null;
function startJobPolling(jobId) {
  stopJobPolling();
  pollTimer = setInterval(async () => {
    try {
      const j = await api(`/api/jobs/${jobId}`);
      S.job = j;
      renderJobHead();
      const stats = j.stats || {};
      for (const [k, v] of Object.entries(stats.engines || {})) S.engineStatus[k] = v;
      renderEngineStatusGrid();
      if (!j.live) {
        stopJobPolling();
        setPhase("done");
        S.jobResults = j.results || [];
        renderResults();
        loadStats();
      }
    } catch { /* transient */ }
  }, 2500);
}

function stopJobPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function handleJobEvent(m) {
  const d = m.data || {};
  switch (m.type) {
    case "phase": {
      if (d.phase) setPhase(d.phase, d.status);
      if (d.phase === "engines" && d.status === "done") applyStats({ engines: d.engines, candidates_found: d.found });
      if (d.phase === "download" && d.status === "start") applyStats({ urls: d.count });
      if (d.phase === "verify" && d.status === "done") applyStats({ verified: d.count });
      if (d.phase === "gallery" && d.status === "done") applyStats({ gallery: d.count });
      break;
    }
    case "engine": {
      S.engineStatus[d.engine] = d;
      renderEngineStatusGrid();
      if (d.reason) appendLog(`[${d.engine}] ${d.status}: ${d.reason}`);
      break;
    }
    case "engine_log":
      appendLog(`[${d.engine}] ${JSON.stringify(d)}`);
      break;
    case "progress": {
      applyStats({ [d.stage]: `${d.done}/${d.total}` });
      break;
    }
    case "summary":
      applyStats(d);
      break;
    case "done": {
      teardownSSE();
      stopJobPolling();
      $("#btn-cancel-job").hidden = true;
      setPhase("done");
      refreshJobResults(m.data?.status === "done");
      break;
    }
    case "error": {
      teardownSSE();
      stopJobPolling();
      $("#btn-cancel-job").hidden = true;
      toast("Job error: " + (d.message || "unknown"), "err");
      refreshJobResults(false);
      break;
    }
  }
}

let statsState = {};
function applyStats(patch) {
  statsState = { ...statsState, ...patch };
  const c = $("#pipeline-counters");
  const s = statsState;
  const bits = [];
  if (s.candidates_found !== undefined) bits.push(`<span class="counter">found <b>${s.candidates_found}</b></span>`);
  if (s.urls !== undefined) bits.push(`<span class="counter">urls <b>${s.urls}</b></span>`);
  if (typeof s.download === "string") bits.push(`<span class="counter">download <b>${s.download}</b></span>`);
  if (typeof s.verify === "string") bits.push(`<span class="counter">verify <b>${s.verify}</b></span>`);
  if (s.downloaded !== undefined) bits.push(`<span class="counter">downloaded <b>${s.downloaded}</b></span>`);
  if (s.verified !== undefined) bits.push(`<span class="counter">verified <b>${s.verified}</b></span>`);
  if (s.gallery_matches !== undefined) bits.push(`<span class="counter">gallery <b>${s.gallery_matches}</b></span>`);
  if (s.duration_s !== undefined) bits.push(`<span class="counter">⏱ ${s.duration_s}s</span>`);
  c.innerHTML = bits.join("");
}

function setPhase(activePhase, status) {
  $$("#phase-track .phase").forEach(p => {
    const name = p.dataset.phase;
    p.classList.remove("active");
    if (activePhase === "done") { p.classList.add("done"); return; }
    p.classList.remove("done");
    if (name === activePhase) p.classList.add("active");
  });
  if (activePhase && status === "done" && activePhase !== "rank") {
    const el = $(`#phase-track .phase[data-phase="${activePhase}"]`);
    if (el) { el.classList.remove("active"); el.classList.add("done"); }
  }
}

function renderEngineStatusGrid() {
  const grid = $("#engine-status-grid");
  const engines = S.system?.engines || [];
  const entries = Object.entries(S.engineStatus);
  if (!entries.length && !engines.length) { grid.innerHTML = ""; return; }
  const known = new Set(engines.map(e => e.key));
  const rows = [];
  for (const e of engines) {
    const st = S.engineStatus[e.key];
    rows.push({ key: e.key, label: e.label, ...(st || { status: "pending" }) });
  }
  for (const [k, v] of entries) if (!known.has(k)) rows.push({ key: k, label: k, ...v });
  grid.innerHTML = rows.map(r => {
    let info = "";
    if (r.status === "done") info = `${r.count} hits · ${((r.ms || 0) / 1000).toFixed(1)}s`;
    else if (r.status === "error" || r.status === "unavailable") info = (r.reason || "").slice(0, 42);
    return `<div class="est ${r.status}" title="${esc(r.reason || r.status)}">
      <span class="est-dot"></span>
      <span class="est-name">${esc(r.label)}</span>
      <span class="est-info ${r.status === "error" || r.status === "unavailable" ? "err" : ""}">${esc(info || r.status)}</span>
    </div>`;
  }).join("");
}

function appendLog(line) {
  const el = $("#pipeline-log");
  el.hidden = false;
  el.textContent += line + "\n";
  el.scrollTop = el.scrollHeight;
}

async function refreshJobResults(ok = true) {
  try {
    S.job = await api(`/api/jobs/${S.job.id}`);
    S.jobResults = S.job.results || [];
    renderResults();
    loadStats();
  } catch (e) {
    toast("Failed to load results: " + e.message, "err");
  }
  if (ok && S.jobResults.length) toast(`Search complete — ${S.jobResults.length} results`, "ok");
}

$("#btn-new-search").addEventListener("click", () => navigate("search"));
$("#btn-cancel-job").addEventListener("click", async () => {
  if (!S.job) return;
  try { await api(`/api/jobs/${S.job.id}`, { method: "DELETE" }); toast("Job cancelled"); } catch (e) { toast(e.message, "err"); }
});

/* export menu */
$("#btn-export").addEventListener("click", ev => {
  ev.stopPropagation();
  $("#export-drop").hidden = !$("#export-drop").hidden;
});
document.addEventListener("click", () => { $("#export-drop").hidden = true; });
$$("#export-drop a").forEach(a => a.addEventListener("click", () => {
  if (S.job) window.location = `/api/jobs/${S.job.id}/export?fmt=${a.dataset.fmt}`;
}));

/* ═══════════════════════ results rendering ═══════════════════════ */

$$("#verdict-filter .seg-btn").forEach(b => b.addEventListener("click", () => {
  $$("#verdict-filter .seg-btn").forEach(x => x.classList.remove("active"));
  b.classList.add("active");
  S.filters.verdict = b.dataset.v;
  renderResults();
}));
$("#minconf").addEventListener("input", ev => {
  S.filters.minConf = +ev.target.value;
  $("#minconf-val").textContent = ev.target.value;
  renderResults();
});
$("#sort-select").addEventListener("change", ev => {
  S.filters.sort = ev.target.value;
  renderResults();
});

const VERDICT_COLORS = { strong: "var(--good)", possible: "var(--possible)", weak: "#aab6c8", none: "#5c6779", unknown: "#5c6779" };

function visibleResults() {
  let rows = [...S.jobResults];
  if (S.filters.verdict === "strong") rows = rows.filter(r => r.verdict === "strong");
  if (S.filters.verdict === "possible") rows = rows.filter(r => r.verdict === "possible" || r.verdict === "strong");
  if (S.filters.verdict === "faces") rows = rows.filter(r => r.face_count > 0);
  rows = rows.filter(r => (r.confidence || 0) >= S.filters.minConf);
  const sorters = {
    rank: (a, b) => (b.rank_score ?? 0) - (a.rank_score ?? 0),
    similarity: (a, b) => (b.similarity ?? -1) - (a.similarity ?? -1),
    engines: (a, b) => b.engines.length - a.engines.length,
    domain: (a, b) => (a.domain || "").localeCompare(b.domain || ""),
  };
  rows.sort(sorters[S.filters.sort] || sorters.rank);
  return rows;
}

function renderResults() {
  const grid = $("#results-grid");
  const rows = visibleResults();
  const all = S.jobResults;
  $("#cnt-all").textContent = all.length;
  $("#cnt-strong").textContent = all.filter(r => r.verdict === "strong").length;
  $("#cnt-possible").textContent = all.filter(r => r.verdict === "possible" || r.verdict === "strong").length;
  $("#cnt-faces").textContent = all.filter(r => r.face_count > 0).length;

  grid.innerHTML = "";
  if (!rows.length) {
    $("#results-empty").hidden = false;
    $("#results-empty-text").textContent = all.length
      ? "No results match the current filters."
      : (S.job?.live ? "Pipeline running…" : "No results for this search.");
    return;
  }
  $("#results-empty").hidden = true;

  for (const r of rows) {
    const card = document.createElement("div");
    card.className = "rcard";
    const conf = Math.round(r.confidence || 0);
    const color = VERDICT_COLORS[r.verdict] || "var(--txt-faint)";
    const thumb = r.thumb_url_media || r.image_url_media || "";
    const isGal = (r.engines || []).includes("gallery");
    card.innerHTML = `
      <div class="rthumb">
        ${thumb ? `<img loading="lazy" src="${esc(thumb)}" alt="">` : `<div class="noface">NO IMAGE</div>`}
        ${r.is_query_dup ? `<span class="dup-flag" title="Near-duplicate of the query image itself">DUP</span>` : ""}
      </div>
      <div class="rconfbar"><div style="width:${conf}%;background:${color}"></div></div>
      <div class="rbody">
        <div class="rrow">
          <span class="rbadge ${esc(r.verdict)}">${esc(r.verdict)}</span>
          <span class="rscore">${r.similarity === null || r.similarity === undefined ? "—" : (r.similarity * 100).toFixed(1) + "%"} <small>cos</small></span>
        </div>
        <div class="rtitle" title="${esc(r.title || r.url)}">${esc(r.title || r.domain || r.url)}</div>
        <div class="rdomain">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20"/></svg>
          <span class="dom" title="${esc(r.source_url || r.url)}">${esc(r.domain || "—")}</span>
          <span style="margin-left:auto;color:var(--txt-faint)">${r.face_count ? r.face_count + " face" : ""}</span>
        </div>
        <div class="rengines">${(r.engines || []).map(e => `<span class="reng ${e === "gallery" ? "gallery" : ""}">${esc(e)}</span>`).join("")}</div>
      </div>`;
    card.addEventListener("click", () => openCompare(r));
    grid.appendChild(card);
  }
}

/* ═══════════════════════ compare modal ═══════════════════════ */

function openCompare(r) {
  S.compareResult = r;
  const j = S.job;
  $("#cmp-query").src = j?.query_thumb ? `/media/${j.query_thumb}` : "";
  const cand = r.image_url_media || r.thumb_url_media || "";
  $("#cmp-candidate").src = cand;
  $("#cmp-candidate-cap").textContent = r.domain || "candidate";
  const conf = r.confidence || 0;
  $("#cmp-score").textContent = r.similarity === null || r.similarity === undefined ? "—" : (r.similarity * 100).toFixed(1) + "%";
  const v = $("#cmp-verdict");
  v.textContent = r.verdict;
  v.style.cssText = `background:color-mix(in srgb, ${VERDICT_COLORS[r.verdict]} 15%, transparent);color:${VERDICT_COLORS[r.verdict]}`;
  $("#cmp-cos").textContent = r.similarity !== null && r.similarity !== undefined ? `cosine ${r.similarity.toFixed(4)}` : "no face comparison";
  $("#cmp-consensus").textContent = `confidence ${conf}% · ${r.face_count} face(s)`;
  $("#cmp-source").textContent = r.source_url || r.url || "";
  $("#cmp-open").style.display = (r.source_url || r.url || "").startsWith("http") ? "" : "none";
  $("#compare-modal").hidden = false;
}

$("#compare-close").addEventListener("click", closeCompare);
$("#compare-modal").addEventListener("click", ev => { if (ev.target.id === "compare-modal") closeCompare(); });
document.addEventListener("keydown", ev => { if (ev.key === "Escape") closeCompare(); });
function closeCompare() { $("#compare-modal").hidden = true; S.compareResult = null; }

$("#cmp-open").addEventListener("click", () => {
  const r = S.compareResult;
  if (r) window.open(r.source_url || r.url, "_blank", "noopener");
});
$("#cmp-fb-good").addEventListener("click", () => sendFeedback(true));
$("#cmp-fb-bad").addEventListener("click", () => sendFeedback(false));
async function sendFeedback(isCorrect) {
  const r = S.compareResult;
  if (!r || !S.job) return;
  try {
    const fd = new FormData();
    fd.append("job_id", S.job.id);
    fd.append("result_url", r.url);
    fd.append("is_correct", isCorrect);
    await api("/api/feedback", { method: "POST", body: fd });
    toast("Feedback recorded — thank you", "ok");
    closeCompare();
  } catch (e) { toast(e.message, "err"); }
}

/* ═══════════════════════ gallery ═══════════════════════ */

async function loadGallery() {
  const grid = $("#gallery-grid");
  grid.innerHTML = `<div class="skeleton-row"></div>`.repeat(3);
  let data;
  try { data = await api("/api/gallery"); } catch (e) { toast(e.message, "err"); return; }
  grid.innerHTML = "";
  if (!data.gallery.length) {
    grid.innerHTML = `<div class="panel" style="grid-column:1/-1;text-align:center;color:var(--txt-faint);padding:40px">
      Gallery is empty. Create an identity and add reference photos — every search will
      compare the query face against them.</div>`;
    return;
  }
  for (const g of data.gallery) {
    const card = document.createElement("div");
    card.className = "gcard";
    card.innerHTML = `
      <div class="gcard-head">
        <div><h3>${esc(g.name)}</h3><span class="gdate">${g.images.length} image(s) · added ${fmtTime(g.created_at)}</span></div>
        <button class="gdel" title="Delete identity">🗑</button>
      </div>
      <div class="gthumbs"></div>`;
    const thumbs = $(".gthumbs", card);
    for (const img of g.images) {
      const t = document.createElement("div");
      t.className = "gthumb";
      t.innerHTML = `<img loading="lazy" src="${esc(img.thumb || "")}" alt=""><button class="gx" title="Remove image">✕</button>`;
      $(".gx", t).addEventListener("click", async ev => {
        ev.stopPropagation();
        try { await api(`/api/gallery/images/${img.id}`, { method: "DELETE" }); loadGallery(); loadStats(); }
        catch (e) { toast(e.message, "err"); }
      });
      thumbs.appendChild(t);
    }
    const add = document.createElement("button");
    add.className = "gadd"; add.textContent = "+"; add.title = "Add reference photo";
    add.addEventListener("click", ev => { ev.stopPropagation(); pickGalleryImage(g.id); });
    thumbs.appendChild(add);
    $(".gdel", card).addEventListener("click", async ev => {
      ev.stopPropagation();
      if (!confirm(`Delete identity "${g.name}" and its images?`)) return;
      try { await api(`/api/gallery/${g.id}`, { method: "DELETE" }); loadGallery(); loadStats(); }
      catch (e) { toast(e.message, "err"); }
    });
    grid.appendChild(card);
  }
}

let galleryPicker = null;
function pickGalleryImage(galleryId) {
  if (galleryPicker) galleryPicker.remove();
  const inp = document.createElement("input");
  inp.type = "file"; inp.accept = "image/*"; inp.hidden = true;
  document.body.appendChild(inp);
  galleryPicker = inp;
  inp.addEventListener("change", async () => {
    const f = inp.files[0];
    inp.remove(); galleryPicker = null;
    if (!f) return;
    toast("Adding image…");
    try {
      const fd = new FormData();
      fd.append("file", f, f.name);
      const res = await api(`/api/gallery/${galleryId}/images`, { method: "POST", body: fd });
      if (!res.face_found) toast("Image added, but no face was detected in it", "");
      else toast("Image added", "ok");
      loadGallery();
    } catch (e) { toast(e.message, "err"); }
  });
  inp.click();
}

$("#btn-add-identity").addEventListener("click", async () => {
  const name = prompt("Identity name (e.g. 'Subject A — confirmed')");
  if (!name) return;
  try {
    const fd = new FormData();
    fd.append("name", name);
    const g = await api("/api/gallery", { method: "POST", body: fd });
    toast(`Identity "${g.name}" created — now add reference photos`, "ok");
    loadGallery();
    loadStats();
    pickGalleryImage(g.id);
  } catch (e) { toast(e.message, "err"); }
});

/* ═══════════════════════ verify 1:1 ═══════════════════════ */

function setupVerifyDrop(el, key) {
  const input = $("input", el);
  el.addEventListener("click", () => input.click());
  el.addEventListener("dragover", ev => { ev.preventDefault(); el.classList.add("drag"); });
  el.addEventListener("dragleave", () => el.classList.remove("drag"));
  el.addEventListener("drop", ev => {
    ev.preventDefault(); el.classList.remove("drag");
    const f = [...ev.dataTransfer.files].find(f => f.type.startsWith("image/"));
    if (f) setVerifyImage(el, key, f);
  });
  input.addEventListener("change", ev => {
    if (ev.target.files[0]) setVerifyImage(el, key, ev.target.files[0]);
    ev.target.value = "";
  });
}

async function setVerifyImage(el, key, file) {
  S.verify[key] = file;
  const img = $("img", el);
  img.hidden = false;
  $(".vd-idle", el).style.display = "none";
  img.src = URL.createObjectURL(file);
  const tag = $(".vd-tag", el);
  tag.hidden = true;
  tag.textContent = "";
  updateVerifyBtn();
}

function updateVerifyBtn() { $("#btn-verify").disabled = !(S.verify.a && S.verify.b); }

function resetVerifyUI() {
  S.verify = { a: null, b: null };
  for (const [elId] of [["vd-a"], ["vd-b"]]) {
    const el = $(`#${elId}`);
    $("img", el).hidden = true;
    $(".vd-idle", el).style.display = "";
    $(".vd-tag", el).hidden = true;
  }
  $("#verify-score").textContent = "–";
  $("#verify-verdict").textContent = "";
  $("#verify-ring-fg").style.strokeDashoffset = 326.7;
  $("#verify-ring-fg").style.stroke = "var(--accent)";
  updateVerifyBtn();
}

setupVerifyDrop($("#vd-a"), "a");
setupVerifyDrop($("#vd-b"), "b");
$("#btn-verify-clear").addEventListener("click", resetVerifyUI);

$("#btn-verify").addEventListener("click", async () => {
  const { a, b } = S.verify;
  if (!a || !b) return;
  const btn = $("#btn-verify");
  btn.disabled = true;
  $("#verify-verdict").textContent = "…";
  try {
    const fd = new FormData();
    fd.append("file1", a, a.name || "a.jpg");
    fd.append("file2", b, b.name || "b.jpg");
    const res = await api("/api/verify", { method: "POST", body: fd });
    for (const [elId, key] of [["vd-a", "image1"], ["vd-b", "image2"]]) {
      const el = $(`#${elId}`);
      const info = res[key] || {};
      if (info.thumb) $("img", el).src = info.thumb;
      const tag = $(".vd-tag", el);
      tag.hidden = false;
      tag.textContent = info.face_found ? `face · q${Math.round(info.quality * 100)}%` : "no face";
    }
    const sim = res.similarity;
    const conf = res.confidence || 0;
    $("#verify-score").textContent = sim === null || sim === undefined ? "—" : (sim * 100).toFixed(1) + "%";
    $("#verify-verdict").textContent = res.verdict;
    const ring = $("#verify-ring-fg");
    ring.style.strokeDashoffset = 326.7 * (1 - conf / 100);
    ring.style.stroke = VERDICT_COLORS[res.verdict] || "var(--accent)";
  } catch (e) {
    toast(e.message, "err");
    $("#verify-verdict").textContent = "";
  } finally { btn.disabled = false; updateVerifyBtn(); }
});

/* ═══════════════════════ history ═══════════════════════ */

async function loadHistory() {
  const list = $("#history-list");
  list.innerHTML = `<div class="skeleton-row"></div>`.repeat(3);
  let data;
  try { data = await api("/api/jobs?limit=100"); } catch (e) { toast(e.message, "err"); return; }
  list.innerHTML = "";
  if (!data.jobs.length) {
    list.innerHTML = `<div class="panel" style="text-align:center;color:var(--txt-faint);padding:40px">No searches yet.</div>`;
    return;
  }
  for (const j of data.jobs) {
    const st = j.stats || {};
    const row = document.createElement("div");
    row.className = "hrow";
    row.innerHTML = `
      <img src="${j.query_thumb ? `/media/${esc(j.query_thumb)}` : ""}" alt="">
      <div class="hmain">
        <div class="htitle">${j.options?.demo ? "Demo search" : "Face search"} · ${esc(j.query_hash.slice(0, 12))}…</div>
        <div class="hsub">${esc(fmtTime(j.created_at))} · ${j.face_backend || "n/a"}</div>
      </div>
      <div class="hstats">
        <span><b>${j.result_count}</b> results</span>
        <span><b>${st.strong || 0}</b> strong</span>
        <span><b>${st.possible || 0}</b> possible</span>
        <span><b>${st.duration_s || "–"}</b> s</span>
      </div>
      <span class="hstatus ${esc(j.status)}">${esc(j.status)}</span>
      <button class="hdel" title="Delete">🗑</button>`;
    row.addEventListener("click", () => navigate("job", j.id));
    $(".hdel", row).addEventListener("click", async ev => {
      ev.stopPropagation();
      if (!confirm("Delete this search and its results?")) return;
      try { await api(`/api/jobs/${j.id}`, { method: "DELETE" }); loadHistory(); loadStats(); }
      catch (e) { toast(e.message, "err"); }
    });
    list.appendChild(row);
  }
}
$("#btn-refresh-history").addEventListener("click", loadHistory);

/* ═══════════════════════ system view ═══════════════════════ */

async function loadSystem() {
  const grid = $("#system-grid");
  grid.innerHTML = "";
  await loadSystemInfo();
  const sys = S.system;
  if (!sys) return;

  const sec = (title, rows) => `
    <div class="sys-section"><h3>${title}</h3>
      ${rows.map(([k, v, cls]) => `<div class="kv"><span class="k">${k}</span><span class="v ${cls || ""}">${v}</span></div>`).join("")}
    </div>`;

  const face = sys.face;
  const models = Object.entries(sys.models).map(([name, m]) =>
    [m.label, m.present ? `${(m.size / 1e6).toFixed(1)} MB` : "missing", m.present ? "ok" : "bad"]);

  const engines = sys.engines.map(e => [
    e.label,
    e.available ? "reachable" : (e.reason || "unavailable").slice(0, 46),
    e.available ? "ok" : "bad",
  ]);

  const verdicts = [
    ["strong (likely same person)", `cos ≥ ${sys.verdict_bands.strong}`, "ok"],
    ["possible", `cos ≥ ${sys.verdict_bands.possible}`, "warn"],
    ["weak", `cos ≥ ${sys.verdict_bands.weak}`, ""],
    ["none", "below weak", ""],
  ];

  const storage = sys.storage;
  const total = storage.uploads_bytes + storage.candidates_bytes + storage.gallery_bytes;
  const limits = [
    ["max upload", `${sys.limits.max_upload_mb} MB`],
    ["max candidates / search", sys.limits.max_candidates],
    ["results / engine", sys.limits.results_per_engine],
    ["download concurrency", sys.limits.download_concurrency],
  ];

  grid.innerHTML =
    sec("Face recognition", [
      ["active backend", face.active_backend, face.available ? "ok" : "bad"],
      ["embedding dimension", face.dim || "—"],
      ["backend order", esc(face.configured_order.join(" → "))],
      ...(face.error ? [["error", esc(face.error.slice(0, 80)), "bad"]] : []),
    ]) +
    sec("Models", models) +
    sec("Verdict thresholds", verdicts) +
    sec("Engines", engines) +
    sec("Limits", limits) +
    sec("Storage", [
      ["uploads", fmtBytes(storage.uploads_bytes)],
      ["candidates", fmtBytes(storage.candidates_bytes)],
      ["gallery", fmtBytes(storage.gallery_bytes)],
      ["total (quota " + storage.quota_gb + " GB)", fmtBytes(total)],
    ]) +
    `<div class="sys-section sys-power">
       <h3>Power</h3>
       <p class="sys-note">Stops the background server. Restart by double-clicking
       the desktop icon again (or running <code>python run.py</code>).</p>
       <button class="btn btn-danger" id="btn-shutdown">
         <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.8 0"/></svg>
         Shut down server
       </button>
     </div>`;

  $("#btn-shutdown").addEventListener("click", async () => {
    if (!confirm("Shut down the server? Any running searches will be stopped.")) return;
    try {
      await api("/api/system/shutdown", { method: "POST" });
      showStoppedOverlay();
    } catch (e) {
      toast(e.message, "err");
    }
  });
}

function showStoppedOverlay() {
  let el = $("#stopped-overlay");
  if (!el) {
    el = document.createElement("div");
    el.id = "stopped-overlay";
    el.className = "stopped-overlay";
    el.innerHTML = `
      <div class="stopped-card">
        <div class="stopped-icon">⏻</div>
        <h2>Server stopped</h2>
        <p>Start it again by double-clicking your desktop icon.</p>
      </div>`;
    document.body.appendChild(el);
  }
  el.hidden = false;
}

$("#btn-sys-refresh").addEventListener("click", loadSystem);

/* ═══════════════════════ boot ═══════════════════════ */

(async function boot() {
  await loadSystemInfo();
  loadStats();
  setInterval(() => { if (S.view === "search") loadStats(); }, 20000);
})();
