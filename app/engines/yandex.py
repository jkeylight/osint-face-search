"""
Yandex Images reverse image search (browser engine).

Yandex is consistently the strongest free engine for face lookups.
Flow: yandex.com/images/search?rpt=imageview -> upload -> parse similar
results from anchors and embedded JSON state.
"""
from __future__ import annotations

import json
import logging
from typing import List

from app.engines.base import Candidate, SearchContext
from app.engines.base import EngineMeta
from app.engines.browser import BrowserEngine

logger = logging.getLogger(__name__)


class YandexEngine(BrowserEngine):
    meta = EngineMeta(
        key="yandex",
        label="Yandex Images",
        category="reverse",
        requires="browser",
        description="Best free engine for face reverse search; similar images + pages",
        homepage="https://yandex.com",
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
                "https://yandex.com/images/search?rpt=imageview",
                wait_until="domcontentloaded",
            )
            await self.human_delay(1.2, 2.2)

            # accept consent banner if it appears
            try:
                consent = await page.query_selector(
                    'button[class*="consent"] , form[data-testid="consent"] button'
                )
                if consent:
                    await consent.click()
                    await self.human_delay(0.8, 1.4)
            except Exception:
                pass

            file_input = await page.query_selector('input[type="file"]')
            if not file_input:
                for sel in ("button.Button-SearchBy-image", ".CbirButton", "button[aria-label*='search by image']"):
                    btn = await page.query_selector(sel)
                    if btn:
                        try:
                            await btn.click()
                            await self.human_delay(0.8, 1.5)
                        except Exception:
                            pass
                        file_input = await page.query_selector('input[type="file"]')
                        if file_input:
                            break
            if not file_input:
                raise RuntimeError("upload input not found (page layout changed)")

            await file_input.set_input_files(ctx.face_path)
            await self.human_delay(3.0, 5.0)
            try:
                await page.wait_for_load_state("networkidle")
            except Exception:
                pass

            # --- similar image results (anchors carry data-bem with URLs)
            anchors = await page.query_selector_all("a.Link, a.SerpItem, a.CbirSites-ItemTitle")
            for a in anchors[:80]:
                try:
                    href = await a.get_attribute("href")
                    if not href or not href.startswith("http"):
                        continue
                    if "yandex" in href and "yandex.ru/images/search" in href:
                        continue
                    out.append(Candidate(image_url=href, source_url=href, engine=self.meta.key))
                    if len(out) >= ctx.max_results:
                        break
                except Exception:
                    continue

            # --- embedded state (cbir) with direct image URLs
            try:
                content = await page.content()
                needle = '"serpItems":'
                idx = content.find(needle)
                if idx != -1:
                    blob = content[idx + len(needle): idx + len(needle) + 400000]
                    # crude extraction of imgHref / href pairs
                    for key in ('"imgHref":"', '"href":"', '"originalImage":{"url":"'):
                        pos = 0
                        while len(out) < ctx.max_results * 2:
                            pos = blob.find(key, pos)
                            if pos == -1:
                                break
                            s = pos + len(key)
                            e = blob.find('"', s)
                            if e == -1:
                                break
                            url = blob[s:e].encode().decode("unicode_escape", "ignore")
                            pos = e
                            if url.startswith("http") and "yandex" not in url:
                                out.append(Candidate(image_url=url, engine=self.meta.key))
            except Exception as e:  # noqa: BLE001
                logger.debug("[yandex] state parse: %s", e)

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
