"""Offline UI checks; transport access is always mocked."""
import queue
import threading
import unittest
from unittest.mock import patch

try:
    import tkinter as tk
    from lumalock import gui
except ImportError:
    tk = None


@unittest.skipIf(tk is None, 'Tk is not installed')
class WorkerTests(unittest.TestCase):
    def test_worker_serializes_jobs_and_passes_exact_target(self):
        entered, release = threading.Event(), threading.Event()
        def run(action, display, backend, on_progress):
            entered.set()
            release.wait(3)
            on_progress(dict(stage='write', completed=1, total=43, message='write'))
            return {'success': True}
        with patch.object(gui.control, 'run', side_effect=run) as control:
            tasks = gui.Tasks()
            try:
                self.assertTrue(tasks.start('apply', 'intel:sample', 'intel'))
                self.assertTrue(entered.wait(2))
                self.assertFalse(tasks.start('restore', 'other', 'nvidia'))
            finally:
                release.set()
            self.assertEqual(tasks.events.get(timeout=3)[0], 'progress')
            self.assertEqual(tasks.events.get(timeout=3), ('result', {'success': True}))
            self.assertTrue(tasks.busy)  # UI must process completion before allowing another task.
            self.assertEqual(control.call_args.args, ('apply', 'intel:sample', 'intel'))

    def test_worker_exception_is_reported(self):
        with patch.object(gui.compatibility, 'list_displays', side_effect=RuntimeError('offline')):
            tasks = gui.Tasks()
            tasks.start('list')
            kind, result = tasks.events.get(timeout=3)
            self.assertEqual(kind, 'error')
            self.assertEqual(result['message'], 'offline')


@unittest.skipIf(tk is None, 'Tk is not installed')
class GuiTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.start = patch.object(gui.Tasks, 'start', return_value=False)
        self.start.start()
        self.addCleanup(self.start.stop)
        self.app = gui.App(self.root)
        self.addCleanup(self.cancel_timers)
        self.candidate = dict(candidate=True, endpoint_id='nvidia:sample', backend='nvidia')

    def cancel_timers(self):
        self.app.bar.stop()
        for timer in self.root.tk.call('after','info'):
            self.root.after_cancel(timer)

    def test_no_device_and_multiple_devices_require_selection(self):
        self.app.show_devices([])
        self.assertTrue(all(str(b['state'])=='disabled' for b in self.app.actions))
        self.app.show_devices([self.candidate, dict(self.candidate, endpoint_id='nvidia:other')])
        self.assertIsNone(self.app.selected())
        self.assertTrue(all(str(b['state'])=='disabled' for b in self.app.actions))
        self.app.device_choice.current(1)
        self.app.selection_changed()
        self.assertEqual(self.app.selected()['endpoint_id'],'nvidia:other')
        self.assertTrue(all(str(b['state'])=='normal' for b in self.app.actions))

    def test_active_job_locks_controls_and_window_close(self):
        self.app.show_devices([self.candidate])
        self.app.tasks.busy = True
        self.app.set_controls()
        self.assertTrue(all(str(b['state'])=='disabled' for b in self.app.actions))
        self.assertEqual(str(self.app.refresh['state']), 'disabled')
        with patch.object(gui.messagebox, 'showinfo') as info, patch.object(self.root, 'destroy') as close:
            self.app.close()
            info.assert_called_once()
            close.assert_not_called()

    def test_buttons_dispatch_selected_target_and_ignore_repeat_clicks(self):
        self.app.show_devices([self.candidate])
        def begin(*args):
            self.app.tasks.busy=True
            return True
        with patch.object(self.app.tasks,'start',side_effect=begin) as start:
            self.app.actions[1].invoke()
            start.assert_called_once_with('apply','nvidia:sample','nvidia')
            self.app.actions[1].invoke()
            self.app.actions[2].invoke()
            self.assertEqual(start.call_count,1)

    def test_write_percent_is_phase_local_not_success(self):
        self.app.update_progress(dict(stage='write', message='正在写入', completed=43, total=43))
        self.assertEqual(self.app.percent['text'], '100%')
        self.assertEqual(self.app.stage, 'write')
        self.app.update_progress(dict(stage='verify', message='读回校验', completed=None, total=None))
        self.assertNotEqual(self.app.percent['text'], '100%')
        self.assertEqual(str(self.app.bar['mode']), 'indeterminate')

    def test_result_and_pending_recovery(self):
        self.app.action = 'apply'
        self.app.finish(dict(success=True, after='fixed_high'))
        self.assertEqual(self.app.heading['text'], '高亮度已锁定')
        self.assertEqual(self.app.percent['text'], 'OK')
        self.app.finish(dict(success=False, error='failure', recovery_pending=True,
                             recovery_path='not-used', recovery_deadline=0))
        self.assertTrue(self.app.tasks.busy)
        self.assertEqual(self.app.heading['text'], '等待独立恢复')
        self.assertTrue(all(str(b['state'])=='disabled' for b in self.app.actions))

    def test_primary_controls_fit_at_minimum_window_size(self):
        self.root.geometry('1040x760')
        self.root.deiconify()
        self.root.update()
        for widget in [*self.app.actions,self.app.refresh,self.app.footer]:
            self.assertTrue(widget.winfo_ismapped())
            self.assertGreaterEqual(widget.winfo_height(),widget.winfo_reqheight())
            self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),
                                 self.root.winfo_rooty()+self.root.winfo_height())


if __name__ == '__main__':
    unittest.main()
