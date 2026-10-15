# LIB-I09 · Regulation (EU) 2024/1689 (AI Act), Article 15: Accuracy, robustness and cybersecurity

고위험 AI 시스템이 정확성, 견고성, 사이버보안 수준을 갖추고 수명 주기 전반에서 일관되게 유지하도록 요구한다. 제5항은 권한 없는 제3자가 취약점을 악용해 시스템 사용, 출력, 성능을 바꾸려는 시도에 대한 복원력을 명시한다.

## 출처와 확인 수준

- 공식 출처: [Regulation (EU) 2024/1689 (AI Act), Article 15: Accuracy, robustness and cybersecurity](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-15)
- 유형: 표준·규제 · 2024년 · EU AI Act Service Desk · `official_publication`
- 저자·발행: EU 입법기관(Regulation 2024/1689), 요약은 Commission AI Act Service Desk
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 제5항(사이버보안)은 데이터 포이즈닝, 모델 포이즈닝, 적대적 입력(회피), 기밀성 공격, 모델 결함을 위협 예로 든다(Service Desk 요약 기준).
- 제4항은 중복성(백업, 페일세이프)과 학습 중 피드백 루프 완화를 요구한다.

## 우리 솔루션 개발에 사용할 곳

- 도구 설명과 스키마 변경 탐지를 제5항 대응 통제로 문서화하고, 무단 변경이 감지되면 해당 도구 호출을 막는 정책을 둔다.
- 데이터·모델 포이즈닝과 적대적 입력에 대응해 도구 응답의 무결성 검사와 지시문 탐지를 게이트웨이 입력 검증 계층에 둔다.
- 제3항의 정확도 지표 기재 요구에 맞춰, 정책 적용 효과(차단율, 마스킹 누락률)를 측정 지표로 남긴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

Service Desk 요약만 확인하고 EUR-Lex 원문은 대조하지 않음. 2차 사이트가 제시한 세부 공격 유형(모델 역추론, 모델 추출 등)은 원문에서 확인하지 못해 제외했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
