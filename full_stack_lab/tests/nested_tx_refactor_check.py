"""Connection/commit ordering checks using real function ASTs and stdlib doubles, no service startup."""
from __future__ import annotations

import ast
import asyncio
import sys
import threading
import types
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

APP = Path(__file__).resolve().parents[1] / 'gateway/app'


def load(file, names, **namespace):
    tree = ast.parse((APP / file).read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    assert len(nodes) == len(names)
    for node in nodes:
        node.decorator_list = [d for d in node.decorator_list if isinstance(d, ast.Name) and d.id == 'asynccontextmanager']
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)] + nodes, type_ignores=[])
    namespace.update(__package__='app', asynccontextmanager=asynccontextmanager)
    exec(compile(ast.fix_missing_locations(module), file, 'exec'), namespace)
    return types.SimpleNamespace(**namespace)


class ConnectionReuse(unittest.IsolatedAsyncioTestCase):
    async def test_db_helpers_and_savepoint_do_not_acquire(self):
        cursor = types.SimpleNamespace(fetchone=AsyncMock(return_value={'id': 1}), fetchall=AsyncMock(return_value=[{'id': 1}]), rowcount=1)
        connection = types.SimpleNamespace(execute=AsyncMock(return_value=cursor))
        @asynccontextmanager
        async def transaction():
            yield
        connection.transaction = transaction
        pool = AsyncMock(side_effect=AssertionError('second pool acquisition'))
        db = load('db.py', ['_run', 'fetch_one', 'fetch_all', 'execute', 'transaction'], pool=pool)
        self.assertEqual(await db.fetch_one('SELECT', connection=connection), {'id': 1})
        self.assertEqual(await db.fetch_all('SELECT', connection=connection), [{'id': 1}])
        self.assertEqual(await db.execute('UPDATE', (1,), connection=connection), 1)
        async with db.transaction(connection=connection) as actual:
            self.assertIs(actual, connection)
        pool.assert_not_awaited()

    async def test_token_stop_commits_separately_but_poll_reuses_locked_connection(self):
        cursor = types.SimpleNamespace(fetchone=AsyncMock(side_effect=[{'id': 1}, None]))
        connection = types.SimpleNamespace(execute=AsyncMock(return_value=cursor))
        db = types.SimpleNamespace(execute=AsyncMock(), fetch_one=AsyncMock(side_effect=AssertionError('pooled polling')))
        module = load('local_jobs.py', ['prepare_token_revocation'], asyncio=asyncio, db=db, RUN_SECONDS=20)
        await module.prepare_token_revocation(connection, [{'jti': 'jti'}])
        db.execute.assert_awaited_once()
        db.fetch_one.assert_not_awaited()
        self.assertIn('pg_advisory_xact_lock', connection.execute.call_args_list[0].args[0])
        self.assertIn('stop_requested=true', db.execute.call_args.args[0])
        self.assertIn('stopped_at IS NULL', connection.execute.call_args_list[-1].args[0])

    async def test_revocation_tombstone_finishes_before_database_revocation_without_blocking_loop(self):
        events = []
        started, release = threading.Event(), threading.Event()
        def remember_token(*_):
            started.set()
            if not release.wait(3):
                raise RuntimeError('event loop did not release worker')
            events.append('durable')
        async def execute(sql, *_):
            if sql.startswith('SELECT jti'):
                rows = [{'jti': 'j', 'expires_at': 'expiry'}]
            elif sql.startswith('SELECT token_sha256'):
                rows = []
            else:
                self.assertIn('durable', events)
                events.append('db-revocation')
                rows = []
            return types.SimpleNamespace(fetchall=AsyncMock(return_value=rows))
        local_jobs = types.ModuleType('app.local_jobs')
        local_jobs.prepare_token_revocation = AsyncMock()
        package = types.ModuleType('app')
        package.local_jobs = local_jobs
        module = load('idp.py', ['_revoke_family'], asyncio=asyncio,
                      disposal=types.SimpleNamespace(remember_token=remember_token), db=None)
        with patch.dict(sys.modules, {'app': package, 'app.local_jobs': local_jobs}):
            task = asyncio.create_task(module._revoke_family('family', types.SimpleNamespace(execute=execute)))
            try:
                for _ in range(200):
                    if started.is_set():
                        break
                    await asyncio.sleep(.005)
                self.assertTrue(started.is_set())
                self.assertFalse(task.done())
            finally:
                release.set()
                await task
        self.assertEqual(events[0], 'durable')
        self.assertEqual(events.count('db-revocation'), 2)

    async def test_disposal_error_prevents_database_revocation(self):
        cursor = types.SimpleNamespace(fetchall=AsyncMock(side_effect=[[{'jti': 'j', 'expires_at': 'expiry'}], []]))
        connection = types.SimpleNamespace(execute=AsyncMock(return_value=cursor))
        local = types.ModuleType('app.local_jobs')
        local.prepare_token_revocation = AsyncMock()
        package = types.ModuleType('app')
        package.local_jobs = local
        module = load('idp.py', ['_revoke_family'], asyncio=asyncio,
                      disposal=types.SimpleNamespace(remember_token=Mock(side_effect=OSError('fsync failed'))), db=None)
        with patch.dict(sys.modules, {'app': package, 'app.local_jobs': local}), self.assertRaises(OSError):
            await module._revoke_family('family', connection)
        self.assertEqual(connection.execute.await_count, 2)


    async def test_review_transition_and_event_use_the_supplied_connection(self):
        events = []
        cursor = types.SimpleNamespace(fetchone=AsyncMock(return_value={'id': 1}))
        connection = types.SimpleNamespace(execute=AsyncMock(return_value=cursor))
        @asynccontextmanager
        async def transaction(*, connection=None):
            self.assertIsNotNone(connection)
            yield connection
        async def record_event(**event):
            self.assertIs(event['connection'], connection)
            events.append(event)
        review = load('review.py', ['transition'], db=types.SimpleNamespace(transaction=transaction), record_event=record_event)
        await review.transition('UPDATE', (), connection=connection, kind='approval')
        self.assertEqual(len(events), 1)
        cursor.fetchone.return_value = None
        await review.transition('UPDATE', (), connection=connection, kind='approval')
        self.assertEqual(len(events), 1)

    async def test_independence_refusal_is_durable_outside_the_callers_connection(self):
        class NotIndependent(PermissionError):
            pass
        record = AsyncMock()
        same_person = AsyncMock(return_value=True)
        review = load('review.py', ['require_independent'], same_person=same_person, record_event=record, NotIndependent=NotIndependent)
        connection = object()
        with self.assertRaises(NotIndependent):
            await review.require_independent('approval', 'intake', 'id', 'alias-a', 'alias-b', connection=connection)
        self.assertIs(same_person.call_args.kwargs['connection'], connection)
        self.assertNotIn('connection', record.call_args.kwargs)
        self.assertEqual(record.call_args.args[1], 'refused')


