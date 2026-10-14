"""Packaged recovery must launch the same app without interpreter flags."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from lumalock import runtime


class RuntimeTests(unittest.TestCase):
    def test_source_guard_command(self):
        with patch.object(sys, 'frozen', False, create=True):
            command = runtime.guard_command(Path('state.json'))
        self.assertEqual(command, [sys.executable, '-X', 'utf8', '-B', '-m',
                                   'lumalock', '--guard', 'state.json'])

    def test_frozen_guard_is_independent_and_has_no_python_flags(self):
        with patch.object(sys, 'frozen', True, create=True):
            self.assertEqual(runtime.guard_command('state.json'),
                             [sys.executable, '--guard', 'state.json'])
            before = os.environ.copy()
            env = runtime.guard_environment()
        self.assertEqual(env['PYINSTALLER_RESET_ENVIRONMENT'], '1')
        self.assertEqual(dict(os.environ), before)

    def test_windowed_streams_accept_output(self):
        with patch.object(sys, 'stdout', None), patch.object(sys, 'stderr', None):
            runtime.ensure_standard_streams()
            out, err = sys.stdout, sys.stderr
            try:
                print('progress', flush=True)
                err.write('diagnostic')
                runtime.ensure_standard_streams()
                self.assertIs(sys.stdout, out)
            finally:
                out.close()
                err.close()
