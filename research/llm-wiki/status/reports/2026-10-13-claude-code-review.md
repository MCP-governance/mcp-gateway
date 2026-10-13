# Claude 독립 코드 검토 원문 — 2026-10-13

WSL Claude CLI 실제 세션의 공개 최종 응답입니다. 주 모델은 claude-sonnet-5-5, 요청 effort xhigh. 첫 실행은 35턴 제한으로 종료되어 같은 네이티브 세션을 재개했습니다. 아래 결함·권고의 확정 여부는 Codex 재현과 수정 후 검토에서 판정하며, 원문 자체가 실기기 검증 결과를 뜻하지 않습니다. 재실행 토큰의 만료 검증 완화 등 제안은 구현 결정을 별도로 내려야 합니다.

---

# MCP 거버넌스 게이트웨이 읽기 전용 분석 최종 보고

**증거 범위**
- 아래는 전부 로컬 소스 열람(S)입니다. 솔루션 기기(100.83.175.111)와 PJ1은 접속·실행하지 않았으므로 실행 증거(R)는 0건입니다.
- 비교군 근거는 D(저장소 문서·주석이 인용한 벤더 문서/소스)와 W(위키 기록, 이번에 재열람하지 않음)로만 적습니다. 동일 입력 비교 실험은 미수행입니다.
- Codex 패치는 `system_metrics.py` 전체, `agent_service.py:703`, 테스트 파일명만 확인했습니다. diff 전체와 `field_kit_check.py` 수정분은 보지 못했습니다.

## A. 현재 기능과 경계

| 영역 | 구현(소스 근거) | 경계·한계 |
|---|---|---|
| 도입·공급망 | Trivy/Syft 보고 import와 스캔 연결 표시(`core.py:1669-1752`), Gitleaks, 치명 취약점 차단 | 스캔이 연결된 서버만 게이트됩니다. 라이선스 판정 코드는 미확인(`intake_validation_test.py` 미열람) |
| 계약 고정 | 호출 직전 같은 연결에서 해시 재대조(`core.py:1092-1110`), 재승인은 관측값만 기록(`core.py:293-367`) | 활성 도구만 대상. 미노출 도구 변경은 기록만 남깁니다(`core.py:211-214`) |
| 신원 | transport 토큰만 사용, 폐기·계정·관리형 단말을 매 호출 확인(`agent_contract.py:106-145`, `core.py:1418-1421`) | bearer 토큰이며 mTLS/DPoP 없음(`SECURITY_BOUNDARIES.md:14-17`) |
| 호출 인가 | 분류 → PAC 사실 생성(`pac.py`) → OPA, 실행 직전 PAC 재평가(`core.py:1136-1148`), 예약 기반 호출량 제한(`core.py:904-981`) | 에이전트 신원은 Gateway 브로커(`pac.py:122`). 능력은 정적 grant 또는 원격 도입 승인 범위 |
| 입력 통제 | Gitleaks, Presidio(영문 + RRN·휴대폰·email 정규식, `privacy.py:35-57`), 지시문 탐지. 검사 불능이면 차단 | w/x/외부/공급자호스팅 호출만 검사(`core.py:1466`). 한국어 이름·주소는 미탐 |
| 출력 통제 | 크기·형식·지시문·마스킹·Secret 재검사(`core.py:1166-1184`, `1575-1578`). 실행 후 보류는 `MCP-OUTPUT-001` | B3 참조 |
| 엔드포인트 | AppArmor + UID nft(`enforce-linux.py:67-140`), root 서비스의 정책 해시·nft 기준선 heartbeat(`managed-linux.py:98-122`), 커널 거부 이벤트 수집(`os-observer.py`), 타 계정은 우회 가능으로 보고(`managed-linux.py:125-141`) | 점검은 root 서비스의 자기 보고(`managed-linux.py:6-7`). Windows 키트는 미검토 |
| 감사 | 해시 체인(`core.py:1207-1360`), 본문 제외 투영·내보내기, attempted/executed/withheld 분리(`audit.py:44-47`) | B1, G1, G2 |
| 종료·폐기 | C1–C4/T1–T3 판정, 케이스 개시 즉시 차단 | 판정이 `decisions.created_at`에 의존(B1) |
| Console | 역할별 페이지, 관리형 키트, 시스템 지표(Codex 추가) | B4, B7 |

