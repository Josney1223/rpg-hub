# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Mothership Lights.
# Build:  pyinstaller mothership_lights.spec
# Produces a single-file executable in ./dist/ for whatever OS you run it on.

block_cipher = None

a = Analysis(
    ['mothership_lights.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['tinytuya', 'pygame'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'PIL', 'cv2'],  # not used; keeps the bundle small
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='mothership-lights',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # windowed app (no terminal window on Windows)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='app.ico',       # optional: drop an .ico here to brand the .exe
)
