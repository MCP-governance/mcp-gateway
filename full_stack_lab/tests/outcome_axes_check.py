"""Offline outcome and persistence checks; DB/HTTP objects are unit-test doubles only."""
from __future__ import annotations

import ast
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

APP = Path(__file__).resolve().parents[1] / "gateway" / "app"
if not APP.is_dir():
    APP = Path(__file__).resolve().parents[1] / "app"
spec = importlib.util.spec_from_file_location("outcomes", APP / "outcomes.py")
outcomes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(outcomes)


def selected(filename, names, namespace):
    tree = ast.parse((APP / filename).read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if getattr(node, "name", None) in names]
    if {node.name for node in nodes} != set(names):
        raise AssertionError("production definitions missing")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP / filename), "exec"), namespace)
    return SimpleNamespace(**namespace)


def event(**values):
    return {"decision": "Allow", "policy_id": "P-AUTHZ-ALLOW-001", "upstream_attempted": True,
            "upstream_executed": True, "result": {"content": [{"type": "text", "text": "done"}],
                                                    "is_error": False}, **values}


class OutcomeAxes(unittest.TestCase):
    def test_representative_cases(self):
        cases = [
            ("normal", event(), ("연결 성공", "허용", "업무 성공", "미확인")),
            ("denied", event(decision="Block", policy_id="P-SCOPE-001", upstream_attempted=False,
                             upstream_executed=False, result=None), ("미시도", "정책 거부", "미실행", "실행 안 됨")),
            *[(pid, event(decision="Block", policy_id=pid, upstream_attempted=False,
                          upstream_executed=False, result=None), ("미시도", "통제 장애 차단", "미실행", "실행 안 됨"))
              for pid in ["P-DATA-INSPECTION-001", "P-CONTROL-FAIL-CLOSED", "MCP-CATALOG-001",
                          "P-CONTROL-LEDGER-001", "INPUT_CONTRACT", "POLICY_BUNDLE"]],
            ("connection failure", event(decision="Block", policy_id="MCP-UPSTREAM-001",
                                         upstream_attempted=False, upstream_executed=False, result=None),
             ("연결 실패", "허용", "미실행", "실행 안 됨")),
            ("tool error", event(result={"is_error": True}), ("연결 성공", "허용", "도구 오류", "미확인")),
            ("quota", event(result={"content": [{"type": "text", "text": "Monthly quota exceeded. Create a free API key"}],
                                   "is_error": False}), ("연결 성공", "허용", "제공자 한도·인증 실패", "미확인")),
            ("withheld", event(decision="Block", policy_id="MCP-OUTPUT-001", result=None,
                               result_evidence={"disposition": "withheld"}),
             ("연결 성공", "정책 거부", "응답 보류", "미확인")),
            ("output scanner failed", event(decision="Block", policy_id="MCP-OUTPUT-001", result=None,
                                            control_failure=True, result_evidence={"disposition": "withheld"}),
             ("연결 성공", "통제 장애 차단", "응답 보류", "미확인")),
            ("approval", event(decision="Approval", policy_id="PAC-13", upstream_attempted=False,
                               upstream_executed=False, result=None), ("미시도", "승인 대기", "미실행", "실행 안 됨")),
            ("uncertain intent", event(decision="Block", policy_id="MCP-UPSTREAM-001", upstream_executed=False,
                                       result=None, intent_state="uncertain"), ("연결 성공", "허용", "미확인", "미확인")),
            ("observe", event(enforcement="monitor", would_decision="Block", would_policy_id="P-SCOPE-001"),
             ("연결 성공", "허용", "업무 성공", "미확인")),
            ("connected contract drift", event(decision="Block", policy_id="MCP-CATALOG-001", upstream_connected=True,
                                               upstream_attempted=False, upstream_executed=False, result=None),
             ("연결 성공", "통제 장애 차단", "미실행", "실행 안 됨")),
        ]
        for name, data, expected in cases:
            with self.subTest(name=name):
                before = deepcopy(data)
                self.assertEqual(tuple(outcomes.outcome_axes(data).values()), expected)
                self.assertEqual(data, before)

    def test_http_statuses_are_separate_from_generic_errors(self):
        for status in [401, 403, 429]:
            self.assertEqual(outcomes.outcome_axes(event(upstream_http_status=status))["task"], "제공자 한도·인증 실패")
        self.assertEqual(outcomes.outcome_axes(event(upstream_http_status=500, result={"is_error": True}))["task"], "도구 오류")
        for text in ["Docs explain Monthly quota exceeded", "quota", "rate", "unauthorized field"]:
            self.assertEqual(outcomes.outcome_axes(event(result={"content": [{"type": "text", "text": text}]}))["task"], "업무 성공")

    def test_legacy_is_not_rewritten_or_guessed_successful(self):
        legacy = event(result=None, result_preview={"disposition": "returned"})
        self.assertEqual(outcomes.recorded_outcome(legacy)["task"], "미확인")
        self.assertNotIn("outcome", legacy)
        self.assertEqual(outcomes.recorded_outcome({**legacy, "error": "Monthly quota exceeded."})["task"], "제공자 한도·인증 실패")
        self.assertEqual(outcomes.recorded_outcome({**legacy, "error": "bad SQL"})["task"], "도구 오류")
        snapshot = outcomes.outcome_axes(event())
        self.assertEqual(outcomes.recorded_outcome({**legacy, "outcome": snapshot}), snapshot)

    def test_independent_confirmation_only(self):
        for state, expected in [("pending", "미확인"), ("resolved", "미확인"), ("uncertain", "미확인"),
                                ("confirmed_executed", "실행됨"), ("confirmed_not_executed", "실행 안 됨")]:
            self.assertEqual(outcomes.outcome_axes(event(intent_state=state))["effect"], expected)
        self.assertEqual(outcomes.outcome_axes(event(upstream_attempted=False, upstream_executed=False,
                                                     intent_state="pending"))["effect"], "미확인")
        snapshot = outcomes.outcome_axes(event())
        projected = outcomes.recorded_outcome(event(outcome=snapshot, intent_state="confirmed_executed"))
        self.assertEqual(projected["effect"], "실행됨")
        self.assertEqual(snapshot["effect"], "미확인")

    def test_new_chain_covers_snapshot_and_old_versions_stay_stable(self):
        # Load the actual column definitions without importing optional gateway dependencies.
        tree = ast.parse((APP / "contract.py").read_text(encoding="utf-8"))
        assignments = [n for n in tree.body if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in {"AUDIT_COLUMN_SETS", "CHAIN_VERSION", "AUDIT_COLUMNS"}
            or isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == "AUDIT_COLUMN_SETS"
            for t in n.targets)]
        namespace = {"datetime": datetime, "UTC": timezone.utc, "canonical_hash": lambda v: repr(v)}
        exec(compile(ast.Module(body=assignments, type_ignores=[]), "contract columns", "exec"), namespace)
        contract = selected("contract.py", ["audit_fingerprint"], namespace)
        row = {"outcome": outcomes.outcome_axes(event())}
        changed = {"outcome": {**row["outcome"], "task": "도구 오류"}}
        self.assertNotEqual(contract.audit_fingerprint(row), contract.audit_fingerprint(changed))
        for version in range(1, 8):
            self.assertEqual(contract.audit_fingerprint(row, version), contract.audit_fingerprint(changed, version))


