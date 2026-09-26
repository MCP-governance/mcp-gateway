# docs/ai — 다음 AI 작업자를 위한 문서

처음이면 이 순서로 읽는다: **ARCHITECTURE → RUNBOOK → TESTING**, 그리고 손댈 영역의 문서.
저장소 규칙과 작업 방식은 루트의 [AGENTS.md](../../AGENTS.md).

| 문서 | 무엇 | 언제 |
| --- | --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | v3 정본 설계: 직원 PC의 하네스·관리형 설정·서버별 엔드포인트·LLM 경로·망·신원·디렉터리 | 항상 먼저 |
| [architecture.html](architecture.html) · [architecture.png](architecture.png) | 구성도(archify로 생성, HTML은 브라우저로 — 확대·경로 추적·가이드 뷰) | 그림이 필요할 때 |
| [DECISIONS.md](DECISIONS.md) | 설계 결정 D-01~ 과 이유, 되돌릴 조건 | "왜 이렇게 했지?" |
| [RUNBOOK.md](RUNBOOK.md) | 환경(WSL·포트·비밀번호 1111), `console.sh` 명령, 계정, 자주 하는 일, PC에서 하네스를 손으로 쓰는 법 | 띄우고 돌릴 때 |
| [TESTING.md](TESTING.md) | 검증 층, 개별 실행, 시험 작성 규칙 | 고친 뒤 |
| [MCP_SERVERS.md](MCP_SERVERS.md) | 10종 서버, 설치·실행, 함정, 추가 절차 | 서버를 만질 때 |
| [POLICY.md](POLICY.md) | Rego 구조, 우선순위, 권한 번들과 27칸 기본 판정, 예외, 정책 추가 절차 | 판정을 바꿀 때 |
| [TERMINATION_MODEL.md](TERMINATION_MODEL.md) | 논문 모델 ↔ 코드, C1~C4 규칙, E1~E3 | 종료·폐기 |
| [DATA_MODEL.md](DATA_MODEL.md) | 테이블과 열의 의미, 감사 체인 | DB를 볼 때 |
| [CONSOLE_UI.md](CONSOLE_UI.md) | v3 화면 구조(탭·차트), 디자인 시스템·레퍼런스, 원칙(CSP·이스케이프), 새 화면 추가 | UI |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | 실제로 겪은 증상 → 원인 → 해결 | 막혔을 때 |
| [ROADMAP.md](ROADMAP.md) | 남은 일, 의도적 한계 | 다음 할 일 |
| [BENCHMARK_LITELLM.md](BENCHMARK_LITELLM.md) | LiteLLM MCP 게이트웨이와의 기능 대조(코드 근거), 반영한 것·가져오지 않는 것·main의 차별점 | 기능을 더하기 전, 발표·논문 |

API 요약은 [../API.md](../API.md), 기계용 명세는 `./console.sh openapi` → `docs/openapi/*.json`.

구성도를 고치려면 원본 `architecture.archify.json`을 편집하고 [archify](https://github.com/tt-a1i/archify)로 다시 만든다
(설치 불필요, Node 18+):
```bash
git clone --depth 1 https://github.com/tt-a1i/archify.git /tmp/archify && cd /tmp/archify/archify
node bin/archify.mjs validate architecture <repo>/docs/ai/architecture.archify.json --quality showcase --json
node bin/archify.mjs deliver  architecture <repo>/docs/ai/architecture.archify.json <repo>/docs/ai/architecture.html --quality showcase --json
node bin/archify.mjs visual-check <repo>/docs/ai/architecture.html --json   # 1440~2048 뷰포트 넘침 검사(스크린샷 생성)
```
`architecture.png`는 visual-check의 2048×1320 라이트 스크린샷을 잘라 만든다. 뷰어 UI 문구는 archify가
`en`/`zh-CN`만 지원해서 영어로 나온다(도식 내용은 한국어).
v1 시기의 설계 배경(여전히 유효한 근거)은 [../design/](../design/).
