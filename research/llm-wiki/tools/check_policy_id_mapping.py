"""Check analysis/drive-curation/policy-id-mapping.json against the workbook extract, pac15.rego and the policy ledger."""
import json
import sys

import build_policy_id_mapping as b


def check():
    errors, warnings = [], []

    def require(condition, message):
        if not condition:
            errors.append(message)

    data = json.loads(b.OUT.read_text(encoding="utf-8"))
    derived = b.derive()
    defs = b.runtime_definitions()
    by_pac, _ = b.ledger_by_pac()
    hashes = data["source_hashes"]
    require(hashes["workbook_extract_sha256"] == derived["workbook_extract_sha256"], "Workbook extract changed after mapping; review and rerun build_policy_id_mapping.py")
    if hashes["pac15_rego_sha256_lf"] != b.sha256(b.REPO / b.SOURCES["pac15"], True):
        warnings.append("pac15.rego changed after the runtime PAC judgements; review runtime-pac15 links")
    if hashes["policy_ledger_sha256_lf"] != b.sha256(b.REPO / b.SOURCES["ledger"], True):
        warnings.append("policy_ledger.json changed after mapping; ledger_policy_ids may be stale")

    require(data["number_collisions"]["items"] == derived["collisions"], "number_collisions differs from the workbook")
    require(data["number_collisions"]["count"] == len(derived["collisions"]), "number_collisions count mismatch")
    require(data["stale_cross_references"]["items"] == derived["stale"], "stale_cross_references differs from the workbook")
    for item in data["stale_cross_references"]["items"]:
        require(item["same_number_pol"]["pol_id"] in item["docs_counterpart_cite_resolves_to_pol"],
                f"Stale reference rule (PACnn means POL-nn) not confirmed by the docs counterpart: {item['in_policy']} {item['label']}")

    mappings = data["mappings"]
    ids = [m["policy_id"] for m in mappings]
    require(ids == list(derived["pol"]), "Mappings must list POL-01~50 in workbook order")
    require(len(set(ids)) == len(ids) == 50, "Duplicate or missing policy id")
    groups = {"PAC-01..PAC-15"}
    cur_counts, after_counts = {}, {}
    for m in mappings:
        pid = m["policy_id"]
        derived_link = derived["links"][pid]
        docs = [x for x in m["links"] if x["system"] == "pac50-docs"]
        original = [x for x in m["links"] if x["system"] == "pac24-original"]
        runtime = [x for x in m["links"] if x["system"] == "runtime-pac15"]
        require(len(docs) == (1 if derived_link["docs_pac_id"] else 0), f"Docs link presence: {pid}")
        for x in docs:
            require(x["id"] == derived_link["docs_pac_id"] and x["name_match"] == derived_link["docs_name_match"], f"Docs link id/name: {pid}")
            require(x["body_similarity"] == derived_link["docs_body_similarity"], f"Docs body similarity: {pid}")
            require((x["relationship"] == "equal-to") == (x["body_similarity"] == 1.0), f"equal-to only for identical bodies: {pid}")
            require(x["relationship"] in b.RELATIONSHIPS and x["relationship"] != "unreviewed", f"Docs relationship: {pid}")
        require(len(original) == (1 if "original_pac_id" in derived_link else 0), f"Original link presence: {pid}")
        for x in original:
            require(x["id"] == derived_link["original_pac_id"] and x["body_similarity"] == derived_link["original_body_similarity"], f"Original link: {pid}")
        in35 = pid in b.STATUS_35
        require(m["scope"] == ("technical_control_35" if in35 else "outside_35"), f"Scope: {pid}")
        require(("status_report" in m) == in35, f"status_report only for the 35 controls: {pid}")
        if in35:
            s = m["status_report"]
            cur_counts[s["current"]] = cur_counts.get(s["current"], 0) + 1
            after_counts[s["after_planned_development"]] = after_counts.get(s["after_planned_development"], 0) + 1
        else:
            require(not runtime and m["runtime_coverage"] == "not_assessed", f"Runtime links outside the 35 controls: {pid}")
        for x in runtime:
            require(x["relationship"] in b.RELATIONSHIPS[:6], f"Runtime relationship value: {pid} {x['id']}")
            require(x["id"] in defs or x["id"] in groups, f"Unknown runtime PAC {x['id']}: {pid}")
            members = [f"PAC-{n:02d}" for n in range(1, 16)] if x["id"] in groups else [x["id"]]
            require(x["ledger_policy_ids"] == sorted({p for k in members for p in by_pac.get(k, [])}), f"ledger_policy_ids: {pid} {x['id']}")
            require(bool(x["remarks"]), f"Runtime link without remarks: {pid} {x['id']}")
        if in35:
            expected = "none" if not runtime else ("equivalent" if all(x["relationship"] == "equivalent-to" for x in runtime) else "partial")
            require(m["runtime_coverage"] == expected, f"runtime_coverage: {pid}")
            require(any(g["kind"] == "no_runtime_pac" for g in m["gaps"]) == (expected == "none"), f"no_runtime_pac gap: {pid}")
            if expected == "none":
                require(bool(m.get("runtime_note")), f"No-PAC policy without a note: {pid}")
        require(any(g["kind"] == "docs_only_clause" for g in m["gaps"]) == any(x["relationship"] == "subset-of" for x in docs), f"docs_only_clause gap: {pid}")
    require(cur_counts == {"구현": 14, "일부 구현": 20, "미구현": 1}, f"Current status counts changed: {cur_counts}")
    require(after_counts == {"구현": 28, "일부 구현": 7}, f"Planned status counts changed: {after_counts}")
    require(data["summary"]["technical_control_35"] == 35, "Summary: technical control count")
    require(sorted(set(defs)) == [f"PAC-{n:02d}" for n in range(1, 16)], "pac15.rego must define PAC-01~15")
    print(json.dumps({"ok": not errors, "counts": {"policies": len(mappings), "number_collisions": len(derived["collisions"]),
                      "stale_cross_references": len(derived["stale"]), "status_current": cur_counts}, "warnings": warnings, "errors": errors},
                     ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(check())
