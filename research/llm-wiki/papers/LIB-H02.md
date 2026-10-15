# LIB-H02 · GLiNER: Generalist Model for Named Entity Recognition using Bidirectional Transformer

임의의 개체 유형 레이블을 입력받아 문장에서 개체를 추출하는 소형 양방향 인코더 기반 범용 NER 모델을 제안한다. 생성형 LLM처럼 토큰을 하나씩 생성하지 않고 개체를 병렬로 추출하며, 제로샷 설정에서 ChatGPT를 앞선다고 보고한다.

## 출처와 확인 수준

- 공식 출처: [GLiNER: Generalist Model for Named Entity Recognition using Bidirectional Transformer](https://arxiv.org/abs/2311.08526)
- 유형: 논문 · 2023년 · NAACL 2024 (Long Papers) · `venue_reported_unverified`
- 저자·발행: Urchade Zaratiana, Nadi Tomeh, Pierre Holat, Thierry Charnois
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 임의의 개체 유형을 레이블로 받아 병렬로 추출하는 소형 양방향 인코더가 생성형 LLM의 대안이 될 수 있다고 제안한다.
- 여러 NER 벤치마크의 제로샷 평가에서 ChatGPT와 미세조정 LLM보다 낫다고 보고한다(저자 보고).

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이의 2단계 PII 탐지기로 쓴다. 정규식과 Presidio가 놓치는 이름, 주소, 소속 같은 문맥 의존 엔티티를 레이블 문자열만 바꿔 제로샷으로 추가하고, 엔티티 목록은 정책 파일에서 관리한다.
- LLM API 호출 없이 사내 CPU 또는 GPU에서 돌릴 수 있어, 원문을 외부 모델로 보내면 안 되는 사내 하네스 트래픽 경로에 맞는다.
- 논문 평가에는 한국어 PII가 충분히 포함되지 않았을 것으로 보이므로, 도입 전 사내 한국어 골드셋으로 재검증한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지에서 제목, 저자, 날짜, 라이선스와 초록 첫 두 문장만 열람했다. 실험 결과는 검색 요약에 의존해 본문은 정독하지 않았다. 학회 게재 정보는 검색 결과 기준이며, 체크포인트별 라이선스 차이는 검색 스니펫에만 있어 미확인이다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

논문 CC BY 4.0(arXiv 페이지 확인). 체크포인트별 라이선스는 상이하다는 검색 결과가 있으나 미확인

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
