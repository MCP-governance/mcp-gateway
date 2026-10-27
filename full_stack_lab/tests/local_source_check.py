"""Approved-source unit checks. HTTP/DB/engine doubles are not Gitea or Linux execution evidence."""
from __future__ import annotations

import ast
import asyncio
import hashlib
import importlib.util
import io
import json
import os
import re
import socket
import struct
import sys
import tarfile
import tempfile
import threading
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import quote, urlsplit

from approved_mcp_download_check import BackgroundTask, HTTPException, StreamingResponse
from dev73_rework_check import APP, G, manifest, runner
from open_endpoints import route_auth

ROOT=APP.parents[2]
SOURCE=APP/'local_sources.py'
BASE='python:3.13@sha256:'+'c'*64
IMAGE_ID='sha256:'+'d'*64
SOURCE_SPEC={'commit':'a'*40,'sha256':'b'*64,'recipe':'markitdown-mcp','recipe_sha256':'c'*64,
             'dockerfile':f'FROM {BASE}\nCOPY . /src\nENTRYPOINT ["serve"]\n'}


def functions(path,names,scope):
    nodes=[n for n in ast.parse(path.read_text(encoding='utf-8')).body
           if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names]
    assert {n.name for n in nodes}==set(names)
    for node in nodes:
        node.decorator_list=[]
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*nodes],type_ignores=[])
    exec(compile(ast.fix_missing_locations(module),str(path),'exec'),scope)
    return scope


def source_body():
    return {**manifest(),'image':'','source':dict(SOURCE_SPEC)}


def archive(files=None):
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w:gz') as handle:
        for name,data in (files or {'repo/a.txt':b'approved','repo/folder/b.txt':b'content'}).items():
            member=tarfile.TarInfo(name)
            if isinstance(data,tuple):
                member.type=tarfile.SYMTYPE;member.linkname=data[0]
                handle.addfile(member)
            else:
                member.size=len(data);handle.addfile(member,io.BytesIO(data))
    return output.getvalue()


def gateway_scope():
    return functions(SOURCE,{'source_errors','recipe_for','source_for','authorized_source','receive','download'},
                     dict(asyncio=asyncio,hashlib=hashlib,os=os,re=re,Path=Path,quote=quote,urlsplit=urlsplit,
                          tempfile=tempfile,HTTPException=HTTPException,StreamingResponse=StreamingResponse,
                          BackgroundTask=BackgroundTask,RECIPES=ROOT/'full_stack_lab/runtime/recipes',
                          DOWNLOAD_SLOTS=asyncio.Semaphore(1),httpx=SimpleNamespace(HTTPError=OSError)))


