"""Small native Tk components for the frameless desktop shell."""
import os
import tkinter as tk


class HoverButton(tk.Frame):
    """A real keyboard-accessible button over a reserved shadow/lift area."""
    def __init__(self, parent, text, command, primary=False, dark=False,
                 height=48, font=None, **kw):
        super().__init__(parent, bg=parent.cget('bg'), height=height, bd=0)
        self.primary, self.dark = primary, dark
        self.selected = False
        self.hovered = False
        self.pressed = False
        self.focused = False
        self.animation = None
        self.level = 0.0
        self.shadow = tk.Frame(self, bg='#c5cbbf' if not dark else '#0e1110')
        self.shadow.place(x=4, y=5, relwidth=1, width=-4, relheight=1, height=-5)
        self.face = tk.Button(self, text=text, command=command, font=font,
                              bd=0, relief='flat', padx=16, pady=7,
                              highlightthickness=1, takefocus=True, **kw)
        self.face.place(x=0, y=3, relwidth=1, width=-4, relheight=1, height=-5)
        super().configure(width=self.face.winfo_reqwidth()+4)
        for widget in (self,self.shadow,self.face):
            widget.bind('<Enter>', lambda e: self._hover(True))
            widget.bind('<Leave>', self._leave)
        self.face.bind('<ButtonPress-1>', self._press, add='+')
        self.face.bind('<ButtonRelease-1>', self._release, add='+')
        self.face.bind('<FocusIn>', lambda e: self._focus(True))
        self.face.bind('<FocusOut>', lambda e: self._focus(False))
        self.face.bind('<Return>', lambda e: self.invoke())
        self.bind('<Destroy>', self._destroy, add='+')
        self._paint()

    def _enabled(self):
        return str(self.face.cget('state')) != 'disabled'

    def _hover(self, hovered):
        self.hovered = hovered
        if not hovered:
            self.pressed = False
        self._animate()

    def _leave(self,event):
        # Lifting the face must not repeatedly trigger leave/enter at its lower
        # edge. Treat the reserved shadow area as part of the same hover target.
        x,y = self.winfo_rootx(),self.winfo_rooty()
        if not (x <= event.x_root < x+self.winfo_width() and
                y <= event.y_root < y+self.winfo_height()):
            self._hover(False)

    def _focus(self, focused):
        self.focused = focused
        self._paint()

    def _press(self, event=None):
        if self._enabled():
            self.pressed = True
            self._paint()

    def _release(self, event=None):
        self.pressed = False
        self._paint()

    def _animate(self):
        if self.animation:
            self.after_cancel(self.animation)
            self.animation = None
        target = 1.0 if self.hovered and self._enabled() else 0.0
        self.level += max(-.22, min(.22, target-self.level))
        self._paint()
        if abs(self.level-target) > .001:
            self.animation = self.after(16, self._animate)

    @staticmethod
    def _blend(a, b, t):
        parts = [round(int(a[i:i+2],16)*(1-t)+int(b[i:i+2],16)*t) for i in (1,3,5)]
        return '#'+''.join(f'{v:02x}' for v in parts)

    def _paint(self):
        enabled = self._enabled()
        accent = self.primary or self.selected
        normal = '#e9ff47' if accent else ('#191c1d' if self.dark else '#fafbf7')
        hover = '#f3ff9c' if accent else ('#303b32' if self.dark else '#dce6d2')
        t = self.level if enabled else 0
        bg = self._blend(normal, hover, t)
        fg = '#191c1d' if accent or not self.dark else '#fafbf7'
        if self.dark and not accent and t > .3:
            fg = '#e9ff47'
        border = '#e9ff47' if self.dark else '#627344'
        if not enabled:
            bg = '#dce0d6' if not self.dark else '#252a26'
        if self.pressed and enabled:
            bg = '#cfdf62' if accent else '#bac9af'
            fg = '#191c1d'
        self.face.configure(bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
                            disabledforeground='#899184', cursor='hand2' if enabled else 'arrow',
                            highlightcolor=border,
                            highlightbackground=border if (self.focused or t > .1) and enabled else bg)
        y = 5 if self.pressed and enabled else round(3-3*t)
        self.face.place_configure(y=y)

    def set_selected(self, selected):
        self.selected = selected
        self._paint()

    def configure(self, cnf=None, **kw):
        options = dict(cnf or {}, **kw)
        for name in ('state','text','command'):
            if name in options:
                self.face.configure(**{name:options.pop(name)})
        if options:
            super().configure(**options)
        if hasattr(self, 'face'):
            if not self._enabled():
                self.level = 0
                self.pressed = False
            self._paint()

    config = configure

    def cget(self, name):
        if name in ('state','text','command'):
            return self.face.cget(name)
        return super().cget(name)

    __getitem__ = cget

    def invoke(self):
        return self.face.invoke()

    def _destroy(self, event):
        if event.widget is self and self.animation:
            self.after_cancel(self.animation)
            self.animation = None


