# LIB-F05 · AgentSight: System-Level Observability for AI Agents Using eBPF

에이전트 프레임워크 내부를 건드리지 않고 커널의 eBPF 경계에서 암호화된 LLM 트래픽과 시스템 활동을 함께 관측하는 경계 추적(boundary tracing) 기법을 제안한다. 관측한 의도와 실행 효과를 프로세스 경계 너머에서 상관시켜, 어떤 행동이 위험하거나 낭비인지 가려낸다고 설명한다.

## 출처와 확인 수준

- 공식 출처: [AgentSight: System-Level Observability for AI Agents Using eBPF](https://arxiv.org/abs/2508.02736)
- 유형: preprint · 2025년 · arXiv · `preprint`
- 저자·발행: Yusheng Zheng, Yanpeng Hu, Tong Yu, Andi Quinn
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 기존 도구는 에이전트의 상위 의도(LLM 프롬프트)나 하위 행동(시스템 호출) 중 한쪽만 보기 때문에 둘을 잇지 못한다고 지적한다.
- 커널 수준 관측으로 프롬프트 인젝션, 추론 루프, 다중 에이전트 병목을 탐지했다고 보고한다.
- 오버헤드가 3% 미만이라고 초록에서 주장한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 감사 원장에 ‘LLM 의도(요청 요약)’와 ‘실제 실행 효과(파일·네트워크 변화)’를 연결하는 설계 목표로 참고한다. 게이트웨이가 보는 것은 MCP 호출이므로 호스트 효과 관측은 보완 계층으로 둔다.
- 프롬프트 인젝션 탐지와 추론 루프 탐지를 한 관측 파이프라인에서 다루는 구조는 게이트웨이 이상 알림 설계의 참고가 된다.
- 오버헤드가 3% 미만이라는 주장은 배포 전 관측 비용 판단의 근거로만 쓰고, 실측으로 확인한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지만 열람했고 평가 설정과 세부 결과는 확인하지 않았다. eBPF는 리눅스 커널 기능이므로 게이트웨이 배포 OS에서의 지원 범위를 따로 확인해야 한다. 오픈소스 구현의 존재는 검색 요약에서만 확인했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive distribution license v1.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
