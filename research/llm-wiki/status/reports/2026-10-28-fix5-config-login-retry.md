# 2026-10-28 설정 섀도 집계·모델 로그인 안내·설치 연결 복구

- 작업자: Codex, Ponytail full
- 코드 기준: `10/27-bugfix-round1`, 시작 `ca4734afc1932246d2b4b01ceb77ec9e2b6cd8aa`. 시작 시 추적 파일 변경 없음, 기존 미추적 BRIEF·시험·실행 로그는 보존했다.
- 시작 근거: `BRIEF-fix5.md`, `R5-TEST-RESULT.md` 새 결함 1~3, S4 후속, D-279.
- 완료 조건: 설정 경보의 집계/분류 경로와 판단 한계를 기록하고, 설치의 로그인 필요 관측을 상태 안내에 연결하며, 안전하게 재시도할 수 있는 일시 오류를 제한적으로 복구하고 최종 원인을 보존한다. 이번 범위는 로컬 정적·단위 검증이다.

## 결과

### 1. MCP-SHADOW-001: 코드 경로 확인, 원장 165의 설정 출처는 미확인

`core.py:2419`가 `endpoint_plane.shadow_count_for`(`endpoint_plane.py:487`)의 값을 `principal.shadow_endpoints`에 넣는다. 조건은 **같은 직원 소유** + `endpoint_agents.status='active'` + `agent_version<>'unregistered'` + `endpoint_inventory.classification='shadow'`다. 현재 호출 PC 하나나 `shadow_listeners`를 세는 것이 아니다. 다른 PC·일반 관측 에이전트·이전 활성 관측 기록도 조건에 맞으면 포함되며, 이 쿼리에는 보고 신선도 조건이 없다. 이는 현재 구현의 범위이며 이번에 변경하지 않았다.

출처 연결은 다음과 같다.

| 단계 | 코드 | 보존되는 근거 |
| --- | --- | --- |
| 수집 범위 | `managed-linux.py:999` | 등록 계정 홈과 관리형 설정 부모 경로를 `ENDPOINT_CONFIG_PATHS`에 전달 |
| 파일·항목 | `agent.py:358`, `:393`, `:463` | `candidate_files`, `all_server_entries`, `collect_configs`가 `config_path`, `server_label` 기록. Claude 프로젝트 항목에는 `이름@프로젝트경로` 사용 |
| 연결 대상 | `agent.py:438` | URL 또는 stdio 명령 해시. 환경·헤더는 제외 |
| 분류 | `endpoint_plane.py:150`, `:184`, `:299` | 공개 게이트웨이 주소와 등록 서버를 대조해 `registered`, `shadow`, `retired-residue` 저장 |
| 정책 입력 | `endpoint_plane.py:487`, `core.py:2419` | 소유 직원 전체의 섀도 설정 수 |

정상 관리형 `managed-mcp.json`·하네스 기본 `.claude.json`·프로젝트 `.mcp.json`이 승인 게이트웨이 경로를 가리키면 등록으로 대조된다. 같은 관리형 파일에 직접 stdio/외부 URL을 넣으면 파일명이나 서버 이름으로 면제되지 않는다. 합성 임시 파일과 실제 수집기/매처를 연결한 반례가 수정 전후 모두 통과했다. 수신부 분류 규칙·정책·원장은 변경하지 않았다.

**원장 165의 어느 파일·항목인지, 시험자가 남긴 실제 미등록 설정인지, 주소 구성/보고 범위 문제인지 확정할 수 없다.** 제공 기록에는 집계 수치만 있고 해당 시점의 설정 행이 없다. 현재 인벤토리는 완전 보고로 교체되는 상태이므로 현재 행 조회를 당시 원장 스냅숏으로 볼 수도 없다. 「결함 아님」이나 「오탐 수정 완료」로 분류하지 않는다.

다음 읽기 전용 쿼리는 집계와 동일한 필터로 **현재** 출처를 찾는 절차다(이번에는 실행하지 않음). `employee`는 해당 호출 직원의 사용자명으로 바인딩한다. 토큰·장치 키·설정 raw는 조회하지 않는다.

```sql
SELECT a.endpoint_id, a.hostname, a.managed_state, a.agent_version,
       a.last_seen_at AS agent_seen, i.id, i.config_path, i.server_label,
       i.transport, i.endpoint_ref, i.registry_match, i.reported_at
  FROM endpoint_inventory i
  JOIN endpoint_agents a USING (endpoint_id)
  JOIN principals p ON p.token = a.owner_token
 WHERE p.username = :'employee'
   AND a.status = 'active' AND a.agent_version <> 'unregistered'
   AND i.classification = 'shadow'
 ORDER BY a.endpoint_id, i.id;
```

