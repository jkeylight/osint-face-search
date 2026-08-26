"""
Yandex Images - Playwright scraper
"""
import asyncio
from pathlib import Path
from typing import List
import logging

from scrapers.base import BaseScraper, SearchResult

logger = logging.getLogger(__name__)


class YandexScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.engine_name = "yandex"
        self.cooldown = 4.0
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

            logger.info("[yandex] Navigating to Yandex Images...")
            await page.goto("https://yandex.com/images/", wait_until="domcontentloaded")
            await self._random_delay(2, 3)

            # Click camera icon
            camera = await page.query_selector('button.input__camera, .input__camera, [aria-label="Upload by image"]')
            if camera:
                logger.info("[yandex] Clicking camera...")
                await camera.click()
                await self._random_delay(1, 2)

            file_input = await page.query_selector('input[type="file"]')
            if file_input:
                logger.info("[yandex] Uploading image...")
                await file_input.set_input_files(image_path)
                await self._random_delay(5, 8)
            else:
                logger.warning("[yandex] No file input found")
                return results

            await page.wait_for_load_state("networkidle")
            await self._random_delay(3, 4)

            results = await self._extract(page)
            logger.info(f"[yandex] Extracted {len(results)} results")

        except Exception as e:
            logger.error(f"[yandex] Search failed: {e}")
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
            # Get all links on the results page
            links = await page.query_selector_all('a[href]')
            for link in links[:50]:
                try:
                    href = await link.get_attribute('href')
                    if not href or not href.startswith('http'):
                        continue
                    if 'yandex' in href or 'ya.ru' in href:
                        continue
                    if href in seen:
                        continue
                    seen.add(href)

                    title = await link.inner_text()
                    if not title or len(title) > 200:
                        title = ""

                    results.append(SearchResult(
                        url=href, source_url="https://yandex.com",
                        title=title[:100], engine="yandex",
                        thumbnail_url=None
                    ))
                except:
                    continue

            # Also get image thumbnails
            imgs = await page.query_selector_all('.CbirSites-ItemImage img, .serp-item__thumb img, img[data-bem]')
            for img in imgs[:20]:
                try:
                    src = await img.get_attribute('src')
                    if src and src.startswith('http') and src not in seen:
                        seen.add(src)
                        parent = await img.evaluate_handle('el => el.closest("a")')
                        href = await parent.get_attribute('href') if parent else src
                        results.append(SearchResult(
                            url=href or src, source_url="https://yandex.com",
                            title="", engine="yandex", thumbnail_url=src
                        ))
                except:
                    continue

        except Exception as e:
            logger.error(f"[yandex] Extraction error: {e}")

        return results[:20]

    async def close(self):
        try:
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except:
            pass
