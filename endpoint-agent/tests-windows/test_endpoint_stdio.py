"""Windows process lifecycle/Ed25519 unit tests; no kit installation, firewall changes or MCP execution."""
import base64
import ctypes
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('stdio_windows',ROOT/'endpoint-agent/stdio_windows.py')
windows=importlib.util.module_from_spec(spec)
spec.loader.exec_module(windows)


@unittest.skipUnless(os.name=='nt','Windows Job Object required')
class WindowsProcess(unittest.TestCase):
    def test_ctypes_user_creation_inherits_only_pipes_and_binds_before_resume(self):
        events, inherited = [], []
        kernel, security, sessions = Mock(), Mock(), Mock()
        kernel.InitializeProcThreadAttributeList.side_effect = lambda data, count, flags, size: (
            setattr(size._obj, 'value', 64) or True)
        def attribute(data, flags, key, handles, size, previous, returned):
            self.assertEqual(key, 0x20002)
            inherited.extend(handles)
            return True
        kernel.UpdateProcThreadAttribute.side_effect = attribute
        def create(token, app, command, pa, ta, inherit, flags, env, cwd, startup, info):
            events.append('create')
            self.assertEqual(token, 70)
            self.assertTrue(inherit)
            self.assertEqual(flags & (0x4 | 0x80000 | 0x400), 0x4 | 0x80000 | 0x400)
            self.assertEqual(set(inherited), {startup._obj.startup.stdin, startup._obj.startup.stdout, startup._obj.startup.stderr})
            self.assertEqual(env[:env[:].index('\0')], 'LANG=C.UTF-8')
            info._obj.process, info._obj.thread, info._obj.pid = 71, 72, 73
            return True
        security.CreateProcessAsUserW.side_effect = create
        kernel.AssignProcessToJobObject.side_effect = lambda *args: events.append('bind') or True
        kernel.ResumeThread.side_effect = lambda *args: events.append('resume') or 1
        job = windows.Job.__new__(windows.Job)
        job.kernel, job.handle = kernel, 69
        with patch.object(windows.C, 'WinDLL', side_effect=lambda name, **kw: security if name == 'advapi32' else sessions), \
                patch.object(windows, 'user_token', return_value=70) as token:
            child = job.start([sys.executable, '-I'], sid='S-1-5-21-1-2-3-1001', cwd=ROOT, env={'LANG':'C.UTF-8'})
        self.assertEqual(events, ['create', 'bind', 'resume'])
        self.assertEqual(child.pid, 73)
        token.assert_called_once()
        kernel.DeleteProcThreadAttributeList.assert_called_once()
        self.assertIn(unittest.mock.call(70), kernel.CloseHandle.call_args_list)
        self.assertIn(unittest.mock.call(72), kernel.CloseHandle.call_args_list)
        for stream in (child.stdin, child.stdout, child.stderr):
            stream.close()
        child.handle = None
        inherited.clear()
        kernel.AssignProcessToJobObject.side_effect = lambda *args: False
        kernel.ResumeThread.reset_mock()
        with patch.object(windows.C, 'WinDLL', side_effect=lambda name, **kw: security if name == 'advapi32' else sessions), \
                patch.object(windows, 'user_token', return_value=70), patch.object(job, 'close') as close:
            with self.assertRaisesRegex(OSError, '결속'):
                job.start([sys.executable], sid='S-1-5-21-1-2-3-1001', cwd=ROOT, env={'LANG':'C.UTF-8'})
        kernel.ResumeThread.assert_not_called()
        kernel.TerminateProcess.assert_called_once_with(71, 1)
        close.assert_called_once()

    def test_missing_session_never_creates_a_process(self):
        kernel, security, sessions = Mock(), Mock(), Mock()
        job = windows.Job.__new__(windows.Job)
        job.kernel, job.handle = kernel, 1
        with patch.object(windows.C, 'WinDLL', side_effect=lambda name, **kw: security if name == 'advapi32' else sessions), \
                patch.object(windows, 'user_token', side_effect=OSError('등록된 직원의 로그온 세션이 없습니다')), \
                patch.object(job, 'close', return_value=True):
            with self.assertRaisesRegex(OSError, '로그온 세션'):
                job.start([sys.executable], sid='S-1-5-21-1-2-3-1001', cwd=ROOT, env={})
        security.CreateProcessAsUserW.assert_not_called()

    def test_wts_sid_mismatch_and_duplicate_token_cleanup(self):
        kernel, security, sessions = Mock(), Mock(), Mock()
        entries = (windows.SessionInfo * 2)()
        entries[0].id, entries[1].id = 1, 2
        def enumerate_sessions(server, reserved, version, pointer, count):
            ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(windows.SessionInfo)))[0] = entries
            count._obj.value = 2
            return True
        sessions.WTSEnumerateSessionsW.side_effect = enumerate_sessions
        sessions.WTSQueryUserToken.side_effect = lambda sid, token: setattr(token._obj, 'value', sid + 10) or True
        security.GetTokenInformation.side_effect = lambda token, kind, data, size, needed: setattr(needed._obj, 'value', 64) or True
        names = []
        def convert(sid, out):
            text = ctypes.create_unicode_buffer('S-1-5-21-1-2-3-' + ('9999' if not names else '1001'))
            names.append(text)
            ctypes.cast(out, ctypes.POINTER(windows.W.LPWSTR))[0] = ctypes.cast(text, windows.W.LPWSTR)
            return True
        security.ConvertSidToStringSidW.side_effect = convert
        security.DuplicateTokenEx.side_effect = lambda token, access, attrs, level, kind, out: setattr(out._obj, 'value', 99) or True
        primary = windows.user_token('S-1-5-21-1-2-3-1001', kernel, security, sessions)
        self.assertEqual(primary.value, 99)
        self.assertEqual(security.DuplicateTokenEx.call_args.args[0].value, 12)
        self.assertEqual(kernel.CloseHandle.call_count, 2)
        sessions.WTSFreeMemory.assert_called_once()
        names.clear()
        with self.assertRaisesRegex(OSError, '로그온 세션'):
            windows.user_token('S-1-5-21-1-2-3-5555', kernel, security, sessions)

    def test_named_empty_job_recovery_is_idempotent(self):
        import uuid
        name='Global\\MINT-test-'+uuid.uuid4().hex
        job=windows.Job(name)
        try:
            self.assertTrue(windows.Job.recover(name))
        finally:
            self.assertTrue(job.close())
        self.assertTrue(windows.Job.recover(name))

    def test_named_job_collision_is_refused_before_child_spawn(self):
        import uuid
        name='Global\\MINT-test-'+uuid.uuid4().hex
        first=windows.Job(name)
        try:
            with self.assertRaises(OSError):windows.Job(name)
        finally:self.assertTrue(first.close())

    @unittest.skipUnless(shutil.which('openssl'),'OpenSSL CLI test key generator required')
    def test_ed25519_valid_tampered_message_signature_and_key(self):
        # Test the same OpenSSL 3 EVP calls using the host DLL, not a downloaded library.
        candidates=[Path(sys.executable).with_name('libcrypto-3.dll'),
                    Path(shutil.which('openssl')).with_name('libcrypto-3-x64.dll')]
        library=next((p for p in candidates if p.is_file()),None)
        if library is None:self.skipTest('OpenSSL 3 DLL missing')
        load=ctypes.CDLL
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            subprocess.run(['openssl','genpkey','-algorithm','ED25519','-out',str(path/'key')],check=True,capture_output=True)
            subprocess.run(['openssl','pkey','-in',str(path/'key'),'-pubout','-out',str(path/'pub')],check=True,capture_output=True)
            (path/'body').write_bytes(b'approved manifest')
            subprocess.run(['openssl','pkeyutl','-sign','-inkey',str(path/'key'),'-rawin','-in',str(path/'body'),
                            '-out',str(path/'sig')],check=True,capture_output=True)
            signature=base64.b64encode((path/'sig').read_bytes()).decode()
            pem=(path/'pub').read_text()
            with patch.object(windows.C,'CDLL',side_effect=lambda _:load(str(library))):
                self.assertTrue(windows.signed(b'approved manifest',signature,pem))
                self.assertFalse(windows.signed(b'tampered',signature,pem))
                self.assertFalse(windows.signed(b'approved manifest',base64.b64encode(b'0'*64).decode(),pem))
                self.assertFalse(windows.signed(b'approved manifest',signature,pem.replace('MCow','MAow')))

    def test_worker_and_service_include_runner_and_pinned_key(self):
        worker=(ROOT/'endpoint-agent/windows-worker.ps1').read_text(encoding='utf-8')
        service=(ROOT/'endpoint-agent/managed-windows.py').read_text(encoding='utf-8')
        for name in ('local-runner.py','stdio_source.py','stdio_windows.py','pip.zip'):
            self.assertIn(name,worker)
        self.assertIn('manifest_pubkey',service)
        self.assertIn('source_protected',service)
        self.assertIn('runner.run, runner.prepare',service)


if __name__=='__main__':unittest.main(verbosity=2)
