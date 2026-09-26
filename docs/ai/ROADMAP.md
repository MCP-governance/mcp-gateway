# 남은 일과 한계

> 우선순위 순. 끝낸 항목은 지우지 말고 `~~취소선~~ (커밋)`으로 남긴다.

## 1. 다음에 할 일

> LiteLLM MCP 게이트웨이 비교([BENCHMARK_LITELLM.md](BENCHMARK_LITELLM.md))에서 나온 후보는 3·14·15번과 아래 0번이다.

0. **`P-SCOPE-001` 차단 승격과 이용 관계별 도구 목록** — D-39는 범위 밖 자원을 경보로만 남긴다. 관계 소유 부서가
   `allowed_resources`를 인가 목록으로 검토한 뒤 관리대장에서 차단으로 올린다. 같은 입력에 `allowed_tools`를 더하면
   "협력사 A는 filesystem의 read만" 같은 관계를 정책 데이터로 쓸 수 있다(LiteLLM `mcp_tool_permissions`의 1단 축소판).
1. **엔드포인트 평면의 차단** — 지금은 섀도 MCP를 *발견*하고 증적만 강화한다(`MCP-SHADOW-*`).
   ws-nkk의 `fs-direct`가 동작하지 않는 이유는 망 분리(office↛tools)이지 에이전트의 차단이 아니다.
   실제 조직에서는 egress 허용목록·DNS가 해야 한다 → `docs/design/CONTROL_PLANES.md`.
2. **v1 잔재 테이블 정리** — `agent_sessions`, `agent_runs`, `agent_gateway_receipts`(쓰지 않음).
   `agent_tables.sql`에서 CREATE를 빼고 `v2_tables.sql`에 DROP … IF EXISTS.
3. **도입 신청 → 레지스트리 연결** — 승인된 신청은 아직 `catalog.toml`에 자동으로 들어가지 않는다(사람이
   카탈로그·compose·잠금을 편집). 승인 시 카탈로그 초안(PR)을 만드는 흐름이 필요하다.
4. **공급망 검사와 v2 서버** — `intake_worker`의 서버 검사는 `source_ref`를 git ref로 가정한다. v2의
   `source_ref`는 `패키지@버전`이다. npm/PyPI 아티팩트를 받아 SBOM을 만드는 경로가 필요하다.
5. **제공자 증명 양식** — `provider-attestation` 증거는 자유 서술이다. 대상 식별자·시점·서명 필드를 강제하면
   C4 판단을 자동화할 수 있다.
6. **E1의 자원 서버 모사 확대** — 지금은 "서명만 검증하는 자원 서버" 하나. introspection을 캐시하는 서버
   (TTL 동안 수락)를 추가하면 C3 공백의 스펙트럼을 보여 줄 수 있다.
7. **Console 부가 기능** — 활동 로그 CSV 내보내기, 케이스 판정 이력 비교, 관찰 모드 요약(`/api/monitor/summary`) 화면.
8. **CI 시간** — `verify` job이 MCP 런타임 이미지를 매번 빌드한다. GHCR 캐시(`docker/build-push-action` + cache-to)로 줄일 수 있다.
9. **사내망 TLS** — Gateway·LLM 게이트웨이는 지금 평문 HTTP(`http://gateway:8080`, `http://llm-gateway:4000`)다. 실제 사내망에 놓으려면 인증서가 필요하다.
10. **하네스의 완전한 MCP OAuth** — 지금은 `bob-sso`가 password grant로 대신 받아 온다. 인가 코드 + DCR(Dynamic Client Registration)을 하네스가 직접 하게 바꾸는 편이 MCP 인가 명세에 더 가깝다.
11. **추가 클라이언트(Antigravity·Cursor·VS Code)** — 같은 Gateway URL을 각자의 MCP 설정에 넣으면 되고 단말 에이전트는 그 파일들을 이미 인벤토리한다. GUI 앱이라 랩에서 실행·검증하지 않았고, `render.py`에 이 형식들의 관리형 설정 생성을 더할 수 있다.
12. **더 나은 도구 선택을 위한 모델 경로** — GPU 추론(Intel Arc, Vulkan 또는 IPEX 경유) 또는 LiteLLM 뒤에 클라우드 키를 붙이는 두 방향 다 검토할 것. 지금 CPU 2B 모델은 벤치 4건 중 2건만 기대한 도구를 곧바로 골랐다(나머지는 탐색 도구·별칭 도구).
13. **Gemini CLI `tools.exclude` → Policy Engine 이관** — Gemini CLI가 사용 중단을 예고했다. 대체 설정 스키마가 확정되면 `workstation/managed/render.py`의 Gemini 설정을 옮긴다.
14. **CPU 소형 모델용 도구 선택 보조** — 도구가 많은 서버(gitea 39개, desktop 19개)에서 질의와 가까운 도구만 노출.
    LiteLLM은 임베딩(`semantic_tool_filter`)을 쓰지만 의존성 없는 키워드 방식부터. 12번과 함께 벤치 4건으로 비교.
15. **도구 호출 비용 필드** — 도구별 고정 단가를 `decisions`에 남겨 차단이 아낀 비용을 정량화(LiteLLM `cost_calculator`).

## 2. 알려진 한계 (의도적으로 남김)

