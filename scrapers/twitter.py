"""
Twitter/X Scraper - using snscrape for public tweets with images
"""
import logging
from typing import List

from scrapers.base import BaseScraper, SearchResult

logger = logging.getLogger(__name__)


class TwitterScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.engine_name = "twitter"
        self.cooldown = 3.0

    async def search(self, image_path: str) -> List[SearchResult]:
        results = []
        try:
            import snscrape.modules.twitter as sntwitter

            # Search for recent tweets with images
            query = "filter:images -filter:retweets"
            logger.info(f"[twitter] Searching: {query}")

            for i, tweet in enumerate(sntwitter.TwitterSearchScraper(query).get_items()):
                if i >= 30:
                    break

                try:
                    # Get media URLs
                    if hasattr(tweet, 'media') and tweet.media:
                        for media in tweet.media:
                            if hasattr(media, 'fullUrl'):
                                url = media.fullUrl
                            elif hasattr(media, 'mediaUrl'):
                                url = media.mediaUrl
                            else:
                                continue

                            if url and 'pbs.twimg.com' in url:
                                results.append(SearchResult(
                                    url=url,
                                    source_url=f"https://twitter.com/{tweet.user.username}/status/{tweet.id}",
                                    title=tweet.rawContent[:100] if tweet.rawContent else "",
                                    engine="twitter",
                                    thumbnail_url=url
                                ))
                except Exception as e:
                    continue

        except ImportError:
            logger.error("[twitter] snscrape not installed")
        except Exception as e:
            logger.error(f"[twitter] Search failed: {e}")

        logger.info(f"[twitter] Found {len(results)} images")
        self._log_result(len(results), len(results) > 0)
        return results[:20]

    async def close(self):
        pass
