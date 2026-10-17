# LIB-K22 · Common Security Advisory Framework (CSAF) Version 2.0 — OASIS Standard

보안 권고를 기계가 읽는 JSON 구조로 교환하는 OASIS 표준이다. 프로파일(Base, 보안 사고 대응, 정보 권고, 보안 권고, VEX)과 기계 검증 시험(Tests), 제공자·집계자 스키마를 정의한다.

## 출처와 확인 수준

- 공식 출처: [Common Security Advisory Framework (CSAF) Version 2.0 — OASIS Standard](https://docs.oasis-open.org/csaf/csaf/v2.0/csaf-v2.0.html)
- 관련 출처: <https://docs.oasis-open.org/csaf/csaf/v2.0/os/csaf-v2.0-os.html>
- 관련 출처: <https://docs.oasis-open.org/csaf/csaf/v2.1/csaf-v2.1.html>
- 유형: 표준·RFC·권고 · 2022년 · OASIS Standard, 2022-11-18 (OASIS CSAF TC) · `oasis_standard`
- 저자·발행: Langley Rock, Stefan Hagen, Thomas Schmidt (편집)
- 판본: 2.0 OASIS Standard(2022-11-18). 2.1은 2026-09-11 기준 Committee Specification Draft 03이라 표준으로 등록하지 않았다
- 확인일: 2026-10-17 / `full_text_selected_sections_read` — 원문의 지정 절·조문을 직접 읽었다. 읽은 범위: 머리말(단계·날짜·편집자), 목차, §4.5 시작부, 고지문, 2.1 초안 머리말·디렉터리, TC 페이지.
- 요약 검토: 지정한 절을 원문에서 직접 읽고 요약했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- §4.5 Profile 5: VEX는 특정 제품이 취약점의 영향을 받는지 또는 받지 않는지와 그 이유를 밝히는 용도로 쓰도록(SHOULD) 하고 문서가 만족할 요건을 나열한다(세부 요건은 읽지 않았다).
- §6은 필수 시험을 나열한다(제품 ID 정의 누락·중복·순환 등). 표준 문서는 JSON 스키마(CSAF, aggregator, provider)를 함께 제공하고 CVRF 1.2를 대체한다.
- 저작권 고지는 문서 전체 복제·배포를 허용하되 문서 자체의 변경은 금지한다(OASIS IPR 정책).

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-03 | 공급망 출처·취약점 대응 |
| POL-39 | 공급망 출처·취약점 대응 |

## 우리 솔루션 개발에 사용할 곳

- **POL-03**: 서버 제공자의 보안 공지가 CSAF로 게시되는지 확인해 '유지보수·보안 공지·수정 지원 확인'을 자동 수집으로 바꾼다.
- **POL-39**: CSAF의 제품 상태·VEX 정보를 알려진 취약점 대응 기록(영향 없음 판단 근거 포함)에 연결한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

머리말·목차·Profile 5 시작부·고지문만 읽었다. 2.1은 초안 단계다. MCP 서버 제공자 중 CSAF를 게시하는 곳은 확인하지 않았다.

OASIS 저작권 고지: 구현을 위한 파생물 제작과 문서 복제·배포는 고지를 유지하면 허용되나 문서 자체는 수정할 수 없다. 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
