# LIB-K21 · FIRST EPSS (Exploit Prediction Scoring System) — 모델 v5 (v2026.06.15)

CVE마다 향후 30일 안에 악용 활동이 관찰될 확률(0~1)을 매일 공개하는 모델이다. FAQ는 EPSS가 완전한 위험 점수가 아니며 보편 임계값은 없다고 밝히고, 확률과 백분위의 차이를 설명한다.

## 출처와 확인 수준

- 공식 출처: [FIRST EPSS (Exploit Prediction Scoring System) — 모델 v5 (v2026.06.15)](https://www.first.org/epss/)
- 관련 출처: <https://www.first.org/epss/faq>
- 관련 출처: <https://www.first.org/epss/data>
- 유형: 데이터 서비스 · 2026년 · FIRST EPSS SIG, 점수 생성·공개는 Empirical Security · `official_publication`
- 저자·발행: FIRST EPSS Special Interest Group (점수 제공: Empirical Security)
- 판본: Get the Data 페이지의 모델 이력: v1(2021-04-14) → v2 2022-02-04 → v3 2023-03-07 → v4(v2025.03.14) 2025-03-17 → v5(v2026.06.15) 2026-06-15
- 확인일: 2026-10-17 / `page_text_read` — 공식 페이지 본문을 읽었다(절 단위 정독 아님). 읽은 범위: FAQ, Get the Data(모델 이력·접근 방법), How It Works 일부.
- 요약 검토: 출처 페이지 본문과 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 점수는 관찰된 악용 활동의 향후 30일 확률 추정이며, 환경 맥락·보완 통제·피해 크기는 반영하지 않으므로 완전한 위험 계산에는 환경 정보와 영향이 더해져야 한다고 FAQ가 적는다.
- 보편 임계값은 없다. 0.10 임계값은 현장에서 자주 인용되지만 EPSS가 부여한 권위는 없고, 조치 용량과 위험 허용도에 맞춰 정하라고 한다. 확률 0.10이 현재 약 95번째 백분위에 해당한다고 설명한다.
- CSV·API로 무료·등록 없이 공개되며 출판물·제품에 쓸 때는 출처 표시를 요청한다. 모델 버전이 바뀔 때마다 점수 이동이 있어 시계열이 방법론 변화를 포함할 수 있다고 경고한다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-39 | 공급망 출처·취약점 대응 |

## 우리 솔루션 개발에 사용할 곳

- **POL-39**: KEV 포함 여부와 함께 영향도 평가의 '악용 가능성' 입력으로 쓰되 임계값은 우리 조치 용량으로 정한다. 점수와 모델 버전을 함께 기록해 시계열 비교의 방법론 변화를 구분한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

홈페이지, FAQ, Get the Data, How It Works 페이지의 일부를 읽었다. 모델 방법론 논문과 실제 데이터 파일·API는 열지 않았다. 점수는 통계 추정이며 개별 취약점의 악용을 보증하지 않는다.

FAQ·데이터 페이지: 무료 공개, 등록 불필요, 출처 표시 요청(구체 문구는 Get the Data 페이지 참조). 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
