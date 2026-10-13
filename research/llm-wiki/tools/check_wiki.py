"""Check provenance, navigation and offline renderer synchronization."""
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

from build_wiki import ROOT, ResearchRenderer, safe_url, render_markdown
import mistune

REPO = ROOT.parents[1]


def check():
    errors, warnings, totals = [], [], {}

    def require(condition, message):
        if not condition:
            errors.append(message)

    def local_path(value, base=ROOT, optional=False):
        path = (base / unquote(value)).resolve()
        require(path.is_relative_to(REPO), f"Path outside repository: {value}")
        if not optional:
            require(path.is_file(), f"Missing local file: {value}")
        return path

    for name in ("README.md", "AGENTS.md", "CLAUDE.md", "papers/README.md", "solutions/README.md",
                 "experiments/README.md", "status/current.md", "status/backlog.md", "web/index.html"):
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
                local_path(path, file.parent, optional=resolved.is_relative_to(ROOT / "local-sources"))

    renderer = mistune.create_markdown(renderer=ResearchRenderer(escape=True),
                      plugins=["table", "strikethrough", "task_lists", "url"])
    for url in ("javascript:alert(1)", "java&#x73;cript:alert(1)", "data:text/html,test",
                "file:///C:/secret", "//remote.example/x", "java\nscript:test", "C:/tool.exe"):
        require(safe_url(url) == "#harmful-link", f"Unsafe renderer URL accepted: {url}")
    attack = renderer('<script>alert(1)</script> [attack](javascript:alert(1)) ![beacon](https://remote.example/image)')
    require("<script" not in attack and 'href="javascript:' not in attack and "<img" not in attack,
            "Untrusted Markdown is active in browser output")
    require("<table>" in renderer("| a | b |\n| --- | --- |\n| 1 | 2 |"), "Markdown tables not rendered")

    content_file = ROOT / "web/content.js"
    if not content_file.is_file():
        errors.append("Web content missing: run build_wiki.py")
    else:
        text = content_file.read_text(encoding="utf-8")
        prefix = "window.WIKI_DATA="
        require(text.startswith(prefix), "Unexpected generated JS format")
        web = json.loads(text[len(prefix):].rstrip().removesuffix(";"))
        require(web["catalogs"] == catalogs, "Web catalogs stale: run build_wiki.py")
        actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*.md")
                  if p.relative_to(ROOT).parts[0] not in ("web", "tools", "local-sources") and "__pycache__" not in p.parts}
        require(actual == {p["path"] for p in web["pages"]}, "Web document inventory stale")
        for page in web["pages"]:
            require(not page["path"].startswith("local-sources/"), "Local-only full text leaked into public web")
            source = (ROOT / page["path"]).read_text(encoding="utf-8-sig")
            require(source == page["markdown"], f"Web Markdown stale: {page['path']}")
            require(render_markdown(source) == page["html"], f"Web HTML stale: {page['path']}")
        for original, plain_copy in web.get("text_sources", {}).items():
            original_path = local_path(original, optional=original.startswith("local-sources/"))
            copy_path = local_path(plain_copy, optional=plain_copy.startswith("local-sources/"))
            require(copy_path.suffix == ".txt", f"Active source text filename: {plain_copy}")
            if original_path.is_file() and copy_path.is_file():
                require(original_path.read_bytes() == copy_path.read_bytes(), f"Source text copy stale: {original}")
        totals["web_pages"] = len(web["pages"])
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
    sys.exit(check())