class ManifestAndRecipe(unittest.TestCase):
    def setUp(self):
        self.scope=gateway_scope()

    def test_source_and_image_use_exactly_one_signed_choice(self):
        package=ModuleType('source_test');source_module=ModuleType('source_test.local_sources')
        source_module.source_errors=self.scope['source_errors']
        env=functions(APP/'local_jobs.py',{'manifest_errors'},{**G,'__package__':'source_test'})
        with patch.dict(sys.modules,{'source_test':package,'source_test.local_sources':source_module}):
            check=env['manifest_errors']
            self.assertEqual(check(source_body(),'local-files'),[])
            self.assertEqual(check(manifest(),'local-files'),[])
            for body in ({**source_body(),'image':manifest()['image']},{**manifest(),'image':''},
                         {**source_body(),'source':None},{**source_body(),'source':{}}):
                self.assertTrue(check(body,'local-files'))

    def test_each_boundary_is_rejected_by_gateway_and_runner(self):
        changes=[{'commit':'a'*39},{'commit':True},{'sha256':'b'*63},{'recipe_sha256':'x'*64},
                 {'recipe':'../evil'},{'recipe':'A'},{'recipe':'a'*65},{'extra':'x'},
                 {'dockerfile':''},{'dockerfile':'x'*16385},{'dockerfile':'FROM python:latest\n'},
                 {'dockerfile':f'FROM {BASE}\nFROM python:latest\n'},
                 {'dockerfile':f'FROM {BASE}\nADD https://evil.test/x /x\n'},
                 {'dockerfile':f'FROM {BASE}\nadd ["https://evil.test/x", "/x"]\n'},
                 {'dockerfile':f'FROM {BASE}\nADD \\\n https://evil.test/x /x\n'},
                 {'dockerfile':f'FROM {BASE}\nADD $URL /x\n'},
                 {'dockerfile':f'# escape=`\nFROM {BASE}\n'},
                 {'dockerfile':f'# syntax=evil/frontend\nFROM {BASE}\n'}]
        for change in changes:
            for check in (self.scope['source_errors'],runner.source_errors):
                with self.subTest(change=change,check=check.__module__):
                    self.assertTrue(check({**SOURCE_SPEC,**change}))
        valid={**SOURCE_SPEC,'dockerfile':f'FROM --platform=linux/amd64 {BASE} AS first\nFROM {BASE}\nADD ["a", "/a"]\n'}
        self.assertEqual(self.scope['source_errors'](valid),[])
        self.assertEqual(runner.source_errors(valid),[])

    def test_shipped_recipe_hash_stdio_and_provenance_are_bound(self):
        try:
            import tomllib
        except ImportError:
            # Test interpreter only: pip ships the same parser's backport; the appliance uses Python 3.13 tomllib.
            from pip._vendor import tomli as tomllib
        with patch.dict(sys.modules,{'tomllib':tomllib}):
            recipe=self.scope['recipe_for']('https://github.com/microsoft/markitdown')
            path=ROOT/'full_stack_lab/runtime/recipes/markitdown-mcp.toml'
            self.assertEqual(recipe['sha256'],hashlib.sha256(path.read_bytes()+b'\0'+path.with_suffix('.Dockerfile').read_bytes()).hexdigest())
            self.assertEqual(recipe['stdio_args'],[])
            row={'intake_kind':'repository','repository_url':'https://github.com/microsoft/markitdown',
                 'validated_at':'checked','commit_sha':'a'*40,'provenance':{'artifact':{'sha256':'b'*64}}}
            source=self.scope['source_for'](row)
            self.assertEqual(self.scope['source_errors'](source),[])
            for change in ({'validated_at':None},{'commit_sha':'HEAD'},{'provenance':{}},
                           {'repository_url':'https://github.com/unknown/server'}):
                with self.subTest(change=change),self.assertRaises(ValueError):
                    self.scope['source_for']({**row,**change})

    def test_archive_algorithm_matches_gateway_including_symlinks(self):
        env=functions(APP/'provenance.py',{'manifest_digest','archive_digest'},
                      dict(hashlib=hashlib,tarfile=tarfile,Path=Path,MAX_ARCHIVE_BYTES=runner.SOURCE_LIMIT))
        for files in ({'repo/a':b'one','repo/b':b'two'}, {'repo/a':b'one','repo/link':('a',)}):
            data=archive(files)
            self.assertEqual(env['archive_digest'](io.BytesIO(data)),runner.archive_digest(io.BytesIO(data)))
        with self.assertRaises(ValueError):runner.archive_digest(io.BytesIO(archive()),limit=1)

    def test_source_preview_proxy_waits_for_build_without_extending_other_paths(self):
        tree=ast.parse((APP/'local_jobs.py').read_text(encoding='utf-8'))
        budget=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and n.targets[0].id=='SOURCE_PREPARE_SECONDS'))
        self.assertEqual(budget,runner.PREFETCH_SECONDS)
        env=functions(APP/'agent_service.py',{'local_discover_timeout'},
                      dict(local_jobs=SimpleNamespace(SOURCE_PREPARE_SECONDS=runner.PREFETCH_SECONDS),LOCAL_DISCOVER_SECONDS=240))
        self.assertEqual(env['local_discover_timeout']({'manifest':source_body()}),1860)
        self.assertEqual(env['local_discover_timeout']({'manifest':manifest()}),240)
        self.assertEqual(env['local_discover_timeout'](None),45)


