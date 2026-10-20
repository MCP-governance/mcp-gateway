"""DEV-20: real production parsers/collector with DB and engine doubles, never a mock MCP."""
from __future__ import annotations

import ast
import importlib.util
import hashlib
import subprocess
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('server_egress', ROOT / 'gateway/app/server_egress.py')
egress = importlib.util.module_from_spec(spec)
spec.loader.exec_module(egress)


def load_worker_functions(*names, **overrides):
    tree = ast.parse((ROOT / 'runtime/worker.py').read_text(encoding='utf-8'))
    selected = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names],
                          type_ignores=[])
    namespace = dict(server_egress=egress, datetime=datetime, timedelta=timedelta, timezone=timezone,
                     Jsonb=lambda value: value, RuntimeError=RuntimeError, subprocess=subprocess,
                     psycopg=types.SimpleNamespace(Error=type('DatabaseError', (Exception,), {})), **overrides)
    exec(compile(selected, 'runtime/worker.py', 'exec'), namespace)
    return types.SimpleNamespace(**{name: namespace[name] for name in names})


def log(message, second=1):
    return f'2026-10-20T00:00:{second:02d}.123456789Z CONNECT Oct 20 00:00:{second:02d}.123 [1]: {message}'


class ParserCheck(unittest.TestCase):
    def test_connected_denied_failed_are_distinct_and_not_business_effects(self):
        for message, outcome, port in [
                ('Established connection to host "api.example.org" using file descriptor 9.', 'connected', None),
                ('Proxying refused on filtered domain "outside.example.org"', 'blocked', None),
                ('opensock: Could not establish a connection to api.example.org:443', 'connect_failed', 443)]:
            item = egress.parse_log(log(message), 'proxy-1')
            self.assertEqual((item['outcome'], item['port']), (outcome, port))
            self.assertEqual(item['credential_use'], 'unobserved')
            self.assertIsNone(item['retry_count'])
            self.assertEqual(item['external_effect'], 'unverified')

    def test_no_urls_credentials_header_or_forged_multiline_survive(self):
        for message in ['Request (file descriptor 1): GET http://user:secret@api.example.org/?token=secret HTTP/1.1',
                        'Authorization: Bearer secret', 'Proxying refused on filtered url "http://x/?secret"',
                        'Established connection to host "user:secret@api.example.org" using file descriptor 9.',
                        'Proxying refused on filtered domain "api.example.org/?token=secret"',
                        'Proxying refused on filtered domain "x..example.org"',
                        'Proxying refused on filtered domain "x.example.org"\nAuthorization: secret']:
            self.assertIsNone(egress.parse_log(log(message), 'proxy-1'))

    def test_docker_timestamp_and_container_bind_event_identity(self):
        line = log('Proxying refused on filtered domain "outside.example.org"')
        first = egress.parse_log(line, 'proxy-1')
        self.assertEqual(first, egress.parse_log(line, 'proxy-1'))
        self.assertNotEqual(first['event_id'], egress.parse_log(line, 'proxy-2')['event_id'])
        self.assertNotEqual(first['event_id'], egress.parse_log(line.replace('01.123456789Z', '02.123456789Z'), 'proxy-1')['event_id'])
        self.assertEqual(egress.timestamp(first['observed_at']).microsecond, 123456)

    def test_malformed_time_and_invalid_port_are_ignored(self):
        line = log('Proxying refused on filtered domain "outside.example.org"')
        self.assertIsNone(egress.parse_log(line.replace('2026-10-20', 'invalid'), 'proxy-1'))
        self.assertIsNone(egress.parse_log(log('opensock: Could not establish a connection to api.example.org:65536'), 'p'))


