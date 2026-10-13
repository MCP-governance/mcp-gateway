# 현재 기능, 목표 기능과 보강 설계 — 2026-10-13

[개발 목표 10개](2026-10-13-development-goals.md)를 기존 코드와 [8개 솔루션 조사](../../solutions/README.md)에 대조했습니다. 아래의 구현 확인은 소스 확인입니다. 실제 배포·하네스 증거는 작업 결과 보고에 별도로 기록합니다. 공급자 문서나 코드의 존재로 제품 우열을 결정하지 않습니다.

## 현재 기능과 경계

| 영역 | 실제 구현 근거 | 현재 범위·남은 확인 |
| --- | --- | --- |
| MCP 도입·공급망 | `intake.py`, `intake_worker.py`, `supply_chain/`, 도입 신청·검사·승인 API | 검사 결과와 고정 소스·종속성의 연결 존재. 격리 검사 환경·실제 라이선스/취약점 데이터 최신성 확인 필요 |
| 계약·카탈로그 | `core.refresh_catalog`, `approve_contract`, `registry`, `contract` | 도구 설명·스키마·승인 계약 대조. 카탈로그 복귀와 동시 갱신의 관측값 일관성 회귀 필요 |
| 신원·권한 | `idp`, `oidc`, `agent_contract`, `pac`, OPA/Rego | transport 토큰 검증, 관리형 엔드포인트, 주체·행위·자산·인자·목적지의 정책 입력. mock 계정 경로와 외부 OIDC의 운영 배선을 구분 |
| 실행 통제 | `core.execute_call`, 호출 예약·중복·동시성·재검증 | Gateway를 통과한 실행 경로. 다중 프로세스·TTL 경계·승인 철회 경쟁과 실제 부수효과 평가 필요 |
| 데이터·주입 | `classify`, `privacy`, `secret_scan`, `poisoning` | 입력 검사와 결과 마스킹·보류. 한국어·다국어·인코딩의 오탐/미탐 측정 필요. 결과 차단을 이미 실행한 upstream의 취소로 표현하지 않음 |
| 관리형 엔드포인트 | `endpoint-agent/bootstrap.py`, `managed-linux.py`, `enforce-linux.py`, `os-observer.py` | Linux 일반 관리 계정의 고정 launcher·AppArmor·UID 방화벽. 관리자 침해·임의 Windows 앱·웹·클라우드 전부를 통제하는 기능으로 확대 해석하지 않음 |
| 감사·운영 | `audit`, 감사 API·내보내기·무결성 검사, 현황·활동 UI | 판정과 실행·응답 상태를 분리. 실행 중 프로세스 사망·시간 정보 무결성의 회귀 확인 필요 |
| 종료·회수 | `decommission`, 종료 API, C1~C4/T1~T3 모델 | 자원 서버별 폐기·재접근·증거 접근. 제공자 보유 상태는 증거 없으면 미확인 |
| 자원 상태 | 신규 `system_metrics.py`, 관리자 `/api/system/metrics`, 운영 현황 | `/proc`에서 보이는 Linux 호스트 CPU·메모리. Console→Gateway DNS·TCP 연결 시간(ms). 최초 CPU·30초 초과 간격은 미측정, 실패·30초 이상 지난 화면 값은 `—` |
| 개발 협업 | `research/collaboration-console/` | 실제 Codex 요청·Claude 공개 응답·도구 조회·작업·검사 기록. localhost 읽기 전용, 원본 대화와 실행 설정은 Git 제외 |

## 조사 솔루션에서 가져올 설계와 검증

