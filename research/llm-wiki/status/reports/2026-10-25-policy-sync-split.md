# 2026-10-25 정책 동기화 모델 교체 (P0-1, D-238)

- 작업자: Claude Code (리더 세션이 시작한 하위 세션)
- 코드 기준: main `7687a9e`에서 분기한 `10/25-policy-sync-split`. main 병합·push 하지 않음.
- 시작 근거: 2026-10-25 코드 검토 결함 (a) 활성화와 heartbeat 경합, (b) `record_served`의 jsonb 순서·경합. D-198·D-212의 땜질 대체. 백로그 DEV-90.
- 해결할 문제와 완료 조건: 통제 설정만 차단·격리하고 서버 목록·안내문·활성화는 장치를 끊지 않는다. 옛 키트가 새 게이트웨이에서 끊기지 않는다.
  기존 시험 새 실패 0, pyflakes 0, 위키 재생성·검사 오류 0.

## 결과

**판정 모델.** `managed_policy`가 돌려주는 정책에 두 값을 더했다.

| 값 | 내용 | 판정에 쓰는가 |
| --- | --- | --- |
| `control_hash` | 정책 필드(게이트웨이 URL·IP·포트·Tailscale 노드·계정·UID·heartbeat 주기·플랫폼·SID·프록시 포트·환경) + 자리표시 서버 하나·안내문 없이 렌더링한 관리형 파일 전체(허용 목록 형식, 보호 설정, `permissions.deny`, `web_search`, Codex requirements·features, 헤더 도우미, 서버별 틀) | 예 |
| `servers_version` | `mcp_servers` 상태·수명주기 변경과 추가·삭제 때 오르는 전역 시퀀스 `mcp_servers_version`의 값 | 아니오(진단값) |
| `policy_hash` | sha256({`control_hash`, `configuration_hashes`}) — 렌더링 결과의 결속값. 키트가 그대로 돌려 보낸다 | 결속 검사로만 |

서버 목록과 안내문(활성화 대기 문구, `pac.harness_guidance`)은 어느 해시에도 들어가지 않고 설정 파일에만 렌더링된다.
통제 키 목록은 `endpoint_plane.managed_policy`의 주석에 열거했다.

**판정 경로.**

| 경로 | 전 | 후 |
| --- | --- | --- |
| heartbeat 격리 | 보고 해시 = 현재 해시(또는 D-198 재렌더링·D-212 기억과 일치) | `policy_installed`: 보고 해시 = sha256(현재 `control_hash`, 보고 파일 해시)이고 파일 이름 집합이 같다 |
| 호출 시 장치 검사(`managed_failure`) | 같은 비교 + 토큰 `device_policy` = 현재 전체 해시 | `policy_installed` + 토큰 `device_policy` = 현재 `control_hash` |
| 서버 차이 | D-198 재렌더링이 맞을 때만 서버별 | 장치 `managed-mcp.json`이 현재와 다르면 현재 목록에 없는 서버 「사용할 수 없는 서버」, 마지막 확인 목록(`detail.policy_servers`)에 없는 서버 「PC가 새 정책을 적용하면 사용」. 같으면 PaC에 넘긴다(기존과 같음) |
| 토큰 발급(`idp.device_token`) | 정확 일치만, `device_policy` = 전체 해시 | `policy_installed`, `device_policy` = `control_hash` |
| 활성화 | `policy_hash` = 기대값 = 현재 해시 비교-교체 | 기대값 = 장치 보고값이고 `policy_installed`, 장치 보고 파일 해시로 비교-교체. 활성화 뒤 안내문만 바뀌어 보고 해시가 계속 유효 |
| 로컬 작업 | `device_policy` = 장치 보고 해시, 정책 변경 트리거가 `policy_hash` 변경을 전이로 처리 | 생성 때 `control_hash`에 묶고(`_device_control`), 수령·검증은 `_same_control`(통제 일치 + `policy_installed`). 트리거는 `policy_hash`를 보지 않는다 |

**삭제.** `_held_policy`(D-198 재렌더링), `record_served`·`SERVED_POLICIES`·`detail.served_policies`(D-212), `managed_policy(servers=…)` 인자,
`/api/endpoint/managed-policy`의 `record_served` 호출.

**바꾼 파일.**

| 파일 | 변경 |
| --- | --- |
| `full_stack_lab/gateway/app/endpoint_plane.py` | 렌더링을 `render(servers, guidance)`로 묶고 `control_hash`·`servers_version`·결속 `policy_hash`. `installed_hash`·`legacy_hash`·`policy_installed`·`control_matches`·`held_servers`. heartbeat·활성화·`managed_failure`·`policy_accepted` 교체, 땜질 삭제 |
| `full_stack_lab/gateway/app/main.py` | `record_served` 호출 삭제 |
| `full_stack_lab/gateway/app/idp.py` | 장치 토큰 `device_policy`를 `control_hash`로 |
| `full_stack_lab/gateway/app/local_jobs.py` | `_device_control`·`_same_control`, `current_job`·`validate_job`이 통제로 비교 |
| `full_stack_lab/gateway/app/local_run_tables.sql` | `endpoint_agents` 전이 비교에서 `policy_hash` 제외 |
| `full_stack_lab/gateway/app/lifecycle_tables.sql` | `mcp_servers_version` 시퀀스와 트리거 2개 |
| `full_stack_lab/tests/managed_policy_gap_check.py` | 다시 작성(12건) |
| 시험 대역 9개 | 아래 「기대값을 바꾼 시험」 |
| `docs/ai/DECISIONS.md` | D-238 추가, D-198·D-212에 대체 표시 |
| `docs/ai/ARCHITECTURE.md`, `endpoint-agent/README.md` | 해시 설명 |

