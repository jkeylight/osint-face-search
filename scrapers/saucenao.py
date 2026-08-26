"""
SauceNAO Scraper - Anime/Art/Illustration reverse search
"""
import asyncio
from typing import List
import logging

from scrapers.base import BaseScraper, SearchResult

logger = logging.getLogger(__name__)

class SauceNAOScraper(BaseScraper):
    """SauceNAO reverse image search for anime/art"""
    
    def __init__(self):
        super().__init__()
        self.engine_name = "saucenao"
        self.cooldown = 3.0
        self._browser = None
        self._context = None
    
    async def _get_browser(self):
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True, args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
            )
            self._context = await self._browser.new_context(
                user_agent=self._get_random_ua(), viewport={"width": 1920, "height": 1080},
            )
            await self._context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        return self._context
    
    async def search(self, image_path: str) -> List[SearchResult]:
        results = []
        try:
            context = await self._get_browser()
            page = await context.new_page()
            
            await page.goto("https://saucenao.com/search.php", wait_until="networkidle")
            await self._random_delay(2, 3)
            
            file_input = await page.query_selector('input[type="file"]')
            if file_input:
                await file_input.set_input_files(image_path)
                await self._random_delay(1, 2)
            
            search_btn = await page.query_selector('input[type="submit"], button[type="submit"]')
            if search_btn:
                await search_btn.click()
                await self._random_delay(4, 6)
            
            await page.wait_for_load_state("networkidle")
            await self._random_delay(2, 3)
            
            results = await self._extract_results(page)
            self._log_result(len(results), True)
        except Exception as e:
            self._log_result(0, False, str(e))
        finally:
            try: await page.close()
            except: pass
        return results
    
    async def _extract_results(self, page) -> List[SearchResult]:
        results = []
        try:
            items = await page.query_selector_all('.result, .result-image, table.result-table')
            for item in items[:30]:
                try:
                    link = await item.query_selector('a[href]')
                    if link:
                        href = await link.get_attribute('href')
                        if href and href.startswith('http'):
                            img = await item.query_selector('img')
                            thumbnail = await img.get_attribute('src') if img else None
                            title_el = await item.query_selector('.title, .result-title')
                            title = await title_el.inner_text() if title_el else ""
                            results.append(SearchResult(
                                url=href, source_url="https://saucenao.com",
                                title=title.strip()[:100], engine="saucenao",
                                thumbnail_url=thumbnail
                            ))
                except: continue
        except Exception as e:
            logger.error(f"SauceNAO extraction failed: {e}")
        
        seen = set()
        return [r for r in results if r.url not in seen and not seen.add(r.url)][:20]
    
    async def close(self):
        try:
            if self._context: await self._context.close()
            if self._browser: await self._browser.close()
            if self._playwright: await self._playwright.stop()
        except: pass
