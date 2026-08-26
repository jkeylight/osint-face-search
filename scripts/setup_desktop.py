#!/usr/bin/env python3
"""
setup_desktop.py — one command, one double-clickable desktop icon.

    python scripts/setup_desktop.py              # or: npm run setup-desktop

Creates a desktop shortcut (default name: "MyApp") that:

  * starts the app with NO console/terminal window
  * opens your browser at the app automatically
  * uses the bundled custom icon (assets/icon.png -> .ico/.icns)

Options:
    --name "MyApp"    shortcut name                     (default: MyApp)
    --console         make a console-mode shortcut to run.py (for debugging)
    --no-install      skip automatic pip install of requirements
    --no-models       skip face-model download
    --force           recreate the shortcut even if it already exists

Platform support: Windows (.lnk), macOS (.app bundle), Linux (.desktop).
Everything is created BY THIS SCRIPT — you never touch shortcuts or VBS files.
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import os
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

APP_TITLE = "OSINT Face Search"
ICON_PNG = ROOT / "assets" / "icon.png"
ICON_ICO = ROOT / "assets" / "icon.ico"
ICON_ICNS = ROOT / "assets" / "icon.icns"
DESKTOP_APP = ROOT / "desktop_app.py"
RUN_PY = ROOT / "run.py"

REQUIRED_MODULES = ("fastapi", "uvicorn", "cv2", "numpy", "PIL", "aiohttp")


def log(msg: str) -> None:
    print(msg, flush=True)


def die(msg: str) -> None:
    log(f"\n✗ {msg}")
    raise SystemExit(1)


# ═══════════════════════════════════════════════════════════ step 1: deps

def ensure_dependencies(auto_install: bool) -> None:
    missing = [m for m in REQUIRED_MODULES if importlib.util.find_spec(m) is None]
    if not missing:
        log("✓ dependencies already installed")
        return

    log(f"• missing Python packages: {', '.join(missing)}")
    if not auto_install:
        die("Install them first:  pip install -r requirements.txt")
    log("• installing requirements (pip install -r requirements.txt) …")
    cmd = [sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")]
    try:
        proc = subprocess.run(cmd, check=False)
    except OSError as e:
        die(f"pip failed to run: {e}")
    if proc.returncode != 0:
        die("pip install failed — run it manually:  pip install -r requirements.txt")
    still = [m for m in REQUIRED_MODULES if importlib.util.find_spec(m) is None]
    if still:
        die(f"packages still missing after install: {', '.join(still)}")
    log("✓ dependencies installed")


# ═════════════════════════════════════════════════════════ step 2: models

def ensure_models(skip: bool) -> None:
    if skip:
        log("• skipping model download (--no-models)")
        return
    from app.models import ensure_models as fetch
    status = fetch(ROOT / "models", auto_download=True)
    if all(status.values()):
        log("✓ face models present")
    else:
        log("⚠ some models missing — the app will retry on first use "
            "(or run scripts/download_models.py)")


# ══════════════════════════════════════════════════════════ step 3: icons

def make_square(src: Path, size: int = 1024) -> "Image.Image":
    from PIL import Image

    img = Image.open(src).convert("RGBA")
    w, h = img.size
    s = min(w, h)
    img = img.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
    if img.size != (size, size):
        img = img.resize((size, size), Image.LANCZOS)
    return img


def build_ico(src: Path, dst: Path) -> None:
    """Windows .ico with all standard sizes (built by Pillow)."""
    img = make_square(src)
    img.save(dst, format="ICO",
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                    (64, 64), (128, 128), (256, 256)])


def _icns_chunk(ostype: bytes, png_bytes: bytes) -> bytes:
    return ostype + struct.pack(">I", len(png_bytes) + 8) + png_bytes


def build_icns(src: Path, dst: Path) -> None:
    """macOS .icns (modern PNG-payload chunks ic07…ic10)."""
    from PIL import Image
    import io

    img = make_square(src)
    chunks = b""
    for ostype, size in ((b"ic07", 128), (b"ic08", 256), (b"ic09", 512), (b"ic10", 1024)):
        buf = io.BytesIO()
        resized = img.resize((size, size), Image.LANCZOS)
        resized.save(buf, format="PNG", optimize=True)
        chunks += _icns_chunk(ostype, buf.getvalue())
    data = b"icns" + struct.pack(">I", len(chunks) + 8) + chunks
    dst.write_bytes(data)


def build_icons() -> dict:
    if not ICON_PNG.exists():
        die(f"icon source missing: {ICON_PNG}")
    ICON_PNG.parent.mkdir(parents=True, exist_ok=True)
    build_ico(ICON_PNG, ICON_ICO)
    log(f"✓ built {ICON_ICO.name} (Windows icon)")
    build_icns(ICON_PNG, ICON_ICNS)
    log(f"✓ built {ICON_ICNS.name} (macOS icon)")
    return {"png": ICON_PNG, "ico": ICON_ICO, "icns": ICON_ICNS}


# ══════════════════════════════════════════════════════ step 4: shortcut

def _safe_name(name: str) -> str:
    name = (name or "").strip() or "MyApp"
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "")
    return name[:60]


# -------------------------------------------------------------- windows

def _ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def _vbs_str(s: str) -> str:
    """Quote a string for VBScript (embedded quotes doubled)."""
    return '"' + str(s).replace('"', '""') + '"'


def _windows_shortcut_script(lnk: Path, target: str, arguments: str,
                             window_style: int = 1) -> str:
    """PowerShell script that creates a .lnk via the WScript.Shell COM API."""
    return f"""
