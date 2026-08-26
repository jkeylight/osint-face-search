"""Baidu Graph reverse image search (browser engine). Strong for Asian-source content."""
from __future__ import annotations

import logging
from typing import List

from app.engines.base import Candidate, SearchContext
from app.engines.base import EngineMeta
from app.engines.browser import BrowserEngine

logger = logging.getLogger(__name__)


class BaiduEngine(BrowserEngine):
    meta = EngineMeta(
        key="baidu",
        label="Baidu Image",
        category="reverse",
        requires="browser",
        description="Baidu Graph reverse search; coverage skewed to Chinese web",
        homepage="https://graph.baidu.com",
    )

    async def search(self, ctx: SearchContext) -> List[Candidate]:
        out: List[Candidate] = []
        page = None
        browser_ctx = None
        try:
            browser_ctx = await ctx.browser.new_context()
            page = await browser_ctx.new_page()
            page.set_default_timeout(25000)

            await page.goto(
                "https://graph.baidu.com/pcpage/index?tpl_from=graph",
                wait_until="domcontentloaded",
            )
            await self.human_delay(1.5, 2.5)

            file_input = await page.query_selector('input[type="file"]')
            if not file_input:
                raise RuntimeError("upload input not found")
            await file_input.set_input_files(ctx.face_path)
            await self.human_delay(5.0, 7.0)
            try:
                await page.wait_for_load_state("networkidle")
            except Exception:
                pass

            # result cards expose data attributes with image + source urls
            cards = await page.query_selector_all(".graph_result, .similar-item, a[data-src]")
            for card in cards[: ctx.max_results]:
                try:
                    src = await card.get_attribute("data-src") or ""
                    href = await card.get_attribute("href") or ""
                    if not src:
                        img = await card.query_selector("img")
                        src = (await img.get_attribute("src")) if img else ""
                    if src.startswith("//"):
                        src = "https:" + src
                    if not src.startswith("http"):
                        continue
                    out.append(Candidate(image_url=src, source_url=href, engine=self.meta.key))
                except Exception:
                    continue

            if not out:
                hrefs = await self._extract_json_links(
                    page, ["a.graph-sign-item", "a[href^='http']"], self.meta.key
                )
                out = [Candidate(image_url=h, engine=self.meta.key) for h in hrefs]

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
