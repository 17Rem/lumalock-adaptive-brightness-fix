"""Small Windows/POSIX differences used by the daily transaction runner."""
import os
import subprocess
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
