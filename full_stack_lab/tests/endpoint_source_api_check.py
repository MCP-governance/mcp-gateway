"""D-263 authorization/streaming regression tests reused for source processes; HTTP/DB doubles only."""
from __future__ import annotations
import ast
import asyncio
import hashlib
import os
import re
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import quote, urlsplit
from approved_mcp_download_check import BackgroundTask, HTTPException, StreamingResponse
from dev73_rework_check import APP
from open_endpoints import route_auth
ROOT=APP.parents[2]
SOURCE=APP/'local_sources.py'
SOURCE_SPEC={'commit':'a'*40,'sha256':'b'*64,'runtime':'python','entrypoint':'main.py',
             'lock':'requirements.lock','lock_sha256':'c'*64,
             'locks':{key:{'python':version,'sha256':'c'*64,'packages':1} for key,version in [('win_amd64','3.13'),('linux_x86_64','3.12')]}}


def functions(path,names,scope):
    nodes=[n for n in ast.parse(path.read_text(encoding='utf-8')).body
           if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names]
    assert {n.name for n in nodes}==set(names)
    for node in nodes:
        node.decorator_list=[]
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*nodes],type_ignores=[])
    exec(compile(ast.fix_missing_locations(module),str(path),'exec'),scope)
    return scope

def gateway_scope():
    return functions(SOURCE,{'source_errors','source_for','authorized_source','receive','download'},
                     dict(asyncio=asyncio,hashlib=hashlib,os=os,re=re,Path=Path,quote=quote,urlsplit=urlsplit,
                          tempfile=tempfile,HTTPException=HTTPException,StreamingResponse=StreamingResponse,
                          BackgroundTask=BackgroundTask,DOWNLOAD_SLOTS=asyncio.Semaphore(1),httpx=SimpleNamespace(HTTPError=OSError)))

class SourceSpec(unittest.TestCase):
    def test_legacy_execution_is_ineligible_without_mutating_history(self):
        history={'servers':{'old':{'runtime':{'id':'old'}}, 'remote':{'endpoint':'https://vendor/mcp'},
                            'pc':{'local':{'manifest_sha256':'d'*64}}}}
        scope=functions(APP/'registry.py',{'servers','server'},dict(catalog=lambda:history))
        self.assertEqual(set(scope['servers']()),{'remote','pc'})
        self.assertIsNone(scope['server']('old'))
        self.assertIn('old',history['servers'])

    def test_python_source_cannot_use_an_unscanned_legacy_lock(self):
        scope=gateway_scope()
        row={'intake_kind':'repository','validated_at':'verified','commit_sha':SOURCE_SPEC['commit'],
             'provenance':{'artifact':{'sha256':SOURCE_SPEC['sha256']}},
             'evidence':{'local_run':{'source':{k:v for k,v in SOURCE_SPEC.items() if k!='locks'}}}}
        with self.assertRaisesRegex(ValueError,'플랫폼별 잠금'):scope['source_for'](row)

    def test_source_metadata_pins_validation_and_lock(self):
        scope=gateway_scope()
        row={'intake_kind':'repository','validated_at':'verified','commit_sha':SOURCE_SPEC['commit'],
             'provenance':{'artifact':{'sha256':SOURCE_SPEC['sha256']}},'evidence':{'local_run':{'source':SOURCE_SPEC},'endpoint_source':SOURCE_SPEC}}
        self.assertEqual(scope['source_for'](row),SOURCE_SPEC)
        for change in ({'commit_sha':'f'*40},{'validated_at':None},{'provenance':{}},{'intake_kind':'remote-endpoint'}):
            with self.assertRaises(ValueError):scope['source_for']({**row,**change})
        for change in ({'entrypoint':'../escape'},{'lock':'C:/escape'},{'runtime':'shell'},{'lock_sha256':'bad'},
                       {'image':'extra'}):
            self.assertTrue(scope['source_errors']({**SOURCE_SPEC,**change}))


class DeviceAPI(unittest.IsolatedAsyncioTestCase):
    async def test_migration_revalidation_preserves_commit_and_requires_admin(self):
        database=SimpleNamespace(fetch_one=AsyncMock(side_effect=[{'intake_kind':'repository'}, {'id':'intake'}]))
        scope=functions(APP/'agent_service.py',{'queue_validation'},dict(
            current_identity=AsyncMock(return_value={'roles':['admin'],'principal':'admin'}),db=database,
            HTTPException=HTTPException,Header=lambda **kw:None))
        await scope['queue_validation']('intake',None)
        query=database.fetch_one.call_args.args[0]
        self.assertIn('revalidation_commit',query)
        self.assertIn("status='APPROVED' AND EXISTS",query)
        self.assertIn('mcp_runtimes',query)
        scope['current_identity'].return_value={'roles':['employee']}
        database.fetch_one.reset_mock()
        with self.assertRaises(HTTPException) as error:await scope['queue_validation']('intake',None)
        self.assertEqual(error.exception.status_code,403)
        database.fetch_one.assert_not_awaited()
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

    def test_solution_runtime_routes_and_worker_are_removed(self):
        tree=ast.parse((APP/'agent_service.py').read_text(encoding='utf-8'))
        self.assertFalse(any(getattr(node,'name','') in {'start_runtime','stop_runtime','rollback_runtime','runtime_recipe'} for node in tree.body))
        self.assertFalse((APP.parents[1]/'runtime/worker.py').exists())

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

    async def test_lock_commit_or_source_replacement_refuses(self):
        self.scope['source_for'].return_value={**SOURCE_SPEC,'lock_sha256':'f'*64}
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

    async def test_lock_download_is_authenticated_rechecked_and_hash_verified(self):
        before=await self.check()
        content=b'package==1 --hash=sha256:' + b'a'*64 + b'\n'
        digest=hashlib.sha256(content).hexdigest()
        before={**before,'source':{**SOURCE_SPEC,'locks':{'win_amd64':{'sha256':digest}}}}
        self.scope['authorized_source']=AsyncMock(return_value=before)
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'INTAKE_REPORT_DIR':folder}):
            path=Path(folder)/f'dependency-{digest}.lock'
            path.write_bytes(content)
            response=await self.scope['download'](self.device,'local-files','e'*64,'win_amd64')
            self.assertEqual(b''.join([b async for b in response.body_iterator]),content)
            self.assertEqual(response.headers['X-Content-SHA256'],digest)
            self.assertEqual(self.scope['authorized_source'].await_count,2)
            path.write_bytes(b'tampered')
            with self.assertRaises(HTTPException) as error:
                await self.scope['download'](self.device,'local-files','e'*64,'win_amd64')
            self.assertEqual(error.exception.status_code,409)
            with self.assertRaises(HTTPException):
                await self.scope['download'](self.device,'local-files','e'*64,'../escape')

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

if __name__=="__main__":unittest.main(verbosity=2)
