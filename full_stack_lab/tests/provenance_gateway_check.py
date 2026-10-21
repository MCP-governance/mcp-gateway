"""DEV-77/D-179: 게이트웨이 도입 승인 경로(agent_service.approve_mcp_request)의 출처 증명 검사.

provenance_verify_check.py는 검증 함수와 실행기(worker) 경로만 본다. 여기서는 승인 함수를 실제로 호출해
  - 유효 서명은 진행하고, 미제공은 `확인 안 됨`으로 표시하며 진행하고,
  - 서명 불일치는 MCP-SUPPLY-001로 보류(HOLD)하고,
  - 검증 불가(형식 오류·키 설정 오류·확인 경로 실패)는 미제공과 구별해 보류하고,
  - 신뢰 키 파일이 비었을 때 증명 안의 키를 처음 본 대로 믿지 않는지
를 확인한다.
대역: 데이터베이스(root_solo_behavior_check.FakeLedger), 게이트웨이 HTTP, 저장소 게시(publish_internal_repo).
실제 코드: artifact_provenance 전체(실제 Ed25519 서명·검증, 신뢰 키 파일 읽기), 승인 함수 본문, review.transition.
시험 안에서 만든 키로 서명한 증명이며 외부 빌더의 실제 SLSA 증명이 아니다.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import root_solo_behavior_check as lab  # noqa: E402

service = lab.service
if service is not None:
    from app import artifact_provenance as verify

ARTIFACT = "c" * 64  # base.row("repository")가 기록한 artifact.sha256
BUILDER = "https://example.test/builder"
KEY_FILE = "MCP_PROVENANCE_TRUST_KEYS_FILE"


def public_pem(private):
    return private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def attestation(private, digest=ARTIFACT, keyid="release-key", payload_type=None):
    """DSSE envelope: in-toto Statement v1 / SLSA Provenance v1, Ed25519 서명."""
    kind = verify.PAYLOAD_TYPE.encode()
    payload = json.dumps({"_type": verify.STATEMENT_TYPE, "predicateType": verify.SLSA_PREDICATE,
                          "subject": [{"name": "source-release", "digest": {"sha256": digest}}],
                          "predicate": {"buildDefinition": {"buildType": "https://example.test/build"},
                                        "runDetails": {"builder": {"id": BUILDER}}}}, separators=(",", ":")).encode()
    pae = b"DSSEv1 " + str(len(kind)).encode() + b" " + kind + b" " + str(len(payload)).encode() + b" " + payload
    return {"payloadType": payload_type or verify.PAYLOAD_TYPE, "payload": base64.b64encode(payload).decode(),
            "signatures": [{"keyid": keyid, "sig": base64.b64encode(private.sign(pae)).decode()}]}


@unittest.skipIf(service is None, "게이트웨이 이미지 의존성이 없어 승인 경로 시험을 건너뜀")
class GatewayProvenance(lab.Lab):
    env_mode = None  # 출처 검사는 승인 방식과 무관하다

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.signer = Ed25519PrivateKey.generate()
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.key_file = Path(self.folder.name) / "keys.json"
        self.trust({"release-key": {"public_key": public_pem(self.signer), "builders": [BUILDER]}})

    def trust(self, keys):
        self.key_file.write_text(keys if isinstance(keys, str) else json.dumps(keys), encoding="utf-8")
        self.use_file(str(self.key_file))

    def use_file(self, path):
        patcher = patch.dict(os.environ, {KEY_FILE: path} if path is not None else {})
        patcher.start()
        self.addCleanup(patcher.stop)
        if path is None:
            os.environ.pop(KEY_FILE, None)

    def intake(self, **verification):
        """저장소 신청(낮은 등급: 승인 1명으로 끝남). verification은 intake가 저장한 검증 기록에 들어간다."""
        row = lab.repository_row("low")
        row["provenance"] = {**row["provenance"], "verification": verification}
        self.ledger.add_intake({**row, "submitted_by": "employee"})
        self.ledger.tokens["employee"] = "employee"

    def stored(self):
        return self.ledger.intake()["provenance"].get("verification") or {}

    def hold_events(self):
        return self.ledger.kinds("provenance-mismatch", "held")

    async def blocked(self):
        """승인 시도가 MCP-SUPPLY-001로 보류되고 아무것도 게시·승인되지 않았음을 확인한다."""
        with self.assertRaises(service.HTTPException) as caught:
            await self.approve("tok-root")
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn(verify.POLICY_ID, caught.exception.detail)
        self.assertEqual(self.ledger.intake()["status"], "HOLD")
        (held,) = self.hold_events()
        self.assertIn(verify.POLICY_ID, held["reason"])
        self.assertEqual((self.published, self.ledger.kinds("intake-approve", "approved")), ([], []))
        return caught.exception.detail

    async def test_valid_signature_proceeds_and_is_recorded_as_verified(self):
        self.intake(attestation=attestation(self.signer))
        result = await self.approve("tok-root")
        self.assertEqual(result["request"]["status"], "APPROVED")
        self.assertEqual(self.published, [lab.REQUEST_ID])
        self.assertEqual((self.stored()["provenance_status"], self.stored()["provenance_keyid"]),
                         (verify.VERIFIED, "release-key"))
        self.assertEqual(self.hold_events(), [])

    async def test_missing_attestation_proceeds_and_is_shown_as_unconfirmed(self):
        for trust in ({}, "", "not json at all"):  # 증명이 없으면 신뢰 키 파일은 읽지도 않는다
            with self.subTest(trust_file=trust):
                await self.asyncSetUp()
                self.trust(trust)
                self.intake()
                result = await self.approve("tok-root")
                self.assertEqual(result["request"]["status"], "APPROVED")
                self.assertEqual(self.stored()["provenance_status"], verify.MISSING)
                self.assertEqual(self.stored()["provenance_status"], "확인 안 됨")
                self.assertEqual(self.hold_events(), [])
                self.assertEqual(len(self.published), 1)

    async def test_signature_mismatch_is_blocked_with_the_supply_policy_id(self):
        self.intake(attestation=attestation(Ed25519PrivateKey.generate()))  # 신뢰 키가 아닌 키로 서명
        detail = await self.blocked()
        self.assertIn(verify.MISMATCH, detail)
        self.assertNotIn(verify.MISSING, detail)

    async def test_attested_digest_other_than_the_recorded_artifact_is_blocked(self):
        self.intake(attestation=attestation(self.signer, digest="d" * 64))  # 서명은 맞지만 다른 산출물
        self.assertIn(verify.MISMATCH, await self.blocked())

    async def test_tampered_payload_is_blocked(self):
        envelope = attestation(self.signer)
        payload = json.loads(base64.b64decode(envelope["payload"]))
        payload["subject"][0]["digest"]["sha256"] = ARTIFACT  # 같은 값을 다시 써도 바이트가 달라지면 서명이 깨진다
        envelope["payload"] = base64.b64encode(json.dumps(payload, indent=2).encode()).decode()
        self.intake(attestation=envelope)
        self.assertIn(verify.MISMATCH, await self.blocked())

    async def test_unverifiable_is_blocked_and_told_apart_from_missing(self):
        wrong_type = attestation(self.signer, payload_type="application/octet-stream")
        cases = {
            "형식 오류": dict(attestation=wrong_type),
            "확인 경로 실패": dict(attestation=attestation(self.signer), error="network timeout"),
            "서명 없는 envelope": dict(attestation={"payloadType": verify.PAYLOAD_TYPE, "payload": "!!", "signatures": [{}]}),
        }
        for name, verification in cases.items():
            with self.subTest(name):
                await self.asyncSetUp()
                self.intake(**verification)
                detail = await self.blocked()
                self.assertIn(verify.UNAVAILABLE, detail)
                self.assertNotIn(verify.MISSING, detail)

    async def test_trust_key_configuration_errors_block_instead_of_passing(self):
        broken = {"목록 형식": json.dumps(["release-key"]), "값 형식": json.dumps({"release-key": 5}), "JSON 아님": "{",
                  "빈 파일": ""}
        for name, content in broken.items():
            with self.subTest(name):
                await self.asyncSetUp()
                self.trust(content)
                self.intake(attestation=attestation(self.signer))
                detail = await self.blocked()
                self.assertIn(verify.UNAVAILABLE, detail)
        await self.asyncSetUp()
        self.use_file(str(Path(self.folder.name) / "missing.json"))  # 파일이 없다
        self.intake(attestation=attestation(self.signer))
        self.assertIn(verify.UNAVAILABLE, await self.blocked())

    async def test_empty_trust_configuration_never_trusts_the_key_it_first_sees(self):
        for name, content, path in (("빈 객체", "{}", True), ("설정 안 함", None, False)):
            with self.subTest(name):
                await self.asyncSetUp()
                if path:
                    self.trust(content)
                else:
                    self.use_file(None)
                self.intake(attestation=attestation(self.signer))  # 형식·digest·서명 모두 맞는 증명
                before = self.key_file.read_bytes()
                await self.blocked()
                self.assertEqual(self.key_file.read_bytes(), before)  # 증명에서 키를 배워 파일에 쓰지 않는다
                self.ledger.intake()["status"] = "VALIDATED"  # 다시 시도해도 마찬가지다
                self.ledger.events.clear()
                await self.blocked()

    async def test_attestation_cannot_name_its_own_trust_key(self):
        other = Ed25519PrivateKey.generate()
        self.trust({"release-key": {"public_key": public_pem(other), "builders": [BUILDER]}})  # 신뢰 키는 다른 키
        self.intake(attestation=attestation(self.signer, keyid="attacker-key"))
        self.assertIn(verify.UNAVAILABLE, await self.blocked())

    async def test_valid_signature_under_a_key_id_the_configuration_does_not_list_is_blocked(self):
        self.intake(attestation=attestation(self.signer, keyid="unlisted-key"))  # 서명은 신뢰 키로 했지만 증명이 붙인 이름이 설정에 없다
        self.assertIn(verify.UNAVAILABLE, await self.blocked())

    async def test_builder_outside_the_trusted_list_is_not_accepted(self):
        self.trust({"release-key": {"public_key": public_pem(self.signer), "builders": ["https://other.test/builder"]}})
        self.intake(attestation=attestation(self.signer))
        await self.blocked()


if __name__ == "__main__":
    unittest.main(verbosity=2)
