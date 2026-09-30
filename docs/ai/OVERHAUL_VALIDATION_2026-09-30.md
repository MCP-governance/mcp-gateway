# Claude hardening 인계와 클린 검증 — 2026-09-30

## 사용자가 대시보드에서 못 본 이유

착수 시 솔루션 `100.83.175.111`의 소스와 실행 서비스는 `853e0a6`이었다. Claude의
`feat/2026-09-30-hardening` 변경은 WSL `/home/kali/mcp-gateway`의 미커밋 작업으로 남아 있었다.
기존 WSL 스택에는 두 checkout의 bind mount가 섞여 있었다. 로컬 변경·자체 검사·운영 배포를 구분하지
않으면 “시험은 됐는데 대시보드에는 없다”는 상황이 반복된다.

원본 작업은 patch·25개 파일의 해시 manifest로 private backup에 보존했다. 새 detached checkout
`/home/kali/mcpgw-clean-20260930`, 별도 Compose 프로젝트와 신규 DB·회사 시스템·키·장치 볼륨을 만들고
초기화 후 시험했다. 기존 field의 계정과 감사 원장은 migration으로 유지하며 배포 전에 DB·환경·runtime
registry·이미지 목록을 백업했다. SSH VM에는 공식 CLI를 설치한 새 Docker 이미지와 임시 profile을 만들었다.
이것은 VM의 OS 전체를 포맷했다는 뜻이 아니다.

## 구조에 대한 판단과 적용

Gateway·OPA·계약 고정·이용 관계·종료 판정은 유효한 기반이다. 승인은 **등록 resource·도구 계약·주체·기간**에
묶고, 집행은 해당 경로에서 검증한다. 다운로드·설치·로드·프로세스 실행·도구 호출·데이터 전송은 다른 사건이다.
Gateway 하나로 모든 Claude/Codex 확장과 셸·REST·웹·클라우드 연결을 통제했다는 주장은 하지 않는다.
전체 위협 모델은 [SECURITY_BOUNDARIES.md](SECURITY_BOUNDARIES.md), PAC 대응은 [PAC_MAPPING.md](PAC_MAPPING.md)다.

| 경계 | 이번 구현 | 남은 범위 |
| --- | --- | --- |
| 입구 신원·관리 | 서명된 transport 신원, `mcp`/`console` scope, Console 공통 인증·커넥터 관리까지 scope 검사, 자기 승인 거부 | 조직 IdP·앱/장치 증명 기반 표준 위임 |
| 의미 분류 | IPv4 우회 표기·mapped IPv6·내부 FQDN·malformed URL, PostgreSQL AST, 미검토 함수 `x` | DNS 재바인딩·view/operator/함수 부작용은 네트워크·DB 권한과 별도 검사 |
| 내용 | 계약·인자·결과 공유 규칙, Sentry `root cause` 오탐 수정 | 정규식이 모든 프롬프트 주입을 탐지한다는 보장 없음 |
| 설명 검토 | 노출된 도구의 경고만 집행, 명시적 검토를 설명·schema hash에 보존, 전체 catalog 변경은 계속 차단 | 검토한 내용 자체의 악성 여부는 별도 심사·sandbox 필요 |
| 실행 상한 | PostgreSQL 주체별 advisory lock과 도착 예약, 동시·중복·중요정보 호출량, 저장 뒤 해제 | lease 만료 뒤 원격 작업의 exactly-once 보장 없음 |
| 결과 불명 | `tools/call` 직전에 attempted, 전달 후 응답 유실은 lease 유지, 전달 전 실패는 즉시 해제 | 원격 provider의 실제 완료·취소 확인 수단은 서비스별 필요 |
| 원격 자격 | 별도 private 파일, exact HTTPS resource·등록 주체·만료·파일 권한, SSO 전달 없음 | 자동 OAuth refresh·RFC 8693·provider 폐기 증거 없음 |
| 배포 | Console `정책 → 배포 확인`, code revision/hash·OPA 로드 정책 비교 | 해당 서비스 상태의 증거이며 모든 endpoint 강제성 증명은 아님 |