$ErrorActionPreference = 'Stop'
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut({_ps_quote(str(lnk))})
$sc.TargetPath = {_ps_quote(target)}
$sc.Arguments = {_ps_quote(arguments)}
$sc.WorkingDirectory = {_ps_quote(str(ROOT))}
$sc.IconLocation = {_ps_quote(str(ICON_ICO))},0
$sc.Description = {_ps_quote(APP_TITLE)}
$sc.WindowStyle = {window_style}
$sc.Save()
Write-Output 'OK'
"""


def _lnk_vbs_script(lnk: Path, target: str, arguments: str,
                    window_style: int = 1) -> str:
    """VBScript that creates the same .lnk (used when PowerShell is blocked)."""
    return "\n".join([
        "On Error Resume Next",
        "Set ws = CreateObject(\"WScript.Shell\")",
        f"Set sc = ws.CreateShortcut({_vbs_str(str(lnk))})",
        f"sc.TargetPath = {_vbs_str(target)}",
        f"sc.Arguments = {_vbs_str(arguments)}",
        f"sc.WorkingDirectory = {_vbs_str(str(ROOT))}",
        f"sc.IconLocation = {_vbs_str(str(ICON_ICO))},0",
        f"sc.Description = {_vbs_str(APP_TITLE)}",
        f"sc.WindowStyle = {window_style}",
        "sc.Save",
        "If Err.Number <> 0 Then WScript.Quit 1",
    ]) + "\n"


def _vbs_launcher_content(python: str, script: Path) -> str:
    """VBS that runs the launcher with a fully hidden console (fallback)."""
    return (
        "Set sh = CreateObject(\"WScript.Shell\")\n"
        f"sh.CurrentDirectory = \"{ROOT}\"\n"
        f"sh.Run \"\"\"{python}\"\" \"\"{script}\"\"\", 0, False\n"
    )


def _run_powershell(script: str) -> str:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-EncodedCommand", encoded],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "unknown error").strip()[:400])
    return proc.stdout.strip()


def _windows_desktop_dir() -> Path:
    """
    Resolve the real Desktop folder (handles OneDrive redirection).

    Order: registry (no subprocess needed) -> PowerShell -> %USERPROFILE%\\Desktop.
    """
    # 1) registry — "User Shell Folders\\Desktop" tracks OneDrive redirection
    try:
        import winreg  # stdlib, Windows only

        for subkey in (
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        ):
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey) as key:
                    val, _ = winreg.QueryValueEx(key, "Desktop")
                    desktop = Path(os.path.expandvars(val))
                    if desktop.is_dir():
                        return desktop
            except OSError:
                continue
    except ImportError:
        pass

    # 2) PowerShell known-folder query
    try:
        out = _run_powershell(
            "[Environment]::GetFolderPath([Environment+SpecialFolder]::Desktop)"
        ).strip()
        if out:
            desktop = Path(out.splitlines()[-1])
            desktop.mkdir(parents=True, exist_ok=True)
            return desktop
    except Exception:
        pass

    # 3) plain fallback
    desktop = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    return desktop


def _create_lnk_powershell(lnk: Path, target: str, args: str,
                           window_style: int) -> bool:
    try:
        _run_powershell(_windows_shortcut_script(lnk, target, args, window_style))
    except Exception:
        return False
    return lnk.exists()


def _create_lnk_vbs(lnk: Path, target: str, args: str,
                    window_style: int) -> bool:
    """Fallback .lnk creator via cscript (for PowerShell-locked machines)."""
    import tempfile

    try:
        with tempfile.NamedTemporaryFile("w", suffix=".vbs", delete=False,
                                         encoding="ascii") as fh:
            fh.write(_lnk_vbs_script(lnk, target, args, window_style))
            vbs_path = Path(fh.name)
    except OSError:
        return False
    try:
        subprocess.run(["cscript", "//nologo", str(vbs_path)],
                       capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        vbs_path.unlink(missing_ok=True)
    return lnk.exists()


def _reveal_in_explorer(path: Path) -> None:
    """Open Explorer with the shortcut selected so the user sees where it is."""
    try:
        subprocess.run(["explorer", f"/select,{path}"],
                       check=False, timeout=10)
    except Exception:
        pass


def create_windows_shortcut(name: str, console_mode: bool = False) -> Path:
    desktop = _windows_desktop_dir()
    lnk = desktop / f"{name}.lnk"

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    target, args = None, None

    if console_mode:
        # debugging shortcut: visible console running run.py (minimized)
        target, args = sys.executable, f'"{RUN_PY}"'
        window_style = 7
    elif pythonw.exists():
        # preferred: pythonw.exe = zero window, zero taskbar console
        target, args = str(pythonw), f'"{DESKTOP_APP}"'
        window_style = 1
    else:
        # fallback: hidden launch through wscript + generated VBS
        vbs = ROOT / "scripts" / "desktop_launcher.vbs"
        vbs.write_text(_vbs_launcher_content(sys.executable, DESKTOP_APP),
                       encoding="ascii")
        target, args = "wscript.exe", f'"{vbs}"'
        window_style = 1

    created = _create_lnk_powershell(lnk, target, args, window_style)
    if not created:
        log("• PowerShell shortcut creation failed — trying VBScript fallback …")
        created = _create_lnk_vbs(lnk, target, args, window_style)
    if not created:
        die(f"could not create the shortcut at {lnk} — create it manually "
            f"pointing to: {target} {args}")
    log(f"✓ desktop folder: {desktop}")
    _reveal_in_explorer(lnk)
    return lnk


# ----------------------------------------------------------------- macOS

def create_macos_app(name: str, console_mode: bool = False) -> Path:
    desktop = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    app_path = desktop / f"{name}.app"
    if app_path.exists():
        shutil.rmtree(app_path)

    contents = app_path / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Resources").mkdir(parents=True)

    script_name = _safe_name(name).replace(" ", "")
    if console_mode:
        exec_body = f"""#!/bin/bash