| 조사 대상·근거 | 연결 목표 | 보강·추가 설계 | 채택 전 완료 조건 |
| --- | --- | --- | --- |
| [IBM ContextForge](../../solutions/ibm-contextforge.md), 고정 코드 | G03/G04 | 기존 PDP·사전 실행·결과 처리 경로의 플러그인 실패 계약을 명시. 모든 플러그인이 꺼져 있다는 과거 주장은 폐기 | 동일 입력, 활성 enforce 설정, 검사기 오류/시간 초과에서 차단·실제 효과 확인 |
| [IBM CPEX](../../solutions/ibm-cpex.md), 고정 코드 | G03/G06 | 현재 PostgreSQL 예약을 유지하며 계수·TTL·중복·동시 실행을 하나의 일관된 연산으로 검증 | 경계 시각·동시 호출·프로세스 사망에서 실제 효과 수와 불확실한 실행 기록 확인 |
| [Microsoft MCP Gateway](../../solutions/ms-mcp-gateway.md), 고정 코드 | G01/G03/G08 | 역할만으로 끝내지 않고 자산 소유권·조직·위임 범위의 교집합을 승인과 호출에 연결 | 타 조직·타 소유자·철회된 위임은 전달 전 차단, 정상군 유지 |
| [Wassette](../../solutions/ms-wassette.md), 고정 코드 | G01/G05 | 격리 실행이 필요한 도구를 선택 대상으로 설계. Wasm 실행 경계와 일반 원격 MCP 호출 경계를 구분 | 파일·네트워크·CPU 상한을 명시한 도구 실행 실험. 현재 Gateway를 새 실행 엔진으로 교체하지 않음 |
| [LiteLLM](../../solutions/litellm.md), 고정 코드 | G02/G03/G08 | 승인 서버 목록의 범위가 기본값·누락·캐시 때문에 확대되지 않는 처리와 회귀 | 누락/빈/다른 서버 목록, 권한 변경 후 캐시, 활성 하네스의 실제 도구 목록 확인 |
| [Kong AI Gateway](../../solutions/kong-ai-gateway.md), 공식 문서 | G02/G03/G08 | tool ACL·token audience·scope·protocol 호환성 시험을 현재 API 경계에 추가 | 다른 audience/scope, 만료/철회, 허용 도구 정상군과 지원 하네스 프로토콜 시험 |
| [BeyondTrust Pathfinder](../../solutions/beyondtrust-pathfinder.md), 공식 문서 | G02/G03/G07 | 기한 있는 사용자/사이트 승인과 운영자 철회 근거를 계약·권한 회수에 연결 | 만료·조직 이동·권한 철회 후 새/기존 세션 모두 차단 및 자원 서버 재접근 확인 |
| [Lunar MCPX/AI Gateway](../../solutions/lunar-mcpx.md), 공급자 설명 | G04/G05/G06 | Gateway 호출과 MCP 서버가 별도로 수행하는 외부 API 통신을 각각 관측·집행 | MCP 서버 egress 경로·자격·목적지·재시도·실제 외부 효과의 독립 증거 |

## 실행 순서와 설계 결정

이번 묶음은 협업 콘솔, 실제 Claude 독립 분석, 자원 상태 API/UI, field 게시 경계 검사와 재현된 결함 수정입니다. 기존 FastAPI·PostgreSQL·OPA·Registry·Endpoint 구조를 사용합니다. 지표를 위해 Docker 소켓·셸 명령·추가 수집 서비스를 노출하지 않습니다. CPU는 누적 tick 차분, 메모리는 `MemTotal-MemAvailable`, 지연은 고정 Gateway host/port의 DNS·TCP 연결 시간으로 계산합니다. health 응답에는 DB·OPA·Presidio 등의 처리 시간이 섞이므로 네트워크 지연 측정에 쓰지 않습니다. 이 값은 내부 연결 측정이며 PC↔솔루션 Tailnet 지연·패킷 손실률을 뜻하지 않습니다. 동시 조회는 5초 캐시로 합칩니다. 화면은 10초마다 갱신하고 이동 시 요청을 취소하며, 누락/타임아웃/오래된 측정은 수치를 숨깁니다. Claude의 수정 후 리뷰는 실제 계정 세션 한도로 미완료이며 다른 모델로 대체하지 않았습니다.

후속 우선순위는 ① 승인·카탈로그·예약의 경쟁 조건과 사망 복구 ② 실제 관리 하네스 정상·차단 증거 ③ 다국어/한국어 PII·주입 코퍼스 ④ OAuth 대상·권한·철회와 외부 OIDC 운영 배선 ⑤ 자원 서버별 종료 검증입니다. 각 작업은 [백로그](../backlog.md)에 재현 입력·정확한 판정·독립 효과·완료 조건을 남깁니다. 조사 제품과 같은 조건의 실행 비교가 끝나기 전에는 “기존 제품보다 우수”라는 결과를 쓰지 않습니다.
