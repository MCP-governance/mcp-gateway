# MINT 리팩토링·최적화 제안서 — main v0.9.0 기준 (2026-10-25)

- 대상: `MCP-governance/mcp-gateway` **main `cdef0bb`**(v0.9.0 태그 `4edec39` 뒤 보고서 색인 커밋). 운영 배포 묶음 `deploy/`, 게이트웨이 `full_stack_lab/gateway/app/`, 엔드포인트 키트 `endpoint-agent/`, 시험 `full_stack_lab/tests/`, CI `.github/workflows/verify.yml`.
- 근거: 저장소에서 직접 센 값(LOC·커밋·시험·라우트), 10-25 PJ1 실사용 시험의 실측 지연([bugbash-pj1](../../status/reports/2026-10-25-bugbash-pj1.md)), 결정 D-243~D-248, 이전 제안서(10-25 오후, `프로젝트/제안서_구조_권한_격리_20261025.md`)의 결함 분류, **코드 감사**([code-audit.md](code-audit.md): 핫패스 비용 분해·중첩 연결 전수 조사·import 그래프·시험·배포·키트, 파일:행 근거), **외부 레퍼런스 조사**([references.md](references.md): 공식 페이지 110개 열람). GitHub Actions 실행 기록은 읽기만 했다.
- 성격: 분석과 제안이다. 코드 변경은 없다. 수치는 센 값(「정적 집계」)·실행 기록(「실측」)·추정(「추정」)을 구분한다. 실환경에서 재지 않은 성능 수치를 결론으로 쓰지 않는다.
- 전제: 소유자 원칙 유지 — 보안을 약화하지 않는 범위에서 편의 최대화(10-20), 타 솔루션이 받친다는 가정에서 키트 편의·자동화 극대화와 Windows 우선(10-25), 오픈소스를 통으로 쓰고 하네스는 고치지 않는다, 콘솔은 판매 가능한 제품 화면, 정상 기능 > 키트 > 원클릭 > 실사용 시험. 「메타 관점에서 다 뜯어고쳐도 좋다」는 요청에 따라 현재 설계를 전제하지 않고 다시 그렸다. 단 **깨면 안 되는 불변식**(`AGENTS.md`: 전송 계층 신원, 토큰 비전달, fail-closed, 사람의 계약 승인, append-only 원장, 콘솔은 MCP 호출 안 함)은 그대로 둔다.

## 0. 요약

1. **제품의 핵심 가치 넷은 바꾸지 않는다.** ① 하네스를 고치지 않는 관리형 설정 배포, ② 호출 전 판정, ③ 계약(도구 스키마) 고정과 사람 승인, ④ 직원별 자격 분리·append-only 원장. 바꿀 것은 이 넷을 감싼 구조·비용·시험·설치다.
2. **호출 한 건의 비용 구조가 문제의 뿌리다.** `tools/call` 한 건이 DB 풀 체크아웃 약 35회·SQL 약 49문장을 한 코루틴에서 순차로 실행하고(관리형 PC는 51회·65문장), 같은 요청에서 인증을 2번, 계약·PAC 사실을 2~3번 다시 읽고, 서명 달린 폐기 목록 파일 전체를 flock과 함께 **동기로 5회 이상** 재검증한다. `tools/list`는 도구마다 트랜잭션 1건과 `decisions` 전수 `count(*)`를 한다(정적 집계, [code-audit §A](code-audit.md)). 10-25 실측의 「거절 판정 108~164ms」와 「동시 목록 조회 교착(S4-01)」은 이 구조의 증상이다. 게이트웨이는 uvicorn 워커 1개·풀 10이다.
3. **구조 제안의 골자는 「제어 평면 / 데이터 평면 / 엔드포인트」 3분할과 「정책 스냅숏」이다.** 데이터 평면(게이트웨이)은 호출마다 서버·계약·범위·중지·동의·폐기 목록을 DB·파일에서 읽지 않고, 제어 평면이 발행한 불변 스냅숏을 메모리에서 읽는다. DB 쓰기는 예약·원장 두 곳으로 줄인다. 게이트웨이는 제어 상태를 갖지 않게 되어(업스트림 세션은 워커 소유로 남는다) 워커·복제가 가능해지고, 판정 경로의 풀 교착류가 구조적으로 줄어든다. 스냅숏에는 유효기간·버전 단조성·철회 반영 확인이 붙고 제어 평면과 끊기면 차단한다(fail-closed). `catalog.toml`은 관리형 설정 렌더링의 정본으로 그대로 둔다(불변식). MCP 2026-07-28판(세션·`initialize` 제거, 헤더 라우팅)이 같은 방향이다.
4. **판정 경로는 「단계 파이프라인」으로 다시 짠다.** `execute_call`(386줄·`await` 49회·조기 반환 15곳)에 조건문으로 쌓인 통제를 입력·출력이 정해진 단계로 나누고, 단계마다 기본 동작(차단/기록)과 실패 모드를 선언한다. 완화는 출력 정규식류 탐지기(카드번호·문서 속 예시)에 정책 ID별로 한정하고, 그 기본을 「마스킹+기록」으로 둔다(10-25 오후 제안서 P0-2를 구조로 고정). 반출 차단(MCP-DATA-EGRESS)·연쇄(P-CHAIN)·검사 불능 차단·비신뢰 지시의 쓰기 승인은 그대로다.
5. **성능은 측정부터 시작한다.** 측정 수단은 이미 있다(`decisions.timings` 단계별 시각, `GET /api/latency`, 콘솔 개요 카드). 목표치(게이트웨이 자체 지연 p95 허용 50ms·거절 30ms, 동시 목록 100건 무오류, 로컬 MCP 2회째 0.5초)를 정하고 CI 일회용 스택에 부하 시험을 넣은 뒤, ① 폐기 목록 메모리 색인 ② 목록 스냅숏 ③ 요청 컨텍스트 재사용(인증·계약·PAC 1회) ④ 독립 단계 병렬화 ⑤ 원장 락 밖 해시·아웃박스 ⑥ 로컬 MCP 세션 재사용 ⑦ 다중 워커 순서로 줄인다. 정책 엔진 인프로세스화는 Python 바인딩이 소규모라 **측정 뒤 결정**한다.
6. **시험은 자원이 아니라 연결이 문제다.** 시험 파일 189개 중 CI·`console.sh`가 이름으로 부르는 것은 45개뿐이고, 실제 PostgreSQL 시험 16개 중 15개(S4-01 회귀 포함)는 어디에도 연결돼 있지 않다. 스택 없이 도는 시험 120개를 돌리는 `run_local_suite.py`도 CI에 없다. CI 한 번은 15~18분(실측)이며 세 job이 이미지를 캐시 없이 각자 빌드한다.
7. **설치 편의의 최대 지렛대는 「빌드하지 않는 설치」와 「키트 없는 연결」이다.** 서버는 GHCR에 서명·digest 고정 이미지를 올려 `git clone`·빌드 없이 한 줄로 설치하고(CI 러너에서도 설치 118초 중 대부분이 빌드), 직원 PC는 MCP 표준 OAuth 2.1(인가 코드+PKCE, CIMD·DCR)을 IdP가 제공해 Claude Code·Codex가 **키트 없이** 로그인하게 한다. 두 하네스 모두 원격 MCP의 OAuth 로그인을 공식 지원한다(Claude Code `managedMcpServers`는 HTTPS URL만 받고 `headersHelper`를 금지, Codex `codex mcp login`은 CIMD·DCR 지원). 키트는 관찰·격리가 필요한 조직의 선택지로 남긴다. 먼저 지금 키트의 자동화·갱신 안내·배포 채널(winget·MSIX·Intune 템플릿)을 넓히고, 단일 실행 파일 전환(Go 또는 유지보수되는 OSS 패키징)은 기존 구현과 비교 검증 뒤 따로 결정한다.
8. **실행은 0~3의 4단계, 각 단계에 통과 조건을 둔다.** 0단계(1주) 측정·CI 연결·풀 중첩 금지 린트·폐기 목록 색인·목록 스냅숏, 1단계(2~3주) 패키지 경계·파이프라인·설정·마이그레이션·시험 피라미드·사전 빌드 이미지·설치 마법사, 2단계(3~4주) 평면 분리·스냅숏·다중 워커·OAuth 네이티브. Windows 키트 편의 개선은 1단계에 앞당긴다. 3단계(평가)는 측정 결과가 목표에 못 미칠 때만 데이터 평면을 Rust/Go OSS(agentgateway 계열, 외부 인가 ext_authz로 MINT 결합)로 바꾸는 선택지다. 전면 재작성은 제안하지 않는다(strangler 방식).

## 1. 현재 구조 진단 (main `cdef0bb`)

### 1.1 규모 (정적 집계)

| 항목 | 값 | 비고 |
| --- | --- | --- |
| 게이트웨이 Python(`gateway/app/*.py`) | 68파일(모듈 67) · 24,451줄 · 함수 1,118개(async 611) | 상위 5개 `core` 2,907 · `agent_service` 2,876 · `main` 1,942 · `endpoint_plane` 1,552 · `acceptance` 1,347 = 10,624줄(43%) |
| HTTP 라우트 | 187 | 게이트웨이 `main` 106, 콘솔 `agent_service` 62, `oidc` 7, `idp` 6, `connectors` 4, `integrations` 2 |
| 콘솔 정적 파일 | 5,951줄 | `console.js` 3,347(ES 모듈 1개, 빌드 도구 없음) · `i18n-en.mjs` 1,389 · 상태·차트 모듈, ECharts 내장 |
| SQL | 파일 7개 1,517줄 · 테이블 61 · 인덱스 57 · 트리거 21 · `ALTER TABLE` 182 | 기동마다 전부 재실행 |
| 정책(Rego) | 정책 1,257줄 · 시험 1,486줄(규칙 122+8) · 통제 ID 88개 | OPA 1.20.2 사이드카 HTTP |
| 시험(`full_stack_lab/tests/`) | 197파일 · 38,821줄(실행 파일 189) | `*_check.py` 130 · `*_pg_check.py` 16 · unittest 9 · `.test.mjs` 10 |
| 엔드포인트 키트(`endpoint-agent/`) | 10,379줄 | Python 7,194 · PowerShell 1,616 · Windows 시험 1,126. Linux(+macOS 래퍼)와 Windows(Python+PowerShell) **두 벌** |
| 결정 기록 | D-001~D-250(항목 235) | 10-18~25 한 주에 D-131~D-250 |
| 운영 배포(`deploy/`) | 서비스 12(기본 11+SIEM), 직접 빌드 이미지 5, 내려받기 5(모두 digest 고정), 게시 포트 2, 망 7, 볼륨 10 | 요구 자원 4 vCPU·16GB·40GB |
| 연구 위키 | `research/` 1,650파일, `analysis/` 바로 아래 77폴더 | 코드 해시가 위키 CI에 결합 |

