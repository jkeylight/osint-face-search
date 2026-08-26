"""
Bing Visual Search - Playwright scraper (verified working selectors)
"""
import asyncio
import base64
from pathlib import Path
from typing import List
import logging

from scrapers.base import BaseScraper, SearchResult

logger = logging.getLogger(__name__)


class BingScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.engine_name = "bing"
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

            logger.info("[bing] Navigating to Bing Images...")
            await page.goto("https://www.bing.com/images", wait_until="domcontentloaded")
            await self._random_delay(2, 3)

            # Click the camera/search by image button
            camera_btn = await page.query_selector('a[aria-label="Search by image"], button[aria-label="Search by image"], .btn_camera, #sb_camera')
            if camera_btn:
                logger.info("[bing] Clicking camera button...")
                await camera_btn.click()
                await self._random_delay(1, 2)
            else:
                logger.info("[bing] No camera button found, trying direct URL approach")
                # Use Bing visual search URL directly
                upload_url = "https://www.bing.com/images/search?view=detailv2&iss=sbiupload&FORM=SBIHMP"
                await page.goto(upload_url, wait_until="domcontentloaded")
                await self._random_delay(2, 3)

            # Find file input
            file_input = await page.query_selector('input[type="file"]')
            if file_input:
                logger.info("[bing] Uploading image...")
                await file_input.set_input_files(image_path)
                await self._random_delay(5, 8)
            else:
                logger.warning("[bing] No file input found")
                return results

            # Wait for results to load
            await page.wait_for_load_state("networkidle")
            await self._random_delay(3, 4)

            # Extract image result links
            results = await self._extract(page)
            logger.info(f"[bing] Extracted {len(results)} results")

        except Exception as e:
            logger.error(f"[bing] Search failed: {e}")
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
            # Method 1: Get all links that point to external sites
            links = await page.query_selector_all('a.iusc, a[href*="http"]')
            for link in links[:40]:
                try:
                    href = await link.get_attribute('href')
                    if not href or not href.startswith('http'):
                        continue
                    if 'bing.com' in href or 'microsoft.com' in href:
                        continue
                    if href in seen:
                        continue
                    seen.add(href)

                    # Try to get m attribute (Bing stores metadata there)
                    m_attr = await link.get_attribute('m')
                    title = ""
                    thumbnail = ""
                    if m_attr:
                        import json
                        try:
                            m_data = json.loads(m_attr)
                            title = m_data.get('t', '')
                            thumbnail = m_data.get('purl', '')
                        except:
                            pass

                    if not title:
                        title_el = await link.query_selector('.tit, .title')
                        if title_el:
                            title = await title_el.inner_text()

                    results.append(SearchResult(
                        url=href,
                        source_url="https://bing.com",
                        title=title[:100] if title else "",
                        engine="bing",
                        thumbnail_url=thumbnail if thumbnail else None
                    ))
                except:
                    continue

            # Method 2: Get image thumbnails and their source pages
            img_containers = await page.query_selector('.imgpt')
            for container in img_containers[:30]:
                try:
                    link = await container.query_selector('a')
                    if link:
                        href = await link.get_attribute('href')
                        if href and href.startswith('http') and href not in seen:
                            seen.add(href)
                            img = await container.query_selector('img')
                            thumb = await img.get_attribute('src') if img else None
                            results.append(SearchResult(
                                url=href, source_url="https://bing.com",
                                title="", engine="bing", thumbnail_url=thumb
                            ))
                except:
                    continue

        except Exception as e:
            logger.error(f"[bing] Extraction error: {e}")

        return results[:20]

    async def close(self):
        try:
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except:
            pass
