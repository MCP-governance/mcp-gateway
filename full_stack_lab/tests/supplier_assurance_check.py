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
                self.assertIn("공급자 법인명", raised.exception.detail)
                self.assertIn("취약점 공개 정책 주소", raised.exception.detail)
        asyncio.run(run())

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
