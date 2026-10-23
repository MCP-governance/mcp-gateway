# 하네스의 승인 MCP 탐지·사용 편의 (10-23)

- 결정: [D-233](../../../../docs/ai/DECISIONS.md). 시험: `full_stack_lab/tests/harness_detect_check.py`, `kit_continuity_check.py`.
- 대상: pj2(Ubuntu 24.04, 키트 활성, 관리 계정 managed-pj2) · Claude Code 2.1.309 · codex-cli 0.164.0. 승인된 MCP 11개만 사용했다. 새 승인·철회·기기 배포 없음.
- 측정 방법: `claude -p --output-format stream-json --verbose`를 pj2 계정에서 실행해 도구 호출 순서를 기록했다(원본: `tmp/mcp-detect/o_*.jsonl`, 저장소 밖). 서버 이름을 말하지 않은 자연어 요청을 썼다.

## 1. 직원이 겪는 문제 (측정)

| # | 문제 | 측정 | 비고 |
|---|---|---|---|
| 1 | 서버 이름을 말하지 않으면 MCP 도구를 쓰지 않는다 | 요청 4종 × 3회: **2/12만 MCP 사용** (파일 폴더 질문 2/3, DeepWiki 0/3, 기억 0/3, 단계별 사고 0/3) | 기억 요청은 내장 파일 메모리에 썼고, 저장소 구조 질문은 일반 지식으로 답했다 |
| 2 | 서비스 이름이 들어간 요청은 잘 쓴다 | MS 문서·Hugging Face·GitHub 커밋·Cloudflare·AWS·grep.app·MarkItDown **8/8 사용**. 대부분 ToolSearch 1회(`select:`로 정확한 이름 선택) 뒤 호출. Cloudflare만 키워드 검색 2회 | 지연 로딩된 도구 이름은 모델에게 보인다(init의 tools·시스템 알림) |
| 3 | 파일 서버는 경로 오해로 돌아간다 | “홈 디렉터리의 mcp-docs”라고 하자 내장 Read·Bash가 먼저 실패(7턴) → `list_allowed_directories`로 `/workspace/mcp-docs` 발견 | 서버가 허용한 경로와 직원이 아는 경로가 다르다 |
| 4 | 서버 이름이 해시 접미 형태 | `claude mcp list`: `learn-microsoft-com-46f63c3e`, `docs-mcp-cloudflare-c-681a2b17` 등 11개 모두 연결됨(✔ Connected) | 이름은 원장·권한 규칙에 쓰이는 ID라 바꾸지 않는다 |
| 5 | 공급자 오류가 정책 차단처럼 보인다 | grep.app 호출 7건 중 2건 `MCP-UPSTREAM-001` → 모델에 `[MCP Gateway · 차단 · …]`로 전달 (모델은 재시도해 성공) | 같은 오류가 실행 전 연결 실패(`Error POSTing to endpoint:`, 원장 기록 없음)로도 1회 나왔다. 두 번째 배터리와 겹쳐 돌 때였고 재현하지 못했다 |
| 6 | 차단 사유는 잘 전달된다 | MarkItDown `https://example.com` → `PAC-01` 사유·해결 방법을 모델이 그대로 안내 | 변경 없음 |
| 7 | 새 승인이 PC에 닿는 시간 | 키트 정책 조회 간격 **약 62초**(heartbeat 로그 20:50:04, 51:06, 52:09, 53:12, 54:14 … 간격 62~63초; 중복 실행 중 한 번 94초). 승인 직후 최대 약 1분 + 하네스 재시작 | 실행 중 세션 반영은 아래 3절(미측정) |
| 8 | 직원이 어떤 서버가 있는지 알 수 없다 | `mcpgw-status`는 「승인 서버: 11개」만 표시 | 새 서버가 들어와도 알림 없음 |
| 9 | 동의 마찰 | 11개 서버에서 `P-CONSENT-001` 미발생(원장 확인). 첫 사용 마찰 없음 | 동의 필요 도구가 생기면 「콘솔의 동의 요청을 확인하세요」로 안내(코드 확인, 미재현) |
| 10 | Codex | `/etc/codex/managed_config.toml`에 11개 `[mcp_servers.*]`가 들어 있고 `codex mcp list`(로그인 없이)가 11개를 `enabled`로 표시. Auth 열은 `Unknown`. 모델 호출은 로그인이 없어 미측정 | |

