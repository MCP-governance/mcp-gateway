# Kong AI Gateway MCP — 상용 문서 확인

확인일: 2026-10-13 · 확인 수준: 공급자 공식 문서 · 코드·제품 시험 미실시.

[AI MCP Proxy 공식 문서](https://developer.konghq.com/plugins/ai-mcp-proxy/)는 기본 ACL과 도구별 ACL, 거부 우선 평가, 도구 목록 필터링·호출 판정을 설명한다. ACL을 구성하지 않으면 허용하는 동작도 문서에 명시한다. 기본 거부 구성과 버전별 HTTP 오류 동작을 실험 조건에 남겨야 한다.

[AI MCP OAuth2 공식 문서](https://developer.konghq.com/plugins/ai-mcp-oauth2/)는 AI Gateway Enterprise·Tech Preview 범위, audience 검증, 사용자 access token의 upstream 미전달, introspection/JWKS 검증을 설명한다. 3.13 이후 처리 변화와 같은 route의 conversion-listener 조합 제한도 표시한다. 적용 버전과 mode를 비교 조건으로 고정한다.

우리 개발에 참고할 것은 인증된 주체 기반의 도구 ACL, discovery와 call의 일관성, 사용자 토큰과 공급자 자격의 분리다. 이들은 이미 다른 제품에서 고려하는 통제다. 우리 이용 관계·계약 hash·실효 행위·개인정보 검사와 같은 입력으로 비교 실험하기 전에는 차별성·성능 우위를 주장하지 않는다.

라이선스 필요 범위는 공식 문서 표시를 확인했으며 가격·계약·국내 인증·도입 가능성은 확인하지 않았다. 제품 소스, 실행 설정, 감사 원장의 위변조 방지, OS 우회 차단은 미확인이다. 공개 문서 전체 복제본은 보관하지 않고 링크와 자체 요약을 보관한다.

2026-10-23 재확인(문서 날짜 미표시, [클라우드 벤치마크 manifest](../analysis/cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json) H1): 도구별 ACL은 v3.13 이후·Enterprise로 표시되고, Konnect MCP 레지스트리는 기술 미리보기다. 로그·추적은 별도 플러그인으로 더하는 구조로 읽힌다. 감사 무결성은 미확인이다.
