"""Offline production-route checks. DB/auth/response doubles are not appliance evidence."""
import ast
import asyncio
import hashlib
import io
import json
import os
import re
import secrets
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlencode, urlsplit

APP = Path(__file__).resolve().parents[1] / 'gateway/app'


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail


class Response:
    def __init__(self, content, media_type=None, headers=None):
        self.body, self.headers = content, headers or {}


class Request:
    def __init__(self, ticket=None, *, body=None, query=''):
        self.headers = {'content-type': 'application/x-www-form-urlencoded; charset=UTF-8'}
        self.body = body if body is not None else urlencode({'ticket': ticket} if ticket is not None else {}).encode()
        self.query_params = parse_qs(query)

    async def stream(self):
        for offset in range(0, len(self.body), 128):
            yield self.body[offset:offset + 128]


class TicketDB:
    def __init__(self):
        self.grants = {}
        self.active = True

    async def execute(self, sql, params):
        assert 'INSERT INTO endpoint_enrollment_tokens' in sql
        digest, owner, expires = params
        self.grants[digest] = {'owner_token': owner, 'expires': expires, 'consumed': False}

    async def fetch_one(self, sql, params):
        if sql.startswith('SELECT user_id,token'):
            return {'user_id': 'staff', 'token': 'principal'} if self.active else None
        assert 'UPDATE endpoint_enrollment_tokens SET consumed_at=now()' in sql
        assert "p.status='active'" in sql
        assert 'consumed_at IS NULL AND expires_at>now()' in sql
        grant = self.grants.get(params[0])
        if not grant or grant['consumed'] or grant['expires'] <= datetime.now(timezone.utc) or not self.active:
            return None
        grant['consumed'] = True
        return grant


