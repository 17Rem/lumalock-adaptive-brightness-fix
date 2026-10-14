"""Check an extracted EXE, including guard dispatch, without changing a LUT.

The GUI performs its normal initial candidate enumeration. No check/apply/restore
command is invoked. Guard inputs are synthetic, never expire and contain no target.
"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import zipfile


def main():
    archive = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix='LumaLock 解压测试 ') as folder:
        root = Path(folder)
        with zipfile.ZipFile(archive) as z:
            z.extractall(root)
        exe = root / 'LumaLock/LumaLock.exe'
        env = os.environ.copy()
        env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
        env['LUMALOCK_STATE_DIR'] = str(root / 'private-state')
        env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        options = dict(cwd=root, env=env, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        state = root / 'synthetic-state.json'
        state.write_text(json.dumps({'done': True}), encoding='utf-8')
        subprocess.run([str(exe), '--guard', str(state)], timeout=15, check=True, **options)
        state.write_text(json.dumps({'done': False, 'deadline': time.time()+3600}), encoding='utf-8')
        guard = subprocess.Popen([str(exe), '--guard', str(state)], **options)
        try:
            time.sleep(2)
            assert guard.poll() is None, 'Guard exited before completion signal'
            replacement = state.with_suffix('.tmp')
            replacement.write_text(json.dumps({'done': True}), encoding='utf-8')
            os.replace(replacement, state)
            assert guard.wait(timeout=15) == 0, 'Guard failed on completion signal'
        finally:
            if guard.poll() is None:
                guard.terminate()
                guard.wait(timeout=10)
        print('PASS: packaged guard starts, waits and exits without a GUI')

        user = ctypes.WinDLL('user32', use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user.IsWindowVisible.argtypes = [wintypes.HWND]
        user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        app = subprocess.Popen([str(exe)], **options)
        windows = []
        @callback_type
        def collect(hwnd, _):
            pid = wintypes.DWORD()
            user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == app.pid and user.IsWindowVisible(hwnd):
                title = ctypes.create_unicode_buffer(512)
                user.GetWindowTextW(hwnd, title, len(title))
                windows.append((hwnd, title.value))
            return True
        try:
            deadline = time.monotonic()+20
            while time.monotonic() < deadline:
                assert app.poll() is None, 'GUI exited during startup'
                windows.clear()
                user.EnumWindows(collect, 0)
                if any(title == 'LumaLock · 便携屏亮度控制' for _, title in windows):
                    break
                time.sleep(.25)
            else:
                raise AssertionError('No application window appeared: '+repr(windows))
            time.sleep(3)
            for hwnd, title in windows:
                if title == 'LumaLock · 便携屏亮度控制':
                    user.PostMessageW(hwnd, 0x0010, 0, 0)
            assert app.wait(timeout=20) == 0, 'GUI failed during normal close'
        finally:
            if app.poll() is None:
                app.terminate()
                app.wait(timeout=10)
        print('PASS: extracted GUI opens and closes with Python removed from PATH')
        print('PASS: paths with spaces/non-ASCII characters; no LUT operations invoked')


if __name__ == '__main__':
    main()
