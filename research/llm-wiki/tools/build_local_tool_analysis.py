"""Build the reviewed local-tool index; never approve tools in the runtime registry."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
ANALYSIS = ROOT / "analysis/local-tools"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    reverse, data, desktop = (read(ANALYSIS / (name + ".json")) for name in ("reverse", "data", "desktop"))
    ghidra = reverse["tools"][0]
    data_evidence = Path(data["reproduction"]["raw_protocol_evidence"])
    if not data_evidence.is_absolute():  # kept in the wiki, relative to the repository
        data_evidence = REPO / data_evidence
    assert data_evidence.is_relative_to(REPO), "Unexpected local protocol path"
    assert digest(data_evidence) == data["reproduction"]["raw_protocol_evidence_sha256"], "Protocol evidence changed"
    raw_data = read(data_evidence)
    sources = {
        "ghidra": ghidra["protocol_evidence"]["tool_schemas"],
        "git": raw_data["servers"]["git"]["tools_list"]["result"]["tools"],
        "sqlite": raw_data["servers"]["sqlite"]["tools_list"]["result"]["tools"],
    }
    for result in desktop["results"]:
        if result["id"] in ("blender", "playwright-chromium"):
            sources["playwright" if result["id"] == "playwright-chromium" else result["id"]] = result["mcp"]["tools"]

    classes = {"ghidra": {name: ["read"] for name in ghidra["permissions"]["read_tools"]}}
    classes["ghidra"].update({name: ["project-write"] for name in ghidra["permissions"]["write_tools"]})
    classes["git"] = {name: ["read", "git-subprocess"] for name in (
        "git_blame", "git_changelog_analyze", "git_diff", "git_log", "git_reflog", "git_show", "git_status", "git_wrapup_instructions")}
    classes["git"].update({name: ["read", "repository-write", "git-subprocess"] for name in (
        "git_add", "git_branch", "git_checkout", "git_cherry_pick", "git_clean", "git_commit", "git_init",
        "git_merge", "git_rebase", "git_remote", "git_reset", "git_stash", "git_tag", "git_worktree")})
    classes["git"].update({name: ["read", "repository-write", "git-subprocess", "network"] for name in (
        "git_clone", "git_fetch", "git_pull", "git_push")})
    classes["git"].update({name: ["read", "session-write"] for name in ("git_set_working_dir", "git_clear_working_dir")})
    classes["git"]["git_wrapup_instructions"] = ["read", "repository-write", "git-subprocess"]
    classes["sqlite"] = {"execute_sql": ["read", "database-write", "sql-execution"], "search_objects": ["read"]}
    classes["blender"] = {
        "get_addon_status": ["read"], "disable_telemetry": ["settings-write"], "get_scene_info": ["read"],
        "execute_blender_code": ["read", "project-write", "python-execution"],
        "record_trajectory_feedback": ["read", "network"], "look": ["read", "host-file-read", "view-write"],
        "generate_3d": ["project-write", "network"], "search_assets": ["read", "network"],
        "import_asset": ["project-write", "network"],
    }
    classes["playwright"] = {name: ["read"] for name in (
        "browser_console_messages", "browser_find", "browser_network_requests", "browser_snapshot", "browser_wait_for")}
    classes["playwright"].update({name: ["read", "browser-write"] for name in (
        "browser_close", "browser_resize", "browser_handle_dialog", "browser_emulate_media", "browser_fill_form",
        "browser_press_key", "browser_type", "browser_navigate_back", "browser_click", "browser_drag", "browser_hover",
        "browser_select_option", "browser_tabs")})
    classes["playwright"].update({
        "browser_navigate": ["read", "browser-write", "network"],
        "browser_network_request": ["read", "host-write"],
        "browser_evaluate": ["read", "browser-write", "page-javascript"],
        "browser_run_code_unsafe": ["read", "host-write", "server-javascript", "network"],
        "browser_file_upload": ["host-file-read", "browser-write", "network"],
        "browser_drop": ["host-file-read", "browser-write", "network"],
        "browser_take_screenshot": ["read", "host-write"],
    })
    for name in ("browser_console_messages", "browser_find", "browser_network_requests", "browser_snapshot"):
        classes["playwright"][name] = ["read", "host-write"]
    classes["playwright"]["browser_tabs"] = ["read", "browser-write", "network"]
    tested = {
        "ghidra": {"get_program_info"},
        "git": {"git_set_working_dir", "git_status", "git_clone", "git_add", "git_commit"},
        "sqlite": {"execute_sql"},
        "blender": {"get_addon_status", "get_scene_info", "execute_blender_code"},
        "playwright": {"browser_navigate", "browser_snapshot"},
    }
    paths = {"ghidra": "reverse.md", "git": "data.md", "sqlite": "data.md", "blender": "desktop.md", "playwright": "desktop.md"}
    output = []
    for server, schemas in sources.items():
        assert {schema["name"] for schema in schemas} == set(classes[server]), f"Schema changed; review {server} manually"
        for schema in schemas:
            canonical = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            output.append({"id": server + ":" + schema["name"], "server": server, "name": schema["name"],
                           "capability_tags": classes[server][schema["name"]], "schema": schema,
                           "schema_sha256": hashlib.sha256(canonical).hexdigest(),
                           "call_observed": schema["name"] in tested[server],
                           "source_analysis": "analysis/local-tools/" + paths[server],
                           "verification": "reviewed-schema-and-selected-local-calls",
                           "limitation": "스키마 광고·보수적 권한 상한 분류; 개별 도구 전체 실행 또는 관리 엔드포인트 집행 증거 아님"})
    (ANALYSIS / "tool-capabilities.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    lines = ["# 실제 MCP 스키마의 기능 유형", "",
             "2026-10-14 검수. 태그는 해당 기능의 보수적 권한 상한이며 인자/상태에 따라 달라집니다. readOnlyHint 등 annotation은 권한 보장이 아닙니다.",
             "실제 호출을 확인한 도구와 목록만 확인한 도구를 분리합니다. 정상 read 한 건을 서버의 모든 도구 실행 완료로 집계하지 않습니다.", "",
             "| MCP | 실제 도구 | 기능 유형 | 선택 호출 관측 |", "| --- | --- | --- | --- |"]
    for item in output:
        lines.append(f"| {item['server']} | `{item['name']}` | {', '.join(item['capability_tags'])} | {'확인' if item['call_observed'] else '목록만'} |")
    (ANALYSIS / "tool-capabilities.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    risks = read(ROOT / "catalogs/local-tool-risks.json")
    lines = ["# 로컬 소프트웨어·MCP 위험매핑", "",
             "실제 공개 MCP의 로컬 설치·프로토콜 결과와 엔드포인트 코드 회귀를 원본 PAC01~24에 의미로 연결했습니다.",
             "운영 카탈로그에 자동 등록·계약 승인하지 않았으며 게이트웨이 경유·실기기 집행으로 표시하지 않습니다.", "",
             "| ID | 위험·관찰 | 원본 정책 | 통제 위치·개선 | 남은 확인 |", "| --- | --- | --- | --- |"]
    for risk in risks:
        href = "../" + risk["path"]
        lines.append(f"| {risk['id']} | [{risk['title']}]({href}): {risk['observation']} | {', '.join(risk['source_controls'])} | {risk['boundary']}: {risk['required_control']} | {risk['remaining']} |")
    (ROOT / "threats/local-tool-map.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    manifest = {"date": "2026-10-14", "verification": "reviewed-local-protocol-evidence",
                "tool_count": len(output), "counts": {server: len(schemas) for server, schemas in sources.items()},
                "manifests": [{"path": "analysis/local-tools/" + name + ".json", "sha256": digest(ANALYSIS / (name + ".json"))}
                              for name in ("reverse", "data", "desktop")],
                "capability_index_sha256": digest(ANALYSIS / "tool-capabilities.json"),
                "risk_count": len(risks), "all_local_tools_managed_endpoint_verified": False,
                "selected_pj1_kernel_evidence": "status/reports/2026-10-14-pj1-endpoint-update.json",
                "runtime_registry_changed": False}
    (ANALYSIS / "review.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(manifest["counts"], ensure_ascii=False), "reviewed tools", len(output))


if __name__ == "__main__":
    build()
