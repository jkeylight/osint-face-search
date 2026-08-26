"""
Google Lens - Playwright scraper
"""
import asyncio
from pathlib import Path
from typing import List
import logging

from scrapers.base import BaseScraper, SearchResult

logger = logging.getLogger(__name__)


class GoogleLensScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.engine_name = "google_lens"
        self.cooldown = 5.0
        self._pw = None
        self._browser = None

    async def _ensure_browser(self):
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
            )
        ctx = await self._browser.new_context(
            user_agent=self._get_random_ua(),
            viewport={"width": 1920, "height": 1080},
        )
        await ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        return ctx

    async def search(self, image_path: str) -> List[SearchResult]:
        results = []
        ctx = None
        page = None
        try:
            ctx = await self._ensure_browser()
            page = await ctx.new_page()

            logger.info("[google] Navigating to Google Lens...")
            await page.goto("https://lens.google.com/", wait_until="domcontentloaded")
            await self._random_delay(2, 3)

            file_input = await page.query_selector('input[type="file"]')
            if file_input:
                logger.info("[google] Uploading image...")
                await file_input.set_input_files(image_path)
                await self._random_delay(5, 8)
            else:
                logger.warning("[google] No file input found")
                return results

            await page.wait_for_load_state("networkidle")
            await self._random_delay(3, 4)

            results = await self._extract(page)
            logger.info(f"[google] Extracted {len(results)} results")

        except Exception as e:
            logger.error(f"[google] Search failed: {e}")
        finally:
            if page:
                try:
                    await page.close()
                except:
                    pass
            if ctx:
                try:
                    await ctx.close()
                except:
                    pass

        self._log_result(len(results), len(results) > 0)
        return results

    async def _extract(self, page) -> List[SearchResult]:
        results = []
        seen = set()

        try:
            links = await page.query_selector_all('a[href]')
            for link in links[:50]:
                try:
                    href = await link.get_attribute('href')
                    if not href or not href.startswith('http'):
                        continue
                    if 'google' in href or 'gstatic' in href or 'googleapis' in href:
                        continue
                    if href in seen:
                        continue
                    seen.add(href)

                    title = await link.inner_text()
                    if not title or len(title) > 200:
                        title = ""

                    results.append(SearchResult(
                        url=href, source_url="https://lens.google.com",
                        title=title[:100], engine="google_lens",
                        thumbnail_url=None
                    ))
                except:
                    continue

            # Get image results
            imgs = await page.query_selector_all('img[src^="http"]')
            for img in imgs[:20]:
                try:
                    src = await img.get_attribute('src')
                    if src and 'google' not in src and src not in seen:
                        seen.add(src)
                        parent = await img.evaluate_handle('el => el.closest("a")')
                        href = await parent.get_attribute('href') if parent else src
                        results.append(SearchResult(
                            url=href or src, source_url="https://lens.google.com",
                            title="", engine="google_lens", thumbnail_url=src
                        ))
                except:
                    continue

        except Exception as e:
            logger.error(f"[google] Extraction error: {e}")

        return results[:20]

    async def close(self):
        try:
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except:
            pass
