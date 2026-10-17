# LIB-K28 · OpenID Shared Signals Framework Specification 1.0

협력하는 피어 사이에서 신호와 이벤트를 공유하는 프레임워크다. SET 프로파일, 주체(subject principals)와 주체 식별자, 이벤트, 송신자(Transmitter) 구성 메타데이터와 탐색, 이벤트 스트림 관리 API(구성·상태·주체·검증)를 정의하며 RISC·CAEP 같은 응용을 가능하게 한다.

## 출처와 확인 수준

- 공식 출처: [OpenID Shared Signals Framework Specification 1.0](https://openid.net/specs/openid-sharedsignals-framework-1_0.html)
- 관련 출처: <https://openid.net/wg/sharedsignals/>
- 유형: 명세 · 2025년 · OpenID Foundation Shared Signals WG, Standards Track, 2025-08-29 (Final Specification 승인: 2025-09-02 공지) · `open_standard`
- 저자·발행: A. Tulshibagwale, T. Cappalli, M. Scurtescu, A. Backman, J. Bradley, S. Miel
- 판본: Version 1.0, 2025-08-29. Shared Signals WG 페이지에 'Three Shared Signals Final Specifications Approved – 2nd Sept 2025' 공지가 있다
- 확인일: 2026-10-17 / `full_text_selected_sections_read` — 원문의 지정 절·조문을 직접 읽었다. 읽은 범위: 초록, 목차, §4.1·§6·§8의 제목 구조, Appendix B 고지문, WG 페이지 공지.
- 요약 검토: 지정한 절을 원문에서 직접 읽고 요약했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- §4.1은 RFC 8417 SET의 프로파일(명시적 타이핑, 서명 키 해석, iss·exp·aud·txn 클레임)을, §6은 push(HTTP, §6.1.1)와 poll(HTTP, §6.1.2) 전달을 정의한다.
- §8은 이벤트 스트림 관리 API(스트림 구성, 상태, 주체, 검증, 스트림 갱신 이벤트)를 정의하고, §7은 송신자 구성 메타데이터와 수신자의 탐색·검증을 정의한다.
- §9 보안 고려사항은 주체 탐침(Subject Probing), 정보 수집(Information Harvesting), 악의적 주체 제거(Malicious Subject Removal)를 다룬다. OIDF 고지는 Final Specification의 구현·파생을 위한 저작권 사용 허가와 출처 표시를 규정한다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-41 | 공급자 측 자격 회수 |
| POL-45 | 공급자 측 자격 회수 |
| POL-44 | 공급자 측 자격 회수 |

## 우리 솔루션 개발에 사용할 곳

- **POL-41·POL-45·POL-44**: 자격·세션 철회를 제공자가 push 이벤트로 알려주는 표준 경로의 후보다. 상류 서비스(IdP·SaaS)가 SSF 송신자를 제공하는 경우에 한해, 게이트웨이가 수신자로서 이벤트를 받아 캐시된 자격·세션을 무효화하는 구조를 검토한다(설계 제안).

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

초록, 목차, 고지문과 §4.1·§6·§8의 구조만 확인했고 필드별 본문은 읽지 않았다. 우리가 연동하는 상류 MCP 서버·제공자(GitHub 등)가 SSF 송신자를 제공하는지 확인하지 못했다. 수신자 구현·시험은 없다.

OpenID Foundation 고지: 개발자·구현자에게 비독점·무상·전 세계 저작권 사용을 허가하되 OIDF를 출처로 표시해야 한다(보증 암시 불가). 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
