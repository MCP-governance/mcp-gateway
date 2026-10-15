# LIB-F06 · TrajAD: Trajectory Anomaly Detection for Trustworthy LLM Agents

입출력만 검사하는 기존 안전장치와 달리 실행 중간 단계의 궤적을 점검해 어느 단계가 이상인지 짚는 궤적 이상 탐지 과제를 정의한다. 정상 궤적을 교란한 뒤 완성하는 방식으로 만든 TrajBench와 전용 검증기 TrajAD를 제시한다.

## 출처와 확인 수준

- 공식 출처: [TrajAD: Trajectory Anomaly Detection for Trustworthy LLM Agents](https://arxiv.org/abs/2602.06443)
- 유형: preprint · 2026년 · arXiv · `preprint`
- 저자·발행: Yibing Liu, Chong Zhang, Zhongyi Han, Hansong Liu 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 범용 LLM은 제로샷 프롬프트로 궤적 이상을 식별하고 위치를 지정하는 데 어려움을 겪는다고 보고한다.
- 정확한 오류 위치 지정이 롤백과 재시도를 가능하게 한다는 문제 설정을 제시한다.
- 전용 검증기가 베이스라인보다 낫다고 주장하나, 초록에는 구체 수치가 없다.

## 우리 솔루션 개발에 사용할 곳

- 세션 단위 호출 궤적을 저장해 두고, 이상 단계를 지목하면 해당 호출 직전으로 되돌려 재시도하거나 승인 요구로 넘기는 흐름의 설계 근거로 쓴다.
- 범용 LLM이 제로샷으로 이상 위치를 잘 못 찾는다는 발견에 따라, 게이트웨이에 LLM 판정기를 넣기 전에 교란 궤적 데이터로 먼저 측정한다.
- 정상 궤적을 교란해 이상 궤적을 만드는 데이터 생성법은 게이트웨이 회귀 테스트용 비정상 호출 시나리오를 만드는 데 가져온다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지만 열람했고 본문과 데이터셋은 정독하지 않았다. 2026년 2월 프리프린트라 동료 심사 여부는 확인하지 못했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive distribution license v1.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
