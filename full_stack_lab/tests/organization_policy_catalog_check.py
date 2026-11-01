"""Check policy catalog provenance and unavailable-data behavior without a service stack."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CatalogTests(unittest.TestCase):
    def test_generated_catalog_matches_original_identifiers_and_content(self):
        generator = load("console_catalog_generator", ROOT / "policy/tools/build_console_catalog.py")
        expected = generator.build()
        actual = json.loads(generator.OUTPUT.read_text(encoding="utf-8"))
        self.assertEqual(actual, expected)
        originals = json.loads((ROOT / "policy/source/sheet.json").read_text(encoding="utf-8"))["policies"]
        self.assertEqual(len(actual["policies"]), 90)
        self.assertEqual({p["id"] for p in actual["policies"]}, set(originals))
        for policy in actual["policies"]:
            self.assertEqual(policy["content"], originals[policy["id"]]["content"])
            self.assertNotIn("applied", policy)
            self.assertNotIn("status", policy)
            self.assertNotIn("note", policy)

    def test_rule_presence_agrees_with_existing_policy_trace(self):
        generator = load("catalog_generator_trace", ROOT / "policy/tools/build_console_catalog.py")
        trace = load("catalog_existing_trace", ROOT / "policy/tools/trace.py")
        sources, _ = trace.rule_sources()
        actual = generator.build()
        self.assertEqual({p["id"] for p in actual["policies"] if p["has_rule"]}, set(sources))

    def test_missing_and_invalid_catalog_are_unavailable_not_empty_success(self):
        reader = load("catalog_reader", ROOT / "full_stack_lab/gateway/app/organization_policy.py")
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            with patch.object(reader, "__file__", str(base / "organization_policy.py")):
                self.assertEqual(reader.catalog(), {"source_state": "unavailable", "policies": []})
                (base / "organization_policies.json").write_text('{"schema":1,"policies":null}', encoding="utf-8")
                self.assertEqual(reader.catalog()["source_state"], "unavailable")
                (base / "organization_policies.json").write_text('{"schema":1,"policies":[{}]}', encoding="utf-8")
                self.assertEqual(reader.catalog()["source_state"], "unavailable")
                (base / "organization_policies.json").write_text('{"schema":1,"policies":[]}', encoding="utf-8")
                self.assertEqual(reader.catalog()["source_state"], "available")


if __name__ == "__main__":
    unittest.main()
