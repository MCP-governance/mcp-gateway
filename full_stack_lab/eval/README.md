# 통제 적용 전후 효과 비교 평가 도구

제품 외 평가 도구로, 동일한 OPA 정책 입력을 통제 적용 전후의 정책 번들에 각각 보내 판정과 여섯 지표를 비교합니다. 기본 시나리오는 기존 `full_stack_lab/opa/replay_cases.json`의 공통 `base`와 사례별 `patch`를 병합해 독립 입력으로 변환했습니다. 지표 정의는 팀 평가계획 확정 전 잠정안입니다.

사례 파일(`scenarios/`): `baseline.json` 10건(PAC15 재생), `controls-2026-10-18.json` 4건(서버 간 전달), `controls-2026-10-20.json` 10건(전송 목적지·등급 결속 4, 공급자 호스팅 서버 4, 열람 뒤 외부 전송 연쇄 2).

## 실행

Docker와 Python 3이 필요합니다. OPA는 `openpolicyagent/opa:1.20.2-static`을 쓰며 실행 전에 이미지가 로컬에 있어야 합니다.

```bash
python3 full_stack_lab/eval/before_after.py \
  --cases full_stack_lab/eval/scenarios/baseline.json \
  --before none --out /tmp/eval
```

여러 입력 파일은 `--cases file1.json file2.json`처럼 전달합니다. `--before`는 `none` 또는 Git ref, `--after`는 Git ref 또는 기본값 `worktree`입니다. Git ref에서 `full_stack_lab/opa/`를 `git archive`로 꺼내며 `_test.rego` 파일은 제외합니다. `worktree`는 현재 작업 트리의 OPA 디렉터리를 복사합니다. 양쪽 번들은 Docker 안에서 같은 OPA 이미지와 게이트웨이의 `POST /v1/data/mcp/authz/decision` 경로로 평가합니다. 요청은 사례당 `--repeat`회(기본 5회) 실행합니다. 컨테이너는 종료 시 제거합니다.

`--before none`은 정책 없는 직접 사용 기준선으로 모든 사례를 `Allow`, 지연 0 ms로 계산합니다. 이 기준선은 실제 MCP 서버 호출을 실행하지 않습니다.

도커 없이 지표 계산과 레거시 사례 변환을 점검하려면:

```bash
python3 full_stack_lab/eval/before_after.py --self-test
```

결과는 `<out>/result.json`과 `<out>/report.md`에 기록됩니다. JSON에는 Git ref와 commit SHA, 제외 테스트 파일을 뺀 정책 번들의 SHA-256, OPA 이미지 digest, 입력 사례 파일 SHA-256, 사례별 판정·정책 ID·반복별 지연 및 지표가 포함됩니다. 사례는 ID 순으로 정렬되고 JSON 키와 비율 소수점 자릿수는 고정됩니다. 실행 시각은 `run` 필드에만 기록합니다.

## 지표 정의 (잠정안)

실행 가능 판정은 `Allow`, `Alert`, `Restrict`입니다. 그 밖의 판정(`Block`, `Approval`)은 차단으로 셉니다. 공격·정상 사례 수가 0인 비율은 `null`입니다. 판정 지연 p50·p95는 모든 사례 반복 요청의 ms를 합쳐 계산하며, 백분위는 선형 보간 방식입니다.

| 지표 | 계산 |
| --- | --- |
| 공격 차단율 | 차단된 공격 사례 수 / 전체 공격 사례 수 |
| 정상 허용률(유용성) | 실행 가능한 정상 사례 수 / 전체 정상 사례 수 |
| 오탐률 | 차단된 정상 사례 수 / 전체 정상 사례 수 |
| 정밀도 | 차단된 공격 사례 수 / 차단된 전체 사례 수 |
| 차단 사유 일치율 | 기대 `policy_id`가 지정된 차단 공격 중 실제 ID 일치 수 / 해당 사례 수 |
| 판정 지연 p50·p95 (ms) | 각 OPA POST 왕복 시간의 50·95 백분위. `none` 기준선은 0 ms |

## 범위와 한계

이 도구는 같은 입력에 대한 OPA 판정만 비교합니다. 게이트웨이 앞단의 로컬 판정·분류, OPA 외의 게이트웨이 처리, 실제 MCP 실행 효과, 업스트림 상태와 전체 사용자 경험은 범위 밖입니다. 현재 `none` 기준선은 직접 MCP 사용을 모델링한 모든 허용 계산이며 실제 서버에 호출하지 않습니다. 따라서 이 결과만으로 엔드포인트 우회 통제나 제품의 실효성을 주장할 수 없습니다. 시나리오의 기대 판정·라벨도 잠정 기준이므로 팀 평가계획에서 검토해야 합니다.
