# LIB-J05 · Agent Flight Recorder: Tamper-Evident Audit Trails with On-Chain Anchoring for Long-Horizon Tool-Using Agents

도구를 쓰는 에이전트의 행동을 구조화된 이벤트로 기록하고, 해시 체인과 Merkle 묶음으로 편집, 삭제, 재정렬, 분기 같은 변조를 드러내며, 에포크 루트를 주기적으로 블록체인에 앵커링해 외부 검증자가 신뢰 중개자 없이 확인하게 하는 감사 로그 시스템을 제안한다. 이벤트 내용은 온체인에 저장하지 않는다.

## 출처와 확인 수준

- 공식 출처: [Agent Flight Recorder: Tamper-Evident Audit Trails with On-Chain Anchoring for Long-Horizon Tool-Using Agents](https://arxiv.org/abs/2609.01931)
- 유형: preprint · 2026년 · arXiv preprint (2026년 9월 제출, BCCA 2026 채택으로 표기) · `preprint`
- 저자·발행: Laurent Bindschaedler, Quentin Botha, Christoph Siebenbrunner
- 확인일: 2026-10-14 / `arxiv_api_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 해시 체인과 Merkle 묶음으로 변조 증거와 간결한 포함 증명을 제공하고, 에포크 루트를 주기적으로 온체인에 앵커링한다고 초록이 밝힌다.
- 합성 워크로드에서 편집, 삭제, 재정렬, 분기 변조를 모두 탐지했고 거짓 양성은 없었다고 자체 보고한다.
- 초록에는 전자서명이 언급되지 않아 행위 주체 귀속은 별도 설계가 필요하다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 원장에 에포크 단위 Merkle 루트를 만들어 WORM 저장소나 공개 로그에 주기적으로 게시하는 방식을 설계할 수 있다. 블록체인 앵커는 필수가 아니고 외부 고정 저장소로 대체할 수 있다.
- 포렌식 질의 정밀도를 비교한 자체 평가 방식을 참고해, 정책 결정 ID와 실행 결과를 함께 조회하는 질의 설계를 검토한다.
- 보고된 지연과 바이트당 비용 수치는 용량 산정의 참고값으로만 쓰고, 저자 자체 합성 워크로드 결과라는 점을 함께 적는다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 수준 요약만 확인했고 전문은 정독하지 않았다. 평가가 합성 워크로드 기반이라 실환경 부하의 근거로 쓰기 어렵다. 성능과 비용 수치는 모두 저자 자체 보고이다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
