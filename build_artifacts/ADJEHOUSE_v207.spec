# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['..\\adjehouse_main.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\Administrator\\Documents\\Cursor\\Cursor\\ADJEHOUSE\\scrapers', 'scrapers'), ('C:\\Users\\Administrator\\Documents\\Cursor\\Cursor\\ADJEHOUSE\\signups', 'signups'), ('C:\\Users\\Administrator\\Documents\\Cursor\\Cursor\\ADJEHOUSE\\monitors', 'monitors')],
    hiddenimports=['selenium', 'requests', 'imaplib', 'email', 'json', 'html', 'html.parser', 'twilio', 'twilio.rest', 'dolphin_base', 'capsolver_helper', 'lxml', 'lxml.html', 'lxml.etree', 'lxml._elementpath', 'discord', 'discord.client', 'discord.intents'],
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
    name='ADJEHOUSE_v207',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
