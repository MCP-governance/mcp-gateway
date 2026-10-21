# 2026-10-21 DEV-03 위협표 현 판본 검토 갱신

- 작업자: Codex sol 자동 운영, 임시 통합 담당
- 브랜치: `10/21-dev03-review-refresh`, 시작 `204579981ac02956a3ee40301f251ee99af9de6e`(원격 HEAD `main`, 작업 트리 깨끗함 확인 후 fetch·ff-only).
- 시작 근거: DEV-03, 원본 위협표 24개 정책, [현 판본 대조](../../analysis/threat-trace-review-1021/README.md).
- 완료 조건: 의미 변경 재검토·이전 바이트 보존·고정 참조 갱신·기존 단언 무변경·로컬 회귀 실패 증가 없음·위키 오류0·Gemini 독립 검토.

## 결과

20개 파일·71개 낡은 참조를 기준 커밋 이후 diff 및 함수 AST/호출 경계와 대조했다. 원본 요구 24행을 유지하고 9개 한계 문장을 정정했다. 출처 증명·새 승인 경로·관할 팩 활성 조건·로컬 작업 정지에 코드 참조11개를 추가했다. [이전 JSON 원본](../../analysis/threat-trace-review-1021/review-2026-10-20.json)과 해시·행별 [변경 검토](../../analysis/threat-trace-review-1021/delta-review.json)를 보존했다. 생성 화면에 이전 검토/후속 분석 연결을 추가하고 새 AST 추출 시험2건을 작성했다.

핵심 정정은 증명 미제공은 차단이 아닌 확인 안 됨, 위험 입력은 신청자 직접 입력 외에 도구 기반 제안 경로가 있음, 관할 팩은 기본 비활성, 공개 주입 corpus의 후속 재현율·오탐 보고가 존재함이다. 과거 수치를 현재 측정으로 쓰지 않았다. 제품 코드·보안 통제·정책 의미·기존 시험 기대값/단언은 변경하지 않았다. 새 설계 결정은 없어 D-번호를 추가하지 않았다.

## 검증

Python은 `C:/Users/bobysg/bob/프로젝트/.venv-mcpgw/Scripts/python.exe` 3.12를 사용했다. 원시 실행 결과는 후속 검증 기록을 따른다.

| 확인 | 결과 | 근거 |
| --- | --- | --- |
| 변경 전 전체 로컬 회귀 | 89통과·1실패·18생략 | Agent Hub runtime/dev03-baseline.json, 이번 실행 |
| 위협 추적 기존4·새 AST/이력2 | 6/6 통과 | `python -m unittest discover -s full_stack_lab/tests -p 'threat*check.py' -v` |
| 매핑 재생성 | 24행·낡은 파일0 | `python research/llm-wiki/tools/map_threats.py` |
| 최종 전체 로컬 회귀 | 91통과·0실패·18생략(파일109개) | [현재 실행](../../analysis/threat-trace-review-1021/final-suite.json), 기준선 대비 실패1 감소·새 파일1 추가 |
| 위키·정적 검사 | 위키 오류0, pyflakes0·diff 공백 오류0 | [명령·시각·출력](../../analysis/threat-trace-review-1021/validation.json) |
| Gemini 독립 적대 검토 | 요청 전 | 아래 후속 기록 |
| 실제 MCP·기기 배포·PJ1·PG | 미실행 | 이번 범위 밖 |

## 실패·미완료·한계

DEV-81 F1은 이전 브랜치 `10/21-dev81-direct-helper`의 기존 헤더 시험 추가 실패와 독립 검토 불명확으로 보류라 이번에 재구현하지 않았다. 기존 기준선의 유일 실패는 `threat_trace_mapping_check.py`다. 이번 정적 참조 정합성 회복은 전체 보안 요구 충족·실제 외부 효과·현재 배포 검수를 뜻하지 않는다.

공개 스킬·OSS 후보2개의 commit·본문 해시·라이선스·최근 push·실제 사용 범위는 [후보 기록](../../analysis/threat-trace-review-1021/public-candidates.json)에 있다. 외부 스킬 실행·설치·코드 재사용은 하지 않았다. 라이선스 경로 조회 중 404는 파일 대소문자를 확인해 정정했고 최종 고정 원문을 확보했다.

## 다음 작업

독립 검토 A/B/C와 높음 발견 여부를 확인해야 병합할 수 있다. 실제 컨테이너·기기·PJ1 검증과 DEV-81 강제 승격은 메인 복귀 후 판단이다. 현재 현황 문서는 공통 레인 규칙에 따라 보존하고 백로그와 이 보고서에 결과를 연결한다.

## 사용자에게 필요한 입력

없음. 미확정 판단은 queue.md에 남긴다.
