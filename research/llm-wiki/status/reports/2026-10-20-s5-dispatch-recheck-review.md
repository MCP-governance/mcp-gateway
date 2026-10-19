# 2026-10-20 S5 전송 재확인 적대 검토

- 작업자: Codex luna
- 코드 기준: HEAD 4f486596a3fe6c121e70bad82f4b6cbb13b291d1, 브랜치 10/20-dispatch-recheck-review, 시작 트리 clean. 분석·보고 문서만 추가.
- 시작 근거: DEV-43 / D-140, [S5 분석](../../analysis/review-1020/s5-dispatch-recheck.md), [D-140 구현 지도](../../analysis/dispatch-recheck-1020/README.md).
- 해결할 문제와 완료 조건: 교착, 흐름 입력 차이, 철회·중지 우회, broad exception/cancellation 처리를 반박 중심으로 추적한다. 결함이 확실하면 최소 수정하고 기존 기대값은 바꾸지 않는다.

## 결과

네 가설에서 확실한 코드 결함은 확인되지 않았다. 제품 송신 경로는 동의 유무와 무관하게 재확인 callback을 전달한다. 최초와 재확인의 지문 입력은 동일한 원본 인자이며 observed 차이는 기록용 map에 한정된다. 잠금 순서에서 역순 순환은 확인되지 않았고, 일반 예외는 fail-closed, 취소는 재전파된다.

중요 읽기 결정 원장 append commit과 지문 별도 저장 사이의 짧은 content-mode 비교 불가 구간은 확인했다. fail-closed에 따른 보수 차단 가능성으로 분석에 기록했으며 동작은 변경하지 않았다. 상세 근거와 수정 방향은 [S5 분석](../../analysis/review-1020/s5-dispatch-recheck.md)에 있다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 대역 적대 시험 | python -B -X utf8 full_stack_lab/tests/dispatch_recheck_check.py, Windows Python 3.10.5, 2026-10-20 | 15/15 통과 | 실행 출력, 기존 시험 파일 |
| Python 구문 | python -m py_compile full_stack_lab/gateway/app/dispatch.py full_stack_lab/gateway/app/consent.py full_stack_lab/gateway/app/core.py full_stack_lab/tests/dispatch_recheck_check.py | 통과 | 반환 코드 0 |
| 패치 공백 | git diff --check | 통과 | 반환 코드 0 |
| PostgreSQL·프로토콜 경합 | 미실행 | 미확인 | 없음 |
| PJ1·실제 MCP·upstream 효과 | 미실행 | 미확인 | 없음 |

## 실패·미완료·한계

AsyncMock은 PostgreSQL 행 잠금, READ COMMITTED/EvalPlanQual, lock manager deadlock detection, commit 응답 유실을 증명하지 않는다. 잠금 그래프는 소스 기반 결론이다. PG 동시성·PJ1 효과 확인은 남는다. 코드·신규 시험·기존 시험 기대값은 변경하지 않았다.

## 다음 작업

DEV-43은 코드 적대 검토와 대역 시험 확인, 실 DB·PJ1 검수 대기다. 격리 PostgreSQL에서 계정 중지·동의 철회·종료의 선행/후행 commit, advisory 대기 중 원장 append, snapshot, timeout/cancel을 계측하고 request_id별 intent와 호출 수를 대조한다.

## 사용자에게 필요한 입력

없음.
