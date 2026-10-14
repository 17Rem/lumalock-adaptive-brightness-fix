"""Build a portable ZIP with a deliberately small, reviewed payload."""
import hashlib
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lumalock import __version__


def main():
    if sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise SystemExit('Build on Windows x64 with 64-bit Python.')
    if sys.maxsize <= 2**32:
        raise SystemExit('64-bit Python is required.')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    str(ROOT / 'LumaLock.spec')], cwd=ROOT, check=True)
    bundle = ROOT / 'dist/LumaLock'
    for name in ('README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT / name, bundle / name)
    (bundle / 'START-HERE.txt').write_text(
        'LumaLock ' + __version__ + ' — Windows x64\n\n'
        '解压整个文件夹后，双击 LumaLock.exe。无需安装 Python。\n'
        '请保留 _internal 文件夹，不能只复制 EXE。\n'
        '选择屏幕 → 检查兼容性 → 固定高亮度；恢复自适应可还原。\n'
        '只修改易失内存，不刷固件；断电后若失效，重新应用。\n'
        '完整说明见界面内「使用说明」及 _internal/docs/USAGE.zh-CN.md。\n\n'
        'Extract the complete folder, then run LumaLock.exe. No Python required.\n'
        'Keep _internal beside the executable. GPU drivers are still required.\n'
        'Windows NVIDIA hardware tested; AMD/Intel remain experimental.\n'
        'No automatic startup or firmware flashing. Reapply after a reset.\n'
        'Unsigned community build. Source and releases:\n'
        'https://github.com/17Rem/lumalock-adaptive-brightness-fix\n', encoding='utf-8')
    archive = ROOT / 'dist' / f'LumaLock-{__version__}-windows-x64.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in sorted(bundle.rglob('*')):
            if path.is_file():
                output.write(path, path.relative_to(bundle.parent))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (ROOT / 'dist/SHA256SUMS.txt').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    print(f'Created {archive.name} ({archive.stat().st_size:,} bytes)\nSHA256: {digest}')


if __name__ == '__main__':
    main()
