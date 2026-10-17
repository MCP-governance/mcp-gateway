# 2026-10-17 정책 번호 체계 대응 정본과 OPA 규칙 레이블 시험

- 작업자: Claude Code (메인이 직접 수행, 서브에이전트 없음)
- 코드 기준: `10/15-wbs-implementation` `c0fbab3`. 같은 날 앞선 [레퍼런스 보강](2026-10-17-policy50-gap-references.md)의 미커밋 변경 위에 이어서 작업했다. 제품 코드·정책·배포·DB 변경 없음, **커밋·푸시하지 않았다**. 새 파일: `analysis/drive-curation/policy-id-mapping.json`, `analysis/drive-curation/opa-labels-probe/`(정책·케이스·실행 스크립트·결과), `tools/build_policy_id_mapping.py`, `tools/check_policy_id_mapping.py`, 이 보고서. 수정: `analysis/drive-curation/README.md`, `README.md`(자료 지도 한 줄), `papers/LIB-K03.md`와 카탈로그의 해당 항목, `papers/policy50-gap-references.md`, 앞선 보고서 2곳, `status/current.md`.
- 시작 근거: 정책 번호 체계 표류(xlsm POL ↔ 독스용 PAC50 ↔ 원본 PAC24 ↔ 런타임 PAC-01~15), [LIB-K01](../../papers/LIB-K01.md) OSCAL 매핑 어휘, [LIB-K03](../../papers/LIB-K03.md) 결정 로그 `labels`, [정책50 의미 매핑](../../analysis/drive-curation/policy-50-crosswalk.json)
- 해결할 문제와 완료 조건: (1) 번호 대응을 OSCAL 어휘의 JSON 정본으로 만들고 기존 crosswalk를 덮어쓰지 않는다. 부분 구현 판정과 런타임 PAC가 못 덮는 공백이 같은 표에서 보여야 한다. (2) 게이트웨이와 같은 OPA 1.20.2에서 규칙 `labels`가 결정 로그에 남는지 격리된 일회성 시험으로 확인한다(compose 스택·기기·PJ1 없이). (3) 매핑 검증 스크립트와 기존 위키 검사 통과.

## 결과

### 1. 정책 번호 체계 대응 정본 — [policy-id-mapping.json](../../analysis/drive-curation/policy-id-mapping.json)

POL 50개 모두에 독스용 PAC·원본 PAC24 대응(원본 시트 이름·본문 비교로 자동 도출)과, 기술통제 35개에는 런타임 PAC-01~15 대응(의미 판단)과 현재 구현 판정, 남는 공백(`gaps`)을 적었다. 관계값은 OSCAL 어휘(`equal-to`, `equivalent-to`, `subset-of`, `superset-of`, `intersects-with`, `no-relationship`)이고 기준은 요구 항목 집합이다(POL이 PAC보다 더 요구하면 `superset-of`). OSCAL 도구는 쓰지 않았다.

**원본 시트에서 확인한 사실** (모두 `check_policy_id_mapping.py`가 다시 계산해 일치를 검사한다):

| 발견 | 내용 |
| --- | --- |
| 같은 번호가 다른 통제 | POL 49개(독스용에 대응 행이 있는 것) 중 **47개**가 독스용 PAC 번호와 다르다. 예: POL-03 보안 업데이트 지원 여부 ↔ PAC25, POL-08 연결 승인·동의 ↔ PAC03. 번호가 같은 것은 POL-01·02뿐 |
| 독스용 ↔ 원본 | 독스용 PAC01~24는 원본 PAC24와 번호·정책명이 1:1로 같고 PAC25~49가 뒤에 붙었다. 본문은 원본 24개 모두 다시 쓰여 공백 제거 동일 0/24 |
| 빈 행·대응 없음 | 독스용 PAC50은 영역만 있고 정책명·본문이 빈 행이다. POL-18(HTTP 요청 출처 검증)에 대응하는 독스용 행이 없다(빈 PAC50이 그 자리인지는 추정) |
| 낡은 교차 참조 | (본) POL-10·30 본문의 `PAC26`, POL-44의 `PAC45`는 독스용 번호로 읽으면 각각 Tool 설명의 악성 지시 검토, 잔존 서버 프로세스 종료다. 독스용 시트의 같은 문장은 `PAC15`·`PAC24`(= POL-26·POL-45)를 쓴다. (본) 시트는 번호를 POL 번호로 바꾸면서 `PAC` 접두를 남겼다. **(본) 시트의 `PACnn`은 `POL-nn`으로 읽어야 한다** |
| (본) POL에만 없는 요구 | 독스용 PAC에는 있고 (본) POL 본문에는 없는 요구가 5개 정책에 있다: POL-21 토큰 그대로 전달 금지(저장소 불변식과 같은 내용), POL-22 게이트웨이 검사로 서버 접근통제 대체 금지, POL-26 개인정보 제공·위탁·국외 이전의 법적 요건, POL-31 개인정보 최소 수집, POL-37 실제 동작 변경 검토와 재승인 후 기록 갱신 |
| 정의 없는 번호 | 원장의 `pac_candidate_id`(PAC-CAND-nn, 23종)는 `policy_ledger.json`에만 있고 어느 문서에도 정의가 없다. 매핑에서 제외 |

