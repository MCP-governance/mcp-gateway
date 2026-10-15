# 9개 도구 자연어 하네스 시험 — run-03-claude

- 하네스: claude-code · 모델 `claude-sonnet-5-5` (effort high) · PJ1 관리 계정 uid 1001 · 장치 `managed-3af9a74e-23d3-414f-8145-32edf6280720`
- 집행 증거: 설치된 AppArmor 프로파일 안에서 실행(mcpgw-managed-pj1-claude (enforce)), 정책 해시 `8a9d4eb1b4aa2fb9…` 일치, 사전 점검에서 도구 목록이 정확히 9개
- 결과: 모델 호출 9건 · 원장 판정 9건(id 744~752, 10-14 15:06:23 KST) · 도구 오류 7건(성공 2건) · 해시체인 연결 9/9
- 모델 비용·시간: 32260ms · $0.0730316 · 10턴

| # | 서버.도구 | 인자 | 모델이 받은 결과 | 기대값 포함 | 원장 id | 판정 | 정책 | 업스트림 실행 | 도구 오류 |
| ---: | --- | --- | --- | --- | ---: | --- | --- | --- | --- |
| 1 | `pj1-nine-git.git_status` | 일치 | 오류: Error: Git status failed: Exit Code: 128 Stderr: fatal: detected dubious ownership in repository at '/fixt | 아니오 | 744 | Allow | `P-AUTHZ-ALLOW-001` | 예 | Error: Git status failed: Exit Code: 128 Stderr: fatal: detected dubious ownership in repository at '/fixtures |
| 2 | `pj1-nine-git.git_log` | 일치 | 오류: Error: Git log failed: Exit Code: 128 Stderr: fatal: detected dubious ownership in repository at '/fixture | 아니오 | 745 | Allow | `P-AUTHZ-ALLOW-001` | 예 | Error: Git log failed: Exit Code: 128 Stderr: fatal: detected dubious ownership in repository at '/fixtures/re |
| 3 | `pj1-nine-git.git_add` | 일치 | 오류: Error: Git add failed: Exit Code: 128 Stderr: fatal: detected dubious ownership in repository at '/fixture | 아니오 | 746 | Allow | `P-AUTHZ-ALLOW-001` | 예 | Error: Git add failed: Exit Code: 128 Stderr: fatal: detected dubious ownership in repository at '/fixtures/re |
| 4 | `pj1-nine-git.git_commit` | 일치 | 오류: Error: Git commit failed: Exit Code: 128 Stderr: fatal: detected dubious ownership in repository at '/fixt | 아니오 | 747 | Allow | `P-AUTHZ-ALLOW-001` | 예 | Error: Git commit failed: Exit Code: 128 Stderr: fatal: detected dubious ownership in repository at '/fixtures |
| 5 | `pj1-nine-sqlite.search_objects` | 일치 | {   "success": true,   "data": {     "object_type": "table",     "pattern": "%",     "detail_level": "names",  | 예 | 748 | Allow | `P-AUTHZ-ALLOW-001` | 예 | — |
| 6 | `pj1-nine-sqlite.execute_sql` | 일치 | {   "success": true,   "data": {     "statements": [       {         "sql": "SELECT id, label FROM demo_items  | 예 | 749 | Allow | `P-AUTHZ-ALLOW-001` | 예 | — |
| 7 | `pj1-nine-browser.browser_navigate` | 일치 | 오류: ### Error Error: async initializeServer: Chromium distribution 'chrome' is not found at /opt/google/chrome | 아니오 | 750 | Allow | `P-AUTHZ-ALLOW-001` | 예 | ### Error Error: async initializeServer: Chromium distribution 'chrome' is not found at /opt/google/chrome/chr |
| 8 | `pj1-nine-browser.browser_snapshot` | 일치 | 오류: ### Error Error: async initializeServer: Chromium distribution 'chrome' is not found at /opt/google/chrome | 아니오 | 751 | Allow | `P-AUTHZ-ALLOW-001` | 예 | ### Error Error: async initializeServer: Chromium distribution 'chrome' is not found at /opt/google/chrome/chr |
| 9 | `pj1-nine-browser.browser_evaluate` | 일치 | 오류: ### Error Error: async initializeServer: Chromium distribution 'chrome' is not found at /opt/google/chrome | 아니오 | 752 | Allow | `P-AUTHZ-ALLOW-001` | 예 | ### Error Error: async initializeServer: Chromium distribution 'chrome' is not found at /opt/google/chrome/chr |

## 독립 효과 확인 (기기에서 직접 읽음)
- Git 최근 커밋: `216a1a1 fixture baseline` · 작업 트리: `?? notes.md` · 마지막 커밋 파일: README.md | 1 +
- SQLite 해시 변화 없음: True · HTML 해시 변화 없음: True

## 직접 확인하는 곳
- 콘솔 `모니터링 → 도구 호출 로그`에서 서버 `pj1-nine-*`, 시각 15:06 전후. 상세에서 요청·판정·오류를 본다.
- 이 폴더: `harness.events.jsonl`(모델·도구 이벤트 원본, 토큰 가림), `prompt.txt`, `calls.json`(호출별 인자·결과), `ledger.json`(원장 행·효과), `preflight.json`, `execution.json`
- 한계: 모델 응답은 비결정적이므로 이 표는 한 번의 실행 결과다. 폐기 가능한 합성 fixture만 사용했다.
