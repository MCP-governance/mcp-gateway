# LIB-K26 · The Idempotency-Key HTTP Header Field (draft-ietf-httpapi-idempotency-key-header-07, 만료된 Internet-Draft)

비멱등 HTTP 메서드(POST, PATCH)를 장애 허용적으로 만드는 Idempotency-Key 요청 헤더를 정의하려는 초안이다. 키 유일성, 유효·만료, 요청 지문(fingerprint), 최초·재시도·동시 요청의 서버 처리 방식과 오류 코드를 다룬다.

## 출처와 확인 수준

- 공식 출처: [The Idempotency-Key HTTP Header Field (draft-ietf-httpapi-idempotency-key-header-07, 만료된 Internet-Draft)](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/)
- 관련 출처: <https://www.ietf.org/archive/id/draft-ietf-httpapi-idempotency-key-header-07.txt>
- 유형: 명세 · 2025년 · IETF HTTPAPI WG Internet-Draft -07 (2025-10-15), 2026-04-18 만료(Expired & archived) · `ietf_internet_draft`
- 저자·발행: Jayadeba Jena, Sanjay Dalal
- 판본: -07(2025-10-15). 데이터트래커 상태 'Expired', RFC 번호 없음(초안 머리말은 Standards Track을 의도한 상태로 적지만 데이터트래커의 Intended RFC status 칸은 비어 있다). 후속 개정이 있는지는 확인하지 못했다
- 확인일: 2026-10-17 / `full_text_selected_sections_read` — 원문의 지정 절·조문을 직접 읽었다. 읽은 범위: 초안 -07 텍스트의 머리·§2.2~2.7, 데이터트래커 메타데이터(상태·만료일).
- 요약 검토: 지정한 절을 원문에서 직접 읽고 요약했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- §2.2: 멱등 키는 유일해야 하며 다른 페이로드의 요청에 재사용해서는 안 된다(MUST NOT). §2.4: 서버는 키와 함께 페이로드의 체크섬·선택 필드·요청 서명 등으로 만든 지문을 쓸 수 있다.
- §2.6: 최초 요청은 정상 처리하고, 원래 요청이 끝난 뒤의 재시도에는 이전 결과(성공·오류)를 돌려주며, 원래 요청이 끝나기 전의 동시 재전송에는 충돌 오류를 돌려주라고(SHOULD) 한다.
- §2.7: 같은 키에 다른 페이로드를 보내면 422, 처리 중 재시도는 409 Conflict로 응답하라고 한다. §2.3은 키의 유효기간·만료 정책을 서버가 정의·공개하라고 한다. 초안은 만료되었고 RFC가 아니다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-36 | 중복 실행 |

## 우리 솔루션 개발에 사용할 곳

- **POL-36**: '문서 수정·삭제 요청이 재전송·재시도돼도 같은 작업이 중복 실행되지 않는다'의 설계 패턴이다. 게이트웨이가 변경 도구 호출에 대해 (승인 digest, 요청 식별자, 인자 지문)을 키로 삼아 최초/재시도/동시 요청을 구분하고, 응답 유실 뒤 재시도에는 이전 결과를 재생하는 방식을 비교한다(DEV-43 설계 제안).
- **POL-36**: 독립 쓰기 효과 시험: 같은 키 동시 2회, 응답 유실 후 재시도, 다른 인자로 같은 키 재사용(422 유사 거부), 키 만료 뒤 재시도를 업스트림의 실제 쓰기 횟수로 확인한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

초안 본문의 §2.2~2.7만 읽었고 구현 현황·보안 고려 절은 읽지 않았다. 표준이 아니며 만료·미완성 문서다. MCP 도구 호출에는 이 헤더가 없으므로 그대로 적용할 수 없고, 업스트림 서버가 키를 지원해야 중복 쓰기 방지가 보장된다.

IETF Trust 저작권 및 BCP 78·79 적용(초안 상태란). 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
