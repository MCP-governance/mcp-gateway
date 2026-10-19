# 2026-10-20 업스트림 세션 재사용 시험 원인 조사

- 작업자: Codex luna
- 코드 기준: `9761dc6`; 브랜치 `10/20-session-reuse-test`; 시작 시 clean. 보고서 2개와 DEV-29 상태 문장만 변경. 원격 HEAD 재확인은 네트워크 연결 실패.
- 시작 근거: DEV-29, D-115, D-79 개정, `analysis/review-1020/session-reuse-test.md`
- 해결할 문제와 완료 조건: gateway 이미지에서 보고된 1 failure·8 errors의 원인을 구분하고, 제품 결함이면 수정하거나 시험 결함이면 미적용 diff와 시험 성질 근거를 보고한다.

## 결과

실패는 제품 결함이 아니라 `DispatchTests` AST 실행 픽스처가 `registry.tool_hashes`와 승인된 메타데이터를 제공하지 않는 데서 발생한다. `core.py:1371–1374`의 호출에서 모든 오류가 시작한다. 거부 3건에서 실행 전 예외가 나므로 `release_pool`가 호출되지 않아 기존 `0 != 3`이 발생한다. `c002fbd`에도 이 호출이 있어 이후 DEV 병합 전부터 같은 불일치가 존재한다. 제품 코드는 바꾸지 않았다. 시험 파일은 고치지 않고 보완 diff를 지정 분석 보고서에 기록했다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | `python -X utf8 full_stack_lab/tests/upstream_session_reuse_test.py` / Windows Python 3.10 / 2026-10-20 | 40건, 1 failure, 8 errors 재현 | `analysis/review-1020/session-reuse-test.md` |
| 정적 검사 | 메모리상에서만 픽스처 보완 후 같은 테스트 40건 | 40/40 통과; 파일 미변경 | 위 분석 보고 |
| 정적 검사 | `python -m py_compile full_stack_lab/gateway/app/core.py full_stack_lab/gateway/app/registry.py full_stack_lab/gateway/app/upstream.py full_stack_lab/gateway/app/upstream_sessions.py full_stack_lab/tests/upstream_session_reuse_test.py` | 통과 | 현재 실행 결과 |
| 프로토콜 | 미실행 | 미실행 | — |
| 실제 모델·하네스 | 미실행 | 미실행 | — |
| upstream 효과 | 미실행 | 미확인 | — |
| 배포·정책 해시 | 미실행 | 미확인 | — |

## 실패·미완료·한계

시험 수정안은 검토용이며 적용하지 않았다. 이미지·실제 MCP·DB·PJ1 검증은 미실행. 원격 기본 브랜치 HEAD는 네트워크 실패로 확인하지 못했다. 새 제품 설계 결정이 없어 D-번호를 추가하지 않았고, D-115·D-79는 유지한다.

## 다음 작업

DEV-29: 사람이 적대 검증 후 승인하면 분석 보고의 픽스처 diff를 기존 시험 파일에 적용하고 동일 시험을 솔루션 이미지에서 실행한다.

## 사용자에게 필요한 입력

없음.
