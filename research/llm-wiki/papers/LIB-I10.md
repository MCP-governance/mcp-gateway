# LIB-I10 · Adversarial Machine Learning: A Taxonomy and Terminology of Attacks and Mitigations (NIST AI 100-2e2025)

적대적 머신러닝의 공격과 완화를 분류하고 용어를 정의한 NIST 보고서다. 공격자의 목표, 능력, 지식, 공격 생애주기, 생애주기별 완화 방법과 용어집을 담아 다른 표준과 실무 지침이 참조할 공통 언어를 만든다.

## 출처와 확인 수준

- 공식 출처: [Adversarial Machine Learning: A Taxonomy and Terminology of Attacks and Mitigations (NIST AI 100-2e2025)](https://csrc.nist.gov/pubs/ai/100/2/e2025/final)
- 유형: 보고서·권고 · 2025년 · NIST · `official_publication`
- 저자·발행: Apostol Vassilev, Alina Oprea, Alie Fordyce, Hyrum Anderson, Xander Davies, Maia Hamin
- 확인일: 2026-10-14 / `page_fetched_title_manually_accepted` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 분류 체계는 ML 방법 계열, 공격 생애주기, 공격자 목표·능력·지식의 순서로 구성된다(초록 기준).
- 보고서의 목적은 AML 분야의 공통 용어를 세우고 다른 표준이 참조하도록 하는 것이다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 설계 문서와 위협 모델의 용어를 이 분류 체계에 맞춘다. 예를 들어 회피, 포이즈닝, 프롬프트 인젝션을 같은 이름으로 쓴다.
- 공격자의 능력과 지식 축을 위협 모델의 가정표로 쓴다(예: 공격자가 도구 설명을 읽을 수 있는가, 게이트웨이 정책을 아는가).
- 생애주기 단계 분류로 게이트웨이의 점검 지점(도구 등록, 계약 변경, 런타임 호출)을 나눠 배치한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

CSRC 상세 페이지의 초록과 메타데이터만 확인. PDF 본문은 이 환경에서 읽지 못해 미정독. 프롬프트 인젝션과 에이전트 관련 장의 존재와 내용은 확인하지 못함. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
