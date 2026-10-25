"""Headless Windows release regressions through the actual Rust sampler launch.

Use the package's shared trusted-OS bootstrap, never ambient module discovery.
Run serially, at most six seconds per request. Job ownership precedes helper
requests and includes Add-Type compiler children. The prior eight-case native
differential evidence is retained in the external report, not a failing gate.
"""
import ctypes
from ctypes import wintypes
import json
import pathlib
import time


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


class OwnedJob:
    def __init__(self, pid):
        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                        ('flags', wintypes.DWORD), ('min_working_set', ctypes.c_size_t),
                        ('max_working_set', ctypes.c_size_t), ('active_limit', wintypes.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                        ('scheduling', wintypes.DWORD)]
        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', ctypes.c_uint64 * 6),
                        ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                        ('peak_process_memory', ctypes.c_size_t), ('peak_job_memory', ctypes.c_size_t)]
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateJobObjectW': ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            'SetInformationJobObject': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            'OpenProcess': ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            'AssignProcessToJobObject': ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = args, result
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        process = None
        try:
            limits = Extended()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            process = self.kernel.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE
            if not process:raise ctypes.WinError(ctypes.get_last_error())
            if not self.kernel.AssignProcessToJobObject(self.handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            self.close()
            raise
        finally:
            if process:self.kernel.CloseHandle(process)

    def close(self):
        if self.handle:
            handle, self.handle = self.handle, None
            if not self.kernel.CloseHandle(handle):raise ctypes.WinError(ctypes.get_last_error())


def probe_cases(work, production):
    valid = work / "probe's.pid"
    invalid = work / 'missing-parent' / "probe's.pid"
    # Set-Content -Path matches the original failing fixture exactly. Only the
    # target-parent existence changes between the paired write cases.
    write = lambda path: '$PID | Set-Content -Path ' + literal(path)
    bootstrap = ("mark 'before-import'\n"
                 ". ($PSScriptRoot + '\\windows-modules.ps1') -IncludeManagement\n"
                 "mark 'before-write'\n")
    return [
        ('explicit-valid', bootstrap + write(valid), False),
        ('explicit-invalid', bootstrap + write(invalid), True),
        # Invoke the actual package sampler with its compile-only switch. No
        # DPI/capture/form code runs. Do not inherit the CI environment here.
        ('production-check', '& ' + literal(production) + " -Check\n"
         "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }", False),
    ]


def probe_script(body, stage):
    return ("$ErrorActionPreference = 'Stop'\n"
            'function mark($value) { [IO.File]::WriteAllText(' + literal(stage) + ', $value) }\n'
            "try {\nmark 'entered'\n" + body + "\nmark 'complete'\n[Console]::Write('null')\n"
            "} catch { [Console]::Error.Write('sampler-cmdlet-probe: ' + $_.Exception.GetType().FullName + '; id=' + $_.FullyQualifiedErrorId); exit 24 }\n")


def run_probe(binary, package, work, host_type, job_type=OwnedJob):
    work.mkdir()
    sampler = work / 'package' / 'resources' / 'sampler'
    sampler.mkdir(parents=True)
    helper, stage = sampler / 'windows.ps1', work / 'stage'
    production = (pathlib.Path(package) / 'resources' / 'sampler' / 'windows.ps1').resolve()
    (sampler / 'windows-modules.ps1').write_bytes(production.with_name('windows-modules.ps1').read_bytes())
    failures = []
    for name, body, expected_error in probe_cases(work, production):
        stage.unlink(missing_ok=True)
        (work / "probe's.pid").unlink(missing_ok=True)
        helper.write_text(probe_script(body, stage))
        host, job = None, None
        result = {'case': name}
        started = time.monotonic()
        try:
            host = host_type(binary, sampler.parent.parent, work / (name + '-data'), 'color-picker')
            job = job_type(host.process.pid)
            identity = host.request('session.open', {'sessionId': name, 'commandName': 'pick-color'})
            response = host.wait(identity, allow_error=True, timeout=6)
            result['outcome'] = 'error' if 'error' in response else 'ok'
            result['detail'] = repr(response.get('error', response.get('result')))[:768]
            if expected_error:
                assert 'error' in response and 'sampler-cmdlet-probe:' in result['detail'], 'Expected the real write failure'
                assert 'SetContentCommand' in result['detail'] and 'DirectoryNotFound' in result['detail'], 'Expected the Set-Content missing-parent write error, not lookup/import failure'
                assert stage.read_bytes() == b'before-write', 'Import did not reach the invalid-parent write'
            else:
                assert 'error' not in response, 'Probe operation failed'
                assert stage.read_bytes() == b'complete', 'Probe did not complete its script'
                if name.endswith('-valid'):
                    raw = (work / "probe's.pid").read_bytes()
                    result['pid_bytes'] = raw[:32].hex()
                    assert raw.strip().isdigit(), 'Probe did not publish a numeric PID'
        except Exception as error:
            result['failure'] = (type(error).__name__ + ': ' + str(error))[:768]
            failures.append(name)
        finally:
            try:
                if host is not None:host.cleanup()
            except Exception as error:
                result['cleanup_failure'] = (type(error).__name__ + ': ' + str(error))[:768]
                failures.append(name)
            finally:
                try:
                    if job is not None:job.close()
                except Exception as error:
                    result['job_cleanup_failure'] = (type(error).__name__ + ': ' + str(error))[:768]
                    failures.append(name)
        try:result['stage'] = stage.read_bytes()[:128].decode('ascii', errors='replace')
        except FileNotFoundError:result['stage'] = 'missing (entry unconfirmed)'
        result['seconds'] = round(time.monotonic() - started, 3)
        print('sampler-cmdlet-probe: ' + json.dumps(result), flush=True)
    # Collect all independent release regressions before failing the suite.
    # The caller additionally retains live PID/cancellation/disposal/EOF checks.
    return failures
