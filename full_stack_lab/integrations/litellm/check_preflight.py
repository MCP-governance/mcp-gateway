"""Configuration/credential boundary checks; no model call or MCP server is simulated."""
import copy
import json
import datetime
from pathlib import Path
import ssl
import tempfile
import unittest

from preflight import MAX_CA_BYTES, body_for, has_text, read_secret, tls_context, validate_manifest

BASE = json.loads(Path(__file__).with_name("parallel-harness.example.json").read_text())


class PreflightChecks(unittest.TestCase):
    def test_configuration_is_not_runtime_readiness(self):
        self.assertEqual(validate_manifest(copy.deepcopy(BASE)), BASE)
        bad = [("mode", "aggregated_shared_token"), ("litellm_version", "latest"),
               ("llm_base_url", "http://llm.example.invalid"), ("llm_base_url", "https://llm.example.invalid/v1"),
               ("mcp_url", "https://user:password@mcp.example.invalid/mcp"),
               ("routes", ["chat", "chat"]), ("routes", ["unknown"]),
               ("timeout_seconds", True), ("timeout_seconds", 61),
               ("ca_file", "relative"), ("ca_file", None),
               ("mcp_token_file", BASE["llm_key_file"]), ("mcp_token_file", "relative")]
        for key, value in bad:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_manifest({**BASE, key: value})
        self.assertEqual(validate_manifest({**BASE, "ca_file": "/run/interop-ca/root.crt"})["ca_file"],
                         "/run/interop-ca/root.crt")

    def test_minimal_protocol_requests_and_real_response_shapes(self):
        self.assertIn("input", body_for("responses", "approved"))
        self.assertIn("messages", body_for("messages", "approved"))
        valid = {"chat": {"choices": [{"message": {"content": "READY"}}]},
                 "messages": {"content": [{"type": "text", "text": "READY"}]},
                 "responses": {"output": [{"type": "message", "content": [{"type": "output_text", "text": "READY"}]}]}}
        for route, body in valid.items():
            self.assertTrue(has_text(route, body))
            self.assertFalse(has_text(route, {"error": {"code": "quota"}}))
            self.assertFalse(has_text(route, {}))

    def test_private_posix_files_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test-only-credential"
            path.write_text("synthetic-test-credential")
            path.chmod(0o600)
            self.assertEqual(read_secret(str(path)), "synthetic-test-credential")
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                read_secret(str(path))
            alias = Path(directory) / "alias"
            alias.symlink_to(path)
            with self.assertRaises(OSError):
                read_secret(str(alias))

    def test_explicit_real_ca_preserves_chain_and_hostname_verification(self):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "interop-unit-private-ca")])
        now = datetime.datetime.now(datetime.timezone.utc)
        certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                       .public_key(key.public_key()).serial_number(x509.random_serial_number())
                       .not_valid_before(now - datetime.timedelta(minutes=1))
                       .not_valid_after(now + datetime.timedelta(hours=1))
                       .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                       .sign(key, hashes.SHA256()))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ca.crt"
            path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
            default = tls_context()
            context = tls_context(str(path))
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
            self.assertGreater(context.cert_store_stats()["x509_ca"], default.cert_store_stats()["x509_ca"])
            alias = Path(directory) / "alias"
            alias.symlink_to(path)
            with self.assertRaises(OSError):
                tls_context(str(alias))

    def test_bad_ca_input_is_rejected_without_disabling_tls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ca.crt"
            for content in (b"", b"not a certificate", b"-----BEGIN PRIVATE KEY-----\n", b"x" * (MAX_CA_BYTES + 1)):
                path.write_bytes(content)
                with self.subTest(size=len(content)), self.assertRaises(ValueError):
                    tls_context(str(path))
            with self.assertRaises(ValueError):
                tls_context(directory)


if __name__ == "__main__":
    unittest.main()
