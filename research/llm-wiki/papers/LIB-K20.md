# LIB-K20 · CISA BOD 26-04: Prioritizing Security Updates Based on Risk (BOD 22-01 대체)

연방 민간 행정기관의 취약점 조치 우선순위를 위험으로 정하는 의무 지침이다. 긴급도를 자산 노출(공개 노출 여부), KEV 포함 여부, 익스플로잇 자동화 가능성, 기술적 영향(부분·전체 통제)의 네 변수로 정하고, 조치 기한표(Table 1)는 SSVC에 근거한다. KEV 카탈로그를 유지하며 BOD 22-01을 폐지한다.

## 출처와 확인 수준

- 공식 출처: [CISA BOD 26-04: Prioritizing Security Updates Based on Risk (BOD 22-01 대체)](https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk)
- 관련 출처: <https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk>
- 관련 출처: <https://www.cisa.gov/news-events/directives/bod-22-01-reducing-significant-risk-known-exploited-vulnerabilities-revoked>
- 유형: 정책 문서 · 2026년 · CISA Binding Operational Directive 26-04, 2026-06-10 (구현 지침 갱신 2026-08-25) · `official_publication`
- 저자·발행: CISA
- 판본: 2026-06-10 발령. BOD 19-02와 BOD 22-01을 폐지·대체한다고 본문이 밝힌다. 후보 목록의 BOD 22-01은 폐지(2026-06-10)되어 등록하지 않았다
- 확인일: 2026-10-17 / `full_text_selected_sections_read` — 원문의 지정 절·조문을 직접 읽었다. 읽은 범위: BOD 26-04 본문(배경·정의·범위·필수 조치·CISA 조치·부록 A 도입), 구현 지침 목차·일부, BOD 22-01 폐지 표시 페이지.
- 요약 검토: 지정한 절을 원문에서 직접 읽고 요약했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 본문 '이 지침은 BOD 19-02(2019-04-29)와 BOD 22-01(2021-11-03)을 대체·폐지한다'. BOD 22-01 페이지에는 '폐지됨, BOD 26-04로 대체' 표시가 있다.
- 일정: 즉시(1단계), 60일(2단계, 취약점 관리 절차 갱신), 180일(3단계, Table 1 기한 준수, 외부 도달 자산 식별·태깅). Table 1의 일수 값은 열람한 텍스트에 표 내용이 나오지 않아 확인하지 못했다. '& forensic triage'는 3일 내 조치와 함께 포렌식 트리아지를 하라는 뜻이라고 본문이 정의한다.
- 구현 지침의 포렌식 트리아지는 범위 설정, 증거 보존·수집, 핵심 패치·안정화, 격리·통제, 분석, 상향 판단의 6단계로 구성된다. 범위는 연방 정보시스템이고 계약자는 계약이 정하지 않는 한 적용 대상이 아니다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-39 | 공급망 출처·취약점 대응 |
| POL-43 | 경보 검증·자동 대응 |

## 우리 솔루션 개발에 사용할 곳

- **POL-39**: '정해진 기한 내 조치, 불가하면 격리'의 기한을 정할 때 노출·KEV·자동화·영향 4변수 모델을 사내 기한표 설계의 참고로 쓴다. 연방 기관용 일수를 그대로 가져오지 않는다.
- **POL-43**: KEV 항목에서 포렌식 트리아지가 요구될 때 '중지·격리·영향 범위 조사' 절차에 구현 지침의 6단계를 점검 항목으로 대응시킨다(설계 제안).

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

지침 본문과 구현 지침의 목차·일부를 읽었다. Table 1의 구체 일수, 부속 데이터 스키마(XLSX), 구현 지침의 FAQ는 읽지 못했다. 연방 기관에 대한 의무 지침이며 우리 조직의 법적 의무가 아니다.

페이지에서 별도 이용 조건을 읽지 못했다. 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
