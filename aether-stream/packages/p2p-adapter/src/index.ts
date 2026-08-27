import WebTorrent from "webtorrent";

export type AuthorizedTorrent = {
  magnetUri: string;
  /** The operator must explicitly attest that this content is authorized. */
  authorized: boolean;
};

export type TorrentProgress = {
  downloadedBytes: number;
  totalBytes: number;
  peers: number;
  speedBps: number;
  progress: number;
};

export function isEligibleTorrent(source: AuthorizedTorrent): boolean {
  return source.authorized && /^magnet:\?xt=urn:btih:/i.test(source.magnetUri);
}

/**
 * Optional P2P fallback. It is intentionally opt-in and accepts only a
 * user-provided magnet URI; it never discovers peers or torrents on its own.
 * The production Tauri adapter will stream completed pieces into the same
 * checksum/staging pipeline as HTTP segments.
 */
export function downloadAuthorizedTorrent(
  source: AuthorizedTorrent,
  onProgress: (progress: TorrentProgress) => void,
): Promise<void> {
  if (!isEligibleTorrent(source)) {
    return Promise.reject(new Error("P2P fallback requires an authorized magnet URI"));
  }

  const client = new WebTorrent({ dht: true });
  return new Promise((resolve, reject) => {
    client.add(source.magnetUri, (torrent) => {
      const report = () =>
        onProgress({
          downloadedBytes: torrent.downloaded,
          totalBytes: torrent.length,
          peers: torrent.numPeers,
          speedBps: torrent.downloadSpeed,
          progress: torrent.progress,
        });

      torrent.on("download", report);
      torrent.on("done", () => {
        report();
        client.destroy((error) => (error ? reject(error) : resolve()));
      });
      torrent.on("error", (error) => client.destroy(() => reject(error)));
    });
    client.on("error", (error) => client.destroy(() => reject(error)));
  });
}
