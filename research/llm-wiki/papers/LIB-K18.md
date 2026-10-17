# LIB-K18 · Open Source Vulnerability (OSV) format / schema 1.9.2

오픈소스 패키지의 취약점을 기술하는 표준 교환 JSON 형식이다. 모든 취약점 데이터베이스가 내보내 자동화된 정확한 의존성 취약점 관리를 가능하게 하는 것이 목표이며, 형식은 안정적이고 하위 호환 변경만 가능하다고 밝힌다.

## 출처와 확인 수준

- 공식 출처: [Open Source Vulnerability (OSV) format / schema 1.9.2](https://ossf.github.io/osv-schema/)
- 관련 출처: <https://github.com/ossf/osv-schema>
- 유형: 명세 · 2026년 · OpenSSF osv-schema, 문서 'Version 1.9.2 (October 13, 2026)' · `open_standard`
- 저자·발행: Oliver Chang, Russ Cox (원저자), OpenSSF osv-schema 기여자
- 판본: Version 1.9.2 (2026-10-13). 저장소 최신 태그 v1.9.2
- 확인일: 2026-10-17 / `page_text_read` — 공식 페이지 본문을 읽었다(절 단위 정독 아님). 읽은 범위: 스키마 문서의 목적·형식 개요, 저장소 메타데이터, 태그 목록.
- 요약 검토: 출처 페이지 본문과 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 개요에 나온 최상위 필드는 schema_version, id, modified, published, withdrawn, aliases, upstream, related, summary, details, severity, affected[] 등이다.
- affected[]는 package(ecosystem, name, purl), 버전 범위(ranges)와 열거 버전, 심각도 등을 담아 어떤 패키지 버전이 영향을 받는지 기계가 비교할 수 있게 한다. `withdrawn` 필드가 있다(의미 정의는 읽지 않았다).
- 문서에는 형식 검증용 JSON Schema 링크와 이 형식을 내보내는 데이터베이스 목록 링크가 있다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-39 | 공급망 출처·취약점 대응 |
| POL-03 | 공급망 출처·취약점 대응 |

## 우리 솔루션 개발에 사용할 곳

- **POL-39**: 운영 중 MCP 서버 이미지·의존성의 취약점 판정을 레코드의 affected 범위 비교로 자동화하고, 영향도 평가·조치 기한·격리 결정을 같은 레코드 id에 연결해 기록한다.
- **POL-03**: 도입 단계에서 알려진 취약점 수와 수정 경로 존재를 기계로 확인하는 입력으로 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

스키마 문서의 앞부분(목적·형식 개요)을 읽었고 필드별 상세 정의와 JSON Schema는 읽지 않았다. OSV API·데이터베이스 내용은 확인하지 않았다. 저장소 라이선스(Apache-2.0)는 API 메타데이터로만 확인했다.

GitHub 저장소 메타데이터의 SPDX가 Apache-2.0이다(LICENSE 파일 본문과 문서 별도 조건은 열지 않았다). 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
