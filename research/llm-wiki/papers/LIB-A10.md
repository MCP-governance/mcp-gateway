# LIB-A10 · GHSA-7f8r-222p-6f5g (CVE-2025-49596): MCP Inspector proxy server lacks authentication between the Inspector client and proxy

MCP Inspector 0.14.1 미만에서 클라이언트와 프록시 사이에 인증이 없어, 인증되지 않은 요청으로 stdio MCP 명령을 실행할 수 있었던 원격 코드 실행 취약점 권고다. 0.14.1에서 수정되었다.

## 출처와 확인 수준

- 공식 출처: [GHSA-7f8r-222p-6f5g (CVE-2025-49596): MCP Inspector proxy server lacks authentication between the Inspector client and proxy](https://github.com/advisories/GHSA-7f8r-222p-6f5g)
- 유형: 보고서·권고 · 2025년 · GitHub Advisory Database · `security_advisory`
- 저자·발행: 미상 (GitHub Security Advisory)
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 근본 원인은 Inspector 클라이언트가 프록시에 인증하지 않아 프록시가 인증 없는 요청을 받는 구조다(CWE-306).
- 인증 없는 요청으로 stdio를 통해 MCP 명령을 실행할 수 있어 원격 코드 실행으로 이어진다.
- 0.14.1에서 수정되었고 CVSS v4 기준 9.4(Critical)다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이의 로컬 제어 채널이나 관리 포트는 인증 없이 열지 않는 것을 설계 원칙으로 두고, 인증 없는 요청이 거부되는지를 회귀 테스트에 넣는다.
- 개발자용 디버그 도구는 0.14.1 이상으로 고정하고, 배포 가이드에 업그레이드 필요성을 명시한다.
- 인증 없이 stdio 명령이 전달되는 경로가 정책 엔진의 deny-by-default 테스트에서 실패하도록 케이스를 추가한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

GitHub advisory 페이지 요약 기준이다. 공격 체인의 세부 경로와 익스플로잇 존재 여부는 확인하지 않았다. 검색 결과의 브라우저 기반 공격 설명은 검증되지 않아 제외했다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
