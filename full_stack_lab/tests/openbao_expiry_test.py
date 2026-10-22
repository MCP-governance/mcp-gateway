"""Offline expiry regression: fixed dates plus real OpenSSL on disposable files."""
import contextlib
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "openbao_check_expiry",
    ROOT / "research/llm-wiki/integrations/lab/openbao/check_expiry.py",
)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
NOW = datetime(2026, 10, 22, tzinfo=timezone.utc).timestamp()
DATES = "notBefore=Oct 20 00:00:00 2026 GMT\nnotAfter=Oct 25 00:00:00 2026 GMT\n"


class ExpiryTest(unittest.TestCase):
    def result_for(self, dates=DATES, now=NOW, threshold=172800):
        with patch.object(CHECK.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, dates)):
            return CHECK.check_expiry(Path("public-tls"), threshold, now=now)

    def test_healthy_checks_only_server_and_ca(self):
        with patch.object(CHECK.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, DATES)) as run:
            result = CHECK.check_expiry("public-tls", now=NOW)
        self.assertTrue(result["ok"])
        self.assertEqual([item.args[0] for item in run.call_args_list], [
            ["openssl", "x509", "-in", str(Path("public-tls/server.pem")), "-noout", "-dates"],
            ["openssl", "x509", "-in", str(Path("public-tls/ca.pem")), "-noout", "-dates"],
        ])

    def test_threshold_boundary_and_one_second_outside(self):
        self.assertEqual(self.result_for(threshold=259200)["certificates"]["server"]["status"], "expires_soon")
        self.assertTrue(self.result_for(threshold=259199)["ok"])

    def test_expired_at_exact_not_after(self):
        result = self.result_for(now=NOW + 259200)
        self.assertFalse(result["ok"])
        self.assertEqual(result["certificates"]["server"]["status"], "expired")

    def test_observed_expiry_is_failure(self):
        result = self.result_for("notBefore=Oct 13 12:23:18 2026 GMT\nnotAfter=Oct 20 12:23:18 2026 GMT\n")
        self.assertEqual(result["certificates"]["server"]["status"], "expired")
        self.assertFalse(result["ok"])

    def test_not_yet_valid(self):
        result = self.result_for(now=NOW - 259200)
        self.assertEqual(result["certificates"]["server"]["status"], "not_yet_valid")
        self.assertFalse(result["ok"])

    def test_ca_failure_cannot_be_hidden_by_healthy_server(self):
        bad_ca = DATES.replace("Oct 25", "Oct 21")
        with patch.object(CHECK.subprocess, "run", side_effect=[
            subprocess.CompletedProcess([], 0, DATES), subprocess.CompletedProcess([], 0, bad_ca),
        ]):
            result = CHECK.check_expiry("public-tls", now=NOW)
        self.assertEqual(result["certificates"]["server"]["status"], "ok")
        self.assertEqual(result["certificates"]["ca"]["status"], "expired")
        self.assertFalse(result["ok"])

    def test_invalid_dates_fail(self):
        for dates in ("", "notBefore=bad\nnotAfter=bad\n", DATES.replace("Oct 25", "Oct 19")):
            with self.subTest(dates=dates):
                self.assertEqual(self.result_for(dates)["certificates"]["server"]["status"], "error")

    def test_helper_failures_return_nonzero_and_suppress_error_text(self):
        for error in (FileNotFoundError("sensitive"), PermissionError("sensitive"),
                      subprocess.TimeoutExpired("sensitive", 10),
                      subprocess.CalledProcessError(1, "sensitive", stderr="sensitive")):
            with self.subTest(error=type(error).__name__):
                output = io.StringIO()
                with patch.object(CHECK.subprocess, "run", side_effect=error), contextlib.redirect_stdout(output):
                    code = CHECK.main(["--tls-dir", "public-tls"])
                self.assertEqual(code, 1)
                self.assertNotIn("sensitive", output.getvalue())
                self.assertFalse(json.loads(output.getvalue())["ok"])

    def test_negative_threshold_is_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            CHECK.main(["--tls-dir", "public-tls", "--min-valid-seconds", "-1"])
        self.assertEqual(error.exception.code, 2)

    def test_real_openssl_files_and_cli(self):
        openssl = os.environ.get("OPENBAO_TEST_OPENSSL") or shutil.which("openssl")
        self.assertTrue(openssl, "OpenSSL required; missing checker is a failure")
        with tempfile.TemporaryDirectory(prefix=".openbao-expiry-test-", dir=ROOT) as directory:
            root = Path(directory)
            subprocess.run([
                openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3",
                "-subj", "/CN=expiry-offline-fixture", "-keyout", str(root / "fixture.key"),
                "-out", str(root / "server.pem"),
            ], check=True, capture_output=True, timeout=30)
            # The same synthetic public cert isolates expiry; this is no trust-chain test.
            shutil.copyfile(root / "server.pem", root / "ca.pem")
            command = [sys.executable, "-B", str(SPEC.origin),
                       "--tls-dir", directory, "--openssl", openssl]
            run = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
            self.assertTrue(json.loads(run.stdout)["ok"])
            near = subprocess.run(command + ["--min-valid-seconds", "345600"], capture_output=True, text=True, timeout=30)
            self.assertEqual(near.returncode, 1)
            self.assertEqual(json.loads(near.stdout)["certificates"]["server"]["status"], "expires_soon")
            (root / "ca.pem").write_text("invalid public certificate", encoding="ascii")
            invalid = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(invalid.returncode, 1)
            self.assertEqual(json.loads(invalid.stdout)["certificates"]["ca"]["status"], "error")
            (root / "ca.pem").unlink()
            missing = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(missing.returncode, 1)
            self.assertEqual(json.loads(missing.stdout)["certificates"]["ca"]["status"], "error")


if __name__ == "__main__":
    unittest.main()
