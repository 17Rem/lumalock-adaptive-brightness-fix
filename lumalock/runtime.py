"""Small Windows/POSIX differences used by the daily transaction runner."""
import os
import subprocess
import sys
from pathlib import Path


def state_dir():
    """Keep personal logs/device backups outside the distributable project."""
    override=os.environ.get('LUMALOCK_STATE_DIR')
    if override:return Path(override).expanduser().resolve()
    if os.name=='nt':return Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'LumaLock'
    return Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'lumalock'


def lock(file):
    file.seek(0);file.write(b'0');file.flush();file.seek(0)
    if os.name=='nt':
        import msvcrt
        msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
    else:
        import fcntl
        fcntl.flock(file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)


def detached_options():
    return {'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}


def guard_command(path):
    """A frozen executable is the app itself, not a Python interpreter."""
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--guard', str(path)]
    return [sys.executable, '-X', 'utf8', '-B', '-m', 'lumalock', '--guard', str(path)]


def guard_environment():
    env = os.environ.copy()
    if getattr(sys, 'frozen', False):
        # Recovery must remain independent if the main application exits.
        env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return env


def ensure_standard_streams():
    """Windowed executables/pythonw have no console streams."""
    for name, mode in [('stdin', 'r'), ('stdout', 'w'), ('stderr', 'w')]:
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, mode, encoding='utf-8'))
