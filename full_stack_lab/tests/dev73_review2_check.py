"""Focused regressions for the DEV-73 second-review fixes; no database or engine required."""
from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
APP = LAB / "gateway" / "app"


def function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    return "\n".join(source.splitlines()[node.lineno - 1:node.end_lineno])


class ReviewFixes(unittest.TestCase):
    def test_resume_removes_server_stop_inside_transition_transaction(self):
        source = function_source(APP / "ops_response.py", "resume")
        self.assertIn("async with db.transaction() as connection:", source)
        self.assertLess(source.index("UPDATE mcp_servers SET status='PENDING'"),
                        source.index("DELETE FROM local_run_stops"))
        self.assertIn("DELETE FROM local_run_stops WHERE server_id=%s AND user_token='' AND device_id=''", source)
        suspend = function_source(APP / "ops_response.py", "suspend")
        self.assertIn("batch=None", suspend)
        self.assertIn('globals().get("local_jobs")', suspend)
        self.assertIn("local_runner.quiesce(server_id=server_id)", suspend)
        self.assertIn('scope["batch"] = batch', suspend)

    def test_request_params_limit_has_exact_boundary_and_both_guards(self):
        jobs_path = APP / "local_jobs.py"
        source = jobs_path.read_text(encoding="utf-8")
        self.assertIn('os.getenv("LOCAL_PARAMS_MAX_BYTES", "65536")', source)
        tree = ast.parse(source)
        selected = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))
                    and getattr(n, "name", None) in {"NotStarted", "canonical", "validate_params"}]
        namespace = {"json": json, "MAX_PARAMS_BYTES": 1}
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(jobs_path), "exec"), namespace)
        params = {"name": "call", "arguments": {"value": "x" * 48}}
        size = len(namespace["canonical"](params))
        namespace["MAX_PARAMS_BYTES"] = size
        namespace["validate_params"](params)
        namespace["MAX_PARAMS_BYTES"] = size - 1
        with self.assertRaises(namespace["NotStarted"]) as raised:
            namespace["validate_params"](params)
        self.assertEqual(raised.exception.local_policy, "P-RATE-003")

        exchange = function_source(jobs_path, "exchange")
        self.assertLess(exchange.index("validate_params(params)"), exchange.index("INSERT INTO local_jobs"))
        ingress = function_source(APP / "mcp_facade.py", "call_tool")
        self.assertLess(ingress.index("local_jobs.validate_params"), ingress.index("await execute_call"))
        self.assertIn("LOCAL_PARAMS_MAX_BYTES: ${LOCAL_PARAMS_MAX_BYTES:-65536}",
                      (LAB / "compose.yaml").read_text(encoding="utf-8"))

    def test_result_hash_is_for_value_after_storage_cap(self):
        source = function_source(APP / "local_jobs.py", "complete")
        self.assertLess(source.index("stored['bytes']+len(canonical(result))>RESULT_STORE_BYTES"),
                        source.index("digest = hashlib.sha256"))
        self.assertLess(source.index("digest = hashlib.sha256"), source.index("UPDATE local_jobs SET state="))
        self.assertIn("result_sha256=%s", source)

    def test_cancel_control_reads_recorded_stop_before_token_lock(self):
        source = function_source(APP / "local_jobs.py", "validate_job")
        self.assertLess(source.index("SELECT stop_requested FROM local_jobs"),
                        source.index("async with db.transaction()"))
        self.assertLess(source.index("if stop and stop['stop_requested']"), source.index("lock_execution(connection,row)"))

    def test_registration_view_uses_measured_mapping_and_d189_screen(self):
        source = function_source(APP / "core.py", "discover_for_registration")
        self.assertNotIn("LOCAL_ENGINE_SETTINGS", source)
        self.assertIn("isolation.get('engine_version')", source)
        self.assertIn("if namespace == \"host\":", source)
        self.assertIn("탈출 시 호스트 root", source)
        self.assertIn("WHERE server_id=%s AND device_id=%s AND evidence ? 'isolation'", source)
        self.assertIn('"user_mapping": isolation.get("uid_map") or "확인 안 됨"', source)
        self.assertIn('principal: str | None = None', source)

        console = (APP / "agent_static" / "console.js").read_text(encoding="utf-8")
        approval = console[console.index("function intakeApprovalFields("):console.index("async function showIntakeApproval(")]
        self.assertIn('const localRun = out.local_execution || p.local_execution || r.local_execution || r.evidence?.local_execution;', approval)
        self.assertIn("<legend>PC 격리 실행</legend>", approval)
        self.assertIn("localRun.user_mapping || unknown", approval)
        self.assertIn('async "intake-one-click"', console)
        self.assertNotIn('async "intake-approve"', console)
        self.assertNotIn('async "intake-approve-risk"', console)


if __name__ == "__main__":
    unittest.main(verbosity=2)
