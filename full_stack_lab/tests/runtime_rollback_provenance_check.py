"""DEV-78: rollback rechecks a prior signed source against the trust roots active now."""
from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "runtime"), str(ROOT / "gateway" / "app"), str(ROOT / "supply_chain")]
import runtime_rollback_reconcile_check as base  # noqa: E402
from runtime_rollback_reconcile_check import Harness, Ledger, worker  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402


def signed_evidence(private: Ed25519PrivateKey) -> dict:
    verify = worker.artifact_provenance
    digest = "5" * 64
    payload = json.dumps({"_type": verify.STATEMENT_TYPE, "subject": [
        {"name": "source", "digest": {"sha256": digest}}], "predicateType": verify.SLSA_PREDICATE,
        "predicate": {"buildDefinition": {"buildType": "https://builder.example/build"},
                      "runDetails": {"builder": {"id": "https://builder.example"}}}},
        separators=(",", ":")).encode()
    payload_type = verify.PAYLOAD_TYPE.encode()
    pae = b"DSSEv1 " + str(len(payload_type)).encode() + b" " + payload_type + b" " + str(len(payload)).encode() + b" " + payload
    envelope = {"payloadType": verify.PAYLOAD_TYPE, "payload": base64.b64encode(payload).decode(),
                "signatures": [{"keyid": "release", "sig": base64.b64encode(private.sign(pae)).decode()}]}
    return {"source_archive_sha256": digest, "source_attestation": envelope}


class RollbackProvenance(Harness):
    def setUp(self):
        self.private = Ed25519PrivateKey.generate()
        self.public = self.private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.key_file = Path(self.folder.name) / "keys.json"

    def ledger_with_proof(self, evidence):
        ledger = Ledger()
        ledger.row(1)["evidence"] = evidence
        return ledger

    def verify_with_current_file(self):
        verify = worker.verify_source_provenance
        return lambda evidence, **_kwargs: verify(evidence, trust_file=str(self.key_file))

    def test_currently_trusted_signature_allows_rollback(self):
        self.key_file.write_text(json.dumps({"release": {"public_key": self.public,
            "builders": ["https://builder.example"]}}), encoding="utf-8")
        ledger = self.ledger_with_proof(signed_evidence(self.private))
        self.run_reconcile(ledger, verify=self.verify_with_current_file())
        self.assertEqual(ledger.row(3)["status"], "QUEUED")
        self.assertNotIn("runtime-rollback-refused", ledger.kinds())

    def test_revoked_key_refuses_rollback_and_does_not_requeue(self):
        self.key_file.write_text("{}", encoding="utf-8")
        ledger = self.ledger_with_proof(signed_evidence(self.private))
        self.run_reconcile(ledger, verify=self.verify_with_current_file())
        self.assertEqual(self.calls, [])
        self.assertEqual(ledger.row(2)["status"], "STOPPED")
        self.assertEqual(len(ledger.runtimes), 2)
        self.assertNotIn("runtime-rollback-queued", ledger.kinds())
        refusal = next(event for event in ledger.events if event["kind"] == "runtime-rollback-refused")
        self.assertEqual(refusal["outcome"], "refused")
        self.assertIn("MCP-SUPPLY-001", refusal["reason"])

    def test_missing_proof_allows_rollback_as_unconfirmed(self):
        evidence = dict(base.PRIOR_EVIDENCE)
        evidence.pop("source_attestation", None)
        evidence.pop("provenance_verification", None)
        ledger = self.ledger_with_proof(evidence)
        self.run_reconcile(ledger)
        self.assertEqual(ledger.row(3)["status"], "QUEUED")
        self.assertNotIn("runtime-rollback-refused", ledger.kinds())


if __name__ == "__main__":
    unittest.main()
