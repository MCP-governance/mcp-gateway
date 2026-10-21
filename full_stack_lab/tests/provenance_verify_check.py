"""DEV-77: signed DSSE source provenance is optional, but present failures fail closed."""
from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "runtime"), str(ROOT / "gateway" / "app"), str(ROOT / "supply_chain")]
import artifact_provenance as verify  # noqa: E402
import worker  # noqa: E402

DIGEST = "a" * 64
TYPE = verify.PAYLOAD_TYPE.encode()


class ProvenanceVerification(unittest.TestCase):
    def setUp(self):
        self.private = Ed25519PrivateKey.generate()
        public = self.private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        self.keys = {"release-key": {"public_key": public,
                                     "builders": ["https://example.test/builder"]}}

    def envelope(self, digest=DIGEST, private=None):
        payload = json.dumps({"_type": "https://in-toto.io/Statement/v1", "subject": [
            {"name": "source-release", "digest": {"sha256": digest}}],
            "predicateType": "https://slsa.dev/provenance/v1",
            "predicate": {"buildDefinition": {"buildType": "https://example.test/build"},
                          "runDetails": {"builder": {"id": "https://example.test/builder"}}}},
            separators=(",", ":")).encode()
        pae = b"DSSEv1 " + str(len(TYPE)).encode() + b" " + TYPE + b" " + str(len(payload)).encode() + b" " + payload
        signature = (private or self.private).sign(pae)
        return {"payloadType": verify.PAYLOAD_TYPE, "payload": base64.b64encode(payload).decode(),
                "signatures": [{"keyid": "release-key", "sig": base64.b64encode(signature).decode()}]}

    def record(self, envelope=None):
        return {"verification": {"attestation": envelope}}

    def test_valid_attestation_passes(self):
        result = verify.verify_source_attestation(self.record(self.envelope()), DIGEST, self.keys)
        self.assertEqual(result["status"], verify.VERIFIED)

    def test_bad_signature_blocks_with_supply_policy_id(self):
        wrong = Ed25519PrivateKey.generate()
        result = verify.verify_source_attestation(self.record(self.envelope(private=wrong)), DIGEST, self.keys)
        self.assertEqual(result["status"], verify.MISMATCH)
        self.assertIn("MCP-SUPPLY-001", verify.blocking_reason(result))

    def test_absent_attestation_is_visible_but_allowed(self):
        result = verify.verify_source_attestation({}, DIGEST, {})
        self.assertEqual(result["status"], verify.MISSING)
        self.assertIsNone(verify.blocking_reason(result))

    def test_verifier_failure_is_distinct_from_missing_and_blocks(self):
        result = verify.verify_source_attestation(
            {"verification": {"error": "network timeout"}}, DIGEST, {})
        self.assertEqual(result["status"], verify.UNAVAILABLE)
        self.assertIsNotNone(verify.blocking_reason(result))
        self.assertNotEqual(result["status"], verify.MISSING)

    def test_startup_expected_digest_is_the_recorded_digest(self):
        evidence = {"source_archive_sha256": DIGEST, "source_attestation": self.envelope()}
        self.assertEqual(worker.verify_source_provenance(
            {"source_archive_sha256": DIGEST}, trust_file="")["status"], verify.MISSING)
        with tempfile.TemporaryDirectory() as folder:
            key_file = Path(folder) / "keys.json"
            key_file.write_text(json.dumps(self.keys), encoding="utf-8")
            self.assertEqual(worker.verify_source_provenance(evidence, trust_file=str(key_file))["status"], verify.VERIFIED)
            evidence["source_archive_sha256"] = "b" * 64
            with self.assertRaisesRegex(worker.Refused, "MCP-SUPPLY-001"):
                worker.verify_source_provenance(evidence, trust_file=str(key_file))

    def test_missing_trust_key_never_learns_key_from_attestation(self):
        result = verify.verify_source_attestation(self.record(self.envelope()), DIGEST, {})
        self.assertEqual(result["status"], verify.UNAVAILABLE)
        self.assertIsNotNone(verify.blocking_reason(result))


if __name__ == "__main__":
    unittest.main()
