# LIB-F09 · Granite Guardian

프롬프트와 응답의 위험(사회적 편향, 폭력, 탈옥 등)을 판정하는 오픈 가드 모델 제품군 Granite Guardian을 소개한다. RAG의 맥락 관련성, 근거성, 답변 관련성을 점검하는 기능도 포함한다.

## 출처와 확인 수준

- 공식 출처: [Granite Guardian](https://arxiv.org/abs/2412.07724)
- 유형: preprint · 2024년 · arXiv · `preprint`
- 저자·발행: Inkit Padhi, Manish Nagireddy, Giandomenico Cornacchia, Subhajit Chaudhury 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 프롬프트·응답 위험 판정과 RAG 환각 관련 판정을 하나의 제품군에서 제공한다고 밝힌다.
- 유해 콘텐츠 벤치마크에서 AUC 0.871, RAG 환각 관련 벤치마크에서 AUC 0.854를 보고한다(자체 보고).
- 오픈소스로 공개했다고 밝힌다.

## 우리 솔루션 개발에 사용할 곳

- RAG 기반 사내 지식 도구를 게이트웨이 뒤에 둘 때, 도구가 가져온 문서에 대한 근거성 판정을 출력 검사 단계에 넣어 환각 의심 응답을 감사 원장에 남긴다.
- 오픈 가중치라 외부 분류 API 없이 온프레미스에서 PII·위험 판정을 구성할 수 있다. Llama Guard와 같은 조건에서 비교 평가할 후보다.
- 위험 차원 분류를 OPA 정책 입력 필드의 카테고리 값과 매핑하는 표를 만들 때 이 분류 체계를 참고한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지(v2)만 열람했고 본문과 비교 실험은 정독하지 않았다. 검색에서 NAACL 2025 산업 트랙판과 이후 기술 보고서 갱신 언급이 보였으나 확인하지 못해, arXiv 버전과 다를 수 있다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
