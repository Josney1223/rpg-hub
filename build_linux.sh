#!/usr/bin/env bash
# Build a standalone Linux executable -> dist/mothership-lights
set -e

# System Tk is required to bundle the GUI (not a pip package):
#   Debian/Ubuntu:  sudo apt install python3-tk
#   Fedora:         sudo dnf install python3-tkinter
#   Arch:           sudo pacman -S tk

python3 -m pip install --upgrade pyinstaller tinytuya pygame-ce
python3 -m PyInstaller mothership_lights.spec --noconfirm --clean

echo
echo "Done -> dist/mothership-lights"
echo "Smoke test:"
./dist/mothership-lights --selftest
