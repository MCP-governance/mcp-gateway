# LIB-N03 · A Gateway Architecture for Enterprise MCP Authentication: Unifying Heterogeneous Auth, Identity Delegation, and the User / Non-User Persona Problem

대규모 조직이 팀마다 제각각 만든 MCP 서버 인증(무인증·API 키·OAuth)을 중앙 MCP 게이트웨이 한 층으로 모은 운영 경험 보고다. 사용자·비사용자 두 축과 자격 유형을 교차한 인증 모델, 토큰 교환(RFC 8693) 위임, 세 가지 신원 흐름을 제시한다. 회사명은 초록에 없다.

## 출처와 확인 수준

- 공식 출처: [A Gateway Architecture for Enterprise MCP Authentication: Unifying Heterogeneous Auth, Identity Delegation, and the User / Non-User Persona Problem](https://arxiv.org/abs/2608.10760)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-08-11) · `preprint`
- 저자·발행: Suraj Kumar, Amy Wang, Srinivasan Manoharan
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 토큰을 직접 가져오기·게이트웨이가 발급·토큰 교환 위임의 세 방식을 제시하고, 수십 개 서버 앞에서 운영 중이라고 밝힌다.

## 우리 솔루션 개발에 사용할 곳

- MINT의 업스트림 자격(사용자 위임 대 서비스 계정)을 정리할 때 「사용자·자동 주체 × 자격 유형」 2축 분류를 그대로 대조표로 쓴다.
- 퇴사자 일괄 회수처럼 게이트웨이를 지나지 않으면 못 하는 운영 이점을 도입 근거 목록에 넣는다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
