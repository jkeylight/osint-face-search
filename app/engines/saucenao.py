"""
SauceNAO reverse image search.

Uses the free JSON API when SAUCENAO_API_KEY is set, otherwise falls back to
browser upload.  Excellent for anime/art and indexed source pages.
"""
from __future__ import annotations

import logging
from typing import List
from urllib.parse import quote_plus

from app.config import config
from app.engines.base import Candidate, SearchContext, ProbeResult
from app.engines.base import EngineMeta
from app.engines.browser import BrowserEngine

logger = logging.getLogger(__name__)


class SauceNAOEngine(BrowserEngine):
    meta = EngineMeta(
        key="saucenao",
        label="SauceNAO",
        category="reverse",
        requires="http",
        description="Anime/art focused reverse search; free API key supported",
        homepage="https://saucenao.com",
    )

    async def probe(self) -> ProbeResult:
        if not config.SAUCENAO_API_KEY:
            # browser fallback path
            return await super().probe()
        return ProbeResult(True, "api key configured")

    async def _api_search(self, ctx: SearchContext) -> List[Candidate]:
        import aiohttp

        url = (
            "https://saucenao.com/search.php?output_type=2&numresults="
            f"{min(30, ctx.max_results)}&db=999&api_key={config.SAUCENAO_API_KEY}"
        )
        data = await ctx.session.post(
            url,
            data={"file": open(ctx.face_path, "rb")},
            timeout=aiohttp.ClientTimeout(total=config.ENGINE_TIMEOUT_S),
        )
        if data.status != 200:
            raise RuntimeError(f"API HTTP {data.status}")
        payload = await data.json()
        out: List[Candidate] = []
        for res in payload.get("results", []):
            header = res.get("header", {})
            data_ = res.get("data", {})
            thumb = header.get("thumbnail", "")
            if thumb.startswith("//"):
                thumb = "https:" + thumb
            out.append(Candidate(
                image_url=data_.get("source") or thumb,
                source_url=header.get("source_url") or "",
                title=(data_.get("title") or header.get("index_name") or "")[:200],
                engine=self.meta.key,
                thumb_url=thumb,
                score=float(header.get("similarity") or 0.0),
            ))
        return [c for c in out if c.image_url.startswith("http")][: ctx.max_results]

    async def search(self, ctx: SearchContext) -> List[Candidate]:
        if config.SAUCENAO_API_KEY and ctx.session is not None:
            return await self._api_search(ctx)

        # Browser fallback
        out: List[Candidate] = []
        page = None
        browser_ctx = None
        try:
            browser_ctx = await ctx.browser.new_context()
            page = await browser_ctx.new_page()
            page.set_default_timeout(25000)
            await page.goto("https://saucenao.com/", wait_until="domcontentloaded")
            await self.human_delay(0.8, 1.6)
            file_input = await page.query_selector('input[type="file"]')
            if not file_input:
                raise RuntimeError("upload input not found")
            await file_input.set_input_files(ctx.face_path)
            await self.human_delay(4.0, 6.0)
            try:
                await page.wait_for_selector(".result", timeout=30000)
            except Exception:
                pass

            tiles = await page.query_selector_all(".result")
            for tile in tiles[: ctx.max_results]:
                try:
                    link = await tile.query_selector("a")
                    href = (await link.get_attribute("href")) if link else ""
                    img = await tile.query_selector("img")
                    src = (await img.get_attribute("src")) if img else ""
                    if src.startswith("//"):
                        src = "https:" + src
                    if not href.startswith("http") and not src.startswith("http"):
                        continue
                    out.append(Candidate(image_url=src or href, source_url=href, engine=self.meta.key))
                except Exception:
                    continue
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(str(e)[:200]) from e
        finally:
            for closer in (page, browser_ctx):
                try:
                    if closer:
                        await closer.close()
                except Exception:
                    pass
        return out[: ctx.max_results]
