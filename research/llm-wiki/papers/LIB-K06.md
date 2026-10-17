# LIB-K06 · Cedar: A New Language for Expressive, Fast, Safe, and Analyzable Authorization

Cedar는 인가 로직을 애플리케이션 코드 밖의 정책으로 쓰게 하는 정책 언어다. 정책 검증기가 선택적 타입으로 실수를 막고, 논리 인코딩이 건전·완전해 정책을 리팩터링해도 허용 권한이 변하지 않는지 같은 정밀 분석이 가능하다고 한다. Lean으로 설계 성질을 증명하고 Rust로 구현·공개했으며, OpenFGA·Rego와 비교해 가독성은 주관적으로 대등 이상, 성능은 훨씬 낫다고 보고한다(초록).

## 출처와 확인 수준

- 공식 출처: [Cedar: A New Language for Expressive, Fast, Safe, and Analyzable Authorization](https://doi.org/10.1145/3649835)
- 관련 출처: <https://arxiv.org/abs/2403.04651>
- 관련 출처: <https://github.com/cedar-policy/cedar>
- 유형: 논문 · 2024년 · Proc. ACM Program. Lang. 8(OOPSLA1), 2024, pp. 670–697 (OOPSLA 2024) · `official_publication`
- 저자·발행: Joseph W. Cutler, Craig Disselkoen, Aaron Eline, Shaobo He, Kyle Headley, Michael Hicks 외 9명
- 판본: ACM 판 2024-04-29 게재(Crossref). arXiv 확장판 v2(2024-03-08)의 초록·저자·라이선스 표기를 확인했다
- 확인일: 2026-10-17 / `bibliographic_and_abstract_checked` — 서지와 초록을 출판사·집계 메타데이터와 대조했다(본문 정독 아님). 읽은 범위: Crossref 서지, arXiv abs 페이지 초록, arXiv v2 PDF 앞 3쪽, GitHub 저장소 메타데이터.
- 요약 검토: 초록을 원문·출판사 메타데이터와 직접 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 초록은 역할·속성·관계 기반 접근 제어의 개념을 읽기 쉬운 문법으로 담는다고 설명한다. 정책 구조 덕에 접근 요청을 빠르게 판정할 수 있다고 한다.
- 정책 분석의 예로 정책 집합을 리팩터링할 때 인가된 권한이 바뀌지 않는지 확인하는 것을 든다.
- ACM 판은 CC BY 4.0(Crossref VoR 라이선스 정보)이고 arXiv PDF 앞부분에도 CC BY 4.0 표기가 있다. 구현 저장소는 Apache-2.0이다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-37 | 정책 변경 시험·동치 분석 |
| POL-22 | 정책 변경 시험·동치 분석 |
| POL-23 | 정책 변경 시험·동치 분석 |

## 우리 솔루션 개발에 사용할 곳

- **POL-37·POL-22**: 정책(룰셋) 교체·변경이 허용 집합을 넓히지 않는지 보는 '변경 전후 동치·포함 분석'의 개념 근거로 쓴다. Rego에는 같은 분석기가 없으므로 대표 요청 집합을 만들어 변경 전후 결정을 비교하는 회귀 시험으로 대체하는 것이 현실적이다(설계 제안).
- **POL-23**: principal·action·resource·context로 요청을 나누는 구조를 게이트웨이 정책 입력(주체·기능·자산·맥락)의 필드 설계와 비교한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

Crossref 서지와 arXiv 확장판의 초록·저자·라이선스 표기(PDF 앞 3쪽)만 확인했다. ACM 사이트는 봇 차단(403)이라 열지 못했다. 성능 수치, Lean 증명, Rego 비교 방법은 읽지 않았고 재현하지 않았다. Cedar 도입은 결정하지 않았다.

CC BY 4.0 (Crossref 라이선스 정보, arXiv PDF 앞부분 표기). 저자·제목·출처를 표기한다. 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
