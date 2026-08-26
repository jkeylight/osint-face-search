@echo off
setlocal EnableExtensions
title OSINT Face Search - Desktop Icon Installer

echo ============================================================
echo   OSINT FACE SEARCH - Desktop Icon Installer
echo   (creates the "MyApp" shortcut on your Desktop)
echo ============================================================
echo.

rem -- always run from the folder this file lives in
cd /d "%~dp0"

if not exist "scripts\setup_desktop.py" (
    echo [ERROR] scripts\setup_desktop.py not found.
    echo         Your project folder does not contain the new code.
    echo         Run:  git pull origin main
    echo         or re-download the repository from GitHub.
    pause
    exit /b 1
)

rem -- find Python: py launcher first, then plain python
set "PYOK="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PYOK=py -3"

if not defined PYOK (
    python --version >nul 2>&1
    if not errorlevel 1 set "PYOK=python"
)

if not defined PYOK (
    echo [ERROR] Python 3 was not found on this computer.
    echo.
    echo         Install Python 3.10+ from https://www.python.org/downloads/
    echo         and make sure you tick "Add Python to PATH" in the installer.
    echo         Then double-click this file again.
    echo.
    pause
    exit /b 1
)

echo Using Python:
%PYOK% --version
echo.
echo Creating your desktop shortcut ...
echo.

%PYOK% "scripts\setup_desktop.py" --name "MyApp"
set "RC=%ERRORLEVEL%"
echo.

if "%RC%"=="0" (
    echo ============================================================
    echo   DONE - the "MyApp" icon is on your Desktop.
    echo   Double-click it: the app starts with no black window
    echo   and your browser opens automatically.
    echo ============================================================
) else (
    echo ============================================================
    echo   INSTALL FAILED  ^(exit code %RC%^).
    echo   Read the messages above - they say exactly what failed
    echo   ^(missing Python packages are installed automatically^).
    echo ============================================================
)
pause