키트(`endpoint-agent/managed-*.py`·`agent.py`)는 바꾸지 않았다.

## 전환 경로(옛 키트 호환)

키트는 `policy_hash`를 해석하지 않는다. 받은 값이 이전과 다르면 정책을 다시 설치하고, heartbeat에 받은 값과 설치 파일 해시를 보낸다
(`managed-linux.py` 703~789행, `managed-windows.py` 666~724행, macOS는 Linux 루프 재사용). 그래서 **게이트웨이만 배포하면 된다.**

1. 게이트웨이 배포 직후: 장치 행의 `policy_hash`와 발급된 5분 토큰·대기 중 로컬 작업의 `device_policy`는 옛 계산식 값이다.
   `legacy_hash`(옛 계산식을 같은 렌더링에 적용)를 `policy_installed`(파일 해시가 현재와 같을 때)와 `control_matches`가 함께 받아 끊기지 않는다.
2. 각 키트의 다음 루프(대기 10초·활성 60초): 정책을 받으면 해시가 달라져 같은 파일을 다시 쓰고 새 해시로 heartbeat한다. 이후 legacy 분기는 쓰이지 않는다.
3. 옛 키트가 모두 한 번 보고한 뒤 legacy 분기를 지운다(`policy_installed` 주석의 `ponytail:` 표시).

렌더링 동일성: main `7687a9e`의 `managed_policy`와 이 브랜치를 같은 대역 입력으로 렌더링해 Linux·macOS·Windows × 대기·활성·격리 × 프록시 유무
18가지에서 파일이 같고 `legacy_hash`가 옛 `policy_hash`와 같음을 확인했다(일회성 스크립트, 기준 commit을 인자로 받아 `git show`로 옛 코드를 읽는다).
`managed_policy_gap_check.test_kit_installed_before_this_gateway_keeps_working`이 legacy 보고·토큰 통과, 새 해시 전환, 통제 변경 시 legacy도 차단을 고정한다.

전환 한계: 배포와 장치의 다음 루프 사이에 서버 승인이 끼면 legacy 해시는 현재 렌더링과 달라져 그 PC는 다음 heartbeat(최대 60초)까지
`ENDPOINT-MANAGED-001`로 막힌다(격리는 아니다. 키트는 heartbeat 전에 정책을 먼저 받으므로 heartbeat는 새 해시를 보고한다). 배포 직후 1분은 승인을 미루면 피할 수 있다.
배포 시점에 실행 중인 로컬 컨테이너는 `device_policy`가 옛 값이라도 legacy로 계속된다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | `python -m pyflakes full_stack_lab/gateway/app/*.py full_stack_lab/tests/*.py endpoint-agent/*.py` (Windows, venv 3.12, 10-25) | 0건 | 터미널 |
| 재작성 시험 | `python -B -X utf8 full_stack_lab/tests/managed_policy_gap_check.py` | 12/12 통과 | 터미널 |
| 변이 시험 | 결속 검사를 `True`로, 서버 목록을 통제 해시에 넣기 | 각각 6건 실패(검사가 결함을 잡음) | 터미널 |
| 렌더링 동일성 | main `7687a9e` 대비 18가지 렌더링 | 파일·legacy 해시 일치 | 일회성 스크립트 |
| 관련 단위 시험 | `user_command_settings_check`, `fresh_requester_check`, `local_runner_usability_check`, `dev73_rework_check`, `dest_pin_credential_redaction_check`, `command_surfaces_check`, `harness_detect_check`, `endpoint_evidence_check`, `kit_continuity_check`, `windows_config_env_check` | 통과 | 터미널 |
| 회귀 실행기 | `python -X utf8 full_stack_lab/tests/run_local_suite.py` | 통과 108·실패 6·생략 17, 작업 전과 상태가 달라진 파일 0 | 작업 전 main: 통과 108·실패 6·생략 17 |
| PostgreSQL 시험 | `dev73_rework_pg_check`, `local_jobs_pg_check`, `endpoint_evidence_pg_check`, `token_revocation_pg_check`, `restore_residual_pg_check`, `intake_identity_pg_check` | 미실행(로컬 PostgreSQL 없음, 소유자 규칙) | 대역만 새 모델에 맞춤 |
| 실제 모델·하네스 | PJ1·pj3 | 미실행 | — |
| 배포·정책 해시 | 솔루션 기기 | 미배포 | — |

