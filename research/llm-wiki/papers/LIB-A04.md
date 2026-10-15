# LIB-A04 · SEP-985: Align OAuth 2.0 Protected Resource Metadata with RFC 9728

MCP 스펙이 401 응답에 WWW-Authenticate 헤더를 사실상 필수로 요구하던 부분을 고쳐, 헤더가 없으면 well-known 메타데이터 경로로 폴백하도록 클라이언트 동작을 정한 SEP다. RFC 9728과 정합되도록 바꾸는 변경이다.

## 출처와 확인 수준

- 공식 출처: [SEP-985: Align OAuth 2.0 Protected Resource Metadata with RFC 9728](https://modelcontextprotocol.io/seps/985)
- 유형: 명세·제안 · 2025년 · MCP SEP (Final, Standards Track) · `mcp_sep`
- 저자·발행: sunishsheth2009
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 클라이언트는 헤더를 해석하고, 헤더가 없으면 /.well-known/oauth-protected-resource를 조회한다.
- 서버는 WWW-Authenticate 헤더를 SHOULD로 내보내도록 완화되었다. 헤더 방식은 스코프 증분 인가에 유리하다고 명시된다.
- 중앙 집중형 인증 구조와 동적으로 생성·소멸되는 MCP 인스턴스 환경이 근거로 제시된다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이 클라이언트 측 401 처리에서 헤더의 resource_metadata를 우선 쓰고, 없으면 well-known 경로로 폴백한다. 두 경로가 모두 실패하면 명확한 오류로 끝낸다.
- 중앙 인증 서비스 뒤에 게이트웨이를 두는 배포는 헤더 주입이 어려우므로 well-known 경로 게시를 기본으로 설계한다.
- 발견한 인가 서버 URL은 정책의 허용 목록과 대조한 뒤에만 메타데이터를 가져오게 해서 임의 인가 서버로의 연결을 막는다(설계 제안).

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

SEP 본문 전체를 확인했다. Final 상태이며 현행 스펙 문구와의 차이는 확인하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
