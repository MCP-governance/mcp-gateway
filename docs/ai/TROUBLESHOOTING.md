# 문제 해결 — 실제로 겪은 것들

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| 컨테이너가 한꺼번에 사라짐 | WSL VM 유휴 종료 | 백그라운드 `wsl.exe -d kali-linux -- sleep infinity`, 서비스는 `restart: unless-stopped` |
| gateway·agent-service가 `Exited (0)`, 8000/8080에 다른 스택 | 같은 WSL의 다른 작업 트리 랩(v1)이 포트 선점 | 그 스택은 건드리지 말고 `.env`에 `CONSOLE_PORT`/`GATEWAY_PORT` 등을 다른 값으로(D-14) |
| `curl 127.0.0.1:8080`이 이상한 데이터(예: `read_document`, `mock-http-mcp`) | 다른 스택의 v1 Gateway에 붙었다 | `docker ps --format '{{.Names}} {{.Ports}}'`로 포트 주인 확인 |
| 브라우저가 옛 JS를 계속 씀 | 해시만 바꾼 navigate는 새로 고침이 아니다 | `location.reload()` (응답은 `no-store`) |
| `docker run … opa test`가 아무것도 출력 안 함 | static 이미지 기본 entrypoint | `--entrypoint /opa` |
| Rego를 고쳤는데 판정이 그대로 | OPA가 `--watch` 없이 뜸 | `docker compose restart opa` |
| desktop 서버가 재생성마다 DRIFT | 도구 설명에 컨테이너 id | `hostname: mcp-desktop` 고정(D-13) |
| mcp-proxy/postgres-mcp import 오류 | MCP SDK 2.x | venv에 `mcp>=1.17,<2` |
| fetch 첫 호출이 멈춤 | readabilipy가 런타임에 npm install | 빌드 때 설치 |
| email 서버 421 | 허용 호스트 | `MCP_ALLOWED_HOSTS: mcp-email:8000` |
| 업스트림 거부가 `MCP-UPSTREAM-001`(ExceptionGroup) | MCP 클라이언트 TaskGroup 안에서 raise | `_call_upstream`은 컨텍스트 밖에서 판단, `_root_cause` |
| 작은 모델이 도구를 안 부름 | 도구 설명이 길고 많음 | 160자 요약 + 상위 8개(D-09) |
| 모델이 "차단됐다"고 답하는데 실제는 실행 | 결과 맨 앞 Gateway 메모를 거절로 읽음 | 도구 출력 먼저, 메모는 뒤 |
| LiteLLM 응답에 tool_calls 없음 | `ollama_chat/` 경로 | `openai/` + Ollama `/v1`(D-07) |
| Ollama 0.5 tok/s | 하이브리드 CPU 16스레드 | `num_thread 6`(`LOCAL_LLM_THREADS`) |
| refresh family 폐기 SQL 오류 | `jti` text vs uuid | `jti::uuid` |
| 종료 케이스가 반쯤 열림 | v1 CHECK 제약이 새 kind 거부 | `v2_tables.sql`이 제약 재정의, `open_case` 원자화 |
| C4가 증거를 인정 안 함 | 증거 시각이 `revoked_at`보다 앞 | `revoke_target(at=…)` |
| 케이스마다 회수 대상 주체가 늘어남 | 프로브 호출을 이용으로 셈 | `REAL_CALL` 필터(D-12) |
| 승인했는데 실행 안 됨(EXC-002) | 승인형 예외가 재판정에서 다시 Approval | `exception_effect`(D-17) |
| gitea 도구가 401 | 종료 케이스가 PAT 폐기 | `./console.sh restore-token gitea` |
| workday `--check` 대량 실패, 사유 `MCP-DECOMM-001` | 누가 연 종료 케이스로 서버가 TERMINATING | 케이스 확인 후 종결/복원(`./console.sh restore <server>`) |
| Console 목록 500 한 번 | Gateway 재시작 중 프록시 연결 실패 | 이제 503 "Gateway에 연결할 수 없습니다"로 응답 |
| Git Bash에서 보낸 스크립트의 `\n`·`$변수`가 사라짐 | heredoc/따옴표 처리 | 스크립트를 `\\wsl.localhost\kali-linux\tmp\`에 파일로 쓰고 실행 |
| `all predefined address pools have been fully subnetted` | 명시 대역(D-24) 이전에 만든 스택 | `./console.sh down` 뒤 `up`(볼륨 유지) — 이후에는 `MCP_NET_PREFIX` 아래 `/24`만 쓴다 |
| `네트워크 대역 자동 선택 실패` | `10.200`~`10.249` 전부 다른 망·라우트와 겹침 | 안 쓰는 자기 복제본 `down`, 또는 `.env`에 `MCP_NET_PREFIX=10.x` 직접 지정 |
| 원격 MCP 승인이 409 "…증거 문서로 확인해야…" | 종료 조건 검증 기록 없음(D-26) | 도입 신청 → **종료 조건 검증**(관리자, HTTPS 근거 문서) 뒤 승인 |
| 도입 신청이 422 | 신청 본문에 종료 조건 필드(D-26) | 저장소·목적만 보낸다. 종료 조건은 관리자가 따로 기록 |
| CI `node --check console.js`가 "Cannot use import statement" | Node 20 이하(ES 모듈 감지 없음) | `actions/setup-node`로 Node 24(verify.yml) |
| 워크스테이션 빌드가 `endpoint` 컨텍스트를 못 찾음 | compose가 `additional_contexts` 미지원(2.17 미만) | Docker Compose 2.17+ |
| 결과에 `[REDACTED]`가 보임 | Presidio 출력 마스킹(주민번호·전화·외부 이메일·카드·자격 문자열) | 의도된 동작. 가린 유형은 활동 로그의 "개인정보" 칩과 감사 행 `privacy_types` |
| 외부 메일·URL 호출이 `P-CHAIN-001` | 같은 사용자가 10분 안에 중요정보를 읽었다 | 의도된 동작(D-22). 창은 `CHAIN_WINDOW_MINUTES` |
| 모든 쓰기·외부 호출이 `P-DATA-INSPECTION-001` | presidio-analyzer 불능 | `docker compose ps presidio-analyzer`, `/api/health`의 `presidio_*` |
| `./console.sh: Permission denied` | Windows 도구로 `\\wsl.localhost\…` 파일을 편집하면 새 파일로 다시 써져 실행 비트가 사라진다 | `chmod +x console.sh tests/security_regression.sh`, 커밋 전 `git diff --summary`로 mode change 확인 |
| `git` "dubious ownership"(시드) | root로 남의 디렉터리 | `git -c safe.directory=*` |
| Gitea `PUT /orgs/bob/members` 405 | API가 팀 경유만 허용 | Owners 팀 멤버 PUT |
