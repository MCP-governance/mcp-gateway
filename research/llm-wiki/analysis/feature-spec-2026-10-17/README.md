# 기능명세서·개발 WBS (2026-10-17)

보고용 기능명세서, 현재 개발과 추가 개발을 나눈 개발 WBS, 기술통제 정책 35개의 대응 현황을 한 통합 문서로 만든 기록이다. 구조화 정본은 [feature-spec.json](feature-spec.json), 검토용 통합 문서는 [feature-spec.xlsx](feature-spec.xlsx)이며 둘 다 [build_feature_spec.py](../../tools/build_feature_spec.py)가 다시 만든다.

- 코드 기준: `10/15-wbs-implementation` `c0fbab3`(기기 배포 `b639432` 포함). 이 작업은 제품 코드·정책·배포를 바꾸지 않았다.
- 입력: [WBS 스냅샷](../development-wbs/snapshot.json)(10-15 단계 점수), [정책 추출본](../../threats/extracted/policies.json)의 `(본)정책 최종본` POL-01~50 정책명.
- 정책 판정 근거: 10-17 보고의 정적 판정(구현 14·일부 20·미구현 1). [정책 번호 체계 대응](../drive-curation/policy-id-mapping.json)과 [공백 레퍼런스](../../papers/policy50-gap-references.md)를 함께 본다.

## 시트

| 시트 | 내용 | 수 |
| --- | --- | ---: |
| 기능명세서 | 대분류·기능·설명·대응 정책·구현 수단·상태·비고. 상태는 구현 완료(검수 전) 34, 일부 구현 4, 개발 예정 16, 자동화 범위 제외 10 | 64 |
| 개발 WBS | 기존 G01~G10 40개 + 실행기 G01.05 + 추가 개발 16개. 구현·회귀 시험·기기 배포·실기기 확인·완료 검수 점수(0/0.5/1), 진척률·상태 수식, 일정 제안안 | 57 |
| 정책 대응 | 기술통제 35개의 현재/개발 후 상태와 관련 추가 개발, 자동화 한계 | 35 |

진척률: 현재 개발 41개 57.8%, 추가 개발 포함 전체 41.6%. 정책 구현 비율(구현 + 일부 구현 × 0.5): 현재 68.6%, 개발 후 90.0%. 최종 검수 완료는 0건이다.

## 상태의 뜻

- **구현 완료(검수 전)**: 코드가 있고 기기에 배포된 상태. 실기기 확인과 최종 검수를 뜻하지 않는다. 단계별 상태는 개발 WBS 시트의 점수로 본다.
- **일부 구현**: 구현 단계 점수 0.5.
- **개발 예정**: 확실히 구현 가능한 것만 넣었다. 일정 열은 팀 확정 전 제안안이다.
- **자동화 범위 제외**: 솔루션이 관측할 수 없어 구현하지 않는 것. 비고에 대체 통제를 적었다(예: 위임을 주장하는 요청은 거부).

## 2026-10-17 리뷰 반영

팀 리뷰 9건을 코드와 대조해 반영했다.

