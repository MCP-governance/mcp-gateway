"""D-124 offline unit checks; no MCP server or appliance is started."""
import ast
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import unittest
import urllib.request
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "full_stack_lab"


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def functions(path, names, namespace):
    # Exercise platform-independent production functions on Windows without loading pwd/grp.
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selected = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    assert {node.name for node in selected} == set(names)
    for node in selected:
        node.decorator_list = []
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return SimpleNamespace(**namespace)


class FieldTLS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="field-tls-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.folder = Path(cls.tmp.name)
        openssl = shutil.which("openssl") or "C:/Program Files/Git/mingw64/bin/openssl.exe"
        cls.ca = cls.folder / "root.crt"
        subprocess.run([openssl, "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
                        "-nodes", "-days", "1", "-subj", "/CN=Offline D124 test CA", "-addext", "basicConstraints=critical,CA:TRUE",
                        "-keyout", str(cls.folder / "root.key"), "-out", str(cls.ca)],
                       check=True, capture_output=True)
        cls.pem = cls.ca.read_text()
        cls.sha = hashlib.sha256(ssl.PEM_cert_to_DER_cert(cls.pem)).hexdigest()
        cls.kit = load(LAB / "field/pc/mcpgw_pc.py")
        with mock.patch.object(sys, "argv", ["agent.py"]):
            cls.agent = load(ROOT / "endpoint-agent/agent.py")

    def test_ca_pin_and_tls_verification(self):
        self.assertEqual(self.kit.verify_ca(self.ca, self.sha).replace(":", "").lower(), self.sha)
        context = self.agent.tls_context(self.pem, self.sha)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertGreaterEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        for pem, sha in ((self.pem, "0" * 64), (self.pem, ""), (self.pem * 2, self.sha), ("invalid", self.sha), ("", self.sha)):
            with self.subTest(pem=pem[:20], sha=sha), self.assertRaises(ValueError):
                self.agent.tls_context(pem, sha)
        with self.assertRaises(SystemExit):
            self.kit.verify_ca(self.ca, "0" * 64)

    def test_bad_pin_stops_setup_before_writes_or_login(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {"MCPGW_HOME": folder, "CODEX_HOME": folder}), \
                mock.patch.object(self.kit, "login") as login, mock.patch.object(self.kit, "preflight") as preflight:
            with self.assertRaises(SystemExit):
                self.kit.main(["setup", "--url", "https://100.83.175.111", "--servers", "git",
                               "--ca", str(self.ca), "--ca-sha256", "0" * 64])
            self.assertFalse(list(Path(folder).iterdir()))
            login.assert_not_called()
            preflight.assert_not_called()
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(self.kit, "__file__", str(Path(folder) / "mcpgw_pc.py")):
            shutil.copyfile(self.ca, Path(folder) / "root.crt")
            (Path(folder) / "root.sha256").write_text(self.sha)
            with mock.patch.dict(os.environ, {"MCPGW_HOME": str(Path(folder) / "home")}), self.assertRaises(SystemExit):
                self.kit.main(["setup", "--url", "https://100.83.175.111", "--servers", "git", "--ca-sha256", "0" * 64])
            self.assertFalse((Path(folder) / "home").exists())

    def test_observer_installer_bad_pin_stops_before_key_or_files(self):
        installer = load(ROOT / "endpoint-agent/install.py")
        argv = ["install.py", "--gateway-url", "https://100.83.175.111", "--endpoint-id", "tls-unit",
                "--scan-path", str(self.folder), "--ca", str(self.ca), "--ca-sha256", "0" * 64]
        with mock.patch.object(sys, "argv", argv), mock.patch.dict(sys.modules, {"agent": self.agent}), \
                mock.patch.object(installer, "install_dir") as folder, mock.patch.object(installer.getpass, "getpass") as key, \
                mock.patch.object(sys, "stderr", io.StringIO()), self.assertRaises(SystemExit):
            installer.main()
        folder.assert_not_called()
        key.assert_not_called()

    def test_file_ca_requires_matching_sidecar(self):
        sidecar = self.ca.with_suffix(".sha256")
        sidecar.write_text(self.sha)
        with mock.patch.dict(self.agent.CONFIG, {"ENDPOINT_CA_FILE": str(self.ca)}):
            self.assertTrue(self.agent.tls_context().check_hostname)
            sidecar.write_text("0" * 64)
            with self.assertRaises(ValueError):
                self.agent.tls_context()

    def test_remote_plaintext_rejected_before_transport(self):
        with mock.patch.object(urllib.request, "build_opener") as opener:
            with self.assertRaises(SystemExit):
                self.kit.request({"url": "http://100.83.175.111"}, "http://100.83.175.111/oauth/token", data=b"synthetic")
            with mock.patch.object(self.agent, "GATEWAY_URL", "http://100.83.175.111"), self.assertRaises(ValueError):
                self.agent.call("POST", "/api/endpoint/heartbeat", {})
            opener.assert_not_called()

    def test_managed_bad_pin_stops_before_enrollment_transport(self):
        module = functions(ROOT / "endpoint-agent/managed-linux.py", ["request", "verify_transport"], {
            "load_module": lambda *args: self.agent, "Path": Path, "__file__": str(ROOT / "endpoint-agent/managed-linux.py"),
            "urlsplit": __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit,
            "urllib": __import__("urllib"), "json": json,
        })
        bundle = {"gateway_url": "https://100.83.175.111", "ca_certificate": self.pem, "ca_sha256": "0" * 64}
        with mock.patch.object(urllib.request, "build_opener") as opener, self.assertRaises(ValueError):
            module.request(bundle, "/oauth/device-enroll", {}, credential=False)
        opener.assert_not_called()

    def test_harness_ca_is_process_scoped_and_checked(self):
        settings = {"ca": str(self.ca), "ca_sha256": self.sha}
        for name, key in (("codex", "CODEX_CA_CERTIFICATE"), ("claude", "NODE_EXTRA_CA_CERTS")):
            with self.subTest(name=name), mock.patch.object(self.kit, "load_settings", return_value=settings), \
                    mock.patch.object(self.kit, "claude_path", return_value="claude"), \
                    mock.patch.object(self.kit.shutil, "which", return_value="codex"), \
                    mock.patch.object(self.kit.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
                before = dict(os.environ)
                with self.assertRaises(SystemExit) as outcome:
                    self.kit.cmd_harness(SimpleNamespace(name=name, arguments=["--version"]))
                self.assertEqual(outcome.exception.code, 0)
                self.assertEqual(run.call_args.kwargs["env"][key], str(self.ca))
                self.assertEqual(dict(os.environ), before)

    def test_console_archive_contains_matching_root_and_pin(self):
        class HTTPException(Exception):
            pass
        namespace = {"os": os, "Path": Path, "re": re, "ssl": ssl, "hashlib": hashlib, "HTTPException": HTTPException}
        module = functions(LAB / "gateway/app/agent_service.py", ["field_ca"], namespace)
        with mock.patch.dict(os.environ, {"FIELD_CA_FILE": str(self.ca), "MCP_FIELD_MODE": "1"}):
            ca = module.field_ca()
        self.assertEqual(ca, {"ca_certificate": self.pem, "ca_sha256": self.sha})
        # Execute the production archive block with a synthetic enrollment grant; no MCP is involved.
        tree = ast.parse((LAB / "gateway/app/agent_service.py").read_text(encoding="utf-8"))
        download = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "download_managed_kit")
        archive_block = next(node for node in download.body if isinstance(node, ast.With))
        output = io.BytesIO()
        with tempfile.TemporaryDirectory() as folder:
            static = Path(folder)
            (static / "kit").mkdir()
            (static / "kit/mcpgw_pc.py").write_text("# unit fixture")
            exec(compile(ast.Module(body=[archive_block], type_ignores=[]), "archive", "exec"), {
                "zipfile": zipfile, "output": output, "bundle": {**ca, "enrollment_token": "synthetic"}, "json": json,
                "ca": ca, "STATIC_DIR": static, "names": [],
            })
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.read("root.crt").decode(), self.pem)
            self.assertEqual(archive.read("root.sha256").decode().strip(), self.sha)
            self.assertEqual(json.loads(archive.read("enrollment.json"))["ca_sha256"], self.sha)

    def test_caddy_and_overlay_security_invariants(self):
        caddy = (LAB / "field/Caddyfile").read_text(encoding="utf-8")
        for required in ("tls internal", "auto_https disable_redirects", "skip_install_trust", "default_sni {$APPLIANCE_BIND}", "protocols tls1.2 tls1.3"):
            self.assertIn(required, caddy)
        self.assertNotIn("http://:8080", caddy)
        self.assertNotIn("http_redirect", caddy)
        overlay = (LAB / "compose.field.yaml").read_text(encoding="utf-8")
        self.assertNotIn("http://${APPLIANCE_BIND}:443", overlay)
        self.assertIn("field_caddy_data:/data", overlay)
        self.assertIn("FIELD_CA_FILE: /field-ca/root.crt", overlay)


if __name__ == "__main__":
    unittest.main(verbosity=2)
