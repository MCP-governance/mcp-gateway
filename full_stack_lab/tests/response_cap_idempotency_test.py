"""Offline production-function tests with DB/scanner doubles, never MCP execution evidence."""
import ast
import base64
from contextlib import asynccontextmanager, contextmanager, nullcontext
import importlib.util
import json
import os
from pathlib import Path
import posixpath
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

APP = Path(__file__).resolve().parent.parent / "gateway" / "app"


def selected(file, names, **namespace):
    tree = ast.parse((APP / file).read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if getattr(node, "name", None) in names or
             isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets)]
    found = {getattr(n, "name", None) for n in nodes}
    found.update(t.id for n in nodes if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name))
    assert set(names) <= found, set(names) - found
    exec(compile(ast.fix_missing_locations(ast.Module(
        body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes],
        type_ignores=[])), file, "exec"), namespace)
    return SimpleNamespace(**namespace)


def classifier(parser=None):
    return selected("classify.py", ["LISTING_TOOLS", "result_items", "bulk_read_reason"],
                    json=json, posixpath=posixpath, pgparser=parser)


def guard(limit=3, byte_limit=1000):
    cls = classifier()
    return selected("core.py", ["body_of", "_decoded_strings", "_guarded_result", "ResultRejected"],
                    json=json, classify=cls, MAX_RESULT_BYTES=byte_limit, MAX_RESULT_ITEMS=limit,
                    response_evidence=lambda *args: {}, poisoning=SimpleNamespace(result_findings=lambda _: []))


