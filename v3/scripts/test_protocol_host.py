"""Focused regressions for the headless host used by native CI and ZIP smoke."""
import contextlib
import io
import os
import pathlib
import queue
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from protocol_test import Host, preserve_failure, temporary_work
from windows_cmdlet_probe import run_probe


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

    def test_sampler_deadline_reports_entry_stage_without_unbounded_output(self):
        stagefile = self.pidfile.with_suffix('.stage')
        stagefile.write_bytes(b'entered-before-set-content' + b'x' * 1000)
        with self.assertRaisesRegex(AssertionError, 'fixture stage=.*entered-before-set-content') as failure:
            self.host.sampler_pid('picker', self.pidfile, timeout=.02, stagefile=stagefile)
        self.assertLess(len(str(failure.exception)), 400)

    def test_sampler_deadline_distinguishes_no_script_entry(self):
        with self.assertRaisesRegex(AssertionError, 'script entry unconfirmed'):
            self.host.sampler_pid('picker', self.pidfile, timeout=.02, stagefile=self.pidfile.with_suffix('.stage'))


class FailureCleanupTests(unittest.TestCase):
    def test_eof_from_live_peer_does_not_block_on_open_stderr(self):
        host = Host.__new__(Host)
        host.messages = queue.Queue()
        host.messages.put(None)
        stderr = SimpleNamespace(read=lambda: self.fail('Live stderr read would defeat the deadline'))
        host.process = SimpleNamespace(poll=lambda: None, stderr=stderr)
        with self.assertRaisesRegex(AssertionError, 'Unexpected EOF: extension still running'):
            host.receive(timeout=.02)

    def test_cleanup_failure_without_primary_error_must_fail(self):
        def cleanup():raise PermissionError('owned fixture directory still in use')
        with self.assertRaisesRegex(PermissionError, 'still in use'):
            preserve_failure(cleanup)

    def test_process_cleanup_error_keeps_original_assertion_and_reports_both(self):
        host = Host.__new__(Host)
        primary = AssertionError('Temporary sampler startup deadline: PID file missing')
        with patch.object(host, '_cleanup', side_effect=RuntimeError('owned helper still live')):
            try:
                try:raise primary
                finally:host.cleanup()
            except AssertionError as failure:
                self.assertIs(failure, primary)
                self.assertIn('owned helper still live', '\n'.join(failure.__notes__))
            else:self.fail('Original readiness assertion was swallowed')

    def test_directory_cleanup_error_keeps_original_assertion_and_reports_both(self):
        primary = AssertionError('Temporary sampler startup deadline: PID file missing')
        with patch('protocol_test.tempfile.TemporaryDirectory') as directory:
            directory.return_value.name = 'owned-fixture'
            directory.return_value.cleanup.side_effect = PermissionError('WinError 32: directory in use')
            try:
                with temporary_work('fixture-'):raise primary
            except AssertionError as failure:
                self.assertIs(failure, primary)
                self.assertIn('WinError 32', '\n'.join(failure.__notes__))
            else:self.fail('Original readiness assertion was swallowed')
            directory.return_value.cleanup.assert_called_once_with()


class WindowsProbeTests(unittest.TestCase):
    def run_matrix(self, broken=None):
        owners, cleaned, closed = [], [], []
        class Job:
            def __init__(self, pid):owners.append(pid)
            def close(self):
                closed.append(True)
                if broken in ('job-cleanup', 'both-cleanup'):raise OSError('owned job close failed')
        class Peer:
            def __init__(self, binary, package, data, slug):
                self.name = data.name[:-5]
                self.work = package.parent
                self.process = SimpleNamespace(pid=123)
            def request(self, method, params):
                if len(owners) <= len(cleaned):raise AssertionError('Helper requested before tree ownership')
                return self.name
            def wait(self, identity, allow_error, timeout):
                if timeout != 6:raise AssertionError('Changed probe deadline')
                if self.name == broken or (broken == 'both-cleanup' and self.name == 'explicit-valid'):raise AssertionError('Response deadline ' + 'x' * 4000)
                if self.name.endswith('-invalid'):
                    (self.work / 'stage').write_text('before-write' if self.name == 'explicit-invalid' else 'entered')
                    cause = 'DirectoryNotFoundException; id=GetContentWriterDirectoryNotFoundError,Microsoft.PowerShell.Commands.SetContentCommand'
                    if broken == 'wrong-error' and self.name == 'explicit-invalid':cause = 'Modules_ModuleNotFound'
                    if broken == 'missing-module' and self.name == 'explicit-invalid':
                        (self.work / 'stage').write_text('before-import')
                        cause = 'DirectoryNotFoundException; id=Modules_ModuleNotFound'
                    return {'error': {'message': 'sampler-cmdlet-probe: ' + cause}}
                (self.work / 'stage').write_text('complete')
                if self.name.endswith('-valid') and broken != 'missing-write':
                    (self.work / "probe's.pid").write_bytes(b'12345\r\n')
                return {'result': {'mode': 'no-view'}}
            def cleanup(self):
                cleaned.append(self.name)
                if broken == 'both-cleanup':raise OSError('graceful fixture cleanup failed')
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()) as output:
            work = pathlib.Path(directory) / 'probe'
            failures = run_probe('fixture.exe', pathlib.Path(__file__).resolve().parents[1], work, Peer, Job)
        self.assertEqual(len(owners), 3)
        self.assertEqual(len(cleaned), 3)
        self.assertEqual(len(closed), 3)
        self.assertEqual(len(output.getvalue().splitlines()), 3)
        self.assertLess(len(output.getvalue()), 5000)
        if broken == 'both-cleanup':
            import json
            first = json.loads(output.getvalue().splitlines()[0].split(': ', 1)[1])
            self.assertIn('Response deadline', first['failure'])
            self.assertIn('graceful fixture cleanup failed', first['cleanup_failure'])
            self.assertIn('owned job close failed', first['job_cleanup_failure'])
        return failures

    def test_timeout_collects_remaining_cases_and_cleans_each_owned_tree(self):
        self.assertEqual(self.run_matrix('explicit-valid'), ['explicit-valid'])

    def test_production_check_failure_cannot_be_accepted_as_success(self):
        self.assertEqual(self.run_matrix('production-check'), ['production-check'])

    def test_import_error_cannot_impersonate_the_expected_write_error(self):
        self.assertEqual(self.run_matrix('wrong-error'), ['explicit-invalid'])

    def test_success_response_cannot_conceal_missing_write(self):
        self.assertEqual(self.run_matrix('missing-write'), ['explicit-valid'])

    def test_missing_module_directory_cannot_impersonate_missing_write_parent(self):
        self.assertEqual(self.run_matrix('missing-module'), ['explicit-invalid'])

    def test_job_cleanup_failure_fails_the_gate(self):
        self.assertEqual(self.run_matrix('job-cleanup'), ['explicit-valid', 'explicit-invalid', 'production-check'])

    def test_primary_timeout_survives_both_cleanup_failures(self):
        self.assertEqual(self.run_matrix('both-cleanup'), [
            'explicit-valid', 'explicit-valid', 'explicit-valid',
            'explicit-invalid', 'explicit-invalid', 'production-check', 'production-check'])



if __name__ == '__main__':
    unittest.main()
