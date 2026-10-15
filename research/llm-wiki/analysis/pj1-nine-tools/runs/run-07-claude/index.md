# 9개 도구 자연어 하네스 시험 — run-07-claude

- 하네스: claude-code · 모델 `claude-sonnet-5-5` (effort high) · PJ1 관리 계정 uid 1001 · 장치 `managed-3af9a74e-23d3-414f-8145-32edf6280720`
- 집행 증거: 설치된 AppArmor 프로파일 안에서 실행(mcpgw-managed-pj1-claude (enforce)), 정책 해시 `8a9d4eb1b4aa2fb9…` 일치, 사전 점검에서 도구 목록이 정확히 9개
- 결과: 모델 호출 9건 · 원장 판정 9건(id 780~788, 10-14 15:15:32 KST) · 도구 오류 0건(성공 9건) · 해시체인 연결 9/9
- 모델 비용·시간: 26701ms · $0.0568414 · 10턴

| # | 서버.도구 | 인자 | 모델이 받은 결과 | 기대값 포함 | 원장 id | 판정 | 정책 | 업스트림 실행 | 도구 오류 |
| ---: | --- | --- | --- | --- | ---: | --- | --- | --- | --- |
| 1 | `pj1-nine-git.git_status` | 일치 | {   "success": true,   "currentBranch": "master",   "isClean": false,   "stagedChanges": {},   "unstagedChange | 예 | 780 | Allow | `P-AUTHZ-ALLOW-001` | 예 | — |
| 2 | `pj1-nine-git.git_log` | 일치 | {   "success": true,   "commits": [     {       "hash": "216a1a1aaa6e054b9d1147aed71657b88c7c96df",       "sho | 예 | 781 | Allow | `P-AUTHZ-ALLOW-001` | 예 | — |
| 3 | `pj1-nine-git.git_add` | 일치 | {   "success": true,   "stagedFiles": [     "notes.md"   ],   "totalFiles": 1,   "status": {     "current_bran | 예 | 782 | Allow | `P-AUTHZ-ALLOW-001` | 예 | — |
| 4 | `pj1-nine-git.git_commit` | 일치 | {   "success": true,   "commitHash": "5182624df7763dcb52effad209ed47a2e1c68f0f",   "message": "test: PJ1 synth | 예 | 783 | Allow | `P-AUTHZ-ALLOW-001` | 예 | — |
| 5 | `pj1-nine-sqlite.search_objects` | 일치 | {   "success": true,   "data": {     "object_type": "table",     "pattern": "%",     "detail_level": "names",  | 예 | 784 | Allow | `P-AUTHZ-ALLOW-001` | 예 | — |
| 6 | `pj1-nine-sqlite.execute_sql` | 일치 | {   "success": true,   "data": {     "statements": [       {         "sql": "SELECT id, label FROM demo_items  | 예 | 785 | Allow | `P-AUTHZ-ALLOW-001` | 예 | — |
| 7 | `pj1-nine-browser.browser_navigate` | 일치 | ### Ran Playwright code ```js await page.goto('http://pj1-nine-fixture:8080/index.html'); ``` ### Page - Page  | 예 | 786 | Allow | `P-AUTHZ-ALLOW-001` | 예 | — |
| 8 | `pj1-nine-browser.browser_snapshot` | 일치 | ### Page - Page URL: about:blank ### Snapshot ```yaml  ``` | 아니오 | 787 | Allow | `P-AUTHZ-ALLOW-001` | 예 | — |
| 9 | `pj1-nine-browser.browser_evaluate` | 일치 | ### Result {   "title": "",   "text": "" } ### Ran Playwright code ```js await page.evaluate('() => ({ title:  | 아니오 | 788 | Allow | `P-AUTHZ-ALLOW-001` | 예 | — |

## 독립 효과 확인 (기기에서 직접 읽음)
- Git 최근 커밋: `5182624 test: PJ1 synthetic MCP harness` · 작업 트리: `(clean)` · 마지막 커밋 파일: notes.md | 1 +
- SQLite 해시 변화 없음: True · HTML 해시 변화 없음: True

## 직접 확인하는 곳
- 콘솔 `모니터링 → 도구 호출 로그`에서 서버 `pj1-nine-*`, 시각 15:15 전후. 상세에서 요청·판정·오류를 본다.
- 이 폴더: `harness.events.jsonl`(모델·도구 이벤트 원본, 토큰 가림), `prompt.txt`, `calls.json`(호출별 인자·결과), `ledger.json`(원장 행·효과), `preflight.json`, `execution.json`
- 한계: 모델 응답은 비결정적이므로 이 표는 한 번의 실행 결과다. 폐기 가능한 합성 fixture만 사용했다.