## B. 확정 코드 결함 (7건, 영향 순)

**B1. 감사 체인이 `created_at`을 덮지 않음** (신뢰도 높음)
- 위치: `contract.py:47-80`(v1~v6 지문 컬럼에 시각 없음), `core.py:1208-1244`, `init.sql:84`.
- 트리거: DB 쓰기 권한자가 `decisions.created_at`만 UPDATE합니다.
- 기대는 `verify_audit_chain`의 변조 검출입니다. 실제는 intact로 나옵니다.
- 이 값이 종료 C3(`decommission.py:546`), 호출량·연쇄 창(`core.py:872`, `937`, `956`), 감사 시간 필터(`audit.py:36`)를 정합니다. cutover 이후 실행 호출을 cutover 이전으로 옮기면 T1을 만들 수 있습니다.
- 수정: 체인 v7(v6 + `created_at`)을 만들고, 앱이 UTC ISO 시각을 INSERT에 명시해 지문에 넣습니다. v1~v6 행은 기존 규칙으로 계속 검증합니다.

**B2. 승인 재실행이 만료된 transport claims를 재사용** (높음, 소스 추적. 실행 미재현)
- 위치: `core.py:1546`(claims 저장), `1657`(재실행), `pac.py:119-121`(`now < exp`), `idp.py:187,194`(단말 토큰 5분), `core.py:39`(승인 TTL 10분), `pac15.rego:180-190`.
- 트리거: 관리형 단말에서 Approval이 나온 뒤 5분 넘게 지나 관리자가 승인합니다.
- 기대는 1회 실행입니다. 실제는 PAC-06 불충족으로 Block, 상태 `NOT_EXECUTED`이며 승인은 소진됩니다.
- 수정: 재실행 때 `approval_replay` 플래그와 원 jti를 두고 `pac.py`의 facts만 바꿉니다. 원 발급 시점 유효 + jti 미폐기 + `managed_failure` 재확인으로 판정하고, 유효 종료는 `min(승인 expires_at)`으로 제한합니다. Rego는 그대로 둡니다.
- `acceptance.py:263`의 `call()` 헬퍼가 신선한 claims를 주입하는지는 읽지 않았습니다.

**B3. 결과 주입 검사가 JSON 직렬화 본문을 대상으로 함** (높음)
- 위치: `core.py:1172,1182`, `poisoning.py:62`(`^### instruction`, re.M), `poisoning.py:70`(위조 대화록 `_Both`, `^` 앵커).
- 트리거: 결과 텍스트에 줄바꿈으로 구성된 위조 대화록이나 `### system`이 있습니다.
- `json.dumps`가 개행을 `\n` 두 글자로 바꿔 줄 단위 `^` 규칙이 불발합니다. 자기 시험(`poisoning.py:263`)은 원문 텍스트로만 통과합니다.
- 수정: `upstream.text_of(content)`(이미 `core.py:1576`에서 사용)와 structured를 따로 검사합니다. 개행 포함 회귀 시험을 추가합니다.
- 별도 확인 필요: `INVISIBLE` 클래스에 U+200C/200D/FEFF가 들어 있는 것으로 보입니다(grep 출력으로 확정 못 함). 그렇다면 BOM CSV나 ZWJ 이모지 결과가 실행 후 보류될 수 있으니 한 줄 시험으로 확인해야 합니다.

