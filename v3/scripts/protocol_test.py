#!/usr/bin/env python3
"""Actual stdio executable regressions, with a headless generic fixture host.

No desktop effects: clipboard/tray/AI/notifications are acknowledged by this host.
The sampler is a temporary process fixture, never the live screen sampler.
"""
import argparse
import contextlib
import ctypes
import json
import os
import pathlib
import queue
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zlib


def preserve_failure(cleanup):
    """Keep the assertion primary while still reporting every cleanup failure."""
    primary=sys.exc_info()[1]
    try:cleanup()
    except Exception as error:
        if primary is None:raise
        note=f'Fixture cleanup also failed: {type(error).__name__}: {error}'
        if hasattr(primary,'add_note'):primary.add_note(note)
        else:
            primary.__notes__=getattr(primary,'__notes__',[])+[note]
            print(note,file=sys.stderr)  # Python 3.9/3.10 traceback lacks notes.


@contextlib.contextmanager
def temporary_work(prefix):
    work=tempfile.TemporaryDirectory(prefix=prefix)
    try:yield pathlib.Path(work.name)
    finally:preserve_failure(work.cleanup)


class Host:
    def __init__(self, binary, package, data, slug, migration=None):
        self.package, self.data, self.slug = pathlib.Path(package), pathlib.Path(data), slug
        self.calls, self.events, self.responses = [], [], {}
        self.policy = lambda message: True
        self.messages = queue.Queue()
        # Python uppercases Windows environment keys, including SYSTEMROOT.
        env = {k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','TEMP','TMP')}
        windows_root = next((v for k,v in env.items() if k.upper()=='SYSTEMROOT'),'C:/Windows')
        env['PATH'] = os.path.join(windows_root,'System32') if os.name=='nt' else '/usr/bin:/bin'
        self.process = subprocess.Popen([str(pathlib.Path(binary).resolve())], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=package, env=env)
        def read():
            for line in self.process.stdout: self.messages.put(json.loads(line))
            self.messages.put(None)
        threading.Thread(target=read,daemon=True).start()
        hello = self.receive()
        assert hello['type']=='hello' and hello['id']=='com.tezbar.native.'+slug and hello['protocol']==1,hello
        self.invoke('initialize',{'protocol':1,'extensionId':hello['id'],'platform':'x86_64-pc-windows-msvc' if os.name=='nt' else 'aarch64-apple-darwin',
                                 'packageDir':str(self.package.resolve()),'dataDir':str(self.data.resolve()),'tempDir':str((self.data/'tmp').resolve()),
                                 'grantedCapabilities':['clipboard','window','selection','screen','shell','settings','ai','tray','background','notifications'],
                                 'migrationPaths':migration or {},'reason':'process-regression'})
    def receive(self,timeout=6):
        value=self.messages.get(timeout=timeout)
        if value is None:
            # EOF is a protocol failure even if a broken peer keeps stderr
            # open; do not let its diagnostic read defeat cleanup's deadline.
            detail=self.process.stderr.read().decode() if self.process.poll() is not None else 'extension still running'
            raise AssertionError('Unexpected EOF: '+detail)
        return value
    def send(self,value):
        self.process.stdin.write((json.dumps(value,ensure_ascii=False)+'\n').encode());self.process.stdin.flush()
    def request(self,method,params):
        identity='h:'+str(uuid.uuid4());self.send({'type':'request','id':identity,'method':method,'params':params});return identity
    def reply(self,request,value=True,error=None):
        response={'type':'response','id':request['id']}
        if error:response['error']={'code':'fixture_denied','message':error}
        else:response['result']=value
        self.send(response)
    def route(self,message):
        if message['type']=='request':
            self.calls.append(message)
            result=self.policy(message)
            if isinstance(result,Exception):self.reply(message,error=str(result))
            else:self.reply(message,result)
        elif message['type']=='event':self.events.append(message)
        elif message['type']=='response':self.responses[message['id']]=message
        else:assert message['type']=='cancel',message
    def wait(self,identity,allow_error=False,timeout=8):
        deadline=time.monotonic()+timeout
        while identity not in self.responses:
            assert time.monotonic()<deadline,'Response deadline'
            try:self.route(self.receive(min(.1,max(0,deadline-time.monotonic()))))
            except queue.Empty:pass
        response=self.responses.pop(identity)
        if not allow_error:assert 'error' not in response,response
        return response
    def invoke(self,method,params,allow_error=False):return self.wait(self.request(method,params),allow_error)
    def open(self,session,command,preferences=None,arguments=None):
        return self.invoke('session.open',{'sessionId':session,'commandName':command,'preferences':preferences or {},'argumentValues':arguments or {}})['result']
    def action(self,session,action,form=None):
        return self.invoke('session.call',{'sessionId':session,'operation':'extension:invoke-action','payload':{'actionId':action,'formValues':form or {}}})['result']
    def store(self):return json.loads((self.data/self.slug/'storage.json').read_text())
    def write_store(self,value):
        path=self.data/self.slug/'storage.json';temp=path.with_suffix('.fixture');temp.write_text(json.dumps(value));temp.replace(path)
    def until(self,predicate,timeout=6):
        deadline=time.monotonic()+timeout
        while not predicate():
            assert time.monotonic()<deadline,'Condition deadline'
            try:self.route(self.receive(.1))
            except queue.Empty:pass
    def sampler_pid(self,identity,pidfile,timeout=6,stagefile=None):
        deadline=time.monotonic()+timeout
        while True:
            assert identity not in self.responses, (
                'Temporary sampler returned before publishing PID: '+repr(self.responses.get(identity))[:2048])
            try:
                raw=pidfile.read_bytes()
                evidence='PID file bytes='+raw[:32].hex()+f' (length={len(raw)})'
                if raw.strip().isdigit():return int(raw)
            except FileNotFoundError:evidence='PID file missing'
            except OSError as error:evidence=f'PID file unreadable: {type(error).__name__} errno={error.errno}'
            if stagefile is not None:
                try:evidence+='; fixture stage='+repr(stagefile.read_bytes()[:128])
                except FileNotFoundError:evidence+='; fixture stage missing (script entry unconfirmed)'
                except OSError as error:evidence+=f'; fixture stage unreadable: {type(error).__name__} errno={error.errno}'
            assert time.monotonic()<deadline, (
                f'Temporary sampler startup deadline ({timeout}s): {evidence}; extension exit={self.process.poll()}')
            try:self.route(self.receive(min(.1,max(0,deadline-time.monotonic()))))
            except queue.Empty:pass
    def finish(self,eof=False,timeout=5):
        deadline=time.monotonic()+timeout
        if self.process.poll() is None:
            if eof:
                self.process.stdin.close()
            else:
                self.wait(self.request('shutdown',{}),timeout=timeout)
            self.process.wait(timeout=max(.001,deadline-time.monotonic()))
        assert self.process.returncode==0,self.process.stderr.read().decode()
        if not self.process.stdin.closed:self.process.stdin.close()
        self.process.stdout.close();self.process.stderr.close()
    def cleanup(self):
        preserve_failure(self._cleanup)
    def _cleanup(self):
        # Let SDK shutdown cancel sessions/drop owned sampler handles before a
        # hard fallback. Do not reuse a deliberately denying test policy here.
        self.policy=lambda message:True
        try:
            try:self.finish(timeout=5)
            except Exception as shutdown_error:
                if not self.process.stdin.closed:self.process.stdin.close()
                try:self.process.wait(timeout=5)  # SDK EOF cancellation fallback.
                except subprocess.TimeoutExpired:
                    self.process.kill();self.process.wait(timeout=3)
                    raise AssertionError('Fixture required hard termination after shutdown and EOF') from shutdown_error
                raise AssertionError('Fixture graceful shutdown failed; EOF fallback completed') from shutdown_error
        finally:
            for pipe in (self.process.stdin,self.process.stdout,self.process.stderr):
                if not pipe.closed:pipe.close()


def png(path):
    def chunk(t,d):return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0\x0c\x22\x38\xff'))+chunk(b'IEND',b''))


def action_id(view,title):
    return next(action['id'] for action in view['actions'] if action['title']==title)


def windows_pid_script(pidfile,stagefile):
    # Keep the failing cmdlet path for the next native evidence round. .NET
    # markers distinguish script entry, PID publication and a fatal write error.
    # PowerShell single-quoted literals escape apostrophes by doubling them.
    pid=str(pidfile).replace("'","''");stage=str(stagefile).replace("'","''")
    return ("$ErrorActionPreference = 'Stop'\ntry {\n"
            "[IO.File]::WriteAllText('"+stage+"', 'entered-before-set-content')\n"
            "$PID | Set-Content -Path '"+pid+"'\n"
            "[IO.File]::WriteAllText('"+stage+"', 'pid-written-before-start-sleep')\n"
            "Start-Sleep -Seconds 60\n"
            "} catch { [Console]::Error.Write('sampler-fixture-pid: ' + $_.Exception.ToString()); exit 24 }\n")


def sampler_cleanup_regression(binary, work):
    # Reproduce a readiness failure only AFTER proving a real owned helper live.
    # A different PID path models the native missing-file symptom without
    # depending on Windows cmdlet behavior to trigger the failure cleanup path.
    sampler=work/"cleanup's package"/'resources'/'sampler';sampler.mkdir(parents=True)
    helper=sampler/('windows.ps1' if os.name=='nt' else 'color-picker-helper')
    pidfile=work/"cleanup's.pid"
    if os.name=='nt':
        helper.write_text("[IO.File]::WriteAllText('"+str(pidfile).replace("'","''")+"', [string]$PID); [Threading.Thread]::Sleep(60000)")
    else:
        helper.write_text('#!/bin/sh\necho $$ > "'+str(pidfile)+'"\nexec /bin/sleep 60\n');helper.chmod(0o755)
    h=Host(binary,sampler.parent.parent,work/'cleanup-data','color-picker')
    pid=None
    try:
        try:
            identity=h.request('session.open',{'sessionId':'cleanup-picker','commandName':'pick-color'})
            pid=h.sampler_pid(identity,pidfile)
            assert not process_gone(pid),'Cleanup regression requires a live owned helper'
            h.sampler_pid(identity,work/'intentionally-missing.pid',timeout=.03)
        finally:h.cleanup()
    except AssertionError as failure:
        assert 'PID file missing' in str(failure),failure
        assert not getattr(failure,'__notes__',[]),failure.__notes__
    else:raise AssertionError('Cleanup regression must enter the readiness failure path')
    assert pid is not None
    deadline=time.monotonic()+6
    while not process_gone(pid):
        assert time.monotonic()<deadline,'Owned temporary sampler survived fixture cleanup'
        time.sleep(.01)
    # Also cover EOF with an in-flight sampler, rather than only an idle SDK.
    pidfile.unlink()
    h=Host(binary,sampler.parent.parent,work/'cleanup-eof-data','color-picker')
    try:
        identity=h.request('session.open',{'sessionId':'eof-picker','commandName':'pick-color'})
        pid=h.sampler_pid(identity,pidfile)
        assert not process_gone(pid),'EOF regression requires a live owned helper'
        h.finish(eof=True)
        deadline=time.monotonic()+6
        while not process_gone(pid):
            assert time.monotonic()<deadline,'Owned temporary sampler survived SDK EOF'
            time.sleep(.01)
    finally:h.cleanup()


def process_gone(pid):
    if os.name=='nt':
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong]
        kernel.OpenProcess.restype=ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:
            error=ctypes.get_last_error()
            assert error==87,f'Cannot inspect owned temporary sampler {pid}: WinError {error}'
            return True
        try:
            code=ctypes.c_ulong()
            assert kernel.GetExitCodeProcess(handle,ctypes.byref(code))
            return code.value!=259
        finally:kernel.CloseHandle(handle)
    try:os.kill(pid,0);return False
    except ProcessLookupError:return True


