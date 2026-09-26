@AGENTS.md

## Claude Code 작업 방식 (저장소 소유자의 지시)

- **메인 에이전트가 직접 일한다.** 서브에이전트는 동시에 최대 2개, 모델은 Sonnet 5에 effort high~max
  (Agent 도구로 effort를 못 정하면 `claude -p --model claude-sonnet-5 --effort high` CLI로 띄운다, 2026-09-25 지시).
  Workflow 팬아웃·수십 개 에이전트 분산 금지. 토큰 예산이 곧 이 팀의 시간이다.
- CLI 창을 여러 개 띄워 병렬로 하는 것은 괜찮다. WSL·sudo 등 로컬 비밀번호는 `1111`.
- 브라우저 확인은 Claude 내장 브라우저로 `http://localhost:${CONSOLE_PORT}`(이 노트북은 18000).
  사용자가 같은 창을 쓰고 있을 수 있으니 **백그라운드 탭**에서 확인하고, 로그인 토큰(localStorage)이
  공유되므로 다른 계정으로 로그인해서 사용자의 세션을 바꾸지 않는다(역할 확인은 curl로).
- 긴 작업 중에는 짧게 진행 상황을 알린다.
