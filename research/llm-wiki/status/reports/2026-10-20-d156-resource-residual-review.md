# 2026-10-20 D-156 자원 잔존 적대 검토

- 작업자: Codex luna
- 코드 기준: `10/20-resource-residual-review`, 시작 commit `877a5138574308fd18ee72817f3d9712f6af114e`, 시작 작업 트리 clean. 검토 변경 미커밋.
- 시작 근거: DEV-08, D-156, [적대 검토](../../analysis/review-1020/d156-resource-residual.md), [원자 요구사항](../../analysis/resource-residual/README.md).
- 완료 조건: 지정된 네 반박 항목을 코드·시험·문서와 대조하고, 확실한 결함은 최소 수정하며 결과와 미실행 검증을 기록한다.

## 결과

지정한 네 항목에서 D-156이 만든 확실한 결함은 확인되지 않았다. 종결 케이스 재판정은 거부되며, 재개하면 기존 증거를 유지한 채 현재 등급만 다시 산정한다. 증거 행은 추가만 되지만 케이스의 등급·상태는 갱신 가능한 스냅샷이다. 갱신 토큰은 매 요청에서 계정 활성·관리형 인증 여부·OIDC 전환을 확인한다. 자원 서버 수락 증거가 없다는 이유만으로 C3가 미충족되지는 않는다. 상태 저장 토큰의 발급자 비활성 증거가 전파 확인에 쓰이며, 상태 비저장 토큰의 만료 공백은 T2 한계로 남는다. 관리자 API를 통한 수동 증거 등록은 가능하지만 그 자체가 외부 증거를 독립 검증하지는 않는다.

코드 수정·기존 시험 기대값 변경은 하지 않았다. 추가 시험도 결함 근거가 없어 만들지 않았다. 상세 근거와 각 경계는 [검토 결과](../../analysis/review-1020/d156-resource-residual.md)에 남겼다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 신규 순수/대역 시험 | `python -B -X utf8 full_stack_lab/tests/resource_residual_check.py -v` | 13/13 통과 | 터미널 출력 |
| Python 구문 | `python -m py_compile` 대상 제품 2개·시험 3개 | 통과 | 터미널 종료 코드 0 |
| CI 범위 pyflakes | `python -m pyflakes full_stack_lab/gateway/app/*.py full_stack_lab/tests/*.py full_stack_lab/supply_chain/*.py endpoint-agent/*.py full_stack_lab/field/pc/mcpgw_pc.py` | 미실행: Python 3.10 환경에 pyflakes 모듈 없음 | `No module named pyflakes` |
| 위키 링크·구조 | `python research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | 오류 0, ignored 원본 누락 경고 존재 | 터미널 출력 |
| 공백 검사 | `git diff --check` | 통과 | 터미널 종료 코드 0 |
| PostgreSQL/Gitea | `resource_residual_pg_check.py` | 미실행 | 기기 전용 |
| 실제 모델·하네스·효과 | 솔루션 기기·PJ1 | 미실행 | 없음 |

## 실패·미완료·한계

- 원격 HEAD 조회는 github.com:443 연결 실패로 확인할 수 없었다.
- PostgreSQL/Gitea 시험, 전체 종료 랩, 배포, PJ1, 실제 자원 서버·실행기 효과는 검증하지 않았다.
- append-only 증거와 달리 판정 등급은 현재 스냅샷이다. 종전 판정의 별도 불변 이력 저장은 이번 검토 범위에서 확인되지 않았다.
- 외부 자원 서버가 introspection 결과를 캐시하거나 미고지·복제 자격을 보유하는 경우는 별도 시험 범위다.

## 다음 작업

DEV-08의 기존 후속 절차에 따라 기기의 격리 PostgreSQL/Gitea 시험, 솔루션 배포 및 PJ1 하네스 검증을 진행한다. 다른 사람이 사용 중인 랩은 재시작하지 않는다.

## 사용자에게 필요한 입력

없음.
