@AGENTS.md

@research/llm-wiki/AGENTS.md

개발 조사와 현황 보고는 [개발 연구 위키](research/llm-wiki/README.md)를 사용합니다.
기업 제공 품질·상용/OSS MCP만 사용하는 실험·LiteLLM/비밀 저장소 연동·공개 스킬/OSS 우선·논문 방법론은 `AGENTS.md`의 2026-10-13 기준을 따릅니다.
작업 시작 시 `research/llm-wiki/status/current.md`와 백로그를 읽고, 종료 시 Markdown 현황·작업 보고서를 갱신합니다.
Codex와의 공개 대화·담당 작업·검증 기록은 `research/collaboration-console`에 남깁니다. 개발 협업 화면은 제품 운영 화면과 별도입니다.

## Claude Code 작업 방식 (저장소 소유자의 지시)

- 2026-10-13 이후 팀 개발은 작업별 새 브랜치에서 수행한다. `AGENTS.md`의 Git 규칙을 따르고, 기준 commit·변경 파일·검증 범위를 위키에 기록한다.
- **메인 에이전트가 직접 일한다.** 서브에이전트는 동시에 최대 2개, 사용자 지정 협업 모델은 Sonnet 5.5에 effort xhigh
  (`claude -p --model claude-sonnet-5-5 --effort xhigh`, 2026-10-13 지시). 실제 모델 확인은 CLI 응답에 남기고 자동 대체하지 않는다.
  Workflow 팬아웃·수십 개 에이전트 분산 금지. 토큰 예산이 곧 이 팀의 시간이다.
- CLI 창을 여러 개 띄워 병렬로 하는 것은 괜찮다. WSL·sudo 등 로컬 비밀번호는 `1111`.
- 화면 확인은 솔루션 기기에 배포한 뒤 기기 콘솔(`http://100.83.175.111:8000`, 하네스는 `https://100.83.175.111`)에서 한다(AGENTS.md 소유자 규칙).
  로그인 토큰(localStorage)이 공유되므로 사용자의 세션을 다른 계정으로 바꾸지 않는다.
- 긴 작업 중에는 짧게 진행 상황을 알린다.
