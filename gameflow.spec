# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Recolectar customtkinter
datas_ctk, binaries_ctk, hiddenimports_ctk = collect_all('customtkinter')

# Datos adicionales
datas = datas_ctk + [
    ('assets', 'assets'),
]

binaries = binaries_ctk
hiddenimports = list(set(hiddenimports_ctk + [
    'win32gui',
    'win32process',
    'win32con',
    'win32api',
    'psutil',
    'cffi',
    'ctypes',
    'PIL',
    'PIL.ImageTk',
    'PIL._imaging',
    'darkdetect',
    'packaging',
    'ui.display_scale',
    'core.external_launchers',
    'core.feedback',
    'ui.dialogs.base_dialog',
    'ui.dialogs.external_import_dialog',
    'ui.dialogs.glass_folder_browser',
    'ui.dialogs.glass_message_box',
    'ui.dialogs.on_screen_keyboard',
    'ui.dialogs.controller_info_dialog',
]))

# 1. Main Launcher
a_launcher = Analysis(
    ['lanzador.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter.test', 'unittest', 'test'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz_launcher = PYZ(a_launcher.pure, a_launcher.zipped_data, cipher=block_cipher)

exe_launcher = EXE(
    pyz_launcher,
    a_launcher.scripts,
    [],
    exclude_binaries=True,
    name='GameFlow Launcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if os.path.isfile('assets/icon.ico') else None,
)

# 2. Gamepad Watcher
a_watcher = Analysis(
    ['gamepad_watcher.pyw'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter.test', 'unittest', 'test'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz_watcher = PYZ(a_watcher.pure, a_watcher.zipped_data, cipher=block_cipher)

exe_watcher = EXE(
    pyz_watcher,
    a_watcher.scripts,
    [],
    exclude_binaries=True,
    name='gamepad_watcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if os.path.isfile('assets/icon.ico') else None,
)

# 3. Sentinel Process
a_sentinel = Analysis(
    ['core/sentinel_process.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter.test', 'unittest', 'test'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz_sentinel = PYZ(a_sentinel.pure, a_sentinel.zipped_data, cipher=block_cipher)

exe_sentinel = EXE(
    pyz_sentinel,
    a_sentinel.scripts,
    [],
    exclude_binaries=True,
    name='sentinel_process',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if os.path.isfile('assets/icon.ico') else None,
)

coll = COLLECT(
    exe_launcher,
    a_launcher.binaries,
    a_launcher.zipfiles,
    a_launcher.datas,
    exe_watcher,
    a_watcher.binaries,
    a_watcher.zipfiles,
    a_watcher.datas,
    exe_sentinel,
    a_sentinel.binaries,
    a_sentinel.zipfiles,
    a_sentinel.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='GameFlow Launcher',
)
