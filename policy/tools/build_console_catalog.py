"""Build the read-only console catalog from policy sources; static evidence is not deployment evidence."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parent / "full_stack_lab/gateway/app/organization_policies.json"


def build():
    sheet_bytes = (ROOT / "source/sheet.json").read_bytes()
    classification_bytes = (ROOT / "source/classification.json").read_bytes()
    sheet = json.loads(sheet_bytes)["policies"]
    classes = json.loads(classification_bytes)["policies"]
    if set(sheet) != set(classes):
        raise ValueError("Policy sources contain different identifiers")
    rules, tests = set(), set()
    for path in (ROOT / "pac").glob("*.rego"):
        text = path.read_text(encoding="utf-8")
        if path.name.endswith("_test.rego"):
            tests.update("POL-" + n for n in re.findall(r"test_pol_(\d{3})_(?:pass|block)_", text))
        else:
            rules.update(a or b for a, b in re.findall(r'lib\.finding\("(POL-\d{3})"|"policy_id": "(POL-\d{3})"', text))
    policies = []
    for pid, source in sorted(sheet.items()):
        if not re.fullmatch(r"POL-\d{3}", pid):
            raise ValueError("Invalid policy identifier")
        classification = classes[pid]
        rule = source.get("rule") or {}
        candidates = sorted(set(re.findall(r"(?:MCP|PAC|P)-[A-Z0-9]+(?:-[A-Z0-9]+)*", classification.get("evidence", ""))))
        policies.append({"id": pid, "name": source["target"], "stage": source["stage"],
                         "content": source["content"], "condition": source["condition"],
                         "required_evidence": source.get("evidence", ""),
                         "pass_condition": rule.get("pass_condition", ""),
                         "block_condition": rule.get("block_condition", ""),
                         "category": classification["category"], "implementation": classification["enforced_by"],
                         "has_rule": pid in rules, "has_test_definition": pid in tests,
                         "candidate_rule_ids": candidates})
    return {"schema": 1, "source_sha256": hashlib.sha256(sheet_bytes).hexdigest(),
            "classification_sha256": hashlib.sha256(classification_bytes).hexdigest(), "policies": policies}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != rendered:
            raise SystemExit("Console policy catalog is out of date")
    else:
        OUTPUT.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