class SessionExclusion(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, *, acquired=True, failure=None, unlock_failure=False):
        events = []
        cursor = types.SimpleNamespace(fetchone=AsyncMock(return_value={'acquired': acquired}))
        async def execute(sql):
            events.append(sql)
            if unlock_failure and 'pg_advisory_unlock' in sql:
                raise OSError('connection lost')
            return cursor
        guard = types.SimpleNamespace(execute=execute, commit=AsyncMock(side_effect=lambda: events.append('commit')),
                                      rollback=AsyncMock(), close=AsyncMock())
        @asynccontextmanager
        async def connection():
            yield guard
        async def work(*_):
            self.assertIn('commit', events)
            self.assertNotIn('SELECT pg_advisory_unlock(721017121)', events)
            if failure:
                raise failure
        incidents = types.ModuleType('app.incidents')
        incidents.check_deadlines = AsyncMock()
        package = types.ModuleType('app')
        package.incidents = incidents
        work = AsyncMock(side_effect=work)
        module = load('ops_response.py', ['tick'], db=types.SimpleNamespace(pool=AsyncMock(return_value=types.SimpleNamespace(connection=connection))),
                      observed_alerts=work, contain_repeated=AsyncMock(), self_test=AsyncMock(), LOG=Mock())
        with patch.dict(sys.modules, {'app': package, 'app.incidents': incidents}):
            try:
                await module.tick('opa')
            except BaseException:
                if not failure and not unlock_failure:
                    raise
        self.assertEqual(work.await_count, int(acquired))
        self.assertIn('SELECT pg_advisory_unlock(721017121)', events)
        self.assertEqual(guard.close.await_count, int(unlock_failure))

    async def test_session_guard_commits_before_work(self):
        await self.exercise()

    async def test_loser_does_not_run_work(self):
        await self.exercise(acquired=False)

    async def test_work_error_unlocks(self):
        await self.exercise(failure=RuntimeError('work failed'))

    async def test_cancellation_unlocks(self):
        await self.exercise(failure=asyncio.CancelledError())

    async def test_unlock_failure_closes_session(self):
        await self.exercise(unlock_failure=True)


