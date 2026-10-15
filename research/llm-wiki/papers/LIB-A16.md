# LIB-A16 · GHSA-8r9q-7v3j-jr4g (CVE-2026-0621): Anthropic's MCP TypeScript SDK has a ReDoS vulnerability

TypeScript SDK의 UriTemplate 클래스에서 exploded 배열 패턴을 처리하는 정규식이 ReDoS를 일으켜, 조작된 resources/read 요청 하나로 서버가 멈출 수 있었던 취약점 권고다. 1.25.2에서 수정되었다.

## 출처와 확인 수준

- 공식 출처: [GHSA-8r9q-7v3j-jr4g (CVE-2026-0621): Anthropic's MCP TypeScript SDK has a ReDoS vulnerability](https://github.com/advisories/GHSA-8r9q-7v3j-jr4g)
- 유형: 보고서·권고 · 2026년 · GitHub Advisory Database · `security_advisory`
- 저자·발행: 미상 (GitHub Security Advisory)
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- partToRegExp() 함수가 exploded 변수에 대해 중첩 수량자 정규식을 만들어 역추적이 폭증한다.
- 조작된 URI를 담은 resources/read 요청으로 CPU를 점유해 서버를 멈추거나 충돌시킬 수 있다.
- 영향 범위는 1.3.0 이상 1.25.2 미만이며, 1.25.2에서 정규식을 고쳐 역추적을 막았다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이가 리소스 URI를 정책 평가하기 전에 길이 제한, 패턴 검사, 정규식 실행 타임아웃을 적용한다.
- SDK를 1.25.2 이상으로 올리고, exploded 패턴(예: {/id*}, {?tags*})을 쓰는 리소스 템플릿 목록을 점검한다.
- 단일 요청으로 CPU가 점유되는 경우를 가정해 레이트 리밋과 CPU 상한을 둔 테스트 케이스를 만든다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

GHSA 페이지 요약을 확인했다. 우회책은 페이지 기재 내용만 옮겼고, 검색 결과의 '수정 버전 없음' 기술은 페이지와 상충해 채택하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
