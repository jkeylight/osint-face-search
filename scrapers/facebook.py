"""
Facebook Scraper - using facebook-scraper for public pages
"""
import logging
from typing import List

from scrapers.base import BaseScraper, SearchResult

logger = logging.getLogger(__name__)


class FacebookScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.engine_name = "facebook"
        self.cooldown = 3.0

    async def search(self, image_path: str) -> List[SearchResult]:
        results = []
        try:
            from facebook_scraper import get_posts

            # Search public pages with photos
            pages = ["NatGeo", "BBC", "nytimes", "caborja1"]

            for page_name in pages[:3]:
                try:
                    for post in get_posts(page_name, pages=2, extra_info=True, timeout=10):
                        # Get images from post
                        images = post.get("images", [])
                        if isinstance(images, str):
                            images = [images]

                        for img_url in images:
                            if img_url and img_url.startswith("http"):
                                results.append(SearchResult(
                                    url=img_url,
                                    source_url=post.get("post_url", f"https://facebook.com/{page_name}"),
                                    title=post.get("text", "")[:100] if post.get("text") else "",
                                    engine="facebook",
                                    thumbnail_url=img_url
                                ))

                        # Also check for image key
                        if post.get("image"):
                            img_url = post["image"]
                            if img_url and img_url.startswith("http"):
                                results.append(SearchResult(
                                    url=img_url,
                                    source_url=post.get("post_url", f"https://facebook.com/{page_name}"),
                                    title=post.get("text", "")[:100] if post.get("text") else "",
                                    engine="facebook",
                                    thumbnail_url=img_url
                                ))

                except Exception as e:
                    logger.warning(f"[facebook] Page {page_name} failed: {e}")
                    continue

        except ImportError:
            logger.error("[facebook] facebook-scraper not installed")
        except Exception as e:
            logger.error(f"[facebook] Search failed: {e}")

        logger.info(f"[facebook] Found {len(results)} images")
        self._log_result(len(results), len(results) > 0)
        return results[:20]

    async def close(self):
        pass
