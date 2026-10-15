#!/usr/bin/env python3
"""Build the PJ1 GhidraMCP report from preserved, task-local probe evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = ROOT / ".task-local-20261014/reverse/pj1-ghidra-linux-run1/mcp-probe.json"
MANIFEST = ROOT / ".task-local-20261014/reverse/pj1-ghidra-linux-run1/install-manifest.txt"
ARTIFACTS = ROOT / ".task-local-20261014/reverse/pj1-ghidra-linux-run1/artifact-sha256.txt"
LIVE_OBSERVATION = ROOT / "research/llm-wiki/analysis/pj1-ghidra/live-observation.json"
FINISH_OBSERVATION = ROOT / "research/llm-wiki/analysis/pj1-ghidra/finish-and-managed-denial.json"
JSON_OUT = ROOT / "research/llm-wiki/analysis/pj1-ghidra/report.json"
MD_OUT = ROOT / "research/llm-wiki/analysis/pj1-ghidra/report.md"

READ_TOOLS = {
    "get_program_info", "list_functions", "list_methods", "search_functions_by_name",
    "list_classes", "list_namespaces", "list_segments", "list_imports", "list_exports",
    "list_data_items", "list_strings", "get_function_by_address", "decompile_function",
    "decompile_function_by_address", "disassemble_function", "get_xrefs_to", "get_xrefs_from",
    "get_function_xrefs", "get_function_calls", "read_memory",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    live_observation = json.loads(LIVE_OBSERVATION.read_text(encoding="utf-8"))
    finish_observation = json.loads(FINISH_OBSERVATION.read_text(encoding="utf-8"))
    schemas = evidence["tools_list"]["result"]["tools"]
    names = [item["name"] for item in schemas]
    read_names = [name for name in names if name in READ_TOOLS]
    write_names = [name for name in names if name not in READ_TOOLS]
    assert len(names) == 28 and len(read_names) == 20 and len(write_names) == 8
    assert evidence["initialize"].get("result", {}).get("serverInfo", {}).get("name") == "ghidra-mcp"
    assert evidence["read_call"].get("result", {}).get("isError") is False
    install_manifest = MANIFEST.read_text(encoding="utf-8")
    artifact_manifest = ARTIFACTS.read_text(encoding="utf-8")
    read_result = evidence["read_call"]["result"].get("structuredContent", {})
    if not read_result:
        for item in evidence["read_call"]["result"].get("content", []):
            if item.get("type") == "text":
                try:
                    read_result = json.loads(item["text"])
                    break
                except json.JSONDecodeError:
                    pass
    raw_evidence = {
        "file": ".task-local-20261014/reverse/pj1-ghidra-linux-run1/mcp-probe.json",
        "sha256": sha(EVIDENCE),
        "remote_file": "/home/pj1/mcpgw-ghidra-20261014/logs/mcp-probe.json",
        "remote_sha256": "7f593299b9c2c190c1ed99da764d530757fceddbf227703fd97fb5cd5b18fde3",
    }
    tool = {
        "name": "Ghidra 12.1.4 with GhidraMCP 2.0.0",
        "status": "stdio_protocol_and_read_call_verified; runtime_volatile",
        "license": {
            "ghidra": "Apache-2.0",
            "ghidramcp": "Apache-2.0",
            "temurin": "GPL-2.0 with Classpath Exception",
            "uv": "MIT OR Apache-2.0",
            "paid_key_used": False,
        },
        "versions": {
            "ghidra": evidence["ghidra"],
            "ghidra_source_commit": evidence["ghidra_source_commit"],
            "ghidramcp": evidence["ghidramcp"],
            "ghidramcp_source_commit": evidence["ghidramcp_source_commit"],
            "jdk": evidence["jdk"],
            "python": evidence["python"],
            "mcp_sdk": evidence["mcp_sdk"],
            "pyghidra": evidence["pyghidra"],
            "jpype1": evidence["jpype1"],
            "uv": "0.12.19",
        },
        "installation": {
            "scope": "PJ1 user-owned task directory and /dev/shm only; no system-wide install or startup service",
            "pj1_directory": "/home/pj1/mcpgw-ghidra-20261014",
            "volatile_runtime_directory": "/dev/shm/mcpgw-ghidra-20261014/runtime",
            "volatile_runtime_bytes_at_install": 1330413568,
            "persistent_task_bytes_at_install": 38883328,
            "reboot_persistent_runtime": False,
            "artifact_sha256_manifest": artifact_manifest,
            "ghidramcp_extension_jar_sha256": evidence["extension_jar_sha256"],
            "ghidramcp_python_wheel_sha256": "af9818966da24afbd0a66824081f0486001c64614091caec3fa0e39d07367e8e",
            "install_manifest_sha256": sha(MANIFEST),
            "install_manifest": install_manifest,
            "system_path_firewall_managed_config_auth_or_nine_server_registry_changed": False,
            "initial_attempt": "python3 -m venv failed because ensurepip/pip was absent; no system package installation was attempted",
            "successful_recovery": "SHA-verified standalone uv 0.12.19 created task-local venv and installed pinned/resolved package set",
        },
        "protocol": {
            "transport": "stdio",
            "executed_command": evidence["command"],
            "server_cli_options_used": ["--headless", "--binary", "--ghidra-install-dir", "--extension-jar"],
            "other_relevant_cli_defaults_from_help": {"transport": "stdio", "mcp_host": "127.0.0.1 for HTTP transport", "headless_project": "temporary project by default; discard on exit unless a project is supplied"},
            "initialize": evidence["initialize"],
            "tools_list_response_id": evidence["tools_list"].get("id"),
            "tool_count": len(schemas),
            "tool_schemas": schemas,
            "read_call": {
                "request": {"method": "tools/call", "name": "get_program_info", "arguments": {}},
                "response": evidence["read_call"],
                "result_summary": read_result,
            },
            "process_exit_code": evidence.get("process_exit_code"),
            "hold_completed": evidence.get("hold_completed"),
            "started_kst": evidence["time_kst_started"],
            "finished_kst": evidence["time_kst_finished"],
            "raw_evidence": raw_evidence,
        },
        "permissions": {
            "actual_process_uid": evidence["stdio_uid"],
            "apparmor_profile": evidence["device_apparmor_profile"],
            "schema_counts": {"read": len(read_names), "project_mutation_advertised": len(write_names)},
            "read_tools": read_names,
            "write_tools_advertised_not_called": write_names,
            "script_or_shell_tool_advertised": False,
            "target_binary_executed": False,
            "reachable_paths": "The process ran as pj1 UID 1000 with normal account filesystem access; launcher accepted the explicit synthetic --binary and task-local Ghidra install/extension paths. No OS sandbox was demonstrated.",
            "project_scope": "No --project argument was supplied; the CLI help says headless mode defaults to a temporary project and discard on exit.",
            "bridge": {
                "observed_listener_during_hold": evidence.get("owned_listeners", []),
                "bound_loopback_only_in_observation": True,
                "authentication": "not configured or evidenced",
                "origin_host_checks": "source-level checks are not authentication and do not demonstrate isolation from same-user local processes",
            },
            "persistence_and_extension_surface": "Current probe used the headless GhidraMCP extension. Eight mutating tools were advertised. GUI/other extensions were not tested. RAM runtime is lost on reboot; no persistent service or application registration was made.",
        },
        "synthetic_fixture": {
            "kind": "synthetic 126-byte ELF64 x86-64; one executable segment; mov eax,42; ret",
            "path": evidence["binary_path"],
            "sha256": evidence["binary_sha256"],
            "analyzed_sha256": read_result.get("sha256"),
            "function_count": read_result.get("function_count"),
            "execution": "imported and statically analyzed by Ghidra; never executed as an operating-system process",
        },
        "process_evidence": {
            "pid": evidence["stdio_pid"],
            "process_tree_at_hold": evidence.get("process_tree", []),
            "listeners_at_hold": evidence.get("owned_listeners", []),
            "exit_code": evidence.get("process_exit_code"),
            "parent_reported_post_exit": {
                "pid_absent": True,
                "listeners_absent": True,
                "reported_at_kst": "2026-10-14T19:01:59+09:00",
                "evidence_scope": "reported by parent from live PJ1 process/listener inspection; separate from MCP JSON-RPC evidence",
            },
        },
        "parent_reported_gateway_observation": {
            "source_path": "research/llm-wiki/analysis/pj1-ghidra/live-observation.json",
            "source_sha256": sha(LIVE_OBSERVATION),
            "parent_device_path": "/var/lib/mcpgw-managed/managed-pj1/evidence/ghidra-20261014/live-observation.json",
            "copied_by": "parent agent; copied for shared local review",
            "observations": {
                "collector_process_detection_count": len(live_observation.get("processes", [])),
                "detected_processes": live_observation.get("processes", []),
                "automatic_netscan_enabled": live_observation.get("automatic_scan_enabled"),
                "automatic_report": live_observation.get("automatic_report"),
                "automatic_listener_rows": live_observation.get("automatic_listener_rows"),
                "explicit_user_directed_one_off_netscan": live_observation.get("manual_collection"),
                "endpoint_post_accepted": live_observation.get("receiver_result", {}).get("accepted"),
                "console_shadow_count": live_observation.get("receiver_result", {}).get("counts", {}).get("shadow"),
                "suspected_count": live_observation.get("receiver_result", {}).get("evidence", {}).get("suspected"),
                "registry_approval_performed": live_observation.get("registry_approval_performed"),
                "raw_command_or_credentials_logged": live_observation.get("raw_command_or_credentials_logged"),
                "prior_listener_rows": live_observation.get("prior_listener_rows"),
            },
            "cleanup_and_boundary": {
                "source_path": "research/llm-wiki/analysis/pj1-ghidra/finish-and-managed-denial.json",
                "source_sha256": sha(FINISH_OBSERVATION),
                "ghidra_process_exited": finish_observation.get("ghidra_process_exited"),
                "cleanup_removed_listener_rows": finish_observation.get("listener_snapshot_cleanup", {}).get("removed"),
                "cleanup_remaining_shadow_rows": finish_observation.get("listener_snapshot_cleanup", {}).get("counts", {}).get("shadow"),
                "managed_uid_launch": finish_observation.get("managed_launch"),
                "execution_denial_events_delivered": finish_observation.get("receiver_os_event_result", {}).get("received"),
            },
            "interpretation": "A manually requested one-off process observation reached the endpoint reporting route and Console shadow view; after exit, one stale row was removed and the prior empty state restored. Automatic scan/report was disabled. A separate UID 1001 attempt was denied at general Python interpreter execution before GhidraMCP loaded; it demonstrates the reported generic interpreter rule only, not a Ghidra-specific denial rule. None of this is a managed harness natural-language model turn, Gateway registration/approval, or Gateway-routed MCP invocation.",
        },
        "reproduction": {
            "probe_script": "research/llm-wiki/experiments/pj1-ghidra/probe_pj1_ghidra_mcp.py",
            "fresh_install_script": "research/llm-wiki/experiments/pj1-ghidra/install_pj1_runtime.sh",
            "continuation_script": "research/llm-wiki/experiments/pj1-ghidra/continue_pj1_venv_with_uv.sh",
            "zip_permissions_script": "research/llm-wiki/experiments/pj1-ghidra/restore_ghidra_modes.sh",
            "report_builder": "research/llm-wiki/experiments/pj1-ghidra/build_report.py",
            "remote_task_directory": "/home/pj1/mcpgw-ghidra-20261014",
            "runtime_prerequisite": "current boot's volatile /dev/shm runtime; after reboot the Ghidra/JDK runtime must be reacquired/unpacked",
        },
    }
    data = {
        "category": "PJ1 local reverse engineering MCP installation and endpoint observation",
        "date": "2026-10-14",
        "tools": [tool],
        "sources": [
            {"kind": "official_release", "title": "NSA Ghidra 12.1.4", "url": "https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.1.4_build", "version": "Ghidra_12.1.4_build", "commit": evidence["ghidra_source_commit"], "license": "Apache-2.0", "archive_sha256": "ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db"},
            {"kind": "official_docs", "title": "Ghidra Getting Started", "url": "https://github.com/NationalSecurityAgency/ghidra/blob/Ghidra_12.1.4_build/GhidraDocs/GettingStarted.md", "read_scope": "official headless installation and use guidance at pinned release tag"},
            {"kind": "upstream_release", "title": "GhidraMCP 2.0", "url": "https://github.com/LaurieWired/GhidraMCP/releases/tag/2.0", "commit": evidence["ghidramcp_source_commit"], "license": "Apache-2.0", "release_archive_sha256": "ebf904fd6782e429e95a60a24fe0724b20c0acb2dedb304135a5281f6b5f2e72"},
            {"kind": "upstream_source", "title": "GhidraMCP pinned source", "url": "https://github.com/LaurieWired/GhidraMCP/tree/1e980252087b2479a21b9ca6d82d5829538651a7", "read_scope": ["README.md", "pyproject.toml", "LICENSE", "src/ghidra_mcp/cli.py", "server/headless/backend and extension HTTP bridge sources"], "source_file_sha256": {"README.md": "b82f32e9e36d55c9a7b0d7578a650312b5f319551e2d4a0870552e4895e61850", "pyproject.toml": "f57db8489f8e8ef5da468261385bb115fe0ff881c4e680aeecd6263bee22cb6c", "LICENSE": "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4", "src/ghidra_mcp/cli.py": "bba3e1cd2d17c0b28238488cb2434c7d53d5b77be668d21a6708970ff62943be"}},
            {"kind": "official_runtime", "title": "Eclipse Temurin 21.0.12.1+1 Linux x64 JDK", "url": "https://github.com/adoptium/temurin21-binaries/releases/tag/jdk-21.0.12.1%2B1", "archive_sha256": "ce79869e1307ed8ee1e2baa86a412b1eb5b75d10a01006d788a6f968bcfaee94", "license": "GPL-2.0 with Classpath Exception"},
            {"kind": "official_runtime", "title": "uv 0.12.19", "url": "https://github.com/astral-sh/uv/releases/tag/0.12.19", "archive_sha256": "23bf5552d220e0842b65c862097b2ebaeba0064b74eda5e565e77fd25969d8c8", "license": "MIT OR Apache-2.0"},
        ],
        "limitations": [
            "Ghidra and Temurin runtime were unpacked under /dev/shm because PJ1 persistent filesystem lacked enough free space. Current-run MCP success is confirmed; reboot-persistent application deployment is not.",
            "The headless stdio MCP protocol initialize, tools/list (28 exact schemas), and one get_program_info read call succeeded. Eight project-mutating tools were advertised, not called.",
            "Parent's separate gateway observation indicates automatic collection was disabled and no automatic report was sent; one explicitly requested one-off scan was accepted. Parent evidence itself was not directly read by this subtask.",
            "No harness natural-language model turn, Gateway MCP registry approval, Gateway tool call, or registry change was tested/performed.",
            "No real or untrusted binary was analyzed; only the generated ELF fixture was imported/analyzed and it was never executed.",
            "The process was unconfined under AppArmor and ran as UID 1000 with that user's ordinary filesystem access. No account separation or sandbox property is claimed.",
            "The bridge listener was observed on mapped IPv4 loopback during the hold. The parent independently reported no process/listener after shutdown. Local bridge authentication is not demonstrated; Origin/Host behavior is not authentication.",
            "HTTP/SSE MCP modes, GUI, remote network access, project persistence, write tools, arbitrary user binaries, and post-reboot startup were not exercised.",
        ],
    }
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = [
        "# PJ1 Ghidra + GhidraMCP 설치 및 로그 관측",
        "",
        f"- 기준시각(KST): {evidence['time_kst_started']} ~ {evidence['time_kst_finished']}",
        "- 판정: PJ1 UID 1000에서 실제 Ghidra 12.1.4 + GhidraMCP 2.0.0 headless/stdin MCP 연결 성공. 런타임은 `/dev/shm`에 있어 재부팅 지속 설치는 아니다.",
        "- 증거: 실제 `initialize` → `tools/list` 28 schemas → 무해 read `get_program_info` 성공, exit code 0. 원본 JSON-RPC 응답과 stderr는 `analysis/pj1-ghidra/mcp-probe.json` 및 ignored task-local 사본에 보존했다.",
        "",
        "## 설치 상태와 식별값",
        "",
        "Ghidra, JDK, Python 환경과 GhidraMCP 소스/extension을 요청된 PJ1 사용자 소유 경로에 설치했다. 저장 공간이 부족해 Ghidra/JDK 실행 파일은 `/dev/shm/mcpgw-ghidra-20261014/runtime`에 순차적으로 풀었고, 측정 총량은 1,330,413,568 bytes다. 이 경로는 휘발성이므로 재부팅 후에는 없어지며 지속 설치 완료로 보지 않는다. 설치 로그는 persistent task directory에 남겼다.",
        "",
        "- Ghidra archive SHA-256: `ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db`; GhidraMCP 2.0 release archive: `ebf904fd6782e429e95a60a24fe0724b20c0acb2dedb304135a5281f6b5f2e72`.",
        "- Temurin archive SHA-256: `ce79869e1307ed8ee1e2baa86a412b1eb5b75d10a01006d788a6f968bcfaee94`; standalone uv archive SHA-256: `23bf5552d220e0842b65c862097b2ebaeba0064b74eda5e565e77fd25969d8c8`.",
        "- GhidraMCP extension JAR SHA-256: `" + evidence["extension_jar_sha256"] + "`; Python wheel SHA-256: `af9818966da24afbd0a66824081f0486001c64614091caec3fa0e39d07367e8e`.",
        f"- Source pins: Ghidra `{evidence['ghidra_source_commit']}`; GhidraMCP `{evidence['ghidramcp_source_commit']}`. Licenses: Ghidra/GhidraMCP Apache-2.0, Temurin GPL-2.0 with Classpath Exception, uv MIT or Apache-2.0.",
        "- No system-wide package, PATH, firewall, managed configuration, credentials, startup service, or 9-server registry was changed.",
        "",
        "## 실제 MCP 연결과 권한",
        "",
        f"`initialize` negotiated protocol `{evidence['initialize']['result']['protocolVersion']}` with server `{evidence['initialize']['result']['serverInfo']['name']}`; `tools/list` returned {len(schemas)} exact schemas. The read call returned `isError=false`, synthetic ELF `synthetic_return_42.elf`, SHA-256 `{evidence['binary_sha256']}`, and {read_result.get('function_count')} function. The synthetic ELF was imported and statically analyzed, never run as a program.",
        "",
        "실행 인자는 `--headless --binary <합성 ELF> --ghidra-install-dir <휘발 runtime> --extension-jar <task-local JAR>`였다. 기본 stdio transport를 썼고 `--project`는 전달하지 않았다. 실제 argv는 JSON `protocol.executed_command`에 보존했다.",
        "",
        f"Advertised schema classification: read {len(read_names)}, project mutation {len(write_names)}. Read tools: " + ", ".join(f"`{x}`" for x in read_names) + ".",
        "",
        "Advertised mutation tools (not called): " + ", ".join(f"`{x}`" for x in write_names) + ".",
        "",
        f"The MCP server ran under UID {evidence['stdio_uid']} and AppArmor profile `{evidence['device_apparmor_profile']}`. During the hold its Java bridge listener was `{evidence.get('owned_listeners', ['not captured'])[0]}`; parent later independently reported PID and listener absent. The listener was loopback-bound in this observation, but no bridge authentication or filesystem sandbox was demonstrated. The process retained ordinary account-user access to reachable files.",
        "",
        "## 엔드포인트 로그 관측 경계",
        "",
        "부모가 PJ1에서 수집해 공유한 별도 관측 JSON(`live-observation.json`, SHA-256 `" + sha(LIVE_OBSERVATION) + "`)을 MCP 프로브와 분리해 기록했다. 자동 스캔 비활성 상태에서 자동 보고/감지 행 0건이었다. 명시적 일회성 사용자 지시 스캔 1건은 endpoint POST accepted 1, Console shadow/suspected 1로 수신됐다. 프로세스 종료 뒤 별도 `finish-and-managed-denial.json` evidence에 stale row 1개 제거와 shadow 0 복원을 기록했다. UID 1001의 별도 launch는 `/usr/bin/python3` exec 단계에서 거부됐으며, GhidraMCP 로드 전 일반 Python interpreter 차단이다. 이 결과들은 자연어 모델 도구 호출, Gateway MCP 등록/승인, 자동 로그 forwarding, Ghidra 전용 정책 판정을 뜻하지 않는다.",
        "",
        "## 재현 파일과 한계",
        "",
        "재현 스크립트는 `research/llm-wiki/experiments/pj1-ghidra/`에 있다. 설치 중 기본 Python venv 생성이 ensurepip 부재로 실패했으나, 설치하지 않은 공식 standalone uv의 SHA를 확인하고 task-local venv 복구를 완료했다. 로그와 source/runtime manifest는 `/home/pj1/mcpgw-ghidra-20261014/logs/`에 보존했다.",
        "",
        "Ghidra의 8개 변경 도구는 schema만 확인하고 호출하지 않았다. 임의/실대상 바이너리, Gateway 경유 도구 호출, 모델 자연어 turn, HTTP MCP mode, GUI, 프로젝트 지속성, 시스템 부팅 후 기동은 실행하지 않았다. Ghidra/JDK RAM runtime은 재부팅되면 소실된다.",
        "",
        "## 공식 출처",
        "",
        "- [Ghidra 12.1.4 release](https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.1.4_build) · [Ghidra headless documentation](https://github.com/NationalSecurityAgency/ghidra/blob/Ghidra_12.1.4_build/GhidraDocs/GettingStarted.md)",
        "- [GhidraMCP 2.0 release](https://github.com/LaurieWired/GhidraMCP/releases/tag/2.0) · [GhidraMCP pinned source](https://github.com/LaurieWired/GhidraMCP/tree/1e980252087b2479a21b9ca6d82d5829538651a7)",
        "- [Temurin 21.0.12.1+1](https://github.com/adoptium/temurin21-binaries/releases/tag/jdk-21.0.12.1%2B1) · [uv 0.12.19](https://github.com/astral-sh/uv/releases/tag/0.12.19)",
        "",
        "Exact tool input/output schemas, initialize/tools/list/read-call messages, process tree, and stderr are preserved in the JSON report. The protocol report proves server/client functionality on PJ1 for this session, not durable deployment or managed natural-language execution.",
    ]
    # Keep the installed manifest verbatim in JSON while keeping the human report concise.
    MD_OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"wrote {JSON_OUT}\nwrote {MD_OUT}\ninitialize=success tools={len(schemas)} read={len(read_names)} mutation_advertised={len(write_names)} read_call=success exit={evidence.get('process_exit_code')}")


if __name__ == "__main__":
    main()