**B4. RTT 지표가 네트워크 지연이 아닌 `/api/health` 전체 지연** (Codex 구현, 높음)
- 위치: `system_metrics.py:88-94`, `main.py:217-242`.
- `/api/health`는 OPA·Jaeger·Presidio 2종·DB를 최대 2초씩 병렬 프로브합니다. 의존성 하나만 느려도 수치가 부풀거나 2초 타임아웃으로 `unavailable`이 되고, `status != "ok"`(degraded)이면 네트워크가 정상이어도 값을 버립니다.
- 측정 범위도 Docker 내부 Console→Gateway입니다. 현장 PC↔기기(Tailscale) 지연이 아닙니다.
- 수정: TCP connect 시간과 health 응답 시간을 분리해 별도 상태로 표시합니다. degraded는 RTT와 무관하게 별도 표시하고, 라벨에 "콘솔→게이트웨이(내부)"를 명시합니다.
- CPU 쪽도 폴링이 오래 끊기면 수 시간 평균이 "현재 부하"로 나옵니다. `interval_seconds` 상한을 두고 초과 시 baseline을 재설정해 unavailable로 표시해야 합니다(프런트 처리는 미확인).

**B5. refresh 회전 경쟁** (높음)
- 위치: `idp.py:115-131`. SELECT 후 `UPDATE ... SET rotated_at`에 행 수·`rotated_at IS NULL` 가드가 없습니다.
- 트리거: 같은 refresh 토큰으로 동시 요청 2건을 보냅니다.
- 기대는 1건 성공 + 재사용 시 계열 폐기입니다. 실제는 둘 다 새 토큰을 받아 재사용 탐지가 우회됩니다.
- 수정: `UPDATE ... WHERE id=%s AND rotated_at IS NULL AND revoked_at IS NULL RETURNING id`를 쓰고, 0행이면 재사용으로 처리해 `_revoke_family`를 호출합니다. `asyncio.gather` 시험을 추가합니다.

**B6. egress 허용목록: 읽기 실패와 "통제 없음"을 구분하지 않음** (중간)
- 위치: `core.py:817-820`, `opa_document` `core.py:999-1007`(오류 시 None).
- None이면 `if not entries: return True`로 통과합니다. "실패는 차단" 불변식 위반입니다.
- 호출처가 `_contract`(`core.py:666~`)로 보이나 그 본문은 읽지 않았습니다.
- 수정: None은 False(또는 예외)로 처리하고, 빈 목록이라는 명시적 설정만 True로 둡니다.

**B7. Console 엔드포인트 차단 집계가 잘리고, 수집 상태가 없음** (높음)
- 위치: `endpoint_plane.py:358-359`(전체 `LIMIT 200`), `console.js:987-990`(엔드포인트별 count를 그 200건에서 계산), `console.js:964`("엔드포인트 차단 없음").
- 200건을 넘으면 차트가 과소 집계되고, 수집기가 죽었거나 감사 로그가 다른 경로로 가도 "없음"으로 읽힙니다.
- 수정: 서버에서 엔드포인트별 SQL 집계를 하고, 수집기 마지막 성공 시각(미수신이면 `—`)을 함께 표시합니다.

