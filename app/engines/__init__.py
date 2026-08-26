"""
Engine registry — discovers all engine adapters and exposes metadata.

Engines are instantiated lazily; `get_engine(key)` returns a singleton.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from app.engines.base import BaseEngine

logger = logging.getLogger(__name__)

_ENGINE_CLASSES = {}


def _register(cls):
    _ENGINE_CLASSES[cls.meta.key] = cls
    return cls


def _load_all() -> None:
    # Import for side-effect registration (kept explicit for clarity)
    from app.engines.bing import BingEngine  # noqa: F401
    from app.engines.baidu import BaiduEngine  # noqa: F401
    from app.engines.fourchan import FourChanEngine  # noqa: F401
    from app.engines.google_lens import GoogleLensEngine  # noqa: F401
    from app.engines.reddit import RedditEngine  # noqa: F401
    from app.engines.saucenao import SauceNAOEngine  # noqa: F401
    from app.engines.tineye import TinEyeEngine  # noqa: F401
    from app.engines.yandex import YandexEngine  # noqa: F401

    for mod_cls in (BingEngine, BaiduEngine, FourChanEngine, GoogleLensEngine,
                    RedditEngine, SauceNAOEngine, TinEyeEngine, YandexEngine):
        _register(mod_cls)


_load_all()

_instances: Dict[str, BaseEngine] = {}


def get_engine(key: str) -> Optional[BaseEngine]:
    cls = _ENGINE_CLASSES.get(key)
    if cls is None:
        return None
    if key not in _instances:
        _instances[key] = cls()
    return _instances[key]


def all_engine_keys() -> List[str]:
    return list(_ENGINE_CLASSES.keys())


def registry_info() -> List[dict]:
    """Metadata for the UI, without instantiating engines."""
    out = []
    for key, cls in _ENGINE_CLASSES.items():
        m = cls.meta
        out.append({
            "key": m.key,
            "label": m.label,
            "category": m.category,
            "requires": m.requires,
            "description": m.description,
            "homepage": m.homepage,
        })
    return sorted(out, key=lambda e: (e["category"], e["label"]))
