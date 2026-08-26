"""Tests for the desktop-launcher tooling (icons, entries, port helpers)."""
from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# load scripts/setup_desktop.py as a module (scripts/ is not a package)
_spec = importlib.util.spec_from_file_location(
    "setup_desktop", ROOT / "scripts" / "setup_desktop.py"
)
setup_desktop = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(setup_desktop)


@pytest.fixture(scope="module")
def icon_assets(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("icons")
    ico = tmp / "icon.ico"
    icns = tmp / "icon.icns"
    setup_desktop.build_ico(ROOT / "assets" / "icon.png", ico)
    setup_desktop.build_icns(ROOT / "assets" / "icon.png", icns)
    return ico, icns


class TestIcons:
    def test_ico_built_and_valid(self, icon_assets):
        from PIL import Image

        ico, _ = icon_assets
        assert ico.exists() and ico.stat().st_size > 1000
        img = Image.open(ico)
        assert img.format == "ICO"
        # ICO must embed multiple sizes
        sizes = {s for s, _ in img.ico.sizes()} if hasattr(img, "ico") else set()
        assert sizes or ico.stat().st_size > 10000

    def test_icns_structure(self, icon_assets):
        _, icns = icon_assets
        data = icns.read_bytes()
        assert data[:4] == b"icns"
        total = struct.unpack(">I", data[4:8])[0]
        assert total == len(data)
        # walk chunks
        offset, seen = 8, []
        while offset < len(data):
            ostype = data[offset:offset + 4]
            length = struct.unpack(">I", data[offset + 4:offset + 8])[0]
            assert 8 <= length <= len(data) - offset
            payload = data[offset + 8:offset + length]
            assert payload[:4] == b"\x89PNG"  # modern PNG-encoded icns chunks
            seen.append(ostype)
            offset += length
        assert set(seen) >= {b"ic07", b"ic08", b"ic09", b"ic10"}

    def test_make_square_crops_to_square(self):
        from PIL import Image
        import io

        buf = io.BytesIO()
        Image.new("RGB", (300, 100), (10, 20, 30)).save(buf, format="PNG")
        buf.seek(0)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
            fh.write(buf.read())
        tmp_png = Path(fh.name)
        img = setup_desktop.make_square(tmp_png, size=128)
        assert img.size == (128, 128)
        tmp_png.unlink(missing_ok=True)


class TestDesktopEntry:
    def test_entry_contents(self):
        entry = setup_desktop.desktop_entry_text(
            "MyApp", "/usr/bin/python3 '/opt/app/desktop_app.py'",
            Path("/opt/app/assets/icon.png"), "OSINT Face Search",
        )
        lines = entry.strip().splitlines()
        assert lines[0] == "[Desktop Entry]"
        assert "Name=MyApp" in lines
        assert "Terminal=false" in lines
        assert "Exec=/usr/bin/python3 '/opt/app/desktop_app.py'" in lines
        assert "Icon=/opt/app/assets/icon.png" in lines
        assert "Type=Application" in lines

    def test_safe_name_strips_path_chars(self):
        assert setup_desktop._safe_name('evil/../name') == "evil..name"
        assert setup_desktop._safe_name("  ") == "MyApp"
        assert setup_desktop._safe_name("a:b*c?d") == "abcd"


class TestWindowsScript:
    """The PowerShell/VBS generators are string builders — testable anywhere."""

    def test_shortcut_script_contents(self, tmp_path):
        lnk = tmp_path / "MyApp.lnk"
        script = setup_desktop._windows_shortcut_script(
            lnk, r"C:\Python311\pythonw.exe", '"C:\proj\desktop_app.py"', 1
        )
        assert "WScript.Shell" in script
        assert r"$sc.TargetPath = 'C:\Python311\pythonw.exe'" in script
        assert '"C:\proj\desktop_app.py"' in script
        assert r"$sc.IconLocation = '" in script
        assert "icon.ico" in script
        assert "$sc.Save()" in script
        # path with a single quote must be escaped for PowerShell
        tricky = setup_desktop._windows_shortcut_script(
            tmp_path / "o'brien.lnk", "x", "y", 1
        )
        assert "o''brien.lnk" in tricky

    def test_vbs_content(self):
        vbs = setup_desktop._vbs_launcher_content(
            r"C:\Python311\python.exe", Path(r"C:\proj\desktop_app.py")
        )
        assert vbs.startswith("Set sh = CreateObject")
        assert vbs.rstrip().endswith(", 0, False")   # window style 0 = hidden
        # decode the VBS quoting ("" -> ") and check the command it runs
        import re
        m = re.search(r'sh\.Run "(.*)", 0, False', vbs)
        assert m, "sh.Run statement not found"
        command = m.group(1).replace('""', '"')
        assert command == '"C:\\Python311\\python.exe" "C:\\proj\\desktop_app.py"'

    def test_vbs_str_quotes(self):
        assert setup_desktop._vbs_str("plain") == '"plain"'
        assert setup_desktop._vbs_str('say "hi"') == '"say ""hi"""'

    def test_lnk_vbs_script_contents(self, tmp_path):
        """PowerShell-free .lnk creator (used when PowerShell is blocked)."""
        lnk = tmp_path / "MyApp.lnk"
        vbs = setup_desktop._lnk_vbs_script(
            lnk, r"C:\Python311\pythonw.exe", '"C:\proj\desktop_app.py"', 1
        )
        assert 'Set sc = ws.CreateShortcut("MyApp.lnk")' in vbs.replace(str(lnk), "MyApp.lnk").replace("\\\\", "\\")
        assert 'sc.TargetPath = "C:\\Python311\\pythonw.exe"' in vbs
        assert 'sc.Arguments = """C:\\proj\\desktop_app.py"""' in vbs
        assert "icon.ico" in vbs
        assert vbs.rstrip().endswith("If Err.Number <> 0 Then WScript.Quit 1")
        # decodes to valid .lnk fields (round-trip the VBS escaping)
        import re
        target = re.search(r"sc\.TargetPath = \"(.*)\"", vbs).group(1).replace('""', '"')
        assert target == r"C:\Python311\pythonw.exe"


class TestLauncherHelpers:
    def test_find_free_port_returns_free(self):
        import desktop_app

        # 59152-59170 are in the unlikely-to-be-used range
        port = desktop_app.find_free_port(59152)
        assert 59152 <= port <= 59172
        # the returned port must actually be free (bindable)
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", port))

    def test_app_responds_false_on_closed_port(self):
        import desktop_app

        assert desktop_app.app_responds("127.0.0.1", 59199) is False

    def test_desktop_app_import_is_side_effect_free(self):
        import desktop_app  # noqa: F401  (import alone must not start servers)
        assert hasattr(desktop_app, "main")


class TestShutdownEndpoint:
    def test_shutdown_without_desktop_server_503(self):
        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as client:
            r = client.post("/api/system/shutdown")
            assert r.status_code == 503

    def test_shutdown_with_desktop_server(self):
        import threading
        import time

        from fastapi.testclient import TestClient

        import desktop_app
        from app.main import app, set_desktop_server

        class FakeServer:
            def __init__(self):
                self.should_exit = False

        fake = FakeServer()
        set_desktop_server(fake)
        try:
            with TestClient(app) as client:
                r = client.post("/api/system/shutdown")
                assert r.status_code == 200
                assert r.json()["status"] == "shutting down"
                time.sleep(0.8)
                assert fake.should_exit is True
        finally:
            set_desktop_server(None)
