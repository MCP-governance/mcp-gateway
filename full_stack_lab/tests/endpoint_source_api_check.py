"""D-263 authorization/streaming regression tests reused for source processes; HTTP/DB doubles only."""
from __future__ import annotations
import ast
import asyncio
import hashlib
import os
import re
import tempfile
import sys
from types import ModuleType
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
             'lock':'requirements.lock','lock_sha256':'c'*64}


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
    def test_source_metadata_pins_validation_and_lock(self):
        scope=gateway_scope()
        row={'intake_kind':'repository','validated_at':'verified','commit_sha':SOURCE_SPEC['commit'],
             'provenance':{'artifact':{'sha256':SOURCE_SPEC['sha256']}},'evidence':{'local_run':{'source':SOURCE_SPEC}}}
        self.assertEqual(scope['source_for'](row),SOURCE_SPEC)
        for change in ({'commit_sha':'f'*40},{'validated_at':None},{'provenance':{}},{'intake_kind':'remote-endpoint'}):
            with self.assertRaises(ValueError):scope['source_for']({**row,**change})
        for change in ({'entrypoint':'../escape'},{'lock':'C:/escape'},{'runtime':'shell'},{'lock_sha256':'bad'},
                       {'image':'extra'}):
            self.assertTrue(scope['source_errors']({**SOURCE_SPEC,**change}))


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

    async def test_stdio_cannot_queue_or_reconcile_in_solution_runtime(self):
        row={'intake_kind':'repository','status':'APPROVED','commit_sha':'a'*40,
             'internal_repo_url':'internal','requested_transport':'stdio'}
        database=SimpleNamespace(fetch_one=AsyncMock(side_effect=[row,None]))
        scope=functions(APP/'agent_service.py',{'start_runtime'},dict(
            current_identity=AsyncMock(return_value={'roles':['admin']}),db=database,HTTPException=HTTPException,Header=lambda **kw:None))
        errors=ModuleType('psycopg.errors');errors.UniqueViolation=RuntimeError
        with patch.dict(sys.modules,{'psycopg.errors':errors}):
            with self.assertRaises(HTTPException) as error:await scope['start_runtime']('intake',None)
        self.assertEqual(error.exception.status_code,409)
        self.assertEqual(database.fetch_one.await_count,2)
        connection=Mock()
        connection.execute.return_value.fetchone.return_value=row
        worker=functions(APP.parents[1]/'runtime/worker.py',{'approval_problem'}, {})
        reason=worker['approval_problem'](connection,{'intake_id':'intake'}, {})
        self.assertIn('stdio',reason)
        self.assertEqual(connection.execute.call_count,1)

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
