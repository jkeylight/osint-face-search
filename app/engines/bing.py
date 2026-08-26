"""
Bing Visual Search (browser engine).

The most automation-tolerant of the big engines.  Result tiles are anchors
with an `m` attribute containing JSON: murl = full image URL, purl = source
page, t = title.
"""
from __future__ import annotations

import json
import logging
from typing import List

from app.engines.base import Candidate, SearchContext
from app.engines.base import EngineMeta
from app.engines.browser import BrowserEngine

logger = logging.getLogger(__name__)


class BingEngine(BrowserEngine):
    meta = EngineMeta(
        key="bing",
        label="Bing Visual",
        category="reverse",
        requires="browser",
        description="Microsoft visual search; reliable automation target",
        homepage="https://www.bing.com",
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
                "https://www.bing.com/images?form=HDRSC2",
                wait_until="domcontentloaded",
            )
            await self.human_delay(1.2, 2.0)

            camera = await page.query_selector(
                'a[aria-label*="Image search" i], .cib-topleft-button, li[title*="visual search" i]'
            )
            if camera:
                try:
                    await camera.click()
                    await self.human_delay(0.8, 1.5)
                except Exception:
                    pass

            # try the visible "upload" pill / paste tab
            upload_tab = await page.query_selector('a[title="Upload an image" i], .upload_pill, a[href*="sbi"]')
            if upload_tab:
                try:
                    await upload_tab.click()
                    await self.human_delay(0.8, 1.5)
                except Exception:
                    pass

            file_input = await page.query_selector('input[type="file"]')
            if not file_input:
                await page.goto(
                    "https://www.bing.com/images/search?view=detailv2&iss=sbiupload&FORM=SBIHMP",
                    wait_until="domcontentloaded",
                )
                await self.human_delay(1.5, 2.5)
                file_input = await page.query_selector('input[type="file"]')
            if not file_input:
                raise RuntimeError("upload input not found (page layout changed)")

            await file_input.set_input_files(ctx.face_path)
            await self.human_delay(4.0, 6.0)
            try:
                await page.wait_for_load_state("networkidle")
            except Exception:
                pass

            tiles = await page.query_selector_all("a.iusc")
            for tile in tiles[: ctx.max_results * 2]:
                try:
                    m = await tile.get_attribute("m")
                    if not m:
                        continue
                    data = json.loads(m)
                    murl = data.get("murl") or ""
                    if not murl.startswith("http"):
                        continue
                    out.append(Candidate(
                        image_url=murl,
                        source_url=data.get("purl") or "",
                        title=(data.get("t") or "")[:200],
                        engine=self.meta.key,
                        thumb_url=data.get("turl") or "",
                        width=int(data.get("mw") or 0),
                        height=int(data.get("mh") or 0),
                    ))
                except Exception:
                    continue

            if not out:
                hrefs = await self._extract_json_links(
                    page, ["a.iusc", "a.title", "div.imgpt a"], self.meta.key
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
