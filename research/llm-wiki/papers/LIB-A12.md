# LIB-A12 · SEP-991: Enable URL-based Client Registration using OAuth Client ID Metadata Documents

HTTPS URL을 client_id로 쓰고, 그 URL이 가리키는 JSON 메타데이터 문서로 클라이언트를 식별하는 방식(CIMD)을 MCP 클라이언트 등록 수단으로 추가하는 SEP다. 사전 등록이나 DCR 없이 처음 보는 서버에 연결하는 상황을 겨냥한다.

## 출처와 확인 수준

- 공식 출처: [SEP-991: Enable URL-based Client Registration using OAuth Client ID Metadata Documents](https://modelcontextprotocol.io/seps/991)
- 유형: 명세·제안 · 2025년 · MCP SEP (Final, Standards Track) · `mcp_sep`
- 저자·발행: Paul Carleton (@pcarleton), Aaron Parecki (@aaronpk)
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 서버는 URL형 client_id의 문서를 가져와 client_id 일치와 redirect_uri 허용 여부를 검증해야 한다.
- SSRF, localhost 클라이언트 가장, DDoS 위험을 명시하고, 캐시·타임아웃·크기 제한·사용자 인증 후 fetch 같은 완화책을 제시한다.
- 참조 규격(draft-parecki-oauth-client-id-metadata-document-03)이 아직 초안이어서 성숙도 위험이 있다고 SEP 스스로 적는다.

## 우리 솔루션 개발에 사용할 곳

- URL형 client_id를 처리할 때, 메타데이터를 가져오기 전에 스킴(https)과 호스트·IP를 검증하고 응답 크기, 타임아웃, 캐시 상한을 둔다. SSRF를 막기 위한 체크리스트로 쓴다.
- 클라이언트 신뢰 정책을 도메인 허용 목록으로 두고, client_id와 메타데이터 해시를 감사 원장에 남긴다.
- localhost 리다이렉트를 쓰는 클라이언트에 대해 경고를 띄운다는 SEP 권고를 게이트웨이 동의 화면에 반영한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

SEP 본문 전체를 확인했다. 참조 IETF 초안은 열어보지 않았다. 2026-07-28 개정에서 DCR이 비권장으로 바뀌었다는 2차 자료가 있으나 공식 스펙으로는 확인하지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
