# LIB-C03 · Defending Against Indirect Prompt Injection Attacks With Spotlighting

LLM이 사용자 명령과 외부 데이터를 하나의 텍스트 스트림으로 받기 때문에 간접 주입을 구분하기 어렵다는 문제를 제기한다. 입력을 변환해 출처(provenance)를 모델에 드러내는 프롬프트 기법 계열인 스포트라이팅을 제안한다.

## 출처와 확인 수준

- 공식 출처: [Defending Against Indirect Prompt Injection Attacks With Spotlighting](https://arxiv.org/abs/2403.14720)
- 유형: preprint · 2024년 · arxiv.org · `preprint`
- 저자·발행: Keegan Hines, Gary Lopez, Matthew Hall, Federico Zarfati 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 간접 주입 공격 성공률을 크게 낮추면서 작업 성능 손실은 작다고 보고한다(초록 기준, 수치 생략).
- 실험이 GPT 계열 모델 중심으로 보고되어, 다른 계열 모델로의 일반화는 초록만으로는 확인되지 않는다.
- 방어 효과를 공격 성공률 감소와 작업 성능 유지라는 두 지표로 측정했다고 밝힌다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이가 도구 응답을 모델에 넘기기 전에 출처 표시 변환을 적용하는 전처리 단계로 구현할 수 있다. 모델 재학습 없이 쓸 수 있는 1차 완화책이다.
- 변환 전 원문과 변환 후 결과를 모두 감사 원장에 남겨, 어떤 응답이 어떤 형태로 모델에 전달되었는지 추적한다.
- 효과는 모델 계열에 따라 다를 수 있으므로, 게이트웨이 평가 하네스에서 사용하는 백엔드 모델별로 다시 측정하는 항목을 추가한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록 요약만 확인했고 본문과 실험 설정은 읽지 않았다. 적응형 공격에 대한 저항성은 확인하지 못했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
