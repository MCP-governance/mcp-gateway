# LIB-N28 · Model Context Protocol (MCP): Security Design Considerations for AI-Driven Automation (Cybersecurity Information Sheet)

NSA AI 보안센터가 MCP 도입 조직을 위해 낸 정보 시트(CSI)다. 보도자료는 직렬화 위험·신뢰 경계·에이전트 오용을 주요 문제로 들고, 인증·인가·입력 검증 같은 기존 원칙이 필요하지만 동적 도구 호출·암묵적 신뢰·문맥 공유 때문에 충분하지 않으며 에이전트 환경 전체를 하나의 연속체로 다뤄야 한다고 설명한다.

## 출처와 확인 수준

- 공식 출처: [Model Context Protocol (MCP): Security Design Considerations for AI-Driven Automation (Cybersecurity Information Sheet)](https://www.nsa.gov/Press-Room/Press-Releases-Statements/Press-Release-View/Article/4496698/nsa-releases-security-design-considerations-for-ai-driven-automation-leveraging/)
- 유형: guide · 2026년 · 미국 NSA AI Security Center, 2026-05-20 보도자료(PDF 판본 v1.0 표기는 2차 보도 기준) · `published_guidance`
- 저자·발행: National Security Agency, Artificial Intelligence Security Center
- 확인일: 2026-10-23 / `official_press_release_read_pdf_hash_only`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 보도자료는 MCP가 PII 조회 같은 민감 작업에도 쓰이고 현재 명세는 구현 시 각별한 주의가 필요하다고 밝힌다.
- 프로토콜·구현·운영 태세 세 층의 공백이 함께 문제라고 설명하며 높은 보증이 필요한 환경에서는 신중 도입을 권한다.

## 우리 솔루션 개발에 사용할 곳

- MINT가 호출 경계에서 하는 일(신원·계약·자원 분류·정책 판정)과 CSI가 말하는 연속체 관점(도입 심사·런타임·종료 수명주기)의 대응표를 만들 때 공식 정부 출처로 인용한다.
- CSI 본문 권고 항목은 이번에 읽지 못했으므로 항목별 대응은 PDF를 확보해 읽은 뒤에 한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

보도자료 전문만 읽었다. CSI PDF 본문은 읽지 못했다(서버가 비브라우저 요청에 403을 반환했고, 브라우저 창에서는 다운로드로 처리되어 본문을 추출하지 못했다). PDF 크기 305,977바이트와 SHA-256만 브라우저 요청으로 계산했다. 권고 항목 수·세부 내용은 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
