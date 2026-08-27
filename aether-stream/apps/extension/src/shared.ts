export type MediaKind = "direct" | "hls" | "dash" | "blob";

export type MediaCandidate = {
  url: string;
  kind: MediaKind;
  mimeType?: string;
  title?: string;
  pageUrl: string;
};

const HLS = /\.m3u8(?:$|[?#])/i;
const DASH = /\.mpd(?:$|[?#])/i;
const MEDIA_EXTENSIONS = /\.(?:mp4|webm|mov|m4v|mp3|m4a|wav|ogg|flac)(?:$|[?#])/i;

export function classifyMedia(url: string, mimeType = ""): MediaKind | null {
  if (url.startsWith("blob:")) return "blob";
  if (HLS.test(url) || /application\/(?:vnd\.apple\.mpegurl|x-mpegurl)/i.test(mimeType)) return "hls";
  if (DASH.test(url) || /application\/dash\+xml/i.test(mimeType)) return "dash";
  if (MEDIA_EXTENSIONS.test(url) || /^video\//i.test(mimeType) || /^audio\//i.test(mimeType)) return "direct";
  return null;
}

export function normalizeCandidate(rawUrl: string, pageUrl: string, mimeType?: string): MediaCandidate | null {
  try {
    const url = new URL(rawUrl, pageUrl);
    if (url.protocol !== "https:" && url.protocol !== "http:" && url.protocol !== "blob:") return null;
    const kind = classifyMedia(url.href, mimeType);
    if (!kind) return null;
    return { url: url.href, kind, mimeType, pageUrl };
  } catch {
    return null;
  }
}

export function scanVisibleMedia(): MediaCandidate[] {
  const pageUrl = location.href;
  const candidates = new Map<string, MediaCandidate>();

  const add = (rawUrl: string | null | undefined, mimeType?: string, title?: string) => {
    const candidate = rawUrl && normalizeCandidate(rawUrl, pageUrl, mimeType);
    if (candidate && !candidates.has(candidate.url)) candidates.set(candidate.url, { ...candidate, title });
  };

  document.querySelectorAll<HTMLMediaElement>("video, audio").forEach((element) => {
    add(element.currentSrc || element.src, element.getAttribute("type") ?? undefined, document.title);
    element.querySelectorAll<HTMLSourceElement>("source").forEach((source) => add(source.src, source.type, document.title));
  });

  document.querySelectorAll<HTMLAnchorElement>("a[href]").forEach((anchor) => {
    add(anchor.href, anchor.getAttribute("type") ?? undefined, anchor.textContent?.trim() || document.title);
  });

  for (const entry of performance.getEntriesByType("resource")) {
    const resource = entry as PerformanceResourceTiming;
    add(resource.name);
  }

  return [...candidates.values()];
}
