"""
Application configuration — environment overridable.

All settings can be overridden with the OSINT_ prefix, e.g.:
    OSINT_HOST=0.0.0.0 OSINT_PORT=9000 python run.py
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    return os.environ.get(f"OSINT_{name}", default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(f"OSINT_{name}", default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(f"OSINT_{name}", default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(f"OSINT_{name}")
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    # ------------------------------------------------------------------ paths
    BASE_DIR: Path = BASE_DIR
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    CANDIDATE_DIR: Path = BASE_DIR / "data" / "candidates"
    CACHE_DIR: Path = BASE_DIR / "cache"
    DATA_DIR: Path = BASE_DIR / "data"
    STATIC_DIR: Path = BASE_DIR / "static"
    MODEL_DIR: Path = BASE_DIR / "models"
    DEMO_DIR: Path = BASE_DIR / "demo"
    LOG_DIR: Path = BASE_DIR / "logs"
    DB_PATH: Path = BASE_DIR / "data" / "osint.db"

    YUNET_MODEL: str = "face_detection_yunet_2023mar.onnx"
    SFACE_MODEL: str = "face_recognition_sface_2021dec.onnx"

    # ----------------------------------------------------------------- server
    HOST: str = field(default_factory=lambda: _env("HOST", "0.0.0.0"))
    PORT: int = field(default_factory=lambda: _env_int("PORT", 8000))

    # ------------------------------------------------------- face recognition
    # Preferred backend order. First backend whose deps+models are available
    # becomes active.  ("insightface" needs pip install insightface onnxruntime)
    FACE_BACKENDS: List[str] = field(
        default_factory=lambda: _env("FACE_BACKENDS", "insightface,opencv").split(",")
    )
    AUTO_DOWNLOAD_MODELS: bool = field(
        default_factory=lambda: _env_bool("AUTO_DOWNLOAD_MODELS", True)
    )
    DET_SCORE_THRESHOLD: float = field(
        default_factory=lambda: _env_float("DET_SCORE_THRESHOLD", 0.6)
    )
    MAX_FACES_PER_IMAGE: int = field(
        default_factory=lambda: _env_int("MAX_FACES_PER_IMAGE", 8)
    )

    # Verdict bands (cosine similarity). Defaults calibrated for SFace
    # (documented 0.363 same-person threshold, empirically raised for
    # high-quality studio-like imagery) and ArcFace community practice.
    VERDICT_STRONG: float = field(default_factory=lambda: _env_float("VERDICT_STRONG", 0.55))
    VERDICT_POSSIBLE: float = field(default_factory=lambda: _env_float("VERDICT_POSSIBLE", 0.45))
    VERDICT_WEAK: float = field(default_factory=lambda: _env_float("VERDICT_WEAK", 0.30))

    # ------------------------------------------------------------------ limits
    MAX_UPLOAD_MB: int = field(default_factory=lambda: _env_int("MAX_UPLOAD_MB", 15))
    MAX_CANDIDATES: int = field(default_factory=lambda: _env_int("MAX_CANDIDATES", 120))
    MAX_RESULTS_PER_ENGINE: int = field(
        default_factory=lambda: _env_int("MAX_RESULTS_PER_ENGINE", 25)
    )
    DOWNLOAD_CONCURRENCY: int = field(
        default_factory=lambda: _env_int("DOWNLOAD_CONCURRENCY", 12)
    )
    ENGINE_CONCURRENCY: int = field(default_factory=lambda: _env_int("ENGINE_CONCURRENCY", 4))
    DOWNLOAD_TIMEOUT_S: float = field(default_factory=lambda: _env_float("DOWNLOAD_TIMEOUT_S", 12.0))
    ENGINE_TIMEOUT_S: float = field(default_factory=lambda: _env_float("ENGINE_TIMEOUT_S", 90.0))
    PROBE_TIMEOUT_S: float = field(default_factory=lambda: _env_float("PROBE_TIMEOUT_S", 6.0))
    CANDIDATE_MAX_EDGE: int = field(default_factory=lambda: _env_int("CANDIDATE_MAX_EDGE", 1024))
    THUMB_SIZE: int = field(default_factory=lambda: _env_int("THUMB_SIZE", 480))
    MIN_CANDIDATE_EDGE: int = field(default_factory=lambda: _env_int("MIN_CANDIDATE_EDGE", 40))

    # ---------------------------------------------------------------- retention
    JOB_RETENTION_DAYS: int = field(default_factory=lambda: _env_int("JOB_RETENTION_DAYS", 14))
    MAX_STORAGE_GB: float = field(default_factory=lambda: _env_float("MAX_STORAGE_GB", 10.0))

    # ------------------------------------------------------------------ ranking
    SOURCE_WEIGHTS: Dict[str, float] = field(
        default_factory=lambda: {
            "news": 1.00,
            "official": 0.90,
            "social": 0.75,
            "forum": 0.60,
            "unknown": 0.40,
        }
    )

    USER_AGENTS: List[str] = field(
        default_factory=lambda: [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
        ]
    )

    # ------------------------------------------------------------------ secrets
    # Optional: SauceNAO free API key (https://saucenao.com/user.php)
    SAUCENAO_API_KEY: str = field(default_factory=lambda: os.environ.get("SAUCENAO_API_KEY", ""))
    # Optional: proxy for all outbound HTTP, e.g. socks5://127.0.0.1:9050
    PROXY_URL: str = field(default_factory=lambda: os.environ.get("OSINT_PROXY_URL", ""))

    def __post_init__(self) -> None:
        for d in (
            self.UPLOAD_DIR,
            self.CANDIDATE_DIR,
            self.CACHE_DIR,
            self.DATA_DIR,
            self.LOG_DIR,
            self.MODEL_DIR,
        ):
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- derived info
    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024

    def ensure_dirs(self) -> None:
        self.__post_init__()


config = Config()