def color_suite(binary,package,work):
    sampler_cleanup_regression(binary,work)
    data=work/'color-data'
    h=Host(binary,package,data,'color-picker')
    try:
        h.policy=lambda m: ('hsl(120 100% 50%)' if m['method']=='host.selection.read' else '["#123456","#abcdef"]' if m['method']=='host.ai.ask' else True)
        view=h.open('convert','convert-color')
        h.action('convert',view['root']['children'][0]['props']['actionIds'][0])
        assert next(m for m in h.calls if m['method']=='host.clipboard.write')['params']['text']=='#00FF00'
        h.open('generate','generate-colors',arguments={'prompt':'Ocean'})
        ai=next(m for m in h.calls if m['method']=='host.ai.ask')
        assert 'Ocean' in ai['params']['prompt'] and ai['params']['options']=={'stream':False}
        image=work/'fixture.png';png(image)
        h.policy=lambda m: [str(image)] if m['method']=='host.selection.read' else True
        extract=h.open('extract','extract-color')
        assert extract['root']['children'][0]['props']['content']['color']=='#0C2238'
        saved=h.store();saved['history']=[{'color':'#00FF00','isFavorite':False}];h.write_store(saved)
        h.open('menu','menu-bar')
        methods=[m['method'] for m in h.calls]
        assert methods.index('host.background.retain')<methods.index('host.tray.set')
        menu=next(m for m in reversed(h.calls) if m['method']=='host.tray.set')['params']
        assert any(i['id']=='copy-00FF00' for i in menu['items'])
        h.invoke('session.dispose',{'sessionId':'menu'})
        assert not any(m['method']=='host.tray.remove' for m in h.calls)
        # Component-safe callback still works after every view owning that command closes.
        h.invoke('background.event',{'resourceId':'color-picker','actionId':'copy-00FF00'})
        assert [m for m in h.calls if m['method']=='host.clipboard.write'][-1]['params']['text']=='#00FF00'
        h.invoke('background.event',{'resourceId':'color-picker','actionId':'configure'})
        assert any(m['method']=='host.settings.open' for m in h.calls)
        h.invoke('background.event',{'resourceId':'color-picker','actionId':'delete-00FF00'})
        assert not h.store()['history']
        h.invoke('background.event',{'resourceId':'color-picker','actionId':'hide'})
        assert [m['method'] for m in h.calls][-2:]==['host.tray.remove','host.background.release']
        h.open('menu-again','menu-bar')
        h.finish()
        assert [m['method'] for m in h.calls][-2:]==['host.tray.remove','host.background.release']
    finally:h.cleanup()
    # Denied retain must not create a tray; cancelled creation cleanup owns the
    # tray lock until both removal and lease release complete, even if reopened.
    h=Host(binary,package,work/'tray-cancel-data','color-picker')
    try:
        h.policy=lambda m: False if m['method']=='host.background.retain' else True
        assert 'error' in h.invoke('session.open',{'sessionId':'denied-tray','commandName':'menu-bar'},allow_error=True)
        h.until(lambda:any(m['method']=='host.background.release' for m in h.calls))
        assert not any(m['method']=='host.tray.set' for m in h.calls)
        h.policy=lambda m:True
        pending=h.request('session.open',{'sessionId':'cancelled-tray','commandName':'menu-bar'})
        while True:
            frame=h.receive()
            if frame.get('method')=='host.background.retain':break
            h.route(frame)
        h.send({'type':'cancel','requestId':pending,'reason':'cancel tray registration'})
        # Hold cleanup's remove acknowledgement while immediately opening a new tray.
        while True:
            cleanup=h.receive()
            if cleanup.get('method')=='host.tray.remove':break
            h.route(cleanup)
        reopened=h.request('session.open',{'sessionId':'new-tray','commandName':'menu-bar'})
        try:
            while True:
                frame=h.receive(.15)
                assert frame.get('method') not in ('host.background.retain','host.tray.set'), frame
                h.route(frame)
        except queue.Empty:pass
        h.reply(cleanup)
        h.wait(reopened)
        h.wait(pending,allow_error=True)
        assert h.calls[-1]['method']=='host.tray.set'
        h.invoke('session.dispose',{'sessionId':'new-tray'})
        h.invoke('background.event',{'resourceId':'color-picker','actionId':'configure'})
        hidden=h.request('background.event',{'resourceId':'color-picker','actionId':'hide'})
        removal=h.receive();assert removal.get('method')=='host.tray.remove'
        h.send({'type':'cancel','requestId':hidden,'reason':'cancel hide response'})
        h.wait(hidden,allow_error=True)
        h.reply(removal)
        h.until(lambda:h.calls[-1]['method']=='host.background.release')
        h.finish()
    finally:h.cleanup()
    # Cancellation and success run a real temporary helper process, no desktop UI.
    sampler=work/'sampler-package'/'resources'/'sampler';sampler.mkdir(parents=True)
    helper=sampler/('windows.ps1' if os.name=='nt' else 'color-picker-helper')
    pidfile=work/'sampler.pid';stagefile=work/'sampler.stage'
    if os.name=='nt':helper.write_text("[Console]::Error.Write('sampler-fixture-intentional-failure'); exit 23")
    else:helper.write_text("#!/bin/sh\nprintf '%s' 'sampler-fixture-intentional-failure' >&2\nexit 23\n");helper.chmod(0o755)
    h=Host(binary,sampler.parent.parent,work/'sampler-data','color-picker')
    try:
        # An actual helper's early stderr/error response must explain startup
        # failure immediately, rather than being hidden behind the PID deadline.
        failed=h.request('session.open',{'sessionId':'failed-picker','commandName':'pick-color'})
        try:h.sampler_pid(failed,pidfile)
        except AssertionError as error:
            assert 'sampler-fixture-intentional-failure' in str(error),error
        else:raise AssertionError('Failing sampler unexpectedly published a PID')
        assert 'error' in h.wait(failed,allow_error=True)
        if os.name=='nt':
            # The same instrumented fixture must fail immediately on an actual
            # write/command error, including paths containing apostrophes.
            helper.write_text(windows_pid_script(work/'missing-parent'/"sampler's.pid",stagefile))
            failed=h.request('session.open',{'sessionId':'failed-write-picker','commandName':'pick-color'})
            try:h.sampler_pid(failed,pidfile,stagefile=stagefile)
            except AssertionError as error:assert 'sampler-fixture-pid:' in str(error),error
            else:raise AssertionError('Invalid fixture write unexpectedly published a PID')
            assert 'error' in h.wait(failed,allow_error=True)
            stagefile.unlink()  # The next attempt must prove its own script entry.
            helper.write_text(windows_pid_script(pidfile,stagefile))
        else:helper.write_text('#!/bin/sh\necho $$ > "'+str(pidfile)+'"\nexec /bin/sleep 60\n');helper.chmod(0o755)
        identity=h.request('session.open',{'sessionId':'picker','commandName':'pick-color','preferences':{},'argumentValues':{}})
        pid=h.sampler_pid(identity,pidfile,stagefile=stagefile if os.name=='nt' else None)
        def gone():return process_gone(pid)
        assert not gone(),'Temporary sampler must be running before cancellation'
        dispose=h.request('session.dispose',{'sessionId':'picker'})
        h.wait(dispose)
        assert 'error' in h.wait(identity,allow_error=True)
        h.until(lambda:any(m['method']=='host.window.suppressBlur' and m['params']['suppress'] is False for m in h.calls))
        h.until(gone)
        if os.name=='nt':helper.write_text("[Console]::Write('{\"red\":1,\"green\":0,\"blue\":0,\"alpha\":1,\"colorSpace\":\"srgb\"}')")
        else:helper.write_text("#!/bin/sh\nprintf '%s' '{\"red\":1,\"green\":0,\"blue\":0,\"alpha\":1,\"colorSpace\":\"srgb\"}'\n");helper.chmod(0o755)
        assert h.open('picked','pick-color')['mode']=='no-view'
        assert [m for m in h.calls if m['method']=='host.clipboard.write'][-1]['params']['text']=='#FF0000'
        h.finish(eof=True)
    finally:h.cleanup()
    # Native-v2 import preserves unknown keys and current history without reimport.
    legacy=work/'native-color.json';legacy.write_text(json.dumps({'history':[{'color':'#123456','isFavorite':True,'title':'Brand'}],'future':42}))
    original=legacy.read_bytes()
    h=Host(binary,package,work/'migrated-color','color-picker',{'native-v2-store':str(legacy)})
    try:
        h.open('favorites','favorite-colors');assert h.store()['history'][0]['title']=='Brand';assert h.store()['future']==42
        assert legacy.read_bytes()==original
        h.finish()
    finally:h.cleanup()