### 1.2 변경 속도와 결함 비율

| 주 | 비병합 커밋 |
| --- | --- |
| 2026-W40(9/28~10/4) | 62 |
| 2026-W42(10/12~18) | 168 |
| 2026-W43(10/19~25) | **435** |

10-18 이후 비병합 커밋 433건의 종류는 **docs 177 · fix 127 · feat 64 · test 63**이다. 기능 1건당 수정 2건, 문서 2.8건이다. 이전 제안서(10-25 오후)가 분류한 `fix` 114건 중 약 39건은 「정상 흐름에 끼워 넣은 차단 조건」(정책 해시 6·출력 오탐 6·승인 기본값 12·키트 설치 마찰 15)에서, 17건은 CI·위키 해시 결합에서 났다. 같은 결함의 반복 정정(D-198 3회, D-189 2회, D-176 2회)은 구조 대신 조건을 더한 결과다.

### 1.3 실측된 지연 (10-25 PJ1, 게이트웨이 `decisions.timings.total`)

| 경로 | 값 | 해석 |
| --- | --- | --- |
| 동의 거절(`P-CONSENT-001`, 업스트림 호출 없음) | 108~164ms | 1~21단계+원장 기록, SQL 약 52문장+OPA 1회 경로(감사 §A-1). 문장당 약 0.8ms로는 60~120ms가 남아 OPA 입력 직렬화·분류 CPU·폐기 목록 재검증이 후보(추정) |
| 자격 미연결 차단(`MCP-CREDENTIAL-001`) | 21~26ms | 조기 종료, 약 31문장 경로. 위와의 차이가 「본 판정 경로」의 비용 |
| 로컬 MCP 허용(filesystem·memory·sequentialthinking) | 3,682~5,033ms | 호출마다 PC에서 컨테이너 1회 기동(D-203). 상태형 서버의 기록 단절(S4-09) |
| 원격 MCP 허용 | 666~23,157ms | 대부분 상위 서비스 시간(DeepWiki 19~23초, Cloudflare 12초) |
| 동시 `tools/list` 10건 | 10초 뒤 서버마다 첫 도구 누락, 콘솔·키트 API 500 | 풀 교착. D-243으로 중첩 획득은 풀렸지만 **도구마다 트랜잭션 1건·`count(*) FROM decisions`·동기 폐기 목록 검증**은 남았다(감사 §B-1) |

벽시계(`claude -p` 전체)는 11~36초였고 대부분 모델 추론이다. 직원 체감의 지배 요인은 모델과 상위 서비스지만, 게이트웨이는 「거절 0.1초·로컬 3~5초·동시성」 세 곳이 분명한 문제다. 단계별 p50/p95를 보는 `GET /api/latency`와 콘솔 개요 카드가 있으나(24시간 창, 업스트림 4단계를 뺀 값을 게이트웨이 시간으로 정의) 목표치와 부하 시험이 없다.

### 1.4 구조적 문제 — 왜 결함이 이 비율로 나는가

| # | 문제 | 증거(파일:행은 [code-audit](code-audit.md)) | 결과 |
| --- | --- | --- | --- |
| A | **한 이미지·한 패키지에 두 앱과 모든 평면.** `main.py`(게이트웨이 :8080)와 `agent_service.py`(콘솔·IdP :8000)가 같은 `app/`을 다른 진입점으로 띄우고, 콘솔은 `core` 전체를 불러 심볼 2개만 쓴다. 모듈 최상위 import에는 순환이 없지만 함수 안 지연 import 57곳으로 31개 모듈이 한 강연결 성분이다. `core`의 팬아웃은 33 | §C-1~C-3 | 변경 하나가 전 평면을 다시 빌드·재기동·재검증하게 하고, 판정 경로의 풀 고갈이 콘솔 API 500으로 번진다(S4-01) |
| B | **판정 경로가 조건문의 누적.** `execute_call` 386줄·`await` 49·조기 반환 15. 같은 요청에서 인증 2회(`RequireBearer`+`_caller`), 계약 `_contract`·PAC `pac.build`·OPA 판정을 전송 직전에 한 번 더(8문장+OPA 1회) | §A-1 1·3·16·18·25단계, §C-8 | 새 통제는 「한 줄 더」로 들어가고 기본 동작이 차단이라 정상 호출이 막힌다. 단계 간 의존이 암묵적이어서 병렬화·캐시·단위 시험이 어렵다 |
| C | **호출마다 제어 평면 상태를 읽는다.** 서버·계약·범위·사용 대상·중지·동의·보존 설정을 DB(체크아웃 35·문장 49)와 디스크(`catalog_version()` 전체 읽기+SHA-256, `residency` 팩 2회, stat 15회 이상)에서 읽고, **폐기 목록 `journal.jsonl`을 flock으로 잠근 채 레코드마다 Ed25519 검증하는 동기 호출을 5회 이상** 한다(코드 주석이 「shortcut」이라고 적음). 풀은 두 앱이 각각 10, 워커 1 | §A-1·A-5·A-7, `disposal.py:70-95` | 동시성이 풀 크기에 묶이고 이벤트 루프가 파일 I/O·서명 검증에 막힌다. `/api/overview` 한 요청이 풀 10개를 동시에 쥐고(콘솔이 30초마다 폴링), 트랜잭션 안 두 번째 연결 획득이 5곳 남아 있다(토큰 폐기는 최대 25초 폴링 동안 연결·advisory 락 점유) |
| D | **원장 쓰기가 전역 직렬화.** 모든 판정이 `audit_chain` 한 행 `FOR UPDATE` 안에서 policy_input 포함 41열을 canonical JSON으로 해시하고 INSERT하며, SIEM 트리거가 같은 트랜잭션에서 한 행을 더 쓴다(SIEM이 꺼져 있어도 쌓이고 삭제가 없다). `verify_audit_chain`은 전 행을 메모리에 올린다. `decisions` 인덱스는 4개뿐이어서 `tool_name`·`client->>'workstation'` 조건은 전수 스캔 | §A-6, §C-5 | 처리량 상한 ≈ 1/(락 점유 시간)(추정). 이력이 커질수록 호출마다 느려진다 |
| E | **시험이 CI 밖.** 실행 파일 189개 중 CI·`console.sh`가 부르는 것은 45개. PG 시험 16개 중 1개만 연결. 스택 없이 도는 120개를 돌리는 `run_local_suite.py`는 CI에 없다. 커버리지 도구·pytest·타입 검사 없음(pyflakes만). CI 한 번 15~18분(실측), 세 job이 이미지를 캐시 없이 각자 빌드, 타임아웃은 실측의 4~5배 | §D-1~D-5 | 실제 PG에서만 보이는 결함(DEV-73 교착·S4-01)이 PJ1 실사용에서 처음 드러난다 |
| F | **위키 해시가 코드 CI에 결합.** 코드를 고치면 `map_threats.py`·`build_enterprise_analysis.py --refresh-code-only` 재생성이 없으면 CI 실패 | 10-18 이후 docs 커밋 177건 | 리더 시간이 문서 CI 운영으로 간다 |
| G | **설치가 빌드다.** `install.sh`가 서버에서 이미지 5종을 빌드(Go CGO·gcc·pip·Windows embeddable Python·spaCy 모델 내려받기)한다. CI 러너 실측 118초, 고객 서버는 미측정. `preflight`가 `python3`을 검사하지 않아 없으면 6분 대기 뒤 모호한 실패. 헬스체크 없는 서비스 6개, 자원 제한·로그 회전 없음, OPA 결정 로그가 입력 포함 stdout로 전부 나감 | §E-1·E-2 | 설치 시간·실패 지점이 네트워크·빌드 도구에 좌우되고 오프라인 설치가 불가능하다. 소형 조직(4~8GB 서버)은 못 깐다 |
| H | **스키마가 기동 때 재생성.** SQL 7개를 매 기동 실행하고 CHECK 제약 15쌍을 `DROP`→`ADD`(ACCESS EXCLUSIVE+전수 검증), 인라인 CHECK는 기존 테이블에 반영되지 않아 `approval_events.outcome` 허용값 밖 INSERT가 조용히 실패했다(D-243). 마이그레이션 도구·버전 표 없음, 부트스트랩이 두 앱에 복제. `call_reservations`·`dispatch_intents`·`siem_outbox` 정리 없음 | §C-5 | 기동 시간·락, 「CHECK 함정」, 보조 표 무한 증가 |
| I | **키트가 두 벌.** Linux(`managed-linux.py` 1,256)와 Windows(`managed-windows.py` 1,053+PowerShell 1,616)가 이름만 같은 함수 12개를 따로 구현(동일 본문은 1개). macOS는 Linux 래퍼. 자동 갱신 경로 없음(재설치만), 롤백은 스테이징 없는 보상 방식, 옛 관측 전용 키트가 함께 남아 있음 | §F | 같은 결함을 두 번 고친다(10-23 키트 결함 15건). 갱신이 사람 손에 달림 |
| J | **설정 산재.** `os.getenv` 207곳·33파일·변수 130개가 임포트 시점에 평가되고 `.env.example`은 40개만 담는다. 넓은 `except` 82개, `except Exception: pass` 3곳(`catalog_watch` 전체를 삼키는 곳 포함) | §C-4·C-7 | 설정 오류가 기동 실패로만 드러나고 문서와 어긋난다 |

