"""
Reddit - JSON API scraper (most reliable)
"""
import aiohttp
from typing import List
import logging

from scrapers.base import BaseScraper, SearchResult

logger = logging.getLogger(__name__)


class RedditScraper(BaseScraper):
    SUBREDDITS = ["pics", "selfie", "Face", "face", "faces", "portraits", "photocritique"]

    def __init__(self):
        super().__init__()
        self.engine_name = "reddit"
        self.cooldown = 2.0

    async def search(self, image_path: str) -> List[SearchResult]:
        results = []
        try:
            async with aiohttp.ClientSession() as session:
                for sub in self.SUBREDDITS:
                    try:
                        url = f"https://www.reddit.com/r/{sub}/new.json?limit=25"
                        headers = {'User-Agent': 'Mozilla/5.0 (compatible; OSINTSearch/1.0)'}
                        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            if resp.status != 200:
                                continue
                            data = await resp.json()

                        posts = data.get("data", {}).get("children", [])
                        for post in posts:
                            pdata = post.get("data", {})
                            post_url = pdata.get("url", "")
                            permalink = pdata.get("permalink", "")
                            title = pdata.get("title", "")

                            # Check if it's an image post
                            if any(post_url.lower().endswith(e) for e in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                                results.append(SearchResult(
                                    url=post_url,
                                    source_url=f"https://reddit.com{permalink}",
                                    title=title[:100],
                                    engine="reddit",
                                    thumbnail_url=pdata.get("thumbnail", "") if pdata.get("thumbnail", "").startswith("http") else None
                                ))

                            # Check preview images
                            preview = pdata.get("preview", {})
                            images = preview.get("images", [])
                            for img in images:
                                src = img.get("source", {}).get("url", "")
                                if src:
                                    src = src.replace("&amp;", "&")
                                    results.append(SearchResult(
                                        url=src,
                                        source_url=f"https://reddit.com{permalink}",
                                        title=title[:100],
                                        engine="reddit",
                                        thumbnail_url=src
                                    ))

                    except Exception as e:
                        logger.warning(f"[reddit] Subreddit {sub} failed: {e}")
                        continue

                    await self._random_delay(1, 2)

        except Exception as e:
            logger.error(f"[reddit] Search failed: {e}")

        logger.info(f"[reddit] Found {len(results)} images")
        self._log_result(len(results), len(results) > 0)
        return results[:30]

    async def close(self):
        pass
