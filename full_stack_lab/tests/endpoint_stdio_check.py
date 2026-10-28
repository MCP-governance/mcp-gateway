"""Source/process unit checks. Generic subprocesses and existing protocol doubles; no MCP execution claim."""
import ast
from datetime import datetime, timedelta, timezone
from contextlib import ExitStack
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'full_stack_lab/tests'))
from dev73_rework_check import runner, manifest

source = runner.helper('stdio_source')


def archive(files):
    spool=io.BytesIO()
    with tarfile.open(fileobj=spool, mode='w:gz') as tar:
        for name, body in files.items():
            item=tarfile.TarInfo('approved/'+name)
            item.size=len(body)
            tar.addfile(item,io.BytesIO(body))
    digest=hashlib.sha256(''.join(f'{hashlib.sha256(body).hexdigest()}  {name}\n'
                                for name,body in sorted(files.items())).encode()).hexdigest()
    return spool.getvalue(),digest


class Preparation(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.data,self.digest=archive({'main.py':b'pass\n','requirements.lock':b''})
        self.body={**manifest(),'image':'','source':{'runtime':'python','commit':'a'*40,'sha256':self.digest,
                  'entrypoint':'main.py','lock':'requirements.lock','lock_sha256':hashlib.sha256(b'').hexdigest()}}
        self.body['command']=[]
        self.config={'source_root':str(self.base),'source_protected':lambda path:True}
        self.request=Mock(side_effect=self.receive)
        # Keep the real filesystem for all paths except the bundled pip artifact.
        real_is_file=Path.is_file
        self.patch_file=patch.object(source.Path,'is_file',autospec=True,
                                    side_effect=lambda p:p.name=='pip.zip' or real_is_file(p))
        self.patch_file.start(); self.addCleanup(self.patch_file.stop)
        self.child=Mock(returncode=0)
        self.child.poll.return_value=0
        self.spawn=patch.object(source.subprocess,'Popen',return_value=self.child)
        self.started=self.spawn.start();self.addCleanup(self.spawn.stop)

    def receive(self,config,path,**kwargs):
        self.assertTrue(path.startswith('/api/endpoint/local-sources/local-files?manifest='))
        kwargs['download'].write(self.data)
        return {'X-Content-SHA256':self.digest}

    def test_prepare_and_verified_cache_no_second_install(self):
        args,folder,env=source.prepare(self.config,self.body,self.request)
        self.assertEqual(folder.parent,self.base)
        self.assertIn('-I',args)
        self.assertNotIn('PATH',env)
        source.prepare(self.config,self.body,self.request)
        self.assertEqual(self.request.call_count,1)
        self.assertEqual(self.started.call_count,1)
        command=self.started.call_args.args[0]
        self.assertIn('--require-hashes',command)
        self.assertIn('--only-binary=:all:',command)

    def test_changed_prepared_file_fails_closed(self):
        _,folder,_=source.prepare(self.config,self.body,self.request)
        (folder/'source/main.py').write_text('changed')
        with self.assertRaises(ValueError):source.prepare(self.config,self.body,self.request)

    def test_source_hash_lock_hash_and_network_failure_never_install(self):
        for key in ('sha256','lock_sha256'):
            with self.subTest(key=key):
                body={**self.body,'source':{**self.body['source'],key:'0'*64}}
                with self.assertRaises(ValueError):source.prepare(self.config,body,self.request)
        self.request.side_effect=OSError('offline')
        with self.assertRaises(OSError):source.prepare(self.config,self.body,self.request)
        self.started.assert_not_called()

    def test_missing_node_runtime_and_missing_lock_fail(self):
        data,digest=archive({'main.js':b'','package-lock.json':b'{"lockfileVersion":3,"packages":{"":{}}}'})
        self.data,self.digest=data,digest
        self.body['source'].update(runtime='node',entrypoint='main.js',lock='package-lock.json',sha256=digest,
            lock_sha256=hashlib.sha256(b'{"lockfileVersion":3,"packages":{"":{}}}').hexdigest())
        with self.assertRaisesRegex(ValueError,'Node'):source.prepare(self.config,self.body,self.request)
        self.started.assert_not_called()

    def test_unprotected_root_and_deadline_do_not_download(self):
        with self.assertRaises(ValueError):source.prepare({**self.config,'source_protected':lambda p:False},self.body,self.request)
        with self.assertRaises(TimeoutError):source.prepare(self.config,self.body,self.request,seconds=-1)
        self.request.assert_not_called()

    def test_environment_and_path_boundaries(self):
        with patch.dict(os.environ,{'ACCESS_TOKEN':'do-not-copy'}):
            self.assertNotIn('ACCESS_TOKEN',source.environment(self.body))
        for value in ('../escape','C:/bad','a\\bad','a//b','/absolute'):
            with self.assertRaises(ValueError):source.relative(value)
        for key in ('PATH','HOME','PYTHONPATH','NODE_OPTIONS','NODE_PATH','SYSTEMROOT','COMSPEC','LD_PRELOAD'):
            with self.assertRaises(ValueError):source.environment({**self.body,'env':{key:'bad'}})

    def test_archive_duplicate_symlink_and_size_refused(self):
        for name,kind in (('approved/../escape',tarfile.REGTYPE),('approved/link',tarfile.SYMTYPE)):
            spool=io.BytesIO()
            with tarfile.open(fileobj=spool,mode='w:gz') as tar:
                item=tarfile.TarInfo(name);item.type=kind;item.linkname='elsewhere';tar.addfile(item)
            spool.seek(0)
            with self.assertRaises(ValueError):source.unpack(spool,self.base,self.digest)
        with patch.object(source,'LIMIT',1):
            with self.assertRaises(ValueError):source.unpack(io.BytesIO(self.data),self.base,self.digest)


class ProcessChecks(unittest.TestCase):
    def prepared(self, code):
        return [sys.executable,'-I','-S','-c',code],Path(tempfile.gettempdir()),source.environment({'env':{}})

    def account(self):
        if os.name=='nt':return SimpleNamespace(pw_uid=None)
        import pwd
        return pwd.getpwnam('nobody') if os.getuid()==0 else pwd.getpwuid(os.getuid())

    def test_silent_process_deadline_and_confirmed_tree_stop(self):
        session=runner.ProcessSession(self.prepared('import time; time.sleep(60)'),self.account(),lambda:None)
        try:
            with self.assertRaises((TimeoutError,OSError)):
                session.request('initialize',{},.05)
        finally:
            self.assertTrue(session.stop())
            self.assertTrue(session.stop())
        self.assertIsNotNone(session.process.poll())

    def test_child_tree_is_reaped(self):
        code='import subprocess,sys,time;subprocess.Popen([sys.executable,"-I","-S","-c","import time;time.sleep(60)"]);time.sleep(60)'
        session=runner.ProcessSession(self.prepared(code),self.account(),lambda:None)
        time.sleep(.3)
        self.assertTrue(session.stop())

    def test_control_mismatch_before_spawn(self):
        check=Mock(side_effect=ValueError('revoked'))
        with patch.object(runner.subprocess,'Popen') as spawn:
            with self.assertRaises(ValueError):runner.ProcessSession(self.prepared('pass'),self.account(),check)
            spawn.assert_not_called()

    def test_windows_path_command_has_no_shell_and_no_host_environment(self):
        folder=Path('C:/ProgramData/MCPGatewayManaged/sources/pin')
        args=source.command(folder,{'runtime':'python','entrypoint':'src/main.py'},{'command':['space argument']},{})
        self.assertIn(str(folder/'source/src/main.py'),args)
        self.assertEqual(args[-1],'space argument')
        self.assertNotIn('cmd.exe',args)

    def test_package_entrypoint_and_missing_python(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            package=folder/'source/packages/example/src/example'
            package.mkdir(parents=True)
            (package/'__init__.py').write_text('')
            (package/'value.py').write_text("TEXT='module-ready'")
            (package/'__main__.py').write_text("from .value import TEXT; print(TEXT)")
            args=source.command(folder,{'runtime':'python','entrypoint':'packages/example/src/example/__main__.py'},
                                {'command':[]},{})
            result=subprocess.run(args,capture_output=True,check=True)
            self.assertEqual(result.stdout.strip(),b'module-ready')
            with patch.object(source.sys,'executable',str(folder/'missing-python')):
                with self.assertRaises(ValueError):source.command(folder,{'runtime':'python','entrypoint':'main.py'},
                                                                  {'command':[]},{})

    def test_existing_control_and_contract_checks_remain_shared(self):
        body=ast.parse((ROOT/'endpoint-agent/local-runner.py').read_text(encoding='utf-8'))
        execute=next(n for n in body.body if isinstance(n,ast.FunctionDef) and n.name=='execute_job')
        text=ast.unparse(execute)
        self.assertIn('ProcessSession',text)
        self.assertIn("session.request('tools/list'",text)
        self.assertIn('output_schema_sha256',text)
        self.assertIn('check_control(job, control)',text)
        self.assertIs(runner.ProcessSession.request,runner.Session.request)
        self.assertIs(runner.ProcessSession.diagnostic,runner.Session.diagnostic)


class DispatchContract(unittest.TestCase):
    def test_source_mode_uses_same_contract_and_refuses_mismatch(self):
        now=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()
        for mismatch in (False,True):
            with self.subTest(mismatch=mismatch),ExitStack() as stack:
                body={**manifest(),'image':'','source':{}}
                job={'id':'00000000-0000-0000-0000-000000000001','server_id':'local-files','manifest':body,
                     'account_uid':None,'signature':'x','manifest_sha256':'x','lease_until':now,
                     'policy_generation':1,'device_epoch':'epoch','device_policy':'policy','policy_version':'policy',
                     'control_sha256':'control','method':'tools/call','params':{'name':'read','arguments':{}}}
                tool={'name':'read','description':'approved','inputSchema':{'type':'object'}}
                pin={key:hashlib.sha256(runner.canonical(value)).hexdigest() for key,value in (
                    ('description_sha256',tool['description']),('schema_sha256',tool['inputSchema']),('output_schema_sha256',None))}
                if mismatch:pin['schema_sha256']='0'*64
                control={**job,'revoked':False,'lifecycle':'OPERATING','expires_at':now,'deadline':now,
                         'signature_generation':body['approval']['generation'],'contracts':{'read':pin}}
                def request(config,path,body=None):return control
                stack.enter_context(patch.object(runner,'verify_manifest'))
                stack.enter_context(patch.object(runner.helper('stdio_source'),'prepare',return_value=([],Path('.'),{})))
                stack.enter_context(patch.object(runner.ProcessSession,'__init__',return_value=None))
                stack.enter_context(patch.object(runner.ProcessSession,'mapping',return_value={}))
                stack.enter_context(patch.object(runner.ProcessSession,'stop',return_value=True))
                stack.enter_context(patch.object(runner.ProcessSession,'_send'))
                calls=stack.enter_context(patch.object(runner.ProcessSession,'request',side_effect=[
                    {'protocolVersion':runner.PROTOCOL},{'tools':[tool]},{'content':[]}]))
                answer=runner.execute_job({'uid':None},job,request,SimpleNamespace(pw_uid=None))
                self.assertTrue(answer['stopped'])
                if mismatch:
                    self.assertIn('error',answer)
                    self.assertEqual(calls.call_count,2)
                else:
                    self.assertEqual(answer['result'],{'content':[]})
                    self.assertEqual(calls.call_args.args[0],'tools/call')


if __name__=='__main__':unittest.main(verbosity=2)
