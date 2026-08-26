"""
OSINT Face Search — entry point.

Usage:
    python run.py                 # serve on 0.0.0.0:8000
    OSINT_PORT=9000 python run.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app.config import config  # noqa: E402


def main() -> None:
    import uvicorn

    print("=" * 62)
    print("  OSINT FACE SEARCH  v2.0")
    print("  Reverse image search + local face verification")
    print("=" * 62)
    print(f"  URL      http://localhost:{config.PORT}")
    print(f"  Models   {config.MODEL_DIR}")
    print("  Stop     Ctrl+C")
    print()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    uvicorn.run(
        "app.main:app",
        host=config.HOST,
        port=config.PORT,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