작업 전 main의 실패 6건(`acceptance_tls_check`, `intake_one_click_ast_check`, `macos_kit_check`, `output_credential_span_check`, `sbom_impact_check`,
`threat_trace_mapping_check`)은 이 변경과 무관하며 그대로다.

**기대값을 바꾼 시험과 이유.**

| 시험 | 바꾼 것 | 이유 |
| --- | --- | --- |
| `managed_policy_gap_check.py` | 전체 재작성 | 과제 지시. D-212 시험(중간 정책의 새 서버가 바로 통과)은 「새 정책을 적용하면 사용」으로 바뀌었다(한계 참조) |
| `user_command_settings_check.py` | 정책 대역에 `control_hash`·`servers`·`managed-mcp.json`, 보고 해시를 결속값으로 | heartbeat가 결속으로 판정. 「옛 해시는 비준수」 기대는 그대로 |
| `fresh_requester_check.py` | 장치·정책 대역을 결속값으로, 실제 판정 함수 함께 적재 | `managed_failure`가 새 함수를 쓴다. 기대 판정 변화 없음 |
| `local_runner_usability_check.py` | `policy` 변화는 `current_job`이 거절하도록 | 작업 통제 비교가 `current_job` 안으로 이동. 「변경 시 갱신 없음」 기대는 그대로, 통제 비교 자체는 gap check가 시험 |
| `dev73_rework_check.py` | 공통 대역에 `_device_control` | `exchange`가 통제 해시를 받는 함수 |
| `command_surfaces_check.py`, `dest_pin_credential_redaction_check.py`, `harness_detect_check.py` | 적재 함수에 `installed_hash` | 함수 추출 방식의 시험이라 새 의존 함수 이름이 필요 |
| `dev73_rework_pg_check.py`, `endpoint_evidence_pg_check.py`, `local_jobs_pg_check.py` | 대역 정책·장치 해시를 결속값으로 / 통제 비교 대역 | 새 모델에 맞춤. 미실행 |

## 실패·미완료·한계

- 연속 승인 중 PC가 중간 정책을 가진 동안 그 중간 정책에서 새로 생긴 서버는 다음 확인(활성 장치 최대 60초)까지 거절된다. 내려 준 정책을 기억하지 않는 대가다. PC 전체·기존 서버는 끊기지 않는다.
- 게이트웨이 쪽 통제 변경(주소·프록시·헤더 도우미·관리형 설정 틀)은 지금처럼 장치가 새 정책을 받기 전 heartbeat가 오면 격리된다(fail-closed 유지).
- `servers_version`은 전역 등록 서버 판이고 사람별 사용 대상·소속 변경은 반영하지 않는다. 판정에 쓰지 않는다.
- 결속 해시는 비밀 없는 sha256이다. root 키트가 받은 값을 돌려 보내는 기존 신뢰 모델과 같고, 그 이상을 증명하지 않는다.
- `research/llm-wiki/experiments/risk-scenarios/stateful_endpoint_check.py`(10-14 실험 기록)는 토큰 `device_policy`를 장치 해시로 둔다. 실험 원본이라 고치지 않았다. 다시 돌리려면 `control_hash`로 바꿔야 한다.
- PostgreSQL 시험, 솔루션 기기 배포, PJ1·pj3 실측은 하지 않았다.

## 방향 제안

- `servers_version` 저장 위치: 고른 것은 전역 시퀀스 + `mcp_servers` 트리거(새 테이블 없음, 쓰기 경합 없음). 대안 ① 장치별 판(`endpoint_agents`에 확인한 목록과 번호) — 장치마다 쓰기가 생기고 판정에는 여전히 불필요. ② 사람별 판 — D-234 사용 대상·소속 변경까지 올리려면 트리거가 여러 표에 필요.
- 옛 키트 호환: 고른 것은 결속 해시(키트 무변경) + 옛 계산식 1회 수용. 대안 ① 키트가 `control_hash`를 직접 계산·보고 — 키트 배포가 필요하고, 옛 키트는 계속 전체 해시를 보고. ② HMAC 결속 — 게이트웨이 비밀 관리가 늘고 root 키트 신뢰 모델에서는 이득이 없다.
- 중간 정책 새 서버 대기를 없애려면 키트가 heartbeat에 설치한 `servers`를 같이 보내게 하고, 게이트웨이가 그 목록으로 `managed-mcp.json` 해시를 재계산해 확인하면 된다(키트 변경 필요).

## 다음 작업

DEV-90: 리더가 검토 후 main 병합 → 솔루션 기기 `field up` → PJ1에서 (1) 배포 직후 기존 장치가 끊기지 않고 한 번 재설치하는지,
(2) 연속 승인 3건 중 격리 없음, (3) 서버 철회·원격 MCP 오류 중 다른 서버 호출 Allow, (4) 대기 장치 활성화 직후 heartbeat 격리 없음, (5) 방화벽 허용 목록 변경 시 격리,
을 `endpoint_managed_events`·원장으로 확인. PostgreSQL 시험 6건 실행.

## 사용자에게 필요한 입력

없음.
