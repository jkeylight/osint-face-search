"""
Threads Scraper - public threads posts
"""
import aiohttp
import logging
import re
from typing import List

from scrapers.base import BaseScraper, SearchResult

logger = logging.getLogger(__name__)


class ThreadsScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.engine_name = "threads"
        self.cooldown = 3.0

    async def search(self, image_path: str) -> List[SearchResult]:
        results = []
        try:
            # Threads public profiles
            profiles = ["natgeo", "bbc", "nytimes"]

            async with aiohttp.ClientSession() as session:
                for username in profiles:
                    try:
                        url = f"https://www.threads.net/@{username}"
                        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            if resp.status == 200:
                                html = await resp.text()
                                # Extract image URLs from Threads
                                img_urls = re.findall(r'https://scontent-[^"\s]+\.cdninstagram\.com[^"\s]+\.jpg', html)
                                for img_url in img_urls[:5]:
                                    results.append(SearchResult(
                                        url=img_url,
                                        source_url=url,
                                        title=f"Threads post by @{username}",
                                        engine="threads",
                                        thumbnail_url=img_url
                                    ))
                    except Exception as e:
                        logger.warning(f"[threads] Profile {username} failed: {e}")
                        continue

        except Exception as e:
            logger.error(f"[threads] Search failed: {e}")

        logger.info(f"[threads] Found {len(results)} images")
        self._log_result(len(results), len(results) > 0)
        return results[:20]

    async def close(self):
        pass