class ResponseCaps(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("cryptography"), "cryptography unavailable: signed lab fixture not checked")
    def test_isolated_lab_uses_real_signed_store_and_restores_after_failure(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        spec = importlib.util.spec_from_file_location("offline_disposal", APP / "disposal.py")
        disposal = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(disposal)
        f = selected("../../tests/termination_lab_support.py", ["isolated_disposal"],
                     contextmanager=contextmanager, Ed25519PrivateKey=Ed25519PrivateKey, serialization=serialization,
                     base64=base64, tempfile=tempfile, patch=patch, os=os, Path=Path)
        previous, environment = disposal.DIRECTORY, dict(os.environ)
        with patch.dict(sys.modules, {"app": SimpleNamespace(disposal=disposal)}):
            with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                with f.isolated_disposal():
                    folder = disposal.DIRECTORY
                    self.assertEqual(os.environ["DISPOSAL_DIR"], str(folder))
                    self.assertEqual(disposal.read()[0]["kind"], "genesis")
                    self.assertFalse(disposal.blocked(server_id="untouched"))
                    raise RuntimeError("synthetic failure")
        self.assertEqual(disposal.DIRECTORY, previous)
        self.assertEqual(dict(os.environ), environment)
        self.assertFalse(folder.exists())

    def test_structured_nested_json_text_and_plain_lines(self):
        c = classifier()
        for payload in ({"structured": {"rows": [1, 2, 3, 4]}},
                        {"content": [{"type": "text", "text": '{"rows":[1,2,3,4]}'}]},
                        {"content": [{"type": "text", "text": "a\nb\nc\nd"}]},
                        {"content": [{"type": "text", "text": "[1,2]"}] * 2},
                        # review: records inside one JSON string scalar must not count as one item
                        {"content": [{"type": "text", "text": json.dumps("a\nb\nc\nd")}]},
                        {"structured": {"dump": "a\nb\nc\nd"}}):
            with self.subTest(payload=payload):
                self.assertEqual(c.result_items(payload), 4)

    def test_raw_count_boundary_and_no_truncation(self):
        g = guard()
        for size in (0, 3, 4):
            payload = {"content": [{"type": "text", "text": json.dumps(list(range(size)))}]}
            if size <= 3:
                self.assertIs(g._guarded_result(payload), payload)
            else:
                with self.assertRaises(g.ResultRejected) as caught:
                    g._guarded_result(payload)
                self.assertEqual(caught.exception.evidence["sha256"], None)

    def test_byte_boundary_uses_utf8(self):
        payload = {"content": [{"type": "text", "text": "한글"}]}
        size = len(json.dumps(payload, ensure_ascii=False).encode())
        self.assertEqual(guard(byte_limit=size)._guarded_result(payload), payload)
        g = guard(byte_limit=size - 1)
        with self.assertRaises(g.ResultRejected):
            g._guarded_result(payload)

    def test_folder_selectors_and_normal_lookup(self):
        c = classifier()
        for path in ("", "/", "/shared", "/shared/a/..", "*", "/shared/*", "//shared", "///shared/", "//"):
            with self.subTest(path=path):
                self.assertIsNotNone(c.bulk_read_reason("filesystem", "list_directory", {"path": path}, 3))
        self.assertIsNone(c.bulk_read_reason("filesystem", "list_directory", {"path": "/shared/public"}, 3))
        self.assertIsNone(c.bulk_read_reason("filesystem", "list_directory", {"path": "//shared/public"}, 3))
        self.assertEqual(c.result_items({"structured": {"name": "x", "note": "one line"}}), 0)
        for tool, args in (("directory_tree", {"path": "/shared/public"}),
                           ("search_files", {"path": "/shared/public", "pattern": "**/*"}),
                           ("read_multiple_files", {"paths": ["a", "b", "c", "d"]})):
            self.assertIsNotNone(c.bulk_read_reason("filesystem", tool, args, 3))

    def test_pagination_types_boundaries_and_nesting(self):
        c = classifier()
        for size in (True, -1, 0, "3", 4, None):
            self.assertIsNotNone(c.bulk_read_reason("gitea", "list_issues", {"pagination": {"pageSize": size}}, 3))
        self.assertIsNone(c.bulk_read_reason("gitea", "list_issues", {"perPage": 3}, 3))
        self.assertIsNotNone(c.bulk_read_reason("redis", "scan_all_keys", {}, 3))
        self.assertIsNotNone(c.bulk_read_reason("redis", "scan_keys", {"pattern": "*"}, 3))
        self.assertIsNone(c.bulk_read_reason("redis", "scan_keys", {"pattern": "public:*", "count": 3}, 3))

    def test_sql_ast_constant_limit_only(self):
        # Explicit parser double: native grammar integration is a separate check below.
        parser = SimpleNamespace(parse_sql_json=lambda _: json.dumps({"stmts": [{"stmt": {"SelectStmt": body}}]}))
        c = classifier(parser)
        for body, allowed in (({}, False), ({"limitCount": {"A_Const": {"isnull": True}}}, False),
                              ({"limitCount": {"ParamRef": {"number": 1}}}, False),
                              ({"limitCount": {"A_Const": {"ival": {"ival": 3}}}}, True),
                              ({"limitCount": {"A_Const": {"ival": {"ival": 4}}}}, False),
                              ({"limitOption": "LIMIT_OPTION_WITH_TIES",
                                "limitCount": {"A_Const": {"ival": {"ival": 3}}}}, False)):
            self.assertEqual(c.bulk_read_reason("postgres", "execute_sql", {"sql": "fixture"}, 3) is None, allowed)

    @unittest.skipUnless(importlib.util.find_spec("pglast"), "pglast unavailable: native SQL parser not checked")
    def test_native_postgres_grammar(self):
        from pglast import parser
        c = classifier(parser)
        for sql in ("SELECT * FROM t", "SELECT * FROM t LIMIT ALL", "SELECT * FROM t LIMIT -1",
                    "SELECT * FROM t LIMIT 4", "SELECT * FROM t LIMIT $1", "SELECT 1; SELECT 2",
                    "SELECT * FROM t FETCH FIRST 3 ROWS WITH TIES"):
            self.assertIsNotNone(c.bulk_read_reason("postgres", "execute_sql", {"sql": sql}, 3), sql)
        for sql in ("SELECT * FROM t LIMIT 3", "SELECT * FROM t LIMIT 0", "SELECT 'LIMIT ALL' LIMIT 1",
                    "WITH x AS (SELECT * FROM t) SELECT * FROM x LIMIT 3"):
            self.assertIsNone(c.bulk_read_reason("postgres", "execute_sql", {"sql": sql}, 3), sql)


class InspectedCaps(unittest.IsolatedAsyncioTestCase):
    async def test_masked_growth_is_withheld_and_inspection_failure_stays_closed(self):
        g = guard()
        class Unavailable(Exception):
            pass
        privacy = SimpleNamespace(mask_payload=AsyncMock(return_value=(
            {"content": [{"type": "text", "text": "x" * 1001}]}, ["EMAIL"])))
        # The timeout itself is outside this offline test (also runnable on Python 3.10).
        f = selected("core.py", ["_inspected_result"], asyncio=SimpleNamespace(timeout=lambda _: nullcontext()), privacy=privacy,
                     secret_scan=SimpleNamespace(labels=AsyncMock(return_value=[])), json=json,
                     _decoded_strings=g._decoded_strings, classify=classifier(), MAX_RESULT_BYTES=1000,
                     MAX_RESULT_ITEMS=3, OUTPUT_INSPECTION_TIMEOUT_SECONDS=30, ResultRejected=g.ResultRejected)
        with self.assertRaises(g.ResultRejected):
            await f._inspected_result({"content": []})
        privacy.mask_payload.return_value = ({"content": [{"type": "text", "text": "[1,2,3,4]"}]}, [])
        with self.assertRaises(g.ResultRejected):
            await f._inspected_result({"content": []})
        privacy.mask_payload.side_effect = Unavailable()
        with self.assertRaises(Unavailable):
            await f._inspected_result({"content": []})


class DispatchBoundary(unittest.IsolatedAsyncioTestCase):
    def boundary(self, duplicate=False, failure=False):
        queries = []
        async def execute(query, params=None):
            queries.append((query, params))
            if failure:
                raise OSError("store unavailable")
            row = ({"user_token": "u", "fingerprint": "hash"} if query.startswith("SELECT user_token") else
                   {"exists": 1} if query.startswith("SELECT 1 FROM dispatch_intents") and duplicate else None)
            return SimpleNamespace(fetchone=AsyncMock(return_value=row), rowcount=1)
        @asynccontextmanager
        async def transaction():
            yield SimpleNamespace(execute=execute)
        d = selected("dispatch.py", ["_Refused", "CATALOG_OK", "_INSERT", "REPLAY", "record"],
                     db=SimpleNamespace(transaction=transaction, fetch_one=AsyncMock(return_value={
                         "principal": "active", "lifecycle": "OPERATING", "server_status": "READY", "catalog_ok": True})),
                     IDEMPOTENCY_TTL_SECONDS=86400)
        return d, queries

    async def test_duplicate_write_is_refused_before_intent_insert(self):
        d, queries = self.boundary(duplicate=True)
        self.assertEqual(await d.record("new", "w"), "duplicate")
        self.assertFalse(any(q.startswith("INSERT") for q, _ in queries))
        self.assertIn("pg_advisory_xact_lock", queries[1][0])
        self.assertEqual(queries[2][1], ("u", "hash", "new", 86400))

    async def test_reads_remain_repeatable_and_first_write_records(self):
        for action in ("r", "w", "x"):
            d, queries = self.boundary(duplicate=action == "r")
            self.assertIsNone(await d.record("new", action))
            self.assertEqual(sum(q.startswith("INSERT") for q, _ in queries), 1)
            self.assertEqual(any(q.startswith("SELECT 1 FROM dispatch_intents") for q, _ in queries), action != "r")

    async def test_store_failure_does_not_admit(self):
        d, _ = self.boundary(failure=True)
        with self.assertRaises(OSError):
            await d.record("new", "w")


if __name__ == "__main__":
    unittest.main()
