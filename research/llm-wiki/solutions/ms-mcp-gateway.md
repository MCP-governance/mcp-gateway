# Microsoft MCP Gateway — 소유권·역할 권한 평가

확인일: 2026-10-13 · 확인 수준: 고정 커밋 C# 코드 검토 · 라이선스: MIT.

[검토 커밋](https://github.com/microsoft/mcp-gateway/tree/3594c4eee36308ac131aad1c946ea14140b4353d): `3594c4eee36308ac131aad1c946ea14140b4353d`. 기존 `docs/ai/BENCHMARK_MICROSOFT.md`의 경로를 실제 소스와 대조했다.

## 코드로 확인한 사실

[SimplePermissionProvider.cs:18–96](https://github.com/microsoft/mcp-gateway/blob/3594c4eee36308ac131aad1c946ea14140b4353d/dotnet/Microsoft.McpGateway.Management/src/Authorization/SimplePermissionProvider.cs#L18-L96)은 읽기·쓰기를 분리한다. 읽기는 생성자·`mcp.admin`·`RequiredRoles`와의 역할 일치에 허용하고, `RequiredRoles`가 비면 일반 사용자에게 허용하지 않는다. 쓰기는 소유자 또는 관리자에게 허용한다. 빈 설정이면 누구나 통과한다고 설명하면 틀린다.

[BuiltinToolAuthorizer.cs:18–40](https://github.com/microsoft/mcp-gateway/blob/3594c4eee36308ac131aad1c946ea14140b4353d/dotnet/Microsoft.McpGateway.Management/src/Authorization/BuiltinToolAuthorizer.cs#L18-L40)은 내장 도구 허용 역할에 기본 `mcp.admin`을 넣고 구성된 `RequiredRoles`를 합친다. 신원은 전달된 `ClaimsPrincipal`의 역할로 평가한다. 이 발췌만으로 인증 미들웨어의 전체 신뢰 경계를 입증하지 않는다.

## 채택 판단

관리자가 등록한 도구와 등록 소유자의 권한을 구분하는 모델은 개발 참고 대상이다. 우리 이용 관계·허용 자원·실효 행위와 이 코드의 관리 자원 권한은 입력 단위가 다르다. 도구 이름·관리 자원 역할만으로 개인정보 반출·SQL의 쓰기 효과까지 같은 범위에서 통제한다고 비교하지 않는다.

검증 후보는 관리자·소유자·역할 일치·빈 역할·다른 소유자라는 다섯 권한 조합이다. 기존 코드에 정책 엔진을 추가하기 전에 관리 API 권한과 실제 `tools/call` 집행 경로가 모두 같은 조건을 쓰는지 추적한다.

## 확보 증거와 한계

[권한 평가 발췌](evidence/ms-mcp-gateway/dotnet__Microsoft.McpGateway.Management__src__Authorization__SimplePermissionProvider.cs.excerpt.txt), [내장 도구 인가 발췌](evidence/ms-mcp-gateway/dotnet__Microsoft.McpGateway.Management__src__Authorization__BuiltinToolAuthorizer.cs.excerpt.txt), [라이선스](evidence/ms-mcp-gateway/LICENSE.txt), [NOTICE](evidence/ms-mcp-gateway/NOTICE.txt), [해시 목록](evidence/manifest.json).

Microsoft 제품 전체·APIM·Foundry 기능과 혼동하지 않는다. Azure 배포, Entra 토큰 검증, 세션 라우팅, 실제 권한 회수는 실행하지 않았다. endpoint OS 통제가 이 Gateway 코드로 입증되는 것도 아니다.

## 세션 라우팅 키 (2026-10-15 추가)

같은 커밋 `3594c4e`의 [`AdapterSessionRoutingHandler.cs`](https://github.com/microsoft/mcp-gateway/blob/3594c4eee36308ac131aad1c946ea14140b4353d/dotnet/Microsoft.McpGateway.Service/src/Session/AdapterSessionRoutingHandler.cs#L52-L120)는 세션 저장소 키를 `사용자:어댑터:세션ID`로 묶어, 다른 사용자가 세션 ID를 재생하거나 권한이 회수된 어댑터 경로로 재생해도 대상을 찾지 못하게 한다([시험](https://github.com/microsoft/mcp-gateway/blob/3594c4eee36308ac131aad1c946ea14140b4353d/dotnet/Microsoft.McpGateway.Service/test/AdapterSessionRoutingHandlerTests.cs#L135-L160)). 정적 읽기이며 실행하지 않았다. 10-14 보고의 2차 자료 인용을 이 소스로 대체한다. 적용 검토는 [세션 재사용 설계 비교](../analysis/upstream-session-reuse/README.md).