### 설계 공백 (결함이 아님)
- **G1.** 쓰기 전 의도 기록이 없습니다. `upstream_attempted`는 메모리 값(`core.py:1150`)이고 `decisions`는 호출 종료 뒤 한 번만 기록됩니다(`core.py:1625`). 크래시나 기록 실패 시 `_post_cutover`(`decommission.py:541`)와 `pac.py:194`가 근거를 잃어 실행 불확실성이 사라집니다. 최소안은 예약 행에 `dispatched_at`을 찍고(`core.py:1562` 갱신 지점), 만료된 예약을 UNCONFIRMED 판정 행으로 변환하는 정리 작업을 두는 것입니다.
- **G2.** 체인 head를 외부에 앵커링하지 않고, 검증이 전 행을 메모리에 적재합니다(`core.py:1332`).
- **G3.** 한국어 PII(성명·주소·사업자번호)가 없습니다. 모델 API 경로(프록시 3128)는 Gateway DLP 밖입니다.
- **G4.** 출력 마스킹이 잎 노드마다 순차 호출이고 총 시한이 없습니다(`privacy.py:121-132`, `core.py:1575`). 측정이 필요합니다.
- **G5.** 승인 하네스 바이너리를 직원 홈에서 복사해 해시만 기록합니다(`bootstrap.py:111-118,153-187`, 서명 검증 아님을 코드가 명시).
- **G6.** `compose.field.yaml:109-110`이 필드에서도 랩 기본 Gitea 관리자 비밀번호로 폴백합니다. `:?` 필수화가 필요합니다.

### 배포 불확실성 (실행 확인 필요)
- `destroy table`(`enforce-linux.py:74`)은 nftables 버전 요구가 있을 수 있습니다(미확인).
- auditd가 있는 호스트에서 `journalctl -k`(`os-observer.py:63`)가 AppArmor 거부를 놓칠 수 있습니다.
- nft 로그는 초당 10건으로 제한되어(`enforce-linux.py:76`) 이벤트 수는 하한값입니다.
- 컨테이너 안 `/proc` 수치의 범위는 실행으로 확인해야 합니다. 리눅스 호스트면 호스트 전체, WSL이면 VM 전체일 것으로 추정합니다.

## C. 목표 10개 vs 비교군 8종

표기: [D] 저장소 문서·주석이 인용한 벤더 문서/소스, [W] 위키 기록(재열람 안 함), [U] 사용자 제공 사실. 동등·우위는 주장하지 않으며 비교 실험은 전부 미수행입니다.

| 목표 | 가장 가까운 비교군 | 보강·추가 | 독립 시험 | 범위 밖 |
|---|---|---|---|---|
| 1 도입·공급망 | BeyondTrust Pathfinder의 요청→승인→만료 흐름(`core.py:435-437` [D]), Wassette의 Wasm 격리 [W], LiteLLM `tool_catalog_guard`(`poisoning.py:7` [D]) | Syft 결과로 라이선스 허용목록을 판정해 승인 증거에 포함 | 악성·라이선스 위반 샘플 저장소 입력 | 공급자 호스팅 서버 내부 코드 감사 |
| 2 불변 계약 | Kong·LiteLLM은 접근 ACL 중심(`SECURITY_BOUNDARIES.md` §2 [D]) | 변경 diff 화면 | 설명 변경·스키마 확장·도구 추가 rug-pull별 차단과 복귀 | — |
| 3 신원·비전달 | MS MCP Gateway [W], Kong consumer [D] | 결합 토큰 유지, B2·B5 수정 | 폐기 후 잔여 수락 시간(E1) | mTLS/DPoP는 문서화만 |
| 4 호출 인가 | Kong 도구 ACL [D], LiteLLM 키별 MCP 권한 [D], Lunar/MCPX [W] | 동적 dispatch 메타 도구 승인 | 같은 허용·거부 입력 세트로 대조 | — |
| 5 입력 PII/Secret | ContextForge PII = enforce [U], CPEX 비밀 패턴(`classify.py:104-109` [D]) | 한국어 PII를 Presidio 확장으로 추가, CPEX/ContextForge 규칙 코퍼스와 대조 | 한국어 코퍼스 정탐·오탐 | 모델 API 경로 DLP |
| 6 출력 통제 | LiteLLM 가드레일, ContextForge 플러그인 [W] | B3 수정, 총 시한 | `injection_corpus_check.py`에 개행·BOM 변형 추가 | — |
| 7 엔드포인트·OS 우회 | Pathfinder(특권 접근 제품군) [W]. Wassette는 계층이 다름 | auditd 경로, 수집기 신선도, 에이전트 측 RTT | PJ1 허용·거부 쌍 + 독립 수신 측 확인 | root 침해 attestation, macOS |
| 8 감사·불확실성 분리 | ContextForge·Lunar 감사 로그 [W] | B1, G1, 서명 head 외부 보관 | DB 변조 6종(시각·삭제·삽입·절단·NULL·버전) | — |
| 9 종료·폐기 | 대응 기능 미확인 [—] | B1 선행 | `termination_flow.py` + 변조 대조 | 제공자 내부 회수 |
| 10 온보딩·Console·지표 | LiteLLM 관리 UI, MS MCP Gateway 관리 API [W] | 호출 지연은 DB에 없고 OTel span에만 있음(`core.py:1385`). 새 열 대신 Jaeger/OTel 집계를 재사용(체인 버전 변경 회피) | 4번 항목의 부하 시험 | — |

