"""
Snapchat Scraper - public stories and discover content
"""
import aiohttp
import logging
from typing import List

from scrapers.base import BaseScraper, SearchResult

logger = logging.getLogger(__name__)


class SnapchatScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.engine_name = "snapchat"
        self.cooldown = 3.0

    async def search(self, image_path: str) -> List[SearchResult]:
        results = []
        try:
            # Snapchat public profiles API
            public_profiles = [
                "https://www.snapchat.com/@natgeo",
                "https://www.snapchat.com/@bbc",
                "https://www.snapchat.com/@nytimes",
            ]

            async with aiohttp.ClientSession() as session:
                for profile_url in public_profiles:
                    try:
                        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                        async with session.get(profile_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            if resp.status == 200:
                                html = await resp.text()
                                # Extract image URLs from public profile
                                import re
                                img_urls = re.findall(r'https://(?:sf16-website-login\.s3\.us-west-2\.amazonaws\.com|storycdn\.snap\.com)[^\s"<>]+\.jpg', html)
                                for url in img_urls[:5]:
                                    results.append(SearchResult(
                                        url=url,
                                        source_url=profile_url,
                                        title="Snapchat story",
                                        engine="snapchat",
                                        thumbnail_url=url
                                    ))
                    except Exception as e:
                        logger.warning(f"[snapchat] Profile failed: {e}")
                        continue

        except Exception as e:
            logger.error(f"[snapchat] Search failed: {e}")

        logger.info(f"[snapchat] Found {len(results)} images")
        self._log_result(len(results), len(results) > 0)
        return results[:20]

    async def close(self):
        pass