**구현 판정과 런타임 PAC 대응** (기술통제 35개, 현재 판정은 [상위 보고서](#한계)의 정적 판정):

| 현재 판정 | 런타임 PAC가 같은 통제(equivalent) | 일부만 덮음(partial) | 대응 없음(none) |
| --- | --- | --- | --- |
| 구현 14 | 2 (POL-11·23) | 9 | 3 (POL-18·30·38) |
| 일부 구현 20 | 1 (POL-20) | 13 | 6 (POL-01·13·14·31·35·39) |
| 미구현 1 | 0 | 0 | 1 (POL-50) |

- 대응이 없는 10개는 PAC15가 아니라 다른 경로(도입 심사, 출력·입력 검사, ingress, 감사 원장)가 맡거나 아직 맡을 곳이 없다. 구현 판정 "구현"인 POL-18·30·38이 PAC 대응이 없다는 것은 PAC15 설계만으로 구현 여부를 읽을 수 없다는 뜻이다.
- PAC가 POL보다 좁은 `superset-of` 9개: POL-10, 19, 22, 25, 26, 27, 37, 40, 44. 각각 PAC 밖의 요구를 `gaps`에 적었다(DNS 재바인딩·OAuth 조회, 에이전트 신원 증명, 외부 서비스 자원 등급, 동의 일치, 호스트의 대상·내용 제시, 재승인 절차 등).
- POL-50은 대응 PAC가 없고, PAC-14가 현재 DB의 철회 상태를 읽는다는 PAC_RUNTIME의 서술에서 **복원이 DB를 되돌리면 PAC-14만으로는 폐기 연결 재활성화를 막지 못할 수 있다**는 설계 추론을 적었다(미시험).

### 2. OPA 규칙 레이블 시험 — [opa-labels-probe](../../analysis/drive-curation/opa-labels-probe/README.md)

저장소 compose와 같은 `openpolicyagent/opa:1.20.2-static` 일회성 서버(127.0.0.1만, 종료 후 삭제)로 5개 사례를 시험했다.

- **`labels` → 결정 로그 `rule_labels`는 1.20.2에서 동작한다.** 두 규칙이 발화하면 `{policy_id: POL-26, runtime_pac: PAC-12, …}`와 `{POL-27, PAC-13}`가 남는다.
- **레이블은 규칙이 발화할 때만 남는다.** 발화하지 않은 규칙의 번호는 없고, 아무것도 발화하지 않으면 패키지 레이블만 남는다. 차단 사유의 정책 번호 기록에는 쓸 수 있으나 '검사하고 통과했다'는 증거는 아니다.
- **`id` 주석은 1.20.2에서 오류 없이 받아들여지지만 `ids`로 남지 않았다.** `ids`는 1.21.2 문서에만 있고 1.21.x는 시험하지 않았다. 정책 번호는 `id`가 아니라 `labels`에 싣는다.
- 게이트웨이에는 OPA 결정 로그를 읽는 코드가 없다(콘솔 출력만 켜짐). 현재 정책 번호는 게이트웨이 `decisions` 원장과 `policy_ledger.json`의 `pac_ids`로 남는다.

[LIB-K03](../../papers/LIB-K03.md)과 [공백 지도](../../papers/policy50-gap-references.md)의 "OPA `ids` 필드 도입 판본" 항목을 이 결과로 갱신했다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사(매핑) | `python -B -X utf8 research/llm-wiki/tools/check_policy_id_mapping.py` (저장소 루트, 2026-10-17) | `ok: true`, 정책 50, 번호 충돌 47, 낡은 참조 3, 판정 14/20/1, 오류·경고 0 | 명령 출력 |
| 음성군(검사기 시험) | 정본을 일부러 바꿔 5번 실행: 낡은 참조 삭제, 알 수 없는 관계값, 원장 ID 추가, 판정 변경, 동일하지 않은 본문에 `equal-to` | 5건 모두 exit 1로 서로 다른 오류 보고. 정본은 원복했고 재생성 결과와 바이트 동일 | 실행 로그 |
| 정적 검사(위키) | `build_wiki.py`, `check_wiki.py`, `check_enterprise_analysis.py` | `ok: true`, papers 203, 마크다운 359개, 오류·경고 0 / 기업 분석 점검 `ok: true` | 명령 출력 |
| OPA 시험 | WSL(kali) docker, `run_probe.sh openpolicyagent/opa:1.20.2-static`, 5개 질의 | 위 관찰, 결정 로그 5건, `opa test` 3/3 PASS | [out 폴더](../../analysis/drive-curation/opa-labels-probe/out-openpolicyagent_opa_1.20.2-static/decision-log-events.jsonl) |
| 프로토콜·실제 모델·하네스 | | 해당 없음(분석·격리 시험). 솔루션 기기·PJ1 미사용 | |
| upstream 효과·배포·정책 해시 | | 해당 없음. 실제 `pac15.rego`·`policy.rego`에는 레이블을 달지 않았고 실제 입력도 넣지 않았다 | |

## 한계

- **런타임 PAC 대응(35개 중 25개의 관계값과 `gaps` 문구)은 Claude의 의미 판단이고 검토 전이다.** `review: claude_judgement_2026-10-17_unreviewed`로 표시했다. 구현 완료·독립 검토 결과가 아니다. 관계값 방향(요구 항목 집합 기준)은 OSCAL 개념 문서의 예와 다르게 보일 수 있어 이 JSON을 OSCAL 문서로 변환하려면 방향을 다시 정해야 한다.
- 현재·개발 후 구현 판정, 자동화 한계, 추가 개발 WBS 번호는 상위 보고서의 엑셀(`output/…개발WBS_2026-10-17.xlsx`, 시트 '정책 대응')을 **읽기 전용 복사본으로 읽어 옮긴 값**이다. 개발 브랜치 `c0fbab3` 정적 판정이며 이 작업에서 독립 재검증하지 않았다. WBS 번호(G02.05 등)는 상위 보고서가 제안한 값으로 확정이 아니다. 엑셀은 사용자가 열어 둔 파일이라 값이 바뀌었을 수 있다.
- 원본 PAC24와 (본) POL 사이 본문 대응은 `unreviewed`다(이름만 같고 본문이 전부 다시 쓰임). 독스용과 (본) POL의 본문 차이 9건은 읽고 판정했다(동치 4, 독스용만 더 요구 5).
- `ledger_policy_ids`는 원장이 스스로 단 `pac_ids`에서 기계적으로 도출한 값이라 같은 통제라는 증거가 아니다(예: MCP-SUPPLY-001은 PAC-08로 표기되지만 POL-01·39와 같은 통제가 아니라고 판단했다).
- OPA 시험은 흉내 낸 최소 정책이다. 실제 게이트웨이 정책에 레이블을 달았을 때 기존 `opa test`·재생 사례가 그대로인지, OPA 1.21.x에서 `ids`가 남는지는 미확인이다. 스크립트는 `docker` 이미지 태그만 바꿔 다시 쓸 수 있으나 새 이미지는 내려받지 않았다.
- 비기술(35개 밖) POL 15개는 런타임 PAC 대응을 평가하지 않았다(`not_assessed`).

## 다음 작업

1. 런타임 PAC 대응 25건의 판단을 사람이 검토하고 `reviewed`로 올린다. 검토 전에는 구현·검수 수치에 쓰지 않는다.
2. (본) POL 본문에 빠진 5개 요구(POL-21·22·26·31·37)를 정책 원본에 반영할지 정책 담당자가 정한다. 낡은 교차 참조 3곳(POL-10·30·44)의 `PAC26`·`PAC45` 표기 정정도 같은 요청에 묶는다. 엑셀 원본은 수정하지 않았다.
3. 실제 `pac15.rego`에 `labels`(policy_id, runtime_pac)를 달아 `opa test`·재생 사례를 돌리고, 통과 증거를 남길 출력 방식(모든 PAC 판정 결과)을 정한다. 백로그 DEV-45(원장·경보)와 연결한다.
4. POL-50: 복원 시험에서 폐기 연결이 되살아나는지 확인하는 항목을 DEV-38 검수에 추가한다(문헌에 없는 항목, 레퍼런스 보고서의 공백 지도 참조).

## 사용자에게 필요한 입력

- 커밋·푸시 여부와 브랜치. 위키 규칙은 작업별 새 브랜치를 요구하는데 공유 폴더에서 브랜치를 바꾸지 않았다. 앞선 레퍼런스 보강의 미커밋 변경과 이번 변경이 같은 워킹 트리에 있다.
- 런타임 PAC 대응 판단(1항)을 누가 검토할지. 자격증명은 필요 없다.