class CorrelationCheck(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 20, tzinfo=timezone.utc)
        self.call = dict(server_id='server-a', request_id='req-a', trace_id='trace-a',
                         created_at=self.start + timedelta(seconds=10))
        self.intent = dict(attempted_at=self.start)

    def row(self, second=1, server='server-a'):
        item = egress.parse_log(log('Proxying refused on filtered domain "outside.example.org"', second), 'proxy-1')
        return dict(id=5, scope=dict(item, server_id=server, runtime='runtime-1', generation=1,
                                    proxy_container_id='proxy-1', proxy_image_id='sha256:image'))

    def test_same_server_actual_dispatch_interval_and_legacy_exclusion(self):
        rows = [self.row(), self.row(server='server-b'), self.row(second=11)]
        result = egress.correlate(self.call, self.intent, rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['state'], 'blocked')
        self.assertEqual(result[0]['link_strength'], 'corroborating')
        self.assertEqual(result[0]['candidate_trace_id'], 'trace-a')
        self.assertNotIn('request_id', result[0])
        self.assertEqual(egress.correlate(self.call, None, rows), [])
        self.assertEqual(egress.correlate(dict(self.call, request_id=None), self.intent, rows), [])

    def test_boundaries_inclusive_but_not_before_dispatch(self):
        low = dict(self.row()['scope'], observed_at=self.start.isoformat())
        high = dict(low, observed_at=self.call['created_at'].isoformat())
        before = dict(low, observed_at=(self.start - timedelta(microseconds=1)).isoformat())
        result = egress.correlate(self.call, self.intent, [dict(id=i, scope=s) for i, s in enumerate([low, high, before])])
        self.assertEqual(len(result), 2)

    def test_concurrent_calls_are_candidates_never_exact_or_retries(self):
        first = egress.correlate(self.call, self.intent, [self.row(), self.row(second=2)])
        second = egress.correlate(dict(self.call, request_id='req-b', trace_id='trace-b'), self.intent, [self.row()])
        self.assertEqual(first[0]['correlation_id'], second[0]['correlation_id'])
        self.assertEqual({r['link_strength'] for r in first + second}, {'corroborating'})
        self.assertTrue(all(r['retry_count'] is None for r in first + second))


class QueryCheck(unittest.IsolatedAsyncioTestCase):
    async def test_authenticated_correlation_reads_event_time_not_ingestion_time(self):
        package = types.ModuleType('egress_query_test')
        package.__path__ = []
        package.db = types.SimpleNamespace(fetch_all=AsyncMock(return_value=[]))
        old_package, old_spec = egress.__package__, egress.__spec__
        try:
            egress.__package__ = package.__name__
            egress.__spec__ = importlib.util.spec_from_loader(package.__name__ + '.server_egress', loader=None)
            with patch.dict(sys.modules, {package.__name__: package}):
                call = dict(server_id='s', request_id='r', created_at=datetime.now(timezone.utc))
                result = await egress.for_decision(call, dict(attempted_at=call['created_at']))
                self.assertEqual(result['observation_status'], 'unobserved')
                query, params = package.db.fetch_all.call_args.args
                self.assertIn('observed_at', query)
                self.assertEqual(params[0], 's')
                package.db.fetch_all.side_effect = RuntimeError('database unavailable')
                with self.assertRaises(RuntimeError):
                    await egress.for_decision(call, dict(attempted_at=call['created_at']))
                package.db.fetch_all.reset_mock()
                self.assertEqual((await egress.for_decision(call, None))['observation_status'], 'no_dispatch')
                package.db.fetch_all.assert_not_awaited()
        finally:
            egress.__package__, egress.__spec__ = old_package, old_spec


