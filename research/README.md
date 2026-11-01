# research

솔루션 개발용 조사·분석·실험 자료와 현황 보고를 모읍니다.

**[LLM 개발 연구 위키 · Markdown](llm-wiki/README.md)** · **[Codex × Claude 개발 협업 콘솔](collaboration-console/README.md)** · **[개발 현황](llm-wiki/status/current.md)**

논문·기술문서 원본과 Markdown, 상용·오픈소스 분석, 구축 방법론, 실험 대상 MCP와 위협 XLSM을 연결합니다.
Claude Code·Codex 공통 규칙과 갱신 방법은 [위키 AGENTS.md](llm-wiki/AGENTS.md)에 있습니다.
웹 콘솔은 연구 문서 뷰어 대신 실제 소통·작업 담당·진행 상태·검증 결과를 보여 줍니다. `python -X utf8 research/collaboration-console/console.py serve`로 실행한 후 `http://127.0.0.1:18766`에서 봅니다.

| 문서 | 내용 |
| --- | --- |
| [../docs/ai/architecture/README.md](../docs/ai/architecture/README.md) | 현재 구조도 2판(29쪽): 구성·영역·확대·기능 집중·시나리오별 흐름과 생성기 |
| [../docs/ai/OVERHAUL_2026-10-31.md](../docs/ai/OVERHAUL_2026-10-31.md) | `mint` 직원 기능·관리형 호출 후 훅·중앙 경보·커넥터와 기본 기능 분리의 설계·한계 |
| [llm-wiki/status/reports/2026-11-01-console-ux-2.md](llm-wiki/status/reports/2026-11-01-console-ux-2.md) | 호출 결과 축·경보 기간/묶음/미열람·엔드포인트 검색·상세 주소 복원·도구별 동의의 변경·검증 범위 |
| [llm-wiki/analysis/endpoint-stdio/README.md](llm-wiki/analysis/endpoint-stdio/README.md) | 승인 소스 MCP의 엔드포인트 프로세스 실행: 플랫폼별 잠금·직원 실행 계정·요구사항·남은 검증 |
| [../policy/README.md](../policy/README.md) | 팀 정책 90개 PaC와 추적표. 현재 게이트웨이 판정 번들과 별도 |
| [pac15-review/](pac15-review/README.md) | 팀원 PAC-15 Rego 초안: 원본·수정본·300건 시험(`run.sh`), 결함 7종과 수정 |
| [../docs/ai/BENCHMARK_LITELLM.md](../docs/ai/BENCHMARK_LITELLM.md) | LiteLLM MCP 게이트웨이와의 기능 대조(코드 근거), 반영한 것·가져오지 않는 것 |
| [../docs/ai/FIELD_MCP_CANDIDATES.md](../docs/ai/FIELD_MCP_CANDIDATES.md) | field 설치에서 시험할 원격 MCP 후보와 취약 버전·엣지 케이스 |
| [../docs/ai/CONSOLE_UI.md](../docs/ai/CONSOLE_UI.md) | Console이 참고한 LLM 게이트웨이·SIEM·SOAR 레퍼런스 |
| [../docs/dashboard-ux-review.md](../docs/dashboard-ux-review.md) | v1 콘솔 UX 개선·검증 기록(v2 반영 현황 포함) |
| [../docs/PDF-INTEGRATION-2026-09.md](../docs/PDF-INTEGRATION-2026-09.md) | PDF 반영 설계·재설치·검증 기록(v1 기준, v2 이식 메모) |
| [../docs/ai/TERMINATION_MODEL.md](../docs/ai/TERMINATION_MODEL.md) | 논문(CISC-W'26) 종료 판정 모델과 실험 E1~E3 |

날짜별 분석·보고는 작성 당시 증거로 보존합니다. 현재 코드·설정·배포·실기기 효과를 구분하고 후속 정정은 [설계 결정](../docs/ai/DECISIONS.md)과 현황에서 찾습니다.
현재 단독 운영 모드의 root 강제 집행은 D-306, 결과·경보 조회는 D-307이며 이전 승인·화면 설명을 읽을 때 함께 확인합니다.
