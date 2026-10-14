"""Windowed entry point for both Python and the portable executable."""
import sys

try:
    from lumalock.runtime import ensure_standard_streams
    ensure_standard_streams()
    from lumalock.control import main
    main()
except Exception:
    import traceback
    error = traceback.format_exc()
    if '--guard' in sys.argv:
        # Never block independent recovery on a modal startup error dialog.
        raise SystemExit(1)
    try:
        from tkinter import Tk, messagebox
        root = Tk()
        root.withdraw()
        messagebox.showerror('LumaLock 启动失败', error, parent=root)
        root.destroy()
    except Exception:
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,
                ('LumaLock could not start. Extract the complete portable ZIP again.'
                 if getattr(sys, 'frozen', False) else
                 'LumaLock could not start. Install Python 3.10+ with Tcl/Tk.')+'\n\n'+error,
                'LumaLock', 16)
        elif sys.stderr:
            sys.stderr.write(error)
