#!/usr/bin/env python3
"""Build the tracked Ghidra reverse-tool report from preserved local evidence."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = ROOT / ".task-local-20261014/reverse/run21/mcp-evidence.json"
JSON_OUT = ROOT / "research/llm-wiki/analysis/local-tools/reverse.json"
MD_OUT = ROOT / "research/llm-wiki/analysis/local-tools/reverse.md"


def main() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    run_time = datetime.fromtimestamp(EVIDENCE.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    schemas = evidence["tools_list"]["result"]["tools"]
    read_names = {
        "get_program_info", "list_functions", "list_methods", "search_functions_by_name",
        "list_classes", "list_namespaces", "list_segments", "list_imports", "list_exports",
        "list_data_items", "list_strings", "get_function_by_address", "decompile_function",
        "decompile_function_by_address", "disassemble_function", "get_xrefs_to", "get_xrefs_from",
        "get_function_xrefs", "get_function_calls", "read_memory",
    }
    tool = {
        "name": "Ghidra with GhidraMCP",
        "role": "reverse engineering and binary analysis",
        "selection": "required Ghidra integration",
        "status": "installed_and_mcp_connected",
        "license": {
            "ghidra": "Apache-2.0",
            "ghidramcp": "Apache-2.0",
            "jdk": "GPL-2.0-with-classpath-exception (Temurin/OpenJDK)",
            "free_use_scope": "free/open-source components; no paid key used",
        },
        "versions": {
            "ghidra": "12.1.4",
            "ghidra_release_tag": "Ghidra_12.1.4_build",
            "ghidra_commit": "8b6bbb857accdfa20dc5b2f5dea471178c2e9fbc",
            "ghidramcp": "2.0.0",
            "ghidramcp_commit": "1e980252087b2479a21b9ca6d82d5829538651a7",
            "java": "Temurin 21.0.12.1+1",
            "python": "3.12.10",
            "mcp_sdk": "1.30.0",
            "pyghidra": "3.1.0",
            "jpype1": "1.5.2",
        },
        "maintenance_observation": "As checked 2026-10-14, GitHub marked Ghidra 12.1.4 and GhidraMCP 2.0 as Latest; GhidraMCP release was published 2026-10-10 and the release commit showed GitHub Verified signature. This is a point-in-time observation, not a support/SLA claim.",
        "installation": {
            "scope": "task-local ignored directory only; no system install, PATH, firewall, harness, or compose changes",
            "root": ".task-local-20261014/reverse/",
            "ghidra_dir": ".task-local-20261014/reverse/ghidra/ghidra_12.1.4_PUBLIC",
            "jdk_dir": ".task-local-20261014/reverse/jdk21/jdk-21.0.12.1+1",
            "ghidramcp_source_dir": ".task-local-20261014/reverse/GhidraMCP-src",
            "venv_dir": ".task-local-20261014/reverse/venv",
            "ghidra_archive_sha256": "ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db",
            "ghidramcp_release_archive_sha256": "ebf904fd6782e429e95a60a24fe0724b20c0acb2dedb304135a5281f6b5f2e72",
            "ghidramcp_wheel_sha256": "af9818966da24afbd0a66824081f0486001c64614091caec3fa0e39d07367e8e",
            "temurin_archive_sha256": "f9d6e191ab098c0d416e7d588a24420a8621cd2f4720dab2459b8b7b2d2d8b4e",
        },
        "transport": {
            "mcp_client_to_server": "stdio",
            "mcp_server_to_ghidra_backend": "ephemeral HTTP on 127.0.0.1",
            "authentication": "none on the local bridge; no auth challenge observed",
            "origin_host_controls": "source rejects requests containing Origin and limits Host to 127.0.0.1, localhost, [::1]",
            "http_transport_option": "CLI supports HTTP mode, --mcp-host defaults to 127.0.0.1; not used for MCP in this test",
        },
        "protocol_evidence": {
            "run_time_local": run_time,
            "evidence_file_ignored": str(EVIDENCE.relative_to(ROOT)).replace("\\", "/"),
            "initialize": evidence["initialize"],
            "tools_list_request_id": evidence["tools_list"].get("id"),
            "tool_count": len(schemas),
            "tool_schemas": schemas,
            "successful_read_call": {
                "request": {"method": "tools/call", "name": "get_program_info", "arguments": {}},
                "response": evidence["read_call"],
            },
            "process_exit_code": evidence["exit_code_after_terminate"],
            "loopback_observation": next((line for line in evidence["stderr"] if "Serving " in line), None),
        },
        "permissions": {
            "schema_classification": {"read": len(read_names), "project_write": len(schemas) - len(read_names)},
            "read_tools": sorted(read_names),
            "write_tools": [item["name"] for item in schemas if item["name"] not in read_names],
            "execute_or_script_tool_exposed": False,
            "execution_note": "The selected binary was imported and analyzed by Ghidra; it was not launched as a process.",
            "reachable_paths": "The launcher accepts caller-selected --binary and optional --project filesystem paths; analysis/process inherits current OS user rights. MCP tools operate on the active loaded program/project.",
            "persistence": "No --project was supplied. Ghidra used a temporary project and logged Discarding unsaved changes at shutdown.",
            "plugin_surface": "The GhidraMCP extension is installed/loaded for headless mode. GUI-only capabilities may expose a different schema; this test covers the headless mode only.",
        },
        "test_input": {
            "kind": "synthetic ELF64 x86-64; mov eax,42; ret; one executable load segment",
            "path_ignored": evidence["binary"],
            "sha256": evidence["binary_sha256"],
            "reported_program_sha256": evidence["read_call"]["result"]["structuredContent"]["sha256"],
            "reported_function_count": evidence["read_call"]["result"]["structuredContent"]["function_count"],
            "result": "read call successful; one function detected",
        },
        "reproduction": {
            "script": "research/llm-wiki/experiments/local-tools/reverse/run_probe.ps1",
            "protocol_driver": "research/llm-wiki/experiments/local-tools/reverse/probe_ghidra_mcp.py",
            "report_builder": "research/llm-wiki/experiments/local-tools/reverse/build_report.py",
            "requirements": "task-local ignored installation described above",
        },
    }

    data = {
        "category": "local reverse engineering and binary analysis",
        "date": "2026-10-14",
        "tools": [tool],
        "sources": [
            {"kind": "official_release", "url": "https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.1.4_build", "commit_or_tag": "Ghidra_12.1.4_build / 8b6bbb857accdfa20dc5b2f5dea471178c2e9fbc", "as_of": "2026-10-14", "latest_label_observed": True, "verified": ["release version", "official archive SHA-256", "Apache-2.0", "minimum JDK 21"]},
            {"kind": "official_docs", "url": "https://github.com/NationalSecurityAgency/ghidra/blob/Ghidra_12.1.4_build/GhidraDocs/GettingStarted.md", "verified": ["headless use and installation guidance"]},
            {"kind": "upstream_mcp_release", "url": "https://github.com/LaurieWired/GhidraMCP/releases/tag/2.0", "commit_or_tag": "2.0 / 1e980252087b2479a21b9ca6d82d5829538651a7", "published": "2026-10-10", "as_of": "2026-10-14", "latest_label_observed": True, "github_signature": "Verified", "verified": ["release bundle SHA-256", "Apache-2.0", "Ghidra 12.1.4 compatibility", "headless PyGhidra and stdio"]},
            {"kind": "upstream_source", "url": "https://github.com/LaurieWired/GhidraMCP/tree/1e980252087b2479a21b9ca6d82d5829538651a7", "files": ["src/ghidra_mcp/server.py", "src/ghidra_mcp/headless.py", "src/ghidra_mcp/cli.py", "src/ghidra_mcp/backend.py", "extension/src/main/java/com/lauriewired/ghidramcp/http/BackendHttpServer.java"], "verified": ["tool declarations and schemas", "loopback binding", "Origin/Host checks", "HTTP routes and absence of arbitrary shell/script tool"]},
            {"kind": "official_runtime_api", "url": "https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=windows&vendor=eclipse", "verified": ["Temurin JDK 21 distribution metadata and archive digest"]},
        ],
        "limitations": [
            "Second candidate (radare2/rizin) was not installed; parent prioritized completion of actual Ghidra integration. No comparative runtime result is claimed.",
            "Only the headless stdio configuration was exercised. GUI mode and optional remote HTTP MCP mode were not run.",
            "The successful tools/call was read-only. The 8 project-edit tools were enumerated but not invoked; their write capability is established by schema/source, not a mutation test.",
            "No authentication is present on the internal loopback bridge. Origin/Host checks are not authentication; there is no evidence here for resistance to local same-user processes.",
            "Paths are process-user reachable; no sandbox or per-project authorization enforcement was demonstrated. Arbitrary --binary/--project selection is a launcher capability.",
            "No real-world or untrusted binary, network target, external MCP client, gateway route, managed harness, or endpoint policy was tested.",
            "On this Korean Windows path PyGhidra child output hit a UTF-8 decoding issue using the native path; the successful run used a temporary drive alias. Runner removes the alias on exit. No persistent project was retained.",
            "Early failed attempts (incorrect cli module entry point, JDK 25, and an explicit project path inside a dot-prefixed directory) are excluded from successful evidence; only the preserved successful run counts.",
        ],
    }
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    read_tools = [item["name"] for item in schemas if item["name"] in read_names]
    write_tools = [item["name"] for item in schemas if item["name"] not in read_names]
    lines = [
        "# 로컬 역공학 도구 조사: Ghidra + GhidraMCP",
        "",
        f"- 조사일: 2026-10-14; 실제 프로토콜 실행시각(KST): {run_time}",
        "- 판정: 설치 완료 및 실제 MCP 연결 성공. Ghidra만 실제 실행했고, 비교 후보를 설치한 것으로 세지 않았다.",
        "- 범위: task-local 설치, headless Ghidra, stdio MCP, 합성 ELF. 게이트웨이/하네스/실대상 검증은 하지 않았다.",
        "",
        "## 설치 및 라이선스",
        "",
        "Ghidra 12.1.4 (Apache-2.0), GhidraMCP 2.0.0 (Apache-2.0), Temurin JDK 21.0.12.1+1, Python 3.12.10을 `.task-local-20261014/reverse/`에 설치했다. 무료 사용 가능한 오픈소스 구성요소이며 유료 키를 사용하지 않았다. 설치 파일과 upstream 코드는 버전/commit에 고정했다.",
        "",
        "- Ghidra archive SHA-256: `ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db`.",
        "- GhidraMCP release archive SHA-256: `ebf904fd6782e429e95a60a24fe0724b20c0acb2dedb304135a5281f6b5f2e72`.",
        "- GhidraMCP Python wheel SHA-256: `af9818966da24afbd0a66824081f0486001c64614091caec3fa0e39d07367e8e`.",
        "- Temurin archive SHA-256: `f9d6e191ab098c0d416e7d588a24420a8621cd2f4720dab2459b8b7b2d2d8b4e`.",
        "- 고정 소스: [Ghidra `Ghidra_12.1.4_build`](https://github.com/NationalSecurityAgency/ghidra/tree/Ghidra_12.1.4_build), commit `8b6bbb857accdfa20dc5b2f5dea471178c2e9fbc`; [GhidraMCP 2.0](https://github.com/LaurieWired/GhidraMCP/tree/1e980252087b2479a21b9ca6d82d5829538651a7), commit `1e980252087b2479a21b9ca6d82d5829538651a7`.",
        "- 조사 시 GitHub는 두 저장소의 해당 버전을 `Latest`로 표시했다. GhidraMCP 2.0은 2026-10-10 공개됐고 release commit에 Verified 서명이 표시됐다. 이는 2026-10-14 시점 관찰이며 지원 보장 의미는 아니다.",
        "",
        "## 실제 연결 증거",
        "",
        "MCP stdio에서 `initialize` 성공(MCP protocol `2025-06-18`, server `ghidra-mcp`; SDK version `1.30.0`) → `tools/list` 성공(28개) → `get_program_info` 성공(`isError=false`)을 확인했다. 합성 x86-64 ELF(126 bytes, SHA-256 `0a64fc68cccfb67b816011fe7a6b58c4deb566c234516520a409dbfc6b2ea8ba`)를 import/analyze 했고 함수 1개를 찾았다. 바이너리 코드는 실행하지 않았다. 원본 JSON-RPC 증거는 ignored 경로 `.task-local-20261014/reverse/run21/mcp-evidence.json`에 있다.",
        "",
        f"실제 schema 기준 읽기 도구 {len(read_tools)}개, 프로젝트 변경 도구 {len(write_tools)}개다. 읽기 도구: `" + "`, `".join(read_tools) + "`. 변경 도구: `" + "`, `".join(write_tools) + "`. 변경 도구는 목록만 확인했고 호출하지 않았다.",
        "",
        "## 권한과 도달 범위",
        "",
        "headless launcher가 지정 `--binary`를 읽고 분석한다. 선택적인 `--project` 경로를 받을 수 있다. 호출 도구는 현재 로드된 프로그램/project에 작동하고 프로세스 권한은 현재 OS 사용자 권한을 상속한다. 프로젝트 변경 도구 8개가 노출되므로 MCP 서버를 read-only로 분류할 수 없다. 테스트 시작 때 MCP transport는 stdio였고 GhidraMCP 내부 Java bridge는 로그상 ephemeral `127.0.0.1` HTTP였다. 내부 bridge의 인증은 확인되지 않았다. upstream 소스는 bridge에 `Origin` 헤더를 거부하고 `Host`를 loopback 이름으로 제한하지만, 이는 인증이 아니다. 별도 HTTP MCP 모드는 `--mcp-host`로 bind host를 지정하며 기본값이 `127.0.0.1`; 이 모드는 실행하지 않았다.",
        "",
        "headless 실행은 `--project`를 주지 않아 종료 시 저장하지 않은 변경을 폐기했다. 이 증거는 GUI capability 목록, 임의 script/command 실행, 외부 네트워크, sandbox, 사용자별 프로젝트 권한 분리, Gateway 집행을 입증하지 않는다. 28개 실제 input/output JSON schema 전체는 JSON의 `tools[0].protocol_evidence.tool_schemas`에 보존했다.",
        "",
        "## 재현",
        "",
        "설치물이 유지되어 있다면 `research/llm-wiki/experiments/local-tools/reverse/run_probe.ps1`을 실행한다. 이 스크립트는 로컬 task 경로를 임시 drive letter로 매핑해 PyGhidra의 Windows UTF-8 출력 문제를 피하고 종료 때 mapping을 제거한다. MCP driver는 `probe_ghidra_mcp.py`; JSON/Markdown 재생성은 `build_report.py`다. 모든 설치·로그·합성 파일은 ignored task-local 폴더에 둔다.",
        "",
        "## 출처",
        "",
        "- [NSA Ghidra 12.1.4 release](https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.1.4_build) · [headless 문서](https://github.com/NationalSecurityAgency/ghidra/blob/Ghidra_12.1.4_build/GhidraDocs/GettingStarted.md)",
        "- [GhidraMCP 2.0 release](https://github.com/LaurieWired/GhidraMCP/releases/tag/2.0) · [고정 upstream source](https://github.com/LaurieWired/GhidraMCP/tree/1e980252087b2479a21b9ca6d82d5829538651a7)",
        "- [Eclipse Adoptium JDK 21 API](https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=windows&vendor=eclipse)",
        "",
        "## 한계",
        "",
        "- radare2/rizin 두 번째 후보는 설치하지 않았다. 실제 Ghidra 연동을 우선했다.",
        "- Ghidra GUI 및 HTTP MCP mode는 실행하지 않았다. MCP write 스키마 8개는 호출하지 않았다.",
        "- 내부 bridge에 인증이 없으며 loopback/Origin/Host 점검만으로 local same-user access가 통제된다고 결론 내릴 수 없다.",
        "- real-world/untrusted binary, 외부 target, Gateway, managed harness 및 policy enforcement는 미실행이다.",
        "- 한국어 경로의 PyGhidra child-output UTF-8 오류는 temporary drive alias로 우회했다. 명시적 project 경로를 dot-prefixed task-local 폴더 아래 두는 경우 Ghidra가 거부했다.",
    ]
    MD_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {JSON_OUT}\nwrote {MD_OUT}\ninitialize=success tools={len(schemas)} read={len(read_tools)} write={len(write_tools)} read_call=success")


if __name__ == "__main__":
    main()
