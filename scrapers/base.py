"""
Base Scraper Adapter - Abstract class for all engine scrapers
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict
import asyncio
import random
import logging

logger = logging.getLogger(__name__)

@dataclass
class SearchResult:
    """Single search result from an engine"""
    url: str
    source_url: str
    title: str
    engine: str
    thumbnail_url: Optional[str] = None
    metadata: Optional[Dict] = None

class BaseScraper(ABC):
    """Abstract base class for reverse image search scrapers"""
    
    def __init__(self):
        self.engine_name = "unknown"
        self.last_query_time = 0
        self.cooldown = 3.0  # seconds between queries
    
    @abstractmethod
    async def search(self, image_path: str) -> List[SearchResult]:
        """Search for image using this engine"""
        pass
    
    async def _random_delay(self, min_sec: float = 2.0, max_sec: float = 6.0):
        """Random delay to appear human"""
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)
    
    def _get_random_ua(self) -> str:
        """Get random user agent"""
        from app.config import config
        return random.choice(config.USER_AGENTS)
    
    def _log_result(self, result_count: int, success: bool, error: str = None):
        """Log search result"""
        status = "success" if success else "failed"
        logger.info(f"[{self.engine_name}] {status}: {result_count} results")
        if error:
            logger.warning(f"[{self.engine_name}] Error: {error}")
