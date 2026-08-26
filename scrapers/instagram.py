"""
Instagram Scraper - using instagrapi for public posts
"""
import logging
from typing import List

from scrapers.base import BaseScraper, SearchResult

logger = logging.getLogger(__name__)


class InstagramScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.engine_name = "instagram"
        self.cooldown = 3.0

    async def search(self, image_path: str) -> List[SearchResult]:
        results = []
        try:
            from instagrapi import Client

            cl = Client()
            # Use without login for public hashtag search
            # Note: Instagram limits unauthenticated access

            # Search recent posts by hashtags
            hashtags = ["face", "portrait", "selfie", "photo", "people"]

            for tag in hashtags[:3]:
                try:
                    medias = cl.hashtag_medias_recent(tag, amount=10)
                    for media in medias:
                        if media.media_type == 1:  # Photo
                            url = media.thumbnail_url or media.url
                            results.append(SearchResult(
                                url=url,
                                source_url=f"https://instagram.com/p/{media.code}/",
                                title=media.caption_text[:100] if media.caption_text else "",
                                engine="instagram",
                                thumbnail_url=url
                            ))
                        elif media.media_type == 8:  # Album
                            for resource in media.resources:
                                url = resource.thumbnail_url or resource.url
                                results.append(SearchResult(
                                    url=url,
                                    source_url=f"https://instagram.com/p/{media.code}/",
                                    title=media.caption_text[:100] if media.caption_text else "",
                                    engine="instagram",
                                    thumbnail_url=url
                                ))
                except Exception as e:
                    logger.warning(f"[instagram] Hashtag {tag} failed: {e}")
                    continue

        except ImportError:
            logger.error("[instagram] instagrapi not installed")
        except Exception as e:
            logger.error(f"[instagram] Search failed: {e}")

        logger.info(f"[instagram] Found {len(results)} images")
        self._log_result(len(results), len(results) > 0)
        return results[:20]

    async def close(self):
        pass
