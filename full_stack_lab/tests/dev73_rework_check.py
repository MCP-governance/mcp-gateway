"""DEV-73 rework: standard-library unit checks, never an MCP/engine execution claim.

The gateway's pure/async functions are loaded without its unavailable third-party imports.
Database doubles below test outcomes only; transaction races have a separate PostgreSQL file.
"""
import ast
import asyncio
import contextvars
import hashlib
import importlib.util
import io
import json
import os
import posixpath
import queue
import re
import tempfile
import threading
import time
import unittest
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

ROOT=Path(__file__).resolve().parents[2]
APP=ROOT/'full_stack_lab/gateway/app'
spec=importlib.util.spec_from_file_location('dev73_runner',ROOT/'endpoint-agent/local-runner.py')
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def load_functions(path, names, namespace):
    tree=ast.parse(path.read_text(encoding='utf-8'))
    nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.name in names]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
    return SimpleNamespace(**{n.name:namespace[n.name] for n in nodes})


G={'asyncio':asyncio,'datetime':datetime,'timedelta':timedelta,'UTC':timezone.utc,
   'hashlib':hashlib,'json':json,'os':os,'posixpath':posixpath,'re':re,'uuid':uuid,
   'IMAGE':runner.IMAGE,'ENV_NAME':runner.ENV_NAME,'ENV_DENIED':runner.ENV_DENIED,
   'REASONS':{'local_file':'로컬 파일'},'Jsonb':lambda v:v,
   'RUN_SECONDS':20,'MAX_PARAMS_BYTES':65536,'QUEUE_LIMIT':8,'ACTIVE_LIMIT':1,'RATE_LIMIT':30,'POLL_SECONDS':.001,
   'RETENTION_SECONDS':3600,'evidence_context':contextvars.ContextVar('evidence',default=None),
   'transport_context':contextvars.ContextVar('transport',default={})}
jobs=load_functions(APP/'local_jobs.py',{'NotStarted','canonical','validate_params','approval_window','mirror_image','manifest_errors',
       'remember','record_evidence','exchange','authorized','current_job','applicant_device','LocalClient'},G)


