# LIB-K30 · RFC 8417: Security Event Token (SET)

발행자 관점에서 주체에 대한 사실 진술을 JWT 형식으로 담는 Security Event Token(SET) 자료구조를 정의한다. 핵심 클레임, 명시적 타이핑, 다른 JWT(ID 토큰·액세스 토큰)와의 혼동 방지, 보안 고려사항(기밀성·무결성, 전달, 순서, 시점 문제)을 다룬다.

## 출처와 확인 수준

- 공식 출처: [RFC 8417: Security Event Token (SET)](https://www.rfc-editor.org/rfc/rfc8417)
- 관련 출처: <https://www.rfc-editor.org/rfc/rfc8417.txt>
- 유형: 표준·RFC·권고 · 2018년 · IETF RFC 8417 (Standards Track), 2018-07 · `ietf_rfc`
- 저자·발행: P. Hunt (Ed.), M. Jones, W. Denniss, M. Ansari
- 판본: 2018년 7월 발행본. 2026-10-17 시점의 갱신·폐기 표시는 확인하지 않았다
- 확인일: 2026-10-17 / `full_text_selected_sections_read` — 원문의 지정 절·조문을 직접 읽었다. 읽은 범위: 머리·초록, 목차 구조, 저작권 고지.
- 요약 검토: 지정한 절을 원문에서 직접 읽고 요약했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 초록: SET은 발행자 관점에서 주체에 대한 사실 진술을 기술한다. §2.2 핵심 SET 클레임, §2.3 명시적 타이핑, §2.4 구성 절차가 있다.
- §4는 SET을 ID 토큰·액세스 토큰·다른 JWT와 혼동하지 않도록 구분하는 방법을 다루고, §5는 기밀성·무결성, 전달, 순서(Sequencing), 시점(Timing Issues), 혼동 방지를 다룬다.
- OpenID SSF 1.0이 이 RFC를 프로파일한다(LIB-K28).

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-44 | 공급자 측 자격 회수 |
| POL-38 | 경보 검증·자동 대응 |

## 우리 솔루션 개발에 사용할 곳

- **POL-44·POL-38**: 철회·승인 변경 같은 상태 전이를 서명된 사실 진술(SET)로 원장에 남기는 형식 후보다. 'SET은 명령이 아니라 사실 진술'이라는 성격이 철회 사실의 감사 기록과 맞는다. 도입 여부는 DEV-45 원장 설계에서 결정한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

초록, 목차, 구조만 확인하고 본문 절의 세부는 읽지 않았다. 우리 원장 형식과 대조하지 않았다.

IETF Trust 저작권 및 BCP 78·IETF Trust Legal Provisions 적용. 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
