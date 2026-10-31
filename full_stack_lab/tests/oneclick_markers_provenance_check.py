"""D-188/D-179: 한 화면 승인(agent_service.approve_and_register)의 승인 방식 표식과 출처 증명 재검증.

root_solo_behavior_check.py·provenance_gateway_check.py의 대역(FakeLedger, 게이트웨이 HTTP, 저장소 게시)을 그대로 빌려 쓴다.
  - 표식: 한 화면 승인이 `intake-one-click` 사건·`risk_assessment`·등록 서버에 solo_mode/solo_operator를 실제 값대로 남긴다.
          표식은 기록값일 뿐이며 승인자 수 계산에는 쓰이지 않는다.
  - 출처: 신뢰 키가 아닌 키로 서명한 증명을 둔 저장소 신청은 한 화면 승인에서 409로 막히고 게시·등록이 나가지 않는다.
          미제공은 `확인 안 됨`으로 표시하며 진행한다. 높음 등급은 첫 승인부터 막힌다.
시험 안에서 만든 키로 서명한 증명이며 외부 빌더의 실제 SLSA 증명이 아니다. 실제 PostgreSQL·HTTP·MCP는 쓰지 않는다.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import provenance_gateway_check as prov  # noqa: E402
import root_solo_behavior_check as lab  # noqa: E402

service, base = lab.service, lab.base
if service is not None:
    from app import artifact_provenance as verify


def without_inherited_tests(cls):
    """상속한 대역 준비만 쓰고, 부모 클래스의 시험은 여기서 다시 돌리지 않는다."""
    for name in dir(cls):
        if name.startswith("test") and name not in cls.__dict__:
            setattr(cls, name, None)
    return cls


@without_inherited_tests
@unittest.skipIf(service is None, "게이트웨이 이미지 의존성이 없어 승인 경로 시험을 건너뜀")
class OneClickMarkers(lab.RegisterServerRoute):
    """한 화면 승인 → (사건·증거) → core.register_server까지 표식이 실제 값대로 옮겨진다."""

    async def run_mode(self, mode):
        self.env_mode = mode
        await self.asyncSetUp()

    def assert_marks(self, found, expected, where):
        self.assertIs(found.get("solo_mode"), expected[0], where + " solo_mode")
        self.assertIs(found.get("solo_operator"), expected[1], where + " solo_operator")

    async def registered_marks(self):
        body = self.registered[-1]
        await self.register(body)
        return self.saved[-1]["servers"][body["server_id"]]["risk_assessment"]

    async def test_one_approver_finish_records_the_real_marks_everywhere(self):
        # (모드 값, 클릭한 사람) -> (solo_mode, solo_operator). tok-root만 root이고 단독 운영은 root에게만 표시된다.
        cases = [("1", "tok-root", (True, True)), ("1", "tok-b", (True, False)),
                 (None, "tok-root", (False, False)), (None, "tok-b", (False, False)),
                 ("0", "tok-root", (False, False))]  # 1이 아닌 값은 꺼짐
        for tier in ("low", "medium"):
            for mode, token, expected in cases:
                with self.subTest(tier=tier, mode=mode, token=token):
                    await self.run_mode(mode)
                    shown = await self.open_review(tier)
                    await self.click(token, shown)
                    self.assertEqual(self.ledger.intake()["status"], "APPROVED")
                    (event,) = self.ledger.kinds("intake-one-click", "approved")
                    self.assert_marks(event["scope"], expected, "사건")
                    self.assert_marks(self.ledger.intake()["evidence"]["risk_assessment"], expected, "증거")
                    if tier == "medium":  # 저장소 신청의 등록은 관리 실행 준비가 더 필요하므로 원격 신청으로 끝까지 본다
                        self.assert_marks(await self.registered_marks(), expected, "등록 서버")

    async def test_two_approver_flow_marks_each_click_and_the_final_record_by_the_finishing_administrator(self):
        for tier, reason in (("high", ""), ("very_high", lab.REASON)):
            # D-306: with the mode on root would finish alone, so another administrator clicks first there.
            for mode, first, second, expected_first, expected_final in (
                    ("1", "tok-b", "tok-root", (True, False), (True, True)),
                    (None, "tok-root", "tok-b", (False, False), (False, False))):
                with self.subTest(tier=tier, mode=mode):
                    await self.run_mode(mode)
                    shown = await self.open_review(tier)
                    self.assertIs((await self.click(first, shown, reason))["pending"], True)
                    (recorded,) = self.ledger.kinds("intake-one-click", "recorded")
                    self.assert_marks(recorded["scope"], expected_first, "1차 사건")
                    self.assertEqual(self.registered, [])
                    await self.click(second, shown, reason)
                    (event,) = self.ledger.kinds("intake-one-click", "approved")
                    self.assert_marks(event["scope"], expected_final, "최종 사건")
                    record = self.ledger.intake()["evidence"]["risk_assessment"]
                    self.assert_marks(record, expected_final, "증거")
                    self.assert_marks(await self.registered_marks(), expected_final, "등록 서버")
                    self.assertEqual((record["approvers"], len(self.registered)), ([first, second], 1))

    async def test_solo_root_alone_still_waits_for_a_second_person_and_marks_do_not_count_as_one(self):
        # D-306: with the mode on, root carries the high tier out alone and the record says so.
        await self.run_mode("1")
        shown = await self.open_review("high")
        await self.click("tok-root", shown)
        self.assertEqual(len(self.registered), 1)
        (event,) = self.ledger.kinds("intake-one-click", "approved")
        self.assert_marks(event["scope"], (True, True), "단독 집행")
        for mode in (None,):
            with self.subTest(mode=mode):
                await self.run_mode(mode)
                shown = await self.open_review("high")
                for token in ("tok-root", "tok-root-2", "tok-root"):
                    self.assertIs((await self.click(token, shown))["pending"], True)
                self.assertEqual((self.registered, self.pending()), ([], ["tok-root"]))
                self.assertEqual(self.ledger.kinds("intake-one-click", "approved"), [])

    async def test_a_click_cannot_bring_its_own_marks(self):
        shown = await self.open_review("medium")
        for field in ("solo_mode", "solo_operator"):
            with self.assertRaises(Exception) as caught:  # pydantic ValidationError (extra=forbid)
                service.OneClickApproval(proposal_sha256=shown["proposal_sha256"], tools=["lookup"], **{field: True})
            self.assertIn("extra", str(caught.exception).lower())


@unittest.skipIf(service is None, "게이트웨이 이미지 의존성이 없어 승인 경로 시험을 건너뜀")
class OneClickProvenance(lab.OneClickLab):
    """저장소 신청의 한 화면 승인. 출처 증명은 게이트웨이 승인 경로와 같은 실제 검증 코드를 거친다."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.signer = Ed25519PrivateKey.generate()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.key_file = Path(folder.name) / "keys.json"
        self.trust(self.signer)
        os.environ[prov.KEY_FILE] = str(self.key_file)  # Lab.start가 환경을 되돌려 놓는다

    def trust(self, signer, builders=None):
        self.key_file.write_text(json.dumps({"release-key": {
            "public_key": prov.public_pem(signer), "builders": builders or [prov.BUILDER]}}), encoding="utf-8")

    async def open_repository(self, tier, envelope=None):
        """tier가 low(공개 자료·읽기) 또는 high(중요 자료·실행)인 저장소 신청의 검토 화면."""
        row = base.row("repository", grade="important" if tier == "high" else "public")
        row["evidence"]["local_run"] = lab.source_run(row)
        if envelope is not None:
            row["provenance"]["verification"] = {"attestation": envelope}
        self.ledger.add_intake(row)
        self.ledger.tokens["employee"] = "employee"
        self.catalog["tools"][0]["suggested"] = "x" if tier == "high" else "r"
        shown = await service.preview_intake_approval(lab.REQUEST_ID, service.ApprovalPreview(), lab.USERS["tok-root"], "tok-root")
        self.assertEqual(shown["proposal"]["risk"]["tier"], tier)
        return shown

    async def finish(self, shown, tier):
        """등급이 요구하는 만큼 서로 다른 관리자가 승인한다(단독 모드의 root는 혼자 끝낸다, D-306)."""
        for token in ("tok-root", "tok-b")[:2 if tier == "high" and not self.forced else 1]:
            await self.click(token, shown)

    def assert_nothing_went_out(self):
        self.assertEqual((self.published, self.registered, self.ledger.kinds("intake-one-click", "approved")), ([], [], []))
        self.assertNotEqual(self.ledger.intake()["status"], "APPROVED")

    async def blocked(self, shown, *needles):
        with self.assertRaises(service.HTTPException) as caught:
            await self.click("tok-root", shown)
        self.assertEqual(caught.exception.status_code, 409)
        for needle in needles:
            self.assertIn(needle, caught.exception.detail)
        self.assert_nothing_went_out()
        self.assertIsNone(self.pending())  # 막힌 첫 승인은 대기 상태도 남기지 않는다
        return caught.exception.detail

    def shown_proof(self, shown):
        """검토 화면(제안)이 보여 주는 출처 증명 결과. 승인 기록 쪽 보존은 이 시험이 보증하지 않는다."""
        return shown["proposal"]["provenance"]["verification"]

    async def test_unattested_repository_proceeds_and_is_shown_as_unconfirmed(self):
        for tier in ("low", "high"):
            with self.subTest(tier=tier):
                await self.asyncSetUp()
                shown = await self.open_repository(tier)
                await self.finish(shown, tier)
                self.assertEqual((self.ledger.intake()["status"], len(self.registered), self.published), ("APPROVED", 1, [lab.REQUEST_ID]))
                self.assertEqual(self.shown_proof(shown)["provenance_status"], verify.MISSING)
                self.assertEqual(self.shown_proof(shown)["provenance_status"], "확인 안 됨")

    async def test_trusted_signature_proceeds_and_is_recorded_as_verified(self):
        for tier in ("low", "high"):
            with self.subTest(tier=tier):
                await self.asyncSetUp()
                shown = await self.open_repository(tier, prov.attestation(self.signer))
                self.assertEqual(shown["proposal"]["blockers"], [])
                await self.finish(shown, tier)
                self.assertEqual((self.ledger.intake()["status"], len(self.registered)), ("APPROVED", 1))
                self.assertEqual((self.shown_proof(shown)["provenance_status"], self.shown_proof(shown)["provenance_keyid"]),
                                 (verify.VERIFIED, "release-key"))

    async def test_signature_by_an_untrusted_key_is_blocked_already_on_the_review_screen(self):
        for tier in ("low", "high"):
            with self.subTest(tier=tier):
                await self.asyncSetUp()
                shown = await self.open_repository(tier, prov.attestation(Ed25519PrivateKey.generate()))
                self.assertEqual([b["code"] for b in shown["proposal"]["blockers"]], ["provenance-mismatch"])
                await self.blocked(shown, "검증을 통과하지 못했습니다")

    async def test_signature_turned_untrusted_after_the_screen_opened_is_blocked_at_the_click(self):
        # 화면을 열 때는 신뢰 키로 서명한 증명이었다가, 클릭 전에 신뢰 키가 바뀐 경우(키 교체·폐기).
        for tier in ("low", "high"):
            with self.subTest(tier=tier):
                await self.asyncSetUp()
                shown = await self.open_repository(tier, prov.attestation(self.signer))
                self.assertEqual(shown["proposal"]["blockers"], [])
                self.trust(Ed25519PrivateKey.generate())
                detail = await self.blocked(shown, verify.POLICY_ID, "재검증")
                self.assertIn(verify.MISMATCH, detail)

    async def test_proposal_with_a_swapped_attestation_is_blocked_by_the_click_time_recheck(self):
        # 저장된 제안 안의 증명을 신뢰 키가 아닌 키의 서명으로 바꾸고 다른 검사는 모두 통과하게 맞춘다(화면 해시도 다시 계산).
        for tier in ("low", "high"):
            with self.subTest(tier=tier):
                await self.asyncSetUp()
                shown = await self.open_repository(tier, prov.attestation(self.signer))
                stored = self.ledger.intake()["evidence"]["approval_proposal"]
                stored["provenance"]["verification"]["attestation"] = prov.attestation(Ed25519PrivateKey.generate())
                shown = {**shown, "proposal_sha256": base.intake_proposal.digest(stored)}
                self.assertEqual(stored["blockers"], [])
                detail = await self.blocked(shown, verify.POLICY_ID, "재검증")
                self.assertIn(verify.MISMATCH, detail)

    async def test_unreadable_trust_configuration_blocks_instead_of_passing(self):
        for name, content in (("JSON 아님", "{"), ("목록 형식", json.dumps(["release-key"]))):
            with self.subTest(name):
                await self.asyncSetUp()
                shown = await self.open_repository("low", prov.attestation(self.signer))
                self.key_file.write_text(content, encoding="utf-8")
                await self.blocked(shown, "신뢰 키를 확인할 수 없습니다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
