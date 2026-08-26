"""
Database operations - SQLite for metadata, hashes, logs
"""
import sqlite3
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)

class Database:
    """SQLite database for OSINT Face Search"""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    sha256 VARCHAR(64) NOT NULL,
                    phash VARCHAR(16),
                    file_path TEXT,
                    file_size INTEGER,
                    width INTEGER,
                    height INTEGER,
                    source_domain TEXT,
                    source_url TEXT,
                    page_title TEXT,
                    crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS faces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER REFERENCES images(id),
                    bbox_x1 INTEGER,
                    bbox_y1 INTEGER,
                    bbox_x2 INTEGER,
                    bbox_y2 INTEGER,
                    embedding BLOB NOT NULL,
                    quality_score REAL,
                    confidence REAL,
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_sha256 VARCHAR(64) NOT NULL,
                    query_image_path TEXT,
                    engine TEXT NOT NULL,
                    result_url TEXT,
                    result_sha256 VARCHAR(64),
                    similarity REAL,
                    source_weight REAL,
                    final_score REAL,
                    rank INTEGER,
                    searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_sha256 VARCHAR(64) NOT NULL,
                    result_url TEXT NOT NULL,
                    is_correct BOOLEAN NOT NULL,
                    noted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS cache (
                    query_hash VARCHAR(64) PRIMARY KEY,
                    response TEXT NOT NULL,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS engine_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    engine TEXT NOT NULL,
                    status TEXT NOT NULL,
                    url_count INTEGER,
                    error_message TEXT,
                    queried_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE INDEX IF NOT EXISTS idx_images_sha256 ON images(sha256);
                CREATE INDEX IF NOT EXISTS idx_images_phash ON images(phash);
                CREATE INDEX IF NOT EXISTS idx_faces_image_id ON faces(image_id);
                CREATE INDEX IF NOT EXISTS idx_searches_query ON searches(query_sha256);
            """)
    
    def compute_sha256(self, file_path: str) -> str:
        """Compute SHA-256 hash of file"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def insert_image(self, url: str, sha256: str, file_path: str = None,
                     source_url: str = None, page_title: str = None,
                     phash: str = None, file_size: int = None) -> int:
        """Insert image record"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT OR IGNORE INTO images 
                (url, sha256, file_path, source_url, page_title, phash, file_size, source_domain)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                url, sha256, file_path, source_url, page_title, phash, file_size,
                Path(url).hostname if url else None
            ))
            return cursor.lastrowid
    
    def insert_face(self, image_id: int, bbox: List[int], embedding, 
                    quality_score: float = None, confidence: float = None) -> int:
        """Insert face record with embedding"""
        import numpy as np
        
        # Convert embedding to bytes
        embedding_bytes = embedding.tobytes() if isinstance(embedding, np.ndarray) else embedding
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO faces 
                (image_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, embedding, quality_score, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                image_id, bbox[0], bbox[1], bbox[2], bbox[3],
                embedding_bytes, quality_score, confidence
            ))
            return cursor.lastrowid
    
    def insert_search(self, query_sha256: str, engine: str, result_url: str,
                      similarity: float, source_weight: float = 1.0,
                      final_score: float = None, rank: int = None) -> int:
        """Insert search result"""
        if final_score is None:
            final_score = similarity * source_weight
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO searches 
                (query_sha256, engine, result_url, similarity, source_weight, final_score, rank)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (query_sha256, engine, result_url, similarity, source_weight, final_score, rank))
            return cursor.lastrowid
    
    def insert_feedback(self, query_sha256: str, result_url: str, is_correct: bool) -> int:
        """Insert user feedback"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO feedback (query_sha256, result_url, is_correct)
                VALUES (?, ?, ?)
            """, (query_sha256, result_url, is_correct))
            return cursor.lastrowid
    
    def get_cached_result(self, query_hash: str) -> Optional[Dict]:
        """Get cached search result"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT response FROM cache WHERE query_hash = ?", (query_hash,)
            ).fetchone()
            if row:
                return json.loads(row[0])
            return None
    
    def set_cached_result(self, query_hash: str, response: Dict):
        """Cache search result"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO cache (query_hash, response)
                VALUES (?, ?)
            """, (query_hash, json.dumps(response)))
    
    def log_engine_stat(self, engine: str, status: str, url_count: int = 0,
                       error_message: str = None):
        """Log engine statistics"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO engine_stats (engine, status, url_count, error_message)
                VALUES (?, ?, ?, ?)
            """, (engine, status, url_count, error_message))
    
    def get_search_history(self, limit: int = 50) -> List[Dict]:
        """Get recent search history"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM searches 
                ORDER BY searched_at DESC 
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(row) for row in rows]
    
    def get_stats(self) -> Dict:
        """Get database statistics"""
        with sqlite3.connect(self.db_path) as conn:
            return {
                "total_images": conn.execute("SELECT COUNT(*) FROM images").fetchone()[0],
                "total_faces": conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0],
                "total_searches": conn.execute("SELECT COUNT(*) FROM searches").fetchone()[0],
                "total_feedback": conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0],
            }
