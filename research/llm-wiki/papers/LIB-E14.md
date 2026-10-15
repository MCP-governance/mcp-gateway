# LIB-E14 · Authenticated Delegation and Authorized AI Agents

자율 에이전트에 권한을 위임하면서도 책임 소재를 추적할 수 있도록 인증, 인가, 감사가 가능한 위임 프레임워크를 제안한다. OAuth 2.0과 OpenID Connect를 확장해 에이전트 전용 자격 증명과 메타데이터를 얹는 방식이며, 자연어 권한 진술을 감사 가능한 접근 제어 설정으로 바꾸는 방안도 포함한다.

## 출처와 확인 수준

- 공식 출처: [Authenticated Delegation and Authorized AI Agents](https://arxiv.org/abs/2501.09674)
- 유형: preprint · 2025년 · arXiv preprint (cs.CY, cs.AI 및 cs.NI 교차 분류) · `preprint`
- 저자·발행: Tobin South, Samuele Marro, Thomas Hardjono, Robert Mahari 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 에이전트 전용 자격 증명과 메타데이터를 OAuth 2.0과 OIDC에 확장하는 설계를 제안한다고 초록에 적혀 있다.
- 사용자가 에이전트의 권한과 범위를 위임하고 제한하며, 책임 연쇄를 유지하는 것을 목표로 한다고 명시한다.

## 우리 솔루션 개발에 사용할 곳

- 사용자, 하네스 클라이언트, 에이전트로 이어지는 위임 메타데이터(위임자, 범위 제한)를 게이트웨이 감사 원장 스키마에 넣어 책임 추적 항목을 설계한다.
- 자연어 권한 번역은 정책 작성 UI 후보로 검토하되, 최종 정책은 OPA 코드로 검토와 승인을 거치도록 하는 편이 안전하다(해석).

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록과 서론 요약만 확인하고 본문은 정독하지 않았다. 2025년 초 preprint이며 cs.CY 분류라 기술 세부는 본문 확인 전까지 판단하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY-SA 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
