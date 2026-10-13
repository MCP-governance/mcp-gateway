# MCP 및 관련 실험 대상

확인일: 2026-10-13. 로컬 목록은 [registry/catalog.toml](../../../full_stack_lab/registry/catalog.toml)의 package/version을 정적으로 확인했다. 아래 10종의 현재 field 배포·기동·tool schema는 미확인이다. 기존 field 하네스 표본과 이 후보 목록을 구분한다.

## 로컬 범위와 우선순위

로컬 MCP는 포함돼 있다. 다만 두 실행 경로를 구분한다.

1. **솔루션 기기의 자체 운영 MCP:** 아래 10종. [run-server.sh](../../../full_stack_lab/mcp/run-server.sh)는 filesystem·git·fetch·memory·desktop·postgres·redis의 stdio를 `mcp-proxy` 뒤 Streamable HTTP로 연결한다. email·gitea·playwright는 HTTP 경로다. PJ1 하네스→Gateway→내부 MCP 경로에서 정책과 실제 효과를 확인한다.
2. **PJ1에서 직접 실행하는 로컬 MCP:** `stdio`, localhost HTTP, 별도 interpreter·실행 파일 경로. 이 경로는 Gateway를 거치지 않으면 도구 단위 원장이 생기지 않는다. 기존 12개 카드에 전용 시험이 없었으므로 [E13](E13-local-bypass.md)을 추가했다. 관리형 Linux의 비승인 실행·직접 접속 차단을 검증하며, 모든 in-process 플러그인·Windows 앱까지 보호한다고 주장하지 않는다.

현재 field 레지스트리는 이 10종 lab 레지스트리와 별도다. [기존 실기기 보고](../status/reports/2026-10-13-development-results.md)는 Context7 실제 호출을 기록했지만 공급자 quota로 정상 문서 조회는 미완료였다. 로컬 10종이 모두 설치·활성화·통과했다는 결과는 없다.

먼저 **수신 횟수·파일/DB 효과를 직접 확인할 수 있는 격리 mock, filesystem, fetch, email sink**를 준비한다. 다음으로 git·postgres·redis·memory, 마지막으로 desktop·playwright·gitea와 원격 OAuth 후보를 진행한다. 패키지와 schema는 후보 목록의 판본을 설치 시 재확인하고 승인 계약을 고정한다. 취약 판본은 도입 거부 메타데이터 fixture로만 사용한다.

솔루션 스택과 자체 운영 fixture는 솔루션 기기에만 배치하고, 실제 하네스는 PJ1에서 실행한다. 사용자 노트북에서 제품 Compose를 기동하지 않는다. 공유 field의 기존 계약·계정·종료 관계는 교체하지 않고 시험용 대상만 별도로 등록한다.

## 저장소에 준비된 10종 MCP

| 서버 | 고정 패키지·버전 | 시험 소재 |
| --- | --- | --- |
| filesystem | `@modelcontextprotocol/server-filesystem@2026.8.31` | 공개/중요 파일, 결과 PII, 경로 정규화, 쓰기 |
| git | `mcp-server-git==2026.8.18` | 저장소 범위, 읽기·쓰기 효과, 작업 기록 |
| fetch | `mcp-server-fetch==2026.8.18` | URL 목적지, SSRF, 외부 비신뢰 응답 |
| memory | `@modelcontextprotocol/server-memory@2026.8.31` | 지속 저장·읽기, 민감정보 잔존 |
| desktop | `@wonderwhy-er/desktop-commander@0.2.51` | 명령 실행·자원 분류·결과 크기 |
| postgres | `postgres-mcp==0.3.0` | SQL 구문 효과와 table 분류, 읽기 위장 쓰기 |
| redis | `redis-mcp-server==0.5.1` | key 분류·읽기/쓰기·TTL |
| email | `mcp-email-server==1.9.1` | 내외부 수신자·PII·비밀 전송·승인 |
| gitea | `gitea-mcp-server@1.7.0` | 공급자 PAT·repo·PR·회수 후 상태 |
| playwright | `@playwright/mcp@0.0.82` | 웹 비신뢰 콘텐츠·스크린샷·외부 통신 |

공식 reference 서버와 Inspector의 현재 저장소도 [Servers](https://github.com/modelcontextprotocol/servers), [Inspector](https://github.com/modelcontextprotocol/inspector)에서 재확인했다. reference 구현을 production 보안 보장으로 해석하지 않는다. 설치 때 버전·lock·실제 dependency hash를 별도로 고정한다.

## 공개 원격 후보 — 연결하지 않음

| 후보 | 확인 자료·endpoint | 용도와 선행 조건 |
| --- | --- | --- |
| Microsoft Learn | [공식 개발 참조](https://learn.microsoft.com/en-us/training/support/mcp-developer-reference), `https://learn.microsoft.com/api/mcp` | 공개 문서 검색, dynamic tool list·계약 변화. 문서의 endpoint를 확인했으며 이번 MCP 연결은 미실시 |
| Cloudflare docs | [공식 서버 목록](https://developers.cloudflare.com/agents/model-context-protocol/cloudflare/servers-for-cloudflare/), `https://docs.mcp.cloudflare.com/mcp` | 공개 검색·응답 검사. 현재 목록과 인증·schema를 등록 전에 다시 확인 |
| GitHub remote MCP | [공식 서버 저장소](https://github.com/github/github-mcp-server), `https://api.githubcopilot.com/mcp/` | 사용자·공급자 token 분리, 읽기/쓰기 권한. 현재 공식 설정 예시의 endpoint·OAuth/PAT 설명을 확인했으며 protocol 접속은 미실시 |
| MCP Feature Reference Server | [공식 예제](https://github.com/modelcontextprotocol/example-remote-server) | OAuth·resources·prompts·페이지네이션·세션. 격리된 자체 배포와 명시 등록을 우선; 현재 원격 endpoint 가용성 미확인 |

Cloudflare 공식 문서는 현재 `/mcp` Streamable HTTP 연결과 transport 호환성 변경을 설명한다. 과거 `/sse` 예시를 그대로 복제하지 않는다. provider 문서가 공개됐다는 사실과 이 솔루션의 현재 protocol/schema 호환성은 별도다.

## 취약 버전 메타데이터 후보 2종

[기존 FIELD 후보 문서](../../../docs/ai/FIELD_MCP_CANDIDATES.md)의 `@modelcontextprotocol/server-filesystem@0.6.2`와 `mcp-server-git==2025.11.25`는 도입·취약 버전 차단 fixture 후보로 이관했다. 2026-10-13에 [filesystem advisory](https://github.com/modelcontextprotocol/servers/security/advisories/GHSA-q66q-fx2p-7w4m)와 [git advisory](https://github.com/advisories/GHSA-j22h-9j4x-23w5)를 다시 읽었다. git 공지는 `<2025.12.18` 영향·`2025.12.18` 수정이다. filesystem 공지는 여러 버전 계열과 권고 버전 표기가 함께 있으므로 `0.6.3 이상 전부 안전`으로 단순화하지 않고 공지 원문 범위를 fixture에 보존한다. 취약 패키지는 설치·실행하지 않았다.

악성 도구 설명·지연·schema drift는 임의 공개 서버를 공격하지 않고 전용 mock MCP fixture로 만든다. 계약 변경 전에 승인한 hash와 변경 후 hash, upstream 수신 횟수·효과를 함께 남긴다.
