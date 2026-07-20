@echo off
REM Build a standalone Windows executable -> dist\mothership-lights.exe
REM Run this on a Windows machine with Python 3 installed (python.org build,
REM which already includes Tkinter). Double-click, or run from a terminal.

python -m pip install --upgrade pyinstaller tinytuya pygame-ce
if errorlevel 1 goto :err

python -m PyInstaller mothership_lights.spec --noconfirm --clean
if errorlevel 1 goto :err

echo.
echo Done -^> dist\mothership-lights.exe
echo Smoke test:
dist\mothership-lights.exe --selftest
goto :eof

:err
echo.
echo Build failed. Make sure Python 3 is installed and on PATH.
pause
