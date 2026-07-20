# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Mothership Lights (package: mslights).
# Build:  pyinstaller mothership_lights.spec   ->   dist/mothership-lights[.exe]

import os
block_cipher = None

hidden = [
    'mslights', 'mslights.app', 'mslights.config', 'mslights.colors',
    'mslights.lights', 'mslights.audio', 'mslights.packs', 'mslights.selftest',
    'mslights.devices_panel', 'mslights.lights_panel', 'mslights.audio_panel',
    'tinytuya', 'pygame',
]

a = Analysis(
    ['mothership_lights.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'PIL', 'cv2'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='mothership-lights',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    upx_exclude=[], runtime_tmpdir=None,
    console=False, disable_windowed_traceback=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
    # icon='app.ico',
)
