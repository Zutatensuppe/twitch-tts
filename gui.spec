# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

pyside6_datas, pyside6_binaries, pyside6_hiddenimports = collect_all("PySide6")
shiboken6_datas, shiboken6_binaries, shiboken6_hiddenimports = collect_all("shiboken6")

a = Analysis(
    ['src/twitch_tts/gui_run.py'],
    pathex=[],
    binaries=pyside6_binaries + shiboken6_binaries,
    datas=pyside6_datas + shiboken6_datas,
    hiddenimports=['pygame', 'twitchio', 'pytchat'] + pyside6_hiddenimports + shiboken6_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='tts-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
