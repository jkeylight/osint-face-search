"""
Image hashing utilities — SHA-256 (exact identity) + DCT perceptual hash
(near-duplicate detection) implemented with numpy + PIL only.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image

try:  # cv2 is optional for these helpers
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------- pHash

def _dct1d(block: np.ndarray) -> np.ndarray:
    """Type-II DCT along the last axis (sufficient, dependency free)."""
    n = block.shape[-1]
    k = np.arange(n).reshape((1,) * (block.ndim - 1) + (n,))
    x = np.arange(n).reshape((1,) * (block.ndim - 1) + (n,))
    cos = np.cos(np.pi * (2 * x + 1) * k / (2 * n))
    scale = np.where(k == 0, np.sqrt(0.5), 1.0)
    return 2.0 * (block * cos).sum(axis=-1) * scale


def phash_from_pil(img: Image.Image, hash_size: int = 16) -> str:
    """Perceptual hash as fixed-width hex string (16x16 => 256 bits)."""
    g = img.convert("L").resize((hash_size, hash_size), Image.LANCZOS)
    arr = np.asarray(g, dtype=np.float64)
    # DCT on rows then on columns
    rows = _dct1d(arr)
    coeffs = _dct1d(rows.T).T
    # Use the top-left (excluding DC) low-frequency block
    low = coeffs[:8, :8]
    flat = low.flatten()
    # Median of AC coefficients (skip DC term)
    ac = np.concatenate([flat[:1], flat[1:]])
    median = np.median(ac[1:])
    bits = ac > median
    return "".join("1" if b else "0" for b in bits)


def phash_from_array(bgr: np.ndarray) -> Optional[str]:
    if bgr is None or bgr.size == 0:
        return None
    try:
        rgb = bgr[:, :, ::-1] if bgr.ndim == 3 and bgr.shape[2] == 3 else bgr
        img = Image.fromarray(np.ascontiguousarray(rgb))
        return phash_from_pil(img)
    except Exception:
        return None


def phash_from_bytes(data: bytes) -> Optional[str]:
    try:
        img = Image.open(io.BytesIO(data))
        return phash_from_pil(img)
    except Exception:
        return None


def phash_hex_to_bits(value: str) -> Optional[np.ndarray]:
    try:
        return np.fromiter((c == "1" for c in value), dtype=bool, count=len(value))
    except Exception:
        return None


def phash_distance(a: str, b: str) -> Optional[int]:
    """Hamming distance between two perceptual hashes (lower = more similar)."""
    if not a or not b or len(a) != len(b):
        return None
    return sum(1 for x, y in zip(a, b) if x != y)


def is_near_duplicate(a: Optional[str], b: Optional[str], threshold: int = 12) -> bool:
    if not a or not b:
        return False
    d = phash_distance(a, b)
    return d is not None and d <= threshold


# ------------------------------------------------------------------ sniffing

_MAGIC: Tuple[Tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"BM", "bmp"),
    (b"\x00\x00\x01\x00", "ico"),
)


def sniff_image_format(data: bytes) -> Optional[str]:
    """Return canonical format name if the bytes look like a supported image."""
    if not data or len(data) < 12:
        return None
    for magic, fmt in _MAGIC:
        if data.startswith(magic):
            return fmt
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None