## 시험 방법과 결과

최종 기능 변경 이전 클린 `reset → up --no-llm → test`는 종료 코드 0으로 완료했다. 실제 SaaS 시험에서
발견한 설명 검토·오탐을 반영한 최종 소스도 전체 검증을 수행하여 종료 코드 0을 확인했다. CI·field 배포 상태는 아래
배포 기록에 따로 남긴다. 테스트의 이력 카운터를 지우거나 상한을 늘려 통과시키지 않았다. 인수·적대적
시험은 일반 역할·정상 정책의 별도 실제 계정을 만들고 끝나면 비활성화한다.

| 검사 | 실제 확인한 결과 |
| --- | --- |
| Rego | 102/102 |
| Gateway 인수 | 21 PASS, 0 FAIL, 0 SKIP |
| 하네스 연결 | PC 4대 × Claude/Codex/Gemini/OpenCode 4종 × 실제 내부 MCP 10종 |
| scripted 업무 | 실제 MCP Inspector 호출 21개 시나리오의 기대 결정과 일치 |
| 보안 회귀 | 55 PASS, 0 FAIL — OPA·상위 서버·검사기 장애와 복구 포함 |
| 적대적 입력 | 38/38 기대 차단·정책, 정상 14/14 허용; 차단은 전달/실행 false도 대조 |
| 예약의 독립 효과 | 실제 PostgreSQL row lock을 유지하며 서로 다른 쓰기 6건 → unlock 전에 2건 차단·DB 변화 4회; 중복 2건 → 1건 차단·DB 변화 1회 |
| 재생·종료 | 합성 재생 공격 미탐/정상 차단 0, 실제 기록 재생; 종료 C1~C4와 E1/E2/E3 검사 통과 |
| 자격 파일 | resource·principal·expiry·NaN·header format·파일 권한 검사 통과 |
| 실제 설명 검토 | Notion 경고 도구: 검토 없이 409, exact hash 검토 시 READY, 검토 hash 무효화 시 `MCP-CATALOG-001`·전달 전 차단 |

### 실제 일곱 SaaS

공식 remote MCP를 두 native CLI에 설정·인증했다. 이후 live contract를 검토하고 도구 하나씩만
임시 등록해 실제 Gateway를 경유했다. 공급자 자격은 Gateway의 private volume에만 있었고 일반 client는
회사 로그인 토큰을 썼다. 모든 대표 호출은 MCP isError=false, Gateway Allow, attempted/executed=true였다.
임시 등록은 해제했고 본문 대신 결정 ID·크기·SHA-256만 보고서에 남겼다. 모델 호출은 없었다.

| 서비스 | 대표 실제 호출 | 검증의 한계 |
| --- | --- | --- |
| GitHub | `get_file_contents`, 공식 MCP 저장소 LICENSE | 일반 private repo 권한·쓰기·폐기 시험 아님 |
| Supabase | `search_docs`, 인증한 docs/read-only profile | 프로젝트 DB·RLS·SQL 쓰기 시험 아님 |
| Sentry | `find_organizations` | 오류 생성·Seer 실행·project 수정 시험 아님 |
| Notion | `notion-search`, 합성 no-match 질의 | 페이지 생성·삭제·workspace별 전 범위 시험 아님 |
| Figma | `whoami` | 디자인 파일 수정·다운로드 시험 아님 |
| Zapier | `discover_zapier_actions`, GitHub app 검색 | 메시지 발송·action 실행 시험 아님 |
| Context7 | `query-docs`, FastAPI 공식 문서 주제 | 모든 library·quota·응답 분실 시험 아님 |

GitHub의 header annotation은 SDK가 같은 session의 `tools/list`를 통해 배운 뒤 Mcp-Param header를
생성한다. 목록 조회 없이 먼저 호출한 첫 시험은 header mismatch로 실패했다. 임의 header shim이나
검증 비활성화 대신 SDK의 정상 도구 목록 흐름을 사용했다.

