"""DEV-69 pure checks; --gateway adds real adapter imports with AsyncMock DB doubles.

Run from full_stack_lab: python tests/data_residency_check.py [--gateway]
No MCP server, database, stack, or credentials are created.
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gateway"))
from app import residency  # noqa: E402

GATEWAY = "--gateway" in sys.argv
if GATEWAY:
    sys.argv.remove("--gateway")

PACK = json.loads((ROOT / "registry/data_residency.json").read_text(encoding="utf-8"))["residency"]
LOCATION = {"processing_countries": ["KR"], "storage_countries": ["KR"],
            "processor": "조직", "evidence_ref": "배치 문서", "transfer_basis": ""}


class LocationTest(unittest.TestCase):
    def test_iso_codes_and_normalization(self):
        self.assertEqual(len(residency.COUNTRIES), 249)
        value = residency.normalize({**LOCATION, "processing_countries": ["US", "KR", "US"]})
        self.assertEqual(value["processing_countries"], ["KR", "US"])
        for bad in (["ZZ"], ["kr"], ["USA"], ["UK"], "KR", [None]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                residency.normalize({**LOCATION, "storage_countries": bad})

    def test_unknown_fields_and_wrong_shapes_refused(self):
        for value in ({"country": "KR"}, {"processor": 12}, {"evidence_ref": "a" * 501}, ["KR"]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                residency.normalize(value)

    def test_internal_uses_machine_location_provider_never_does(self):
        organization = {"machine_location": LOCATION}
        provider = {"deployment": "provider"}
        self.assertEqual(residency.location(provider, organization)["processing_countries"], [])
        self.assertEqual(residency.location({"deployment": "internal", "residency": {"processing_countries": ["US"]}}, organization), LOCATION)

    def test_unknown_machine_location_is_not_assumed_domestic(self):
        self.assertEqual(residency.location({"deployment": "internal"}, {})["processing_countries"], [])

    def test_downstream_is_separate_from_server_location(self):
        cls = SimpleNamespace(server="service", data_class="nonimportant", destinations=[SimpleNamespace(host="outside.example", external=True)])
        organization = {"machine_location": LOCATION}
        value = residency.facts({"deployment": "internal"}, organization, cls, PACK)
        self.assertEqual(value["targets"][0]["processing_countries"], ["KR"])
        self.assertEqual(value["targets"][1]["processing_countries"], [])
        organization["destination_locations"] = {"outside.example": {**LOCATION, "processing_countries": ["US"]}}
        changed = residency.facts({"deployment": "internal"}, organization, cls, PACK)
        self.assertEqual(changed["targets"][1]["processing_countries"], ["US"])
        self.assertNotEqual(residency.sha256(value), residency.sha256(changed))

    def test_rendered_pack_and_ledger(self):
        residency.validate_pack(PACK)
        self.assertEqual(json.loads((ROOT / "opa/residency.json").read_text(encoding="utf-8"))["residency"], PACK)
        ledger = json.loads((ROOT / "opa/policy_ledger.json").read_text(encoding="utf-8"))["policy_ledger"]
        priorities = [entry["priority"] for entry in ledger.values()]
        self.assertEqual(len(priorities), len(set(priorities)))
        self.assertEqual(ledger["P-RESIDENCY-001"]["outcome"], "차단")
        self.assertEqual(ledger["P-RESIDENCY-002"]["outcome"], "추가 승인")

    def test_pack_load_failure_mismatch_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            rendered, source = Path(directory) / "opa.json", Path(directory) / "source.json"
            self.assertEqual(residency.load_pack(rendered, source), {})
            rendered.write_text(json.dumps({"residency": PACK}), encoding="utf-8")
            source.write_text("{}", encoding="utf-8")
            self.assertEqual(residency.load_pack(rendered, source), {})
            source.write_bytes(rendered.read_bytes())
            self.assertEqual(residency.load_pack(rendered, source), PACK)
            rendered.write_text("broken", encoding="utf-8")
            self.assertEqual(residency.load_pack(rendered, source), {})

    def test_pack_rejects_incomplete_and_invalid_rules(self):
        for change in ({"rules": {}}, {"home_countries": []}, {"rules": {**PACK["rules"], "important": {"*": "maybe"}}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                residency.validate_pack({**PACK, **change})


if GATEWAY:
    # Dependency/import failure must exit nonzero in the appliance, never silently skip.
    from app import classify, core, pac, registry, review
    from app.agent_service import IntakeRegistration, RemoteContractReview
    from app.main import RegistryRegister, ResidencyReview

    class GatewayTest(unittest.IsolatedAsyncioTestCase):
        async def test_both_boundaries_validate_iso(self):
            registration = {"server_id": "residency", "endpoint": "https://service.example/mcp", "catalog_hash": "a" * 64,
                            "tools": {"search": "r"}, "data_class": "nonimportant", "valid_days": 30,
                            "tool_reviews": {"search": {"purpose": "자료 검색", "asset": "자료"}}, "residency": LOCATION}
            for model in (IntakeRegistration, RemoteContractReview, RegistryRegister):
                value = {**registration}
                if model is RegistryRegister:
                    value["display_name"] = "위치 서버"
                if model is RemoteContractReview:
                    value.update(allowed_principals=["employee"], review_note="자료 검색을 위한 처리 위치 검토")
                self.assertEqual(model(**value).residency, LOCATION)
                with self.assertRaises(ValueError):
                    model(**{**value, "residency": {**LOCATION, "processing_countries": ["ZZ"]}})

        async def test_residency_review_model_requires_complete_valid_location(self):
            value = ResidencyReview(**LOCATION)
            self.assertEqual(value.model_dump(), LOCATION)
            for change in ({"processing_countries": ["ZZ"]}, {"storage_countries": []},
                           {"evidence_ref": ""}, {"processor": " "}):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    ResidencyReview(**{**LOCATION, **change})

        async def test_residency_review_requires_independent_admin(self):
            doc = {"servers": {"residency": {"intake_id": "00000000-0000-0000-0000-000000000069",
                                               "deployment": "provider", "residency": LOCATION}},
                   "contracts": {}, "usage_relationships": [], "history": []}
            with patch.object(registry, "runtime", return_value=doc), \
                 patch.object(core.db, "fetch_one", AsyncMock(return_value={"submitted_by": "applicant"})), \
                 patch.object(review, "require_independent", AsyncMock(side_effect=review.NotIndependent)), \
                 patch.object(registry, "save_runtime") as save, patch.object(registry, "sync", AsyncMock()):
                with self.assertRaises(review.NotIndependent):
                    await core.review_server_residency("residency", LOCATION, "applicant")
                save.assert_not_called()
                self.assertEqual(review.require_independent.await_args.args[:5],
                                 ("residency-review", "server", "residency", "applicant", "applicant"))

        async def test_residency_review_updates_facts_and_preserves_remote_registration(self):
            old = {**LOCATION, "storage_countries": ["US"]}
            remote_registration = {"residency": old, "tools": {"search": "r"}}
            intake = {"submitted_by": "applicant", "evidence": {"remote_contract": {"registration": remote_registration}}}
            doc = {"servers": {"residency": {"intake_id": "00000000-0000-0000-0000-000000000069",
                                               "deployment": "provider", "residency": old}},
                   "contracts": {"residency": {"tools": {"search": "a" * 64}}},
                   "usage_relationships": [], "history": []}
            contract = copy.deepcopy(doc["contracts"]["residency"])
            with patch.object(registry, "runtime", return_value=doc), \
                 patch.object(core.db, "fetch_one", AsyncMock(return_value=intake)), \
                 patch.object(review, "require_independent", AsyncMock()) as independent, \
                 patch.object(review, "record_event", AsyncMock()) as event, \
                 patch.object(registry, "save_runtime") as save, patch.object(registry, "sync", AsyncMock()) as sync:
                result = await core.review_server_residency("residency", LOCATION, "reviewer")
            spec = doc["servers"]["residency"]
            cls = SimpleNamespace(server="residency", data_class="nonimportant", destinations=[])
            facts = residency.facts(spec, {}, cls, PACK)
            self.assertEqual(facts["targets"][0]["storage_countries"], ["KR"])
            self.assertEqual(spec["residency"], LOCATION)
            self.assertEqual(spec["residency_review"]["reviewed_by"], "reviewer")
            self.assertEqual(spec["residency_review"]["previous_sha256"], residency.sha256(old))
            self.assertEqual(doc["contracts"]["residency"], contract)
            self.assertEqual(intake["evidence"]["remote_contract"]["registration"], remote_registration)
            self.assertEqual(result["residency"], LOCATION)
            self.assertEqual(doc["history"][-1]["type"], "residency-reviewed")
            independent.assert_awaited_once()
            event.assert_awaited_once()
            save.assert_called_once_with(doc)
            sync.assert_awaited_once()

        async def test_remote_location_substitution_rejected_before_network(self):
            request = {"server_id": "residency", "endpoint": "https://service.example/mcp",
                       "intake_id": "00000000-0000-0000-0000-000000000069", "residency": LOCATION,
                       "data_class": "nonimportant"}
            approved_location = {**LOCATION, "storage_countries": ["US"]}
            contract = {"registration": {"residency": approved_location}, "allowed_principals": ["employee"]}
            intake = {"status": "APPROVED", "submitted_by": "employee", "reviewed_by": "admin",
                      "intake_kind": "remote-endpoint", "evidence": {"remote_contract": contract,
                      "remote_approval": {"actor": "admin", "review_digest": core.canonical_hash(contract)}}}
            with patch.object(core.db, "fetch_one", AsyncMock(return_value=intake)), \
                 patch.object(review, "same_person", AsyncMock(return_value=False)), \
                 patch.object(review, "intake_gate", AsyncMock(return_value={"blockers": []})), \
                 patch.object(core.upstream, "discover", AsyncMock()) as network:
                with self.assertRaisesRegex(ValueError, "다른 등록"):
                    await core.register_server(request, "admin")
                network.assert_not_awaited()

        async def test_adapter_binds_location_and_pack_in_existing_pac_digest(self):
            spec = {"deployment": "provider", "residency": LOCATION, "endpoint": "https://service.example/mcp"}
            cls = classify.Classification("residency", "search", "r", "r", resources=[classify.Resource("service", "data", "nonimportant")])
            principal = {"token": "employee", "user_id": "employee", "status": "active"}
            context = {"duplicate_in_flight": False, "execution_timeout_ms": 1000, "active_calls": 1, "recent_calls": 0}
            scope = {"allowed": True, "resources_allowed": True, "actions": ["r"]}
            with patch.object(registry, "server", return_value=spec), patch.object(registry, "catalog", return_value={}), \
                 patch.object(pac, "scope", return_value=scope), patch.object(pac, "capabilities", return_value={}), \
                 patch.object(pac.db, "fetch_one", AsyncMock(return_value=None)), patch.object(residency, "load_pack", return_value=PACK):
                async def build():
                    return await pac.build({"arguments": {}}, principal, cls, {"input_schema": {"type": "object"}}, {}, context, "request", "prod", None)
                original = await build()
                spec["residency"] = {**LOCATION, "storage_countries": ["US"]}
                changed = await build()
                self.assertNotEqual(pac.digest(original), pac.digest(changed))
                self.assertEqual(changed["facts"]["residency"]["targets"][0]["storage_countries"], ["US"])
                changed_pack = copy.deepcopy(PACK)
                changed_pack["version"] = "next"
                with patch.object(residency, "load_pack", return_value=changed_pack):
                    updated = await build()
                self.assertNotEqual(pac.digest(changed), pac.digest(updated))
                self.assertTrue("P-RESIDENCY-001".startswith(core.ALWAYS_ENFORCED))

        async def test_same_intake_cannot_replace_active_location(self):
            request = {"server_id": "residency", "endpoint": "https://service.example/mcp",
                       "source_url": "https://service.example/mcp", "commit_sha": "",
                       "intake_id": "00000000-0000-0000-0000-000000000069", "residency": LOCATION,
                       "data_class": "nonimportant"}
            contract = {"registration": {"residency": LOCATION}, "allowed_principals": ["employee"],
                        "valid_until": "2030-01-01T00:00:00+00:00"}
            intake = {"status": "APPROVED", "submitted_by": "employee", "reviewed_by": "admin",
                      "intake_kind": "remote-endpoint", "endpoint_url": request["endpoint"],
                      "evidence": {"remote_contract": contract,
                      "remote_approval": {"actor": "admin", "review_digest": core.canonical_hash(contract)}}}
            active = {"intake_id": request["intake_id"], "residency": {**LOCATION, "storage_countries": ["US"]}}
            with patch.object(core.db, "fetch_one", AsyncMock(return_value=intake)), \
                 patch.object(review, "same_person", AsyncMock(return_value=False)), \
                 patch.object(review, "intake_gate", AsyncMock(return_value={"blockers": []})), \
                 patch.object(registry, "reviewed_servers", return_value={}), \
                 patch.object(registry, "runtime", return_value={"servers": {"residency": active}}), \
                 patch.object(core.upstream, "discover", AsyncMock()) as network:
                with self.assertRaisesRegex(ValueError, "새 도입 신청"):
                    await core.register_server(request, "admin")
                network.assert_not_awaited()


if __name__ == "__main__":
    unittest.main(verbosity=2)
