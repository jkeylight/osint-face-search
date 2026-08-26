"""
Utility functions - Hashing, storage, anti-block
"""
import hashlib
import imagehash
from PIL import Image
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

def compute_sha256(file_path: str) -> str:
    """Compute SHA-256 hash of file"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()

def compute_phash(file_path: str) -> Optional[str]:
    """Compute perceptual hash of image"""
    try:
        img = Image.open(file_path)
        phash = imagehash.phash(img)
        return str(phash)
    except Exception as e:
        logger.error(f"Failed to compute pHash: {e}")
        return None

def is_duplicate(phash1: str, phash2: str, threshold: int = 8) -> bool:
    """Check if two images are near-duplicates based on pHash"""
    try:
        h1 = imagehash.hex_to_hash(phash1)
        h2 = imagehash.hex_to_hash(phash2)
        return (h1 - h2) < threshold
    except:
        return False

def get_image_info(file_path: str) -> dict:
    """Get image dimensions and size"""
    try:
        img = Image.open(file_path)
        return {
            "width": img.width,
            "height": img.height,
            "format": img.format,
            "mode": img.mode
        }
    except:
        return {}

def get_source_weight(url: str) -> float:
    """Get source weight based on domain"""
    from app.config import config
    
    domain = ""
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).hostname or ""
    except:
        pass
    
    domain = domain.lower()
    
    # News sites
    if any(x in domain for x in ['bbc', 'cnn', 'reuters', 'apnews', 'nytimes', 
                                   'washingtonpost', 'guardian', 'aljazeera']):
        return config.SOURCE_WEIGHTS["news"]
    
    # Official sites
    if any(x in domain for x in ['linkedin', 'company', 'official', 'gov', 'edu']):
        return config.SOURCE_WEIGHTS["official"]
    
    # Social media
    if any(x in domain for x in ['facebook', 'instagram', 'twitter', 'tiktok', 
                                   'youtube', 'reddit', 'pinterest']):
        return config.SOURCE_WEIGHTS["social"]
    
    # Forums
    if any(x in domain for x in ['forum', 'board', 'community', 'stack', 'quora']):
        return config.SOURCE_WEIGHTS["forums"]
    
    return config.SOURCE_WEIGHTS["unknown"]
