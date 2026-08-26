"""
Desktop launcher — starts the OSINT Face Search server with NO console window
and opens it in your browser.

Used by the desktop shortcut created by `scripts/setup_desktop.py`
(`npm run setup-desktop`).  Behaviour:

  * if the server is already running  -> just open a browser tab and exit
  * otherwise                         -> start uvicorn in a background thread
                                         (hidden, logs to logs/desktop.log),
                                         wait until it answers, then open the
                                         browser
  * stop the server from the UI:      System view -> "Shut down server"
    (or kill this process)

Environment overrides:
    OSINT_PORT   port to prefer (default: first free port from 8000)
    OSINT_HOST   bind address    (default: 127.0.0.1 — localhost only)
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "desktop.log"

# pythonw.exe has no console: sys.stdout/stderr are None and any print() or
# unhandled stderr write would crash the process — redirect them to the log.
_log_file = open(LOG_PATH, "a", buffering=1, encoding="utf-8")
if sys.stdout is None:
    sys.stdout = _log_file
if sys.stderr is None:
    sys.stderr = _log_file

sys.path.insert(0, str(BASE_DIR))

log = logging.getLogger("desktop")


def _setup_logging() -> None:
    handler = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=1_000_000, backupCount=1, encoding="utf-8"
    )
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    handler.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    # uvicorn's default config logs to stderr, which does not exist under
    # pythonw — point every uvicorn logger at our file handler instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = [handler]
        lg.propagate = False
    logging.getLogger("uvicorn.access").setLevel(logging.CRITICAL)


LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"std": {"format": "%(asctime)s %(levelname)-7s %(name)s: %(message)s"}},
    "handlers": {"file": {"class": "logging.handlers.RotatingFileHandler",
                          "filename": str(LOG_PATH), "maxBytes": 1000000,
                          "backupCount": 1, "formatter": "std"}},
    "loggers": {
        "uvicorn": {"handlers": ["file"], "level": "WARNING", "propagate": False},
        "uvicorn.error": {"handlers": ["file"], "level": "WARNING", "propagate": False},
        "uvicorn.access": {"handlers": ["file"], "level": "CRITICAL", "propagate": False},
    },
    "root": {"handlers": ["file"], "level": "INFO"},
}


# ------------------------------------------------------------------ helpers

def port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def app_responds(host: str, port: int) -> bool:
    """True when *our* app answers on host:port."""
    base = "127.0.0.1" if host in ("0.0.0.0", "") else host
    try:
        with urllib.request.urlopen(
            f"http://{base}:{port}/api/stats", timeout=1.5
        ) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def find_free_port(preferred: int, host: str = "127.0.0.1",
                   scans: int = 20) -> int:
    if not port_open(host, preferred):
        return preferred
    for p in range(preferred + 1, preferred + 1 + scans):
        if not port_open(host, p):
            return p
    raise RuntimeError(f"No free port found in {preferred}-{preferred + scans}")


def open_browser(url: str) -> bool:
    try:
        opened = webbrowser.open(url)
    except Exception:
        opened = False
    if not opened and sys.platform == "win32":
        try:  # Windows shell fallback — always uses the default browser
            os.startfile(url)  # type: ignore[attr-defined]
            return True
        except Exception:
            return False
    return opened


# -------------------------------------------------------------------- main

def main() -> int:
    _setup_logging()
    log.info("=" * 60)
    log.info("Desktop launcher starting (pid %s)", os.getpid())

    host = os.environ.get("OSINT_HOST", "127.0.0.1")
    try:
        preferred = int(os.environ.get("OSINT_PORT", "8000"))
    except ValueError:
        preferred = 8000

    # Already running?  Just open a tab.
    if app_responds(host, preferred):
        url = f"http://{'localhost' if host == '0.0.0.0' else host}:{preferred}"
        log.info("Server already running on %s — opening browser", url)
        open_browser(url)
        return 0

    try:
        port = find_free_port(preferred, host)
    except RuntimeError as e:
        log.error("%s", e)
        _alert(f"{e}\n\nSee {LOG_PATH} for details.")
        return 1

    if port != preferred:
        log.info("Port %d busy with another service — using %d", preferred, port)

    import uvicorn

    from app.main import app, set_desktop_server

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        log_config=LOG_CONFIG,
    )
    server = uvicorn.Server(config)
    set_desktop_server(server)

    thread = threading.Thread(target=server.run, name="uvicorn", daemon=True)
    thread.start()

    # Wait for the server to answer (model loading happens on first request,
    # so /api/stats is a cheap readiness probe).
    deadline = time.time() + 60
    while time.time() < deadline:
        if server.started or app_responds(host, port):
            break
        if not thread.is_alive():
            log.error("Server thread died during startup — see log above")
            _alert("Server failed to start.\n\nSee logs/desktop.log for details.")
            return 1
        time.sleep(0.25)

    url_host = "localhost" if host in ("0.0.0.0", "") else host
    url = f"http://{url_host}:{port}"
    log.info("Server ready at %s — opening browser", url)
    if not open_browser(url):
        log.warning("Could not open a browser automatically; open %s manually", url)

    log.info("Launcher will keep the server alive until shut down from the UI")
    try:
        while thread.is_alive():
            thread.join(3600)
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        log.info("Server stopped — launcher exiting")
    return 0


def _alert(message: str) -> None:
    """Best-effort message box for fatal launcher errors (no console exists)."""
    log.error("ALERT: %s", message)
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "OSINT Face Search", 0x10)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
