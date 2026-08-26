"""Image IO helpers: normalize, thumbnail, bbox overlay drawing."""
from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Optional, Sequence, Tuple

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


def clamp_bbox(bbox: Sequence[float], width: int, height: int) -> Tuple[int, int, int, int]:
    x1, y1, x2, y2 = [float(v) for v in bbox[:4]]
    x1, x2 = max(0, min(x1, x2)), min(width, max(x1, x2))
    y1, y2 = max(0, min(y1, y2)), min(height, max(y1, y2))
    return int(x1), int(y1), int(x2), int(y2)


def expand_bbox(
    bbox: Sequence[float], width: int, height: int, pad: float = 0.3
) -> Tuple[int, int, int, int]:
    """Expand a bbox by `pad` proportionally, clamped to image bounds."""
    x1, y1, x2, y2 = clamp_bbox(bbox, width, height)
    w, h = x2 - x1, y2 - y1
    px, py = int(w * pad), int(h * pad)
    return (
        max(0, x1 - px),
        max(0, y1 - py),
        min(width, x2 + px),
        min(height, y2 + py),
    )


def crop_bbox(img: np.ndarray, bbox: Sequence[float], pad: float = 0.0) -> np.ndarray:
    h, w = img.shape[:2]
    x1, y1, x2, y2 = expand_bbox(bbox, w, h, pad) if pad else clamp_bbox(bbox, w, h)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return np.zeros((0, 0, 3), dtype=np.uint8)
    return img[y1:y2, x1:x2]


def normalize_image(img: np.ndarray, max_edge: int = 1600, jpeg_quality: int = 90) -> bytes:
    """Resize so the longest edge <= max_edge and re-encode as JPEG bytes."""
    h, w = img.shape[:2]
    scale = min(1.0, max_edge / max(h, w)) if max(h, w) else 1.0
    if scale < 1.0:
        img = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()


def thumbnail_bytes(img: np.ndarray, max_edge: int = 480, jpeg_quality: int = 82) -> Optional[bytes]:
    try:
        return normalize_image(img, max_edge=max_edge, jpeg_quality=jpeg_quality)
    except Exception:
        return None


def draw_face_overlay(
    img: np.ndarray,
    boxes: Sequence[Sequence[float]],
    color: Tuple[int, int, int] = (80, 220, 255),
    labels: Optional[Sequence[str]] = None,
    thickness: int = 2,
) -> np.ndarray:
    """Return a copy of the image with bounding boxes (and optional labels) drawn."""
    out = img.copy()
    for i, box in enumerate(boxes):
        h, w = out.shape[:2]
        x1, y1, x2, y2 = clamp_bbox(box, w, h)
        if x2 - x1 < 2 or y2 - y1 < 2:
            continue
        cv2.rectangle(out, (x1, y1), (x2, y2), color, thickness)
        label = labels[i] if labels and i < len(labels) else None
        if label:
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            ty = y1 - 6 if y1 - th - 6 > 0 else y2 + th + 6
            cv2.rectangle(out, (x1, ty - th - 4), (x1 + tw + 6, ty + 2), (0, 0, 0), -1)
            cv2.putText(out, label, (x1 + 3, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    return out


def save_image_bytes(path: str | Path, data: bytes) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(data)


def safe_rel_path(base: Path, rel: str) -> Optional[Path]:
    """Resolve rel under base, refusing traversal outside base."""
    try:
        p = (base / rel).resolve()
        base_r = base.resolve()
        if p == base_r or base_r in p.parents:
            return p
    except Exception:
        pass
    return None


def decode_image_bytes(data: bytes):
    """Decode image bytes to a BGR numpy array; returns None on failure."""
    if cv2 is None or data is None or len(data) < 12:
        return None
    from app.utils.hashing import sniff_image_format

    if sniff_image_format(data) is None:
        return None
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


# Maps BASE_DIR-relative paths to the URL mounts defined in app.main
_MEDIA_MOUNTS = (
    ("uploads/", "/media/uploads/"),
    ("data/candidates/", "/media/candidates/"),
    ("data/gallery/", "/media/gallery/"),
    ("cache/", "/media/cache/"),
    ("demo/", "/media/demo/"),
)


def media_url(rel: str) -> str:
    """Convert a BASE_DIR-relative file path to its served /media/ URL."""
    if not rel:
        return ""
    rel = str(rel).replace("\\", "/").lstrip("/")
    for prefix, mount in _MEDIA_MOUNTS:
        if rel.startswith(prefix):
            return mount + rel[len(prefix):]
    return "/media/" + rel