## 2. 원인

- Claude Code는 MCP 도구를 지연 로드한다. 세션 시작에는 도구 이름과 서버 `instructions`만 들어가고, 정의는 ToolSearch로 불러온다([mcp 문서, Scale with MCP tool search](https://code.claude.com/docs/en/mcp)). 모델이 “이 요청은 MCP 몫”이라고 판단하지 않으면 검색 자체를 하지 않는다(문제 1).
- 게이트웨이 `instructions`는 모든 서버 경로에 같은 한 문장(`mcp_facade.build_mcp`)이고, MCP SDK 2.2.0은 `Server` 생성 시 고정이라(`lowlevel/server.py`의 `self.instructions`) 서버·사람별로 바꿀 수 없다.
- 관리형 메모리 수단은 있었지만 쓰지 않았다: `managed-settings.json`의 `claudeMd`(managed 전용, 사용자가 `claudeMdExcludes`로 뺄 수 없음, v2.1.309에서 사용 가능)와 Codex `developer_instructions`.

## 3. 공식 근거 (WebFetch/curl로 원문 확인, 2026-10-23)

| 수단 | 출처 | 적용 |
|---|---|---|
| 관리형 CLAUDE.md `/etc/claude-code/CLAUDE.md` 또는 managed settings의 `claudeMd`; 사용자 제외 불가 | https://code.claude.com/docs/en/memory (Deploy organization-wide CLAUDE.md), https://code.claude.com/docs/en/settings-reference (`claudeMd`) | **적용**: 별도 파일을 늘리면 구형 키트가 「지원하지 않는 관리형 파일 목록」으로 거부하므로 이미 있는 `managed-settings.json`에 넣었다 |
| 서버 instructions·도구 설명 한도(4,096자 / 지연 도구 16,384자), 검색에 쓰일 단어는 앞쪽에 | https://code.claude.com/docs/en/mcp (Tool search for MCP server authors) | 안내문 1.9KB로 한도 안. 서버별 instructions는 SDK 고정이라 **보류** |
| `alwaysLoad`(서버 전체 지연 제외), `ENABLE_TOOL_SEARCH`, `anthropic/alwaysLoad` | https://code.claude.com/docs/en/mcp (Exempt a server from deferral) | **보류**: 도구 41개 정의가 매 대화 컨텍스트에 상주. 안내문만으로 11/12가 되므로 비용 대비 이득이 작다. 서버가 적고 항상 쓰는 경우에만 검토 |
| `managedMcpServers` 설정 키는 실행 중 대화형 세션에 추가·변경을 재시작 없이 반영 | https://code.claude.com/docs/en/managed-mcp (When provided servers connect) | **보류**: 지금은 `managed-mcp.json`(독점 제어)을 쓴다. 이 파일이 실행 중 세션에 반영되는지는 문서에 없다. 전환은 강제 범위가 달라져(사용자 서버 허용 목록 의존) 별도 결정 필요 |
| Codex `developer_instructions`(config.toml, 세션에 주입), `additional_developer_instructions`(requirements.toml, 오케스트레이터 지원 필요라 제외) | https://developers.openai.com/codex/config-reference.md | **적용**(Linux·macOS의 `managed_config.toml`). Windows는 직원 자신의 `config.toml`에 서버 블록이 들어가 키 중복 위험이 있어 제외 |
| `list_changed` 알림으로 도구 목록 갱신 | https://code.claude.com/docs/en/mcp (Updates to running sessions) | 서버 도구 변경에만 해당. 새 서버 추가와 별개 |

## 4. 구현 (D-233)

1. **관리형 안내문 렌더링**(`pac.harness_guidance`, `endpoint_plane.managed_policy`): 이 직원이 도구를 볼 수 있는 서버만, 관리자가 검토한 표시 이름과 도구 이름만 넣는다. 공급자 설명문은 넣지 않는다(조직 지침의 신뢰로 읽히므로). 이름은 `[0-9A-Za-z가-힣 ._()·-]` 밖을 지워 줄바꿈·백틱으로 지침을 끼워 넣을 수 없다. Claude는 `managed-settings.json`의 `claudeMd`, Codex(Linux·macOS)는 `managed_config.toml`의 `developer_instructions`.
2. **공급자 오류 표기**(`mcp_facade._render`): 원장은 그대로 Block이고 화면 머리표만 `오류`, 「정책이 막은 것이 아니라 공급자의 응답을 받지 못했습니다. 조회는 한 번 더, 쓰기·전송은 실행 여부를 확인한 뒤」를 덧붙인다.
3. **`mcpgw-status`**(Linux 키트 `managed-linux.py`): 서버 이름 줄과 「새로 반영된 서버 … (시각) — 이미 열려 있는 하네스에 보이지 않으면 다시 시작하세요」(1시간 표시).

## 5. 효과 (같은 4개 요청, pj2)

안내문을 managed 대신 managed 계정의 사용자 메모리(`~/.claude/CLAUDE.md`)에 임시로 두고 측정했다(managed 경로는 키트가 점검하는 파일이라 건드리지 않음; 시험 뒤 삭제). 같은 텍스트이며 로딩 위치만 다르다.

| 요청 | 적용 전 MCP 사용 | 적용 후 |
|---|---|---|
| 접근 가능한 폴더·파일 | 2/3 | **3/3** (filesystem) |
| facebook/react 저장소 구조 | 0/3 | **3/3** (DeepWiki) |
| 팀 배포 요일 기억 | 0/3 (내장 파일 메모리) | **3/3** (memory 서버) |
| 단계별 사고 | 0/3 | **2/3** (sequentialthinking) |
| 합계 | 2/12 | **11/12** |
| 「GitHub 최근 커밋 보여줘」 | 1/1 | 3/3 |
| 「사내 MCP로 뭘 할 수 있나」 | ToolSearch 2회 뒤 부분 답 | 도구 호출 없이 11개 서버 전체 목록으로 즉답 3/3 |

한계: 표본은 요청당 3회, 모델 응답 변동이 있다. 사용자 메모리와 managed `claudeMd`의 동일성은 문서상 근거(managed가 먼저 로드)이며 실제 managed 경로 측정은 배포 뒤 확인 대상이다. memory 서버 시험으로 `mcp-memory`(managed-pj2)에 항목이 남았을 수 있다.

## 6. 보류·후속

- 실행 중 세션 반영: 실제 승인 1건이 있을 때 대화형 Claude를 띄워 둔 채 `/mcp` 목록 변화를 본다(문서에 managed-mcp.json 규정 없음).
- `managedMcpServers`로의 전환(재시작 없는 추가), `alwaysLoad`: 위 표.
- 정책 조회 간격 60초 단축: 키트 루프가 점검·보고·토큰 갱신을 한 바퀴에 하므로 정책만 짧게 도는 별도 경로가 필요. 승인 직후 1분은 허용 범위로 보고 보류.
- 파일 서버의 허용 경로 안내(문제 3): 허용 디렉터리는 서버 실행 설정이라 안내문에 정적으로 넣을 수 없다. 서버 `instructions`를 서버별로 낼 수 있게 SDK를 확장해야 한다.
- macOS·Windows 키트의 상태 출력은 이번에 바꾸지 않았다.
