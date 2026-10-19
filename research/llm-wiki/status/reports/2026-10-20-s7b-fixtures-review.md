# 2026-10-20 S7b 기존 시험 대역 보정 적대 검토

- 작업자: Codex luna
- 코드 기준: `321fa5655261378c6900dafba9b87be3072448f4`, 작업 트리 시작 시 깨끗함, 브랜치 `10/20-output-contract-fixtures-review`
- 시작 근거: DEV-44 / D-149 / [기존 시험 대역 보정 기록](2026-10-20-output-contract.md#기존-시험-대역-보정)
- 해결할 문제와 완료 조건: HEAD가 바꾼 기존 시험 세 파일의 각 diff hunk에 대해 assert 약화, 검사 범위 축소, 새 제품 동작을 숨기는 대역, AST 실제 정의 여부를 분류하고 hunk별 A/B/C를 분석 정본에 기록한다.

## 결과

[S7b hunk 판정](../../analysis/review-1020/s7b-fixtures.md)에 7개 hunk를 기록했다. 모두 A(채택)다. 기존 assert·입력·기대 정책 결정은 바뀌지 않았다. 두 출력 경로 대역은 각각 오류 봉투/세션 문맥과 dispatch 수명주기 시험의 범위에 국한되며, 출력 검증·판본 렌더링은 별도 시험이 직접 검사한다. 새 `ContractClient`, 출력 계약 예외·비교 함수와 등록부 비교 함수는 실제 모듈 AST 정의에서 가져온다. 제품 코드와 시험 코드는 수정하지 않았다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 변경 범위 | `git show --format=fuller --find-renames HEAD -- full_stack_lab/tests/`, `git diff --unified=0 HEAD^ HEAD -- full_stack_lab/tests/`, 2026-10-20 로컬 | 7개 hunk 확인, assert 변경 없음 | HEAD commit 및 작업 트리 |
| 정적 대조 | 제품 정의 AST, 시험 대역·assert, D-149 분석/결정 및 기존 시험 파일을 읽어 대조 | 7개 A, B/C 없음 | [hunk별 판정](../../analysis/review-1020/s7b-fixtures.md) |
| 시험 실행 | 미실행 | 이 검토 턴에서 실행하지 않음 | 해당 없음 |
| 이미지·실제 MCP·PJ1 | 미실행 | 미실행 | 해당 없음 |

## 실패·미완료·한계

이번에는 시험을 다시 실행하지 않았다. `A` 판정은 기존 시험 변경의 검토 결과이며 D-149 출력 동작의 이미지·DB·SDK·실기기 검증 증거를 추가하지 않는다. 기존 시험 변경 필요는 없음.

## 다음 작업

DEV-44의 후속 기기 이미지 직접 실행과 SDK·DB 전환·실제 MCP/PJ1 검증을 기존 출력 계약 보고의 절차대로 수행한다.

## 사용자에게 필요한 입력

없음.
