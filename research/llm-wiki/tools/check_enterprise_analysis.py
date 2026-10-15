"""Check granular evidence links and hashes without inferring acceptance-test success."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def main():
    errors, warnings = [], []
    def require(ok, message):
        if not ok:
            errors.append(message)
    load = lambda name: json.loads((ROOT / "analysis" / name).read_text(encoding="utf-8-sig"))
    req = load("requirements.json")["records"]
    comps = load("competitor-mapping.json")["records"]
    cases = load("integration-cases.json")
    targets = load("mcp-candidates.json")
    experiments = json.loads((ROOT / "catalogs/experiments.json").read_text(encoding="utf-8-sig"))
    ids = {r["id"] for r in req}
    for name, rows in [("requirements",req),("comparison",comps),("integration",cases),("targets",targets)]:
        require(len({r["id"] for r in rows})==len(rows), "Duplicate ID: "+name)
    for r in req:
        require(bool(r["acceptance"]) and bool(r["negative_cases"]) and bool(r["gap"]), "Incomplete condition: "+r["id"])
        require(r["status"] in {"source_only","gap","partial","verified_unit","verified_field"}, "Unknown status: "+r["id"])
        if r["status"].startswith("verified"):
            require(bool(r["test_evidence"]), "Verified condition lacks test evidence: "+r["id"])
        for e in r["test_evidence"]:
            p = REPO / e["path"]
            require(p.is_file() and bool(e.get("symbol")) and bool(e.get("assertion_lines")), "Missing precise test anchor: "+r["id"])
            if p.is_file() and e.get("normalized_sha256"):
                require(hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == e["normalized_sha256"], "Test hash changed: "+e["path"])
            run = ROOT / e.get("run_evidence", "missing-run")
            require(run.is_file(), "Missing verification run: "+r["id"])
            if run.is_file():
                records = json.loads(run.read_text(encoding="utf-8")).get("records", [])
                require(any(x.get("path") == e["path"] and x.get("exit_code") == 0 and
                            x.get("source_normalized_sha256") == e.get("normalized_sha256") for x in records),
                        "Verification does not match test source: "+r["id"])
        for e in r["code_evidence"]:
            p=(REPO/e["path"]).resolve()
            require(p.is_relative_to(REPO) and p.is_file(), "Bad code path: "+e["path"])
            if p.is_file():
                raw=p.read_bytes()
                expected=e.get("normalized_sha256",e["sha256"])
                actual=hashlib.sha256(raw.replace(b"\r\n",b"\n") if "normalized_sha256" in e else raw).hexdigest()
                if actual!=expected and e["source_state"]=="worktree_modified":
                    warnings.append("Local worktree observation differs: "+e["path"])
                else:
                    require(actual==expected, "Code hash changed: "+e["path"])
                if actual == expected:
                    require(1<=e["line_start"]<=e["line_end"]<=len(raw.splitlines()), "Invalid code lines: "+e["path"])
                require(e["symbol_found"], "Missing symbol: "+e["path"])
    for r in comps:
        require(r["requirement_id"] in ids, "Orphan comparison: "+r["id"])
        require(bool(r["evidence_url"]) and bool(r["version_or_commit"]), "Missing version/source: "+r["id"])
        for p in r["evidence_paths"]:
            require((ROOT/p).is_file(), "Missing comparator excerpt: "+p)
    target_ids={r["id"] for r in targets}
    for r in experiments:
        require(r.get("target_id") in target_ids and r.get("self_written_mcp") is False, "Non-vendor/OSS target: "+r["id"])
        require(r["status"] in {"not_run", "blocked", "failed", "passed", "partial"}, "Unknown run status: "+r["id"])
        require((r["result"] is None) if r["status"] == "not_run" else isinstance(r["result"], dict) and bool(r["result"]),
                "Run status lacks a result or falsely claims execution: "+r["id"])
        require("wiki-fixture" not in json.dumps(r), "Superseded mock input: "+r["id"])
    for r in cases:
        require(r["status"] in {"not_run", "blocked", "failed", "passed", "partial"} and bool(r["expected"]) and bool(r["negative_case"]), "Missing integration condition: "+r["id"])
        require(bool(r.get("source_refs")) and bool(r.get("failure_fix")) and bool(r.get("procedure")), "Incomplete integration source/procedure: "+r["id"])
        if r["status"] != "not_run":
            require(bool(r.get("runtime_evidence") or r.get("test_evidence")), "Integration result lacks execution evidence: "+r["id"])
        for e in r.get("code_evidence", []):
            p = REPO / e["path"]
            require(p.is_file(), "Missing integration source: "+e["path"])
            if p.is_file():
                actual = hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                if actual != e["normalized_sha256"] and e["source_state"] == "worktree_modified":
                    warnings.append("Local integration observation differs: "+e["path"])
                else:
                    require(actual == e["normalized_sha256"], "Integration code hash changed: "+e["path"])
                    require(1 <= e["line_start"] <= e["line_end"] <= len(p.read_bytes().splitlines()), "Bad integration lines: "+e["path"])
    for name in ("reference-updates.json","skill-candidates.json"):
        for r in load(name):
            for key in ("metadata_evidence","source_evidence","license_evidence"):
                e=r.get(key)
                if isinstance(e,dict) and e.get("path"):
                    p=(ROOT/e["path"]).resolve()
                    require(p.is_relative_to(ROOT) and p.is_file(), "Missing source: "+e["path"])
                    if p.is_file():
                        require(hashlib.sha256(p.read_bytes()).hexdigest()==e["sha256"], "Source hash mismatch: "+e["path"])
    print(json.dumps({"ok":not errors,"requirements":len(req),"comparisons":len(comps),"integration_conditions":len(cases),
                      "real_mcp_targets":len(targets),"errors":errors,"warnings":sorted(set(warnings))},ensure_ascii=False,indent=2))
    return bool(errors)


if __name__=="__main__":
    sys.exit(main())