잘 된 것도 분명하다. 계약 해시 고정, 예약(advisory lock)으로 중복·동시 실행 통제, 해시 체인 원장, RFC 9728 챌린지, 관리형 설정 렌더링의 단일 원천(`catalog.toml`), 전송 직전 재검증(TOCTOU 방지 의도), 간편 모드 6~15초 설치(10-25 실측), 대화형 입력 0회의 서버 설치, Rego 규칙 시험 130건, 적대 회귀 42/42·정상 16/16. 제안은 이것들을 **유지한 채 감싼 구조를 바꾸는 것**이다.

### 1.5 코드 감사 요약 — 리팩토링 후보 25건 중 상위

[code-audit.md §③](code-audit.md)의 R-01~R-25에서 심각도 「상」을 옮긴다. 이 문서의 2·3절 제안은 R-번호를 인용한다.

| R | 영역 | 현상 | 제안 요지 |
| --- | --- | --- | --- |
| R-01 | 핫패스 | 호출당 체크아웃 35·문장 49, 계약·PAC·인증 2~3회 재독 | 요청 범위 `CallContext` 1회 조립, 변경 감지는 `dispatch.record`의 FOR SHARE 한 곳 |
| R-02 | 이벤트 루프 | 폐기 목록 전체 서명 검증을 호출당 5회 이상 동기로 | (mtime·크기·head 해시) 키 메모리 색인, 바뀔 때만 전체 검증, 읽기는 스레드 |
| R-03 | S4-01 뿌리 | `tools/list` 도구마다 트랜잭션, 호출마다 `count(*) FROM decisions` | (서버·도구) 상태 TTL 캐시(만료는 즉시), 봉인 판정은 기동 1회, 서버 단위 한 쿼리, 부분 인덱스 |
| R-05 | 풀 | `/api/overview`가 풀 10개를 동시에 점유, 판정과 같은 풀 | 관리 API 전용 풀 분리, 집계는 단일 CTE+5초 캐시 |
| R-15 | 구조 | `execute_call` 386줄이 병렬화·캐시·단위 시험을 막음 | 단계 함수+공유 컨텍스트, `core.py`를 `decision/` 패키지로(2.2절) |
| R-19 | 시험 | 144/189 시험·PG 15/16이 CI 밖, 커버리지 없음 | CI에 `run_local_suite` job·postgres 서비스 컨테이너 job·coverage 최초 측정 |
| R-21 | 배포 | 설치=서버 빌드, `preflight` 누락 | 서명된 사전 빌드 이미지 pull, preflight 보강(4.1절) |
| R-23 | 키트 | Linux/Windows 두 벌 구현 | 공통 코어+OS 어댑터(4.3절) |

## 2. 리팩토링 제안 — 메타 관점의 재설계

### 2.1 목표 구조: 3평면

```text
직원 PC ──(MCP Streamable HTTP + OAuth 2.1)──► [데이터 평면] mint-gateway ×N ──► 승인된 MCP 서버
                                                   │ 읽기: 정책 스냅숏(메모리, 버전 v)        (원격·로컬·솔루션 내 격리 실행)
                                                   │ 쓰기: 예약·원장(PostgreSQL append-only)
관리자·직원 브라우저 ──(HTTPS)──► [제어 평면] mint-control ── 스냅숏 발행(v+1) ──► NOTIFY/버전 폴링 ──► 게이트웨이
                                   콘솔·IdP·도입 심사·승인·엔드포인트 평면·종료 판정·LiteLLM 동기화·SIEM 아웃박스
직원 PC(선택) ◄──── [엔드포인트] mint-agent(단일 실행 파일): 관리형 설정 배포·보고·격리 실행기·트레이/TUI
```

| 평면 | 책임 | 상태 | 확장 |
| --- | --- | --- | --- |
| 데이터 평면 `mint-gateway` | MCP 입구(`/mcp/<server>/`), 단계 파이프라인, 업스트림 세션, 출력 검사·마스킹, 원장 기록 | **없음**(스냅숏은 읽기 전용 복제, 예약·원장만 DB) | 워커·복제 N개, Caddy 뒤 라운드로빈 |
| 제어 평면 `mint-control` | 지금의 `agent_service` + 레지스트리 쓰기 + 엔드포인트 평면 + 도입·승인 + 종료 판정 + 연동 + 스냅숏 발행 | DB(설정·승인·장치) | 1개 |
| 엔드포인트 `mint-agent` | 하네스 탐지·관리형 설정·CA·헤더 헬퍼·보고·로컬 실행기 | 장치 키(root/SYSTEM) | OS별 빌드, 갱신 안내 |

**정책 스냅숏.** 제어 평면이 승인·철회·범위·사용 대상·중지·동의·보존 설정·계약 잠금·**폐기 목록 색인**을 바꿀 때마다 `policy_snapshots(version, sha256, payload, published_at)`에 한 행을 쓰고 `NOTIFY`한다. 게이트웨이는 기동 때 최신 버전을 읽고 알림(또는 2초 폴링)으로 교체한다. 호출은 자기 시작 시점의 스냅숏 버전을 원장에 기록한다(지금의 `policy_version`·`control_hash` 결속과 같은 역할, D-238과 호환). 철회·중지는 「거부 쪽으로만」 즉시 반영되도록 게이트웨이가 철회 큐를 추가로 본다(fail-closed 유지). 스냅숏이 fail-closed이려면 네 조건이 더 필요하다: ① **유효기간** — 제어 평면 heartbeat 없이 정한 시간이 지나면 새 호출을 차단 ② **버전 단조성** — 낮은 버전은 거부, 호출은 적용 버전을 원장에 기록 ③ **철회 반영 확인** — 철회 큐를 적용한 뒤에만 그 버전을 「적용됨」으로 보고 ④ **만료가 있는 값**(동의·승인 기한)은 스냅숏 값이 아니라 호출 시점에 만료를 검사. `catalog.toml`·`servers.json`은 관리형 설정 렌더링의 정본으로 유지하고(`AGENTS.md` 불변식) 스냅숏은 그 파생 읽기 모델이다.

이 구조가 주는 것: ① 호출 경로의 DB 읽기·디스크 읽기·폐기 목록 재검증이 사라져 풀 교착·PoolTimeout·루프 차단 계열이 구조적으로 줄어든다(R-01·R-02·R-03·R-10) ② 게이트웨이에 제어 상태가 없어 `--workers N`·복제가 가능해진다(R-13). 업스트림 세션·백그라운드 작업은 워커 소유로 남으므로 세션 친화 라우팅(또는 세션 비재사용 모드)·작업 단일 실행(advisory lock)·전체 동시성 한도를 먼저 설계한다 ③ 제어 평면 장애(콘솔 500)가 판정을 멈추지 않는다(R-05) ④ 「무엇이 판정에 쓰였는가」가 스냅숏 버전 하나로 재현된다(정책 재생 `replay.py`가 단순해진다). MCP 2026-07-28판이 프로토콜 세션과 `initialize` 핸드셰이크를 없애고 `Mcp-Method`·`Mcp-Name` 헤더로 중간자 라우팅을 하게 한 것([references §1](references.md))과 같은 방향이다.

### 2.2 판정 경로: 단계 파이프라인 (R-15·R-01·R-12)

`execute_call`을 아래 단계로 나눈다. 각 단계는 `Stage.run(ctx) -> ctx | Rejection`이고 단계 목록은 코드 한 곳(`pipeline.py`)에 순서대로 선언한다. 지금 코드의 단계 시각 기록(`_Laps`, `decisions.timings`)은 그대로 단계 경계가 된다.

| 순서 | 단계 | 입력 → 출력 | 기본 동작 | 외부 비용(목표) | 지금(감사 §A-1) |
| --- | --- | --- | --- | --- | --- |
| 1 | `authenticate` | bearer → principal·device | 차단 | 서명 검증(메모리), 폐기 색인(스냅숏) | 2회 수행, 폐기 목록 파일 검증 2회, DB 2~6문장 |
| 2 | `resolve` | server·tool → 계약·범위·사용 대상·분류 규칙 | 차단(미등록·미승인·계약 변경) | 스냅숏 | `_contract` 4문장+파일 stat, 전송 직전 재독 |
| 3 | `classify` | 인자 → 자원·행위·등급·목적지 | 모르면 important | CPU(스레드로) | 동기 정규식 ≤20,000자×≤200개 |
| 4 | `reserve` | 주체·서버·도구·지문 → 예약 | 차단(예약 불가) | DB 1트랜잭션 | 1/5 + 자동 중지 만료 1/2 |
| 5 | `inspect_input` | 인자 → 스키마 위반·PII·지시문·자격 | **스키마·자격·검사 불능=차단**, 반출(MCP-DATA-EGRESS)·연쇄(P-CHAIN)·비신뢰 지시의 쓰기 승인은 그대로 | Presidio 1회(필요할 때만, 상한·시간 제한) | 비밀 스캔과 PII 분석이 순차 |
| 6 | `decide` | 정책 입력 → Allow/Alert/Restrict/Approval/Block | 차단(불능) | 정책 엔진 1회, 동의·중지·흐름은 스냅숏 | OPA 2~4회, 정책 입력 조립 3문장+PAC 3문장 |
| 7 | `dispatch` | 승인된 호출 → 업스트림 결과 | 미확정 보존(D-96·97) | 업스트림 1~2회, 세션 풀, 의도 기록 1트랜잭션 | 재검증 8문장+OPA 1, initialize+list+call |
| 8 | `inspect_output` | 결과 → 상한·마스킹·지시문 | **구조화 자격=보류**, 정규식 휴리스틱(카드번호·문서 속 예시, 정책 ID별 한정)=마스킹+기록 | Presidio 1~2회(잎을 합쳐) | 잎 문자열마다 순차 HTTP(k+2회), 직렬화·검증 2회 |
| 9 | `record` | 전 단계 ctx → 원장 1행 + 예약 해제 | — | DB 1~2문장, 해시는 락 밖 | 락 안 해시, 트리거 1행, 지문 3문장 |

