# LIB-D04 · AEGIS: Preventing Cross-Domain Resource Abuse in MCP

MCP 도구 호출이 지나치게 큰 요청으로 백엔드를 과부하시키는 자원 남용을 막으려고, LLM 추론으로 이종 도구 호출을 하나의 표준 형식으로 정규화하고 Open Policy Agent로 정책을 검사하는 집행 계층 AEGIS를 제안한다. ContextForge AI Gateway의 플러그인 체계에 구현했다고 밝힌다.

## 출처와 확인 수준

- 공식 출처: [AEGIS: Preventing Cross-Domain Resource Abuse in MCP](https://arxiv.org/abs/2608.20481)
- 유형: preprint · 2026년 · arXiv preprint (v1 2026-08-20) · `preprint`
- 저자·발행: Shriti Priya, Teryl Taylor, Frederico Araujo
- 확인일: 2026-10-14 / `arxiv_api_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 도구마다 요청 스키마가 달라 정책을 일반적이면서 정밀하게 쓰기 어렵다는 문제를 제기하고, 정규화 계층으로 이를 해결하려 한다(초록).
- Open Policy Agent와 ContextForge AI Gateway에 통합했다고 초록이 밝힌다. 정량 평가 결과는 초록에 없다.

## 우리 솔루션 개발에 사용할 곳

- 우리 게이트웨이도 OPA 기반이므로, AEGIS의 '도구 온톨로지 캐시, 파라미터 정규화, 임계값 정책' 흐름을 자원 남용 방지 플러그인 설계의 직접 참고로 쓴다.
- 온톨로지가 캐시에 없는 호출을 정책 검사 없이 통과시키는 공백이 있으므로, 우리는 미등록 도구 기본 거부 원칙으로 같은 공백을 막는 방안을 검토한다.
- 멀티모달 인자(이미지, 영상, 위치) 정규화 기준을 PII 마스킹 대상 필드 목록과 함께 정리한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록과 앞부분 발췌만 확인했고 전문과 실험 설정은 정독하지 못했다. 같은 제목의 다른 항목이 저자와 학회 표기가 달라 arXiv 기록을 기준으로 삼았다. 2026년 8월 제출본이라 후속 버전이 있을 수 있다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
