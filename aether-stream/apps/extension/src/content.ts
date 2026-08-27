import { scanVisibleMedia, type MediaCandidate } from "./shared";

type ScanRequest = { type: "scan" };

let lastFingerprint = "";
let scanTimer: number | undefined;

function fingerprint(candidates: MediaCandidate[]) {
  return candidates.map((candidate) => `${candidate.kind}:${candidate.url}`).sort().join("|");
}

function publishScan() {
  const candidates = scanVisibleMedia();
  const fingerprintValue = fingerprint(candidates);
  if (fingerprintValue === lastFingerprint) return;
  lastFingerprint = fingerprintValue;
  void chrome.runtime.sendMessage({
    type: "media-candidates",
    candidates,
    pageUrl: location.href,
  });
}

function scheduleScan() {
  window.clearTimeout(scanTimer);
  scanTimer = window.setTimeout(publishScan, 180);
}

const observer = new MutationObserver(scheduleScan);
observer.observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ["src", "href"] });
window.addEventListener("aether-stream-route-change", scheduleScan);
window.addEventListener("load", scheduleScan, { once: true });
scheduleScan();

chrome.runtime.onMessage.addListener((message: ScanRequest, _sender, sendResponse) => {
  if (message?.type !== "scan") return;
  const candidates = scanVisibleMedia();
  lastFingerprint = fingerprint(candidates);
  sendResponse({ candidates, pageUrl: location.href });
});

// Dispatch a semantic event after SPA navigation. We do not patch router
// internals; wrapping the platform history calls keeps this framework-neutral.
for (const method of ["pushState", "replaceState"] as const) {
  const original = history[method];
  history[method] = function (this: History, ...args: Parameters<History[typeof method]>) {
    const result = original.apply(this, args);
    window.dispatchEvent(new Event("aether-stream-route-change"));
    return result;
  } as History[typeof method];
}
window.addEventListener("popstate", scheduleScan);
