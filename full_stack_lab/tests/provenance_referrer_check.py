"""DEV-77: OCI referrer discovery is optional, bounded, allowlisted and still fail-closed once found."""
from __future__ import annotations

import asyncio
import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from gateway.app import agent_service
from gateway.app import artifact_provenance as provenance

DIGEST = "a" * 64
REPOSITORY = "https://github.com/example/project"
ORIGIN = "https://registry.example"


def signed_envelope(private: Ed25519PrivateKey, digest: str = DIGEST) -> dict:
    payload = json.dumps({"_type": provenance.STATEMENT_TYPE, "subject": [
        {"name": "source", "digest": {"sha256": digest}}], "predicateType": provenance.SLSA_PREDICATE,
        "predicate": {"buildDefinition": {"buildType": "https://builder.example/build"},
                      "runDetails": {"builder": {"id": "https://builder.example"}}}},
        separators=(",", ":")).encode()
    payload_type = provenance.PAYLOAD_TYPE.encode()
    pae = b"DSSEv1 " + str(len(payload_type)).encode() + b" " + payload_type + b" " + str(len(payload)).encode() + b" " + payload
    return {"payloadType": provenance.PAYLOAD_TYPE, "payload": base64.b64encode(payload).decode(),
            "signatures": [{"keyid": "release", "sig": base64.b64encode(private.sign(pae)).decode()}]}


class ReferrerCollection(unittest.TestCase):
    def setUp(self):
        self.private = Ed25519PrivateKey.generate()
        self.public = self.private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        self.envelope = signed_envelope(self.private)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.key_file = Path(self.temp.name) / "keys.json"
        self.key_file.write_text(json.dumps({"release": {"public_key": self.public,
            "builders": ["https://builder.example"]}}), encoding="utf-8")
        self.env = mock.patch.dict("os.environ", {"MCP_PROVENANCE_TRUST_KEYS_FILE": str(self.key_file)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def row(self):
        return {"intake_kind": "repository", "repository_url": REPOSITORY}

    def record(self):
        return {"artifact": {"sha256": DIGEST}}

    def test_valid_referrer_is_discovered_and_filled_into_proposal(self):
        with mock.patch.object(provenance, "allowed_registry_origins", return_value=[ORIGIN]), \
                mock.patch.object(provenance, "collect_intake_referrer", return_value=self.envelope) as collect:
            record, blocker = asyncio.run(agent_service.collect_proposal_provenance(self.row(), self.record()))
        collect.assert_called_once_with([ORIGIN], REPOSITORY, f"sha256:{DIGEST}")
        self.assertEqual(record["verification"]["attestation"], self.envelope)
        self.assertEqual(record["verification"]["attestation_source"], "oci-referrer")
        self.assertEqual(record["verification"]["provenance_status"], provenance.VERIFIED)
        self.assertIsNone(blocker)

    def test_distribution_referrers_response_yields_dsse_blob(self):
        index = {"schemaVersion": 2, "manifests": [{"digest": "sha256:" + "b" * 64}]}
        manifest = {"schemaVersion": 2, "layers": [{"mediaType": "application/vnd.dsse.envelope.v1+json",
            "data": base64.b64encode(json.dumps(self.envelope).encode()).decode()}]}

        def get(_origin, path, **_kwargs):
            if "/referrers/" in path:
                return json.dumps(index).encode()
            if path.endswith("sha256:" + "b" * 64):
                return json.dumps(manifest).encode()
            raise AssertionError(path)

        with mock.patch.object(provenance, "_registry_get", side_effect=get):
            found = provenance.collect_intake_referrer([ORIGIN], REPOSITORY, f"sha256:{DIGEST}")
        self.assertEqual(found, self.envelope)

    def test_no_proof_leaves_proposal_unconfirmed(self):
        with mock.patch.object(provenance, "allowed_registry_origins", return_value=[]):
            record, blocker = asyncio.run(agent_service.collect_proposal_provenance(self.row(), self.record()))
        self.assertEqual(record["verification"]["provenance_status"], provenance.MISSING)
        self.assertIsNone(blocker)

    def test_discovery_failure_leaves_proposal_unconfirmed_and_does_not_block(self):
        with mock.patch.object(provenance, "allowed_registry_origins", return_value=[ORIGIN]), \
                mock.patch.object(provenance, "_registry_get", side_effect=URLError("offline")):
            record, blocker = asyncio.run(agent_service.collect_proposal_provenance(self.row(), self.record()))
        self.assertEqual(record["verification"]["provenance_status"], provenance.MISSING)
        self.assertIsNone(blocker)

    def test_malformed_registry_response_leaves_proposal_unconfirmed(self):
        with mock.patch.object(provenance, "allowed_registry_origins", return_value=[ORIGIN]), \
                mock.patch.object(provenance, "_registry_get", return_value=b"not-json"):
            record, blocker = asyncio.run(agent_service.collect_proposal_provenance(self.row(), self.record()))
        self.assertEqual(record["verification"]["provenance_status"], provenance.MISSING)
        self.assertIsNone(blocker)

    def test_found_but_invalid_proof_blocks(self):
        invalid = signed_envelope(Ed25519PrivateKey.generate())
        with mock.patch.object(provenance, "collect_intake_referrer", return_value=invalid):
            record, blocker = asyncio.run(agent_service.collect_proposal_provenance(self.row(), self.record()))
        self.assertEqual(record["verification"]["provenance_status"], provenance.MISMATCH)
        self.assertIn(provenance.POLICY_ID, blocker)

    def test_registry_outside_allowlist_is_never_queried(self):
        origins = provenance.allowed_registry_origins(ORIGIN)
        malicious = {**self.row(), "repository_url": "https://registry.example/other/project"}
        with mock.patch.object(provenance, "allowed_registry_origins", return_value=origins), \
                mock.patch.object(provenance, "_registry_get", side_effect=AssertionError("network request")) as get:
            record, blocker = asyncio.run(agent_service.collect_proposal_provenance(malicious, self.record()))
        self.assertEqual(record["verification"]["provenance_status"], provenance.MISSING)
        self.assertIsNone(blocker)
        get.assert_not_called()
        self.assertEqual(origins, [ORIGIN])

    def test_response_over_limit_leaves_proposal_unconfirmed(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self, limit):
                return b"x" * limit

        class Opener:
            def open(self, *_args, **_kwargs):
                return Response()

        with mock.patch.object(provenance, "allowed_registry_origins", return_value=[ORIGIN]), \
                mock.patch.object(provenance, "build_opener", return_value=Opener()):
            record, blocker = asyncio.run(agent_service.collect_proposal_provenance(self.row(), self.record()))
        self.assertEqual(record["verification"]["provenance_status"], provenance.MISSING)
        self.assertIsNone(blocker)


if __name__ == "__main__":
    unittest.main()