class SourceBuild(unittest.TestCase):
    def setUp(self):
        self.body=source_body();self.data=archive()
        self.body['source']['sha256']=runner.archive_digest(io.BytesIO(self.data))['sha256']
        self.digest=hashlib.sha256(runner.canonical(self.body)).hexdigest()
        self.popen=Mock(return_value=Mock(poll=Mock(return_value=0),returncode=0))
        self.inspections=0
        def inspect(argv,**kwargs):
            self.inspections+=1
            image={'Id':IMAGE_ID,'Config':{'Labels':{'mcpgw.manifest':self.digest}}}
            return SimpleNamespace(returncode=1 if self.inspections==1 else 0,stdout=json.dumps([image]).encode())
        self.inspect=Mock(side_effect=inspect)
        self.download=Mock(side_effect=self.receive)
        self.unpack=runner.unpack_source
        self.patches=[patch.object(runner.subprocess,'run',self.inspect),patch.object(runner.subprocess,'Popen',self.popen),
                      patch.object(runner,'unpack_source',side_effect=lambda spool,path:path)]
        for p in self.patches:p.start();self.addCleanup(p.stop)

    def receive(self,config,path,*,download,deadline):
        self.assertIn(f'?manifest={self.digest}',path)
        download.write(self.data)
        return {'X-Content-SHA256':self.body['source']['sha256']}

    def build(self,check=None):
        return runner.source_image({},self.body,['docker'],self.download,check,seconds=10)

    def test_build_tags_labels_and_immutable_execution_id(self):
        signed=runner.canonical(self.body)
        self.assertEqual(self.build(),IMAGE_ID)
        args=self.popen.call_args.args[0]
        self.assertEqual(args[args.index('--tag')+1],f'mcpgw-src/local-files:{self.digest[:12]}')
        self.assertEqual(args[args.index('--label')+1],'mcpgw.manifest='+self.digest)
        self.assertEqual(runner.canonical(self.body),signed)
        account=SimpleNamespace(pw_uid=2001,pw_gid=2001)
        _,args=runner.container_command(['docker'],{**self.body,'image':IMAGE_ID},account,mount_options=[],host_paths=[])
        for flag in ('--network=none','--read-only','--cap-drop=ALL','--pull=never'):
            self.assertIn(flag,args)
        self.assertIn(IMAGE_ID,args)
        for image in ('mcpgw-src/local-files:mutable',manifest()['image']):
            with self.assertRaises(ValueError):
                runner.container_command(['docker'],{**self.body,'image':image},account,mount_options=[],host_paths=[])

    def test_digest_or_header_mismatch_never_builds(self):
        for header in (True,False):
            self.inspections=0
            if header:self.data=archive({'repo/a':b'tampered'})
            else:self.download.side_effect=lambda config,path,**kw:{'X-Content-SHA256':'0'*64}
            with self.subTest(header=header),self.assertRaises(ValueError):self.build()
            self.popen.assert_not_called()

    def test_cached_image_checks_label_and_avoids_download(self):
        self.inspections=1
        self.assertEqual(self.build(),IMAGE_ID)
        self.download.assert_not_called();self.popen.assert_not_called()
        self.inspect.side_effect=None
        self.inspect.return_value=SimpleNamespace(returncode=0,stdout=json.dumps([{'Id':IMAGE_ID,'Config':{'Labels':{}}}]).encode())
        with self.assertRaises(ValueError):self.build()
        self.download.assert_not_called()

    def test_job_and_prefetch_race_builds_once_then_reuses_verified_image(self):
        started,release,available=threading.Event(),threading.Event(),threading.Event()
        image={'Id':IMAGE_ID,'Config':{'Labels':{'mcpgw.manifest':self.digest}}}
        self.inspect.side_effect=lambda *a,**kw:SimpleNamespace(returncode=0 if available.is_set() else 1,stdout=json.dumps([image]).encode())
        def poll():
            if release.is_set():available.set();return 0
            return None
        def start(*a,**kw):
            started.set()
            return SimpleNamespace(poll=poll,returncode=0,kill=Mock(),wait=Mock())
        self.popen.side_effect=start
        results,errors=[],[]
        def build():
            try:results.append(self.build())
            except Exception as exc:errors.append(exc)
        threads=[threading.Thread(target=build) for _ in range(2)]
        try:
            threads[0].start();self.assertTrue(started.wait(2))
            threads[1].start();release.set()
            for thread in threads:thread.join(3)
            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertEqual(errors,[]);self.assertEqual(results,[IMAGE_ID,IMAGE_ID])
            self.assertEqual(self.popen.call_count,1);self.assertEqual(self.download.call_count,1)
        finally:
            release.set()
            for thread in threads:
                if thread.ident is not None:thread.join(3)

    def test_build_failure_and_revocation_kill_client_and_do_not_execute(self):
        self.popen.return_value=Mock(poll=Mock(return_value=1),returncode=1)
        with self.assertRaises(ValueError):self.build()
        self.assertEqual(next(r for r in runner.preparation['servers'] if r['server']=='local-files')['status'],'빌드 실패')
        self.inspections=0
        process=Mock(poll=Mock(return_value=None),returncode=None)
        def start(*a,**kw):
            self.running=True
            return process
        self.running=False;self.popen.side_effect=start
        def check():
            if self.running:raise ValueError('승인 철회')
        with self.assertRaises(ValueError):self.build(check)
        process.kill.assert_called_once();process.wait.assert_called_once()
        self.assertFalse(any('run' in call.args[0] for call in self.inspect.call_args_list))

    def test_deadline_expiry_never_builds(self):
        with patch.object(runner.time,'monotonic',side_effect=[0,11]),self.assertRaises(TimeoutError):self.build()
        self.popen.assert_not_called()

    def test_build_deadline_kills_and_reaps_running_client(self):
        process=Mock(poll=Mock(return_value=None),returncode=None)
        started=False
        def start(*a,**kw):
            nonlocal started
            started=True
            return process
        self.popen.side_effect=start
        with patch.object(runner.time,'monotonic',side_effect=lambda:11 if started else 0),self.assertRaises(TimeoutError):
            self.build()
        process.kill.assert_called_once();process.wait.assert_called_once()

    def test_old_python_refuses_unfiltered_extraction(self):
        with patch.dict(tarfile.__dict__):
            tarfile.__dict__.pop('data_filter',None)
            with tempfile.TemporaryDirectory() as folder,self.assertRaisesRegex(ValueError,'Python'):
                self.unpack(io.BytesIO(self.data),folder)

    @unittest.skipUnless(hasattr(tarfile,'data_filter'),'Python tarfile data filter 보안 업데이트 필요')
    def test_data_filter_removes_one_root_and_blocks_traversal_links_and_multiple_roots(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.unpack(io.BytesIO(self.data),Path(folder)/'ok')
            self.assertEqual(root.name,'repo');self.assertEqual((root/'a.txt').read_bytes(),b'approved')
            for files in ({'../escape':b'x'},{'repo/link':('/etc/passwd',)}, {'one/a':b'x','two/a':b'y'}):
                with self.subTest(files=files),self.assertRaises((ValueError,tarfile.TarError)):
                    self.unpack(io.BytesIO(archive(files)),Path(folder)/'bad')


class DeviceAPI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.scope=gateway_scope()
        self.device={'endpoint_id':'device','owner_token':'employee','device_epoch':'epoch','policy_hash':'policy'}
        self.approval={'observed':True,'intake_id':'intake','policy_generation':2}
        self.row={'evidence':{'local_run':{'source':SOURCE_SPEC}},'internal_repo_url':'https://console/git/mcp/repo'}
        async def execute(query,params=None):
            return SimpleNamespace(fetchone=AsyncMock(return_value=self.row if 'mcp_intake_requests' in query else {'token':'employee'}))
        @asynccontextmanager
        async def transaction():yield SimpleNamespace(execute=execute)
        self.jobs=SimpleNamespace(_device=AsyncMock(return_value=self.device),authorized=AsyncMock(return_value=self.approval),NotStarted=ConnectionError)
        self.scope.update(db=SimpleNamespace(transaction=transaction),local_jobs=self.jobs,
                          pac=SimpleNamespace(servers_for=lambda user:['local-files']),
                          registry=SimpleNamespace(server=lambda sid:{'local':{'manifest':{'source':SOURCE_SPEC},'manifest_sha256':'e'*64}}),
                          review=SimpleNamespace(SERVER=re.compile(r'^[a-z0-9-]{1,64}$'),record_event=AsyncMock()),
                          source_for=Mock(return_value=SOURCE_SPEC))

    async def check(self):return await self.scope['authorized_source'](self.device,'local-files','e'*64)

    async def test_current_authorization_and_only_bound_observer_can_fetch(self):
        out=await self.check()
        self.assertEqual(out['source'],SOURCE_SPEC)
        self.assertTrue(out['path'].endswith('/archive/'+'a'*40+'.tar.gz'))
        self.jobs.authorized.assert_awaited_once()
        self.approval['observed']=False
        self.assertEqual((await self.check())['source'],SOURCE_SPEC)

    async def test_revocation_wrong_manifest_and_user_scope_refuse(self):
        self.jobs.authorized.return_value=None
        with self.assertRaises(HTTPException) as error:await self.check()
        self.assertEqual(error.exception.status_code,403)
        self.jobs.authorized.return_value=self.approval
        self.scope['pac'].servers_for=lambda user:[]
        with self.assertRaises(HTTPException) as error:await self.check()
        self.assertEqual(error.exception.status_code,403)
        with self.assertRaises(HTTPException) as error:
            await self.scope['authorized_source'](self.device,'local-files','bad')
        self.assertEqual(error.exception.status_code,409)

    async def test_recipe_commit_or_source_replacement_refuses(self):
        self.scope['source_for'].return_value={**SOURCE_SPEC,'recipe_sha256':'f'*64}
        with self.assertRaises(HTTPException) as error:await self.check()
        self.assertEqual(error.exception.status_code,409)

    async def test_download_rechecks_after_io_and_audits_only_success(self):
        before=await self.check()
        self.scope['authorized_source']=AsyncMock(side_effect=[before,before])
        handles=[]
        async def receive(spool,path):
            handles.append(spool);spool.write(b'archive');spool.seek(0);return 7
        self.scope['receive']=receive
        response=await self.scope['download'](self.device,'local-files','e'*64)
        self.assertEqual(response.headers['X-Content-SHA256'],SOURCE_SPEC['sha256'])
        self.assertEqual(b''.join([b async for b in response.body_iterator]),b'archive')
        self.assertTrue(handles[-1].closed)
        self.scope['review'].record_event.assert_awaited_once()
        self.scope['review'].record_event.reset_mock()
        for after in (HTTPException(403,'철회'),{**before,'policy_generation':3}):
            self.scope['authorized_source']=AsyncMock(side_effect=[before,after])
            with self.subTest(after=after),self.assertRaises(HTTPException) as error:
                await self.scope['download'](self.device,'local-files','e'*64)
            self.assertIn(error.exception.status_code,(403,409));self.assertTrue(handles[-1].closed)
            self.scope['review'].record_event.assert_not_awaited()

    async def test_stream_bounds_and_internal_credentials_without_device_key(self):
        class Response:
            status_code=200
            headers={}
            async def aiter_raw(self,chunk_size):
                yield b'ab';yield b'cd'
        response=Response()
        @asynccontextmanager
        async def stream(*a,**kw):yield response
        client=SimpleNamespace(stream=stream)
        @asynccontextmanager
        async def factory(**kw):
            self.client_options=kw
            yield client
        self.scope.update(httpx=SimpleNamespace(AsyncClient=factory),provenance=SimpleNamespace(MAX_ARCHIVE_BYTES=3))
        with tempfile.SpooledTemporaryFile() as spool,self.assertRaises(HTTPException) as error:
            await self.scope['receive'](spool,'/archive')
        self.assertEqual(error.exception.status_code,413)
        self.assertFalse(self.client_options['trust_env']);self.assertFalse(self.client_options['follow_redirects'])
        self.assertNotIn('headers',self.client_options)
        response.status_code=302
        with tempfile.SpooledTemporaryFile() as spool,self.assertRaises(HTTPException) as error:
            await self.scope['receive'](spool,'/archive')
        self.assertEqual(error.exception.status_code,502)

    def test_route_requires_enforcement_device_credential(self):
        tree=ast.parse((APP/'main.py').read_text(encoding='utf-8'))
        self.assertEqual(route_auth(tree)[('get','/api/endpoint/local-sources/{server_id}')],'device')
        node=next(n for n in tree.body if getattr(n,'name',None)=='endpoint_local_source')
        self.assertIn("endpoint_device('enforcement')",ast.unparse(node))


class AdministratorFlow(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.package=ModuleType('source_admin_test')
        self.sources=SimpleNamespace(source_for=Mock(return_value=SOURCE_SPEC),
                                     recipe_for=Mock(return_value={'stdio_args':['--stdio']}))
        self.package.local_sources=self.sources
        self.modules=patch.dict(sys.modules,{'source_admin_test':self.package})
        self.modules.start();self.addCleanup(self.modules.stop)
        self.row={'intake_kind':'repository','repository_url':'https://github.com/microsoft/markitdown',
                  'evidence':{},'commit_sha':'a'*40,'provenance':{'artifact':{'sha256':'b'*64}}}
        self.db=SimpleNamespace(fetch_one=AsyncMock(return_value={'id':'intake'}))
        self.publish=AsyncMock(return_value=('https://console/git/mcp/markitdown',{}))
        self.env=functions(APP/'agent_service.py',{'set_local_run'},
                           dict(__package__='source_admin_test',Depends=lambda fn:None,admin_caller=None,
                                approval_row=AsyncMock(return_value=self.row),pinned_image=AsyncMock(),db=self.db,
                                local_jobs=SimpleNamespace(manifest_errors=lambda *a:[],mirror_image=lambda *a:True),
                                os=os,Jsonb=lambda value:value,publish_internal_repo=self.publish,
                                ProvenanceMismatch=ValueError,HTTPException=HTTPException))

    async def submit(self,**changes):
        data={'image':'','build_from_source':True,'command':[],'mounts':[],'env':{},
              'reason_kind':'local_file','reason_text':'사내 로컬 문서 접근이 필요함',**changes}
        return await self.env['set_local_run']('intake',SimpleNamespace(**data,model_dump=lambda:dict(data)),{'principal':'admin'})

    async def test_admin_selects_recipe_stdio_and_publishes_copy_before_observation(self):
        out=await self.submit()
        self.assertEqual(out['local_run']['source'],SOURCE_SPEC)
        self.assertEqual(out['local_run']['command'],['--stdio'])
        self.assertEqual(out['local_run']['image'],'')
        self.publish.assert_awaited_once_with(self.row)
        query,params=self.db.fetch_one.call_args.args
        self.assertIn('provenance IS NOT DISTINCT FROM',query)
        self.assertEqual(params[1],'https://console/git/mcp/markitdown')
        self.assertEqual(params[0]['local_run']['source'],SOURCE_SPEC)
        self.env['pinned_image'].assert_not_awaited()

    async def test_conflicting_image_missing_recipe_or_changed_intake_cannot_be_signed(self):
        with self.assertRaises(HTTPException) as error:await self.submit(image='mcp/image')
        self.assertEqual(error.exception.status_code,422)
        self.publish.assert_not_awaited()
        self.sources.source_for.side_effect=ValueError('레시피 없음')
        with self.assertRaises(HTTPException) as error:await self.submit()
        self.assertEqual(error.exception.status_code,422);self.db.fetch_one.assert_not_awaited()
        self.sources.source_for.side_effect=None
        self.db.fetch_one.return_value=None
        with self.assertRaises(HTTPException) as error:await self.submit()
        self.assertEqual(error.exception.status_code,409)

    async def test_gateway_approval_rechecks_source_and_recipe_under_intake_lock(self):
        calls=[]
        async def execute(query,params=None):
            calls.append(query)
            return SimpleNamespace(fetchone=AsyncMock(return_value=self.row if 'mcp_intake_requests' in query else None))
        @asynccontextmanager
        async def transaction():yield SimpleNamespace(execute=execute)
        body=source_body()
        local={'manifest':body,'manifest_sha256':hashlib.sha256(runner.canonical(body)).hexdigest(),'observer_device':'device'}
        scope=functions(APP/'local_jobs.py',{'approve_manifest'},
                        {**G,'__package__':'source_admin_test','db':SimpleNamespace(transaction=transaction)})
        self.assertEqual(await scope['approve_manifest'](local,'intake'),local)
        self.assertTrue(any('mcp_intake_requests' in q and 'FOR SHARE' in q for q in calls))
        self.assertTrue(any('INSERT INTO local_approvals' in q for q in calls))
        for change in ({'commit':'f'*40},{'sha256':'f'*64},{'recipe_sha256':'f'*64},
                       {'dockerfile':SOURCE_SPEC['dockerfile']+'RUN echo changed\n'}):
            calls.clear();self.sources.source_for.return_value={**SOURCE_SPEC,**change}
            with self.subTest(change=change),self.assertRaises(ValueError):
                await scope['approve_manifest'](local,'intake')
            self.assertFalse(any('INSERT INTO local_approvals' in q for q in calls))


class PreparationStatus(unittest.TestCase):
    def test_prefetch_uses_the_same_source_preparation_function(self):
        body=source_body();digest=hashlib.sha256(runner.canonical(body)).hexdigest()
        request=Mock(return_value={'servers':[{'server_id':body['server_id'],'manifest':body,
                                              'signature':'signed','manifest_sha256':digest}]})
        with patch.object(runner,'signed',return_value=True),patch.object(runner,'ensure_mounts',return_value=[]), \
             patch.object(runner,'engine_configuration') as engine:
            runner.prepare_once({},request,Mock(),SimpleNamespace(),set(),{}, {})
        self.assertEqual(engine.call_args.kwargs,{'seconds':runner.PREFETCH_SECONDS,'request':request})
        self.assertEqual(runner.preparation['servers'][0]['status'],'준비됨')

    def test_preparation_request_uses_peer_uid_and_never_returns_a_token(self):
        env=functions(ROOT/'endpoint-agent/managed-linux.py',{'accept_preparation'},dict(struct=struct,socket=socket))
        local=SimpleNamespace(prepare_requested=threading.Event())
        connection=Mock()
        # Windows has no SO_PEERCRED; the production function is Linux-only.
        with patch.object(socket,'SO_PEERCRED',17,create=True):
            for uid,accepted in ((0,True),(2001,True),(2002,False)):
                local.prepare_requested.clear();connection.getsockopt.return_value=struct.pack('3i',1,uid,uid)
                answer=env['accept_preparation'](connection,{'uid':2001},local)
                self.assertEqual(answer,{'accepted':accepted});self.assertEqual(local.prepare_requested.is_set(),accepted)

    def test_status_projects_existing_runner_rows_and_p_requests_preparation(self):
        spec=importlib.util.spec_from_file_location('source_screen',ROOT/'endpoint-agent/kit_screen.py')
        screen=importlib.util.module_from_spec(spec);spec.loader.exec_module(screen)
        summary={'prepare_socket':'/run/fixture.sock','local':{'servers':[{'server':'notes','status':'빌드 실패','reason':'확인 필요'}]}}
        text=screen.frame(summary,lines=40,columns=120)
        for value in ('승인된 MCP','notes  빌드 실패  확인 필요','p 지금 다시 준비'):self.assertIn(value,text)
        fake=SimpleNamespace(summary={},window=True,cells=[],next='',draw=Mock(),stop=Mock(),read_key=Mock(side_effect=['p','q']))
        prepare=Mock()
        screen.live(lambda:summary,screen=fake,prepare=prepare)
        prepare.assert_called_once_with(summary)


if __name__=='__main__':unittest.main(verbosity=2)
