# LIB-K08 · NIST SP 800-162: Guide to Attribute Based Access Control (ABAC) Definition and Considerations

ABAC를 주체·객체·요청 동작·환경 조건의 속성을 정책·규칙·관계와 비교해 접근을 정하는 논리적 접근 제어 방법으로 정의하고, 조직 안팎 정보 공유에 ABAC를 쓸 때의 고려 사항을 정리한 연방기관 지침이다.

## 출처와 확인 수준

- 공식 출처: [NIST SP 800-162: Guide to Attribute Based Access Control (ABAC) Definition and Considerations](https://csrc.nist.gov/pubs/sp/800/162/upd2/final)
- 관련 출처: <https://doi.org/10.6028/NIST.SP.800-162>
- 관련 출처: <https://nvlpubs.nist.gov/nistpubs/specialpublications/NIST.SP.800-162.pdf>
- 유형: 표준·RFC·권고 · 2014년 · NIST Special Publication 800-162, 2014-01 (2019-08-02 갱신 반영), 47쪽 · `official_publication`
- 저자·발행: Vincent C. Hu, David Ferraiolo, Rick Kuhn, Adam Schnitzer, Kenneth Sandlin, Robert Miller, Karen Scarfone
- 판본: 2014년 1월판, 2019-08-02 갱신 반영(CSRC 페이지 'upd2'). 폐기·대체 표시는 2026-10-17 페이지에서 확인되지 않았다
- 확인일: 2026-10-17 / `full_text_selected_sections_read` — 원문의 지정 절·조문을 직접 읽었다. 읽은 범위: CSRC 페이지(초록·판본), PDF 표지·고지·목차, §2.2, §2.4.2, §3.3.1, §3.4.1 도입부.
- 요약 검토: 지정한 절을 원문에서 직접 읽고 요약했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- §2.2·2.3은 ABAC를 주체 속성·객체 속성·환경 조건을 접근 결정 시점의 값으로 정책과 맞춰 보는 방식으로 정의한다.
- §2.4.2는 속성이 이름·허용 값·스키마를 갖고 주체·객체에 연결돼야 하며, 속성은 권한 있는 기관이 발급·저장·관리해야 한다고 설명한다. 조직 간 공유 속성은 게시·검증·갱신·폐지되어야 한다고 적는다.
- §3.3.1은 속성 캐시가 성능을 높이지만 속성 최신성과 보안 사이의 절충이 있고 권한이 바뀐 뒤에도 갱신 전까지 옛 속성이 쓰일 수 있다고 경고한다. §3.4.1은 속성 서비스·정책 저장소의 가용성과 데이터 품질을 요구사항으로 다룬다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-25 | 데이터 등급 |
| POL-19 | 에이전트 신원·위임 |
| POL-20 | 에이전트 신원·위임 |
| POL-22 | 에이전트 신원·위임 |

## 우리 솔루션 개발에 사용할 곳

- **POL-25**: '자산과 보안등급을 확인하고 사용자·위임·기능 범위를 모두 검사'를 객체 속성(보안등급)·주체 속성·환경 조건의 결정으로 풀어 쓰는 근거다. 등급 속성의 이름·허용 값·부여 주체를 정의하는 §2.4.2가 '데이터 등급' 공백의 출발점이다.
- **POL-19·POL-20·POL-22**: 에이전트 신원·위임 범위·유효기간을 주체 속성으로 두고 결정 시점에 평가하며, 속성 캐시 때문에 철회가 늦게 반영되는 경쟁(§3.3.1)을 시험 항목으로 둔다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

PDF의 목차와 §2.2·2.4.2·3.3.1·3.4.1 도입부만 읽었다(문서 전체 정독 아님). ABAC 정의 문서이며 MCP·에이전트를 다루지 않는다. 우리 게이트웨이의 속성 모델과 대조하지 않았다.

NIST 간행물: 미국에서 저작권 보호 대상이 아니며 출처 표기를 요청한다고 PDF에 적혀 있다. 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
