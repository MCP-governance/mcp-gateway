"""D-179: 한 화면 승인(agent_service.approve_and_register)의 저장소 분기가 출처 검증 결과를 승인 기록에 남긴다.

미리보기가 계산한 provenance_status·provenance_keyid·provenance_reason과 증명 본문(attestation, attestation_source)이
승인 기록(mcp_intake_requests.provenance)과 등록 서버(spec.provenance)에 남고, 콘솔 「서명·빌드 증명」(console.js)이 읽는
`provenance.verification.provenance_status`가 실제 결과를 보여 준다. 클릭 시점 재검증 결과는 미리보기 값보다 우선한다.
대역과 증명은 oneclick_markers_provenance_check.py와 같다(시험 안에서 만든 키로 서명, 실제 PostgreSQL·HTTP·MCP 없음).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import oneclick_markers_provenance_check as mk  # noqa: E402
import provenance_gateway_check as prov  # noqa: E402
import root_solo_behavior_check as lab  # noqa: E402

service, base, verify = lab.service, lab.base, getattr(mk, "verify", None)


@mk.without_inherited_tests
@unittest.skipIf(service is None, "게이트웨이 이미지 의존성이 없어 승인 경로 시험을 건너뜀")
class OneClickVerificationRecord(mk.OneClickProvenance, lab.RegisterServerRoute):
    """저장소 신청의 한 화면 승인. 승인 기록과 등록 서버에 남은 검증 결과를 본다."""

    def recorded(self):
        return self.ledger.intake()["provenance"]["verification"]

    async def registered_provenance(self):
        body = self.registered[-1]
        await self.register(body)
        return self.saved[-1]["servers"][body["server_id"]]["provenance"]["verification"]

    async def test_verified_signature_is_kept_on_the_approval_record_and_the_registered_server(self):
        for tier in ("low", "high"):
            with self.subTest(tier=tier):
                await self.asyncSetUp()
                envelope = prov.attestation(self.signer)
                shown = await self.open_repository(tier, envelope)
                await self.finish(shown, tier)
                self.assertEqual(self.ledger.intake()["status"], "APPROVED")
                for where, found in (("승인 기록", self.recorded()), ("등록 서버", await self.registered_provenance())):
                    self.assertEqual((found["provenance_status"], found["provenance_keyid"]), (verify.VERIFIED, "release-key"), where)
                    self.assertTrue(found["provenance_reason"], where)
                    self.assertEqual(found["attestation"], envelope, where)  # 증명 본문
                    self.assertEqual(found["match"], True, where)  # 사본 대조 결과도 그대로
                    self.assertEqual((found["by"], found["sha256"]), ("tok-root" if tier == "low" else "tok-b", "c" * 64), where)

    async def test_missing_attestation_is_recorded_as_unconfirmed(self):
        for tier in ("low", "high"):
            with self.subTest(tier=tier):
                await self.asyncSetUp()
                shown = await self.open_repository(tier)
                await self.finish(shown, tier)
                for where, found in (("승인 기록", self.recorded()), ("등록 서버", await self.registered_provenance())):
                    self.assertEqual(found["provenance_status"], verify.MISSING, where)
                    self.assertEqual(found["provenance_status"], "확인 안 됨", where)
                    self.assertIsNone(found["provenance_keyid"], where)
                    self.assertNotIn("attestation", found, where)
                    self.assertEqual(found["match"], True, where)

    async def test_the_click_time_recheck_outranks_the_previews_stored_result(self):
        # 저장된 제안의 검증 결과 필드가 낡았거나 바뀌어 있어도(화면 해시는 다시 계산), 기록은 클릭 때 다시 검증한 값이다.
        stale = {"provenance_status": verify.MISSING, "provenance_keyid": "stale-key", "provenance_reason": "낡은 값"}
        for tier in ("low", "high"):
            with self.subTest(tier=tier):
                await self.asyncSetUp()
                shown = await self.open_repository(tier, prov.attestation(self.signer))
                stored = self.ledger.intake()["evidence"]["approval_proposal"]
                stored["provenance"]["verification"].update(stale)
                shown = {**shown, "proposal_sha256": base.intake_proposal.digest(stored)}
                await self.finish(shown, tier)
                for where, found in (("승인 기록", self.recorded()), ("등록 서버", await self.registered_provenance())):
                    self.assertEqual((found["provenance_status"], found["provenance_keyid"]), (verify.VERIFIED, "release-key"), where)
                    self.assertNotEqual(found["provenance_reason"], stale["provenance_reason"], where)

    async def test_trust_key_changed_after_the_preview_is_blocked_and_leaves_no_record(self):
        # 키가 바뀌어 재검증이 실패하면 승인되지 않으므로 승인 기록에 검증됨이 남을 수 없다.
        for tier in ("low", "high"):
            with self.subTest(tier=tier):
                await self.asyncSetUp()
                shown = await self.open_repository(tier, prov.attestation(self.signer))
                self.trust(Ed25519PrivateKey.generate())
                await self.blocked(shown, verify.POLICY_ID, "재검증")
                self.assertNotIn("provenance_status", self.ledger.intake()["provenance"].get("verification", {}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
