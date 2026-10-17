# LIB-K23 · OpenVEX Specification v0.2.0

VEX(Vulnerability Exploitability eXchange)를 가볍게 구현한 JSON 형식이다. 문(statement)은 제품·취약점·상태의 교차이며 시간 순서가 중요하다. 상태 라벨은 not_affected, affected, fixed, under_investigation이고, not_affected에는 표준화된 사유(justification)가 필요하다.

## 출처와 확인 수준

- 공식 출처: [OpenVEX Specification v0.2.0](https://github.com/openvex/spec/blob/main/OPENVEX-SPEC.md)
- 관련 출처: <https://github.com/openvex/spec>
- 유형: 명세 · 2026년 · openvex/spec 저장소, CC0-1.0, 문서 제목 'OpenVEX Specification v0.2.0' · `open_standard`
- 저자·발행: OpenVEX 프로젝트
- 판본: v0.2.0 문서, 파일 마지막 변경 커밋 3a134a07ded8(2026-09-05). 미국 CISA VEX 최소 요건(2023-04) 충족을 표방한다
- 확인일: 2026-10-17 / `full_text_selected_sections_read` — 원문의 지정 절·조문을 직접 읽었다. 읽은 범위: 스펙 개요, VEX 문(statement) 절, Status Labels, Status Justifications 앞부분, 저장소 메타데이터, 파일 최종 커밋.
- 요약 검토: 지정한 절을 원문에서 직접 읽고 요약했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 상태 라벨: not_affected(조치 불필요, justification 필수), affected(조치 권고), fixed(수정 포함), under_investigation(영향 여부 미확정, 이후 VEX 문서로 갱신).
- justification 라벨은 VEX 작업반이 2022년 7월에 정의한 목록이며 component_not_present, vulnerable_code_not_present 등이 있어 배포 정책에 자동으로 쓸 수 있다.
- 문서는 스캐너가 라벨에 따라 동작을 바꾸고 대시보드가 취약점 영향의 시간 경과를 보이는 용도를 든다. 저장소 라이선스는 CC0-1.0이다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-39 | 공급망 출처·취약점 대응 |

## 우리 솔루션 개발에 사용할 곳

- **POL-39**: 스캐너가 보고한 취약점이 서버에 실제로 영향이 없을 때 '영향 없음' 판단을 사유 라벨과 함께 기록해 격리·중지 결정의 오탐을 줄인다. 영향 여부 미확정(under_investigation)은 기한 안에 해소되지 않으면 격리하는 규칙과 연결한다(설계 제안).

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

스펙 본문의 개요·상태 라벨·justification 일부를 읽었다. 문서 구조·제품·취약점 데이터 구조 절은 목차 수준이다. OpenVEX 문서를 생성·소비하는 도구는 시험하지 않았다. v0.2.0은 1.0 이전 판본이다.

GitHub 저장소 메타데이터의 SPDX가 CC0-1.0이다(LICENSE 파일 본문은 열지 않았다). 본문을 복제하지 않는다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
