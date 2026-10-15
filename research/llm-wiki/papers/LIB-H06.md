# LIB-H06 · Are Large Pre-Trained Language Models Leaking Your Personal Information?

사전학습 언어모델(PLM)에 이메일 주소의 주변 맥락이나 소유자 이름을 넣어 질의해 개인정보가 새는지 분석한다. 암기 때문에 개인정보가 새지만, 모델의 연관 능력이 약해 공격자가 특정인의 정보를 뽑아낼 위험은 낮다고 결론짓는다.

## 출처와 확인 수준

- 공식 출처: [Are Large Pre-Trained Language Models Leaking Your Personal Information?](https://arxiv.org/abs/2205.12628)
- 유형: 논문 · 2022년 · arxiv.org · `preprint`
- 저자·발행: Jie Huang, Hanyin Shao, Kevin Chen-Chuan Chang
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- PLM은 암기 때문에 이메일 주소 같은 개인정보를 유출한다.
- 이름과 이메일을 연결하는 연관 능력은 약해 특정인을 겨냥한 추출 위험은 낮다고 본다.

## 우리 솔루션 개발에 사용할 곳

- 도구 응답이나 모델 출력에 섞이는 이메일·연락처 유출을 게이트웨이 출력 검사 대상으로 두는 근거로 쓴다. 2022년 PLM 대상 연구라 현재 대형 모델에 그대로 적용하지 않는다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록만 확인했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
