"""실행 도구 장애·고아 시험·DB 격리가 거짓 통과로 바뀌지 않는지 검사한다."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import run_local_suite as runner


class RunnerChecks(unittest.TestCase):
    def test_platform_skips(self):
        for name in ("credential_binding_check", "intake_validation_test", "managed_enforcement_check"):
            path = runner.TESTS / (name + ".py")
            self.assertTrue(runner.skip_reason(path, "win32"))
            self.assertEqual(runner.skip_reason(path, "linux"), "")
        self.assertTrue(runner.skip_reason(runner.TESTS / "oss_audit_test.py", "linux"))

    def test_inventory_rejects_orphan_and_ignores_lint_glob(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tests = root / "full_stack_lab/tests"
            tests.mkdir(parents=True)
            workflows = root / ".github/workflows"
            workflows.mkdir(parents=True)
            (workflows / "verify.yml").write_text("python -m pyflakes tests/*.py\nnode --test tests/*.test.mjs\n")
            (tests.parent / "console.sh").write_text("python tests/direct.py\n")
            for name in ("local_test.py", "fresh_pg_check.py", "direct.py", "ui.test.mjs", "orphan.py", "x_support.py"):
                (tests / name).write_text("")
            with patch.object(runner, "TESTS", tests), patch.object(runner, "REPO", root):
                data = runner.inventory()
                self.assertEqual(data["counts"], {"ci": 2, "local-suite": 1, "pg-suite": 1, "external": 0, "orphan": 1})
                self.assertEqual([e["file"] for e in data["excluded"]], ["x_support.py"])
                output = root / "inventory.json"
                with patch.object(sys, "argv", ["runner", "--inventory", "--out", str(output)]):
                    self.assertEqual(runner.main(), 1)
                self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["counts"]["orphan"], 1)

    def test_child_failure_timeout_and_zero_tests_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample_test.py"
            path.write_text("class Check(unittest.TestCase): pass\n")
            for result in (SimpleNamespace(returncode=1, stdout=b"", stderr=b"crashed"),
                           SimpleNamespace(returncode=0, stdout=b"", stderr=b"Ran 0 tests\nOK")):
                with patch.object(runner.subprocess, "run", return_value=result):
                    self.assertEqual(runner.run_one(path)["status"], "실패")
            for error in (OSError("missing interpreter"), subprocess.TimeoutExpired("python", 1)):
                with patch.object(runner.subprocess, "run", side_effect=error):
                    self.assertEqual(runner.run_one(path)["status"], "실패")
            with patch.object(runner.subprocess, "run", return_value=SimpleNamespace(
                    returncode=0, stdout=b"", stderr=b"Ran 1 test\nOK")):
                self.assertEqual(runner.run_one(path)["status"], "통과")

    def pg_mocks(self):
        connection = MagicMock()
        driver = SimpleNamespace(connect=MagicMock(return_value=connection),
                                 sql=SimpleNamespace(SQL=lambda value: value, Identifier=lambda value: value))
        conninfo = SimpleNamespace(make_conninfo=lambda original, **kwargs: kwargs["dbname"])
        return driver, conninfo, connection.__enter__.return_value

    def test_failed_or_empty_suite_exits_nonzero_and_writes_json(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "results.json"
            for files in ([], [runner.TESTS / "sample_test.py"]):
                with patch.object(runner, "discover", return_value=files), \
                        patch.object(runner, "run_one", return_value={"file": "sample_test.py", "status": "실패"}), \
                        patch.object(sys, "argv", ["runner", "--out", str(output)]):
                    self.assertEqual(runner.main(), 1)
                self.assertEqual(len(json.loads(output.read_text(encoding="utf-8"))), len(files))

    def test_missing_pg_driver_fails_without_connecting(self):
        with patch.dict(sys.modules, {"psycopg": None}):
            result = runner.run_pg(runner.TESTS / "dispatch_intent_pg_check.py")
        self.assertEqual(result["status"], "실패")
        self.assertIn("ModuleNotFoundError", result["note"])

    def test_pg_isolation_cleanup_and_empty_database_exception(self):
        driver, conninfo, admin = self.pg_mocks()
        environments = []

        def child(path, env):
            environments.append(env)
            return {"file": path.name, "status": "실패", "rc": 1}

        with patch.dict(sys.modules, {"psycopg": driver, "psycopg.conninfo": conninfo}), \
                patch.dict(os.environ, {"DATABASE_URL": "admin-db"}), \
                patch.object(runner, "run_one", side_effect=child):
            for name in ("dispatch_intent_pg_check.py", "endpoint_evidence_pg_check.py"):
                self.assertEqual(runner.run_pg(runner.TESTS / name)["status"], "실패")
        statements = [call.args[0] for call in admin.execute.call_args_list]
        self.assertEqual(sum("CREATE DATABASE" in query for query in statements), 2)
        self.assertEqual(sum("DROP DATABASE" in query for query in statements), 2)
        self.assertEqual(sum("CREATE EXTENSION" in query for query in statements), 1)
        self.assertEqual(len({env["DATABASE_URL"] for env in environments}), 2)
        self.assertTrue(all(env["EVIDENCE_LAB"] == "isolated" for env in environments))
        self.assertTrue(all(not Path(env["REGISTRY_RUNTIME_DIR"]).exists() for env in environments))

    def test_pg_setup_and_cleanup_failure_cannot_pass(self):
        for failed_command in ("CREATE DATABASE", "DROP DATABASE", "CREATE EXTENSION"):
            driver, conninfo, admin = self.pg_mocks()

            def execute(query):
                if failed_command in query:
                    raise RuntimeError("driver error with secret")

            admin.execute.side_effect = execute
            with patch.dict(sys.modules, {"psycopg": driver, "psycopg.conninfo": conninfo}), \
                    patch.dict(os.environ, {"DATABASE_URL": "admin-db"}), \
                    patch.object(runner, "run_one", return_value={"status": "통과", "rc": 0}):
                result = runner.run_pg(runner.TESTS / "dispatch_intent_pg_check.py")
            self.assertEqual(result["status"], "실패")
            self.assertNotIn("secret", json.dumps(result))
            drops = sum("DROP DATABASE" in call.args[0] for call in admin.execute.call_args_list)
            self.assertEqual(drops, int(failed_command != "CREATE DATABASE"))


if __name__ == "__main__":
    unittest.main()