Notion의 미노출 후속 안내 도구 경고가 전체 정상 검색까지 차단하던 오류도 실서비스에서 재현했다.
선택한 도구의 경고는 명시적으로 검토하고 hash에 묶어 저장한다. 검토되지 않은 경고 도구를 자동 허용하지 않는다.

### SSH VM과 Gateway 밖의 경계

`100.110.81.60`의 fresh image에는 공식 Claude Code 2.1.282·Codex 0.158.0이 설치됐다. 관리 정책 전
두 CLI 모두 일곱 실제 서비스를 연결했고 Codex는 합계 143개 외부 도구를 로드했다. 정책 후 직접 MCP는
각각 0개였다. 이 결과와 host packet 관측은 다른 증거다.

host tcpdump는 unmanaged 구간 TCP 443 SYN record 94개, managed 구간 6개를 관측했다. 여러 interface의
중복 record가 포함되며 MCP 호출 횟수가 아니다. managed record에는 허용 Gateway와 다른 외부 주소가
있어 native policy만으로 전체 egress 0이라고 판정하지 않았다(`INCOMPLETE`). packet payload는 수집하지 않았다.

추가 fresh Docker internal network 시험은 동일 client가 외부 연결 가능한 대조 환경에서 7/7 destination의
실제 TLS를 연결하고, 격리 후 0/7 연결하면서 고정 Caddy relay를 통한 실제 솔루션 Gateway health는 계속
성공하는 것을 확인했다. `cap-drop ALL`·`no-new-privileges`를 사용했다. 이는 해당 container에 대한 증거다.
VM 밖 프로세스, root가 바꾼 host 설정, 다른 포트·BYOD·웹/클라우드는 이 시험의 보장 범위에 넣지 않는다.

## 실패에서 수정한 것

- 비활성 인수 계정을 종료 모집단에서 제거하지 않았다. 서버 종료 차단과 확인된 계정 차단을 구분하여 기록한다.
- 연결 실패를 전달 불명으로 기록해 재시도를 막던 오류를 `tools/call` 전달 시점으로 고쳤다.
- 빈 시험 비밀번호 환경 변수와 client import/output mount 문제를 고쳤다. 실패를 성공으로 집계하지 않았다.
- Sentry의 정상 root cause 문구 오탐, 미노출 Notion 도구 경고의 전파, 등록 시 설명 검토의 소실을 고쳤다.
- VM의 20GB 디스크에서 npm/중복 build cache가 공간을 소진했다. 이 작업의 이미지·cache를 정리했고
  재현 Dockerfile은 npm cache를 같은 layer에서 제거한다. 기존 field의 데이터·계정은 초기화하지 않았다.

## 공개 레퍼런스 정정

[IBM 보고서](BENCHMARK_IBM_CONTEXTFORGE.md)는 별도 공개 CPEX 저장소의 Rust/Python 탐지 코드와
Redis Lua 원자적 제한을 확인하여 기존 “비공개·원자성 미확인” 주장을 철회한다.
[Microsoft 보고서](BENCHMARK_MICROSOFT.md)는 Entra·관리 authorizer·라우팅과 Wasm 실행 경계를
분리한다. 특정 OSS 저장소에서 못 찾은 기능을 IBM/Microsoft 전체 제품의 부재로 일반화하지 않는다.
첨부 PAC ZIP은 설계 입력·결과 계약이 다른 자료로 검토했고, Claude가 제시한 200/100건 수치는 독립 재검증
하지 않아 확정 근거에서 제외했다. 사용자 SSO 패스스루라는 기존 비교도 정정했다.

## 배포 기록

field 배포와 SSH VM의 실제 호출·브라우저 `배포 확인` 검증은 코드 commit 이후 기록한다.
증거 요약은 [2026-09-30-overhaul.json](evidence/2026-09-30-overhaul.json)에 남기며 secret·계정 응답 본문은 포함하지 않는다.