- 합성 로그인은 조직 SSO가 아니다. 비밀번호는 모두 `test-password`.
- Compose 내부망은 호스트 방화벽·tailnet ACL이 아니다. 여러 호스트로 나누면 `docs/design/NETWORK.md`의
  설계가 선행되어야 한다.
- LLM 모드의 업무 결과는 로컬 모델(기본 `qwen3.5:2b-q4_K_M`) 품질에 좌우된다. 정책 검증은 scripted 모드로 한다.
- 종료 판정의 C1은 제공자 고지에 의존한다. 고지가 없으면 T3이고 엔진은 T1을 주지 않는다 — 구현의
  한계가 아니라 논문이 특정한 구조적 한계다. 도입 시 종료 조건 합의가 유일한 완화.
- `server_version`은 mcp-proxy가 자기 SDK 버전을 보고한다(D-03). 패키지 버전 고정은 이미지 빌드가 보장한다.

## 3. 처리한 것 (2026-09-26)
- ~~직원 PC 하네스 네이티브 전환: 손으로 짠 `office_agent.py`·`workstation/configs/` 삭제, Claude Code·Codex·Gemini CLI·
  OpenCode를 공식 패키지 그대로 설치. IT 관리형 설정은 `registry/catalog.toml`에서 빌드 때 생성~~
- ~~서버별 MCP 엔드포인트(`/mcp/<server>/`): 하네스 관리형 설정이 서버 하나당 Gateway URL 하나를 갖고, 도구도 서버 고유
  이름 그대로 보임(집계 엔드포인트 `/mcp/`는 유지)~~
- ~~콘솔 v3: ECharts 기반 탭 레이아웃, 활동 로그의 하네스 신원 표시~~

## 4. 처리한 것 (2026-09-25)
- ~~origin/main 24시간 변경 통합(a14fe13·0c1736d·374dc0b·7a8aacb·906d227·ae7ec85·f2a5913·8b2b1b4): 권한 번들·P-AUTHZ(D-25),
  원격 MCP 종료 조건의 관리자 증거 검증(D-26), 망마다 명시 서브넷과 privacy 망 복원(D-24), 루트 `endpoint-agent/`
  패키지(D-29), 콘솔 UX·접근성과 상태 모듈 node 시험(D-28), 승인 최종 상태 UNCONFIRMED/NOT_EXECUTED(D-27),
  배포 정책 묶음 digest(D-25)~~
- ~~origin/main의 PDF 통합(cc086e5·45b9f6e) 병합: Presidio 입력 검사·출력 마스킹, MCP-DATA-EGRESS-001, P-CHAIN-001, 위험 점수, 정책 재생을 v2 구조로 이식(D-20~D-23)~~

## 4-1. PDF 통합에서 이어서 할 일
- Presidio 인식기 정확도를 실제 한국어 업무 문서로 측정(현재는 합성 식별자 정규식 + 기본 인식기 일부).
- 위험 점수를 Console 목록 정렬·경보 기준으로 쓰기(지금은 표시만, 판정 근거 아님).
- 정책 재생 결과를 Console에서 보기(지금은 `reports/policy-replay.json`).

## 5. 처리한 것 (2026-09-24)
- ~~Console 전면 재작성, 종료 판정 워크스페이스~~ (5567111)
- ~~Gateway 읽기 API 인증, Console 프록시 역할 경계~~ (5567111)
- ~~프로브 호출이 모집단을 불리는 문제~~ (5567111)
- ~~`/mcp/` 401 + RFC 9728 챌린지, 승인형 예외가 실행되지 않던 문제, acceptance v2, 보안 회귀, 검사기, CI 재작성, v1 잔재 삭제~~

## 6. 아키텍처 제안(`docs/architecture/`)에서 이어서 할 일
제안은 v1 기준 커밋(45b9f6e)의 정적 검토다. v2에 반영한 것과 남은 것:
- ~~승인 최종 상태가 미확인 실행을 REJECTED로 덮음~~ → D-27
- ~~권한 데이터와 정책 코드의 배포 식별~~ → 네 파일 묶음 digest(D-25). **남음**: digest를 감사 행·재생 결과에 기록(감사 체인 v7).
- **실행 journal**(RECEIVED → DISPATCHING → COMPLETED/OUTPUT_BLOCKED/UNKNOWN): 전송 의도를 전송 전에 영속화하고,
  프로세스가 전송 뒤 감사 저장 전에 죽은 건을 UNKNOWN으로 남긴다. 지금은 `upstream_attempted`와 감사 행이 사후에 한 번 쓰인다.
- **DB 역할 분리**: migration owner / 실행(감사 append만) / 관리 / Agent(IdP) / Worker. 지금은 모든 서비스가 `mcp`
  역할(스키마 owner)이라 append-only 트리거를 끌 수 있다(보안 회귀가 변조 탐지로 보완).
- ~~**순수 계약 모듈**: 해시·스키마 유틸을 tracing을 초기화하는 `core`에서 분리(agent_service·replay의 import 경계).~~
  → `gateway/app/contract.py`(canonical_hash·POLICY_RESULT·감사 열 집합·fingerprint). `replay`·`registry`가 `core`를 import하지 않는다.
- 제안의 A.I.G 고권한 오버레이 항목은 v2에 해당 없음(v2는 A.I.G를 Gateway 컨테이너에서 실행하지 않는다).
