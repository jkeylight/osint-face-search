"""
Search engine adapter framework.

Each engine is an adapter that turns a query face image into a list of
candidate image URLs.  Engines must:
  * declare metadata (category, requirements)
  * implement `probe()`  — cheap availability check (deps + reachability)
  * implement `search()` — return candidates or raise

Every failure is a *status*, never a crash: the pipeline records the reason
and moves on.
"""
from __future__ import annotations

import asyncio
import logging
import random
import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse

from app.config import config

logger = logging.getLogger(__name__)


@dataclass
class Candidate:
    """A candidate image URL discovered by an engine."""
    image_url: str
    source_url: str = ""
    title: str = ""
    engine: str = ""
    thumb_url: str = ""
    width: int = 0
    height: int = 0
    score: float = 0.0          # engine-relevance (optional)
    meta: dict = field(default_factory=dict)


@dataclass
class ProbeResult:
    available: bool
    reason: str = ""


@dataclass
class EngineMeta:
    key: str
    label: str
    category: str            # "reverse" (reverse image search) | "feed" (public feeds)
    requires: str            # "browser" | "http"
    description: str = ""
    homepage: str = ""


def _reachable(host: str, timeout: float = 4.0) -> bool:
    """Quick TCP-level reachability check."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return _reachable_sync(host, timeout)
    try:
        fut = loop.run_in_executor(None, _reachable_sync, host, timeout)
        return asyncio.wait_for(asyncio.shield(fut), timeout=timeout + 1)
    except Exception:
        return False


def _reachable_sync(host: str, timeout: float = 4.0) -> bool:
    """Quick TCP-level reachability check."""
    try:
        conn = socket.create_connection((host, 443), timeout=timeout)
        conn.close()
        return True
    except Exception:
        pass
    try:
        conn = socket.create_connection((host, 80), timeout=timeout)
        conn.close()
        return True
    except Exception:
        return False


async def _http_reachable(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Real HTTPS probe — catches TLS-level blocking, not just TCP."""
    import aiohttp

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout),
            headers={"User-Agent": "Mozilla/5.0 (compatible; OSINT-Face-Search/2.0)"},
        ) as session:
            async with session.head(url, allow_redirects=True) as resp:
                return True, f"HTTP {resp.status}"
    except asyncio.TimeoutError:
        return False, f"timeout after {timeout:.0f}s"
    except Exception as e:  # noqa: BLE001
        return False, f"{e.__class__.__name__}: {str(e)[:80]}"


class BaseEngine(ABC):
    meta: EngineMeta

    def __init__(self):
        self._last_used = 0.0

    # ------------------------------------------------------------------ probes
    async def probe(self) -> ProbeResult:
        host = urlparse(self.meta.homepage).hostname or ""
        ok, detail = await _http_reachable(self.meta.homepage, timeout=config.PROBE_TIMEOUT_S)
        if not ok:
            return ProbeResult(False, f"unreachable ({detail})")
        return ProbeResult(True, "ready")

    # ------------------------------------------------------------------ search
    @abstractmethod
    async def search(self, ctx: "SearchContext") -> List[Candidate]:
        """Return candidate image URLs for the query image."""

    # ------------------------------------------------------------------ helpers
    @staticmethod
    async def human_delay(min_s: float = 0.8, max_s: float = 2.2) -> None:
        await asyncio.sleep(random.uniform(min_s, max_s))

    @staticmethod
    def random_ua() -> str:
        return random.choice(config.USER_AGENTS)


@dataclass
class SearchContext:
    """Everything an engine needs to run one search."""
    query_path: str                 # normalised full query image (jpg)
    face_path: str                  # cropped face / upper context (jpg)
    face_bbox: Optional[list] = None
    session=None                    # aiohttp.ClientSession
    browser=None                    # engines.browser.BrowserManager
    emit=None                       # callable(str, dict) progress emitter
    max_results: int = 25

    def event(self, kind: str, **data) -> None:
        if self.emit:
            try:
                self.emit(kind, data)
            except Exception:
                pass