규칙: ① 단계는 자기 입력만 읽고 `ctx`에 결과를 덧붙인다(암묵 전역·재독 금지) ② 독립 단계는 `asyncio.gather`로 묶는다(감사 §A-4의 10구간: 계약 4쿼리, 섀도·관계·흐름 조회, PAC 3쿼리, 비밀 스캔과 PII, 잎 문자열 분석, 업스트림 목록과 DB 목록) ③ 단계마다 `mode: block | record`와 `on_error: fail_closed | degrade`를 선언한다. 이 표는 운영 문서에 두고, 콘솔에는 지금처럼 설정 가능한 통제와 한국어 상태값만 보인다(제품 화면 규칙) ④ 단계별 지연 히스토그램을 OTel로 낸다 ⑤ 전송 직전 재검증(TOCTOU 방지)은 검사별로 「무엇이 어떤 락·변경 감지로 보호되는가」 대응표를 먼저 만들고, `dispatch.record`의 FOR SHARE가 동등하게 막는다고 입증된 중복만 없앤다. 관리형 상태·PAC·정책·제약 변경 검사는 입증 전까지 유지하며 적대 회귀·`dispatch_recheck_pg_check.py`가 합격선이다.

### 2.3 모듈 경계와 패키지 (R-16)

| 패키지 | 들어가는 것 | 지금 위치 |
| --- | --- | --- |
| `mint.gateway` | 파이프라인·단계·MCP 파사드·업스트림 세션·출력 검사 | `core.py` 후반, `mcp_facade.py`, `upstream.py`, `privacy.py`, `poisoning.py`, `textscan.py`, `classify.py` |
| `mint.policy` | 정책 입력 스키마, 정책 엔진 어댑터, 정책 원장, 재생 | `core._policy`, `pac.py`, `replay.py`, `opa/` |
| `mint.ledger` | 원장 append, 해시 체인, 봉인, 보존, SIEM 아웃박스 | `_record_decision`, `audit.py`, `retention.py`, `siem.py`, `disposal.py` |
| `mint.control` | 콘솔 API, 도입·승인·심사·위험 등급·사용 대상·종료 판정·운영 대응·스냅숏 발행 | `agent_service.py`, `review.py`, `intake_proposal.py`, `decommission.py`, `ops_response.py`, … |
| `mint.identity` | IdP(OAuth 2.1 인가 코드·CIMD/DCR·OIDC 연동·세션·토큰 폐기), 직원 자격 금고 | `idp.py`, `oidc.py`, `user_credentials.py` |
| `mint.endpoint` | 장치 등록·heartbeat·통제 해시·관리형 정책 렌더링·로컬 작업 | `endpoint_plane.py`, `local_jobs.py` |
| `mint.snapshot` | 스냅숏 모델·발행·구독·폐기 색인 | 신설 |
| `mint.shared` | 설정(단일 `Settings`), DB 풀(판정용·관리용 분리), 계약 해시, 시간, 로깅 | `db.py`, `contract.py`, 흩어진 `os.getenv` |

경계는 `import-linter` 계약으로 CI에서 강제한다(`gateway`는 `control`을 import 못 함, `shared`는 아무도 import 안 함). 지연 import로 닫히는 2-사이클 6쌍(`agent_contract↔oidc`, `agent_service↔idp`, `endpoint_plane↔local_jobs`, `endpoint_plane↔idp`, `incidents↔ops_response`, `registry↔upstream`)부터 끊고, 콘솔은 `contract.canonical_hash`만 가져온다.

### 2.4 데이터 계층 (R-06·R-07·R-08·R-09·R-17)

| 항목 | 지금 | 제안 |
| --- | --- | --- |
| 스키마 관리 | 기동 때 SQL 7개 실행, CHECK 15쌍 DROP/ADD, 부트스트랩 두 앱 복제 | `schema_migrations` 표+번호 SQL+작은 러너(또는 yoyo), CHECK는 `NOT VALID`→`VALIDATE` 분리, 업그레이드 때만 실행, 롤백 스크립트 동반 |
| DB 역할 | 모든 서비스가 스키마 소유자 `mcp` | 게이트웨이=append+예약만(원장 UPDATE/DELETE 권한 없음), 제어 평면=설정 쓰기, 마이그레이션=소유자(ROADMAP §6) |
| 원장 | 단일 `decisions`, 전역 행 락 안 해시·INSERT, 트리거 SIEM 큐 | 정규화로 확정한 **불변 레코드의 지문**(`canonical_hash`)만 락 밖에서 계산하고, 이전 head 결합·INSERT·head 갱신은 지금처럼 한 트랜잭션·한 락 안에서 원자적으로 한다. 검증기는 ID 순서를 따르므로 시각 순서와 무관. policy_input의 요약 해시+압축 열 분리(체인 v9)는 구판 검증·봉인(`retention`)과의 호환을 PG 시험으로 확인한 뒤. 월 파티션+BRIN(시각), 체인은 스트림별. SIEM은 **아웃박스 표**를 워커가 비우고 비활성 시 트리거를 만들지 않는다. 검증은 커서 청크 스트리밍+구간 체크포인트 |
| 인덱스·정리 | `decisions` 인덱스 4, `tool_name`·`workstation` 조건 전수 스캔, 보조 표 정리 없음 | `decisions(server_id, tool_name, created_at DESC) WHERE upstream_executed` 부분 인덱스, `client->>'workstation'` 표현식 인덱스. 정리는 아웃박스의 전달 완료 행, 그리고 **확인된 종결 상태이고 재실행 방지 기간(D-126 24시간)을 지난** 예약·의도 행만. 미확정(`pending`/`uncertain`) 의도는 시간만으로 지우지 않는다(동일 쓰기 재실행 방지 증거) |
| 풀 | 앱마다 풀 1(최대 10·대기 10초·대기열 무제한), 중첩 획득 5곳, 관리 API가 10개 동시 점유 | 연결은 **짧은 DB 작업 범위에만**(업스트림 대기·HTTP·폴링 중 점유 금지), 트랜잭션 안 `db.fetch_*`는 **예외**(AST 린트 `nested_tx`를 CI에), 같은 연결의 `gather`는 병렬이 아니므로 단일 CTE 또는 짧은 체크아웃으로, 판정 풀과 관리 풀 분리(DB 락·CPU 경쟁은 따로 측정), `max_waiting`·`statement_timeout`·`lock_timeout` 명시, 워커 수×풀 ≤ `max_connections`, 다중 워커 때 PgBouncer |
| 레지스트리 파일(`catalog.toml`·`servers.json`) | 디스크가 정본, 호출마다 stat·해시 | **정본 유지**(관리형 설정은 레지스트리에서 렌더링한다는 불변식). 호출 경로만 파일 대신 파생 스냅숏을 읽는다 |
| 폐기 목록(`journal.jsonl`) | 호출마다 전체 서명 검증(동기, flock) | 색인은 **검증된 본문에 결속**: 서명된 `head.json`이 바뀌지 않았고 본문 SHA-256이 head와 같을 때만 재사용(레코드별 Ed25519 재검증 생략), 그 밖엔 전체 재검증, 갱신은 임시 파일→rename으로 원자적, 불일치·실패는 차단(지금과 같음). 캐시 우회 변조(같은 크기·mtime 보존)를 시험에 추가(R-02) |

### 2.5 시험 체계 (R-19·R-20)

| 층 | 지금 | 제안 | 목표 시간 |
| --- | --- | --- | --- |
| 단위(스택 불필요) | 120개가 돌지만 CI 밖(`run_local_suite.py`), unittest·단독 스크립트 혼재, 커버리지 없음 | pytest로 통일(마커 `stack`·`pg`로 파일 이름 유지), CI job으로 `run_local_suite` 즉시 연결, 단계별 순수 함수 시험, `coverage.py` 핫패스 80% | PR마다 < 3분 |
| 통합(DB만) | `*_pg_check.py` 16(CI 연결 1) | postgres 서비스 컨테이너 job으로 16개 전부, 풀·락·파티션·마이그레이션 시험 포함 | < 8분 |
| 계약(정책) | Rego 규칙 130건 | 유지 + 정책 입력 스키마 골든 파일 | 수 초 |
| 인수(일회용 스택) | `console.sh test` 345초, CI 전체 15~18분, 이미지 캐시 없음 | `buildx`+gha 캐시 또는 사전 빌드 이미지 공유, 타임아웃 30분, `push`+`pull_request` 중복 트리거 정리, 필수 경로만 PR·전체는 nightly | PR ≤ 10분 |
| 부하 | 없음 | k6(또는 locust)로 `tools/list` 동시 100·`tools/call` 50rps·거절 경로, p95를 보고서에 | nightly |
| 실기기 | PJ1·pj2·pj3 수동 | 지금처럼, 보고서 양식 유지 | — |

「검사 도구가 죽으면 실패」 규칙과 종료 코드 판정은 유지한다.

### 2.6 콘솔 (R-25)

`console.js` 3,347줄은 ES 모듈 1개에 함수 84개·화면 12개·모듈 최상위 상태 변수로 구성되고, 공통 `api()` 58회 외 직접 `fetch` 6곳, 토큰은 `localStorage`, 영어 번역은 렌더 뒤 DOM 전체를 정규식으로 치환한다. 제안: ① 화면별 ES 모듈 분할(빌드 도구 없이 `<script type="module">`)과 상태 모듈 1개, ② `api()` 단일화, ③ 토큰은 메모리+HttpOnly 쿠키, ④ 번역은 키 기반, ⑤ 30초 폴링의 `overview`는 서버 캐시(R-05). CSP same-origin·인라인 금지·`html\`\`` 이스케이프·화면 문구 규칙(`console_copy_check.py`)은 그대로. 콘솔 재작성은 우선순위가 낮다.

