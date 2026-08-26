"""
Application configuration
"""
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List

BASE_DIR = Path(__file__).parent.parent

@dataclass
class Config:
    # Paths
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    CACHE_DIR: Path = BASE_DIR / "cache"
    DATA_DIR: Path = BASE_DIR / "data"
    STATIC_DIR: Path = BASE_DIR / "static"
    DB_PATH: Path = BASE_DIR / "data" / "osint.db"
    FAISS_INDEX: Path = BASE_DIR / "data" / "faiss.index"
    
    # Server
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    
    # Face Recognition
    FACE_MODEL: str = "buffalo_l"
    EMBEDDING_DIM: int = 512
    MIN_FACE_SIZE: int = 50
    QUALITY_THRESHOLD: float = 0.3
    
    # Thresholds (dynamic based on quality)
    THRESHOLD_HIGH: float = 0.75
    THRESHOLD_MEDIUM: float = 0.65
    THRESHOLD_LOW: float = 0.50
    
    # Image constraints
    MIN_IMAGE_SIZE: int = 50  # pixels
    MAX_IMAGE_SIZE: int = 10 * 1024 * 1024  # 10 MB
    
    # Scraping
    MAX_CONCURRENT_DOWNLOADS: int = 15
    RESULTS_PER_ENGINE: int = 20
    MIN_DELAY: float = 2.0
    MAX_DELAY: float = 6.0
    
    # Storage
    MAX_STORAGE_GB: float = 10.0
    
    # Source weights for ranking
    SOURCE_WEIGHTS: Dict[str, float] = None
    
    # User agents for rotation
    USER_AGENTS: List[str] = None
    
    def __post_init__(self):
        if self.SOURCE_WEIGHTS is None:
            self.SOURCE_WEIGHTS = {
                "news": 1.0,
                "official": 0.9,
                "social": 0.7,
                "forums": 0.5,
                "unknown": 0.3
            }
        
        if self.USER_AGENTS is None:
            self.USER_AGENTS = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            ]
        
        # Create directories
        for d in [self.UPLOAD_DIR, self.CACHE_DIR, self.DATA_DIR]:
            d.mkdir(exist_ok=True)

config = Config()
