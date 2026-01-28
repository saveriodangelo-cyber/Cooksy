from pathlib import Path
import fido2

fido2_data = Path(fido2.__file__).parent / 'public_suffix_list.dat'

a = Analysis(
    ['app/launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('ui', 'ui'), ('templates', 'templates'), ('data', 'data'), (str(fido2_data), 'fido2')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Cooksy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon='ui/assets/cooksy_logo.png',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Cooksy',
)
