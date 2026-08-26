"""TinEye reverse image search (browser engine). Free tier shows top matches."""
from __future__ import annotations

import logging
from typing import List

from app.engines.base import Candidate, SearchContext
from app.engines.base import EngineMeta
from app.engines.browser import BrowserEngine

logger = logging.getLogger(__name__)


class TinEyeEngine(BrowserEngine):
    meta = EngineMeta(
        key="tineye",
        label="TinEye",
        category="reverse",
        requires="browser",
        description="Oldest reverse image search; exact + modified matches with dates",
        homepage="https://tineye.com",
    )

    async def search(self, ctx: SearchContext) -> List[Candidate]:
        out: List[Candidate] = []
        page = None
        browser_ctx = None
        try:
            browser_ctx = await ctx.browser.new_context()
            page = await browser_ctx.new_page()
            page.set_default_timeout(25000)

            await page.goto("https://tineye.com/", wait_until="domcontentloaded")
            await self.human_delay(1.0, 2.0)

            file_input = await page.query_selector('input[type="file"]')
            if not file_input:
                raise RuntimeError("upload input not found")
            await file_input.set_input_files(ctx.face_path)

            try:
                await page.wait_for_selector(".result-wrap, .results-wrap, .match", timeout=30000)
            except Exception:
                pass
            await self.human_delay(1.5, 3.0)

            tiles = await page.query_selector_all(".result, .match, div.image-result")
            for tile in tiles[: ctx.max_results]:
                try:
                    link = await tile.query_selector("a")
                    if not link:
                        continue
                    href = await link.get_attribute("href") or ""
                    img = await tile.query_selector("img")
                    img_src = (await img.get_attribute("src")) if img else ""
                    if img_src and img_src.startswith("//"):
                        img_src = "https:" + img_src
                    if not href.startswith("http") and not img_src.startswith("http"):
                        continue
                    out.append(Candidate(
                        image_url=img_src or href,
                        source_url=href if href.startswith("http") else "",
                        engine=self.meta.key,
                    ))
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

        seen, uniq = set(), []
        for c in out:
            if c.image_url not in seen:
                seen.add(c.image_url)
                uniq.append(c)
        return uniq[: ctx.max_results]
