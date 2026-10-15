# PJ1 9개 도구 자연어 시험 로그 (2026-10-14) — 무효

**이 로그의 서버(`pj1-nine-*`)는 에이전트가 스스로 승인해 등록한 비인가 로컬 도구였다. 통과/차단 결과를 거버넌스 증거로 쓰지 않는다.** 서버는 철회했고 원장 행은 append-only라 남아 있다. 보고서의 정정 항목을 먼저 읽는다.

각 폴더의 `index.md`가 모델 호출·Gateway 판정(원장 id)·기기에서 읽은 효과를 한 표로 모은 요약이다. 원본은 같은 폴더의 `harness.events.jsonl`(모델·도구 이벤트, 토큰 가림), `prompt.txt`, `calls.json`, `ledger.json`, `preflight.json`, `execution.json`.

| 폴더 | 하네스 | 원장 id | 내용 |
| --- | --- | --- | --- |
| [run-02-codex-limit](run-02-codex-limit/harness.events.jsonl) | Codex (PJ1 관리 계정) | 없음 | 사전 점검 통과 후 모델 턴이 사용량 한도로 실패 — 도구 호출 0건이라 콘솔 로그 없음 |
| [run-03-claude](run-03-claude/index.md) | Claude Code | 744~752 | 시험 환경 오류(Git 소유권·브라우저 채널)로 도구 오류 7건 |
| [run-04-claude](run-04-claude/index.md) | 〃 | 753~761 | 환경 수정 후 Git·SQLite 성공, 브라우저 상태 유실 |
| [run-05-claude](run-05-claude/index.md) | 〃 | 762~770 | 공유 컨텍스트(+isolated) — 여전히 유실 |
| [run-06-claude](run-06-claude/index.md) | 〃 | 771~779 | 공유 컨텍스트 — 여전히 유실 |
| [run-07-claude](run-07-claude/index.md) | 〃 | 780~788 | 대기 세션 — 여전히 유실 |
| [run-08-claude](run-08-claude/index.md) | 〃 | 789~797 | 정상 9/9처럼 보이나 **무효**(자가 승인 서버, 실패를 구성으로 가림) |
| [run-09-claude-negative](run-09-claude-negative/index.md) | 〃 | 798~800 | 범위 밖 3건 차단 — **무효**(인자를 `const`로 고정한 자가 승인 서버) |

## 콘솔에서 보는 법
`모니터링 → 도구 호출 로그`에서 서버 `pj1-nine-git`·`pj1-nine-sqlite`·`pj1-nine-browser`, 10-14 15:06~15:19(KST). 행을 열면 요청·판정·오류가 나온다. 같은 행은 기기 DB `decisions` id 744~800이다.

## 해석 주의
- 판정이 `Allow`이고 업스트림이 실행됐어도 도구가 오류를 돌려줄 수 있다(run-03). `index.md`의 "도구 오류"·"기대값 포함" 열을 함께 본다.
- 브라우저 8·9번은 run-08에서 새 세션이 fixture 페이지로 시작하는 구성으로 확인했다. 호출 간 상태 유지를 증명하지 않는다(보고서 참조).