class WindowFrame:
    """Keep Windows taskbar/Alt-Tab behavior while removing native decoration.

    Windows stays window-manager owned (no override-redirect), so native
    minimize/restore works. Other Tk platforms use override-redirect with a
    temporary managed window when minimizing.
    """
    def __init__(self, root, on_close):
        self.root = root
        self.on_close = on_close
        self.maximized = False
        self.restore_geometry = None
        self.drag_origin = None
        self.resize_origin = None
        self.style_after = None
        self.user32 = None
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            self.user32 = ctypes.WinDLL('user32', use_last_error=True)
            self.user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
            self.user32.GetAncestor.restype = wintypes.HWND
            self.user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
            self.user32.GetWindowLongW.restype = wintypes.LONG
            self.user32.SetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.LONG)
            self.user32.SetWindowLongW.restype = wintypes.LONG
            self.user32.SetWindowPos.argtypes = (wintypes.HWND,wintypes.HWND,ctypes.c_int,
                                                ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT)
            self.user32.SetWindowPos.restype = wintypes.BOOL
        else:
            root.overrideredirect(True)
        root.bind('<Map>', self._mapped, add='+')
        root.bind('<Alt-F4>', lambda e: self._close(), add='+')
        root.bind('<Destroy>', self._destroy, add='+')
        self.style_after = root.after_idle(self._style)

    def hwnd(self):
        return self.user32.GetAncestor(self.root.winfo_id(), 2)

    def _style(self):
        self.style_after = None
        if not self.root.winfo_exists() or self.root.state() == 'iconic':
            return
        if self.user32:
            hwnd = self.hwnd()
            style = self.user32.GetWindowLongW(hwnd, -16)
            # Remove WS_CAPTION and WS_THICKFRAME, retaining system menu and
            # minimize/maximize capabilities. No foreign windows are touched.
            self.user32.SetWindowLongW(hwnd, -16, style & ~0x00c40000)
            self.user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x37)
        else:
            self.root.overrideredirect(True)

    def _mapped(self, event):
        if event.widget is self.root and self.style_after is None:
            self.style_after = self.root.after_idle(self._style)

    def _close(self):
        self.on_close()
        return 'break'

    def minimize(self):
        if not self.user32:
            self.root.overrideredirect(False)
        self.root.iconify()

    def toggle_maximize(self):
        if self.maximized:
            if self.user32:
                self.root.state('normal')
            if self.restore_geometry:
                self.root.geometry(self.restore_geometry)
            self.maximized = False
        else:
            self.restore_geometry = self.root.geometry()
            if self.user32:
                self.root.state('zoomed')
            else:
                self.root.geometry(f'{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0')
            self.maximized = True
        self._style()

    def bind_drag(self, widget):
        widget.bind('<ButtonPress-1>', self.drag_start)
        widget.bind('<B1-Motion>', self.drag_move)
        widget.bind('<Double-Button-1>', lambda e: self.toggle_maximize())

    def drag_start(self, event):
        if self.maximized:
            return
        self.drag_origin = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())

    def drag_move(self, event):
        if self.maximized or not self.drag_origin:
            return
        px,py,x,y = self.drag_origin
        x,y = x+event.x_root-px,y+event.y_root-py
        if self.user32:
            self.user32.SetWindowPos(self.hwnd(),None,x,y,0,0,0x15)
        else:
            self.root.geometry(f'+{x}+{y}')

    def resize_start(self, event):
        self.resize_origin = (event.x_root,event.y_root,self.root.winfo_width(),self.root.winfo_height())

    def resize_move(self, event):
        if self.maximized or not self.resize_origin:
            return
        x,y,w,h = self.resize_origin
        minw,minh = self.root.minsize()
        self.root.geometry(f'{max(minw,w+event.x_root-x)}x{max(minh,h+event.y_root-y)}')

    def _destroy(self, event):
        if event.widget is self.root and self.style_after:
            self.root.after_cancel(self.style_after)
            self.style_after = None
