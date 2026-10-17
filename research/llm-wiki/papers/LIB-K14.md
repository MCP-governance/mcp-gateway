# LIB-K14 · SPIFFE 표준: SPIFFE ID, X509-SVID, JWT-SVID (spiffe/spiffe, Stability: Stable)

SPIFFE는 이질적인 환경에서 서비스에 신원을 발급하는 표준이다. SPIFFE ID(신뢰 도메인 + 경로)와 이를 담는 검증 가능한 신원 문서(SVID)를 X.509 인증서와 JWT 두 형식으로 정의한다.

## 출처와 확인 수준

- 공식 출처: [SPIFFE 표준: SPIFFE ID, X509-SVID, JWT-SVID (spiffe/spiffe, Stability: Stable)](https://github.com/spiffe/spiffe/blob/main/standards/SPIFFE-ID.md)
- 관련 출처: <https://github.com/spiffe/spiffe/blob/main/standards/X509-SVID.md>
- 관련 출처: <https://github.com/spiffe/spiffe/blob/main/standards/JWT-SVID.md>
- 유형: 명세 · 2026년 · SPIFFE 프로젝트 표준 문서(spiffe/spiffe 저장소), 세 문서 모두 Stability: Stable · `open_standard`
- 저자·발행: SPIFFE 프로젝트
- 판본: SPIFFE-ID.md 마지막 변경 커밋 665a28f3253e(2026-07-01), X509-SVID.md·JWT-SVID.md 21896acad5c6(2026-07-01)
- 확인일: 2026-10-17 / `full_text_selected_sections_read` — 원문의 지정 절·조문을 직접 읽었다. 읽은 범위: SPIFFE-ID.md 머리·목차, X509-SVID.md §2·§3.1, JWT-SVID.md §2·§3·§7.1, 저장소 LICENSE, 파일별 최종 커밋.
- 요약 검토: 지정한 절을 원문에서 직접 읽고 요약했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- X509-SVID(§2·3.1): SPIFFE ID는 SAN의 URI에 정확히 한 개만 담아야 하며(MUST), 다수면 감사가 어려워진다고 설명한다. 잎(leaf) 인증서의 SPIFFE ID는 루트가 아닌 경로 요소를 가져야 한다.
- JWT-SVID(§3.1·3.2): `sub`는 워크로드의 SPIFFE ID여야 하고 `aud`는 반드시 있어야 한다. 검증자는 `aud`가 없거나 자신의 식별자가 없으면 거부해야 하며, `production` 같은 넓은 값은 하나의 서비스가 침해되면 사칭 가능성이 열리므로 권장하지 않는다.
- JWT-SVID §7.1은 JWT-SVID가 bearer 토큰이라 재전송 공격에 노출되며 `aud`·`exp` 필수화로 완화하지만 완전히 해결하지는 못한다고 적는다. JOSE 허용 범위를 제한해(JWS Compact만, 알고리즘 목록 고정) 알려진 취약점 유형을 피한다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-19 | 에이전트 신원·위임 |
| POL-20 | 에이전트 신원·위임 |
| POL-21 | 에이전트 신원·위임 |
| POL-15 | 에이전트 신원·위임 |

## 우리 솔루션 개발에 사용할 곳

- **POL-19**: 요청 주체의 이름·clientInfo가 아니라 검증 가능한 암호 신원(SVID)을 transport 신원으로 쓰는 방식의 근거다. 게이트웨이↔MCP 서버, endpoint-agent↔게이트웨이 같은 구간의 워크로드 신원을 비교한다.
- **POL-21·POL-15**: JWT-SVID의 `aud` 필수·서비스 범위 한정은 '대상 불일치 시 거부'와 '서버별 인증정보 분리'의 사례다. 토큰 대상(aud)과 만료(exp) 음성군 시험 설계에 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

세 문서의 도입·목차와 위 인용 절을 읽었다. 워크로드(프로세스) 신원 표준이며 사용자 위임·업무 목적·에이전트 권한 범위를 정의하지 않는다. SPIFFE Workload API 문서는 받았지만 읽지 않았다. 우리 배포에 SPIFFE를 적용하지 않았다.

spiffe/spiffe 저장소 LICENSE는 Apache License 2.0이다. 각 표준 문서의 상태란은 '배포 제한 없음(Distribution of this document is unlimited)'이다. 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