### 2.7 개발 흐름 (R-18·F)

| 항목 | 지금 | 제안 |
| --- | --- | --- |
| 위키 CI 결합 | 코드 변경 → 분석 해시 재생성 필수 | 코드 PR의 CI는 제품 검사만. 위키 해시 재생성은 `research/`·`docs/ai` 경로 변경 때만 또는 nightly 봇 커밋 |
| 설정 | `os.getenv` 207곳/변수 130, `.env.example` 40 | `settings.py` 하나(타입·기본값·검증), `.env.example`·compose 환경 목록을 거기서 생성, `mint doctor`가 같은 모델을 읽음 |
| 린트·타입 | pyflakes | ruff + mypy(핫패스 strict) + import-linter + `nested_tx` AST 린트 |
| 결정 기록 | D-번호 235건(분할 완료) | 유지. 구조 결정(D-30·D-53·D-238·이 제안)만 ADR 색인으로 따로 |
| 릴리스 | `VERSION`·태그·CHANGELOG(D-242) | 유지 + GHCR 이미지 digest·SBOM(syft)·cosign 서명을 릴리스 노트에 자동 기재 |

## 3. 성능 최적화 제안

### 3.1 먼저 정할 것 — 측정 기준(SLO)과 측정 통로

| 지표 | 정의 | 목표(제안) | 측정 위치 |
| --- | --- | --- | --- |
| 게이트웨이 자체 지연(허용) | **입구 수신 → 응답** 전체에서 업스트림 4단계를 뺀 값. 지금 `timings`는 인증 뒤에 시작해 원장 저장 전에 끝나므로(`core.py` `_Laps`) 입구 계측을 따로 더한다 | p95 ≤ 50ms | 새 입구 히스토그램 + `decisions.timings` |
| 게이트웨이 자체 지연(거절) | 입구 수신 → 거절 응답 | p95 ≤ 30ms(지금은 표본 범위 108~164ms뿐, 분위수 아님) | 같음 |
| 목록 조회 | `tools/list` 동시 100건(서버 10×PC 10) | 오류 0, p95 ≤ 200ms | 부하 시험 |
| 로컬 MCP | 승인 서버 반복 호출 | 2회째부터 p95 ≤ 500ms(지금 3.4~5.0초) | PJ1 실측 |
| 풀 | 대기 시간·PoolTimeout | p99 < 50ms, 0건 | `pool.get_stats()` 지표 |
| 호출당 비용 | 체크아웃·문장·외부 HTTP·동기 파일 검증 | 체크아웃 ≤ 12, 문장 ≤ 20, OPA 1, 폐기 검증 ≤ 1 | 정적 집계+쿼리 로그 |
| 자원 | 게이트웨이+제어+DB+정책 | 유휴 ≤ 1.5GB, 설치 요구 ≤ 8GB(`small`) | compose stats |

바로 재볼 수 있는 질의([code-audit 부록](code-audit.md))가 있다: 24시간 단계별 p50/p95(`percentile_cont` over `jsonb_each_text(d.timings)`), `EXPLAIN (ANALYZE, BUFFERS) SELECT count(*) FROM decisions`, 보조 표 크기, `pg_stat_activity` 상태별 연결 수. 0단계의 첫 보고서는 이 네 결과다.

### 3.2 최적화 항목 (효과가 큰 순, R-번호는 감사 후보)

| # | 항목 | 지금 | 제안 | 기대 효과 | 위험·조건 |
| --- | --- | --- | --- | --- | --- |
| P1 | **폐기 목록 메모리 색인**(R-02) | 호출당 flock+전체 Ed25519 검증 5회 이상, 동기 | 서명된 `head.json`이 그대로이고 본문 SHA-256이 head와 같으면 검증된 색인을 재사용(레코드별 서명 재검증만 생략), 바뀌면 전체 재검증, 읽기는 `to_thread`. 2단계에서 스냅숏으로 흡수 | 호출당 동기 Ed25519 검증 5회 → 0회(본문 해시 1회는 남음). 거절 경로 지연의 큰 몫(추정) | 변조 탐지 — head 서명·본문 해시 대조와 기동 시 전체 검증 유지, 캐시 우회 변조 시험 |
| P2 | **목록 조회 스냅숏**(R-03) | 도구마다 트랜잭션·advisory·`count(*)` | 서버 단위 한 쿼리 또는 스냅숏 필드. (서버·도구) 상태 캐시는 **절대 만료 시각과 심사·봉인 버전에 결속**(만료 시각이 지나면 즉시 만료, 심사·봉인이 바뀌면 무효). 봉인 유무 판정은 봉인 버전 변경 때만 | S4-01 계열 재발 불가, `5N+6`문장 → 6문장 | 봉인·심사 변경을 버전으로 놓치지 않게 — 이용 기한 시험(`tool_sunset_*`) 합격선 |
| P3 | **요청 컨텍스트 재사용**(R-01) | 인증 2회, 계약·PAC·관리형 정책 2~3회, 전송 직전 8문장+OPA 1회 재검증 | `CallContext` 1회 조립. 전송 직전 재검증은 검사별 보호 대응표에서 `dispatch.record` FOR SHARE와 동등함이 입증된 것만 제거 | 문장 49→약 20~30, 체크아웃 35→약 12~18(추정, 입증 범위에 따라) | TOCTOU 방지 의도 유지 — 적대 회귀·`dispatch_recheck_pg_check` 합격선 |
| P4 | **독립 단계 병렬화**(§A-4) | 계약 4쿼리·정책 입력 5조회·PAC 3조회·비밀/PII·잎 분석·업스트림 목록/DB 목록이 순차 | `gather`(서로 다른 연결·HTTP) 또는 단일 CTE(같은 DB) | 허용 경로 수십 ms(추정, Presidio·OPA 왕복 1회분) | 실패 처리 순서 명시, 같은 연결의 `gather`는 병렬이 아님 |
| P5 | **정책 스냅숏**(2.1, R-10) | 호출마다 DB·파일에서 제어 평면 상태 읽기, `catalog_version()` 전체 해시, stat 15회 | 메모리 스냅숏+버전 | 호출당 DB 읽기 0, syscall 약 60 → 약 5 | 전파 지연(≤2초), 철회는 즉시 큐 |
| P6 | **원장 락 밖 지문·아웃박스·인덱스**(R-07·R-08·R-09) | 전역 행 락 안 해시·INSERT·트리거 | 불변 레코드 지문만 락 밖, head 결합·INSERT·head 갱신은 원자적 유지, 아웃박스 워커, 파티션·BRIN, 부분 인덱스, 종결 행만 정리 | 처리량 상한↑(추정), O(이력) 스캔 제거, 메모리 O(1) 검증 | 해시 뒤 가변 값 변경 금지, v9·분할 체인·봉인 호환을 PG 시험으로 먼저(미확인) |
| P7 | **로컬 MCP 세션 재사용**(S4-09) | 호출마다 컨테이너 기동 3.4~5.0초, 상태형 서버 단절 | (장치·서버) 단위 컨테이너 유휴 N분 유지, stdio 세션 재사용, 철회·종료 때 즉시 폐기 | 2회째부터 수백 ms, sequentialthinking 정상화 | 격리 경계(동일 UID·네트워크 none) 재검토 |
| P8 | **관리 API 풀 분리·개요 캐시**(R-05·R-14) | `/api/overview` 10연결 동시, `/api/health`가 호출마다 번들 150KB 해시·OPA 정책 전체 조회 | 판정 풀/관리 풀 분리, 단일 CTE+5초 캐시, health 결과 캐시·클라이언트 재사용 | 관리 화면이 판정을 굶기지 못함 | DB 연결 총량 증가 |
| P9 | **Presidio 비용 통제**(R-04) | 잎 문자열마다 순차 HTTP, 요청마다 인식기 4.7KB 재전송, 동시 2 | 잎을 구분자로 합쳐 1회 분석(기존 `joined` 방식), 인식기 사전 등록, 내용 해시 캐시, 소형 조직용 라이브러리 인프로세스 옵션, 한국어 인식기 성능 측정 | HTTP k+2 → 2~3회, 메모리↓ | 구분자 경계 오탐 — `korean_pii_eval`·`inspection_corpus_eval`로 동등성 |
| P10 | **정책 엔진 호출 축소·인프로세스 검토** | OPA HTTP 2~4회/호출(판정 2+문서 조회), 「OPA 불능 → 전부 차단」 | 1단계: 판정 1회로 통합, 연결 재사용, 결정 로그 끄기. 2단계: 같은 Rego를 Wasm 또는 Regorus로 인프로세스 — **측정 뒤 결정** | HTTP 왕복·직렬화 제거(OPA 엔진 자체 평가는 수십 µs 수준: 공식 문서 샘플 45µs/중앙값 36µs/p99 134µs) | Python Wasm 바인딩(별 13)·Regorus(패키지 미배포, OPA v1.2 호환)는 지원 부담 — 사이드카 유지가 기본 |
| P11 | **다중 워커**(R-13) | uvicorn 워커 1, 프로세스 로컬 상태 약 25개 | 제어 상태 제거 뒤 `--workers N`(또는 granian). 먼저 업스트림 세션 소유권·세션 친화 라우팅(또는 비재사용 모드)·백그라운드 작업 단일 실행·전체 동시성 한도·복제 간 철회 처리를 설계하고, 로그인 제한·브라우저 페이지 상태는 공유 저장소로 | 코어 수에 비례(추정, MINT 실측 없음) | 전역 `asyncio.Lock`·캐시 제거 선행. 긴 I/O가 지배하면 서버 교체 효과는 작다(Granian 자체 벤치: 100ms I/O에서 모두 약 5,000rps 수렴) |
| P12 | CPU·직렬화(R-12) | 출력 직렬화·`check_schema`·독성 검사 2회, 검증기 매 호출 생성 | 스키마 해시별 검증기 캐시, 직렬화 1회, 분류 정규식은 스레드 | 큰 결과에서 CPU 절반(추정) | 낮음 |
| P13 | CI 캐시(R-20) | 세 job이 이미지를 각자 빌드 | `buildx`+gha 캐시 또는 사전 빌드 이미지 재사용 | 15~18분 → 약 10분(추정) | 없음 |

