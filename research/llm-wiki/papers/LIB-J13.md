# LIB-J13 · Taxonomy of Attacks on Open-Source Software Supply Chains

코드 기여부터 패키지 배포까지 오픈소스 공급망의 모든 단계를 언어와 생태계에 독립적으로 다루는 공격 분류 체계를 제안한다. 공격 트리 형태로 107개 고유 공격 벡터를 정리하고 94개 실제 사고를 대응시키며, 33개 방어 장치와 연결한다.

## 출처와 확인 수준

- 공식 출처: [Taxonomy of Attacks on Open-Source Software Supply Chains](https://arxiv.org/abs/2204.04008)
- 유형: 논문 · 2022년 · IEEE Symposium on Security and Privacy 2023 (arXiv 메타데이터 기준) · `venue_reported_unverified`
- 저자·발행: Piergiorgio Ladisa, Henrik Plate, Matias Martinez, Olivier Barais
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 107개 고유 공격 벡터, 94개 실제 사고, 33개 방어 장치와의 매핑을 초록에서 확인했다.
- 전문가 17명과 개발자 134명 설문으로 분류의 정확성, 포괄성, 유용성을 평가했다고 보고한다.

## 우리 솔루션 개발에 사용할 곳

- MCP 서버 공급망 위협 모델의 공격 벡터 목록을 이 트리에서 가져와, 설치 단계(출처, 의존성 고정, 서명 검증)별 방어 체크리스트를 만든다.
- 33개 방어 장치 목록을 게이트웨이 설계 검토 항목으로 쓰고, 아직 구현하지 않은 항목을 우선순위로 정리한다.
- 94건의 실제 사고를 분류한 방식을 우리 보안 사고 분류 체계의 참고로 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

초록 수준만 확인했고 전문은 정독하지 않았다. 학회 게재 정보는 arXiv 메타데이터 기준이며 DOI는 확인하지 못했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
