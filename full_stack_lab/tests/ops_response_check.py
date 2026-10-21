"""Pure unit tests; DB/HTTP functions are doubles, no MCP server or container is started."""
import asyncio
import ast
import base64
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import asynccontextmanager, nullcontext
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

LAB = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(LAB / "gateway"), str(LAB / "runtime"), str(LAB / "supply_chain")]
from app import disposal
import image_scan
import trivy_scan


def ops_module():
    # Import-time dependencies are replaced only for this isolated unit module.
    db, release, review = (types.ModuleType("app." + name) for name in ("db", "release", "review"))
    contract = types.ModuleType("app.contract")
    contract.canonical_hash = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    contract.POLICY_RESULT = types.SimpleNamespace(is_valid=lambda v: isinstance(v, dict) and "decision" in v and "policy_id" in v)
    http = types.ModuleType("httpx")
    http.AsyncClient = Mock()
    psycopg_json = types.ModuleType("psycopg.types.json")
    psycopg_json.Jsonb = lambda value: value
    dependencies = {"app.db": db, "app.release": release, "app.review": review, "app.contract": contract,
                    "httpx": http, "psycopg": types.ModuleType("psycopg"),
                    "psycopg.types": types.ModuleType("psycopg.types"), "psycopg.types.json": psycopg_json}
    with patch.dict(sys.modules, dependencies):
        spec = importlib.util.spec_from_file_location("app.ops_response_unit", LAB / "gateway/app/ops_response.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, dependencies


ops, DEPENDENCIES = ops_module()
NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)
FINDING = {"id": "CVE-example", "target": "linux", "package": "lib-example", "installed_version": "1", "severity": "CRITICAL"}
IMAGE = "sha256:" + "a" * 64