### 3.3 하지 않을 것

- 판정·계약·승인 재확인을 생략하는 결과 캐시(D-74 유지). 읽기 도구의 계약 재확인 TTL(R-11)은 허용 범위를 결정한 뒤에만.
- 전송 뒤 자동 재시도(D-96·97 유지).
- 정확도를 희생하는 검사 생략 — 검사는 **필요한 단계에만, 상한 안에서, 병렬로**.

## 4. 설치·운영 편의성 극대화

원칙: 사람이 하는 일은 「주소 하나 정하기 → 로그인 → 승인」 셋뿐이다. 나머지는 솔루션이 채우고 검증한다(10-20 소유자 지시). 비교 사례는 [references §5](references.md)에 있다.

### 4.1 서버 설치 (R-21·R-22)

| 단계 | 지금(v0.9.0) | 제안 | 비교 사례 |
| --- | --- | --- | --- |
| 받기 | `git clone --branch v0.9.0` | `curl -fsSL https://<배포 주소>/install.sh \| sh` — 스크립트는 SHA-256·서명을 검증한 뒤 `mint` 단일 실행 파일만 받음. 오프라인은 이미지 포함 `.tar`. **서명된 수동 경로를 함께 제공** | Tailscale·K3s·Coolify·agentgateway는 한 줄 설치, 서명 검증을 문서에 보이는 곳은 Gitea(GPG, v1.27부터 Sigstore) 정도 |
| 준비 | Docker·Compose v2·`openssl`·`python3`(검사 누락)·`git` | `mint install`이 preflight(Docker·포트·디스크·메모리·시계·`MINT_NET_PREFIX` 대역 충돌)를 표로 보이고 모자란 것을 안내. `git`·`python3`·`openssl` 불필요(키 생성은 `mint`가) | — |
| 빌드 | 서버에서 이미지 5종 빌드(Go·gcc·pip·Windows Python·spaCy) | **GHCR에 digest 고정 이미지**를 릴리스마다 게시, `pull`만. SBOM(syft)·cosign 서명 동봉, 설치기가 검증 | ToolHive는 이미지 Sigstore 서명·GitHub Attestations 검증을 `warn`(기본)/`enabled`(운영) 모드로 |
| 주소 | `--bind <IPv4>` 필수 | `--bind auto`: Tailscale IP → 사설 IPv4 순으로 제안, 확인 1회 | — |
| TLS | 사설 CA(Caddy) | 기본 유지 + 선택: 조직 CA 가져오기, ACME DNS-01, Tailscale 인증서(`*.ts.net`, 공개 CT 로그에 이름이 남는 점 안내) | Caddy 내부 CA·Tailscale HTTPS 공식 문서 |
| 첫 관리자 | `initial-admin-password` 파일 | 설치 끝에 **1회용 설정 링크**를 출력 → 브라우저 마법사(비밀번호·조직 이름·새 PC 자동 활성화·직원 초대 방식). 환경변수 선생성도 지원 | Coolify는 「먼저 접속한 사람이 관리자」 선점 위험을 공식 경고하고 환경변수 선생성 제공 |
| 규모 | 12서비스·16GB, 헬스체크 5개, 자원 제한 0 | 프로필 `small`(게이트웨이·제어·DB·정책·Caddy, Presidio 인프로세스 옵션; 내부 Git·도입 워커·격리 실행기는 `mint enable <기능>`) ≤ 8GB, `full`은 지금과 같음. 전 서비스 헬스체크·`mem_limit`·`pids_limit`·로그 회전, OPA 결정 로그 끄기 | — |
| 시간 | CI 러너 118초(빌드 포함), 고객 서버 미측정 | pull만: 목표 2분 이내(이미지 크기 측정 뒤 확정) | — |

### 4.2 운영

| 일 | 제안 |
| --- | --- |
| 점검 | `mint doctor`: 서비스·포트·TLS 만료·DB 풀 통계(`get_stats`)·정책 스냅숏 버전·Presidio·디스크·시계·업스트림 연결을 한 표로, 실패 항목마다 「다음 할 일」 한 줄. 지원 번들 내보내기(비밀 가림) |
| 업그레이드 | `mint upgrade`: 백업 → 새 digest pull·서명 검증 → 마이그레이션 → 헬스체크 → 실패 시 자동 롤백. 「업그레이드 주의」는 CHANGELOG에서 자동 추출. 컨테이너 자동 갱신 도구(Watchtower)는 2025-12 보관(archived)돼 운영 비권장이므로 자체 `upgrade` 명령+선택 야간 창으로 |
| 백업 | 지금의 `backup/restore` 유지 + 보존 개수·외부 저장소(S3 호환) 옵션 |
| 알림 | 승인 대기·격리·차단 급증을 Slack/Teams/메일 웹훅으로. 콘솔 설정 한 화면 |
| 관측 | `/metrics`(Prometheus)와 OTel 동시 지원(MCP 2026-07-28판은 `_meta`의 `traceparent` 전파 규약을 문서화), 기본 대시보드 JSON 동봉, 풀·단계 지연 히스토그램 |
| 확장 | 게이트웨이 복제 수 설정(`MINT_GATEWAY_REPLICAS`), 나중에 Helm 차트 |

### 4.3 직원 PC 연결 (R-23·R-24)

| 모드 | 지금 | 제안 | 근거 |
| --- | --- | --- | --- |
| **키트 없음(신설)** | 없음(키트 필수) | IdP가 MCP 표준 OAuth 2.1(인가 코드+PKCE, **CIMD** 우선·DCR 폴백, RFC 9728·8414는 이미 있음)을 제공. 지금 IdP는 password grant·refresh 경로뿐이므로 인가 코드 흐름은 이미 쓰는 Authlib의 인가 서버 또는 선택형 Keycloak(기존 OIDC 경로)으로 구현하고, CIMD 문서 조회는 SSRF 통제(https만·사설 주소 차단·크기·시간 제한), DCR은 등록 상한·만료, 리디렉션 URI 정확 일치, 토큰 수명은 지금 10분/8시간 유지, 회전 경쟁·철회 시험을 하네스별로 둔다. 직원은 `claude mcp add --transport http <주소>` 또는 콘솔 「내 PC 연결」의 복사 버튼 한 줄, 하네스의 브라우저 로그인 1회. 조직은 Claude Code `managedMcpServers`로 서버를 제공하고 **`allowedMcpServers`에 정확한 `serverUrl` 항목**과 `allowManagedMcpServersOnly`를 함께 둔다(잠금만으로는 목록이 고정되지 않음). Codex는 `codex mcp login <서버>`. 통제 범위는 「게이트웨이 판정만」으로 표시(화면은 한국어 상태값) | Claude Code `managedMcpServers`는 HTTPS URL만 받고 `command`·`headersHelper`·`${VAR}`를 금지, 사용자별 OAuth를 권장(v2.1.259+). Codex는 「OAuth authentication, including CIMD and DCR」을 지원하고 기본 `auth = oauth`. MCP 규격은 DCR을 폐기 예정으로 두고 CIMD를 SHOULD로 |
| 간편 모드(기본) | Linux 한 줄·Windows 파일 하나, 6~15초, 자동 활성화 | **1단계(지금 키트 위에서)**: 등록은 콘솔 링크·deep link(일회용 코드), 서버의 `kit_version` 비교로 「새 키트 필요」 표시, 새 판을 따로 깔고 교체하는 갱신, Windows winget·MSIX·Intune 템플릿, macOS Homebrew cask·pkg, Linux apt/rpm 저장소, 공통 코어(`kit_core`)+OS 어댑터로 Linux/Windows 두 벌을 하나로. **단일 실행 파일 전환**(Go, 또는 PyInstaller·Nuitka 같은 유지보수되는 OSS 패키징)은 기존 구현과 크기·기동·갱신·서명 기준으로 비교 검증한 뒤 따로 결정 | 등록 토큰은 일회용·만료·자동 그룹(Tailscale 최대 90일, NetBird 기본 7일) 관행. Claude Code MDM 정책은 30분마다 변경 확인 |
| 격리 계정(고급) | AppArmor·nft·sudoers·shim, gcc 컴파일 | 유지, 같은 실행 파일의 `--isolated`. 헬퍼 사전 빌드로 gcc 제거(이전 제안 P0-3) | — |

직원이 보는 흐름: 콘솔 로그인 → 「내 PC 연결」에 **자기 OS에 맞는 명령 한 줄**과 상태(연결됨·승인 서버 N개) → 하네스에서 승인 서버가 바로 보임 → 첫 호출 때 서버 단위 동의 1회(지금과 같음) → 차단되면 메시지에 「도입 신청」 deep link로 신청 화면 자동 기입. 키트 갱신은 서버가 보고된 `kit_version`을 최신과 비교해 콘솔·트레이에 「새 키트 필요」를 표시하고, 새 판을 따로 깔고 교체하는 순서로 바꿔 재설치 중 단절을 없앤다(R-24).

### 4.4 관리자 흐름

| 일 | 제안 |
| --- | --- |
| 도입 신청 승인 | 원클릭 승인(D-184~187·D-245) 유지 + **카탈로그 프리셋**: 자주 쓰는 공식 MCP(filesystem·memory·GitHub·MS Learn·Context7 등)의 계약 해시·분류·허용 호스트·격리 기본값을 서명된 프리셋으로 배포. 「프리셋에서 도입」 한 번. 공식 MCP Registry는 비공개 서버를 받지 않으므로 사내 승인 목록은 MINT 자체 레지스트리가 맞다 |
| 정책 프리셋 | 부서·역할 템플릿(「개발팀 기본」「협력사 읽기 전용」)으로 사용 대상·범위 일괄 적용 |
| 승인 받은편지함 | 승인 대기·동의 요청·격리·만료 예정을 한 목록, 일괄 승인·만료 연장 |
| 보고 | 주간 PDF/CSV 자동 생성(호출·차단·승인·종료 판정), 메일 전송 |