def manifest():
    return {'server_id':'local-files','image':'mirror.corp/mcp/filesystem@sha256:'+'a'*64,
            'command':['serve'],'mounts':[],'env':{},'reason':{'kind':'local_file','text':'사내 로컬 문서 폴더 접근이 필요함'},
            'approval':{'generation':2,'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()}}


class ControlChecks(unittest.TestCase):
    def setUp(self):
        self.body=manifest()
        self.job={'manifest':self.body,'manifest_sha256':'a'*64,'policy_generation':3,'device_epoch':'epoch',
                  'device_policy':'device-policy','policy_version':'policy-version','account_uid':2001,'control_sha256':'control'}
        self.control={**self.job,'signature_generation':2,'revoked':False,'lifecycle':'OPERATING',
                      'expires_at':self.body['approval']['expires_at'],
                      'deadline':(datetime.now(timezone.utc)+timedelta(seconds=10)).isoformat()}

    def test_F2_current_generation_accepts_then_each_change_blocks(self):
        runner.check_control(self.job,self.control)
        for change in ({'revoked':True},{'lifecycle':'TERMINATING'},{'manifest_sha256':'old'},
                       {'policy_generation':2},{'device_epoch':'old'},{'device_policy':'old'},
                       {'policy_version':'old'},{'control_sha256':'old'},{'signature_generation':1},{'account_uid':2002},
                       {'expires_at':'2020-01-01T00:00:00+00:00'},{'deadline':'2020-01-01T00:00:00+00:00'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                runner.check_control(self.job,{**self.control,**change})

    def test_F2_signed_expiry_and_generation_are_required(self):
        self.assertEqual(jobs.approval_window(self.body)[0],2)
        for approval in ({},{'generation':True,'expires_at':self.control['expires_at']},
                         {'generation':1,'expires_at':'2020-01-01T00:00:00+00:00'},
                         {'generation':1,'expires_at':'2030-01-01T00:00:00'}):
            with self.subTest(approval=approval),self.assertRaises(ValueError):
                jobs.approval_window({**self.body,'approval':approval})

    def test_F3_both_sides_restrict_exact_mirror_and_digest(self):
        for check in (runner.image_allowed,jobs.mirror_image):
            self.assertTrue(check(self.body['image'],['mirror.corp/mcp']))
            for image in ('evil.test/mcp/filesystem@sha256:'+'a'*64,
                          'mirror.corp.evil/mcp/filesystem@sha256:'+'a'*64,'mirror.corp/mcp/filesystem:latest'):
                self.assertFalse(check(image,['mirror.corp/mcp']))
            self.assertFalse(check(self.body['image'],[]))

    def test_F5_missing_or_wrong_engine_mapping_is_blocked(self):
        for setting in ({},{'engine':'docker','namespace':'podman-auto'},
                        {'engine':'docker','namespace':'host'}):
            with self.subTest(setting=setting),self.assertRaises(ValueError),patch.object(runner.subprocess,'run') as command:
                runner.engine_configuration({'local_engine':setting},self.body)
            command.assert_not_called()

    def test_F5_actual_host_mapping_cannot_pass_as_userns(self):
        session=runner.Session.__new__(runner.Session)
        session.engine=['podman'];session.name='unit';session.stopped=threading.Event()
        with patch.object(runner.subprocess,'run',return_value=SimpleNamespace(stdout=b'123')),patch.object(Path,'read_text',return_value='0 0 4294967295\n'):
            with self.assertRaises(ValueError):session.mapping('podman-auto')
            self.assertEqual(session.mapping('host')['scope'],'탈출 시 호스트 root')

    def test_F3_container_uses_preimported_digest_and_no_log_disk(self):
        account=SimpleNamespace(pw_uid=2001,pw_gid=2001)
        _,argv=runner.container_command(['podman'],self.body,account,namespace='podman-auto',
                                        mount_options=['-v','/proc/123/fd/4:/home/u/work:ro'])
        for flag in ('--pull=never','--network=none','--read-only','--log-driver=none','--userns=auto'):
            self.assertIn(flag,argv)
        self.assertIn('type=bind,source=/proc/123/fd/4,target=/home/u/work,ro,idmap',argv)


class OutputBounds(unittest.TestCase):
    def session(self,data):
        s=runner.Session.__new__(runner.Session)
        s.process=SimpleNamespace(stdout=io.BytesIO(data))
        s.lines=queue.Queue(runner.MAX_QUEUE);s.stopped=threading.Event();s.failure=None;s.next_id=0
        s.stop=Mock(side_effect=lambda:s.stopped.set())
        return s

    def test_F6_single_line_bound_stops_and_discards_session(self):
        s=self.session(b'x'*(runner.MAX_LINE+1))
        s._read()
        self.assertEqual(s.failure,'ValueError');self.assertTrue(s.stopped.is_set());s.stop.assert_called_once()

    def test_F6_queue_bound_stops_without_unbounded_growth(self):
        s=self.session(b'{}\n'*(runner.MAX_QUEUE+1));s._read()
        self.assertEqual(s.failure,'Full');self.assertLessEqual(s.lines.qsize(),runner.MAX_QUEUE)
        self.assertTrue(s.stopped.is_set())

    def test_F6_total_byte_bound_is_independent(self):
        s=self.session(b'x'*50)
        with patch.object(runner,'MAX_BYTES',32):s._read()
        self.assertEqual(s.failure,'ValueError');s.stop.assert_called_once()

    def test_F6_line_count_bound_is_independent(self):
        s=self.session(b'{}\n'*4)
        with patch.object(runner,'MAX_LINES',3):s._read()
        self.assertEqual(s.failure,'ValueError');s.stop.assert_called_once()

    def test_F6_silent_stdout_read_deadline_stops(self):
        s=self.session(b'');s._send=Mock()
        with self.assertRaises(TimeoutError):s.request('tools/list',{},.02)
        s.stop.assert_called_once()
        with self.assertRaises(OSError):runner.Session._send(s,{})

    def test_F2_stop_receipt_is_idempotent_and_requires_engine_confirmation(self):
        s=runner.Session.__new__(runner.Session)
        s.engine=['docker'];s.name='unit';s.stopped=threading.Event();s.stop_lock=threading.Lock()
        s.stop_confirmed=False;s.creation_uncertain=False;s.process=None;s.pinned=SimpleNamespace(close=Mock())
        with patch.object(runner.subprocess,'run',return_value=SimpleNamespace(stdout=b'')) as cmd:
            self.assertTrue(s.stop());self.assertTrue(s.stop());self.assertEqual(cmd.call_count,2)
        s.pinned.close.assert_called_once()
        s.stop_confirmed=False
        with patch.object(runner.subprocess,'run',side_effect=OSError('engine offline')):
            self.assertFalse(s.stop())


@unittest.skipUnless(os.name=='posix' and hasattr(os,'O_NOFOLLOW'),'Linux openat/FD bind 실측 필요')
class MountRaces(unittest.TestCase):
    def test_F4_parent_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder)/'home';home.mkdir();(home/'real').mkdir();(home/'link').symlink_to(home/'real',target_is_directory=True)
            with self.assertRaises((OSError,ValueError)):runner.PinnedMounts({'mounts':[{'path':'link','mode':'ro'}]},str(home))

    @unittest.skipUnless(os.path.isdir('/proc/self/fd'), 'Linux procfs FD path required')
    def test_F4_repeated_replacement_never_redirects_pinned_source(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder)/'home';home.mkdir();work=home/'work';work.mkdir()
            (work/'allowed').write_text('allowed');secret=Path(folder)/'secret';secret.mkdir();(secret/'forbidden').write_text('secret')
            for _ in range(200):
                held=runner.PinnedMounts({'mounts':[{'path':'work','mode':'ro'}]},str(home))
                try:
                    work.rename(home/'saved');work.symlink_to(secret,target_is_directory=True)
                    with self.assertRaises((OSError,ValueError)):held.recheck()
                    descriptor=held.paths[0][1]
                    opened=os.open('allowed',os.O_RDONLY,dir_fd=descriptor)
                    try:self.assertEqual(os.read(opened,7),b'allowed')
                    finally:os.close(opened)
                    with self.assertRaises(FileNotFoundError):os.open('forbidden',os.O_RDONLY,dir_fd=descriptor)
                    source=held.options[1].split(':')[0]
                    self.assertEqual((Path(source)/'allowed').read_text(),'allowed')
                finally:
                    held.close();work.unlink();(home/'saved').rename(work)

    def test_F4_concurrent_parent_replacement_never_selects_secret_inode(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder)/'home';home.mkdir();work=home/'work';work.mkdir()
            (work/'allowed').write_text('allowed');secret=Path(folder)/'secret';secret.mkdir();(secret/'forbidden').write_text('secret')
            stop=threading.Event();errors=[]
            def replace():
                try:
                    while not stop.is_set():
                        work.rename(home/'saved');work.symlink_to(secret,target_is_directory=True)
                        work.unlink();(home/'saved').rename(work)
                except BaseException as exc:errors.append(exc)
            thread=threading.Thread(target=replace);thread.start()
            try:
                for _ in range(200):
                    try:held=runner.PinnedMounts({'mounts':[{'path':'work','mode':'ro'}]},str(home))
                    except (OSError,ValueError):continue
                    try:
                        descriptor=held.paths[0][1]
                        with self.assertRaises(FileNotFoundError):os.open('forbidden',os.O_RDONLY,dir_fd=descriptor)
                        try:held.recheck()
                        except (OSError,ValueError):pass
                    finally:held.close()
            finally:
                stop.set();thread.join(timeout=3)
            self.assertFalse(thread.is_alive());self.assertEqual(errors,[])


class OutcomeAndQueue(unittest.IsolatedAsyncioTestCase):
    async def test_F10_claimed_unknown_result_is_not_retried(self):
        send=AsyncMock(side_effect=TimeoutError('unknown after claim'))
        with patch.dict(G,{'exchange':send}):
            client=jobs.LocalClient('device',{},1)
            client.bind_evidence({'client':{}})
            with self.assertRaises(TimeoutError):await client._send('tools/call',{})
        self.assertEqual(send.await_count,1)

    async def test_F10_restart_only_removes_orphans_and_never_executes_them(self):
        identity=str(uuid.uuid4());posted=[]
        def request(config,path,body=None):
            if body is None:return {'jobs':[{'id':identity}]}
            posted.append((path,body));return {'accepted':True}
        with patch.object(runner.os.path,'isfile',return_value=True),patch.object(runner.subprocess,'run',return_value=SimpleNamespace(stdout=b'')) as engine:
            runner.recover({},request)
        self.assertTrue(posted[0][1]['stopped'])
        self.assertTrue(all(not any(v in command.args[0] for v in ('run','start','create')) for command in engine.call_args_list))
    async def test_F9_F10_dispatch_outcomes_keep_not_executed_and_unconfirmed_separate(self):
        namespace={'_record_decision':AsyncMock(return_value=7),'_release_call':AsyncMock(),'time':time,'_Laps':object}
        core=load_functions(APP/'core.py',{'_decision_payload'},namespace)
        laps=SimpleNamespace(view=lambda:{},started=time.perf_counter())
        for attempted,expected in ((False,'confirmed_not_executed'),(True,'uncertain')):
            event={'request_id':str(uuid.uuid4()),'upstream_attempted':attempted,'upstream_executed':False,
                   'client':{'local_execution':True,'local_jobs':[{'id':'job','state':'expired'}]}}
            await core._decision_payload(event,laps)
            self.assertEqual(namespace['_release_call'].await_args.args[2],expected)
            self.assertEqual(namespace['_record_decision'].await_args.args[0]['client']['local_jobs'][0]['id'],'job')

    async def test_F7_queue_and_rate_saturation_block_before_insert(self):
        for dimension in ('queued','active','rate'):
            for saturated_at in range(3):
                calls=[];counter=0
                class Cursor:
                    async def fetchone(self):return self.row
                class Connection:
                    async def execute(self,query,params=None):
                        nonlocal counter
                        calls.append(query);c=Cursor();c.row={'n':0,'queued':0,'active':0,'rate':0}
                        if 'FILTER(WHERE' in query:
                            if counter==saturated_at:c.row[dimension]={'queued':8,'active':1,'rate':30}[dimension]
                            counter+=1
                        return c
                @asynccontextmanager
                async def transaction():yield Connection()
                device={'endpoint_id':'device','owner_token':'owner','device_epoch':'epoch','policy_hash':'policy'}
                replacements={'db':SimpleNamespace(transaction=transaction),'_device':AsyncMock(return_value=device),
                              'cleanup':AsyncMock(),'authorized':AsyncMock(return_value=True),'admission_locks':AsyncMock(),
                              'lock_execution':AsyncMock(),'transport_context':SimpleNamespace(get=lambda:{'_principal':'owner'})}
                with patch.dict(G,replacements),self.assertRaises(jobs.NotStarted) as blocked:
                    await jobs.exchange('device',{'manifest':manifest(),'manifest_sha256':'a'*64,'signature':'signature'},'tools/call',{},1)
                self.assertEqual(blocked.exception.local_policy,'P-RATE-003')
                self.assertFalse(any('INSERT INTO local_jobs' in q for q in calls))

    async def test_F9_result_evidence_retains_uuid_timestamps_state_hash(self):
        row={'id':str(uuid.uuid4()),'request_id':str(uuid.uuid4()),'device_id':'device','server_id':'local-files',
             'method':'tools/call','manifest_sha256':'a'*64,'state':'done','result_sha256':'b'*64,
             'claimed_at':datetime.now(timezone.utc),'finished_at':datetime.now(timezone.utc)}
        event={};jobs.remember(row,event)
        evidence=event['client']['local_jobs'][0]
        self.assertTrue(event['upstream_attempted'])
        for key in ('id','request_id','claimed_at','finished_at','state','result_sha256'):
            self.assertEqual(evidence[key],str(row[key]))

    async def test_F8_bound_observer_survives_a_newer_device_heartbeat(self):
        fake=SimpleNamespace(fetch_one=AsyncMock(return_value={'local_observer_device':'original-device'}))
        current=AsyncMock(return_value={'endpoint_id':'original-device','owner_token':'applicant'})
        with patch.dict(G,{'db':fake,'_device':current}):
            self.assertEqual(await jobs.applicant_device('applicant',str(uuid.uuid4())),'original-device')
        self.assertEqual(fake.fetch_one.await_count,1)


if __name__=='__main__':unittest.main(verbosity=2)
