# 2026-10-23 실사용 시험 — 로컬 MCP 3종을 PJ1 실제 하네스로 끝까지

- 작업자: Claude Code (리더)
- 코드 기준: main `b92ee91` → `56e9a36`. 작업 브랜치 `10/23-scan-url-parse`, `10/23-tool-action-override`, `10/23-reapply-after-deregister`,
  `10/23-ast-harness`, `10/23-runner-consent`(Codex 00b·00c 병합), `10/23-policy-removal-gap`, `10/23-runner-failure-log`,
  `10/23-output-credential-span`, `10/23-local-call-one-container`, `10/23-recipient-heuristic`, `10/23-local-jobs-policy-gap`,
  `10/23-agent-skip-local-runner`, `10/23-runner-http-detail`
- 시작 근거: 소유자 지시(10-23) — 인기 MCP를 실제로 도입·승인·호출해 정상 기능부터 동작시킬 것, 시험 신청·승인은 리더가 대행, 끝나면 철회
- 해결할 문제와 완료 조건: PJ1 Claude Code가 filesystem(문서 읽기) → memory(엔티티·관계 저장·재조회) → sequentialthinking(계획)을
  게이트웨이 경유로 차단 없이 끝낸다.

## 결과

시나리오가 PJ1 관리형 계정의 실제 Claude Code에서 끝까지 통과했다(마지막 실행: 허용 3건·경보 5건·차단 0건, 저장 그래프를 다시 읽어 확인).
막혔던 순서대로 고친 것:

| 막힘 | 원인 | 수정 |
| --- | --- | --- |
| 51KB 문서 읽기 `MCP-OUTPUT-001`(Gitleaks ValueError) | `secret_scan.scan_text`의 `urlsplit`이 `http://[` 링크에서 Invalid IPv6 URL | 쿼리를 직접 절단(da732e3) |
| 읽기 재호출 `P-RATE-003` | 공식 filesystem 이미지가 `readOnlyHint`를 달지 않아 읽기 도구가 쓰기로 등록 | 승인에서 분류를 제안값 이하로 낮춤(D-199), 철회 후 재신청 허용 |
| 도구마다 첫 사용 동의로 여러 번 정지 | 동의가 도구 단위로만 생성 | Codex 00c 병합: 서버 단위 일괄 동의(D-201) |
| 원격 MCP 하나 ERROR로 PC 전체 `ENDPOINT-MANAGED-001` | 서버 제거를 통제 변경으로 봄 | 서버 목록만 다르면 그 서버만 거절(D-198 정정) |
| SDK 문서 5개 통째 보류 | 문자열 값의 `text=<문서>`에서 OAuth 예시가 구조화 자격으로 탐지 | 키 경계를 넘는 탐지만 보류(D-202) |
| 로컬 호출 시간 초과·컨테이너 전 실패 | 호출마다 컨테이너 3번(initialize·list·call) | 호출의 앞 두 단계는 승인 계약으로 응답, 대조는 PC 러너(D-203) |
| memory `create_relations` PAC-10 | 인자 이름 `to`를 메일 수신자로 분류 | 주소 형태·메일 분류일 때만 수신자(D-204) |
| memory 그래프가 비어 있음 | 호출마다 새 컨테이너라 `/tmp` 저장이 사라짐 | 영구 폴더 `mcp-memory:rw` + `MEMORY_FILE_PATH`로 재승인(설정) |
| 서버 하나 철회·승인 뒤 로컬 작업 409 | 로컬 작업 정책 비교가 정확 일치 | 같은 서버 목록 규칙 적용(D-198 정정 2) |
| 승인된 로컬 컨테이너가 섀도 MCP 경보 | 관찰기가 러너 컨테이너 프로세스를 미등록 stdio MCP로 보고 | `mcpgw.local=1` 라벨 컨테이너 제외(D-205) |

Codex 00(출력 오탐)은 같은 문제를 main에 이미 배포·실측된 305b79d와 다르게 구현해 병합하지 않았다. 그중 구조화 자격 판정 방식만 D-202로 가져왔다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | pyflakes, `node --check`, `node --test` 콘솔 2종 | 통과 | 콘솔 출력 |
| 단위·대역 | `intake_one_click_check`(게이트웨이 이미지 20), `intake_one_click_ast_check` 12, `consent_per_server_check` 25, `local_runner_usability_check` 28, `managed_policy_gap_check` 5, `output_credential_span_check` 2, `endpoint_collector_check` 8, `dev73_*` | 통과 | 콘솔 출력 |
| 실제 모델·하네스 | PJ1 `claude -p`(Sonnet), `tmp/w4/st_local3.json` PTY 구동, 10-23 04:20 KST | filesystem→memory→sequentialthinking 완료 | `tmp/w4/local3_final.log`, 원장 decisions |
| upstream 효과 | PJ1 `/home/managed-pj1/mcp-memory/memory.json`에 엔티티·관계 저장, `read_graph` 재조회 일치 | 확인 | 하네스 응답 |
| 배포 | 기기 `dev_deploy_nocred.sh`, main 56e9a36 | 배포됨 | 기기 출력 |
| CI | push 실행이 02:31~ 생성되지 않다가 41095eb부터 다시 생성 | 56e9a36 진행 중 | GitHub Actions |

## 실패·미완료·한계

- `MCP-SHADOW-002` 경보 5건은 시험 명령(`--allowedTools 'mcp__modelcontextprotocol-…'`)의 명령행이 관찰기 표식(`modelcontextprotocol`)에
  걸린 것이다. 실제 사용 명령행에는 없는 패턴이라 고치지 않았다.
- 오전에 로컬 작업 1건이 실행 중 `/control` 409로 정지됐는데 사유가 남지 않아 특정하지 못했다. 러너가 이제 게이트웨이 거절 문장을 PC 로그에 남긴다.
- `pac_boundary_check`·`adversarial_check`는 운영 기기 DB에 시험용 서버·템플릿이 없어 main에서도 실패한다(환경 의존).
- `local_jobs_pg_check`의 새 확인은 운영 DB의 작업 행을 지우는 시험이라 기기에서 돌리지 않았다.
- 시험 서버 8개(원격 5·로컬 3)는 시험 뒤 철회했다. 10-15 기준 서버 3개(GitHub·Context7·MarkItDown)는 남겼다.

## 다음 작업

- 로컬 MCP 승인 화면에서 저장형 MCP(memory 등)의 영구 폴더 지정을 안내 없이 기본값으로 제안(현재는 관리자가 직접 입력).
- 로컬 호출 지연(컨테이너 1회 기동 3~4초) 단축 — 같은 사용자·서버의 짧은 재사용 세션 검토.

## 사용자에게 필요한 입력

없음