| 리뷰 | 코드 대조 결과 | 반영 |
| --- | --- | --- |
| MCP 요청·응답 중계 누락 | `mcp_facade.py`가 `initialize`·`ping`·`tools/list`·`tools/call`만 중계하고 나머지는 거부 | 구현 완료 행 추가 |
| 4가지 결과 집행 | 실제 결과는 Allow·Alert·Restrict·Approval·Block 5종(`db/init.sql` CHECK). 우선순위는 성립한 후보를 모두 모은 뒤 관리대장 `priority`로 선택(`opa/policy.rego`), 관찰 모드는 `would_decision` 기록 | 5종과 선택 방식으로 행 추가(리뷰의 4종·고정 순서는 정정) |
| 변경 영향 판정·선택적 제한 | 사용 승인 도구의 설명·스키마 변경만 차단하고 버전·미승인 도구 변경은 기록(`core.py` D-69). 차단 단위는 서버 전체 | 개발 예정 행·WBS G02.06 추가, 계약 잠금 비고 수정 |
| 판정 증적 상세 필드 | `decisions`에 trace_id·request_id·policy_input·policy_id·policy_version·reason·decision·restrictions·upstream_attempted/executed·environment·prev/entry_sha256 저장. 응답은 해시·크기·처리 결과만(`response_evidence`), 300자 넘는 인자는 앞 120자와 해시만(`_audit_payload`) | 구현 완료 행 추가 |
| 적용 전후 효과 비교 | `replay.py`(기록된 입력을 후보 정책에 재생)와 관찰 모드는 정책 변경 비교이고 통제 효과 평가가 아님 | 제품 외 평가 도구로 분리, WBS G10.05. 평가지표 6개의 정의는 위키에 없어 팀 평가계획으로 확정 필요 |
| SIEM 연계 | OTLP 추적(Jaeger)과 해시 붙은 감사 내보내기만 있음. syslog·CEF·OCSF 전달 없음 | 개발 예정(확장) 행·WBS G06.06 추가 |
| 에이전트 신원·위임 표현 | 위임은 `PAC-05-DELEGATION-UNSUPPORTED`로 거부, 하네스 신원은 기록만 | 자동화 범위 문장과 신원 행 비고 수정 |
| 엔드포인트 통제 범위 | 게이트웨이 + 엔드포인트 에이전트 + 격리 실행기 구조 | 솔루션 구성 문장 추가 |
| 개발 완료 ≠ 검증 완료 | WBS 완료 검수 점수 0/41 | 상태 이름 변경과 안내 문장 추가 |

## 원본과 산출물

| 파일 | 내용 | SHA-256 |
| --- | --- | --- |
| [originals/drive-2026-10-17T062108Z.xlsx](originals/drive-2026-10-17T062108Z.xlsx) | 팀 Drive 공유본(소유 soeunbob, 수정 2026-10-17 06:21:08Z). 첫 판에 기능명세서 대분류 셀 병합만 더해진 판 | `96b160a579f2ac2f4b939e18bd32d9da064a725da79da038dff533b7b6cb3e92` |
| [feature-spec.xlsx](feature-spec.xlsx) | 리뷰 반영판. 대분류 병합 서식 유지 | 생성 시마다 바이트가 달라진다(문서 속성 시각) |

Drive 링크: https://docs.google.com/spreadsheets/d/1wAMcbyTRWe6imdzRKBVoS3shoMDENwz9 — Drive 연결 도구는 파일 내용을 교체할 수 없어 리뷰 반영판의 Drive 반영(새 버전 업로드)은 이 기록 시점에 하지 않았다.

## 한계

2026-10-18 후속: G02.06(DEV-52)·G06.06(DEV-61)은 D-127·128로 구현하고 [로컬 단위·HTTP 시험](../selective-restriction-siem/README.md)을 수행했다. 위의 10-17 상태·진척률은 당시 기록으로 보존한다. 제품 배포·실제 OSS MCP·하네스·SIEM 검수는 남았으며 이 문서의 Excel/정본 점수는 재산정하지 않았다.

- 기존 작업과 POL 번호의 연결, 추가 개발 일정은 작성자 판단이다. WBS 원본 스냅샷에는 POL 연결이 없다.
- 단계 점수는 10-15 스냅샷 값이며 이번에 다시 시험하지 않았다. G01.05 점수는 10-15 밤 DEV-38 보고 기준이다.
- 수식(COUNTIF·AVERAGE·AVERAGEIF·IF)은 파이썬으로 같은 값을 계산해 범위를 대조했다. 이 PC의 LibreOffice가 동작하지 않아 계산값을 저장하지 못했고, Excel이 열 때 다시 계산하도록 설정했다.
