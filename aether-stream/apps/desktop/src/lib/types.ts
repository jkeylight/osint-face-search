export type DownloadStatus = "queued" | "downloading" | "paused" | "complete" | "failed";

export type ChunkState = "pending" | "active" | "complete" | "error";

export type ChunkSnapshot = {
  index: number;
  state: ChunkState;
  progress: number;
  throughputBps: number;
};

export type DownloadSnapshot = {
  id: string;
  name: string;
  source: string;
  destination: string;
  totalBytes: number;
  completedBytes: number;
  speedBps: number;
  etaSeconds: number | null;
  status: DownloadStatus;
  protocol: "HTTP/3" | "HTTP/2" | "HTTP/1.1";
  chunks: ChunkSnapshot[];
  encrypted: boolean;
};
