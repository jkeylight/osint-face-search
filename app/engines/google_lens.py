"""
Google Lens reverse image search (browser engine).

Flow: lens.google.com -> file input -> parse result links.  Google rotates
its DOM frequently, so extraction uses several strategies and the engine
reports a clean "no results / selectors moved" status instead of crashing.
"""
from __future__ import annotations

import json
import logging
from typing import List

from app.engines.base import Candidate, SearchContext
from app.engines.base import EngineMeta
from app.engines.browser import BrowserEngine

logger = logging.getLogger(__name__)


class GoogleLensEngine(BrowserEngine):
    meta = EngineMeta(
        key="google_lens",
        label="Google Lens",
        category="reverse",
        requires="browser",
        description="Reverse image search via Google Lens (visually similar pages and images)",
        homepage="https://lens.google.com",
    )

    async def search(self, ctx: SearchContext) -> List[Candidate]:
        out: List[Candidate] = []
        page = None
        browser_ctx = None
        try:
            browser_ctx = await ctx.browser.new_context()
            page = await browser_ctx.new_page()
            page.set_default_timeout(20000)

            await page.goto("https://lens.google.com/", wait_until="domcontentloaded")
            await self.human_delay(1.0, 2.0)

            file_input = await page.query_selector('input[type="file"]')
            if not file_input:
                # Lens sometimes renders the picker behind a button
                for sel in ('button[aria-label*="search by image"]', 'div[role="button"]'):
                    btn = await page.query_selector(sel)
                    if btn:
                        try:
                            await btn.click()
                            await self.human_delay(0.5, 1.0)
                        except Exception:
                            pass
                        file_input = await page.query_selector('input[type="file"]')
                        if file_input:
                            break
            if not file_input:
                raise RuntimeError("upload input not found (page layout changed)")

            await file_input.set_input_files(ctx.face_path)
            await page.wait_for_load_state("networkidle")
            await self.human_delay(2.5, 4.0)

            # ---- strategy 1: external result links
            hrefs = await self._extract_json_links(
                page,
                [
                    'a[data-url]', 'div[data-attrid] a',
                    'a[href^="http"] span + img', 'c-wiz a[href^="http"]',
                ],
                self.meta.key,
            )
            for href in hrefs:
                out.append(Candidate(
                    image_url=href, source_url=href,
                    engine=self.meta.key, title="",
                ))

            # ---- strategy 2: embedded state blobs contain image matches
            try:
                content = await page.content()
                for needle in ('"originalImageUrl":"', '"imageUrl":"', '"sourceUrl":"'):
                    idx = 0
                    while len(out) < ctx.max_results:
                        idx = content.find(needle, idx)
                        if idx == -1:
                            break
                        start = idx + len(needle)
                        end = content.find('"', start)
                        if end == -1:
                            break
                        raw = content[start:end].encode().decode("unicode_escape", "ignore")
                        idx = end
                        if raw.startswith("http") and not any(
                            x in raw for x in ("google", "gstatic")
                        ):
                            out.append(Candidate(image_url=raw, engine=self.meta.key))
            except Exception as e:  # noqa: BLE001
                logger.debug("[google_lens] state parse: %s", e)

        except Exception as e:  # noqa: BLE001
            raise RuntimeError(str(e)[:200]) from e
        finally:
            for closer in (page, browser_ctx):
                try:
                    if closer:
                        await closer.close()
                except Exception:
                    pass

        # dedupe
        seen, uniq = set(), []
        for c in out:
            if c.image_url not in seen:
                seen.add(c.image_url)
                uniq.append(c)
        return uniq[: ctx.max_results]