class ImageScan(unittest.TestCase):
    def test_deadline_boundary_survives_a_new_scan(self):
        first = image_scan.assess([FINDING], {}, NOW)
        self.assertFalse(image_scan.assess([FINDING], first["critical"], NOW + timedelta(days=7, microseconds=-1))["overdue"])
        overdue = image_scan.assess([FINDING], first["critical"], NOW + timedelta(days=7))
        self.assertEqual(len(overdue["overdue"]), 1)
        self.assertEqual(first["critical"], overdue["critical"])
        self.assertFalse(image_scan.assess([], first["critical"], NOW + timedelta(days=8))["critical"])

    def test_report_cannot_truncate_away_critical_findings(self):
        with tempfile.TemporaryDirectory(dir=LAB) as folder:
            report = Path(folder) / "report.json"
            items = [{"Severity": "LOW", "VulnerabilityID": f"low-{i}"} for i in range(205)]
            items.append({"Severity": "CRITICAL", "VulnerabilityID": "last-critical"})
            report.write_text(json.dumps({"SchemaVersion": 2, "Results": [{"Target": "x", "Vulnerabilities": items}]}))
            counts, findings = trivy_scan.trivy_counts(report, Path(folder), limit=None)
            self.assertEqual(counts["CRITICAL"], 1)
            self.assertEqual(findings[-1]["id"], "last-critical")
            report.write_text("{}")
            with self.assertRaises(ValueError):
                trivy_scan.trivy_counts(report, Path(folder))

    def run_scan(self, *, age=0, code=0, image=IMAGE, malformed=False):
        def run(command, **_):
            if command[1] == "image":
                report = Path(command[command.index("--output") + 1])
                report.write_text("{" if malformed else json.dumps({"SchemaVersion": 2,
                    "Metadata": {"ImageID": image}, "Results": []}))
                self.assertEqual(command[-1], IMAGE)
                self.assertIn("--image-src", command)
                return types.SimpleNamespace(returncode=code)
            return types.SimpleNamespace(returncode=0, stdout=json.dumps({"VulnerabilityDB": {
                "UpdatedAt": (NOW - timedelta(days=age)).isoformat()}}))
        original = tempfile.TemporaryDirectory
        with patch.object(image_scan.subprocess, "run", side_effect=run), patch.object(
                image_scan.tempfile, "TemporaryDirectory", side_effect=lambda **kw: original(dir=LAB, **kw)):
            return image_scan.scan(IMAGE, {}, NOW)

    def test_fresh_db_seven_days_is_accepted(self):
        self.assertEqual(self.run_scan(age=7)["status"], "checked")

    def test_stale_future_missing_bad_scanner_and_wrong_image_are_not_passes(self):
        for kwargs in ({"age": 7.01}, {"age": -1}, {"code": 1}, {"image": "sha256:" + "b" * 64}, {"malformed": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises((ValueError, RuntimeError)):
                self.run_scan(**kwargs)
        for document in ({}, {"VulnerabilityDB": {"UpdatedAt": "bad"}}, {"VulnerabilityDB": {"UpdatedAt": "2026-01-01T00:00:00"}}):
            self.assertIsNone(trivy_scan.database_time(document))

    def test_scanner_failure_records_hold_and_preserves_deadline(self):
        previous = image_scan.assess([FINDING], {}, NOW)["critical"]
        connection = Mock()
        connection.execute.return_value.fetchone.side_effect = [
            {"acquired": True}, {"runtime_id": "r", "checked_at": NOW, "result": {"critical": previous, "status": "failed"}}]
        event = Mock()
        with patch.dict(sys.modules, DEPENDENCIES), patch.object(image_scan, "scan", side_effect=OSError("unavailable")):
            reason = image_scan.rescan(connection, {"id": "r", "image_id": IMAGE, "intake_id": "i"}, event)
        self.assertEqual(reason, "운영 이미지 검사 실패")
        event.assert_called_once()
        self.assertEqual(event.call_args.kwargs["scope"]["scan"]["critical"], previous)
        queries = "\n".join(call.args[0] for call in connection.execute.call_args_list)
        self.assertIn("INSERT INTO runtime_image_scans", queries)
        self.assertIn("INSERT INTO ops_suspensions", queries)
        self.assertIn("status='DISABLED'", queries)


class AlertSelfTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # These servers are remote: the local-run check must not load the registry or wait on a device.
        local = patch.object(ops.local_jobs, "is_local", return_value=False)
        local.start()
        self.addCleanup(local.stop)
        corpus = json.loads((LAB / "opa/replay_cases_pac15.json").read_text(encoding="utf-8"))["pac15_replay"]
        self.base = {**corpus["base"], **corpus["cases"][0]["patch"]}
        self.info = {"matches": True, "loaded_sha256": "a", "loaded_data_sha256": "b", "capabilities_sha256": "c"}
        ops.release.policy_info = AsyncMock(return_value=self.info)
        async def fetch_one(query, *_):
            return None if "SELECT passed" in query else {"id": 1, "synthetic": True}
        ops.db.fetch_one = AsyncMock(side_effect=fetch_one)
        ops.db.execute = AsyncMock()

    def test_cases_keep_trusted_pac_and_do_not_mutate_frozen_base(self):
        original = copy.deepcopy(self.base)
        cases = ops.self_test_cases(self.base)
        self.assertEqual(original, self.base)
        self.assertEqual(len(cases), 6)
        self.assertTrue(all(c["input"]["synthetic"] and c["input"]["pac"]["facts"]["trusted"] for c in cases))
        self.assertEqual({c["expected"]["policy_id"] for c in cases},
                         {"P-AUTHZ-ALLOW-001", "MCP-REGISTRY-001", "MCP-SHADOW-001", "MCP-SHADOW-002", "P-VOLUME-001", "P-ANOMALY-001"})

    async def self_test(self, wrong=False, down=False):
        cases = ops.self_test_cases(self.base)
        responses = [Mock(json=Mock(return_value={"result": c["expected"]}), raise_for_status=Mock()) for c in cases]
        if wrong:
            responses[2].json.return_value = {"result": {"decision": "Allow", "policy_id": "P-AUTHZ-ALLOW-001"}}
        client = AsyncMock()
        client.post.side_effect = OSError("OPA unavailable") if down else responses
        manager = AsyncMock()
        manager.__aenter__.return_value = client
        with patch.object(ops.httpx, "AsyncClient", return_value=manager), patch.dict(os.environ, {"POLICY_PATH": str(LAB / "opa/policy.rego")}):
            await ops.self_test("http://unused.invalid")
        return ops.db.execute.call_args.args[1]

    async def test_deployment_check_records_success_separately(self):
        _, passed, results = await self.self_test()
        self.assertTrue(passed)
        self.assertEqual(len(results), 6)
        self.assertTrue(all(r["synthetic"] for r in results))
        self.assertIn("INSERT INTO alert_self_tests", ops.db.execute.call_args.args[0])
        self.assertNotIn("decisions", ops.db.execute.call_args.args[0])

    async def test_wrong_policy_or_engine_failure_is_a_failed_test(self):
        self.assertFalse((await self.self_test(wrong=True))[1])
        self.assertFalse((await self.self_test(down=True))[1])

    async def test_policy_changed_mid_test_is_failed(self):
        ops.release.policy_info.side_effect = [self.info, {**self.info, "loaded_sha256": "different"}]
        self.assertFalse((await self.self_test())[1])

    def test_auto_stop_scope_is_configurable(self):
        with patch.object(ops, "SERVERS", {"chosen"}), patch.object(ops, "SOURCES", {"drift"}):
            self.assertTrue(ops.selected("chosen", "drift"))
            self.assertFalse(ops.selected("other", "drift"))
            self.assertFalse(ops.selected("chosen", "anomaly"))

    async def test_suspend_stops_runtime_and_never_reactivates(self):
        connection = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchone.return_value = {"id": 1}
        connection.execute.return_value = cursor
        @asynccontextmanager
        async def transaction():
            yield connection
        ops.db.transaction = transaction
        await ops.suspend("chosen", "drift", "자동 중지", {"findings": []})
        queries = "\n".join(c.args[0] for c in connection.execute.call_args_list)
        self.assertIn("status='STOPPING'", queries)
        self.assertIn("status='DISABLED'", queries)
        self.assertIn("INSERT INTO approval_events", queries)
        self.assertNotIn("status='READY'", queries)

    async def test_missing_alert_storage_is_not_a_success(self):
        with patch.object(ops, "emit_alert", new=AsyncMock(return_value=None)):
            self.assertFalse((await self.self_test())[1])

    async def test_repeated_alerts_stop_only_selected_servers(self):
        ops.db.fetch_all = AsyncMock(return_value=[
            {"server_id": "chosen", "source": "anomaly", "occurrences": 3, "last_decision_id": 20},
            {"server_id": "other", "source": "anomaly", "occurrences": 3, "last_decision_id": 21}])
        with patch.object(ops, "SERVERS", {"chosen"}), patch.object(ops, "suspend", new=AsyncMock()) as suspend:
            await ops.contain_repeated()
        suspend.assert_awaited_once()
        self.assertEqual(suspend.call_args.args[0], "chosen")
        query, params = ops.db.fetch_all.call_args.args
        self.assertEqual(params, (ops.WINDOW, ops.REPEAT))
        self.assertIn("max(resumed_at)", query)
        self.assertNotIn("client->>'synthetic'", query)

    async def test_human_resume_and_approval_record_share_one_transaction(self):
        connection, cursor = AsyncMock(), AsyncMock()
        cursor.fetchone.side_effect = [{"lifecycle": "OPERATING"}, {"id": 1}]
        connection.execute.return_value = cursor
        inside = False
        @asynccontextmanager
        async def transaction():
            nonlocal inside
            inside = True
            yield connection
            inside = False
        async def record(*_, **kwargs):
            self.assertTrue(inside)
            self.assertIs(kwargs["connection"], connection)
        ops.db.transaction = transaction
        ops.review.record_event = AsyncMock(side_effect=record)
        with patch.object(disposal, "locked", return_value=nullcontext()), patch.object(disposal, "read", return_value=[]):
            result = await ops.resume("chosen", "admin", "원인 검토 완료")
        self.assertEqual(result["status"], "PENDING")
        ops.review.record_event.assert_awaited_once()


class TokenReuse(unittest.IsolatedAsyncioTestCase):
    async def test_persistent_suspension_overrides_a_refreshed_server_status(self):
        tree = ast.parse((LAB / "gateway/app/core.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "refresh_catalog")
        fake_db = types.SimpleNamespace(fetch_one=AsyncMock(return_value={
            "status": "PENDING", "automatic_stop_reason": "자동 중지", "status_reason": "계약 확인 대기"}), execute=AsyncMock())
        namespace = {"db": fake_db}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "core.refresh_catalog", "exec"), namespace)
        result = await namespace["refresh_catalog"]("chosen")
        self.assertEqual(result["status"], "DISABLED")
        self.assertEqual(result["reason"], "자동 중지")
        fake_db.execute.assert_awaited_once()

    async def test_signed_tombstone_still_revokes_family_under_its_lock(self):
        # Execute the production function body; HTTP form defaults and type annotations need no server here.
        tree = ast.parse((LAB / "gateway/app/idp.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "token")
        node.decorator_list, node.returns = [], None
        for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
            argument.annotation = None
        node.args.defaults = [ast.Constant(None) for _ in node.args.defaults]
        node.args.kw_defaults = [ast.Constant(None) for _ in node.args.kw_defaults]
        stored = {"client_id": "cli", "family_id": "family"}
        connection, cursor = AsyncMock(), AsyncMock()
        cursor.fetchone.return_value = stored
        connection.execute.return_value = cursor
        inside = False
        @asynccontextmanager
        async def transaction():
            nonlocal inside
            inside = True
            yield connection
            inside = False
        async def revoke(family, conn):
            self.assertTrue(inside)
            self.assertEqual(family, "family")
            self.assertIs(conn, connection)
        family_revoke = AsyncMock(side_effect=revoke)
        namespace = {"__package__": "app", "db": types.SimpleNamespace(
            fetch_one=AsyncMock(return_value=stored), transaction=transaction),
            "disposal": types.SimpleNamespace(blocked=Mock(return_value=True)),
            "_sha": lambda value: hashlib.sha256(value.encode()).hexdigest(),
            "FAMILY_LOCK_SQL": "family lock", "_revoke_family": family_revoke,
            "_error": lambda code, *_: code}
        oidc = types.ModuleType("app.oidc")
        oidc.local_login_allowed = lambda: None
        with patch.dict(sys.modules, {"app.oidc": oidc}):
            exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), "idp.token", "exec"), namespace)
            result = await namespace["token"](None, grant_type="refresh_token", client_id="cli", refresh_token="rt_test")
        self.assertEqual(result, "invalid_grant")
        family_revoke.assert_awaited_once()


OPENSSL = shutil.which("openssl") or ("C:/Program Files/Git/usr/bin/openssl.exe" if Path("C:/Program Files/Git/usr/bin/openssl.exe").is_file() else None)
CRYPTOGRAPHY = importlib.util.find_spec("cryptography") is not None


class OpenSSLKey:
    """Test adapter: real Ed25519 signatures when this host lacks the production cryptography wheel."""
    def __init__(self, folder):
        self.folder = folder
        self.private = folder / "private.pem"
        self.public = folder / "public.pem"
        subprocess.run([OPENSSL, "genpkey", "-algorithm", "ed25519", "-out", str(self.private)], check=True, capture_output=True)
        subprocess.run([OPENSSL, "pkey", "-in", str(self.private), "-pubout", "-out", str(self.public)], check=True, capture_output=True)

    def sign(self, value):
        message, signature = self.folder / "message", self.folder / "signature"
        message.write_bytes(value)
        subprocess.run([OPENSSL, "pkeyutl", "-sign", "-rawin", "-inkey", str(self.private), "-in", str(message), "-out", str(signature)], check=True, capture_output=True)
        return signature.read_bytes()

    def verify(self, signature, value):
        message, signed = self.folder / "verify-message", self.folder / "verify-signature"
        message.write_bytes(value)
        signed.write_bytes(signature)
        subprocess.run([OPENSSL, "pkeyutl", "-verify", "-rawin", "-pubin", "-inkey", str(self.public), "-in", str(message), "-sigfile", str(signed)], check=True, capture_output=True)


@unittest.skipUnless(OPENSSL or CRYPTOGRAPHY, "cryptography or OpenSSL is required for real Ed25519 tests")
class Disposal(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=LAB)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        if CRYPTOGRAPHY:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives import serialization
            private = os.urandom(32)
            public = Ed25519PrivateKey.from_private_bytes(private).public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            self.key_patch = patch.dict(os.environ, {"DISPOSAL_PRIVATE_KEY": base64.urlsafe_b64encode(private).decode(),
                                                     "DISPOSAL_PUBLIC_KEY": base64.urlsafe_b64encode(public).decode()})
        else:
            key = OpenSSLKey(self.folder)
            self.key_patch = patch.object(disposal, "key", return_value=key)
        self.directory_patch = patch.object(disposal, "DIRECTORY", self.folder)
        self.key_patch.start()
        self.directory_patch.start()
        self.addCleanup(self.key_patch.stop)
        self.addCleanup(self.directory_patch.stop)
        disposal.initialize()

    def test_signed_record_is_idempotent_and_blocks_after_database_rollback(self):
        disposal.remember("server", "gone", "gone")
        before = (self.folder / "journal.jsonl").read_bytes()
        disposal.remember("server", "gone", "gone")
        self.assertEqual(before, (self.folder / "journal.jsonl").read_bytes())
        self.assertTrue(disposal.blocked(server_id="gone"))
        self.assertFalse(disposal.blocked(server_id="other"))
        disposal.remember_token("11111111-2222-3333-4444-555555555555", NOW)
        self.assertTrue(disposal.blocked(jti="11111111-2222-3333-4444-555555555555"))

    def test_missing_truncated_corrupt_head_and_corrupt_signature_fail_closed(self):
        disposal.remember("server", "gone", "gone")
        journal, head = self.folder / "journal.jsonl", self.folder / "head.json"
        originals = {journal: journal.read_bytes(), head: head.read_bytes()}
        for path, replacement in ((journal, b""), (journal, originals[journal].splitlines()[0] + b"\n"),
                                  (journal, originals[journal].replace(b'gone', b'back')),
                                  (head, b'{}')):
            with self.subTest(path=path, replacement=replacement[:20]):
                path.write_bytes(replacement)
                self.assertTrue(disposal.blocked(server_id="other"))
                path.write_bytes(originals[path])
        journal.unlink()
        self.assertTrue(disposal.blocked(jti="any"))
        with self.assertRaises(disposal.IntegrityError):
            disposal.remember("server", "new", "new")

    def test_signed_head_does_not_let_wrong_signature_through(self):
        disposal.remember("server", "gone", "gone")
        path = self.folder / "journal.jsonl"
        lines = path.read_bytes().splitlines()
        envelope = json.loads(lines[-1])
        envelope["signature"] = "A" * 88
        lines[-1] = disposal.encoded(envelope)
        raw = b"\n".join(lines) + b"\n"
        path.write_bytes(raw)
        (self.folder / "head.json").write_bytes(disposal.encoded(disposal.signed({"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})))
        with self.assertRaises(disposal.IntegrityError):
            disposal.read()

    def test_existing_list_cannot_be_initialized_again(self):
        with self.assertRaises(disposal.IntegrityError):
            disposal.initialize()

    def test_competing_writers_keep_a_complete_signed_chain(self):
        with ThreadPoolExecutor(max_workers=3) as executor:
            list(executor.map(lambda i: disposal.remember("server", "server-" + str(i), "server-" + str(i)), range(3)))
        self.assertEqual({r["subject"] for r in disposal.read()[1:]}, {"server-0", "server-1", "server-2"})

    def test_interrupted_head_replace_leaves_access_blocked(self):
        with patch.object(disposal.os, "replace", side_effect=OSError("power loss")), self.assertRaises(OSError):
            disposal.remember("server", "gone", "gone")
        self.assertTrue(disposal.blocked(server_id="other"))

    def test_reconcile_reapplies_records_and_appends_an_alert(self):
        disposal.remember("server", "gone", "gone")
        disposal.remember_token("11111111-2222-3333-4444-555555555555", datetime.now(timezone.utc) + timedelta(days=1))
        connection = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchone.return_value = {"subject": "restored"}
        cursor.rowcount = 1
        connection.execute.return_value = cursor
        @asynccontextmanager
        async def transaction():
            yield connection
        fake_db = DEPENDENCIES["app.db"]
        fake_db.transaction = transaction
        with patch.dict(sys.modules, DEPENDENCIES):
            restored = asyncio.run(disposal.reconcile())
        self.assertEqual({r["kind"] for r in restored}, {"server", "token"})
        queries = "\n".join(c.args[0] for c in connection.execute.call_args_list)
        self.assertIn("INSERT INTO agent_revoked_tokens", queries)
        self.assertIn("lifecycle='RETIRED'", queries)
        self.assertIn("status='STOPPING'", queries)
        self.assertIn("INSERT INTO approval_events", queries)
        self.assertNotIn("UPDATE decisions", queries)


if __name__ == "__main__":
    unittest.main()
