# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

pyside6_datas = collect_data_files("PySide6")
pyside6_binaries = collect_dynamic_libs("PySide6") + collect_dynamic_libs("shiboken6")
pyside6_hiddenimports = collect_submodules("PySide6")

a = Analysis(
    ['src/twitch_tts/gui_run.py'],
    pathex=[],
    binaries=pyside6_binaries,
    datas=pyside6_datas,
    hiddenimports=['pygame', 'twitchio', 'pytchat'] + pyside6_hiddenimports,
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