판정 당시의 행이 보존되지 않았다면 깨끗한 기준 조건에서 다시 보고·호출하고 같은 시점의 위 행과 원장 입력을 함께 확보해야 한다. 다른 작업자의 설정이나 감사 기록은 지우지 않는다.

### 2. 설치 로그인 결과를 상태 명령으로 전달

원인: 기존 `bootstrap.connect`의 `model_signed_in`은 최종 출력 JSON에만 있었고 `managed-linux.next_step`에는 전달되지 않았다. 설치 때 Claude 인증 만료가 확인돼도 상태 화면은 하네스 실행을 안내했다.

수정: `bootstrap.py:888`이 불리언 결과를 계정별 `model-<계정>.json`에 원자적으로 저장한다. 파일은 root가 쓰고 일반 사용자는 읽는다. `managed-linux.py:672`의 `model_status`가 Claude/Codex 불리언만 허용해 서비스 게시·일반 상태·실시간 상태·`--check`에 연결한다. `next_step`(`:603`)은 `False`인 하네스의 실제 로그인 명령을 안내하며 격리 계정은 해당 로그인 셸을 사용한다. 서비스의 새 보고로 사라지지 않고 제거 시 파일도 지운다(`:1194`). 무응답·대기·격리·철회·네트워크 단절 안내의 우선순위는 유지한다.

이 값은 **마지막 설치 점검의 관측**이다. 상태 명령은 기존 MCP 연결 확인만 수행하며 모델 인증을 재검사하지 않는다. 로그인 이후의 성공이나 이후 만료는 별도 실제 모델 점검이 필요하다. 기존 설치는 새 키트로 재설치해야 이 관측 파일이 생긴다.

### 3. 안전한 일시 오류 재시도와 최종 원인 표시

당시 첫 설치 실패의 정확한 예외·HTTP 상태는 제공 기록에 없어 **당시 사건의 원인은 재현 불가**다. 다만 기존 `enroll`(`managed-linux.py` 기준 코드 423행)은 등록·정책 요청을 한 번만 실행했고, 실패 안내는 예외 종류/HTTP 상태를 생략했다. 이 동작은 전송 대역으로 재현했다.

`preparation_request`(`managed-linux.py:440`)는 등록 전 연결 거부·임시 DNS 실패에 한해 같은 장치 키로 최대 3회 시도한다. 등록 성공 후 정책 GET의 HTTP 502/503/504·전송 오류도 최대 3회 시도한다. 간격은 1·2초, 요청당 제한은 기존 15초(단계별 요청/대기 최대 약 48초, TLS 확인 등 부대 작업 제외)다. 정책 재시도는 성공한 등록 POST를 반복하지 않는다. 등록 시간 초과·연결 리셋·HTTP 오류는 일회용 토큰이 이미 소모됐을 수 있어 재전송하지 않는다. 인증/인가·인증서·설정 검증 실패도 재시도하지 않는다.

`preparation_error`(`:425`)가 HTTP 상태 또는 안전한 오류 종류만 만든다. Linux bootstrap·macOS 최종 오류와 기존 보호 로그가 이를 사용하며 URL·응답 본문·명령 인자·자격은 남기지 않는다. HTTP 오류에서 없는 `stderr`를 읽다가 진단 자체가 실패하지 않도록 subprocess 오류에만 `stderr`를 읽는다. 등록/정책 실패 시 기존 로컬 설치 보존 경계는 유지한다.

## 검증

Windows Python 3.10.5와 설치된 Node에서 실행했다. 임시 HOME·CODEX_HOME·설정 파일, OS/API/모델 대역의 단위 시험이며 실제 OSS MCP·DB·솔루션 기기·모델 실행 증거가 아니다. 새 의존성은 없다.

