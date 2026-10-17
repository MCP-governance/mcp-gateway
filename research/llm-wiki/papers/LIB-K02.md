# LIB-K02 · Open Policy Agent — Policy Testing (OPA v1.21.2 문서)

`opa test`가 `test_` 접두 Rego 규칙을 찾아 PASS·FAIL·ERROR·SKIPPED로 보고하는 방법을 설명한다. `with`로 입력·데이터를 바꾸는 테스트, JSON·YAML 데이터 주도 케이스, `--format=json` 출력, `--fail-on-empty`를 다룬다.

## 출처와 확인 수준

- 공식 출처: [Open Policy Agent — Policy Testing (OPA v1.21.2 문서)](https://www.openpolicyagent.org/docs/policy-testing)
- 관련 출처: <https://github.com/open-policy-agent/opa/releases/tag/v1.21.2>
- 유형: 공식 문서 · 2026년 · OPA 공식 문서 (OPA v1.21.2, 릴리스 2026-10-12) · `official_publication`
- 저자·발행: Open Policy Agent 프로젝트
- 판본: 문서 시점 최신 릴리스 OPA v1.21.2. 저장소 full_stack_lab/compose.yaml은 openpolicyagent/opa:1.20.2-static을 사용한다
- 확인일: 2026-10-17 / `page_text_read` — 공식 페이지 본문을 읽었다(절 단위 정독 아님). 읽은 범위: Policy Testing 페이지 본문 앞부분(시작·보고·형식·검색·결과·데이터 주도 테스트), OPA LICENSE 머리, 최신 릴리스 태그.
- 요약 검토: 출처 페이지 본문과 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 테스트 규칙이 undefined이거나 true가 아니면 FAIL, 런타임 오류는 ERROR, `todo_` 접두 테스트는 SKIPPED로 집계한다.
- 테스트 이름을 잘못 적거나 테스트가 0건 실행돼도 `opa test`는 성공으로 끝나므로 `--fail-on-empty`로 실패시키라고 하며, CI에서 테스트가 실제로 실행되는지 확인하는 용도로도 쓴다고 적는다.
- 테스트 규칙 머리의 변수(`test_x[note]`)로 케이스를 선언하고 JSON·YAML 파일의 데이터를 읽을 수 있다. `--format=json`은 위치·실패·오류·소요시간을, `--var-values`는 실패한 식의 변수 값을 보여 준다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-22 | 정책 변경 시험·동치 분석 |
| POL-37 | 정책 변경 시험·동치 분석 |
| POL-44 | 정책 변경 시험·동치 분석 |
| POL-01~POL-50 | 정책 번호 체계 표류 |

## 우리 솔루션 개발에 사용할 곳

- **POL-22·POL-37·POL-44**: 정책을 바꿀 때 허용·거부·철회 사례를 데이터 주도 케이스로 고정하고(A→B→A 변경, 철회 직후 호출, 범위가 바뀐 요청), 음성군을 같은 파일에 둔다.
- **정책 번호 체계 표류**: 케이스 이름에 POL 번호를 넣고 `--format=json` 결과를 시험 증거에 연결하면 정책 번호별 통과·실패를 기계로 집계할 수 있다(설계 제안).
- **CI 게이트**: `opa test --fail-on-empty --format=json`을 정책 변경의 필수 검사로 둔다. 룰셋을 교체할 때 게이트웨이의 입력·결정 계약이 유지되는지도 같은 방식으로 시험한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

문서 페이지의 앞부분 본문과 옵션 설명을 읽었다. 우리 게이트웨이 정책에 `opa test`를 실행하지 않았다. 문서는 v1.21.2 기준이고 저장소의 OPA 이미지는 1.20.2라서 옵션·출력 형식 차이를 확인해야 한다.

OPA 저장소 LICENSE는 Apache License 2.0이다. 문서 페이지 자체의 별도 이용 조건은 확인하지 않았다. 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
