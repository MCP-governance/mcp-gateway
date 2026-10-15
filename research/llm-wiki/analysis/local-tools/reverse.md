# 로컬 역공학 도구 조사: Ghidra + GhidraMCP

- 조사일: 2026-10-14; 실제 프로토콜 실행시각(KST): 2026-10-14T13:12:02+09:00
- 판정: 설치 완료 및 실제 MCP 연결 성공. Ghidra만 실제 실행했고, 비교 후보를 설치한 것으로 세지 않았다.
- 범위: task-local 설치, headless Ghidra, stdio MCP, 합성 ELF. 게이트웨이/하네스/실대상 검증은 하지 않았다.

## 설치 및 라이선스

Ghidra 12.1.4 (Apache-2.0), GhidraMCP 2.0.0 (Apache-2.0), Temurin JDK 21.0.12.1+1, Python 3.12.10을 `.task-local-20261014/reverse/`에 설치했다. 무료 사용 가능한 오픈소스 구성요소이며 유료 키를 사용하지 않았다. 설치 파일과 upstream 코드는 버전/commit에 고정했다.

- Ghidra archive SHA-256: `ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db`.
- GhidraMCP release archive SHA-256: `ebf904fd6782e429e95a60a24fe0724b20c0acb2dedb304135a5281f6b5f2e72`.
- GhidraMCP Python wheel SHA-256: `af9818966da24afbd0a66824081f0486001c64614091caec3fa0e39d07367e8e`.
- Temurin archive SHA-256: `f9d6e191ab098c0d416e7d588a24420a8621cd2f4720dab2459b8b7b2d2d8b4e`.
- 고정 소스: [Ghidra `Ghidra_12.1.4_build`](https://github.com/NationalSecurityAgency/ghidra/tree/Ghidra_12.1.4_build), commit `8b6bbb857accdfa20dc5b2f5dea471178c2e9fbc`; [GhidraMCP 2.0](https://github.com/LaurieWired/GhidraMCP/tree/1e980252087b2479a21b9ca6d82d5829538651a7), commit `1e980252087b2479a21b9ca6d82d5829538651a7`.
- 조사 시 GitHub는 두 저장소의 해당 버전을 `Latest`로 표시했다. GhidraMCP 2.0은 2026-10-10 공개됐고 release commit에 Verified 서명이 표시됐다. 이는 2026-10-14 시점 관찰이며 지원 보장 의미는 아니다.

## 실제 연결 증거

MCP stdio에서 `initialize` 성공(MCP protocol `2025-06-18`, server `ghidra-mcp`; SDK version `1.30.0`) → `tools/list` 성공(28개) → `get_program_info` 성공(`isError=false`)을 확인했다. 합성 x86-64 ELF(126 bytes, SHA-256 `0a64fc68cccfb67b816011fe7a6b58c4deb566c234516520a409dbfc6b2ea8ba`)를 import/analyze 했고 함수 1개를 찾았다. 바이너리 코드는 실행하지 않았다. 원본 JSON-RPC 증거는 ignored 경로 `.task-local-20261014/reverse/run21/mcp-evidence.json`에 있다.

실제 schema 기준 읽기 도구 20개, 프로젝트 변경 도구 8개다. 읽기 도구: `get_program_info`, `list_functions`, `list_methods`, `search_functions_by_name`, `list_classes`, `list_namespaces`, `list_segments`, `list_imports`, `list_exports`, `list_data_items`, `list_strings`, `get_function_by_address`, `decompile_function`, `decompile_function_by_address`, `disassemble_function`, `get_xrefs_to`, `get_xrefs_from`, `get_function_xrefs`, `get_function_calls`, `read_memory`. 변경 도구: `rename_function_by_address`, `rename_function`, `rename_data`, `rename_variable`, `set_function_prototype`, `set_local_variable_type`, `set_decompiler_comment`, `set_disassembly_comment`. 변경 도구는 목록만 확인했고 호출하지 않았다.

## 권한과 도달 범위

headless launcher가 지정 `--binary`를 읽고 분석한다. 선택적인 `--project` 경로를 받을 수 있다. 호출 도구는 현재 로드된 프로그램/project에 작동하고 프로세스 권한은 현재 OS 사용자 권한을 상속한다. 프로젝트 변경 도구 8개가 노출되므로 MCP 서버를 read-only로 분류할 수 없다. 테스트 시작 때 MCP transport는 stdio였고 GhidraMCP 내부 Java bridge는 로그상 ephemeral `127.0.0.1` HTTP였다. 내부 bridge의 인증은 확인되지 않았다. upstream 소스는 bridge에 `Origin` 헤더를 거부하고 `Host`를 loopback 이름으로 제한하지만, 이는 인증이 아니다. 별도 HTTP MCP 모드는 `--mcp-host`로 bind host를 지정하며 기본값이 `127.0.0.1`; 이 모드는 실행하지 않았다.

headless 실행은 `--project`를 주지 않아 종료 시 저장하지 않은 변경을 폐기했다. 이 증거는 GUI capability 목록, 임의 script/command 실행, 외부 네트워크, sandbox, 사용자별 프로젝트 권한 분리, Gateway 집행을 입증하지 않는다. 28개 실제 input/output JSON schema 전체는 JSON의 `tools[0].protocol_evidence.tool_schemas`에 보존했다.

## 재현

설치물이 유지되어 있다면 `research/llm-wiki/experiments/local-tools/reverse/run_probe.ps1`을 실행한다. 이 스크립트는 로컬 task 경로를 임시 drive letter로 매핑해 PyGhidra의 Windows UTF-8 출력 문제를 피하고 종료 때 mapping을 제거한다. MCP driver는 `probe_ghidra_mcp.py`; JSON/Markdown 재생성은 `build_report.py`다. 모든 설치·로그·합성 파일은 ignored task-local 폴더에 둔다.

## 출처

- [NSA Ghidra 12.1.4 release](https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.1.4_build) · [headless 문서](https://github.com/NationalSecurityAgency/ghidra/blob/Ghidra_12.1.4_build/GhidraDocs/GettingStarted.md)
- [GhidraMCP 2.0 release](https://github.com/LaurieWired/GhidraMCP/releases/tag/2.0) · [고정 upstream source](https://github.com/LaurieWired/GhidraMCP/tree/1e980252087b2479a21b9ca6d82d5829538651a7)
- [Eclipse Adoptium JDK 21 API](https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=windows&vendor=eclipse)

## 한계

- radare2/rizin 두 번째 후보는 설치하지 않았다. 실제 Ghidra 연동을 우선했다.
- Ghidra GUI 및 HTTP MCP mode는 실행하지 않았다. MCP write 스키마 8개는 호출하지 않았다.
- 내부 bridge에 인증이 없으며 loopback/Origin/Host 점검만으로 local same-user access가 통제된다고 결론 내릴 수 없다.
- real-world/untrusted binary, 외부 target, Gateway, managed harness 및 policy enforcement는 미실행이다.
- 한국어 경로의 PyGhidra child-output UTF-8 오류는 temporary drive alias로 우회했다. 명시적 project 경로를 dot-prefixed task-local 폴더 아래 두는 경우 Ghidra가 거부했다.
