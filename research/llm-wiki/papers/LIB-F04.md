# LIB-F04 · Llama Guard: LLM-based Input-Output Safeguard for Human-AI Conversations

사용자 프롬프트와 LLM 응답을 같은 위험 분류 체계로 판정하는 안전 분류 모델 Llama Guard를 소개한다. 분류 체계를 입력으로 바꿔 넣는 방식으로 정책 카테고리를 조정할 수 있으며, 가중치가 공개됐다.

## 출처와 확인 수준

- 공식 출처: [Llama Guard: LLM-based Input-Output Safeguard for Human-AI Conversations](https://arxiv.org/abs/2312.06674)
- 유형: preprint · 2023년 · arXiv · `preprint`
- 저자·발행: Hakan Inan, Kartikeya Upasani, Jianfeng Chi, Rashi Rungta 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- OpenAI Moderation Evaluation과 ToxicChat에서 당시 공개·상용 모더레이션 도구와 같거나 나은 수준이라고 주장한다.
- 분류 체계를 프롬프트나 파인튜닝으로 바꿔 정책을 적용할 수 있다고 밝힌다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이의 입력(도구 인자)과 출력(도구 결과)을 각각 다른 지시문으로 분류하는 구조를 그대로 가져온다. 역할에 따라 분류 프롬프트를 나누는 설계다.
- 분류 체계를 설정 파일로 빼 두어 조직의 PII·위험 카테고리를 넣고, 판정 결과를 OPA 입력 필드로 넘겨 허용·차단 규칙과 분리한다.
- 오픈 가중치라 온프레미스 게이트웨이에 올릴 수 있다. 후속 버전 존재 여부와 성능은 이번 조사에서 확인하지 않았으므로 채택 전에 최신 버전을 봐야 한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록과 기여 목록만 확인했고 본문의 표와 벤치마크 결과는 보지 않았다. 후속 버전과의 비교는 하지 않았고, 2023년 모델이라 현재 성능은 보장되지 않는다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
