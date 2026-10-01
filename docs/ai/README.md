# docs/ai — 다음 AI 작업자를 위한 문서

처음이면 이 순서로 읽는다: **ARCHITECTURE → RUNBOOK → TESTING**, 그리고 손댈 영역의 문서.
저장소 규칙과 작업 방식은 루트의 [AGENTS.md](../../AGENTS.md).

| 문서 | 무엇 | 언제 |
| --- | --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | v3 정본 설계: 직원 PC의 하네스·관리형 설정·서버별 엔드포인트·LLM 경로·망·신원·디렉터리 | 항상 먼저 |
| [SECURITY_BOUNDARIES.md](SECURITY_BOUNDARIES.md) | 실제 통제 범위, Kong·LiteLLM·Microsoft 비교, 우회 위협 모델, 재설계와 실제 MCP 검증 | 통제·시험·제품 주장을 정할 때 |
| [CONTROL_PLANES_2026-10-01.md](CONTROL_PLANES_2026-10-01.md) | D-62/D-63 통제 상태·증거·응답 통제, 실제 원장 대조와 UI 배포 | 이번 인계를 이어서 볼 때 |
| [PJ1_SIGNALS_2026-10-01.md](PJ1_SIGNALS_2026-10-01.md) | D-59 뒤 실제 PC(pj1)의 신호 81건·하네스 12회를 기기 원장과 대조, 찾은 결함과 조치 | 실기기 최신 검증 결과를 볼 때 |
| [REMASTER_2026-10-01.md](REMASTER_2026-10-01.md) | 사용자 요청 8개, 원격 MCP 오류 원인, 실제 시험과 미완료 경계 | 이번 개편을 이어서 할 때 |
| [BENCHMARK_UI_ONBOARDING_2026-10-01.md](BENCHMARK_UI_ONBOARDING_2026-10-01.md) | MS·IBM·LiteLLM 고정 커밋의 UI·조직 관리 분석, 채택한 흐름과 OS 통제 경계 | UI·가입·단말 통제를 바꿀 때 |
| [FOLLOWUP_VALIDATION_2026-10-01.md](FOLLOWUP_VALIDATION_2026-10-01.md) | 인계 뒤 남은 빈 곳의 실측과 보강(D-56), 실제 LLM 하네스(Codex·Claude Code)가 솔루션 기기 게이트웨이를 거친 업무 10회 | 최신 검증 범위와 결과를 볼 때 |
| [OVERHAUL_VALIDATION_2026-09-30.md](OVERHAUL_VALIDATION_2026-09-30.md) | Claude 변경 인계, 클린 재구축, 실제 일곱 MCP·DB 효과·SSH VM·배포 확인 | 그 전 단계의 검증 |
| [PAC_MAPPING.md](PAC_MAPPING.md) | PAC-01~15의 집행 위치와 남은 경계 | 정책 초안과 실제 구현을 대조할 때 |
| [BENCHMARK_IBM_CONTEXTFORGE.md](BENCHMARK_IBM_CONTEXTFORGE.md) | IBM ContextForge·공개 CPEX 소스 분석 정정본 | IBM 비교·플러그인·호출량 통제 검토 |
| [BENCHMARK_MICROSOFT.md](BENCHMARK_MICROSOFT.md) | MS Gateway·Wassette의 코드 근거와 비교 한계 | Microsoft·실행 경계 검토 |
| [architecture.html](architecture.html) · [architecture.png](architecture.png) | 구성도(archify로 생성, HTML은 브라우저로 — 확대·경로 추적·가이드 뷰) | 그림이 필요할 때 |
| [DECISIONS.md](DECISIONS.md) | 설계 결정 D-01~ 과 이유, 되돌릴 조건(실기기 배치·도입 자동 검증은 D-42~D-46) | "왜 이렇게 했지?" |
| [RUNBOOK.md](RUNBOOK.md) | 환경(WSL·포트·비밀번호 1111), `console.sh` 명령(field 포함), 계정, 자주 하는 일, PC에서 하네스를 손으로 쓰는 법 | 띄우고 돌릴 때 |
| [TESTING.md](TESTING.md) | 검증 층, 개별 실행, 시험 작성 규칙 | 고친 뒤 |
| [MCP_SERVERS.md](MCP_SERVERS.md) | 10종 서버, 설치·실행, 함정, 추가 절차 | 서버를 만질 때 |
| [POLICY.md](POLICY.md) | Rego 구조, 우선순위, PAC15·검토된 capability, 예외, 정책 추가 절차 | 판정을 바꿀 때 |
| [TERMINATION_MODEL.md](TERMINATION_MODEL.md) | 논문 모델 ↔ 코드, C1~C4 규칙, E1~E3 | 종료·폐기 |
| [DATA_MODEL.md](DATA_MODEL.md) | 테이블과 열의 의미, 감사 체인 | DB를 볼 때 |
| [CONSOLE_UI.md](CONSOLE_UI.md) | v3 화면 구조(탭·차트), 디자인 시스템·레퍼런스, 원칙(CSP·이스케이프), 새 화면 추가 | UI |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | 실제로 겪은 증상 → 원인 → 해결 | 막혔을 때 |
| [ROADMAP.md](ROADMAP.md) | 남은 일, 의도적 한계 | 다음 할 일 |
| [BENCHMARK_LITELLM.md](BENCHMARK_LITELLM.md) | LiteLLM MCP 게이트웨이와의 기능 대조(코드 근거), 반영한 것·가져오지 않는 것·main의 차별점 | 기능을 더하기 전, 발표·논문 |
| [BENCHMARK_GATEWAYS.md](BENCHMARK_GATEWAYS.md) | LiteLLM 1.104·ContextForge·Kong·BeyondTrust 재조사와 Claude Code·Codex의 기본 커넥터 통제 키(코드·문서 근거) | 커넥터·도구 통제를 바꾸기 전 |
| [FIELD_MCP_CANDIDATES.md](FIELD_MCP_CANDIDATES.md) | field 설치에서 시험할 원격 MCP 후보, 취약 버전·엣지 케이스(자동 등록하지 않음) | 실기기 시연 준비 |

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
