"""Check the compliance reference set: notes, anchors, provenance hashes, distribution rules, catalog links, aggregates.

Run from the repository root:  python -B -X utf8 research/llm-wiki/tools/check_compliance.py [--strict]
Errors exit 1. `--strict` also fails on warnings (local-only files missing on this PC, optional fields).
Anchor matching is whitespace/case-insensitive and tolerant of hyphenated line breaks, quote variants and dashes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

WIKI = Path(__file__).resolve().parents[1]
REPO = WIKI.parents[1]
NOTES = WIKI / "analysis/compliance/notes"
CATALOG = WIKI / "catalogs/papers.json"
POLICIES = WIKI / "threats/extracted/policies.json"

REQUIRED = ["id", "title", "issuer", "jurisdiction", "instrument_type", "binding", "status", "key_dates", "language", "summary_ko", "provisions",
            "limitations_ko", "license_notice", "distribution", "distribution_reason", "official_page_url", "reading_scope_ko"]
PROV_REQUIRED = ["ref", "topic_ko", "obligation_ko", "actor", "anchor", "gateway_control_ko", "pol_ids", "theme", "strength"]
THEMES = {"human_oversight", "logging_records", "transparency_labelling", "data_protection_lawful_basis", "data_minimisation_retention_deletion",
          "cross_border_transfer", "automated_decision_rights", "security_risk_management", "secure_development_supply_chain", "incident_reporting",
          "access_control_identity", "third_party_management", "risk_impact_assessment", "governance_accountability", "testing_red_teaming_robustness",
          "agentic_ai", "scope_applicability", "penalties_enforcement", "other"}
STRENGTHS = {"mandatory", "recommended", "informative"}
ACTORS = {"provider", "deployer", "importer", "distributor", "controller", "processor", "operator", "authority", "any"}
INSTRUMENTS = {"statute", "regulation", "directive", "decree", "executive_order", "regulator_guidance", "framework", "standard", "code_of_practice",
               "national_standard", "draft"}
DISTRIBUTION = {"public-under-license", "local-only"}
POL_RE = re.compile(r"^POL-(0[1-9]|[1-4][0-9]|50)$")


def norm(text: str) -> str:
    text = text.replace("­", "").replace("‐", "-").replace("‑", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"-\s*\n\s*", "", text)
    text = text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", "", text).lower()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ignored(path: Path) -> bool:
    try:
        run = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", str(path)], capture_output=True)
        return run.returncode == 0
    except OSError:
        return True


def check(strict: bool) -> int:
    errors, warnings = [], []
    policies = set()
    if POLICIES.exists():
        for row in json.loads(POLICIES.read_text(encoding="utf-8"))["policies"]:
            if row.get("sheet") == "(본)정책 최종본" and str(row.get("source_id", "")).startswith("POL-"):
                policies.add(row["source_id"])
    catalog = {e["id"]: e for e in json.loads(CATALOG.read_text(encoding="utf-8"))}
    notes = sorted(NOTES.glob("*.json"))
    totals = {"notes": len(notes), "provisions": 0, "public": 0, "local_only": 0, "local_missing": 0}

    for path in notes:
        note = json.loads(path.read_text(encoding="utf-8"))
        nid = note.get("id", path.stem)
        where = f"{nid}"
        if nid != path.stem:
            errors.append(f"{where}: id differs from file name {path.name}")
        for key in REQUIRED:
            if note.get(key) in (None, "", []):
                (errors if key not in ("official_page_url", "reading_scope_ko", "distribution_reason") else warnings).append(f"{where}: missing {key}")
        if note.get("distribution") not in DISTRIBUTION:
            errors.append(f"{where}: distribution {note.get('distribution')!r} invalid")
        if note.get("instrument_type") not in INSTRUMENTS:
            errors.append(f"{where}: instrument_type {note.get('instrument_type')!r} invalid")
        base = (WIKI / "sources/compliance" / nid) if note.get("distribution") == "public-under-license" else (WIKI / "local-sources/compliance" / nid)
        totals["public" if note.get("distribution") == "public-under-license" else "local_only"] += 1
        if note.get("distribution") == "public-under-license":
            if len(note.get("license_notice", "")) < 40:
                errors.append(f"{where}: public document needs a license_notice that records the reuse evidence")
        else:
            if not ignored(WIKI / "local-sources/compliance" / nid / "provenance.json"):
                errors.append(f"{where}: local-only directory is not git-ignored")
            if (WIKI / "sources/compliance" / nid).exists():
                errors.append(f"{where}: local-only document also exists under sources/compliance")
        prov_path = base / "provenance.json"
        extract = ""
        if not prov_path.exists():
            if note.get("distribution") == "local-only":
                warnings.append(f"{where}: local-only files absent on this PC ({prov_path.relative_to(WIKI)}) — re-acquire from provenance in the catalog")
                totals["local_missing"] += 1
            else:
                errors.append(f"{where}: missing {prov_path.relative_to(WIKI)}")
        else:
            prov = json.loads(prov_path.read_text(encoding="utf-8"))
            original = base / prov["original"]
            if not original.exists():
                errors.append(f"{where}: original missing {prov['original']}")
            elif sha256(original) != prov["sha256"]:
                errors.append(f"{where}: original sha256 differs from provenance")
            ext = base / prov["extract"]
            if ext.exists():
                extract = norm(ext.read_text(encoding="utf-8").split("\n---\n", 1)[-1])
            else:
                errors.append(f"{where}: extract missing {prov['extract']}")
        provisions = note.get("provisions", [])
        totals["provisions"] += len(provisions)
        if len(provisions) < 6:
            errors.append(f"{where}: fewer than 6 provisions")
        for i, prov_item in enumerate(provisions):
            label = f"{where}[{i}] {prov_item.get('ref')}"
            for key in PROV_REQUIRED:
                if key not in prov_item or (prov_item[key] in (None, "") and key != "pol_ids"):
                    errors.append(f"{label}: missing {key}")
            if prov_item.get("theme") not in THEMES:
                errors.append(f"{label}: theme {prov_item.get('theme')!r} invalid")
            if prov_item.get("strength") not in STRENGTHS:
                errors.append(f"{label}: strength {prov_item.get('strength')!r} invalid")
            if prov_item.get("actor") not in ACTORS:
                errors.append(f"{label}: actor {prov_item.get('actor')!r} invalid")
            for pid in prov_item.get("pol_ids", []):
                if not POL_RE.match(pid) or (policies and pid not in policies):
                    errors.append(f"{label}: unknown policy id {pid}")
            anchor = prov_item.get("anchor", "")
            if not 12 <= len(anchor) <= 220:
                errors.append(f"{label}: anchor length {len(anchor)} outside 12-220")
            elif extract and norm(anchor) not in extract:
                errors.append(f"{label}: anchor not found in extract: {anchor[:60]!r}")
            if len(prov_item.get("obligation_ko", "")) > 400:
                errors.append(f"{label}: obligation_ko longer than 400 characters")
        entry = catalog.get(nid)
        if entry is None:
            errors.append(f"{where}: missing from catalogs/papers.json")
        else:
            for rel in entry.get("originals", []) + entry.get("extracts", []):
                if note.get("distribution") == "public-under-license" and not (WIKI / rel).exists():
                    errors.append(f"{where}: catalog path missing {rel}")
            if not (WIKI / "papers" / f"{nid}.md").exists():
                errors.append(f"{where}: papers/{nid}.md missing")

    requirements = WIKI / "analysis/compliance/requirements.json"
    if requirements.exists():
        data = json.loads(requirements.read_text(encoding="utf-8"))
        rows = data.get("requirements", data) if isinstance(data, dict) else data
        if len(rows) != totals["provisions"]:
            errors.append(f"requirements.json has {len(rows)} rows but notes contain {totals['provisions']} provisions — run build_compliance_matrix.py")
    else:
        errors.append("analysis/compliance/requirements.json missing — run build_compliance_matrix.py")
    if not (WIKI / "analysis/compliance/README.md").exists():
        errors.append("analysis/compliance/README.md missing")

    print(json.dumps(totals, ensure_ascii=False))
    for message in warnings:
        print("WARNING:", message)
    for message in errors:
        print("ERROR:", message)
    print(f"compliance check: {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors or (strict and warnings) else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    sys.exit(check(parser.parse_args().strict))
