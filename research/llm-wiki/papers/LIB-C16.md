# LIB-C16 · Benchmarking and Defending Against Indirect Prompt Injection Attacks on Large Language Models

간접 프롬프트 주입을 체계적으로 평가하는 벤치마크 BIPIA를 제안하고, 현존 LLM이 모두 이 공격에 취약하다고 보고한다. 경계 인식과 명시적 리마인더를 이용한 블랙박스 방어와 화이트박스 방어를 함께 제시한다.

## 출처와 확인 수준

- 공식 출처: [Benchmarking and Defending Against Indirect Prompt Injection Attacks on Large Language Models](https://arxiv.org/abs/2312.14197)
- 유형: preprint · 2023년 · arxiv.org · `preprint`
- 저자·발행: Jingwei Yi, Yueqi Xie, Bin Zhu, Emre Kiciman 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 현존 LLM이 간접 주입에 취약하며, 정보성 맥락과 실행할 지시를 구분하지 못하는 것이 원인이라고 설명한다.
- 블랙박스 방어가 공격을 크게 완화하고, 화이트박스 방어는 출력 품질을 유지하면서 공격 성공률을 매우 낮춘다고 주장한다.

## 우리 솔루션 개발에 사용할 곳

- BIPIA의 공격 유형 분류(외부 콘텐츠에 지시를 심는 여러 형태)를 게이트웨이 시나리오 목록의 기준으로 쓴다.
- 경계 인식 리마인더 방식(외부 콘텐츠 앞뒤로 데이터이며 지시가 아니라고 명시)을 출력 래핑 템플릿 실험 후보로 두고, 스포트라이팅과 비교 평가한다.
- 화이트박스 방어는 모델 내부 접근이 필요하므로 게이트웨이에는 적용할 수 없고, 블랙박스 방어만 평가 대상으로 둔다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록 요약만 확인했고 본문은 읽지 않았다. BIPIA는 에이전트 전용이 아니라 일반 LLM 응용을 대상으로 한다. 학회(KDD 2025) 게재 정보는 검색 스니펫 기준이며 원문으로 확인하지 못했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive distribution license 1.0 (페이지 링크 기준)

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
