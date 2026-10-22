"""Offline TLS fixture checks: no containers, sockets, or replacement MCP server."""
import importlib.util
import json
from pathlib import Path
import ssl
import tempfile
import tomllib
import unittest
from urllib.parse import urlsplit

import certifi
from cryptography import x509

LAB = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("acceptance_tls_prepare", LAB / "tests/fixtures/acceptance-tls/prepare.py")
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


def handshake(output, hostname, trusted):
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(output / "server.pem", output / "server.key")
    client_context = ssl.create_default_context(cafile=str(output / "ca-bundle.pem") if trusted else certifi.where())
    incoming, outgoing, server_in, server_out = (ssl.MemoryBIO() for _ in range(4))
    client = client_context.wrap_bio(incoming, outgoing, server_hostname=hostname)
    server = server_context.wrap_bio(server_in, server_out, server_side=True)
    completed = set()
    for _ in range(10):
        for name, peer in (("client", client), ("server", server)):
            if name in completed:
                continue
            try:
                peer.do_handshake()
                completed.add(name)
            except ssl.SSLWantReadError:
                pass
        if outgoing.pending:
            server_in.write(outgoing.read())
        if server_out.pending:
            incoming.write(server_out.read())
        if len(completed) == 2:
            return client.version()
    raise AssertionError("TLS handshake did not finish")


class AcceptanceTLSFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.output = Path(cls.temporary.name) / "tls"
        prepare.prepare(LAB / "registry", cls.output, Path(certifi.where()))

    def test_only_fetch_endpoint_changes_and_lock_is_byte_identical(self):
        original = tomllib.loads((LAB / "registry/catalog.toml").read_text())
        generated = tomllib.loads((self.output / "registry/catalog.toml").read_text())
        original["servers"]["fetch"]["endpoint"] = prepare.ENDPOINT
        self.assertEqual(original, generated)
        self.assertEqual((LAB / "registry/contracts.lock.json").read_bytes(),
                         (self.output / "registry/contracts.lock.json").read_bytes())

    def test_fixture_host_is_in_the_egress_allowlist(self):
        # The CI catalog points fetch at this host; MCP-EGRESS-001 blocks every fetch call if it is missing.
        allowed = json.loads((LAB / "opa/data.json").read_text(encoding="utf-8"))["egress"]["allowed_hosts"]
        self.assertIn(urlsplit(prepare.ENDPOINT).hostname, allowed)

    def test_trusted_ca_and_hostname_complete_real_tls_handshake_in_memory(self):
        self.assertIn(handshake(self.output, "mcp-fetch-tls", True), {"TLSv1.2", "TLSv1.3"})

    def test_untrusted_ca_is_rejected(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            handshake(self.output, "mcp-fetch-tls", False)

    def test_wrong_hostname_is_rejected(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            handshake(self.output, "another-provider", True)

    def test_short_lived_leaf_and_no_persisted_signing_key(self):
        leaf = x509.load_pem_x509_certificate((self.output / "server.pem").read_bytes())
        self.assertLessEqual((leaf.not_valid_after_utc - leaf.not_valid_before_utc).total_seconds(), 2 * 86400 + 300)
        self.assertEqual((self.output / "server.key").stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.output.glob("*.key")), [self.output / "server.key"])
        self.assertEqual((self.output / "ca-bundle.pem").read_bytes(),
                         Path(certifi.where()).read_bytes().rstrip() + b"\n" + (self.output / "ca.pem").read_bytes())

    def test_preparation_refuses_rotating_existing_fixture(self):
        before = (self.output / "server.pem").read_bytes()
        with self.assertRaises(ValueError):
            prepare.prepare(LAB / "registry", self.output, Path(certifi.where()))
        self.assertEqual(before, (self.output / "server.pem").read_bytes())


if __name__ == "__main__":
    unittest.main()
