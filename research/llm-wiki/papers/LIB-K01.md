# LIB-K01 · OSCAL (Open Security Controls Assessment Language) v1.2.3 — Control Mapping Model

OSCAL은 통제 카탈로그·프로파일·평가 정보를 XML·JSON·YAML로 나타내는 NIST 주도의 개방 형식이다. 통제 매핑 모델은 서로 다른 출처의 통제 사이의 관계를 원문을 복제하지 않고 기록하며, 관계값(equivalent-to, equal-to, subset-of, superset-of, intersects-with, no-relationship)과 분석 방법(구문·의미·기능)을 따로 적게 한다.

## 출처와 확인 수준

- 공식 출처: [OSCAL (Open Security Controls Assessment Language) v1.2.3 — Control Mapping Model](https://pages.nist.gov/OSCAL/learn/concepts/layer/control/mapping/)
- 관련 출처: <https://pages.nist.gov/OSCAL/>
- 관련 출처: <https://github.com/usnistgov/OSCAL/releases/tag/v1.2.3>
- 관련 출처: <https://raw.githubusercontent.com/usnistgov/OSCAL/main/LICENSE.md>
- 유형: 명세 · 2026년 · NIST OSCAL 프로젝트 (usnistgov/OSCAL 릴리스 v1.2.3, 2026-08-07) · `official_publication`
- 저자·발행: NIST (OSCAL 프로젝트)
- 판본: OSCAL v1.2.3 (GitHub 릴리스 2026-08-07, 패치 릴리스). 홈페이지 갱신일 2026-06-02
- 확인일: 2026-10-17 / `page_text_read` — 공식 페이지 본문을 읽었다(절 단위 정독 아님). 읽은 범위: 매핑 모델 개념 문서 전체 본문, 홈페이지, 릴리스 v1.2.3 본문, LICENSE.md. 스키마·도구 미열람.
- 요약 검토: 출처 페이지 본문과 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 매핑 모델의 목적은 표준·규제·프레임워크·지침의 통제들이 서로 어떻게 대응하는지를 원문을 되풀이하지 않고 기계가독으로 적는 것이라고 개념 문서가 밝힌다.
- 개념 문서의 예에서 "TLS를 구현한다"는 통제와 "TLS 1.2 이상을 구현한다"는 통제는 구문 방법에서는 subset-of, 기능 방법에서는 superset-of로 서로 다르게 기록된다. 같은 두 통제도 비교 방법에 따라 관계가 달라진다.
- 최신 릴리스 v1.2.3(2026-08-07)은 의존성 갱신 위주의 패치 릴리스이고, 저장소는 CC0 1.0으로 공개 도메인에 배포된다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-01~POL-50 | 정책 번호 체계 표류 |

## 우리 솔루션 개발에 사용할 곳

- **POL-01~POL-50 전체**: 엑셀 POL-xx ↔ 독스용 PAC50 ↔ 원본 PAC01~24 ↔ 런타임 PAC-01~15 대응을 번호 일치가 아니라 '출처 ID·대상 ID·관계값·비교 방법·비고' 레코드로 적는다. 현재 policy-50-crosswalk.json의 `mapping_basis`(의미 대응, 번호 일치 아님)를 같은 어휘로 구조화하는 최소 경로다.
- **부분 구현 판정**: 런타임 PAC 하나가 POL 여러 개 중 일부만 충족하는 경우를 subset-of·intersects-with로 적으면 '완전/부분/미구현' 판정의 근거와 남은 공백(no-relationship)을 같은 표에 둘 수 있다.
- **도입 범위**: OSCAL 도구 전체 도입은 필요 없다. 관계값 어휘와 id-ref 방식만 차용하고 JSON 스키마 검증 가능 여부는 별도로 확인한다(설계 제안).

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

개념 문서·릴리스 노트·LICENSE.md만 읽었다. OSCAL JSON/XML 스키마, 모델 정의, 도구(oscal-cli, Trestle 등)는 열지 않았고 매핑 모델이 어느 OSCAL 판본에서 도입됐는지도 확인하지 않았다. 우리 크로스워크에 적용해 시험하지 않았다.

CC0 1.0 (저장소 LICENSE.md: 미국 정부 저작물 + CC0 1.0 공개 도메인 선언). NIST를 출처로 명시해 달라는 요청이 있다. 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
