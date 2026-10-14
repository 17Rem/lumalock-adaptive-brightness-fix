"""Double-click entry point on Windows (Python + Tcl/Tk required)."""
import sys

try:
    from lumalock.gui import main
    main()
except Exception:
    import traceback
    error = traceback.format_exc()
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
                'LumaLock could not start. Install Python 3.10+ with Tcl/Tk.\n\n'+error,
                'LumaLock', 16)
        elif sys.stderr:
            sys.stderr.write(error)
