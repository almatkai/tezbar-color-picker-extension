"""Focused regressions for the headless host used by native CI and ZIP smoke."""
import os
import pathlib
import queue
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from protocol_test import Host


class HostEnvironmentTests(unittest.TestCase):
    def test_windows_environment_keeps_os_variables_and_excludes_secrets(self):
        # Python's Windows os.environ iterates uppercase keys. Exercise the
        # actual Host -> Popen boundary without requiring a Windows binary.
        source = {
            'SYSTEMROOT': r'D:\Windows',
            'WINDIR': r'D:\Windows',
            'TEMP': r'D:\Temp',
            'TMP': r'D:\Temp',
            'PATH': r'D:\untrusted-toolchain',
            'FIXTURE_SECRET': 'must-not-be-inherited',
        }
        with tempfile.TemporaryDirectory() as work:
            with patch('protocol_test.os', SimpleNamespace(environ=source, name='nt', path=os.path)), \
                 patch('protocol_test.subprocess.Popen', return_value=SimpleNamespace(stdout=[])) as spawn, \
                 patch.object(Host, 'receive', return_value={
                     'type': 'hello', 'id': 'com.tezbar.native.color-picker', 'protocol': 1,
                 }), \
                 patch.object(Host, 'invoke'):
                Host('fixture.exe', pathlib.Path(work), pathlib.Path(work), 'color-picker')
            env = spawn.call_args.kwargs['env']
        self.assertEqual(env.get('SYSTEMROOT'), source['SYSTEMROOT'])
        self.assertEqual(env['WINDIR'], source['WINDIR'])
        self.assertEqual(env['TEMP'], source['TEMP'])
        self.assertEqual(env['TMP'], source['TMP'])
        self.assertEqual(env['PATH'], str(pathlib.Path(source['SYSTEMROOT']) / 'System32'))
        self.assertNotIn('FIXTURE_SECRET', env)
        self.assertEqual(set(env), {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'PATH'})


class SamplerStartupTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.pidfile = pathlib.Path(self.work.name) / 'sampler.pid'
        self.host = Host.__new__(Host)
        self.host.responses = {}
        self.host.messages = queue.Queue()
        self.host.process = SimpleNamespace(poll=lambda: None)

    def test_sampler_launch_error_is_reported_before_pid_deadline(self):
        self.host.messages.put({
            'type': 'response', 'id': 'picker',
            'error': {'code': 'handler_error', 'message': 'Cannot launch native color sampler: fixture failure'},
        })
        with self.assertRaisesRegex(AssertionError, 'Cannot launch native color sampler: fixture failure'):
            self.host.sampler_pid('picker', self.pidfile, timeout=.02)

    def test_sampler_completion_without_pid_is_not_silently_accepted(self):
        self.host.responses['picker'] = {'type': 'response', 'id': 'picker', 'result': {'mode': 'no-view'}}
        with self.assertRaisesRegex(AssertionError, 'returned before publishing PID'):
            self.host.sampler_pid('picker', self.pidfile, timeout=.02)

    def test_sampler_deadline_distinguishes_missing_pid_file(self):
        with self.assertRaisesRegex(AssertionError, 'PID file missing'):
            self.host.sampler_pid('picker', self.pidfile, timeout=.02)

    def test_sampler_deadline_reports_bounded_invalid_pid_bytes(self):
        self.pidfile.write_bytes(b'not-a-pid' * 100)
        with self.assertRaisesRegex(AssertionError, 'PID file bytes=6e6f742d612d706964') as failure:
            self.host.sampler_pid('picker', self.pidfile, timeout=.02)
        self.assertLess(len(str(failure.exception)), 400)

    def test_sampler_returns_pid_without_changing_cancellation_precondition(self):
        self.pidfile.write_bytes(b'12345\r\n')
        self.assertEqual(self.host.sampler_pid('picker', self.pidfile, timeout=.02), 12345)


if __name__ == '__main__':
    unittest.main()
