//! AETHER-STREAM's transport core.
//!
//! The engine is intentionally UI-agnostic. Tauri consumes `DownloadEvent`s,
//! while a future daemon or mobile shell can use the same `DownloadManager`.
//! The implementation below is a production-shaped skeleton: it has real
//! range validation, concurrent workers, cancellation, HTTP/3 preference with
//! protocol fallback, private staging, and atomic publication.

mod storage;

pub use storage::{QueueStore, StoreError};

use futures_util::StreamExt;
use reqwest::{
    header::{ACCEPT_RANGES, CONTENT_LENGTH, CONTENT_RANGE, ETAG, IF_RANGE, RANGE},
    Client, RequestBuilder, Response, StatusCode,
};
use serde::{Deserialize, Serialize};
use std::{
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc,
    },
    time::{Duration, Instant},
};
use thiserror::Error;
use tokio::{
    fs::{self, File},
    io::{self, AsyncWriteExt},
    sync::{broadcast, Semaphore},
    task::JoinSet,
};
use tokio_util::sync::CancellationToken;
use tracing::debug;
use url::Url;
use uuid::Uuid;

pub const MAX_CHUNKS: usize = 64;
const DEFAULT_MAX_PARALLEL: usize = 8;
const DEFAULT_MIN_CHUNK_SIZE: u64 = 4 * 1024 * 1024;
const DEFAULT_REQUEST_TIMEOUT: Duration = Duration::from_secs(45);

#[derive(Debug, Clone)]
pub struct DownloadConfig {
    /// Hard upper bound for a single file. The planner may choose fewer parts.
    pub max_chunks: usize,
    /// Number of ranged requests allowed to be in flight at once.
    pub max_parallel: usize,
    /// Small files are kept single-stream to avoid coordination overhead.
    pub min_chunk_size: u64,
    pub request_timeout: Duration,
}

impl Default for DownloadConfig {
    fn default() -> Self {
        Self {
            max_chunks: MAX_CHUNKS,
            max_parallel: DEFAULT_MAX_PARALLEL,
            min_chunk_size: DEFAULT_MIN_CHUNK_SIZE,
            request_timeout: DEFAULT_REQUEST_TIMEOUT,
        }
    }
}

