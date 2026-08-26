"""Shared fixtures for the test suite."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import config  # noqa: E402

DEMO = ROOT / "demo"


@pytest.fixture(scope="session")
def demo_images():
    imgs = {p.name: p.read_bytes() for p in DEMO.glob("*.jpg")}
    if not imgs:
        pytest.skip("demo images not bundled")
    return imgs


@pytest.fixture(scope="session")
def face_engine():
    from app.face_engine import FaceEngine
    eng = FaceEngine()
    if not eng.available:
        pytest.skip("face models unavailable")
    return eng