class OutcomePersistence(unittest.IsolatedAsyncioTestCase):
    async def test_insert_snapshot_hash_and_sql_arity(self):
        connection = SimpleNamespace(execute=AsyncMock())
        connection.execute.side_effect = [SimpleNamespace(fetchone=AsyncMock(return_value=None)),
                                          SimpleNamespace(fetchone=AsyncMock(return_value={"id": 48})), None]

        @asynccontextmanager
        async def transaction():
            yield connection

        fingerprint = Mock(return_value="fingerprint")
        namespace = {"outcome_axes": outcomes.outcome_axes, "secret_scan": SimpleNamespace(redact_error=AsyncMock(return_value=None)),
                     "db": SimpleNamespace(transaction=transaction), "datetime": datetime, "UTC": timezone.utc,
                     "hashlib": hashlib, "GENESIS": "0" * 64, "CHAIN_VERSION": 8, "GATEWAY_ENVIRONMENT": "test",
                     "_audit_fingerprint": fingerprint, "Jsonb": lambda v: v, "_audit_payload": lambda v: v,
                     "response_disposition": lambda v: "returned"}
        core = selected("core.py", ["_record_decision", "_storable"], namespace)
        data = event(request_id="request", trace_id="trace", user_token="employee", role="staff",
                     tool_name="read", data_class="public", action="r", reason="allowed")
        self.assertEqual(await core._record_decision(data), 48)
        sql, params = connection.execute.call_args_list[1].args
        self.assertEqual(sql.count("%s"), len(params))
        self.assertEqual(params[-1], outcomes.outcome_axes(data))
        self.assertEqual(fingerprint.call_args.args[0]["outcome"], params[-1])
        self.assertFalse(any("UPDATE decisions" in call.args[0] for call in connection.execute.call_args_list))

    async def test_audit_projection_discards_private_diagnostic(self):
        audit = selected("audit.py", ["with_outcome"], {"recorded_outcome": outcomes.recorded_outcome})
        row = event(result=None, outcome_error="Monthly quota exceeded. private diagnostic")
        result = audit.with_outcome(row)
        self.assertNotIn("outcome_error", result)
        self.assertNotIn("error", result)
        self.assertEqual(result["outcome_axes"]["task"], "제공자 한도·인증 실패")

    async def test_nested_http_status_survives_redaction(self):
        class StatusError(Exception):
            response = SimpleNamespace(status_code=429)

        namespace = {"httpx": SimpleNamespace(HTTPStatusError=StatusError),
                     "DestinationBlocked": type("DestinationBlocked", (Exception,), {}),
                     "local_verdict": lambda policy, decision, reason, **extra: {
                         "policy_id": policy, "decision": decision, **extra},
                     "_root_cause": lambda exc: "redacted"}
        core = selected("core.py", ["_upstream_failure"], namespace)
        outer = RuntimeError("private diagnostic")
        outer.__cause__ = StatusError()
        data = event(upstream_attempted=False, upstream_executed=False, result=None)
        data.update(core._upstream_failure(outer, data))
        self.assertEqual(data["policy_id"], "MCP-UPSTREAM-001")
        self.assertEqual(outcomes.outcome_axes(data)["task"], "제공자 한도·인증 실패")


class GatewayIntegration(unittest.IsolatedAsyncioTestCase):
    """Enabled explicitly in the gateway image, where production imports are available."""
    async def test_gateway_imports_and_read_projections(self):
        from unittest.mock import patch
        sys.path.insert(0, str(APP.parent))
        from app import activity, audit, core
        self.assertEqual(core.outcome_axes(event()), outcomes.outcome_axes(event()))
        snapshot = outcomes.outcome_axes(event())
        row = event(id=48, outcome=snapshot, intent_state="confirmed_executed")
        with patch.object(audit.db, "fetch_one", AsyncMock(return_value=row)), \
             patch.object(audit.review, "mark_invalid", AsyncMock(side_effect=lambda rows: rows)):
            detail = await audit.detail(48)
        self.assertEqual(detail["outcome"]["effect"], "미확인")
        self.assertEqual(detail["outcome_axes"]["effect"], "실행됨")
        self.assertEqual(activity.describe(row)["outcome_axes"], detail["outcome_axes"])


if __name__ == "__main__":
    if "--gateway" in sys.argv:
        sys.argv.remove("--gateway")
    else:
        del GatewayIntegration
    unittest.main(verbosity=2)