class CollectorCheck(unittest.TestCase):
    def setUp(self):
        self.runtime = dict(id='runtime-1', intake_id='intake-1', evidence={})
        self.proxy = dict(Id='proxy-1', Image='sha256:image', Created='2026-10-20T00:00:00Z',
                          Config=dict(Labels={'mcpgw.runtime': 'runtime-1', 'mcpgw.role': 'egress'}))
        self.db = Mock()
        self.events = []
        self.cursor = {}
        self.seen = set()

        def execute(sql, args):
            result = Mock()
            if 'FOR UPDATE' in sql:
                result.fetchone.return_value = dict(evidence=self.cursor.copy())
            elif 'registered_server_id' in sql:
                result.fetchone.return_value = dict(registered_server_id='server-a')
            elif 'SELECT 1 FROM approval_events' in sql:
                result.fetchone.return_value = {'found': 1} if args[1] in self.seen else None
            elif 'jsonb_set' in sql:
                self.cursor['egress_log_cursor'] = args[0]
            else:
                raise AssertionError(sql)
            return result

        def event(connection, runtime, kind, outcome='recorded', scope=None):
            self.seen.add(scope['event_id'])
            self.events.append((kind, outcome, scope))

        self.db.execute.side_effect = execute
        self.docker = Mock(return_value=subprocess.CompletedProcess([], 0, log(
            'Proxying refused on filtered domain "outside.example.org"'), ''))
        self.worker = load_worker_functions('collect_egress', docker=self.docker, event=event)

    def test_overlap_replay_is_idempotent_and_new_container_is_separate(self):
        for _ in range(2):
            self.worker.collect_egress(self.db, self.runtime, self.proxy)
        self.assertEqual(len(self.events), 1)
        kind, outcome, scope = self.events[0]
        self.assertEqual((kind, outcome, scope['server_id']), ('runtime-egress', 'recorded', 'server-a'))
        self.assertEqual(scope['proxy_image_id'], 'sha256:image')
        self.worker.collect_egress(self.db, self.runtime, dict(self.proxy, Id='proxy-2'))
        self.assertEqual(len(self.events), 2)

    def test_engine_failure_does_not_advance_checkpoint(self):
        self.docker.side_effect = RuntimeError('engine unavailable')
        with self.assertRaises(RuntimeError):
            self.worker.collect_egress(self.db, self.runtime, self.proxy)
        self.db.execute.assert_not_called()
        self.assertFalse(self.events)

    def test_wrong_proxy_and_truncated_log_batch_fail(self):
        proxy = dict(self.proxy, Config=dict(Labels={'mcpgw.runtime': 'other', 'mcpgw.role': 'egress'}))
        with self.assertRaises(RuntimeError):
            self.worker.collect_egress(self.db, self.runtime, proxy)
        self.docker.assert_not_called()
        self.docker.return_value.stdout = '\n'.join(['line'] * 10001)
        with self.assertRaises(RuntimeError):
            self.worker.collect_egress(self.db, self.runtime, self.proxy)
        self.db.execute.assert_not_called()

    def test_commit_failure_is_not_success_and_replay_can_recover(self):
        self.db.commit.side_effect = [None, RuntimeError('commit acknowledgement lost')]
        with self.assertRaises(RuntimeError):
            self.worker.collect_egress(self.db, self.runtime, self.proxy)
        self.db.commit.side_effect = None
        self.worker.collect_egress(self.db, self.runtime, self.proxy)
        self.assertEqual(len(self.events), 1)

    def test_stale_collector_does_not_move_cursor_backwards(self):
        future = '2099-01-01T00:00:00Z'
        self.cursor['egress_log_cursor'] = dict(container_id='proxy-1', until=future)
        self.worker.collect_egress(self.db, self.runtime, self.proxy)
        self.assertEqual(self.cursor['egress_log_cursor']['until'], future)
        self.db.rollback.assert_called_once()
        self.assertFalse(self.events)

    def test_observation_failure_removes_superseded_filter_before_propagating(self):
        proxy = dict(self.proxy, State=dict(Running=True),
                     Config=dict(Labels={'mcpgw.allow': 'old'}))
        docker = Mock()
        worker = load_worker_functions('sync_egress', hashlib=hashlib, names=lambda r: dict(egress='proxy'),
                                       egress_filter=lambda h: '^$', destinations=lambda i: [],
                                       inspect=lambda kind, name: proxy, docker=docker,
                                       collect_egress=Mock(side_effect=RuntimeError('logs unavailable')))
        with self.assertRaises(RuntimeError):
            worker.sync_egress(self.db, self.runtime, {})
        docker.assert_called_once_with('rm', '-f', 'proxy')

    def test_event_writer_only_appends_and_binds_runtime_generation(self):
        worker = load_worker_functions('event', WORKER_ID='worker')
        connection = Mock()
        worker.event(connection, dict(self.runtime, generation=2), 'runtime-egress', scope={'destination': 'example.org'})
        sql, params = connection.execute.call_args.args
        self.assertTrue(sql.startswith('INSERT INTO approval_events'))
        self.assertEqual(params[-1]['runtime'], self.runtime['id'])
        self.assertEqual(params[-1]['generation'], 2)


if __name__ == '__main__':
    unittest.main()
