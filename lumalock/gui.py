"""Native Tk interface. All device work runs off the UI thread."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

from . import compatibility, control, runtime
from . import __version__

BG = '#eeefeb'
PAPER = '#fafbf7'
INK = '#191c1d'
MUTED = '#656c6c'
LINE = '#d2d6d0'
YELLOW = '#e9ff47'
GREEN = '#2c7759'
RED = '#b03c30'
FONT = 'Microsoft YaHei UI' if os.name == 'nt' else 'Noto Sans CJK SC'
MONO = 'Consolas' if os.name == 'nt' else 'DejaVu Sans Mono'


class Tasks:
    """One job at a time; queue messages are the only worker/UI boundary."""
    def __init__(self):
        self.events = queue.Queue()
        self.busy = False

    def start(self, action, display=None, backend='auto'):
        if self.busy:
            return False
        self.busy = True
        threading.Thread(target=self._work, args=(action, display, backend), daemon=False).start()
        return True

    def _work(self, action, display, backend):
        try:
            if action == 'list':
                result = compatibility.list_displays(backend)
                self.events.put(('devices', result))
            else:
                result = control.run(action, display, backend,
                                     on_progress=lambda e: self.events.put(('progress', e)))
                self.events.put(('result', result))
        except Exception as exc:
            self.events.put(('error', {'message': str(exc), 'action': action}))


def open_folder(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        os.startfile(str(path))
    else:
        subprocess.Popen(['xdg-open', str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class App:
    def __init__(self, root):
        self.root = root
        self.tasks = Tasks()
        self.devices = []
        self.history = []
        self.feed_history = []
        self.stage = 'idle'
        self.action = None
        self.started = None
        self.last_message = None
        self.pending = None
        self.blocked = False
        self.root.title('LumaLock · 便携屏亮度控制')
        self.root.configure(bg=BG)
        self.root.geometry('1180x820')
        self.root.minsize(1040, 760)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.option_add('*Font', (FONT, 10))
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TCombobox', fieldbackground=PAPER, background=PAPER,
                        foreground=INK, padding=8, bordercolor=LINE, arrowsize=14)
        style.map('TCombobox', fieldbackground=[('readonly', PAPER)],
                  selectbackground=[('readonly', PAPER)], selectforeground=[('readonly', INK)])
        style.configure('Luma.Horizontal.TProgressbar', background=YELLOW,
                        troughcolor='#3b3f3d', borderwidth=0, lightcolor=YELLOW, darkcolor=YELLOW)
        self._build()
        self.poll_after = self.root.after(80, self.poll)
        self.scan_after = self.root.after(250, self.scan)

    def label(self, parent, text, size=11, fg=INK, bg=None, bold=False, mono=False, **kw):
        return tk.Label(parent, text=text, bg=bg or parent.cget('bg'), fg=fg,
                        font=(MONO if mono else FONT, size, 'bold' if bold else 'normal'), **kw)

    def button(self, parent, text, command, primary=False, dark=False, **kw):
        bg = YELLOW if primary else (INK if dark else PAPER)
        fg = INK if not dark or primary else PAPER
        return tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                         activebackground='#d8ec4a' if primary else '#dfe4db',
                         activeforeground=INK, disabledforeground='#8b928b',
                         relief='flat', bd=0, cursor='hand2', padx=16, pady=10,
                         highlightthickness=1, highlightbackground=LINE,
                         highlightcolor=GREEN, font=(FONT, 10, 'bold'), **kw)

    def _build(self):
        side = tk.Frame(self.root, bg=INK, width=232)
        side.pack(side='left', fill='y')
        side.pack_propagate(False)
        brand = tk.Canvas(side, width=180, height=76, bg=INK, highlightthickness=0)
        brand.pack(anchor='w', padx=26, pady=(30, 10))
        brand.create_polygon(0, 0, 61, 0, 76, 15, 76, 68, 0, 68, fill=YELLOW)
        brand.create_line(23, 16, 23, 49, 56, 49, fill=INK, width=8)
        for x in (94, 105, 116, 127, 138, 149):
            brand.create_line(x, 48, x + 15, 18, fill='#5e6661', width=2)
        self.label(side, 'LUMA\nLOCK', 32, PAPER, bold=True, mono=True,
                   justify='left', anchor='w').pack(anchor='w', padx=26)
        self.label(side, '便携屏亮度控制', 11, '#b5bdb5').pack(anchor='w', padx=28, pady=(4, 30))
        selected = tk.Frame(side, bg=YELLOW, height=55)
        selected.pack(fill='x', padx=16)
        self.label(selected, '01   亮度控制     ↗', 12, bold=True).pack(anchor='w', padx=16, pady=14)
        self.button(side, '02   使用说明', self.help, dark=True, anchor='w').pack(fill='x', padx=16, pady=(10, 0))
        self.button(side, '03   打开本地记录', self.logs, dark=True, anchor='w').pack(fill='x', padx=16, pady=6)
        foot = tk.Frame(side, bg=INK)
        foot.pack(side='bottom', fill='x', padx=28, pady=30)
        self.label(foot, 'DISPLAY / CONTROL', 10, YELLOW, mono=True).pack(anchor='w')
        tk.Frame(foot, height=1, bg='#464d46').pack(fill='x', pady=16)
        self.label(foot, '运行内存设置 · 无需刷固件', 9, '#b5bdb5').pack(anchor='w')
        self.label(foot, 'LUMALOCK  /  '+__version__, 10, '#8d968e', mono=True).pack(anchor='w', pady=(10, 0))

        main = tk.Frame(self.root, bg=BG)
        main.pack(side='left', fill='both', expand=True, padx=32, pady=(26, 18))
        top = tk.Frame(main, bg=BG)
        top.pack(fill='x')
        self.label(top, '01 / BRIGHTNESS CONTROL', 10, MUTED, mono=True).pack(side='left')
        self.label(top, '●  本地运行', 9, GREEN).pack(side='right')
        self.label(main, '让亮度，保持稳定。', 27, bold=True).pack(anchor='w', pady=(8, 3))
        self.label(main, '锁定原厂高亮度，告别画面切换后的忽明忽暗。', 10, MUTED).pack(anchor='w', pady=(0, 14))

        device = tk.Frame(main, bg=PAPER, highlightbackground=LINE, highlightthickness=1)
        device.pack(fill='x', pady=(0, 14))
        device_top = tk.Frame(device, bg=PAPER)
        device_top.pack(fill='x', padx=18, pady=(12, 6))
        self.label(device_top, '目标屏幕', 10, bold=True).pack(side='left')
        self.device_status = self.label(device_top, '等待识别', 9, MUTED)
        self.device_status.pack(side='right')
        device_row = tk.Frame(device, bg=PAPER)
        device_row.pack(fill='x', padx=18, pady=(0, 14))
        self.device_choice = ttk.Combobox(device_row, state='disabled', font=(FONT, 10))
        self.device_choice.pack(side='left', fill='x', expand=True, padx=(0, 10))
        self.device_choice.set('正在查找兼容屏幕…')
        self.device_choice.bind('<<ComboboxSelected>>', self.selection_changed)
        self.backend = ttk.Combobox(device_row, values=('自动检测', 'NVIDIA', 'AMD', 'Intel', 'Linux'),
                                    state='readonly', width=11, font=(FONT, 10))
        self.backend.current(0)
        self.backend.pack(side='left', padx=(0, 10))
        self.backend.bind('<<ComboboxSelected>>', lambda e: self.scan())
        self.refresh = self.button(device_row, '重新检测', self.scan)
        self.refresh.pack(side='right')

        progress = tk.Frame(main, bg=INK)
        progress.pack(fill='x')
        progress_inner = tk.Frame(progress, bg=INK)
        progress_inner.pack(fill='x', padx=24, pady=(18, 16))
        progress_heading = tk.Frame(progress_inner, bg=INK)
        progress_heading.pack(fill='x')
        self.label(progress_heading, 'OPERATION / 当前任务', 10, '#a2aea2', mono=True).pack(side='left')
        self.elapsed = self.label(progress_heading, '00:00', 11, '#a2aea2', mono=True)
        self.elapsed.pack(side='right')
        body = tk.Frame(progress_inner, bg=INK)
        body.pack(fill='x', pady=(13, 12))
        text = tk.Frame(body, bg=INK)
        text.pack(side='left', fill='x', expand=True)
        self.heading = self.label(text, '正在查找屏幕', 20, PAPER, bold=True, anchor='w')
        self.heading.pack(anchor='w')
        self.subheading = self.label(text, '完成后即可选择操作', 10, '#b5bdb5', anchor='w')
        self.subheading.pack(anchor='w', pady=(6, 0))
        self.percent = self.label(body, '—', 38, YELLOW, bold=True, mono=True)
        self.percent.pack(side='right', padx=(10, 0))
        self.bar = ttk.Progressbar(progress_inner, style='Luma.Horizontal.TProgressbar', maximum=100)
        self.bar.pack(fill='x', ipady=2)
        step_row = tk.Frame(progress_inner, bg=INK)
        step_row.pack(fill='x', pady=(16, 0))
        self.steps = []
        for i, title in enumerate(('连接屏幕', '兼容核验', '曲线设置', '完成检查')):
            label = self.label(step_row, f'{i+1:02}  {title}', 9, '#8e998f', anchor='w')
            label.pack(side='left', expand=True, fill='x')
            self.steps.append(label)

        operations = tk.Frame(main, bg=BG)
        operations.pack(fill='x', pady=(16, 0))
        self.actions = []
        specs = [('检查兼容性', '检查当前状态，不改亮度', 'check'),
                 ('固定高亮度  ↗', '应用已验证的原厂高值', 'apply'),
                 ('恢复自适应', '恢复原始亮度曲线', 'restore')]
        for i, (title, description, action) in enumerate(specs):
            operations.columnconfigure(i, weight=1, uniform='actions')
            box = tk.Frame(operations, bg=BG)
            box.grid(row=0, column=i, sticky='ew', padx=(0 if i == 0 else 10, 0))
            button = self.button(box, title, lambda a=action: self.operate(a), primary=action=='apply')
            button.pack(fill='x', ipady=5)
            self.label(box, description, 9, MUTED).pack(anchor='w', pady=(8, 0))
            self.actions.append(button)

        self.notice = self.label(main, '首次使用可先检查兼容性。每次设置前都会重新核验。', 10, MUTED,
                                 anchor='w', justify='left', wraplength=820)
        self.notice.pack(fill='x', pady=(14, 14))
        main.bind('<Configure>', lambda e: self.notice.configure(wraplength=max(100, e.width-8)))
        loghead = tk.Frame(main, bg=BG)
        loghead.pack(fill='x')
        self.label(loghead, '操作动态', 10, bold=True).pack(side='left')
        detail_btn = tk.Button(loghead, text='查看详情  +', command=self.details, relief='flat', bd=0,
                               bg=BG, fg=MUTED, activebackground=BG, cursor='hand2', font=(FONT, 9))
        detail_btn.pack(side='right')
        tk.Frame(main, bg=LINE, height=1).pack(fill='x', pady=(7, 6))
        self.feed = self.label(main, '等待连接…', 9, MUTED, anchor='nw', justify='left')
        self.feed.pack(fill='both', expand=True)
        self.footer = self.label(main, '断电或休眠后若设置失效，重新应用即可。', 9, MUTED, anchor='w')
        self.footer.pack(side='bottom', fill='x', pady=(8, 0), before=loghead)
        self.set_controls()

    def selected(self):
        index = self.device_choice.current()
        return self.devices[index] if 0 <= index < len(self.devices) else None

    def backend_name(self):
        return ('auto', 'nvidia', 'amd', 'intel', 'linux')[max(0, self.backend.current())]

    def set_controls(self):
        idle = not self.tasks.busy and not self.blocked
        self.refresh.configure(state='normal' if idle else 'disabled')
        self.backend.configure(state='readonly' if idle else 'disabled')
        self.device_choice.configure(state='readonly' if idle and self.devices else 'disabled')
        for button in self.actions:
            button.configure(state='normal' if idle and self.selected() else 'disabled')

    def selection_changed(self, event=None):
        self.device_status.configure(text='候选屏幕 · 待完整核验', fg=MUTED)
        self.heading.configure(text='屏幕已就绪')
        self.subheading.configure(text='请选择检查、固定高亮度或恢复')
        self.percent.configure(text='—', fg=YELLOW)
        self.stage = 'idle'
        for label in self.steps:
            label.configure(fg='#8e998f')
        self.set_controls()

    def scan(self):
        if self.blocked:
            return
        if not self.tasks.start('list', backend=self.backend_name()):
            return
        self.action = 'list'
        self.started = time.monotonic()
        self.devices = []
        self.device_choice.set('正在查找兼容屏幕…')
        self.device_status.configure(text='正在检测', fg=MUTED)
        self.set_controls()
        self.update_progress(dict(stage='discovery', message='正在查找屏幕', completed=None, total=None))

    def operate(self, action):
        selected = self.selected()
        if not selected or self.blocked:
            return
        if not self.tasks.start(action, selected['endpoint_id'], selected['backend']):
            return
        self.action = action
        self.started = time.monotonic()
        self.last_message = None
        self.set_controls()
        self.notice.configure(text='操作进行中，请保持屏幕连接。完成校验后会自动结束。', fg=MUTED)
        self.update_progress(dict(stage='discovery', message='正在连接目标屏幕', completed=None, total=None))

    def add_log(self, message):
        line = f'{time.strftime("%H:%M:%S")}   {message}'
        self.history.append(line)
        self.history = self.history[-500:]
        self.feed_history = (self.feed_history+[line])[-3:]
        self.feed.configure(text='\n'.join(self.feed_history))

    def update_progress(self, event):
        stage = event['stage']
        if stage in ('done', 'failed'):
            return  # The result event is emitted only after run() returns.
        self.stage = stage
        title = event['message']
        self.heading.configure(text='正在恢复原始曲线' if stage=='recovery' and event.get('total') else title)
        if title != self.last_message:
            self.add_log(title)
            self.last_message = title
        completed, total = event.get('completed'), event.get('total')
        self.bar.stop()
        if total:
            self.bar.configure(mode='determinate', value=completed/total*100)
            self.percent.configure(text=f'{completed/total:.0%}', fg=YELLOW)
            unit = '数据块' if stage == 'firmware' else '数据包'
            suffix = '已尝试，随后校验' if stage=='recovery' else '本阶段进度'
            self.subheading.configure(text=f'{completed:03} / {total:03} {unit}  ·  {suffix}')
        else:
            self.bar.configure(mode='indeterminate', value=0)
            self.bar.start(18)
            self.percent.configure(text='···', fg=YELLOW)
            self.subheading.configure(text='正在处理，请稍候' if stage!='recovery' else '请保持连接，恢复结束前不要重试')
        index = {'discovery': 0, 'firmware': 1, 'current': 1, 'write': 2,
                 'verify': 2, 'cleanup': 3, 'recovery': 3}.get(stage, 0)
        for i, label in enumerate(self.steps):
            label.configure(fg=YELLOW if i == index else ('#d4ded1' if i < index else '#8e998f'))

    def poll(self):
        try:
            while True:
                kind, value = self.tasks.events.get_nowait()
                if kind == 'progress':
                    self.update_progress(value)
                elif kind == 'devices':
                    self.show_devices(value)
                elif kind == 'result':
                    self.finish(value)
                elif kind == 'error':
                    self.tasks.busy = False
                    # An unexpected worker exception may have left a watchdog armed.
                    self.blocked = value['action'] != 'list'
                    self.bar.stop()
                    self.bar.configure(mode='determinate', value=0)
                    self.heading.configure(text='操作未完成')
                    self.percent.configure(text='!', fg='#ff9a80')
                    self.subheading.configure(text='打开详情查看具体原因')
                    self.notice.configure(text='请查看本地记录；如有恢复进程，请等待其结束后再重新打开工具。' if self.blocked else '未能完成检测，可更换接口或重新检测。', fg=RED)
                    self.add_log(value['message'])
                    self.started = None
                    self.set_controls()
        except queue.Empty:
            pass
        if self.started:
            elapsed = int(time.monotonic()-self.started)
            self.elapsed.configure(text=f'{elapsed//60:02}:{elapsed%60:02}')
        if self.pending:
            path = Path(self.pending['recovery_path'])
            try:
                result = json.loads(path.read_text(encoding='utf-8'))
            except (FileNotFoundError, ValueError, OSError):
                remaining = max(0, int(self.pending['recovery_deadline']-time.time()))
                self.subheading.configure(text=f'独立恢复将在约 {remaining} 秒后启动' if remaining else '独立恢复进行中，请保持连接')
            else:
                self.pending = None
                self.tasks.busy = False
                self.blocked = not result.get('restored', False)
                self.bar.stop()
                self.bar.configure(mode='determinate', value=0)
                self.heading.configure(text='恢复完成' if not self.blocked else '恢复未确认')
                self.subheading.configure(text='上次操作未成功，恢复结果已记录')
                self.notice.configure(text='已恢复屏幕状态，可查看记录后重新检查。' if not self.blocked else '无法确认恢复，请查看记录，断电重连屏幕后重新打开工具。', fg=MUTED if not self.blocked else RED)
                self.add_log('独立恢复完成' if not self.blocked else '独立恢复未确认：'+str(result))
                self.started = None
                self.set_controls()
        self.poll_after = self.root.after(80, self.poll)

    def show_devices(self, rows):
        self.tasks.busy = False
        self.started = None
        self.bar.stop()
        self.bar.configure(mode='determinate', value=0)
        self.percent.configure(text='—', fg=YELLOW)
        self.devices = [r for r in rows if r.get('candidate')]
        labels = [f'NE180QDM-NZ4  /  {r["endpoint_id"]}' for r in self.devices]
        self.device_choice.configure(values=labels)
        for row in rows:
            if not row.get('candidate'):
                self.history.append(row['display']+': '+row.get('reason', '不可用'))
        if len(self.devices) == 1:
            self.device_choice.current(0)
            self.selection_changed()
            self.add_log('已识别 1 块候选屏幕，设置前将完整核验')
        elif self.devices:
            self.device_choice.set('请选择一块目标屏幕')
            self.heading.configure(text='发现多块候选屏幕')
            self.subheading.configure(text='在上方选择要操作的屏幕')
            self.device_status.configure(text=f'{len(self.devices)} 块候选', fg=MUTED)
            self.add_log(f'检测到 {len(self.devices)} 块候选，请选择目标')
        else:
            self.device_choice.set('未发现兼容屏幕')
            self.heading.configure(text='暂未发现兼容屏幕')
            self.subheading.configure(text='检查连接，或在详情中查看接口原因')
            self.device_status.configure(text='未识别', fg=MUTED)
            self.add_log('未找到兼容屏幕；接口诊断已收录在详情中')
        self.set_controls()

    def finish(self, report):
        self.bar.stop()
        self.tasks.busy = False
        self.started = None
        self.stage = 'done' if report['success'] else 'failed'
        if report['success']:
            high = report['after'] == 'fixed_high'
            title = '检查通过' if self.action == 'check' else ('高亮度已锁定' if high else '已恢复自适应')
            self.heading.configure(text=title)
            self.percent.configure(text='OK', fg=YELLOW)
            self.bar.configure(mode='determinate', value=100)
            self.subheading.configure(text='当前为固定高亮度' if high else '当前为原始自适应曲线')
            self.device_status.configure(text='本次核验通过', fg=GREEN)
            self.notice.configure(text='当前亮度表保持不变。' if self.action == 'check' else '设置已生效，断电或休眠后若失效可重新应用。', fg=GREEN)
            for label in self.steps:
                label.configure(fg=YELLOW)
            self.add_log(title+' · '+('固定高亮度' if high else '原始曲线'))
        else:
            self.heading.configure(text='操作未完成')
            self.percent.configure(text='!', fg='#ff9a80')
            self.bar.configure(mode='determinate', value=0)
            restored = report.get('rollback', {}).get('restored', False)
            self.subheading.configure(text='屏幕状态已恢复' if restored else '查看详情中的错误与恢复结果')
            self.notice.configure(text='本次操作未完成，请先查看原因。' if restored else '请查看本地记录，不要连续重试。', fg=RED)
            self.add_log(report.get('error', '未知错误'))
        if report.get('log_path'):
            self.history.append('本地记录：'+report['log_path'])
        if report.get('recovery_pending'):
            self.pending = report
            self.tasks.busy = True
            self.started = time.monotonic()
            self.update_progress(dict(stage='recovery', message='等待独立恢复', completed=None, total=None))
        self.set_controls()

    def details(self):
        window = tk.Toplevel(self.root)
        window.title('LumaLock · 操作详情')
        window.geometry('840x480')
        frame = tk.Frame(window, bg=BG, padx=18, pady=18)
        frame.pack(fill='both', expand=True)
        self.label(frame, '本次会话记录', 16, bold=True).pack(anchor='w', pady=(0, 10))
        text = tk.Text(frame, bg=PAPER, fg=INK, relief='flat', wrap='word', font=(FONT, 10), padx=14, pady=14)
        scroll = ttk.Scrollbar(frame, command=text.yview)
        scroll.pack(side='right', fill='y')
        text.configure(yscrollcommand=scroll.set)
        text.pack(fill='both', expand=True)
        text.insert('1.0', '\n'.join(self.history) or '暂无记录')
        text.configure(state='disabled')
        self.label(frame, '公开反馈时请先移除本机路径、设备标识和原始数据。', 9, MUTED).pack(anchor='w', pady=(10, 0))

    def help(self):
        window = tk.Toplevel(self.root)
        window.title('LumaLock · 使用说明')
        window.geometry('660x470')
        frame = tk.Frame(window, bg=BG, padx=28, pady=24)
        frame.pack(fill='both', expand=True)
        self.label(frame, '从检查到锁定，只需两步。', 19, bold=True).pack(anchor='w', pady=(0, 16))
        help_text = (
            '01  选择屏幕，点击「检查兼容性」。\n'
            '02  检查通过后，点击「固定高亮度」。\n\n'
            '「恢复自适应」会恢复面板的原始亮度曲线。\n'
            '设置写入运行内存，不刷固件；断电或休眠后可能需要重新应用。\n\n'
            '进度条显示当前阶段的实际完成量。写入到 100% 后，\n'
            '仍需等待读回校验和状态恢复，看到完成提示才能断开屏幕。\n\n'
            '适用：通过完整核验的 NE180QDM-NZ4 / NT71873 组合。\n'
            'Windows NVIDIA 已实测；AMD、Intel、Linux 仍属实验性。\n'
            '操作期间不要运行其他显示器控制工具。'
        )
        self.label(frame, help_text, 10, justify='left', anchor='nw', wraplength=600).pack(fill='both', expand=True)
        self.button(frame, '打开完整说明所在文件夹', lambda: open_folder(Path(__file__).resolve().parent.parent/'docs')).pack(anchor='w', pady=(12, 0))

    def logs(self):
        try:
            open_folder(runtime.state_dir())
        except OSError as exc:
            messagebox.showerror('无法打开记录目录', str(exc), parent=self.root)

    def close(self):
        if self.tasks.busy:
            messagebox.showinfo('操作仍在进行', '请等待当前操作或恢复结束后再关闭窗口。\n这能避免在曲线写入期间中断。', parent=self.root)
            return
        self.bar.stop()
        self.root.after_cancel(self.poll_after)
        self.root.after_cancel(self.scan_after)
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
