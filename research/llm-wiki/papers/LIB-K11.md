# LIB-K11 · RFC 9325 (BCP 195): Recommendations for Secure Use of Transport Layer Security (TLS) and Datagram Transport Layer Security (DTLS)

TLS·DTLS 배포의 최신 보안 권고다. SSL 2·3과 TLS 1.0·1.1 협상을 금지하고 TLS 1.2 지원을 필수, TLS 1.3 지원을 권장하며, SSL 스트리핑을 막는 strict TLS, 호스트 이름 검증, 인증서 폐지 확인 등을 다룬다.

## 출처와 확인 수준

- 공식 출처: [RFC 9325 (BCP 195): Recommendations for Secure Use of Transport Layer Security (TLS) and Datagram Transport Layer Security (DTLS)](https://www.rfc-editor.org/rfc/rfc9325)
- 관련 출처: <https://www.rfc-editor.org/rfc/rfc9325.txt>
- 유형: 표준·RFC·권고 · 2022년 · IETF RFC 9325 / BCP 195 (Best Current Practice), 2022-11. RFC 7525를 폐기하고 RFC 5288·6066을 갱신 · `ietf_rfc`
- 저자·발행: Y. Sheffer, P. Saint-Andre, T. Fossati
- 판본: 2022년 11월 발행본 텍스트(RFC Editor) 열람. 2026-10-17 시점의 폐기·갱신 표시는 확인하지 않았다
- 확인일: 2026-10-17 / `full_text_selected_sections_read` — 원문의 지정 절·조문을 직접 읽었다. 읽은 범위: 초록·상태, §3.1.1, §3.2, §7.1, 목차.
- 요약 검토: 지정한 절을 원문에서 직접 읽고 요약했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- §3.1.1: 구현은 SSL 2·3, TLS 1.0·1.1을 협상해서는 안 되고(MUST NOT) TLS 1.2를 지원해야 하며(MUST) TLS 1.3 지원을 권장한다(SHOULD).
- §3.2: 프로토콜이 TLS 전용 포트와 동적 업그레이드(STARTTLS)를 모두 지원하면 TLS 전용 방식을 지원하고 우선 쓰게 설정해야 하며, 업그레이드만 지원하면 평문을 금지하는 엄격한 로컬 정책을 관리자가 설정해야 한다.
- §7.1: 호스트 이름 검증은 모든 일반 TLS 사용에서 보안상 핵심이다. 검증이 없으면 TLS는 인증서가 유효하고 개인키를 소유함은 보장하지만 연결이 의도한 종단에서 끝난다는 보장은 못 한다. §7.5는 인증서 폐지를 다룬다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-16 | 전송 TLS |

## 우리 솔루션 개발에 사용할 곳

- **POL-16**: '승인된 암호화 전송 적용과 연결 상대 검증'의 구체 기준이다. 게이트웨이가 업스트림 MCP로 나가는 TLS 클라이언트에서 TLS 1.0/1.1 협상 거부, 1.2 이상, 호스트 이름 검증을 음성 시험으로 둔다. 현재 field의 HTTP/Tailscale 구간과 조직 운영 TLS를 구분하는 근거로 쓴다.
- **POL-16**: 평문 업그레이드 허용 여부(§3.2)는 '평문 전송이나 검증되지 않은 중간 경로 제외'의 시험 항목이 된다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

§3.1.1, §3.2, §7.1의 본문을 읽었고 암호 스위트 절(§4)은 읽지 않았다. 문서가 '미래 BCP가 TLS 1.2를 폐기할 것으로 기대한다'고 적으므로 이후 개정이 있는지 확인해야 한다. 우리 TLS 설정에는 적용하지 않았다.

IETF Trust 저작권 및 BCP 78·IETF Trust Legal Provisions 적용. 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