def timers_suite(binary,package,work):
    h=Host(binary,package,work/'timers-data','timers')
    try:
        h.open('manager','manageTimers')
        assert not h.calls,'Idle manager must not acquire a lease or start notifications'
        pending=h.request('session.open',{'sessionId':'denied','commandName':'start2MinuteTimer','preferences':{},'argumentValues':{}})
        retain=h.receive();assert retain['method']=='host.background.retain' and retain['params']['durable'] is True
        assert not h.store().get('timers'),'Active state was written before durable retain acknowledgement'
        h.reply(retain,error='durable registration denied')
        assert 'error' in h.wait(pending,allow_error=True)
        assert not h.store().get('timers')
        cancelled=h.request('session.open',{'sessionId':'cancelled-retain','commandName':'start2MinuteTimer','preferences':{},'argumentValues':{}})
        while True:
            frame=h.receive()
            if frame.get('method')=='host.background.retain':break
            h.route(frame)
        h.send({'type':'cancel','requestId':cancelled,'reason':'fixture-cancel'})
        assert 'error' in h.wait(cancelled,allow_error=True)
        h.until(lambda:any(m['method']=='host.background.release' for m in h.calls))
        assert not h.store().get('timers')
        h.open('timer','start2MinuteTimer')
        assert h.store()['timers'][0]['status']=='running'
        assert h.calls[-1]['method']=='host.background.retain'
        h.invoke('session.dispose',{'sessionId':'timer'})
        timer=h.store()['timers'][0]['id']
        assert h.store()['timers'][0]['status']=='running'
        h.action('manager','timers:pause:'+timer)
        assert h.store()['timers'][0]['status']=='paused'
        h.until(lambda:any(m['method']=='host.background.release' for m in h.calls))
        h.action('manager','timers:resume:'+timer)
        assert h.store()['timers'][0]['status']=='running'
        assert len([m for m in h.calls if m['method']=='host.background.retain'])==2
        # EOF must stop worker promptly while preserving active state for restoration.
        h.finish(eof=True)
    finally:h.cleanup()
    h=Host(binary,package,work/'timers-data','timers')
    try:
        assert not h.calls
        h.invoke('background.activate',{'key':'timers'})
        assert h.calls[0]['method']=='host.background.retain'
        h.open('manager','manageTimers')
        h.action('manager','timers:stop:'+timer)
        h.until(lambda:h.calls[-1]['method']=='host.background.release')
        assert not h.store()['timers']
        h.finish()
    finally:h.cleanup()
    # Cancellation abandons the activation response, never persisted pending work.
    legacy_cancel=work/'activation-timers.json'
    legacy_cancel.write_text(json.dumps({'timers':[{'id':'restore','name':'Tea','status':'finished','soundPlayed':True,'notificationSent':False}]}))
    h=Host(binary,package,work/'activation-data','timers',{'native-v2-store':str(legacy_cancel)})
    try:
        activation=h.request('background.activate',{'key':'timers'})
        retain=h.receive();assert retain.get('method')=='host.background.retain'
        h.send({'type':'cancel','requestId':activation,'reason':'cancel activation response'})
        h.wait(activation,allow_error=True)
        h.reply(retain)
        h.until(lambda:h.store()['timers'][0]['notificationSent'] is True)
        h.until(lambda:h.calls[-1]['method']=='host.background.release')
        h.finish()
    finally:h.cleanup()
    # Completed, silent fixtures exercise real reverse notification acknowledgement,
    # failed delivery/retry, removal/retry, and idle release with no audio or GUI.
    legacy=work/'old-timers.json'
    legacy.write_text(json.dumps({'timers':[{'id':'due','name':'Tea','status':'finished','durationMs':1000,'soundPlayed':True,'notificationSent':False,'lastNotificationAttempt':0}], 'presets':[{'id':'saved','name':'Focus','durationMs':120000,'sound':'alarmClock.wav'}],'future':77}))
    original=legacy.read_bytes()
    h=Host(binary,package,work/'notification-data','timers',{'native-v2-store':str(legacy)})
    denied=[True]
    try:
        h.policy=lambda m: RuntimeError('notification denied') if m['method']=='host.notifications.show' and denied[0] else True
        h.invoke('background.activate',{'key':'timers'})
        h.until(lambda:bool(h.store()['timers'][0].get('lastNotificationAttempt')))
        assert h.store()['timers'][0]['notificationSent'] is False
        assert h.store()['future']==77 and h.store()['presets'][0]['name']=='Focus'
        assert legacy.read_bytes()==original
        # Restart with a deterministic pending retry timestamp, avoiding a 30s sleep.
        h.finish(eof=True)
    finally:h.cleanup()
    data=work/'notification-data';path=data/'timers'/'storage.json';store=json.loads(path.read_text());store['timers'][0]['lastNotificationAttempt']=0;path.write_text(json.dumps(store))
    h=Host(binary,package,data,'timers')
    try:
        h.invoke('background.activate',{'key':'timers'})
        h.until(lambda:h.store()['timers'][0]['notificationSent'] is True)
        show=next(m for m in h.calls if m['method']=='host.notifications.show')
        assert show['params']=={'id':'due','title':'Ding!','body':'Timer "Tea" complete'}
        h.until(lambda:h.calls[-1]['method']=='host.background.release')
        h.policy=lambda m:RuntimeError('remove denied') if m['method']=='host.notifications.remove' else True
        h.open('manager','manageTimers')
        h.action('manager','timers:stop:due')
        assert h.store()['pendingNotificationRemovals'][0]['id']=='due'
        h.finish(eof=True)
    finally:h.cleanup()
    store=json.loads(path.read_text());store['pendingNotificationRemovals'][0]['lastAttempt']=0;path.write_text(json.dumps(store))
    h=Host(binary,package,data,'timers')
    try:
        h.invoke('background.activate',{'key':'timers'})
        h.until(lambda:not h.store()['pendingNotificationRemovals'])
        h.until(lambda:h.calls[-1]['method']=='host.background.release')
        assert any(m['method']=='host.notifications.remove' for m in h.calls)
        h.finish()
    finally:h.cleanup()


def run(binary,package,slug):
    info=json.loads(subprocess.check_output([str(pathlib.Path(binary).resolve()),'--protocol-info'],timeout=5))
    manifest=json.loads((pathlib.Path(package)/'extension.json').read_text())
    assert info['id']==manifest['id'] and info['version']==manifest['version']
    assert set(info['commands'])=={c['name'] for c in manifest['commands']}
    with temporary_work(prefix=slug+'-stdio-') as work:
        (color_suite if slug=='color-picker' else timers_suite)(binary,pathlib.Path(package),work)
    print(json.dumps({'passed':True,'slug':slug,'commands':len(info['commands']),'realProcess':True,'desktopEffects':False,'windowsVerified':os.name=='nt'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--binary',required=True);parser.add_argument('--package',type=pathlib.Path,required=True);parser.add_argument('--slug',required=True);args=parser.parse_args()
    run(args.binary,args.package,args.slug)
