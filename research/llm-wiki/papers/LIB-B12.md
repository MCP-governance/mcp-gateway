# LIB-B12 · TRUSTDESC: Preventing Tool Poisoning in LLM Applications via Trusted Description Generation

도구 설명을 서버가 쓴 문구에 기대지 않고 도구 구현 코드에서 직접 생성하는 방어 TRUSTDESC를 제안한다. 코드 조각 추출, 오해 소지 문구 필터링, 동적 실행으로 설명의 행동 주장을 검증하는 세 단계로 구성된다.

## 출처와 확인 수준

- 공식 출처: [TRUSTDESC: Preventing Tool Poisoning in LLM Applications via Trusted Description Generation](https://arxiv.org/abs/2604.07536)
- 유형: preprint · 2026년 · arxiv.org · `preprint`
- 저자·발행: Hengkai Ye, Zhechang Zhang, Jinyuan Jia, Hong Hu
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 기존 탐지가 명백한 이상 지시에 치우쳐 암묵적이고 오해를 부르는 주장에는 약하다고 문제를 제기한다.
- 52개 실환경 도구 집합에서 평가했다고 밝히고, 설명 정확도와 작업 완료 개선을 주장한다.
- 추가 시간과 비용이 작다고 주장한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이가 도구 설명과 실제 호출 결과 샘플을 비교해, 설명에 없는 부작용(외부 전송, 파일 쓰기 등)이 보이면 설명 불일치 플래그를 남긴다.
- 서버 코드를 받을 수 없는 경우에도 동적 실행 검증 아이디어를 격리된 테스트 환경에서만 축소 적용해, 등록 시 설명 주장을 점검한다.
- 설명이 선언하는 동작 목록을 OPA의 허용 동작 목록과 맞춰, 선언하지 않은 동작은 기본 거부한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv 초록 페이지를 열어 확인했고 평가 세부와 비교 기준선은 읽지 않았다. 코드 접근을 전제로 해서, 외부 서버를 쓰는 게이트웨이에 바로 적용하기 어렵다는 판단은 초록을 바탕으로 한 내 판단이다. 2026-04 제출된 프리프린트라 동료 심사 여부는 확인하지 못했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

CC BY 4.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