impl DownloadConfig {
    fn normalized(self) -> Self {
        Self {
            max_chunks: self.max_chunks.clamp(1, MAX_CHUNKS),
            max_parallel: self.max_parallel.max(1),
            min_chunk_size: self.min_chunk_size.max(1),
            request_timeout: self.request_timeout.max(Duration::from_secs(1)),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DownloadSpec {
    pub id: Uuid,
    pub url: Url,
    pub destination: PathBuf,
}

impl DownloadSpec {
    pub fn new(url: Url, destination: impl Into<PathBuf>) -> Self {
        Self {
            id: Uuid::new_v4(),
            url,
            destination: destination.into(),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum DownloadEvent {
    State {
        id: Uuid,
        state: DownloadState,
    },
    Chunk {
        id: Uuid,
        chunk_index: usize,
        chunk_count: usize,
        state: DownloadState,
        completed_bytes: u64,
        expected_bytes: u64,
    },
    Progress {
        id: Uuid,
        completed_bytes: u64,
        total_bytes: Option<u64>,
        speed_bps: u64,
        active_chunks: usize,
        chunk_count: usize,
    },
    Finished {
        id: Uuid,
        bytes_written: u64,
        total_bytes: Option<u64>,
        chunk_count: usize,
        ranged: bool,
    },
    Failed {
        id: Uuid,
        message: String,
    },
}

#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DownloadState {
    Queued,
    Probing,
    Downloading,
    Assembling,
    Complete,
    Cancelled,
    Failed,
}

#[derive(Debug, Clone, Serialize)]
pub struct DownloadSummary {
    pub id: Uuid,
    pub bytes_written: u64,
    pub total_bytes: Option<u64>,
    pub chunk_count: usize,
    pub ranged: bool,
}

#[derive(Debug, Error)]
pub enum EngineError {
    #[error("HTTP request failed: {0}")]
    Http(#[from] reqwest::Error),
    #[error("HTTP/3 failed ({h3}); fallback transport failed ({fallback})")]
    HttpFallback { h3: String, fallback: String },
    #[error("origin returned HTTP {0}")]
    HttpStatus(StatusCode),
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error("download cancelled")]
    Cancelled,
    #[error("invalid destination: {0}")]
    InvalidDestination(String),
    #[error("origin does not expose a usable byte-range response")]
    RangeUnsupported,
    #[error("invalid range response: {0}")]
    InvalidRange(String),
    #[error("download worker failed: {0}")]
    Worker(String),
}

#[derive(Debug, Clone)]
struct RemoteInfo {
    total_bytes: Option<u64>,
    supports_ranges: bool,
    etag: Option<String>,
}

#[derive(Debug, Clone)]
struct ByteRange {
    index: usize,
    start: u64,
    end: u64,
}

impl ByteRange {
    fn len(&self) -> u64 {
        self.end - self.start + 1
    }
}

/// Concurrent, cancellable download coordinator.
///
/// `h3_client` is deliberately separate from `fallback_client`: reqwest's
/// HTTP/3 prior-knowledge mode is strict, so a normal client is needed when an
/// origin or intermediary does not advertise QUIC. Only transport failures
/// fall back; HTTP response statuses retain their original semantics.
#[derive(Clone)]
pub struct DownloadManager {
    h3_client: Client,
    fallback_client: Client,
    config: Arc<DownloadConfig>,
    events: broadcast::Sender<DownloadEvent>,
}

impl DownloadManager {
    pub fn new(config: DownloadConfig) -> Result<Self, EngineError> {
        let config = Arc::new(config.normalized());
        let user_agent = "AETHER-STREAM/0.1 (+local-first)";

        let fallback_client = Client::builder()
            .use_rustls_tls()
            .timeout(config.request_timeout)
            .user_agent(user_agent)
            .build()?;

        // `http3` is enabled in Cargo.toml and the workspace config opts into
        // reqwest's current `reqwest_unstable` gate. This client is strict by
        // design; `send_prefer_h3` retries transport errors with the normal
        // HTTP/2/HTTP/1.1-capable client.
        let h3_client = Client::builder()
            .use_rustls_tls()
            .http3_prior_knowledge()
            .timeout(config.request_timeout)
            .user_agent(user_agent)
            .build()?;

        let (events, _) = broadcast::channel(1024);
        Ok(Self {
            h3_client,
            fallback_client,
            config,
            events,
        })
    }

    pub fn subscribe(&self) -> broadcast::Receiver<DownloadEvent> {
        self.events.subscribe()
    }

    pub fn config(&self) -> &DownloadConfig {
        &self.config
    }

    pub async fn download(&self, spec: DownloadSpec) -> Result<DownloadSummary, EngineError> {
        self.download_with_cancel(spec, CancellationToken::new())
            .await
    }

    pub async fn download_with_cancel(
        &self,
        spec: DownloadSpec,
        cancel: CancellationToken,
    ) -> Result<DownloadSummary, EngineError> {
        validate_destination(&spec.destination)?;
        self.emit(DownloadEvent::State {
            id: spec.id,
            state: DownloadState::Probing,
        });

        let remote = match self.probe(&spec.url).await {
            Ok(remote) => remote,
            Err(error) => {
                self.emit(DownloadEvent::State {
                    id: spec.id,
                    state: DownloadState::Failed,
                });
                self.emit(DownloadEvent::Failed {
                    id: spec.id,
                    message: error.to_string(),
                });
                return Err(error);
            }
        };
        let ranged = remote.supports_ranges
            && remote
                .total_bytes
                .map(|size| size > 0)
                .unwrap_or(false);
        let ranges = if ranged {
            plan_ranges(remote.total_bytes.expect("ranged downloads have a size"), &self.config)
        } else {
            Vec::new()
        };

        if cancel.is_cancelled() {
            self.emit(DownloadEvent::State {
                id: spec.id,
                state: DownloadState::Cancelled,
            });
            return Err(EngineError::Cancelled);
        }

        self.emit(DownloadEvent::State {
            id: spec.id,
            state: DownloadState::Downloading,
        });

        if ranged {
            self.download_ranged(
                &spec,
                remote.total_bytes,
                remote.etag,
                ranges,
                cancel,
            )
            .await
        } else {
            self.download_single(&spec, remote.total_bytes, cancel)
                .await
        }
    }

    async fn probe(&self, url: &Url) -> Result<RemoteInfo, EngineError> {
        let head = self
            .send_prefer_h3(|client| client.head(url.clone()))
            .await?;
        let head_size = content_length(&head);
        let head_ranges = accepts_ranges(&head);
        let head_etag = header_string(&head, ETAG);

        if head.status().is_success() && head_size.is_some() && head_ranges {
            return Ok(RemoteInfo {
                total_bytes: head_size,
                supports_ranges: true,
                etag: head_etag,
            });
        }

        // Some origins omit Accept-Ranges but still support it. A one-byte
        // probe is cheap and gives us a trustworthy total from Content-Range.
        let probe = self
            .send_prefer_h3(|client| client.get(url.clone()).header(RANGE, "bytes=0-0"))
            .await?;
        match probe.status() {
            StatusCode::PARTIAL_CONTENT => Ok(RemoteInfo {
                total_bytes: parse_content_range_header(&probe)
                    .and_then(|(_, _, total)| total)
                    .or(head_size),
                supports_ranges: true,
                etag: header_string(&probe, ETAG).or(head_etag),
            }),
            status if status.is_success() => Ok(RemoteInfo {
                total_bytes: content_length(&probe).or(head_size),
                supports_ranges: false,
                etag: header_string(&probe, ETAG).or(head_etag),
            }),
            status => Err(EngineError::HttpStatus(status)),
        }
    }

    async fn download_ranged(
        &self,
        spec: &DownloadSpec,
        total_bytes: Option<u64>,
        etag: Option<String>,
        ranges: Vec<ByteRange>,
        cancel: CancellationToken,
    ) -> Result<DownloadSummary, EngineError> {
        let staging = staging_dir(&spec.destination, spec.id);
        fs::create_dir_all(&staging).await?;

        let aggregate = Arc::new(AtomicU64::new(0));
        let started = Instant::now();
        let permits = Arc::new(Semaphore::new(self.config.max_parallel.min(ranges.len())));
        let mut workers = JoinSet::new();

        for range in ranges.iter().cloned() {
            let permit = permits
                .clone()
                .acquire_owned()
                .await
                .map_err(|error| EngineError::Worker(error.to_string()))?;
            let manager = self.clone();
            let spec = spec.clone();
            let staging = staging.clone();
            let aggregate = aggregate.clone();
            let cancel = cancel.clone();
            let etag = etag.clone();
            let total_bytes = total_bytes;
            let started = started;
            let chunk_count = ranges.len();

            workers.spawn(async move {
                let _permit = permit;
                manager
                    .download_chunk(
                        &spec,
                        &staging,
                        range,
                        total_bytes,
                        etag,
                        aggregate,
                        started,
                        chunk_count,
                        cancel,
                    )
                    .await
            });
        }

        let mut failure = None;
        while let Some(result) = workers.join_next().await {
            match result {
                Ok(Ok(())) => {}
                Ok(Err(error)) => {
                    failure = Some(error);
                    workers.abort_all();
                    break;
                }
                Err(error) => {
                    failure = Some(EngineError::Worker(error.to_string()));
                    workers.abort_all();
                    break;
                }
            }
        }

        // Drain aborted tasks before returning so their file handles and
        // permits are definitely released. The staging directory is kept for
        // a future checkpoint/resume implementation.
        while workers.join_next().await.is_some() {}

        if let Some(error) = failure {
            let state = if matches!(&error, EngineError::Cancelled) {
                DownloadState::Cancelled
            } else {
                DownloadState::Failed
            };
            self.emit(DownloadEvent::State { id: spec.id, state });
            if !matches!(&error, EngineError::Cancelled) {
                self.emit(DownloadEvent::Failed {
                    id: spec.id,
                    message: error.to_string(),
                });
            }
            return Err(error);
        }

        if cancel.is_cancelled() {
            self.emit(DownloadEvent::State {
                id: spec.id,
                state: DownloadState::Cancelled,
            });
            return Err(EngineError::Cancelled);
        }

        self.emit(DownloadEvent::State {
            id: spec.id,
            state: DownloadState::Assembling,
        });

        let assembled = staging.join("assembled.part");
        let mut output = File::create(&assembled).await?;
        for range in &ranges {
            let mut input = File::open(staging.join(part_name(range.index))).await?;
            io::copy(&mut input, &mut output).await?;
        }
        output.flush().await?;
        output.sync_all().await?;
        publish_atomically(&assembled, &spec.destination).await?;
        fs::remove_dir_all(&staging).await?;

        let bytes_written = aggregate.load(Ordering::Relaxed);
        let summary = DownloadSummary {
            id: spec.id,
            bytes_written,
            total_bytes,
            chunk_count: ranges.len(),
            ranged: true,
        };
        self.emit(DownloadEvent::State {
            id: spec.id,
            state: DownloadState::Complete,
        });
        self.emit(DownloadEvent::Finished {
            id: summary.id,
            bytes_written: summary.bytes_written,
            total_bytes: summary.total_bytes,
            chunk_count: summary.chunk_count,
            ranged: summary.ranged,
        });
        Ok(summary)
    }

    #[allow(clippy::too_many_arguments)]
    async fn download_chunk(
        &self,
        spec: &DownloadSpec,
        staging: &Path,
        range: ByteRange,
        total_bytes: Option<u64>,
        etag: Option<String>,
        aggregate: Arc<AtomicU64>,
        started: Instant,
        chunk_count: usize,
        cancel: CancellationToken,
    ) -> Result<(), EngineError> {
        if cancel.is_cancelled() {
            return Err(EngineError::Cancelled);
        }

        self.emit(DownloadEvent::Chunk {
            id: spec.id,
            chunk_index: range.index,
            chunk_count,
            state: DownloadState::Downloading,
            completed_bytes: 0,
            expected_bytes: range.len(),
        });

        let header_value = format!("bytes={}-{}", range.start, range.end);
        let response = self
            .send_prefer_h3(|client| {
                let mut request = client
                    .get(spec.url.clone())
                    .header(RANGE, header_value.clone());
                if let Some(etag) = &etag {
                    request = request.header(IF_RANGE, etag);
                }
                request
            })
            .await?;

        if response.status() != StatusCode::PARTIAL_CONTENT {
            return Err(EngineError::InvalidRange(format!(
                "requested {}-{}, origin returned {}",
                range.start,
                range.end,
                response.status()
            )));
        }
        if let Some((start, end, _)) = parse_content_range_header(&response) {
            if start != range.start || end != range.end {
                return Err(EngineError::InvalidRange(format!(
                    "requested {}-{}, origin returned {}-{}",
                    range.start, range.end, start, end
                )));
            }
        }

        let mut stream = response.bytes_stream();
        let part_path = staging.join(part_name(range.index));
        let mut part = File::create(part_path).await?;
        let mut chunk_bytes = 0_u64;

        while let Some(next) = stream.next().await {
            if cancel.is_cancelled() {
                return Err(EngineError::Cancelled);
            }
            let bytes = next?;
            chunk_bytes += bytes.len() as u64;
            if chunk_bytes > range.len() {
                return Err(EngineError::InvalidRange(format!(
                    "chunk {} exceeded expected length {}",
                    range.index,
                    range.len()
                )));
            }
            part.write_all(&bytes).await?;
            let completed = aggregate.fetch_add(bytes.len() as u64, Ordering::Relaxed)
                + bytes.len() as u64;
            self.emit(DownloadEvent::Progress {
                id: spec.id,
                completed_bytes: completed,
                total_bytes,
                speed_bps: (completed as f64 / started.elapsed().as_secs_f64().max(0.001)) as u64,
                active_chunks: chunk_count,
                chunk_count,
            });
        }

        if chunk_bytes != range.len() {
            return Err(EngineError::InvalidRange(format!(
                "chunk {} ended at {} bytes, expected {}",
                range.index,
                chunk_bytes,
                range.len()
            )));
        }
        part.flush().await?;
        part.sync_all().await?;

        self.emit(DownloadEvent::Chunk {
            id: spec.id,
            chunk_index: range.index,
            chunk_count,
            state: DownloadState::Complete,
            completed_bytes: chunk_bytes,
            expected_bytes: range.len(),
        });
        Ok(())
    }

    async fn download_single(
        &self,
        spec: &DownloadSpec,
        total_bytes: Option<u64>,
        cancel: CancellationToken,
    ) -> Result<DownloadSummary, EngineError> {
        let staging = staging_dir(&spec.destination, spec.id);
        fs::create_dir_all(&staging).await?;
        let temporary = staging.join("single.part");
        let response = self
            .send_prefer_h3(|client| client.get(spec.url.clone()))
            .await?;
        if !response.status().is_success() {
            let status = response.status();
            self.emit(DownloadEvent::Failed {
                id: spec.id,
                message: format!("origin returned HTTP {status}"),
            });
            return Err(EngineError::HttpStatus(status));
        }

        let mut stream = response.bytes_stream();
        let mut output = File::create(&temporary).await?;
        let mut completed = 0_u64;
        let started = Instant::now();
        while let Some(next) = stream.next().await {
            if cancel.is_cancelled() {
                self.emit(DownloadEvent::State {
                    id: spec.id,
                    state: DownloadState::Cancelled,
                });
                return Err(EngineError::Cancelled);
            }
            let bytes = next?;
            output.write_all(&bytes).await?;
            completed += bytes.len() as u64;
            self.emit(DownloadEvent::Progress {
                id: spec.id,
                completed_bytes: completed,
                total_bytes,
                speed_bps: (completed as f64 / started.elapsed().as_secs_f64().max(0.001)) as u64,
                active_chunks: 1,
                chunk_count: 1,
            });
        }
        output.flush().await?;
        output.sync_all().await?;
        publish_atomically(&temporary, &spec.destination).await?;
        fs::remove_dir_all(&staging).await?;

        let summary = DownloadSummary {
            id: spec.id,
            bytes_written: completed,
            total_bytes: total_bytes.or(Some(completed)),
            chunk_count: 1,
            ranged: false,
        };
        self.emit(DownloadEvent::State {
            id: spec.id,
            state: DownloadState::Complete,
        });
        self.emit(DownloadEvent::Finished {
            id: summary.id,
            bytes_written: summary.bytes_written,
            total_bytes: summary.total_bytes,
            chunk_count: summary.chunk_count,
            ranged: summary.ranged,
        });
        Ok(summary)
    }

    async fn send_prefer_h3<F>(&self, make_request: F) -> Result<Response, EngineError>
    where
        F: Fn(&Client) -> RequestBuilder,
    {
        match make_request(&self.h3_client).send().await {
            Ok(response) => Ok(response),
            Err(h3_error) => {
                debug!(error = %h3_error, "HTTP/3 transport failed; trying negotiated transport");
                make_request(&self.fallback_client)
                    .send()
                    .await
                    .map_err(|fallback| EngineError::HttpFallback {
                        h3: h3_error.to_string(),
                        fallback: fallback.to_string(),
                    })
            }
        }
    }

    fn emit(&self, event: DownloadEvent) {
        // A UI may attach after a job starts. Events are advisory; durable
        // checkpoints belong in QueueStore and are deliberately not blocked by
        // a slow renderer.
        let _ = self.events.send(event);
    }
}

fn validate_destination(destination: &Path) -> Result<(), EngineError> {
    if destination.as_os_str().is_empty() {
        return Err(EngineError::InvalidDestination(
            "destination cannot be empty".into(),
        ));
    }
    if destination.file_name().is_none() {
        return Err(EngineError::InvalidDestination(format!(
            "destination must name a file: {}",
            destination.display()
        )));
    }
    Ok(())
}

fn staging_dir(destination: &Path, id: Uuid) -> PathBuf {
    destination
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .join(format!(".{}.aether-staging", id))
}

fn part_name(index: usize) -> String {
    format!("part-{index:02}.bin")
}

async fn publish_atomically(source: &Path, destination: &Path) -> Result<(), EngineError> {
    // The staging path is created beside the destination, so rename is atomic
    // on the same filesystem. POSIX rename replaces an existing file in one
    // operation. Windows requires a remove-then-rename fallback because its
    // replace semantics differ; the source is still complete and fsynced.
    #[cfg(not(windows))]
    {
        fs::rename(source, destination).await?;
    }
    #[cfg(windows)]
    {
        if fs::try_exists(destination).await? {
            fs::remove_file(destination).await?;
        }
        fs::rename(source, destination).await?;
    }
    Ok(())
}

fn content_length(response: &Response) -> Option<u64> {
    response
        .headers()
        .get(CONTENT_LENGTH)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.parse().ok())
}

fn accepts_ranges(response: &Response) -> bool {
    response
        .headers()
        .get(ACCEPT_RANGES)
        .and_then(|value| value.to_str().ok())
        .map(|value| value.split(',').any(|item| item.trim().eq_ignore_ascii_case("bytes")))
        .unwrap_or(false)
}

fn header_string(response: &Response, name: reqwest::header::HeaderName) -> Option<String> {
    response
        .headers()
        .get(name)
        .and_then(|value| value.to_str().ok())
        .map(ToOwned::to_owned)
}

fn parse_content_range_header(response: &Response) -> Option<(u64, u64, Option<u64>)> {
    let value = response
        .headers()
        .get(CONTENT_RANGE)?
        .to_str()
        .ok()?
        .trim();
    let value = value.strip_prefix("bytes ")?;
    let (range, total) = value.split_once('/')?;
    let (start, end) = range.split_once('-')?;
    Some((
        start.parse().ok()?,
        end.parse().ok()?,
        (total != "*").then(|| total.parse().ok()).flatten(),
    ))
}

/// Choose the number of segments from resource size, minimum useful part
/// size, and the configured cap. Every returned range is contiguous and covers
/// the resource exactly once.
fn plan_ranges(total_bytes: u64, config: &DownloadConfig) -> Vec<ByteRange> {
    if total_bytes == 0 {
        return Vec::new();
    }
    let config = (*config).clone().normalized();
    let by_size = total_bytes
        .saturating_add(config.min_chunk_size - 1)
        .checked_div(config.min_chunk_size)
        .unwrap_or(1) as usize;
    let count = by_size.clamp(1, config.max_chunks);
    let base = total_bytes / count as u64;
    let remainder = total_bytes % count as u64;

    let mut ranges = Vec::with_capacity(count);
    let mut start = 0_u64;
    for index in 0..count {
        let len = base + u64::from((index as u64) < remainder);
        let end = start + len - 1;
        ranges.push(ByteRange { index, start, end });
        start = end + 1;
    }
    ranges
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn planner_caps_at_64_and_covers_every_byte() {
        let config = DownloadConfig {
            max_chunks: 128,
            max_parallel: 8,
            min_chunk_size: 1,
            request_timeout: Duration::from_secs(5),
        };
        let ranges = plan_ranges(10_000, &config);
        assert_eq!(ranges.len(), MAX_CHUNKS);
        assert_eq!(ranges.first().unwrap().start, 0);
        assert_eq!(ranges.last().unwrap().end, 9_999);
        assert!(ranges.windows(2).all(|pair| pair[0].end + 1 == pair[1].start));
        assert_eq!(ranges.iter().map(ByteRange::len).sum::<u64>(), 10_000);
    }

    #[test]
    fn planner_keeps_small_files_single_stream() {
        let ranges = plan_ranges(3 * 1024 * 1024, &DownloadConfig::default());
        assert_eq!(ranges.len(), 1);
        assert_eq!(ranges[0].len(), 3 * 1024 * 1024);
    }

    #[test]
    fn planner_distributes_remainder_without_gaps() {
        let config = DownloadConfig {
            max_chunks: 3,
            max_parallel: 1,
            min_chunk_size: 1,
            request_timeout: Duration::from_secs(5),
        };
        let ranges = plan_ranges(10, &config);
        assert_eq!(ranges.iter().map(ByteRange::len).collect::<Vec<_>>(), vec![4, 3, 3]);
        assert_eq!(ranges[2].end, 9);
    }
}
