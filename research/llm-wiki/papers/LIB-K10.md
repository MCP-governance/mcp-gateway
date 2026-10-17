# LIB-K10 · Stripe Smokescreen — 외부 요청용 HTTP CONNECT 프록시 (stripe/smokescreen v0.1.0)

Stripe가 웹훅 등 외부로 나가는 트래픽을 모으는 HTTP CONNECT 프록시다. 호스트 이름 허용목록(ACL)으로 대상을 제한하고, 요청된 도메인을 해석해 공인 라우팅 가능 IP인지 확인해 내부망 스캔에 쓰이는 것을 막으며, mTLS로 클라이언트 신원을 인증해 클라이언트별 ACL을 적용한다.

## 출처와 확인 수준

- 공식 출처: [Stripe Smokescreen — 외부 요청용 HTTP CONNECT 프록시 (stripe/smokescreen v0.1.0)](https://github.com/stripe/smokescreen)
- 관련 출처: <https://raw.githubusercontent.com/stripe/smokescreen/master/README.md>
- 유형: 도구·OSS · 2026년 · GitHub stripe/smokescreen 릴리스 v0.1.0 (2026-09-21), MIT · `open_source_release`
- 저자·발행: Stripe 및 기여자
- 판본: 릴리스 v0.1.0(2026-09-21). master README 열람(2026-10-17)
- 확인일: 2026-10-17 / `page_text_read` — 공식 페이지 본문을 읽었다(절 단위 정독 아님). 읽은 범위: README 전체, 저장소 메타데이터, 릴리스 v0.1.0.
- 요약 검토: 출처 페이지 본문과 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- README는 사전 구성된 호스트 이름 ACL과, 도메인을 해석한 결과가 내부 IP가 아님을 확인하는 두 단계를 설명한다. IP·범위를 별도로 허용·거부할 수 있다.
- 옵션 목록에 --deny-range, --allow-range, --deny-address, --allow-address, --egress-acl-file이 있고 --unsafe-allow-private-ranges는 기본 꺼짐이다. 겹치는 규칙은 기본적으로 허용 우선이며 --most-specific-ip-rules로 가장 구체적인 규칙을 따르게 할 수 있다.
- 일반적인 사용에서 클라이언트는 mTLS로 접속하고, 인증서의 common name 등에서 추출한 역할(RoleFromRequest)로 서비스별 ACL을 적용한다. 이 함수는 교체할 수 있다. README는 일반적으로 Go 최근 두 버전만 지원한다고 적는다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-10 | 목적지 DNS·서버 outbound |
| POL-26 | 목적지 DNS·서버 outbound |
| POL-40 | 목적지 DNS·서버 outbound |

## 우리 솔루션 개발에 사용할 곳

- **POL-10·POL-26**: 호스트 ACL과 해석된 IP 검사를 한 곳(프록시)에서 하도록 서버 outbound를 모으는 구조의 사례다. MCP 서버 컨테이너의 외부 연결을 이런 프록시로만 허용하는 방안을 DEV-41의 선택지로 검토한다.
- **POL-40**: 서비스별 ACL 파일을 승인 레코드로 보면, 허용 목적지 변경 = ACL 변경 = 재승인으로 연결할 수 있다(설계 제안).

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

README와 저장소·릴리스 메타데이터만 읽었다. 소스 코드(DNS 해석·IP 검사 구현)와 ACL 파일 스키마 상세는 열지 않았고 시험하지 않았다. v0.1.0은 최초 태그 릴리스로 보이며(릴리스 목록은 확인하지 않음) 운영 성숙도는 평가하지 않았다.

GitHub 저장소 메타데이터의 SPDX가 MIT이다(LICENSE 파일 본문은 열지 않았다). 코드를 복제하지 않는다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
