"""
4chan Image Board - JSON API scraper (most reliable)
"""
import aiohttp
from typing import List
import logging

from scrapers.base import BaseScraper, SearchResult

logger = logging.getLogger(__name__)


class FourChanScraper(BaseScraper):
    BOARDS = ["b", "pol", "gif", "wg", "cm", "3", "a", "v", "k", "o"]

    def __init__(self):
        super().__init__()
        self.engine_name = "4chan"
        self.cooldown = 1.0

    async def search(self, image_path: str) -> List[SearchResult]:
        results = []
        try:
            async with aiohttp.ClientSession() as session:
                for board in self.BOARDS:
                    try:
                        url = f"https://a.4cdn.org/{board}/catalog.json"
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            if resp.status != 200:
                                continue
                            catalog = await resp.json()

                        for page_data in catalog:
                            for thread in page_data.get("threads", []):
                                tim = thread.get("tim")
                                ext = thread.get("ext")
                                if not tim or not ext:
                                    continue

                                img_url = f"https://i.4cdn.org/{board}/{tim}{ext}"
                                thread_no = thread.get("no", 0)
                                thread_url = f"https://boards.4chan.org/{board}/thread/{thread_no}"
                                sub = thread.get("sub", "") or ""
                                com = thread.get("com", "") or ""
                                # Strip HTML from comment
                                import re
                                com_clean = re.sub(r'<[^>]+>', '', com)[:100]

                                results.append(SearchResult(
                                    url=img_url,
                                    source_url=thread_url,
                                    title=com_clean or sub or f"/{board}/",
                                    engine="4chan",
                                    thumbnail_url=img_url
                                ))
                    except Exception as e:
                        logger.warning(f"[4chan] Board {board} failed: {e}")
                        continue

                    await self._random_delay(0.5, 1.5)

        except Exception as e:
            logger.error(f"[4chan] Search failed: {e}")

        logger.info(f"[4chan] Found {len(results)} images")
        self._log_result(len(results), len(results) > 0)
        return results[:30]

    async def close(self):
        pass
