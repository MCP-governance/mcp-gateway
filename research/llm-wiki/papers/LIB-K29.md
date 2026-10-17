# LIB-K29 · OpenID Continuous Access Evaluation Profile (CAEP) 1.0

Shared Signals Framework 위에서 송신자가 수신자에게 사람·로봇 사용자, 장치, 세션, 애플리케이션에 대한 접근을 지속적으로 조정하도록 알리는 이벤트 유형을 정의한다. 이벤트는 Session Revoked, Token Claims Change, Credential Change, Assurance Level Change, Device Compliance Change, Session Established, Session Presented, Risk Level Change다.

## 출처와 확인 수준

- 공식 출처: [OpenID Continuous Access Evaluation Profile (CAEP) 1.0](https://openid.net/specs/openid-caep-1_0.html)
- 관련 출처: <https://openid.net/wg/sharedsignals/>
- 유형: 명세 · 2025년 · OpenID Foundation Shared Signals WG, Standards Track, 2025-08-29 · `open_standard`
- 저자·발행: T. Cappalli, A. Tulshibagwale
- 판본: Version 1.0, 2025-08-29(Final Specification 승인 공지: 2025-09-02)
- 확인일: 2026-10-17 / `full_text_selected_sections_read` — 원문의 지정 절·조문을 직접 읽었다. 읽은 범위: 초록, 목차(§3.1~3.8, §4), Appendix B 고지문.
- 요약 검토: 지정한 절을 원문에서 직접 읽고 요약했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 초록은 송신자가 연속 갱신을 보내 수신자가 접근을 조절(attenuate)할 수 있게 하는 것이 목적이라고 밝힌다. 이벤트 유형은 §3.1~3.8이며 각각 이벤트 고유 클레임과 예시가 있다.
- §3.1 Session Revoked, §3.3 Credential Change, §3.2 Token Claims Change는 이름으로 보아 세션 종료·자격 변경·토큰 클레임 변경을 수신자에게 알리는 이벤트다(세부 클레임은 읽지 않았다).
- §4 보안 고려사항이 있고 SSF §9와 함께 읽는다. 고지문은 SSF와 같은 OIDF 저작권 사용 허가다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-44 | 공급자 측 자격 회수 |
| POL-45 | 공급자 측 자격 회수 |
| POL-22 | 공급자 측 자격 회수 |
| POL-20 | 에이전트 신원·위임 |

## 우리 솔루션 개발에 사용할 곳

- **POL-44·POL-45**: 철회·자격 변경 이벤트(session-revoked, credential-change)를 받았을 때 게이트웨이가 해당 주체의 후속 호출을 거부하고 캐시를 무효화하는 동작을 '신규 효과 0' 시험에 포함한다. 이벤트가 오지 않는 제공자는 기존 폴링·introspection(T20)을 유지한다.
- **POL-22·POL-20**: 요청마다 최신 승인·위임 상태를 쓰는 규칙에서, 외부 신호로 상태가 바뀔 때 반영 지연을 측정한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

초록과 목차, 고지문만 읽었고 이벤트 클레임 상세와 §4는 읽지 않았다. 실제 상류 서비스의 CAEP 지원은 확인하지 못했다. 사람의 접근 평가 중심 프로파일이라 에이전트·MCP 서버 호출에 대한 해석은 설계 단계의 가정이다.

OpenID Foundation 고지: 구현·파생을 위한 비독점·무상 저작권 사용 허가와 출처 표시. 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