| 확인 종류 | 명령·범위 | 결과·근거 |
| --- | --- | --- |
| 수정 전후 반례 | Git 제외 `runtime/fix5-checks/compare_baseline.py`, `git show ca4734af` 소스를 메모리에 적용 | 네 시험 중 로그인 결과 연결·일시 실패 복구·최종 원인 세 시험이 기준에서 실패(실패 1·오류 2), 현재 네 시험 모두 통과. 설정 분류 대조는 기준에서도 통과 |
| 관련 Python 7스위트 | `python -B -X utf8 full_stack_lab/tests/<이름>.py`: `endpoint_collector_check` 16, `kit_simple_mode_check` 13, `linux_kit_reinstall_check` 40, `windows_kit_reinstall_check` 10, `kit_screen_check` 19, `kit_continuity_check` 27, `macos_kit_check` 11 | **134통과·POSIX 2생략**, 총 136건. 설치/점검/JSON→실제 `status --check`, 상태 반복 게시, 양 하네스, 잘못된 불리언/비밀 필드 제외, 제한 횟수·등록 미재전송·기존 설치 보존·제거 대조 포함 |
| 확장 설치 사전점검 | `kit_install_upfront_check.py` | 31건 중 24통과·3실패·4생략. TOML 파서 점검 하위 명령 때문에 명령 배열 기대가 다른 세 실패는 기준 커밋에서도 동일. 이번 변경으로 고친 것으로 세지 않음 |
| Node 회귀 | `node --test full_stack_lab/tests/kit-download-console.test.mjs` | 4통과 |
| 정적 검사 | 변경 Python 6파일 `compile`, `deploy/check.py`, `git diff --check`, `split_decisions.py check` | 통과. 지정 `split_decisions.py index`만 실행 |
| 추적 검사 | `check_trace.py` | 실패: 제공된 미추적 `BRIEF-fix5.md`의 예약 결정 번호 두 개가 정의되지 않은 참조로 검출됨. 제품 결정은 D-279 하나만 추가, 제공 파일은 수정하지 않음 |
| 전체 위키/분석 | `check_wiki.py`, `check_enterprise_analysis.py` | 각각 기존 원문 누락 29·매핑 해시 29, 코드/연동 해시 54로 실패. 일괄 생성 금지 유지, 통과 아님 |
| 환경 제약 | `python -m pyflakes`, `endpoint_inventory_check.py` | pyflakes 미설치, 후자는 Python 3.10의 `datetime.UTC` 부재로 import 중단. 지원 기기 이미지에서 확인 필요 |
| 실제 모델·MCP·배포 | 미실행 | 스택·기기 상태를 변경하지 않음 |

실행 로그와 비교 도구는 Git 제외 `research/collaboration-console/runtime/fix5-checks/`에 있다. 개발 중 스텁의 새 파일 저장 동작 누락과 진단의 HTTPError `stderr` 접근 실패를 확인해 수정했고, 해당 최종 스위트는 통과했다. 위키 생성물 일괄 재생성·push·병합은 하지 않았다. 원격 HEAD 재확인은 네트워크 연결 제한으로 실패했다.

## 실패·미완료·한계

- 작업 파일 13개를 명시한 `git add`가 공통 Git 저장소 `.git/worktrees/r1-fix/index.lock: Permission denied`로 실패했다. 스테이징된 파일·새 커밋은 없으며 최종 HEAD는 시작과 같은 `ca4734afc1932246d2b4b01ceb77ec9e2b6cd8aa`다. 잠금·ACL·권한을 바꾸거나 다른 Git 경로로 우회하지 않았다. 정상 Git 쓰기 권한 환경에서 이번 변경만 커밋해야 한다.
- 원장 165의 설정 파일·항목과 당시 첫 설치 실패 원인은 현재 자료만으로 확정할 수 없다. 현재 코드가 같은 직원 전체를 센다는 사실은 당시 원인 확정과 다르다.
- 설치 로그인 관측은 평상시 인증 상태의 지속 검증이 아니다. 로그인 후 성공을 자동 확인하는 새 기능은 추가하지 않았다.
- 생략/실패한 검사와 지원 OS 실설치·실제 네트워크 복구는 기기 이미지에서 확인해야 한다. Linux 설치 경로를 실제로 호출한 단위 시험도 OS·전송은 대역이다.

## 다음 작업

S4 후속: 실제 시험 배치의 같은 직원 전체 설정 행을 원장 입력과 동시에 확보해 정확한 파일·항목을 판별한다. 키트 재설치 후 Claude 로그인 필요 안내, 실제 모델 로그인·응답, 게이트웨이 재배포 중 연결 복구와 토큰 1회 사용 경계를 검증한다. 지원 이미지에서 POSIX·TOML/DB 의존 검사를 완료한다.

`check_freshness.py`는 9점검 중 기존 기준일·시트 사본·보고서 색인 관련 4건의 낡음 경고를 냈다. 일괄 생성물을 재생성하지 않았다.

## 사용자에게 필요한 입력

로컬 구현에는 추가 입력이 없다. 경보 출처 확정에는 당시 설정 인벤토리 행 또는 지정 시험 배치의 읽기 전용 재관측이 필요하다. 토큰·비밀번호 값은 보고서에 보관하지 않는다.
