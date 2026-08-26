"""
Shared Playwright browser manager — one browser instance, isolated context
per search, stealth-ish defaults, hard timeouts, graceful unavailability.

If Playwright (or Chromium) is missing the manager reports unavailable and
browser engines degrade instead of crashing the search.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.config import config
from app.engines.base import BaseEngine, ProbeResult

logger = logging.getLogger(__name__)


class BrowserManager:
    def __init__(self):
        self._pw = None
        self._browser = None
        self._lock = asyncio.Lock()
        self._unavailable_reason: Optional[str] = None
        self._started = False

    async def _ensure(self) -> bool:
        async with self._lock:
            if self._started:
                return self._browser is not None
            self._started = True
            try:
                from playwright.async_api import async_playwright
            except Exception:
                self._unavailable_reason = (
                    "Playwright not installed — run: pip install playwright && playwright install chromium"
                )
                return False
            try:
                self._pw = await async_playwright().start()
                self._browser = await self._pw.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ],
                )
                logger.info("Chromium launched for browser engines")
                return True
            except Exception as e:
                self._unavailable_reason = f"Chromium launch failed: {e}"[:300]
                logger.warning("[browser] %s", self._unavailable_reason)
                return False

    @property
    def unavailable_reason(self) -> Optional[str]:
        return self._unavailable_reason

    async def available(self) -> bool:
        return await self._ensure()

    async def new_context(self):
        ok = await self._ensure()
        if not ok or self._browser is None:
            return None
        import random

        ctx = await self._browser.new_context(
            user_agent=random.choice(config.USER_AGENTS),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            timezone_id="UTC",
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            "window.chrome={runtime:{}};"
        )
        return ctx

    async def close(self) -> None:
        async with self._lock:
            try:
                if self._browser:
                    await self._browser.close()
            except Exception:
                pass
            try:
                if self._pw:
                    await self._pw.stop()
            except Exception:
                pass
            self._browser = None
            self._pw = None


browser_manager = BrowserManager()


class BrowserEngine(BaseEngine):
    """Base for engines that drive a real browser via Playwright."""

    async def probe(self) -> ProbeResult:
        if not await browser_manager.available():
            return ProbeResult(False, browser_manager.unavailable_reason or "browser unavailable")
        return await super().probe()

    async def _extract_json_links(self, page, selectors, engine_key) -> list:
        """Collect hrefs from multiple selector strategies, deduplicated."""
        out, seen = [], set()
        for sel in selectors:
            try:
                for el in await page.query_selector_all(sel):
                    href = await el.get_attribute("href")
                    if not href:
                        continue
                    if href.startswith("//"):
                        href = "https:" + href
                    if not href.startswith("http") or href in seen:
                        continue
                    if any(b in href for b in ("google.", "bing.com/images/search", "yandex.", "microsoft")):
                        continue
                    seen.add(href)
                    out.append(href)
                    if len(out) >= 60:
                        return out
            except Exception:
                continue
        return out

