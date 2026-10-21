"""RM-03: registry-bound location review; real adapters with DB/registry doubles only."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gateway"))
from app import core, registry, residency, review  # noqa: E402

PACK = json.loads((ROOT / "registry/data_residency.json").read_text())["residency"]
LOCATION = {"processing_countries": ["US"], "storage_countries": ["US"],
            "processor": "provider", "evidence_ref": "review-document", "transfer_basis": "approved basis"}
SPEC = {"deployment": "provider", "intake_id": "00000000-0000-0000-0000-000000000069",
        "endpoint": "https://service.example/mcp", "residency": LOCATION}


def reviewed(spec=None, pack=None):
    spec = copy.deepcopy(SPEC if spec is None else spec)
    spec["residency_review"] = {"reviewed_by": "independent-admin", "reviewed_at": "2026-10-21T00:00:00Z",
        "approval_sha256": residency.transfer_review_digest("service", spec, spec["residency"], pack or PACK)}
    return spec


def targets(spec, pack=PACK, destinations=()):
    cls = SimpleNamespace(server="service", data_class="nonimportant", destinations=destinations)
    return residency.facts(spec, {"jurisdiction_pack_enabled": True}, cls, pack)["targets"]


class TransferReviewTest(unittest.TestCase):
    def test_only_current_review_is_reusable(self):
        self.assertFalse(targets(SPEC)[0]["transfer_reviewed"])
        self.assertTrue(targets(reviewed())[0]["transfer_reviewed"])
        old = reviewed()
        del old["residency_review"]["approval_sha256"]
        self.assertFalse(targets(old)[0]["transfer_reviewed"])

    def test_each_location_field_invalidates_review(self):
        for key, value in {"processing_countries": ["JP"], "storage_countries": ["KR"],
                           "processor": "new", "evidence_ref": "new", "transfer_basis": "new"}.items():
            spec = reviewed()
            spec["residency"][key] = value
            with self.subTest(key=key):
                self.assertFalse(targets(spec)[0]["transfer_reviewed"])

    def test_provider_identity_and_policy_revision_invalidate_review(self):
        for key, value in {"endpoint": "https://other.example/mcp", "intake_id": "replacement",
                           "deployment": "internal"}.items():
            spec = reviewed()
            spec[key] = value
            with self.subTest(key=key):
                self.assertFalse(targets(spec)[0]["transfer_reviewed"])
        self.assertFalse(targets(reviewed(), {**PACK, "version": "new"})[0]["transfer_reviewed"])
        self.assertFalse(targets(reviewed(), {})[0]["transfer_reviewed"])
        cls = SimpleNamespace(server="other", data_class="nonimportant", destinations=[])
        self.assertFalse(residency.facts(reviewed(), {}, cls, PACK)["targets"][0]["transfer_reviewed"])

    def test_blank_or_missing_evidence_cannot_be_reviewed(self):
        for field in LOCATION:
            spec = copy.deepcopy(SPEC)
            spec["residency"][field] = [] if field.endswith("countries") else "  "
            with self.subTest(field=field):
                self.assertFalse(targets(reviewed(spec))[0]["transfer_reviewed"])
        for marker in (None, [], "approved", {"approval_sha256": ""}):
            spec = {**SPEC, "residency_review": marker}
            self.assertFalse(targets(spec)[0]["transfer_reviewed"])

    def test_review_does_not_propagate_to_tool_destinations(self):
        result = targets(reviewed(), destinations=[SimpleNamespace(host="other.example", external=True)])
        self.assertTrue(result[0]["transfer_reviewed"])
        self.assertNotIn("transfer_reviewed", result[1])


class TransferReviewRouteTest(unittest.IsolatedAsyncioTestCase):
    async def run_review(self, *, independent_error=None, pack=PACK):
        doc = {"servers": {"service": copy.deepcopy(SPEC)}, "history": []}
        with patch.object(registry, "runtime", return_value=doc), \
             patch.object(core.db, "fetch_one", AsyncMock(return_value={"submitted_by": "applicant"})), \
             patch.object(review, "require_independent", AsyncMock(side_effect=independent_error)) as independent, \
             patch.object(review, "record_event", AsyncMock()) as event, \
             patch.object(registry, "save_runtime") as save, \
             patch.object(registry, "sync", AsyncMock()), \
             patch.object(residency, "load_pack", return_value=pack):
            if independent_error:
                with self.assertRaises(ValueError):
                    await core.review_server_residency("service", LOCATION, "applicant")
                save.assert_not_called()
                self.assertNotIn("residency_review", doc["servers"]["service"])
                event.assert_not_awaited()
            else:
                await core.review_server_residency("service", LOCATION, "independent-admin")
                self.assertEqual(independent.await_args.args[3:5], ("independent-admin", "applicant"))
                binding = doc["servers"]["service"]["residency_review"]["approval_sha256"]
                self.assertEqual(doc["history"][-1]["approval_sha256"], binding)
                self.assertEqual(event.await_args.kwargs["scope"]["approval_sha256"], binding)
        return doc["servers"]["service"]

    async def test_independent_route_stamps_binding_and_audit(self):
        spec = await self.run_review()
        self.assertTrue(targets(spec)[0]["transfer_reviewed"])

    async def test_self_review_cannot_create_grant(self):
        await self.run_review(independent_error=ValueError("independent reviewer required"))

    async def test_missing_pack_can_record_location_but_cannot_grant_exemption(self):
        spec = await self.run_review(pack={})
        self.assertFalse(targets(spec)[0]["transfer_reviewed"])

    async def test_audit_failure_cannot_install_review(self):
        doc = {"servers": {"service": copy.deepcopy(SPEC)}, "history": []}
        with patch.object(registry, "runtime", return_value=doc), \
             patch.object(core.db, "fetch_one", AsyncMock(return_value={"submitted_by": "applicant"})), \
             patch.object(review, "require_independent", AsyncMock()), \
             patch.object(review, "record_event", AsyncMock(side_effect=RuntimeError("audit unavailable"))), \
             patch.object(registry, "save_runtime") as save, \
             patch.object(registry, "sync", AsyncMock()) as sync, \
             patch.object(residency, "load_pack", return_value=PACK):
            with self.assertRaisesRegex(RuntimeError, "audit unavailable"):
                await core.review_server_residency("service", LOCATION, "independent-admin")
        save.assert_not_called()
        sync.assert_not_awaited()
        self.assertFalse(targets(doc["servers"]["service"])[0]["transfer_reviewed"])
        self.assertEqual(doc["history"], [])

    async def test_registry_failure_always_has_prior_audit(self):
        for failing in ("save", "sync"):
            doc = {"servers": {"service": copy.deepcopy(SPEC)}, "history": []}
            events = []

            async def record(*args, **kwargs):
                events.append("audit")

            def save(_doc):
                events.append("save")
                self.assertEqual(events[0], "audit")
                if failing == "save":
                    raise RuntimeError("save failed")

            async def sync():
                events.append("sync")
                self.assertEqual(events[0], "audit")
                raise RuntimeError("sync failed")

            with self.subTest(failing=failing), \
                 patch.object(registry, "runtime", return_value=doc), \
                 patch.object(core.db, "fetch_one", AsyncMock(return_value={"submitted_by": "applicant"})), \
                 patch.object(review, "require_independent", AsyncMock()), \
                 patch.object(review, "record_event", record), \
                 patch.object(registry, "save_runtime", save), patch.object(registry, "sync", sync), \
                 patch.object(residency, "load_pack", return_value=PACK):
                with self.assertRaisesRegex(RuntimeError, "failed"):
                    await core.review_server_residency("service", LOCATION, "independent-admin")
            self.assertEqual(events[0], "audit")


if __name__ == "__main__":
    unittest.main()
