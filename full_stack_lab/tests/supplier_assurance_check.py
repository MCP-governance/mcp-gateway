"""Supplier evidence approval, support lapse, and registry export checks."""
from __future__ import annotations

import asyncio
import csv
import io
import json
from datetime import date, datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
from app import supplier_assurance
try:
    from fastapi import HTTPException
    from app import agent_service
except ModuleNotFoundError:
    HTTPException = None
    agent_service = None


class SupplierAssuranceCheck(unittest.TestCase):
    def setUp(self):
        self.valid = {
            "legal_entity": "Example Provider Ltd.",
            "supplier_contact": "support@example.test",
            "security_contact": "security@example.test",
            "support_end": "2030-12-31",
            "vulnerability_policy_url": "https://example.test/security/policy",
            "subprocessors": "미확인",
            "sbom_submitted": True,
            "vex_submitted": False,
            "contract_basis_ref": "DPA-2026-17",
            "exit_strategy": "연결 해제 및 자격 회수",
        }

    def test_all_required_fields_and_https_policy_are_required(self):
        self.assertEqual(supplier_assurance.validate(self.valid, today=date(2026, 10, 20)), [])
        errors = supplier_assurance.validate({**self.valid, "security_contact": "", "vulnerability_policy_url": "http://example.test/policy"},
                                             today=date(2026, 10, 20))
        self.assertTrue(any("보안 연락처" in error for error in errors))
        self.assertTrue(any("HTTPS" in error for error in errors))
        self.assertTrue(any("문자열" in error for error in supplier_assurance.validate({**self.valid, "legal_entity": True})))

    def test_elapsed_support_is_rejected_and_expiry_is_day_after_date(self):
        self.assertTrue(any("지원 종료일이 지났습니다" in error for error in
                            supplier_assurance.validate({**self.valid, "support_end": "2026-10-19"}, today=date(2026, 10, 20))))
        self.assertEqual(supplier_assurance.support_expiry("2026-10-19"),
                         datetime(2026, 10, 20, tzinfo=timezone.utc))

    def test_auto_renewal_stops_at_support_expiry(self):
        until = datetime(2026, 12, 1, tzinfo=timezone.utc)
        self.assertEqual(supplier_assurance.renewal_until(until, 90, "2026-12-31"),
                         datetime(2027, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(supplier_assurance.renewal_until(datetime(2027, 1, 1, tzinfo=timezone.utc), 90, "2026-12-31"),
                         datetime(2027, 1, 1, tzinfo=timezone.utc))

    @unittest.skipIf(agent_service is None, "게이트웨이 이미지 의존성이 없어 승인 경로는 건너뜀")
    def test_approval_endpoint_holds_when_assurance_is_missing(self):
        async def run():
            with patch.object(agent_service, "current_identity", new=AsyncMock(return_value={"roles": ["admin"], "principal": "admin"})), \
                    patch.object(agent_service.review, "lapse_expired_acceptances", new=AsyncMock()), \
                    patch.object(agent_service.db, "fetch_one", new=AsyncMock(return_value=None)):
                with self.assertRaises(HTTPException) as raised:
                    await agent_service.approve_mcp_request("00000000-0000-0000-0000-000000000001", None, None)
                self.assertEqual(raised.exception.status_code, 409)
                # D-189 추가 판단 3: 공급자 정보는 선택 입력이다. 비어 있어도 보류 사유가 아니며 승인은 다음 관문으로 간다.
                self.assertNotIn("공급자 법인명", raised.exception.detail)
                self.assertNotIn("취약점 공개 정책 주소", raised.exception.detail)
                self.assertIn("격리 검증을 통과한 요청만 승인할 수 있습니다", raised.exception.detail)
        asyncio.run(run())

    @unittest.skipIf(agent_service is None, "게이트웨이 이미지 의존성이 없어 승인 경로는 건너뜀")
    def test_approval_without_body_returns_korean_missing_field_reason(self):
        async def run():
            with patch.object(agent_service, "current_identity", new=AsyncMock(return_value={"roles": ["admin"], "principal": "admin"})), \
                    patch.object(agent_service.review, "lapse_expired_acceptances", new=AsyncMock()), \
                    patch.object(agent_service.db, "fetch_one", new=AsyncMock(return_value=None)):
                with self.assertRaises(HTTPException) as raised:
                    await agent_service.approve_mcp_request("00000000-0000-0000-0000-000000000001", None, None)
                self.assertEqual(raised.exception.status_code, 409)
                self.assertIn("승인할 수 있습니다", raised.exception.detail)
                self.assertNotIn("공급자 법인명", raised.exception.detail)
        asyncio.run(run())

    def test_items_not_received_are_named_unconfirmed_and_never_recorded_as_provided(self):
        self.assertEqual(supplier_assurance.unconfirmed({}), list(supplier_assurance.ASSURANCE_FIELDS))
        self.assertEqual(supplier_assurance.unconfirmed(self.valid), ["subprocessors"])
        # false is an answer ("not submitted"); an empty string and the default "미확인" are not.
        self.assertEqual(supplier_assurance.unconfirmed({"vex_submitted": False, "legal_entity": " ", "subprocessors": "미확인"}).count("vex_submitted"), 0)
        runtime = {"servers": {"alpha": {"intake_id": "i-a", "display_name": "Alpha",
                                         "supplier_assurance": {"legal_entity": "Example Provider Ltd.", "vex_submitted": False}}}}
        row = supplier_assurance.export_rows(runtime)[0]
        self.assertEqual((row["legal_entity"], row["vex_submitted"]), ("Example Provider Ltd.", False))
        for key in ("supplier_contact", "security_contact", "support_end", "vulnerability_policy_url", "subprocessors",
                    "sbom_submitted", "contract_basis_ref", "exit_strategy"):
            self.assertEqual(row[key], supplier_assurance.UNCONFIRMED, key)
        self.assertEqual(supplier_assurance.UNCONFIRMED, "확인 안 됨")
        self.assertTrue(supplier_assurance.matches_registry(runtime, supplier_assurance.export_rows(runtime)))

    @unittest.skipIf(agent_service is None, "게이트웨이 이미지 의존성이 없어 승인 경로는 건너뜀")
    def test_approval_form_defaults_do_not_claim_a_submission(self):
        blank = agent_service.IntakeApproval()
        self.assertEqual((blank.sbom_submitted, blank.vex_submitted, blank.subprocessors), (None, None, "미확인"))
        self.assertEqual(supplier_assurance.unconfirmed({k: v for k, v in blank.model_dump().items()
                                                         if k in supplier_assurance.ASSURANCE_FIELDS and v is not None}),
                         list(supplier_assurance.ASSURANCE_FIELDS))

    def test_json_and_csv_exports_match_runtime_ledger_and_hash(self):
        runtime = {"servers": {
            "zeta": {"intake_id": "intake-z", "display_name": "Zeta", "supplier": "Zeta Ltd.",
                     "endpoint": "https://zeta.test/mcp", "source_url": "https://zeta.test",
                     "license": "MIT", "valid_until": "2030-12-31T00:00:00+00:00",
                     "supplier_assurance": self.valid},
            "reviewed": {"display_name": "Reviewed"},
            "alpha": {"intake_id": "intake-a", "display_name": "Alpha", "supplier_assurance": self.valid},
        }}
        json_bytes, json_digest = supplier_assurance.export_json(runtime)
        payload = json.loads(json_bytes)
        self.assertEqual(payload["sha256"], json_digest)
        self.assertTrue(supplier_assurance.matches_registry(runtime, payload["servers"]))
        self.assertEqual([row["server_id"] for row in payload["servers"]], ["alpha", "zeta"])
        csv_bytes, csv_digest = supplier_assurance.export_csv(runtime)
        self.assertEqual(csv_digest, json_digest)
        rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
        self.assertTrue(supplier_assurance.matches_registry(runtime, rows))
        self.assertEqual(rows[1]["legal_entity"], "Example Provider Ltd.")
        self.assertEqual(rows[1]["sbom_submitted"], "True")
        self.assertEqual(rows[1]["vex_submitted"], "False")


if __name__ == "__main__":
    unittest.main()