### 4.5 편의와 보안의 경계

| 편의 조치 | 보안 영향 | 처리 |
| --- | --- | --- |
| 키트 없는 연결 | 엔드포인트 관찰·격리 없음 | 통제 범위를 「게이트웨이 판정만」으로 정직하게 표시(D-62 체계, 화면은 한국어 상태값), 조직 정책으로 「키트 필수」 전환 가능 |
| 자동 활성화 | 새 PC가 승인 없이 연결 | 간편 모드에만, 설정으로 끔(D-239 그대로) |
| 프리셋 도입 | 사람이 계약을 안 읽음 | 프리셋은 **서명된 계약 해시**를 담고 승인 화면이 그 해시를 보인다. 사람 승인 클릭은 유지(TOFU 금지 불변식) |
| 자동 업그레이드 | 변경이 무단 적용 | 기본 끔, 켜도 백업·롤백 자동, 서명 검증 |
| 스냅숏 전파 지연 | 철회가 늦게 반영 | 철회·중지는 즉시 큐, 전파 지연 상한을 SLO로 |

## 5. 외부 레퍼런스와 비교

상세·URL·확인일은 [references.md](references.md)에 있다(공식 페이지 110개 열람, 10-23까지의 위키 조사와 중복 없이 그 이후·아키텍처·성능·설치 관점만). 이 절은 제안과 연결되는 요점만 둔다.

| 주제 | 확인한 사실(요약) | MINT 제안에 반영 |
| --- | --- | --- |
| MCP 규격 2026-07-28(Current, 그 뒤 초안 변경 없음) | 프로토콜 세션·`Mcp-Session-Id`·`initialize` 제거, 요청마다 `_meta`에 판본·능력, `server/discover` 필수, 중간자용 `Mcp-Method`·`Mcp-Name` 헤더 필수(SEP-2243), `tools/list`에 `ttlMs`·`cacheScope` 필수(SEP-2549), DCR 폐기 예정·CIMD 우선, Enterprise-Managed Authorization(ID-JAG) Stable, 토큰 패스스루 MUST NOT. 로드맵(2026-08-22)은 DPoP·토큰 교환·점진적 도구 노출을 우선순위로 | 제어 상태 없는 게이트웨이(2.1), 헤더 기반 1차 라우팅·속도 제한, 키트 없는 연결의 OAuth 설계(4.3: CIMD 우선), 공유 중간자는 `private` 결과를 캐시하지 않음(3.3), `_meta` 트레이스 전파 |
| OSS 게이트웨이 아키텍처 | 데이터 평면은 Rust(agentgateway: LF/AAIF, Apache-2.0, 단일 바이너리 `curl \| bash`, CEL 인가, 외부 인가 ext_authz gRPC/HTTP로 OPA 등에 위임·본문 포함 옵션 8KB 기본)·Go(Agent Router=구 Envoy AI Gateway, ToolHive v0.56.0 Cedar·Sigstore 검증, Docker MCP Gateway, Obot) 다수. Python은 ContextForge(v1.1.0이 Rust 런타임 연동을 제거)·Lasso. 모두 `tools/list` 결과를 호출 규칙과 같은 규칙으로 필터 | 3단계 선택지: agentgateway를 데이터 평면으로 두고 MINT를 ext_authz 인가·원장 서비스로 결합하는 PoC. 「목록 필터와 호출 거부가 같은 규칙」 유지(D-74). Python 단일 구현+필요한 부분만 네이티브는 ContextForge 사례와 같다 |
| 정책 엔진 | OPA 엔진 자체 평가 45µs(중앙값 36µs·p99 134µs, 공식 샘플), 사이드카 HTTP 왕복과의 공식 비교는 없음. OPA v1.21.3 번들 서명 검증 우회 수정, Rego v1 문법. Wasm은 Python 공식 SDK 없음(커뮤니티 별 13), Regorus는 Python 바인딩 미배포·OPA v1.2 호환. Cedar `cedarpy`는 비공식. CEL은 agentgateway·Agent Router가 채택 | P10: 호출 1회로 축소 → 측정 → 인프로세스는 그 뒤. OPA 1.20.2 → 1.21.x 업그레이드 항목 |
| Python 비동기 성능 | FastAPI 공식: `async def` 안 블로킹 호출은 루프 전체를 멈춤. psycopg_pool 기본 `max_size=None`(고정)·`max_waiting=0`(무제한)·`timeout=30`, 풀 크기는 「생각보다 작게」·`get_stats()`로 조정. Granian 자체 벤치: 10KB 응답에서 Uvicorn(httptools) 51k rps 대 Granian 126k, 100ms I/O에서는 모두 약 5k rps 수렴. free-threading은 3.14에서 「지원·선택」(PEP 779), 기본값화 기준 미정. PostgreSQL BRIN·RANGE 파티션 관행(고유키에 파티션 키 포함) | P1~P4·P8을 서버 교체(P11)보다 먼저. 풀 `max_waiting`·`statement_timeout` 명시, `get_stats` 지표(3.1). 원장 파티션 설계 제약(2.4) |
| 설치·온보딩 관행 | 한 줄 설치가 표준(Tailscale·K3s·Coolify·NetBird·agentgateway), 서명 검증을 보여 주는 곳은 Gitea. 일회용·만료 등록 키(Tailscale·NetBird). Claude Code 관리형 설정 3경로(서버·MDM 30분 폴링·파일), `managedMcpServers`는 HTTPS·OAuth만. Codex `codex mcp login` CIMD/DCR. Watchtower 보관(2025-12). Coolify 첫 관리자 선점 경고 | 4.1~4.3 전체 |
| 2026 연구·표준 | GatewayBench(arXiv 2610.23449, 10-16: 작업 524·도구 11,118·서버 251·게이트웨이 7종, 평면형 vs 계층형 — 본문 수치는 요약기 경유라 원문 재확인 필요), ShieldMCP(ACL 2026 Industry: 도구 포이즈닝 74%→9% 미만, 호출당 중앙값 120ms 미만), Governed MCP(비추론 계층 11.3µs), OWASP MCP Top 10은 베타·CC BY-NC-SA, CISA 등 5개국 공동 지침(2026-05-01)은 MCP 미언급 | 평가 축에 「도구 수가 늘어도 판정·토큰 유지」 추가(LIB-N01과 연결), 점진적 도구 노출(ROADMAP §1-14)의 외부 근거, 「규칙 계층은 µs·의미 검사는 수백 ms」 지연 구도. OWASP 인용 시 비영리 조건 표기 |

가져오지 않는 것: 클라이언트 설정을 직접 고치는 런타임(ToolHive `rm`은 회수가 아님, 10-15 재검토와 같음), 자체 TOFU 승인, 공식 레지스트리 직접 소비(비공개 서버 미지원).

## 6. 실행 로드맵

### 6.1 단계

| 단계 | 기간(안) | 내용 | 통과 조건 |
| --- | --- | --- | --- |
| **0. 측정·안전망** | 1주 | 부하 시험(k6) CI 추가, 단계별 p50/p95 보고서(3.1 질의), 풀 중첩 금지 린트(`nested_tx`) CI, `run_local_suite`·PG 시험 CI 연결(R-19), 폐기 목록 색인(P1), 목록 스냅숏(P2), 중첩 연결 5곳 수정(R-06), 관리 풀 분리(P8), CI 캐시(P13), 코드/위키 CI 분리 | p50/p95 기준선 보고서 1건, 동시 목록 100건 오류 0, PR CI ≤ 10분, CI가 부르는 시험 189/189 |
| **1. 구조 정리** | 2~3주 | 패키지 경계(2.3)+import-linter, 파이프라인(2.2)로 `execute_call` 이식(동작 동일, 인수 시험이 오라클), 요청 컨텍스트 재사용(P3)·병렬화(P4), `Settings`, 마이그레이션 도구·CHECK 분리(R-17), 원장 락 밖 지문·아웃박스·인덱스(P6), GHCR 사전 빌드 이미지·`curl \| sh`·마법사·헬스체크·자원 제한(4.1), **Windows 키트 편의**(deep link 등록·갱신 안내·winget/MSIX/Intune·공통 코어, 4.3) | 인수·적대·Rego·PG 시험 전부 통과, 설치 시간 측정치 게시, 거절 p95 ≤ 50ms, 호출당 문장 ≤ 30, pj3 Windows 등록 1파일·입력 0회 실측 |
| **2. 평면 분리·성능·연결** | 3~4주 | 스냅숏(P5, 유효기간·단조성·철회 확인 포함)·제어 평면 분리(2.1)·다중 워커(P11, 세션 소유권 설계 뒤)·Presidio 통제(P9)·로컬 MCP 세션 재사용(P7)·OAuth 2.1 네이티브+CIMD(4.3, 하네스별 수명·철회 시험)·정책 엔진 호출 1회(P10 1단계). 단일 실행 파일 키트는 비교 검증 보고서 뒤 결정 | SLO 표 전 항목 충족, 키트 없는 연결로 Claude Code·Codex 실측(토큰 수명·철회·회전 포함) |
| **3. 평가(선택)** | — | 2단계 뒤에도 SLO 미달이면 데이터 평면을 agentgateway 계열로 바꾸고 MINT를 ext_authz 인가·승인·원장 서비스로 결합하는 PoC(인자 전달 범위·fail-closed 동작은 PoC에서 확인) | PoC 비교 보고서 |

### 6.2 방법

- **strangler**: 새 파이프라인을 `MINT_PIPELINE=v2` 플래그로 켜고, 같은 입력에 옛 경로와 새 경로의 판정을 비교하는 그림자 모드(기존 `opa-candidate`·통제 효과 비교 기능 재사용)로 1주 돌린 뒤 교체.
- **오라클**: 인수 시험(`acceptance.py`)·적대 회귀·시나리오 21건·Rego 130건·PG 시험 16건을 바꾸지 않고 통과시키는 것이 리팩토링의 완료 조건이다.
- **작업 단위**: 하나의 PR은 한 패키지 경계 또는 한 단계만. 세션이 병렬이면 패키지 소유권을 나눈다(gateway/control/endpoint/deploy/tests).
- **문서**: 구조 결정은 D-번호 1건+ARCHITECTURE 갱신. 위키 해시 재생성은 nightly.

