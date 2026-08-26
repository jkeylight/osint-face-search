#!/usr/bin/env python3
"""Download the OpenCV-Zoo face models (YuNet detector + SFace recognizer)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import ensure_models, model_status  # noqa: E402
from app.config import config  # noqa: E402


def main() -> int:
    status = ensure_models(config.MODEL_DIR, auto_download=True)
    ok = True
    for name, info in model_status(config.MODEL_DIR).items():
        mark = "OK " if info["present"] else "MISSING"
        print(f"  [{mark}] {info['label']:<28} {name}")
        ok = ok and info["present"]
    if not ok:
        print("\nSome models failed to download. Check your network or fetch manually:")
        for name, info in model_status(config.MODEL_DIR).items():
            if not info["present"]:
                print(f"  curl -L '{info['url']}' -o models/{name}")
        return 1
    print("\nAll models present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
