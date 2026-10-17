# LIB-K19 · CISA Known Exploited Vulnerabilities (KEV) Catalog

실제 악용이 확인된 취약점(CVE) 목록으로 CISA가 관리하며 JSON·CSV로 배포된다. 항목에는 cveID, vendorProject, product, dateAdded, requiredAction, dueDate, knownRansomwareCampaignUse, forensicTriage, notes, cwes 등이 있다.

## 출처와 확인 수준

- 공식 출처: [CISA Known Exploited Vulnerabilities (KEV) Catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)
- 관련 출처: <https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json>
- 관련 출처: <https://www.cisa.gov/sites/default/files/licenses/kev/license.txt>
- 유형: 데이터 서비스 · 2026년 · CISA (미국 사이버보안·인프라보안청) 카탈로그, JSON 카탈로그 버전 2026.10.16 · `official_publication`
- 저자·발행: CISA
- 판본: catalogVersion 2026.10.16, dateReleased 2026-10-16T17:15:48Z, 등록 1,748건(열람 시점)
- 확인일: 2026-10-17 / `page_text_read` — 공식 페이지 본문을 읽었다(절 단위 정독 아님). 읽은 범위: 카탈로그 페이지, JSON 피드 헤더·첫 항목, KEV 라이선스 문서, GitHub 미러 메타데이터.
- 요약 검토: 출처 페이지 본문과 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 열람한 JSON 피드는 catalogVersion 2026.10.16, 1,748건이며 최신 항목의 requiredAction은 BOD 26-04의 지침 준수를 요구하고 forensicTriage 필드로 포렌식 트리아지 필요 여부를 표시한다.
- 카탈로그 페이지에는 KEV 포함 기준, 신규 KEV 추천, CSV·JSON 내려받기, JSON Schema(2026-09-02 갱신), 라이선스 링크가 있다.
- KEV 데이터는 CC0 1.0으로 배포된다는 라이선스 문서를 CISA 사이트에서 확인했다. 제3자 링크의 정보는 각자의 정책을 따른다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-39 | 공급망 출처·취약점 대응 |

## 우리 솔루션 개발에 사용할 곳

- **POL-39**: 운영 중인 MCP 서버·의존성의 CVE가 KEV에 있으면 '악용 확인' 신호로 기한 내 조치·격리 대상으로 분류하는 입력이다. JSON의 dueDate는 연방 기관용 기한이므로 우리 기한 정책과 구분해 기록한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

카탈로그 페이지·JSON 헤더와 첫 항목, 라이선스 문서만 확인했다. KEV는 악용이 확인된 목록일 뿐 모든 위험을 포함하지 않으며, 제품 이름을 우리 의존성 식별자(PURL·CPE)와 맞추는 문제는 다루지 않았다. dueDate는 연방 기관 기준이다.

CC0 1.0 (CISA 사이트의 KEV 라이선스 문서, cisagov/kev-data LICENSE). CISA 로고·DHS 직인 사용이나 보증 암시는 허용하지 않는다. 데이터를 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
