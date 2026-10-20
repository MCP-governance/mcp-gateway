"""Offline response-cap boundary tests; not evidence of MCP execution."""
import ast
import importlib.util
import json
from pathlib import Path
import posixpath
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

APP = Path(__file__).resolve().parent.parent / "gateway" / "app"


def selected(file, names, **namespace):
    tree = ast.parse((APP / file).read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if getattr(node, "name", None) in names or
             isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in names
                                                   for target in node.targets)]
    found = {getattr(node, "name", None) for node in nodes}
    found.update(target.id for node in nodes if isinstance(node, ast.Assign)
                 for target in node.targets if isinstance(target, ast.Name))
    assert set(names) <= found, set(names) - found
    exec(compile(ast.fix_missing_locations(ast.Module(
        body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes],
        type_ignores=[])), file, "exec"), namespace)
    return SimpleNamespace(**namespace)


def cap_helpers(items=3, byte_limit=1000, parser=None):
    classifier = selected("classify.py", ["LISTING_TOOLS", "result_items", "bulk_read_reason"],
                          json=json, posixpath=posixpath, pgparser=parser)
    core = selected("core.py", ["body_of", "_decoded_strings", "_guarded_result", "_inspected_result",
                                 "ResultRejected"],
                    asyncio=SimpleNamespace(timeout=lambda _: __import__("contextlib").nullcontext()),
                    classify=classifier, json=json, MAX_RESULT_BYTES=byte_limit, MAX_RESULT_ITEMS=items,
                    OUTPUT_INSPECTION_TIMEOUT_SECONDS=30,
                    _validate_output=lambda *_: None,
                    output_contract=SimpleNamespace(for_protocol=lambda payload, _: payload),
                    privacy=SimpleNamespace(mask_payload=AsyncMock()),
                    secret_scan=SimpleNamespace(labels=AsyncMock(return_value=[])),
                    poisoning=SimpleNamespace(result_findings=lambda _: []),
                    response_evidence=lambda payload, disposition, *args: {
                        "disposition": disposition,
                        "bytes": len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))})
    return classifier, core


class ResponseCapBoundaries(unittest.IsolatedAsyncioTestCase):
    def test_item_limit_exact_and_plus_one_in_nested_arrays(self):
        classifier, core = cap_helpers(items=3)
        for value in ([1, 2, 3], [[1, 2]]):
            payload = {"structured": {"rows": value}, "content": []}
            self.assertEqual(classifier.result_items(payload), 3)
            self.assertIs(core._guarded_result(payload), payload)
        payload = {"structured": {"rows": [[1, 2, 3]]}, "content": []}
        self.assertEqual(classifier.result_items(payload), 4)
        with self.assertRaises(core.ResultRejected):
            core._guarded_result(payload)

    def test_exact_and_plus_one_utf8_bytes_across_structured_and_content(self):
        payload = {"structured": {"value": "한"},
                   "content": [{"type": "text", "text": "가"}]}
        exact = len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        _, core = cap_helpers(byte_limit=exact)
        self.assertIs(core._guarded_result(payload), payload)
        _, core = cap_helpers(byte_limit=exact - 1)
        with self.assertRaises(core.ResultRejected) as caught:
            core._guarded_result(payload)
        self.assertEqual(caught.exception.evidence["disposition"], "withheld")
        # JSON escaping would be shorter for ASCII-only dumps; the enforced size is UTF-8 bytes.
        self.assertGreater(len("한".encode("utf-8")), len("한"))

    async def test_masking_growth_past_byte_limit_is_withheld(self):
        _, core = cap_helpers(byte_limit=1000)
        original = {"content": [{"type": "text", "text": "ok"}]}
        expanded = {"content": [{"type": "text", "text": "x" * 1100}]}
        core.privacy.mask_payload.return_value = (expanded, ["EMAIL"])
        with self.assertRaises(core.ResultRejected) as caught:
            await core._inspected_result(original)
        self.assertEqual(caught.exception.evidence["disposition"], "withheld")
        self.assertGreater(caught.exception.evidence["bytes"], 1000)

    def test_broad_selector_variants_and_normal_scoped_selector(self):
        classifier, _ = cap_helpers()
        for path in ("/SHARED/*", "/shared/ *", "/shared/**/file", "/shared/[a-z]", "/shared/.."): 
            with self.subTest(path=path):
                self.assertIsNotNone(classifier.bulk_read_reason("filesystem", "list_directory",
                                                                  {"path": path}, 3))
        for pattern in ("*", " ** ", "**/*", " . ", "^.*$"):
            with self.subTest(pattern=pattern):
                self.assertIsNotNone(classifier.bulk_read_reason("filesystem", "search_files",
                                                                  {"path": "/shared/docs", "pattern": pattern}, 3))
        self.assertIsNone(classifier.bulk_read_reason("filesystem", "list_directory",
                                                       {"path": "/shared/public"}, 3))

    @unittest.skipUnless(importlib.util.find_spec("pglast"), "pglast unavailable: native parser not checked")
    def test_postgres_selector_case_whitespace_and_comments_use_native_parser(self):
        from pglast import parser
        classifier, _ = cap_helpers(parser=parser)
        for sql in ("select * from t limit 4", "SELECT * FROM t LIMIT /* cap */ 4",
                    "SELECT * FROM t LIMIT ALL", "SELECT * FROM t LIMIT /* comment */ -1"):
            with self.subTest(sql=sql):
                self.assertIsNotNone(classifier.bulk_read_reason("postgres", "execute_sql", {"sql": sql}, 3))
        for sql in ("sElEcT * FROM t LiMiT 3", "SELECT * FROM t /* LIMIT ALL */ LIMIT 2"):
            with self.subTest(sql=sql):
                self.assertIsNone(classifier.bulk_read_reason("postgres", "execute_sql", {"sql": sql}, 3))

    def test_rejection_route_preserves_execution_and_withheld_policy(self):
        source = (APP / "core.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        handlers = [node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)
                    and isinstance(node.type, ast.Name) and node.type.id == "ResultRejected"]
        self.assertEqual(len(handlers), 1)
        calls = [node for node in ast.walk(handlers[0]) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == "local_verdict"]
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual([arg.value for arg in call.args[:2] if isinstance(arg, ast.Constant)],
                         ["MCP-OUTPUT-001", "Block"])
        values = {keyword.arg: keyword.value for keyword in call.keywords}
        self.assertIsInstance(values["upstream_executed"], ast.Constant)
        self.assertIs(values["upstream_executed"].value, True)
        self.assertIsNone(values["result"].value)
        self.assertIn('"disposition": "withheld"', source)


if __name__ == "__main__":
    unittest.main()