### 6.3 위험

| 위험 | 완화 |
| --- | --- |
| 재작성 범위 폭주(second-system) | 전면 재작성 금지. 단계별 플래그·그림자 모드·오라클 시험 |
| 1인 개발+에이전트 체제의 검증 통로 부족 | 0단계에서 부하·PG 시험을 CI에 넣어 사람이 없어도 실측이 남게 |
| 스냅숏 전파 지연을 틈탄 호출 | 철회·중지는 즉시 큐, 호출은 스냅숏 버전을 원장에 기록, 전파 지연 상한 SLO |
| 전송 직전 재검증을 줄이다 TOCTOU 구멍 | 변경 감지를 `dispatch.record` FOR SHARE 한 곳으로 모으고 `dispatch_recheck_pg_check`·적대 회귀를 합격선으로 |
| 정책 엔진 교체의 의미 차이 | 같은 Rego·같은 시험, 그림자 비교 1주. 인프로세스는 측정 뒤 |
| Go 키트 전환 중 두 벌 유지 | Windows부터 교체, Linux·macOS는 Python 키트 유지 기간을 정함 |
| OAuth 네이티브의 하네스별 차이 | Claude Code·Codex·Cursor·VS Code 실측 표 먼저(ROADMAP §1-10), 안 되는 하네스는 헤더 헬퍼 유지 |
| 원장 체인 순서 변경 | 검증기(`walk_chain`) 영향을 PG 시험으로 먼저 확인(미확인 항목) |

## 7. 측정·보고 지표

| 지표 | 지금 | 1단계 목표 | 2단계 목표 |
| --- | --- | --- | --- |
| 거절 경로 게이트웨이 p95 | 108~164ms(표본) | ≤ 50ms | ≤ 30ms |
| 허용 경로 게이트웨이 자체 p95 | 미집계(수단은 있음) | 측정·게시 | ≤ 50ms |
| 호출당 DB 체크아웃 / SQL 문장 | 35 / 49(정적 집계) | ≤ 20 / ≤ 25 | ≤ 12 / ≤ 20 |
| 호출당 동기 폐기 목록 검증 | 5회 이상 | ≤ 1 | 0 |
| 동시 `tools/list` 100건 오류 | 교착 발생(10건) | 0 | 0 |
| 로컬 MCP 2회째 p95 | 3.4~5.0초 | — | ≤ 0.5초 |
| 서버 설치 시간 | CI 러너 118초(빌드 포함), 고객 미측정 | 측정·게시 | ≤ 2분(pull) |
| 설치 요구 메모리 | 16GB | — | `small` ≤ 8GB |
| CI 한 번(PR) | 15~18분 | ≤ 10분 | ≤ 10분 |
| CI가 부르는 시험 파일 | 45 / 189(지원 스크립트 포함, 생략 사유 명시) | 189 / 189 | 189 / 189 |
| 핫패스 커버리지 | 미측정 | 측정 | 80% |
| 상위 5개 모듈 LOC 합 | 10,624 | — | ≤ 5,000(모듈 상한 1,000줄) |
| 트랜잭션 안 두 번째 연결 | 5곳 | 0(린트) | 0 |
| fix/feat 비율(주간) | 127/64 | — | ≤ 1 |

## 8. 위키 보강 내역 (이번 작업으로 추가)

| 파일 | 내용 |
| --- | --- |
| [analysis/refactor-proposal-1025/README.md](README.md) | 이 제안서 |
| [analysis/refactor-proposal-1025/code-audit.md](code-audit.md) | main `cdef0bb` 코드 감사: 핫패스 비용 분해(단계·DB·HTTP·락·디스크), 중첩 연결 전수 조사, import 그래프·설정·예외·함수 길이·콘솔 구조, 시험 분류·CI 실측, 배포 묶음, 키트 중복, 리팩토링 후보 25건, 재볼 질의 |
| [analysis/refactor-proposal-1025/references.md](references.md) | 외부 레퍼런스 110개 URL: MCP 2026-07-28 변경점·인가·레지스트리, OSS 게이트웨이 10종 아키텍처, 정책 엔진 5종, Python 비동기·PostgreSQL·Presidio, 설치·등록·갱신 관행 12제품, 2026 연구·표준 |
| [analysis/refactor-proposal-1025/tools/](tools/) | 감사 집계 스크립트 3개(표준 라이브러리만): `nested_tx.py`(트랜잭션 안 두 번째 풀 연결 탐지 — 0단계에서 CI 린트 후보), `ast_stats.py`(LOC·라우트·import 그래프·순환), `ast_quality.py`(`os.getenv`·예외·함수 길이·전역 상태). 실행: 저장소 루트에서 `python -I -B -X utf8 research/llm-wiki/analysis/refactor-proposal-1025/tools/<스크립트> full_stack_lab/gateway/app` |
| [status/reports/2026-10-25-refactor-proposal.md](../../status/reports/2026-10-25-refactor-proposal.md) | 작업 보고(근거·검증·한계) |
| [status/backlog.md](../../status/backlog.md) WIKI-09 | 제안서 검토·0단계 착수 여부 결정 |

갱신한 색인: [analysis/README.md](../README.md), [status/current.md](../../status/current.md), 보고서 색인(`build_report_index.py`).

## 9. 교차검토 반영 (Codex astra, 2026-10-25)

소유자 지시(10-25)대로 제안서·감사·레퍼런스를 `codex exec -m gpt-6-astra`(읽기 전용, 저장소 루트)로 교차검토했다. 원문은 [astra-review.md](astra-review.md). 15개 지적 중 전부를 반영했고, 반영 방식은 아래와 같다. astra의 채택 판단은 「계측 보완·기존 시험 CI 연결·배포 사전 점검부터 채택, 스냅숏 전면화·보안 상태 TTL·체인 개편·다중 워커·단일 실행 파일 키트는 보류」였고 이 문서의 로드맵도 그 순서다.

| # | 지적(요지) | 반영 |
| --- | --- | --- |
| 1 | 즉시 큐·2초 폴링만으로 스냅숏이 fail-closed는 아님 | 2.1에 유효기간·버전 단조성·철회 반영 확인·만료 값 호출 시점 검사 4조건 추가 |
| 2 | `dispatch.record` FOR SHARE는 전송 직전 재검증의 대체물이 아님 | 2.2 규칙 ⑤·P3: 검사별 보호 대응표를 만들고 동등 입증된 중복만 제거, 나머지 유지 |
| 3 | 「만료 즉시」와 「TTL만큼 늦음」 모순, 계약 TTL 위험 | P2: 캐시를 절대 만료 시각·심사·봉인 버전에 결속. 계약 재확인 TTL(R-11)은 3.3대로 위협 검증 전 미적용 |
| 4 | mtime·크기 캐시는 같은 크기 변조를 놓침 | P1·2.4: head 서명 불변+본문 SHA-256 일치 때만 색인 재사용, 원자적 갱신, 변조 시험 |
| 5 | 원장 위험은 시각 순서가 아니라 정규화·가변 값·v9 호환 | 2.4·P6: 불변 레코드 지문만 락 밖, head 결합·INSERT·갱신은 원자적, 호환은 PG 시험 뒤 |
| 6 | 미확정 의도를 시간으로 지우면 재실행 방지 증거 소실 | 2.4: 확인된 종결 상태+재실행 방지 기간(D-126) 지난 행만 정리 |
| 7 | OAuth 연결의 구현·보안 범위 부족, Claude 허용목록 잠금만으로 목록 고정 안 됨 | 4.3: Authlib/Keycloak 구현, CIMD SSRF 통제, DCR 상한, 리디렉션 정확 일치, 토큰 수명·회전·철회 시험, `allowedMcpServers` 정확 URL 병기 |
| 8 | DB를 레지스트리 정본으로 바꾸면 불변식 충돌 | 2.4·0절: `catalog.toml` 정본 유지, 스냅숏은 파생 읽기 모델 |
| 9 | 입력 「휴리스틱=기록」이 반출·승인·검사 불능 차단을 약화할 수 있음 | 0절·2.2: 완화는 출력 정규식류 탐지기에 정책 ID별 한정, 반출·연쇄·검사 불능·쓰기 승인은 유지 |
| 10 | 스냅숏만으로 무상태·PoolTimeout 소멸은 아님 | 0절·2.1·P11: 「제어 상태 없음」으로 고치고 세션 소유권·라우팅·작업 단일 실행·동시성 한도 설계를 선행 |
| 11 | 요청 전체에 연결 하나를 묶으면 점유 길어짐, 같은 연결 `gather`는 병렬 아님 | 2.4 풀·P4: 연결은 짧은 DB 작업 범위에만, 단일 CTE 또는 짧은 체크아웃 |
| 12 | `timings` 정의가 코드와 다름, 표본 범위를 p95 칸에 | 1.3·3.1: 입구 계측 추가, 표본 범위임을 명시, 「수십 ms」·「코어 수만큼」은 추정 표기 |
| 13 | Windows 편의를 Go 전환·평면 분리에 묶어 미룸 | 0절·4.3·6.1: Windows 키트 편의를 1단계로, 단일 실행 파일은 비교 검증 뒤 결정 |
| 14 | 콘솔에 `mode/on_error`·영어 enum 표시는 제품 화면 규칙 위반 | 2.2·4.3·4.5: 운영 문서에 두고 화면은 한국어 상태값만 |
| 15 | 단계 수·모듈 상한·시험 파일 수 표현 불일치 | 0절·6·7: 「0~3의 4단계」, 「상위 5개 합 ≤ 5,000(모듈 상한 1,000)」, 「189(지원 스크립트 포함)」 |
