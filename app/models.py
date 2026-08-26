"""
Model manager — locates / downloads the OpenCV-Zoo ONNX models.

Download sources are tried in order:
  1. GitHub release assets (fast, works on normal networks)
  2. GitHub codeload tarball streaming (works on restricted networks)

Models: YuNet face detector (~230 KB) + SFace recognizer (~37 MB).
"""
from __future__ import annotations

import logging
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        "YuNet face detector",
        "https://github.com/opencv/opencv_zoo/releases/download/1.0.0/face_detection_yunet_2023mar.onnx",
    ),
    "face_recognition_sface_2021dec.onnx": (
        "SFace recognition model",
        "https://github.com/opencv/opencv_zoo/releases/download/1.0.0/face_recognition_sface_2021dec.onnx",
    ),
}

CODELOAD_URL = "https://codeload.github.com/opencv/opencv_zoo/tar.gz/refs/heads/main"


def _url_open(url: str, timeout: float = 60.0):
    req = Request(url, headers={"User-Agent": "osint-face-search/2.0"})
    return urlopen(req, timeout=timeout)


def download_file(url: str, dest: Path, timeout: float = 240.0) -> bool:
    try:
        with _url_open(url, timeout=timeout) as resp, open(dest.with_suffix(dest.suffix + ".part"), "wb") as fh:
            shutil.copyfileobj(resp, fh, length=1 << 20)
        dest.with_suffix(dest.suffix + ".part").replace(dest)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("Model download failed from %s: %s", url, e)
        try:
            dest.with_suffix(dest.suffix + ".part").unlink(missing_ok=True)
        except Exception:
            pass
        return False


def _download_from_codeload(dest_dir: Path, names: list[str]) -> bool:
    """Stream the opencv_zoo tarball and pull out just the model files."""
    import gzip

    wanted = {f"opencv_zoo-main/models/{n}": n for n in names}
    try:
        with _url_open(CODELOAD_URL, timeout=300) as resp:
            with tarfile.open(fileobj=gzip.open(resp, "rb"), mode="r|") as tf:
                for member in tf:
                    if member.name in wanted:
                        extracted = tf.extractfile(member)
                        if extracted is None:
                            continue
                        out = dest_dir / wanted[member.name]
                        with open(out.with_suffix(out.suffix + ".part"), "wb") as fh:
                            shutil.copyfileobj(extracted, fh, length=1 << 20)
                        out.with_suffix(out.suffix + ".part").replace(out)
                        wanted.pop(member.name)
                        logger.info("Extracted model %s", out.name)
                    if not wanted:
                        return True
        return not wanted
    except Exception as e:  # noqa: BLE001
        logger.warning("Codeload model fetch failed: %s", e)
        return False


def ensure_models(model_dir: Path, auto_download: bool = True) -> dict[str, bool]:
    """Return {model_filename: present}. Downloads missing ones when allowed."""
    status = {name: (model_dir / name).exists() for name in MODELS}
    missing = [n for n, ok in status.items() if not ok]
    if not missing or not auto_download:
        return status

    model_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading missing models: %s", ", ".join(missing))

    for name in missing:
        url = MODELS[name][1]
        if download_file(url, model_dir / name):
            status[name] = True

    still_missing = [n for n, ok in status.items() if not ok]
    if still_missing:
        if _download_from_codeload(model_dir, still_missing):
            for n in still_missing:
                status[n] = True

    return status


def model_status(model_dir: Path) -> dict:
    """Human-readable status for the diagnostics UI."""
    out = {}
    for name, (label, url) in MODELS.items():
        p = model_dir / name
        out[name] = {
            "label": label,
            "present": p.exists(),
            "size": p.stat().st_size if p.exists() else 0,
            "url": url,
        }
    return out
