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
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('stdio_windows',ROOT/'endpoint-agent/stdio_windows.py')
windows=importlib.util.module_from_spec(spec)
spec.loader.exec_module(windows)


@unittest.skipUnless(os.name=='nt','Windows Job Object required')
class WindowsProcess(unittest.TestCase):
    def test_named_job_recovery_kills_descendants_and_is_idempotent(self):
        import uuid
        name='Global\\MINT-test-'+uuid.uuid4().hex
        job=windows.Job(name)
        process=None
        try:
            process=job.start([sys.executable,'-I','-S','-c',
                'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"]);time.sleep(60)'])
            time.sleep(.2)
            self.assertTrue(windows.Job.recover(name))
            process.wait(timeout=3)
            self.assertIsNotNone(process.returncode)
        finally:
            self.assertTrue(job.close())
            if process:process.wait(timeout=3)
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