cd {_sh_quote(str(ROOT))}
exec {_sh_quote(sys.executable)} {_sh_quote(str(RUN_PY))}
"""
    else:
        exec_body = f"""#!/bin/bash
exec {_sh_quote(sys.executable)} {_sh_quote(str(DESKTOP_APP))}
"""

    exec_path = contents / "MacOS" / script_name
    exec_path.write_text(exec_body)
    exec_path.chmod(0o755)

    shutil.copy2(ICON_ICNS, contents / "Resources" / "app.icns")

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>{_xml_escape(name)}</string>
    <key>CFBundleDisplayName</key><string>{_xml_escape(name)}</string>
    <key>CFBundleExecutable</key><string>{_xml_escape(script_name)}</string>
    <key>CFBundleIconFile</key><string>app.icns</string>
    <key>CFBundleIdentifier</key><string>local.osintfacesearch.{_xml_escape(script_name.lower())}</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>2.1.1</string>
    <key>LSBackgroundOnly</key><false/>
</dict>
</plist>
"""
    (contents / "Info.plist").write_text(plist)
    return app_path


def _sh_quote(s: str) -> str:
    return "'" + str(s).replace("'", "'\\''") + "'"


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


# ----------------------------------------------------------------- linux

def desktop_entry_text(name: str, exec_line: str, icon: Path,
                       comment: str = APP_TITLE) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={name}\n"
        f"Comment={comment}\n"
        f"Exec={exec_line}\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=Utility;Science;\n"
    )


