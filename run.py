"""
OSINT Face Search Tool - Desktop Application
Reverse image search aggregator with local face verification
"""
import os
import sys
import webbrowser
import threading
import uvicorn
from pathlib import Path

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
CACHE_DIR = BASE_DIR / "cache"
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"

for d in [UPLOAD_DIR, CACHE_DIR, DATA_DIR]:
    d.mkdir(exist_ok=True)

def open_browser():
    """Open browser after server starts"""
    import time
    time.sleep(2)
    webbrowser.open("http://localhost:8000")

def main():
    print("=" * 60)
    print("  OSINT FACE SEARCH TOOL")
    print("  Reverse Image Search + Local Face Verification")
    print("=" * 60)
    print()
    print("  Starting server on http://localhost:8000")
    print("  Browser will open automatically...")
    print("  Press Ctrl+C to stop")
    print()
    
    threading.Thread(target=open_browser, daemon=True).start()
    
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()
