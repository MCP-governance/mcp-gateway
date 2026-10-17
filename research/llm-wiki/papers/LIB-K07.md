# LIB-K07 · Semantic-based Automated Reasoning for AWS Access Policies using SMT

AWS 접근 정책 언어를 형식화하고 정책 속성을 검증하는 분석 도구 Zelkova를 소개한다. 정책 의미를 SMT로 인코딩해 동작을 비교하고 속성을 검증하며, 정책 설정 실수를 건전하게 찾는다. 문제는 PSPACE-complete이지만 매일 수백만 번 호출된다고 초록이 밝힌다.

## 출처와 확인 수준

- 공식 출처: [Semantic-based Automated Reasoning for AWS Access Policies using SMT](https://www.amazon.science/publications/semantic-based-automated-reasoning-for-aws-access-policies-using-smt)
- 관련 출처: <https://doi.org/10.23919/FMCAD.2018.8602994>
- 유형: 논문 · 2018년 · 2018 Formal Methods in Computer Aided Design (FMCAD), pp. 1–9, IEEE, 2018-10 · `official_publication`
- 저자·발행: John Backes, Pauline Bolignano, Byron Cook, Catherine Dodge, Andrew Gacek, Kasper Luckow, Neha Rungta, Oksana Tkachuk, Carsten Varming
- 판본: IEEE 판 DOI 10.23919/FMCAD.2018.8602994(Crossref). Amazon Science가 호스팅하는 PDF의 초록을 대조했다
- 확인일: 2026-10-17 / `bibliographic_and_abstract_checked` — 서지와 초록을 출판사·집계 메타데이터와 대조했다(본문 정독 아님). 읽은 범위: Crossref 서지, Amazon Science 출판 페이지의 초록, 호스팅 PDF 1쪽.
- 요약 검토: 초록을 원문·출판사 메타데이터와 직접 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 도구가 던지는 질문의 예는 '이 자원이 특정 사용자에게 열려 있는가', '임의 사용자가 이 자원에 쓸 수 있는가'이며, 검증할 속성을 정책 언어 자체로 표현한다고 도입부가 설명한다.
- 문자열 와일드카드(*, ?) 때문에 결정 문제는 PSPACE-complete이지만 실제 정책 질문의 99%는 160ms 안에 답한다고 본문이 보고한다.
- 기존의 휴리스틱 구문 검사는 정책 의미를 다 보지 못해 건전하지 않다는 점을 동기로 든다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-37 | 정책 변경 시험·동치 분석 |
| POL-25 | 데이터 등급 |

## 우리 솔루션 개발에 사용할 곳

- **POL-37·POL-25**: 허용목록·정책 변경이 공개 범위를 넓히지 않는지(예: '모든 사용자에게 열린 자원이 생겼는가') 묻는 질의형 검증의 사례다. 우리 정책 변경 시험에서 '임의 주체' 요청을 합성해 허용되는지 보는 음성 시험으로 단순화할 수 있다(설계 제안).

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

초록과 PDF 1쪽(도입부)만 읽었다. AWS IAM 정책 언어 전용이라 OPA/Rego에 바로 쓸 수 없다. IEEE 판은 열지 않았고 서지는 Crossref로 대조했다. 성능 수치는 저자 보고다.

라이선스 미확인: IEEE 게재 논문이며 Amazon Science가 PDF를 호스팅한다. 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