class ApprovalOrdering(unittest.IsolatedAsyncioTestCase):
    async def test_registration_runs_after_commit_and_failure_keeps_approval(self):
        # Use the complete production approval function, with external/DB boundaries replaced only.
        from datetime import datetime, timedelta, timezone
        state = {'inside': False, 'approved': False}
        lock = types.SimpleNamespace(execute=AsyncMock())
        @asynccontextmanager
        async def transaction():
            state['inside'] = True
            try:
                yield lock
            except BaseException:
                state['approved'] = False
                raise
            finally:
                state['inside'] = False
        proposal = {'expires_at': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                    'blockers': [], 'basis': 'basis', 'tools': {'read': 'r'}, 'supplier_assurance': {},
                    'data_class': 'public', 'jurisdiction_pack_enabled': False, 'endpoint': 'https://example.test',
                    'catalog': {'catalog_hash': 'hash', 'server_name': 'name', 'version': '1', 'protocol_version': 'p'},
                    'provenance': {}, 'scan_sha256': 'scan', 'risk': {'tier': 'low'},
                    'tool_reviews': {'read': {}}, 'server_id': 'server', 'parameter_constraints': {'read': {}}, 'risk_input': {}}
        row = {'evidence': {'approval_proposal': proposal}, 'submitted_by': 'employee', 'intake_kind': 'remote-endpoint'}
        request = types.SimpleNamespace(proposal_sha256='digest', tools=['read'], actions={}, destinations={},
                                       audience='all', audience_users=[], supplier_assurance={}, residency={}, valid_days=1,
                                       critical_reason='', risk_reason='')
        async def transition(*_, connection=None, **__):
            self.assertIs(connection, lock)
            state['approved'] = True
            return {'id': 'id'}
        async def register(*_):
            self.assertFalse(state['inside'])
            self.assertTrue(module.INTAKE_APPROVAL_LOCK.locked())
            self.assertTrue(state['approved'])
            raise OSError('gateway unavailable')
        review = types.SimpleNamespace(intake_gate=AsyncMock(return_value={'blockers': []}),
            solo_mode_enabled=lambda: False, solo_operator=lambda _: False, same_person=AsyncMock(return_value=False),
            transition=transition, record_event=AsyncMock(), RISK_ACCEPTANCE_MIN_REASON=10)
        model = lambda **values: types.SimpleNamespace(model_dump=lambda: values)
        module = load('agent_service.py', ['approve_and_register'], INTAKE_APPROVAL_LOCK=asyncio.Lock(),
            db=types.SimpleNamespace(transaction=transaction), approval_row=AsyncMock(return_value=row),
            intake_proposal=types.SimpleNamespace(digest=lambda _: 'digest', basis=lambda _: 'basis', scan_basis=lambda _: 'scan'),
            datetime=datetime, timedelta=timedelta, UTC=timezone.utc, review=review,
            resolve_audience=AsyncMock(return_value=['*']),
            supplier_assurance=types.SimpleNamespace(ASSURANCE_FIELDS=(), validate=lambda *_, **__: [], unconfirmed=lambda _: []),
            residency=types.SimpleNamespace(normalize=lambda _: {}, require_location=lambda *_: None, enabled=lambda _: False),
            gateway_proxy=AsyncMock(side_effect=[{'organization': {}}, {**proposal['catalog'], 'tools': [{'name': 'read'}]}]),
            discovery=lambda *_: {},
            artifact_provenance=types.SimpleNamespace(verify_source_attestation=lambda *_: {}, blocking_reason=lambda _: None),
            risk_tier=types.SimpleNamespace(APPROVAL={'low': {'reason': 'optional'}}, decide=lambda *_: ('approve', ''), MIN_REASON=10),
            IntakeRegistration=model, Jsonb=lambda v: v, canonical_hash=lambda _: 'hash',
            register_mcp_request=register, Depends=lambda _: None, admin_caller=None, Header=lambda **_: None)
        with self.assertRaisesRegex(OSError, 'gateway unavailable'):
            await module.approve_and_register('id', request, {'principal': 'admin'}, 'token')
        self.assertTrue(state['approved'])
        self.assertIs(module.approval_row.call_args.kwargs['connection'], lock)
        self.assertIs(review.intake_gate.call_args.kwargs['connection'], lock)
        self.assertIs(review.record_event.call_args.kwargs['connection'], lock)


if __name__ == '__main__':
    unittest.main()
