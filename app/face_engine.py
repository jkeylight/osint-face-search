"""
Face engine — multi-backend face detection + recognition.

Backends (tried in configured order, first available wins):
  * insightface : ArcFace embeddings via InsightFace (best accuracy;
                  requires `pip install insightface onnxruntime` + model pack)
  * opencv      : YuNet detector + SFace recognizer from OpenCV Zoo
                  (bundled with this app, always available once models exist)

All heavy calls are blocking CPU work — callers should wrap them in
`asyncio.to_thread` (the pipeline does).
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

from app.config import config
from app.utils.images import clamp_bbox

logger = logging.getLogger(__name__)


@dataclass
class Face:
    """A detected face with its embedding."""
    bbox: tuple[int, int, int, int]           # x1, y1, x2, y2 (pixels)
    det_score: float                          # detector confidence 0..1
    embedding: Optional[np.ndarray]           # L2-normalised float32
    quality: float = 0.0                      # heuristic quality 0..1
    backend: str = ""

    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]


class BaseBackend:
    name: str = "base"
    dim: int = 0

    def load(self) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def detect(self, image_bgr: np.ndarray, max_faces: int = 8) -> List[Face]:
        raise NotImplementedError


# --------------------------------------------------------------------- OpenCV

class OpenCVBackend(BaseBackend):
    """YuNet (detection) + SFace (recognition) via cv2.FaceDetectorYN / FaceRecognizerSF."""
    name = "opencv"
    dim = 128

    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self.detector = None
        self.recognizer = None

    def load(self) -> bool:
        try:
            import cv2  # noqa: F401  (fail fast if opencv missing)
        except Exception as e:
            logger.info("[opencv] OpenCV not importable: %s", e)
            return False

        det_path = self.model_dir / config.YUNET_MODEL
        rec_path = self.model_dir / config.SFACE_MODEL
        if not det_path.exists() or not rec_path.exists():
            logger.info("[opencv] models missing in %s", self.model_dir)
            return False

        try:
            import cv2
            self.detector = cv2.FaceDetectorYN.create(
                str(det_path), "", (320, 320), score_threshold=config.DET_SCORE_THRESHOLD
            )
            self.recognizer = cv2.FaceRecognizerSF.create(str(rec_path), "")
            logger.info("[opencv] YuNet + SFace loaded from %s", self.model_dir)
            return True
        except Exception as e:
            logger.warning("[opencv] failed to initialise: %s", e)
            self.detector = self.recognizer = None
            return False

    def detect(self, image_bgr: np.ndarray, max_faces: int = 8) -> List[Face]:
        import cv2

        if self.detector is None or image_bgr is None or image_bgr.size == 0:
            return []
        h, w = image_bgr.shape[:2]
        # YuNet is more reliable on reasonably sized inputs
        scale = 1.0
        work = image_bgr
        if max(h, w) > 1600:
            scale = 1600.0 / max(h, w)
            work = cv2.resize(image_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        elif max(h, w) < 200:
            scale = 2.0
            work = cv2.resize(image_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

        self.detector.setInputSize((work.shape[1], work.shape[0]))
        _, faces_arr = self.detector.detect(work)
        faces: List[Face] = []
        if faces_arr is None:
            return []

        # YuNet row layout: [x, y, w, h, lm0..lm9 (10), score]  (15 cols)
        for row in faces_arr[: max_faces * 3]:
            score = float(row[14]) if len(row) > 14 else float(row[4])
            if score < config.DET_SCORE_THRESHOLD:
                continue
            x, y, bw, bh = (float(v) for v in row[:4])
            if scale != 1.0:
                row = row.astype(np.float32).copy()
                row[:14] /= scale
                x, y, bw, bh = row[0], row[1], row[2], row[3]
            bbox = clamp_bbox((x, y, x + bw, y + bh), w, h)
            if bbox[2] - bbox[0] < 8 or bbox[3] - bbox[1] < 8:
                continue
            embedding = None
            if self.recognizer is not None:
                try:
                    # alignCrop expects the full 15-value row in image coords
                    aligned = self.recognizer.alignCrop(image_bgr, row)
                    embedding = self.recognizer.feature(aligned).flatten().astype(np.float32)
                except Exception:
                    embedding = None
            quality = assess_face_quality(image_bgr, bbox)
            faces.append(
                Face(bbox=bbox, det_score=score, embedding=embedding,
                     quality=quality, backend=self.name)
            )
            if len(faces) >= max_faces:
                break
        faces.sort(key=lambda f: (f.det_score, f.width * f.height), reverse=True)
        return faces


# ----------------------------------------------------------------- InsightFace

class InsightFaceBackend(BaseBackend):
    """InsightFace FaceAnalysis (SCRFD + ArcFace). Optional, best accuracy."""
    name = "insightface"
    dim = 512

    def __init__(self, model_name: str = "buffalo_l"):
        self.model_name = model_name
        self.app = None

    def load(self) -> bool:
        try:
            from insightface.app import FaceAnalysis
        except Exception as e:
            logger.info("[insightface] not importable: %s", e)
            return False
        try:
            self.app = FaceAnalysis(name=self.model_name, providers=["CPUExecutionProvider"])
            self.app.prepare(ctx_id=0, det_size=(640, 640))
            logger.info("[insightface] %s loaded", self.model_name)
            return True
        except Exception as e:
            logger.warning("[insightface] failed to load model: %s", e)
            self.app = None
            return False

    def detect(self, image_bgr: np.ndarray, max_faces: int = 8) -> List[Face]:
        if self.app is None or image_bgr is None or image_bgr.size == 0:
            return []
        try:
            h, w = image_bgr.shape[:2]
            raw = self.app.get(image_bgr)
        except Exception as e:
            logger.warning("[insightface] detect failed: %s", e)
            return []
        faces: List[Face] = []
        for f in raw[: max_faces * 2]:
            score = min(1.0, float(getattr(f, "det_score", 0.0) or 0.0))
            if score < config.DET_SCORE_THRESHOLD:
                continue
            bbox = clamp_bbox(f.bbox.astype(float).tolist(), w, h)
            emb = getattr(f, "normed_embedding", None)
            emb = np.asarray(emb, dtype=np.float32) if emb is not None else None
            faces.append(
                Face(bbox=bbox, det_score=score, embedding=emb,
                     quality=assess_face_quality(image_bgr, bbox), backend=self.name)
            )
            if len(faces) >= max_faces:
                break
        faces.sort(key=lambda f: (f.det_score, f.width * f.height), reverse=True)
        return faces


# ------------------------------------------------------------------ shared QA

def assess_face_quality(image_bgr: np.ndarray, bbox: Sequence[int]) -> float:
    """Heuristic 0..1 face quality: size + sharpness + exposure."""
    try:
        import cv2
        x1, y1, x2, y2 = bbox
        region = image_bgr[y1:y2, x1:x2]
        if region is None or region.size == 0:
            return 0.0
        h_img, w_img = image_bgr.shape[:2]
        rel_area = (x2 - x1) * (y2 - y1) / float(max(1, w_img * h_img))
        size_score = min(1.0, rel_area / 0.04)                     # >=4% of frame is fine
        px = min(region.shape[0], region.shape[1])
        size_score *= min(1.0, px / 64.0) if px < 64 else 1.0       # penalise tiny crops
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        blur = cv2.Laplacian(gray, cv2.CV_64F).var()
        sharp = min(1.0, blur / 220.0)
        bright = 1.0 - min(1.0, abs(float(np.mean(gray)) - 120.0) / 120.0)
        return float(0.45 * size_score + 0.35 * sharp + 0.20 * bright)
    except Exception:
        return 0.0


# -------------------------------------------------------------------- engine

def cosine(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> Optional[float]:
    if a is None or b is None:
        return None
    a = np.asarray(a, dtype=np.float64).flatten()
    b = np.asarray(b, dtype=np.float64).flatten()
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return None
    return float(np.dot(a / na, b / nb))


class FaceEngine:
    """Facade that selects the best available backend at first use (thread-safe)."""

    _BACKEND_CLASSES = {
        "insightface": InsightFaceBackend,
        "opencv": OpenCVBackend,
    }

    def __init__(self):
        self._lock = threading.Lock()
        self._backend: Optional[BaseBackend] = None
        self._init_error: Optional[str] = None
        self._tried = False

    # -- lifecycle ------------------------------------------------------------
    def _ensure(self) -> Optional[BaseBackend]:
        with self._lock:
            if self._tried:
                return self._backend
            self._tried = True
            from app.models import ensure_models
            try:
                ensure_models(config.MODEL_DIR, auto_download=config.AUTO_DOWNLOAD_MODELS)
            except Exception as e:  # noqa: BLE001
                logger.warning("Model auto-download failed: %s", e)
            for key in config.FACE_BACKENDS:
                key = key.strip().lower()
                cls = self._BACKEND_CLASSES.get(key)
                if cls is None:
                    continue
                try:
                    backend = (
                        cls() if key == "insightface" else cls(config.MODEL_DIR)
                    )
                    t0 = time.time()
                    if backend.load():
                        self._backend = backend
                        logger.info("Face backend active: %s (%.1fs)", key, time.time() - t0)
                        break
                except Exception as e:  # noqa: BLE001
                    logger.warning("Backend %s init error: %s", key, e)
            if self._backend is None:
                self._init_error = (
                    "No face backend available. Install OpenCV models "
                    "(scripts/download_models.py) or `pip install insightface onnxruntime`."
                )
                logger.warning(self._init_error)
            return self._backend

    def reset(self) -> None:
        with self._lock:
            self._backend = None
            self._tried = False
            self._init_error = None

    # -- info -----------------------------------------------------------------
    @property
    def backend_name(self) -> str:
        b = self._ensure()
        return b.name if b else "none"

    @property
    def available(self) -> bool:
        return self._ensure() is not None

    def info(self) -> dict:
        b = self._ensure()
        return {
            "active_backend": b.name if b else "none",
            "available": b is not None,
            "dim": b.dim if b else 0,
            "error": self._init_error,
            "configured_order": [k.strip() for k in config.FACE_BACKENDS],
        }

    # -- core ops ---------------------------------------------------------------
    def detect(self, image_bgr: np.ndarray, max_faces: Optional[int] = None) -> List[Face]:
        b = self._ensure()
        if b is None:
            return []
        try:
            return b.detect(image_bgr, max_faces or config.MAX_FACES_PER_IMAGE)
        except Exception as e:  # noqa: BLE001
            logger.warning("detect() failed: %s", e)
            return []

    def best_face(self, image_bgr: np.ndarray) -> Optional[Face]:
        faces = self.detect(image_bgr)
        if not faces:
            return None
        return max(faces, key=lambda f: (f.embedding is not None, f.quality, f.det_score))

    @staticmethod
    def similarity(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> Optional[float]:
        return cosine(a, b)

    @staticmethod
    def verdict_for(similarity: Optional[float]) -> str:
        """Map a cosine similarity to a verdict band."""
        if similarity is None:
            return "unknown"
        if similarity >= config.VERDICT_STRONG:
            return "strong"
        if similarity >= config.VERDICT_POSSIBLE:
            return "possible"
        if similarity >= config.VERDICT_WEAK:
            return "weak"
        return "none"

    @classmethod
    def confidence(cls, similarity: Optional[float]) -> float:
        """
        Calibrated 0..100 confidence for UI display.

        Cosine similarity for face embeddings is roughly in [-0.2, 0.9];
        we map the practically-interesting [0.0, 0.65] range onto 0-100 with
        a soft curve so verdict bands stay visually distinct.
        """
        if similarity is None:
            return 0.0
        x = max(0.0, min(0.65, similarity))
        return round(min(100.0, 100.0 * (x / 0.65) ** 1.15), 1)
