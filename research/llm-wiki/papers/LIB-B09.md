# LIB-B09 · MCP-Guard: A Multi-Stage Defense-in-Depth Framework for Securing Model Context Protocol in Agentic AI

MCP 도구 호출 경로에 놓는 계층형 방어 구조로, 정적 스캔, 신경망 탐지기(E5 기반), LLM 중재자를 순서대로 결합해 프롬프트 인젝션과 데이터 유출을 막는다고 주장한다. 공격 샘플 벤치마크 MCP-AttackBench도 함께 공개한다.

## 출처와 확인 수준

- 공식 출처: [MCP-Guard: A Multi-Stage Defense-in-Depth Framework for Securing Model Context Protocol in Agentic AI](https://arxiv.org/abs/2508.10991)
- 유형: preprint · 2025년 · arxiv.org · `preprint`
- 저자·발행: Wenpeng Xing, Zhonghao Qi, Yupeng Qin, Yilin Li 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 계층형 탐지(정적, 신경망, 중재)로 프롬프트 인젝션과 데이터 유출 같은 위협을 다룬다는 설계를 제시한다.
- E5 기반 분류기의 적대적 프롬프트 탐지 정확도를 보고한다(수치 생략).
- 벤치마크는 GPT-4로 증강했다고 밝힌다.

## 우리 솔루션 개발에 사용할 곳

- 정책 엔진 앞단에 정적 규칙과 분류기 기반 탐지 단계를 두는 구성을 참고한다. 최종 차단 기준은 OPA 명시 정책으로 두고, 탐지 결과는 근거와 함께 감사 원장에 남긴다.
- LLM 중재자의 최종 판정은 재현성이 낮으므로 참고 신호로만 쓰고 차단 결정에는 넣지 않는다.
- MCP-AttackBench 샘플 중 도구 설명 오염 계열만 골라 게이트웨이 회귀 테스트에 넣는다. 벤치마크 규모와 증강 방식은 본문에서 확인이 필요하다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지를 열어 확인했고 본문 평가와 비교 기준선은 읽지 않았다. 도구 설명 오염 전용 평가인지 일반 적대적 프롬프트 평가인지 초록으로는 구분되지 않는다. 판본에 따라 제목이 바뀌었다. 같은 이름의 MCPGuard(2510.23673, 서버 취약점 스캐너)와 혼동하지 않도록 한다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive 1.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