## D. 즉시 패치 배치와 검증

**권장 순서**
1. **B4** 메트릭 보정 (Codex 구현 후속)
2. **B1** 감사 체인 v7
3. **B3** 결과 검사 대상 변경
4. **B2** 승인 재실행
5. **B5, B6, B7** 소규모 수정

**필드 게시 단언** (Codex가 수정함, diff 미열람)
- 수용 기준은 정확 집합 `{(caddy, 기기 IP, 443→8080), (model-proxy, 기기 IP, 3128→3128)}`이어야 합니다.
- 그 외 서비스는 모두 127.0.0.1만 허용합니다.
- 음성 시험: model-proxy가 0.0.0.0, caddy에 추가 포트, 임의 서비스가 외부 바인딩이면 실패해야 합니다.

**로컬 정적·단위 검증** (규칙상 로컬 허용 범위)
- B4: 가짜 transport로 (a) health가 `degraded`여도 RTT 유지, (b) 응답 지연, (c) 타임아웃, (d) CPU 간격 초과 시 unavailable.
- B1: `created_at` 변조 시 verify 실패, v1~v6 기존 행 계속 통과, `termination_flow.py` 기대값 불변.
- B3: 개행 위조 대화록 차단. 정상 로그("User:" 한 줄)와 BOM/ZWJ 정상 결과는 통과하는지 확인(B3 별도 확인 사항).
- B5: 동일 refresh 토큰 동시 요청 2건 중 1건만 성공.
- B6: OPA data 조회 실패 시 차단.
- 기존 검사: `pyflakes`, `node --test`, `open_endpoints.py`, Rego `opa test`.

**기기 실행 검증** (솔루션 기기 배포 후 PJ1 하네스, 읽기·무해 범위)
- 지표: 부하를 준 전후로 `/proc/stat`·`free -b` 독립 측정값과 대조.
- 지표: 의존성 정지 대신 읽기 전용 비교로 B4 보정을 확인합니다. 공용 기기라 타인의 랩은 멈추지 않습니다.
- B2: 관리형 단말에서 Approval을 만들고 6분 뒤 다른 관리자가 승인합니다. 수정 전 Block(PAC-06)이면 재현이고, 수정 후에는 1회 실행되어야 합니다.
- OS 증거: 관리 계정에서 비허용 목적지 접속 → 독립 수신 측에는 도달하지 않고 `endpoint_os_events`에 행이 생기는지 확인합니다. `nft --version`과 `systemctl is-active auditd`도 기록합니다.

**큰 잔여 작업**
- G1 쓰기 전 의도 기록
- 서명된 head 외부 보관
- 한국어 PII
- auditd 경로와 수집기 신선도
- 에이전트 측 RTT (heartbeat 확장, 구버전 호환 필요)
- 라이선스 판정
- 비교 실험
- Windows 경로 검토
- 필드 기본 비밀번호 제거

수정은 하지 않았고, 모든 내용은 소스 열람에 근거한 판단입니다. 기기 실행 증거는 아직 없습니다.
