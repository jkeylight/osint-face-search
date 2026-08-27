import type { MediaCandidate } from "./shared";

const NATIVE_HOST = "com.aether.stream.bridge";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "aether-capture-media",
    title: "Send visible media to AETHER-STREAM",
    contexts: ["page", "video", "audio", "link"],
  });
});

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message?.type !== "media-candidates" || !sender.tab?.id) return;
  void chrome.storage.session.set({
    [String(sender.tab.id)]: {
      candidates: message.candidates as MediaCandidate[],
      pageUrl: message.pageUrl as string,
      updatedAt: Date.now(),
    },
  });
});

chrome.contextMenus.onClicked.addListener(async (_info, tab) => {
  const tabId = tab?.id;
  if (tabId === undefined) return;
  const response = await chrome.tabs.sendMessage(tabId, { type: "scan" }).catch(() => null) as
    | { candidates: MediaCandidate[]; pageUrl: string }
    | null;
  if (!response?.candidates?.length) return;

  // Explicit user action only. No candidate is sent to the native bridge just
  // because it appeared in the page.
  const envelope = {
    version: 1,
    nonce: crypto.randomUUID(),
    origin: new URL(response.pageUrl).origin,
    candidates: response.candidates,
  };
  chrome.runtime.sendNativeMessage(NATIVE_HOST, { type: "capture-intent", envelope }, () => {
    // A missing native host is a normal state while the desktop app is closed;
    // the UI can surface this via chrome.runtime.lastError if desired.
    void chrome.runtime.lastError;
  });
});
