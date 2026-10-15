# LIB-H01 · Microsoft Presidio (GitHub: microsoft/presidio)

텍스트와 이미지의 PII를 탐지하고 익명화하는 맥락 인식 플러그형 오픈소스 SDK로, 탐지를 담당하는 Analyzer와 치환·마스킹을 담당하는 Anonymizer가 분리되어 있다. 탐지는 NER, 정규식, 규칙, 체크섬을 문맥 단어와 함께 쓰며, 이미지 redactor와 구조화 데이터용 패키지도 제공한다.

## 출처와 확인 수준

- 공식 출처: [Microsoft Presidio (GitHub: microsoft/presidio)](https://github.com/microsoft/presidio)
- 유형: 도구 문서 · 2018년 · GitHub · `official_publication`
- 저자·발행: Microsoft Presidio 메인테이너 (저장소 기준)
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- README 기준 탐지는 NER, 정규식, 규칙, 체크섬을 문맥과 함께 쓰며, 자동 탐지가 모든 민감정보를 찾는다고 보장할 수 없다고 명시한다.
- 다중 언어 recognizer를 지원하고, 커스텀 recognizer를 API나 코드로 추가할 수 있다고 설명한다.
- 외부 PII 탐지 모델을 연결하는 구조도 지원한다고 적혀 있다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이의 도구 호출 인자와 응답 경로에서 Analyzer로 PII 엔티티를 찾고 Anonymizer로 마스킹하는 1차 필터로 쓴다. 감사 원장에는 원문 대신 엔티티 유형과 위치만 남긴다.
- 한국어 식별자(주민등록번호, 휴대전화번호 등)는 기본 제공 여부를 먼저 확인하고, 부족하면 정규식과 체크섬 검증을 갖춘 커스텀 recognizer로 추가한다.
- 탐지기를 바꾸더라도 엔티티별 처리 방식(마스킹, 차단, 승인 요구)은 정책 파일에서 관리해 OPA 입력과 분리한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

GitHub 저장소 메인 페이지와 릴리스 API만 열람했다. 공식 문서 사이트(microsoft.github.io/presidio)는 리다이렉트 안내 페이지만 열려 내용을 확인하지 못했다. 연도는 저장소 생성 연도(2018)이며 최신 릴리스는 2026-07-22다. 탐지 정확도 수치는 이 항목에서 다루지 않는다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

MIT

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
