"""Check Markdown evidence, provenance, licenses, links and experiment claims."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

from build_wiki import ROOT, markdown_files

REPO = ROOT.parents[1]


def check(ci_ignored_local_sources=False):
    errors, warnings, totals = [], [], {}

    def require(condition, message):
        if not condition:
            errors.append(message)

    def local_path(value, base=ROOT, optional=False, link=False):
        path = (base / unquote(value)).resolve()
        require(path.is_relative_to(REPO), f"Path outside repository: {value}")
        # 링크는 디렉터리를 가리킬 수 있다. 추적 파일이 있는 디렉터리만 인정해 빈 디렉터리와 없는 경로는 오류로 남긴다.
        tracked_dir = link and path.is_dir() and path.is_relative_to(REPO) and subprocess.run(
            ["git", "-C", str(REPO), "ls-files", "--", path.relative_to(REPO).as_posix()],
            capture_output=True).stdout.strip() != b""
        if not (path.is_file() or tracked_dir):
            if ci_ignored_local_sources and path.is_relative_to(ROOT / "local-sources"):
                warnings.append(f"Missing ignored local source: {path.relative_to(REPO)}")
            elif not optional:
                require(False, f"Missing local file: {value}")
        return path

    for name in ("README.md", "AGENTS.md", "CLAUDE.md", "papers/README.md", "solutions/README.md",
                 "experiments/README.md", "status/current.md", "status/backlog.md"):
        local_path(name)
    catalogs = {}
    for file in sorted((ROOT / "catalogs").glob("*.json")):
        try:
            records = json.loads(file.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError) as exc:
            errors.append(f"Cannot read {file.name}: {exc}")
            continue
        require(isinstance(records, list), f"Catalog must be a list: {file.name}")
        if not isinstance(records, list):
            continue
        catalogs[file.stem] = records
        totals[file.stem] = len(records)
        ids = [r.get("id") for r in records if isinstance(r, dict) and "id" in r]
        require(len(ids) == len(set(ids)), f"Duplicate ID: {file.name}")
        for record in records:
            require(isinstance(record, dict), f"Non-object catalog entry: {file.name}")
            if not isinstance(record, dict):
                continue
            if file.stem in ("papers", "solutions", "experiments"):
                for key in ("id", "title", "verification"):
                    require(bool(record.get(key)), f"Missing {key}: {file.name}/{record.get('id')}")
            for key in ("path", "page", "provenance"):
                if record.get(key):
                    local_path(record[key])
            for key in ("originals", "extracts"):
                for value in record.get(key, []):
                    target = value if isinstance(value, str) else value["path"]
                    local_path(target, optional=target.startswith("local-sources/"))
            for item in record.get("files", []):
                if isinstance(item, dict) and item.get("path"):
                    path = local_path(item["path"], optional=item["path"].startswith("local-sources/"))
                    if path.is_file() and item.get("sha256"):
                        require(hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"],
                                f"Provenance hash mismatch: {item['path']}")
    for name in ("policies", "wbs"):
        source = ROOT / f"threats/extracted/{name}.json"
        if not source.is_file():
            errors.append(f"Missing workbook extract: {source}")
            continue
        parsed = json.loads(source.read_text(encoding="utf-8"))
        path = local_path(parsed["source"])
        if path.is_file():
            require(hashlib.sha256(path.read_bytes()).hexdigest() == parsed["sha256"],
                    f"Workbook original hash mismatch: {name}")
        require(parsed["macros_executed"] is False, "Workbook macro execution flag must be false")
        require(parsed["formulas_recalculated"] is False, "Workbook recalculation flag must be false")
        if name == "policies":
            rows = [r for r in parsed["policies"] if r["sheet"] == "정책 최종본"]
            require(len(rows) == 24, "Expected 24 source control rows; review source version")
            require(len(catalogs.get("threats", [])) == len(rows), "Threat mapping is incomplete")
    for relative in ("sources/live/acquisition-2026-10-13.json", "solutions/evidence/manifest.json"):
        manifest = json.loads(local_path(relative).read_text(encoding="utf-8"))
        for record in manifest:
            entries = record.get("files", [record])
            for entry in entries:
                path = local_path(entry["path"])
                if path.is_file():
                    require(hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"],
                            f"Evidence hash mismatch: {entry['path']}")
        totals[relative.split('/')[0] + "_evidence_records"] = len(manifest)
    for record in catalogs.get("papers", []):
        require(record.get("distribution") in ("public-under-license", "local-only"),
                f"Unknown redistribution status: {record.get('id')}")
        if record.get("distribution") == "local-only":
            require(all(p.startswith("local-sources/") for p in record["originals"] + record["extracts"]),
                    f"Restricted full source outside ignored cache: {record['id']}")
    for record in catalogs.get("threats", []):
        require(record["verification"] == "static-candidate-mapping", "Mapping must retain candidate status")
        for evidence in record["code_candidates"]:
            path = local_path(evidence["path"], REPO)
            if path.is_file():
                actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                normalized = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                matches_observation = actual_hash == evidence["sha256"] or normalized == evidence.get("normalized_sha256")
                if not matches_observation and evidence.get("worktree_modified") and normalized == evidence.get("committed_sha256"):
                    warnings.append(f"Mapping records an unpublished local observation; clean HEAD baseline: {evidence['path']}")
                else:
                    require(matches_observation,
                            f"Code changed after mapping: {evidence['path']}; review and run map_threats.py")
        risk_ids = {risk["id"] for risk in catalogs.get("local-tool-risks", [])}
        require(set(record.get("local_tool_risk_ids", [])) <= risk_ids,
                f"Unknown local tool risk link: {record['id']}")
    policy_ids = {record["source_id"] for record in catalogs.get("threats", [])}
    for risk in catalogs.get("local-tool-risks", []):
        require(bool(risk.get("observation")) and bool(risk.get("required_control")) and bool(risk.get("remaining")),
                f"Local tool risk lacks evidence/control/limit: {risk.get('id')}")
        require(set(risk.get("source_controls", [])) <= policy_ids,
                f"Unknown source policy in local tool risk: {risk.get('id')}")
    review_path = ROOT / "analysis/local-tools/review.json"
    if review_path.is_file():
        review = json.loads(review_path.read_text(encoding="utf-8"))
        capabilities = json.loads(local_path("analysis/local-tools/tool-capabilities.json").read_text(encoding="utf-8"))
        require(len(capabilities) == review["tool_count"] == sum(review["counts"].values()), "Local tool count mismatch")
        require(len({item["id"] for item in capabilities}) == len(capabilities), "Duplicate local tool capability")
        for manifest in review["manifests"]:
            path = local_path(manifest["path"])
            require(hashlib.sha256(path.read_bytes()).hexdigest() == manifest["sha256"],
                    f"Local tool source changed after review: {manifest['path']}")
        for item in capabilities:
            canonical = json.dumps(item["schema"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            require(hashlib.sha256(canonical).hexdigest() == item["schema_sha256"], f"Tool schema hash mismatch: {item['id']}")
            require(bool(item["capability_tags"]) and isinstance(item["call_observed"], bool), f"Missing capability/call status: {item['id']}")
        totals["reviewed_local_tools"] = len(capabilities)

    # Raw copied source/extract links remain historical data, not wiki navigation.
    for file in ROOT.rglob("*.md"):
        rel = file.relative_to(ROOT)
        if rel.parts[0] in ("sources", "local-sources") or "evidence" in rel.parts:
            continue
        content = file.read_text(encoding="utf-8-sig")
        content = re.sub(r"```.*?```", "", content, flags=re.S)
        for match in re.finditer(r"!?\[[^\]]*\]\((<[^>]+>|[^\s)]+)(?:\s+\"[^\"]*\")?\)", content):
            href = match[1].strip("<>")
            if href.startswith("#") or urlsplit(href).scheme or href.startswith("//"):
                continue
            path = unquote(urlsplit(href).path)
            if path:
                resolved = (file.parent / path).resolve()
                local_path(path, file.parent, optional=resolved.is_relative_to(ROOT / "local-sources"), link=True)

    totals["markdown_documents"] = len(markdown_files())
    require(not (ROOT / "web/content.js").exists(), "Retired wiki browser bundle must not be generated")
    for record in catalogs.get("experiments", []):
        status = record.get("status")
        require(status in ("not_run", "in_progress", "blocked", "passed", "failed"),
                f"Unknown experiment status: {record.get('id')}")
        if status == "not_run":
            require(record.get("executed_on") is None and record.get("result") is None,
                    f"Unexecuted experiment contains a claimed result: {record.get('id')}")
        elif status in ("passed", "failed"):
            require(bool(record.get("executed_on")) and bool(record.get("result")) and bool(record.get("evidence_paths")),
                    f"Executed experiment lacks result/date/raw evidence: {record.get('id')}")
            for path in record.get("evidence_paths", []):
                local_path(path)
        require(bool(record.get("prerequisites")) and bool(record.get("expected")) and bool(record.get("cleanup")),
                f"Experiment prerequisites/result/cleanup incomplete: {record.get('id')}")
    print(json.dumps({"ok": not errors, "counts": totals, "warnings": sorted(set(warnings)), "errors": errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ci-ignored-local-sources", action="store_true",
                        help="Warn for absent files under ignored local-sources; still check available hashes")
    sys.exit(check(ci_ignored_local_sources=parser.parse_args().ci_ignored_local_sources))
