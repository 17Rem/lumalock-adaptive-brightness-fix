"""Windows x64 portable build; explicit data allowlist, no device captures."""
from pathlib import Path
from importlib.metadata import distribution
import sys

root = Path(SPECPATH)
datas = [
    (str(root / 'lumalock/profiles/ne180qdm_nz4.json'), 'lumalock/profiles'),
    (str(root / 'LICENSE'), '.'),
    (str(root / 'THIRD_PARTY_NOTICES.md'), '.'),
    (str(root / 'lumalock/vendor/gpu_aux/LICENSE'), 'licenses/gpu_aux'),
    (str(root / 'lumalock/vendor/gpu_aux/SOURCE.json'), 'licenses/gpu_aux'),
    (str(Path(sys.base_prefix) / 'LICENSE.txt'), 'licenses/python'),
    (str(Path(sys.base_prefix) / 'tcl/tk8.6/license.terms'), 'licenses/tcl-tk'),
]
dist = distribution('pyinstaller')
for file in dist.files:
    if str(file).endswith('licenses/COPYING.txt'):
        datas.append((str(dist.locate_file(file)), 'licenses/pyinstaller'))
        break
else:
    raise RuntimeError('PyInstaller license not found')
for name in ('USAGE.zh-CN.md', 'TECHNICAL.md', 'BACKENDS.md'):
    datas.append((str(root / 'docs' / name), 'docs'))

a = Analysis(['LumaLock.pyw'], pathex=[str(root)], binaries=[], datas=datas,
             hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['pytest', 'numpy', 'matplotlib', 'PIL'], noarchive=False,
             optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='LumaLock',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='LumaLock')
