# PJ1 Ghidra + GhidraMCP 설치 및 로그 관측

- 기준시각(KST): 2026-10-14T18:59:34.284551+09:00 ~ 2026-10-14T19:01:14.651812+09:00
- 판정: PJ1 UID 1000에서 실제 Ghidra 12.1.4 + GhidraMCP 2.0.0 headless/stdin MCP 연결 성공. 런타임은 `/dev/shm`에 있어 재부팅 지속 설치는 아니다.
- 증거: 실제 `initialize` → `tools/list` 28 schemas → 무해 read `get_program_info` 성공, exit code 0. 원본 JSON-RPC 응답과 stderr는 `analysis/pj1-ghidra/mcp-probe.json` 및 ignored task-local 사본에 보존했다.

## 설치 상태와 식별값

Ghidra, JDK, Python 환경과 GhidraMCP 소스/extension을 요청된 PJ1 사용자 소유 경로에 설치했다. 저장 공간이 부족해 Ghidra/JDK 실행 파일은 `/dev/shm/mcpgw-ghidra-20261014/runtime`에 순차적으로 풀었고, 측정 총량은 1,330,413,568 bytes다. 이 경로는 휘발성이므로 재부팅 후에는 없어지며 지속 설치 완료로 보지 않는다. 설치 로그는 persistent task directory에 남겼다.

- Ghidra archive SHA-256: `ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db`; GhidraMCP 2.0 release archive: `ebf904fd6782e429e95a60a24fe0724b20c0acb2dedb304135a5281f6b5f2e72`.
- Temurin archive SHA-256: `ce79869e1307ed8ee1e2baa86a412b1eb5b75d10a01006d788a6f968bcfaee94`; standalone uv archive SHA-256: `23bf5552d220e0842b65c862097b2ebaeba0064b74eda5e565e77fd25969d8c8`.
- GhidraMCP extension JAR SHA-256: `1d41bd86c33879f0e42658cd5e06bb57c5f3a128e5500dd76ab37b2b9db481f1`; Python wheel SHA-256: `af9818966da24afbd0a66824081f0486001c64614091caec3fa0e39d07367e8e`.
- Source pins: Ghidra `8b6bbb857accdfa20dc5b2f5dea471178c2e9fbc`; GhidraMCP `1e980252087b2479a21b9ca6d82d5829538651a7`. Licenses: Ghidra/GhidraMCP Apache-2.0, Temurin GPL-2.0 with Classpath Exception, uv MIT or Apache-2.0.
- No system-wide package, PATH, firewall, managed configuration, credentials, startup service, or 9-server registry was changed.

## 실제 MCP 연결과 권한

`initialize` negotiated protocol `2025-06-18` with server `ghidra-mcp`; `tools/list` returned 28 exact schemas. The read call returned `isError=false`, synthetic ELF `synthetic_return_42.elf`, SHA-256 `0a64fc68cccfb67b816011fe7a6b58c4deb566c234516520a409dbfc6b2ea8ba`, and 1 function. The synthetic ELF was imported and statically analyzed, never run as a program.

실행 인자는 `--headless --binary <합성 ELF> --ghidra-install-dir <휘발 runtime> --extension-jar <task-local JAR>`였다. 기본 stdio transport를 썼고 `--project`는 전달하지 않았다. 실제 argv는 JSON `protocol.executed_command`에 보존했다.

Advertised schema classification: read 20, project mutation 8. Read tools: `get_program_info`, `list_functions`, `list_methods`, `search_functions_by_name`, `list_classes`, `list_namespaces`, `list_segments`, `list_imports`, `list_exports`, `list_data_items`, `list_strings`, `get_function_by_address`, `decompile_function`, `decompile_function_by_address`, `disassemble_function`, `get_xrefs_to`, `get_xrefs_from`, `get_function_xrefs`, `get_function_calls`, `read_memory`.

Advertised mutation tools (not called): `rename_function_by_address`, `rename_function`, `rename_data`, `rename_variable`, `set_function_prototype`, `set_local_variable_type`, `set_decompiler_comment`, `set_disassembly_comment`.

The MCP server ran under UID 1000 and AppArmor profile `unconfined`. During the hold its Java bridge listener was `LISTEN 0      50              [::ffff:127.0.0.1]:35673       *:* users:(("python",pid=29514,fd=183))`; parent later independently reported PID and listener absent. The listener was loopback-bound in this observation, but no bridge authentication or filesystem sandbox was demonstrated. The process retained ordinary account-user access to reachable files.

## 엔드포인트 로그 관측 경계

부모가 PJ1에서 수집해 공유한 별도 관측 JSON(`live-observation.json`, SHA-256 `3385d0018bba7bd467cf04e471883511195a3d2c1b25ff2135d057b26c2d2a0f`)을 MCP 프로브와 분리해 기록했다. 자동 스캔 비활성 상태에서 자동 보고/감지 행 0건이었다. 명시적 일회성 사용자 지시 스캔 1건은 endpoint POST accepted 1, Console shadow/suspected 1로 수신됐다. 프로세스 종료 뒤 별도 `finish-and-managed-denial.json` evidence에 stale row 1개 제거와 shadow 0 복원을 기록했다. UID 1001의 별도 launch는 `/usr/bin/python3` exec 단계에서 거부됐으며, GhidraMCP 로드 전 일반 Python interpreter 차단이다. 이 결과들은 자연어 모델 도구 호출, Gateway MCP 등록/승인, 자동 로그 forwarding, Ghidra 전용 정책 판정을 뜻하지 않는다.

## 재현 파일과 한계

재현 스크립트는 `research/llm-wiki/experiments/pj1-ghidra/`에 있다. 설치 중 기본 Python venv 생성이 ensurepip 부재로 실패했으나, 설치하지 않은 공식 standalone uv의 SHA를 확인하고 task-local venv 복구를 완료했다. 로그와 source/runtime manifest는 `/home/pj1/mcpgw-ghidra-20261014/logs/`에 보존했다.

Ghidra의 8개 변경 도구는 schema만 확인하고 호출하지 않았다. 임의/실대상 바이너리, Gateway 경유 도구 호출, 모델 자연어 turn, HTTP MCP mode, GUI, 프로젝트 지속성, 시스템 부팅 후 기동은 실행하지 않았다. Ghidra/JDK RAM runtime은 재부팅되면 소실된다.

## 공식 출처

- [Ghidra 12.1.4 release](https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.1.4_build) · [Ghidra headless documentation](https://github.com/NationalSecurityAgency/ghidra/blob/Ghidra_12.1.4_build/GhidraDocs/GettingStarted.md)
- [GhidraMCP 2.0 release](https://github.com/LaurieWired/GhidraMCP/releases/tag/2.0) · [GhidraMCP pinned source](https://github.com/LaurieWired/GhidraMCP/tree/1e980252087b2479a21b9ca6d82d5829538651a7)
- [Temurin 21.0.12.1+1](https://github.com/adoptium/temurin21-binaries/releases/tag/jdk-21.0.12.1%2B1) · [uv 0.12.19](https://github.com/astral-sh/uv/releases/tag/0.12.19)

Exact tool input/output schemas, initialize/tools/list/read-call messages, process tree, and stderr are preserved in the JSON report. The protocol report proves server/client functionality on PJ1 for this session, not durable deployment or managed natural-language execution.