def create_linux_desktop(name: str, console_mode: bool = False) -> list:
    created = []
    slug = _safe_name(name).lower().replace(" ", "-")
    script_arg = RUN_PY if console_mode else DESKTOP_APP
    exec_line = f"{_sh_quote(sys.executable)} {_sh_quote(str(script_arg))}"
    entry = desktop_entry_text(_safe_name(name), exec_line, ICON_PNG)

    # 1) application menu entry
    apps_dir = Path.home() / ".local" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    menu_file = apps_dir / f"{slug}.desktop"
    menu_file.write_text(entry)
    menu_file.chmod(0o755)
    created.append(menu_file)

    # 2) desktop icon
    desktop = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    desktop_file = desktop / f"{slug}.desktop"
    desktop_file.write_text(entry)
    desktop_file.chmod(0o755)
    created.append(desktop_file)

    try:  # best effort: make GNOME trust the desktop launcher
        subprocess.run(["gio", "set", str(desktop_file),
                        "metadata::trusted", "true"],
                       check=False, capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return created


# ══════════════════════════════════════════════════════════════ main

def main() -> int:
    parser = argparse.ArgumentParser(description="Create the desktop shortcut")
    parser.add_argument("--name", default="MyApp", help="shortcut name (default: MyApp)")
    parser.add_argument("--console", action="store_true",
                        help="debugging shortcut with a visible console")
    parser.add_argument("--no-install", action="store_true",
                        help="skip pip install of requirements")
    parser.add_argument("--no-models", action="store_true",
                        help="skip face-model download")
    parser.add_argument("--force", action="store_true",
                        help="recreate shortcut even if it exists")
    args = parser.parse_args()

    name = _safe_name(args.name)

    log("═" * 62)
    log(f"  {APP_TITLE} — desktop shortcut setup")
    log("═" * 62)
    log(f"  project : {ROOT}")
    log(f"  shortcut: \"{name}\"")

    ensure_dependencies(auto_install=not args.no_install)
    ensure_models(skip=args.no_models)
    build_icons()

    platform = sys.platform
    if platform.startswith("win"):
        target = create_windows_shortcut(name, args.console)
        how_to = f'Double-click "{target}" — the app starts hidden and your browser opens.'
    elif platform == "darwin":
        target = create_macos_app(name, args.console)
        how_to = f'Double-click {target} — the app starts and your browser opens.'
    else:
        files = create_linux_desktop(name, args.console)
        target = files[-1]
        how_to = f'Double-click "{target}" (or find "{name}" in your application menu).'

    log("─" * 62)
    log(f"✓ DONE — shortcut created: {target}")
    log(f"  {how_to}")
    log("  Stop the app from its System page → \"Shut down server\".")
    log("  Launcher log: logs/desktop.log")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