class KitDownloadCheck(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        for name in ('install.sh', 'install.cmd', 'windows-oneclick.ps1.in', 'python.zip', 'windows-python.json'):
            (folder / name).write_text('offline fixture', encoding='utf-8')
        self.env = patch.dict(os.environ, {'ENDPOINT_KIT_DIR': str(folder), 'WINDOWS_PYTHON_DIR': str(folder),
                                          'IDP_ISSUER': 'https://gateway.invalid', 'MCP_FIELD_MODE': '0'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.db = TicketDB()

        async def identity(authorization):
            if authorization != 'Bearer console':
                raise HTTPException(401, '로그인이 필요합니다.')
            return {'user_id': 'staff', 'principal': 'principal'}

        self.enrollment = AsyncMock(return_value={'enrollment_token': 'separate-enrollment'})
        endpoint = ModuleType('kit_test.endpoint_plane')
        endpoint.enrollment_token = self.enrollment
        commands = ModuleType('kit_test.kit_commands')
        exec(compile((APP / 'kit_commands.py').read_text(encoding='utf-8'), str(APP / 'kit_commands.py'), 'exec'), commands.__dict__)
        windows = ModuleType('kit_test.windows_oneclick')
        windows.launcher = lambda archive, template: b'cmd-fixture:' + archive
        self.modules = patch.dict(sys.modules, {'kit_test.endpoint_plane': endpoint,
                                               'kit_test.kit_commands': commands, 'kit_test.windows_oneclick': windows})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        scope = {**globals(), '__package__': 'kit_test', 'UTC': timezone.utc, 'db': self.db,
                 'hashlib': hashlib, 'secrets': secrets, 'urlsplit': urlsplit,
                 'Header': lambda **kw: None, 'current_identity': identity,
                 'field_ca': lambda: {'ca_certificate': 'certificate\n', 'ca_sha256': 'fixture-pin'},
                 'KIT_FILES': {'linux': ('install.sh',), 'macos': ('install.sh',), 'windows': ('install.cmd',)},
                 'KIT_EXECUTABLE': {'install.sh'}, 'STATIC_DIR': folder, 'JSONResponse': Response}
        (folder / 'kit').mkdir()
        (folder / 'kit/mcpgw_pc.py').write_text('fixture')
        tree = ast.parse((APP / 'agent_service.py').read_text(encoding='utf-8'))
        nodes = [node for node in tree.body if getattr(node, 'name', '') in {'kit_download_hash', 'download_managed_kit'}]
        for node in nodes:
            node.decorator_list = []
        # Production annotations are not needed for this standard-library route harness.
        module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *nodes],
                            type_ignores=[])
        exec(compile(ast.fix_missing_locations(module), str(APP / 'agent_service.py'), 'exec'), scope)
        self.download = scope['download_managed_kit']

    async def issue(self, **scope):
        request = Request()
        request.headers = {}
        result = await self.download(request, authorization='Bearer console', issue_ticket=True, **scope)
        self.assertEqual(result.headers['Cache-Control'], 'no-store')
        ticket = result.body['ticket']
        self.assertRegex(ticket, r'^[A-Za-z0-9_-]{43}$')
        grant = next(reversed(self.db.grants.values()))
        self.assertLessEqual(grant['expires'] - datetime.now(timezone.utc), timedelta(minutes=5))
        self.assertGreater(grant['expires'] - datetime.now(timezone.utc), timedelta(minutes=4, seconds=55))
        self.enrollment.assert_not_awaited()
        return ticket

    async def denied(self, request, **scope):
        with self.assertRaises(HTTPException) as caught:
            await self.download(request, **scope)
        self.assertIn(caught.exception.status_code, (401, 403))
        self.assertRegex(caught.exception.detail, '[가-힣]')

    async def test_issue_form_consume_once_and_attachment_headers(self):
        ticket = await self.issue()
        result = await self.download(Request(ticket))
        self.assertEqual(result.headers['Content-Disposition'], 'attachment; filename="mcp-managed-kit-linux.zip"')
        self.assertEqual(result.headers['Cache-Control'], 'no-store')
        with zipfile.ZipFile(io.BytesIO(result.body)) as archive:
            self.assertEqual(json.loads(archive.read('enrollment.json'))['owner'], 'staff')
        await self.denied(Request(ticket))

    async def test_all_output_scope_fields_are_bound_without_consuming_on_mismatch(self):
        ticket = await self.issue()
        for scope in ({'platform': 'macos'}, {'platform': 'windows'}, {'packaging': 'oneclick'},
                      {'isolated': True}, {'delivery': 'command'}):
            await self.denied(Request(ticket), **scope)
        await self.download(Request(ticket))

    async def test_expired_disabled_and_query_only_tickets_are_rejected(self):
        ticket = await self.issue()
        await self.denied(Request(query=urlencode({'ticket': ticket})))
        query_only = Request(query=urlencode({'ticket': ticket}))
        query_only.headers = {}
        await self.denied(query_only)
        self.db.active = False
        await self.denied(Request(ticket))
        self.db.active = True
        next(iter(self.db.grants.values()))['expires'] = datetime.now(timezone.utc) - timedelta(seconds=1)
        await self.denied(Request(ticket))

    async def test_bad_duplicate_oversized_forms_and_ticket_redelegation_are_rejected(self):
        for body in (b'', b'ticket=bad', b'ticket=' + b'x' * 43 + b'&ticket=' + b'y' * 43, b'x' * 1025):
            await self.denied(Request(body=body))
        ticket = await self.issue()
        await self.denied(Request(ticket), issue_ticket=True)
        await self.download(Request(ticket))

    async def test_authentication_is_required_for_issuance_and_header_download_still_works(self):
        request = Request()
        request.headers = {}
        await self.denied(request, issue_ticket=True)
        result = await self.download(Request(), authorization='Bearer console')
        self.assertEqual(result.headers['Cache-Control'], 'no-store')
        self.enrollment.assert_awaited_once()

    async def test_windows_oneclick_and_zip_keep_filenames(self):
        for packaging, filename in (('oneclick', 'mcp-managed-setup-windows.cmd'), ('zip', 'mcp-managed-kit-windows.zip')):
            self.enrollment.reset_mock()
            ticket = await self.issue(platform='windows', packaging=packaging, isolated=True)
            result = await self.download(Request(ticket), platform='windows', packaging=packaging, isolated=True)
            self.assertIn(filename, result.headers['Content-Disposition'])
            self.assertEqual(result.headers['Cache-Control'], 'no-store')

    async def test_macos_command_issues_a_separate_scoped_header_ticket(self):
        ticket = await self.issue(platform='macos', delivery='command', isolated=True)
        result = await self.download(Request(ticket), platform='macos', delivery='command', isolated=True)
        self.assertIn('mcp-connect-macos.command', result.headers['Content-Disposition'])
        self.assertEqual(result.headers['Cache-Control'], 'no-store')
        self.assertIn('?platform=macos&isolated=true', result.body)
        inner = re.search(r'Bearer kit-download\.([A-Za-z0-9_-]{43})', result.body)[1]
        await self.denied(Request(inner), platform='macos')
        request = Request()
        request.headers = {}
        archive = await self.download(request, platform='macos', isolated=True, authorization='Bearer kit-download.' + inner)
        self.assertIn('mcp-managed-kit-macos.zip', archive.headers['Content-Disposition'])
        await self.denied(request, platform='macos', isolated=True, authorization='Bearer kit-download.' + inner)

    async def test_two_consumers_get_one_success(self):
        ticket = await self.issue()
        results = await asyncio.gather(self.download(Request(ticket)), self.download(Request(ticket)), return_exceptions=True)
        self.assertEqual(sum(isinstance(result, Response) for result in results), 1)
        self.assertEqual(sum(isinstance(result, HTTPException) for result in results), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
