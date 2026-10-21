# DEV-73 1차 구현 적대 검토 — D-175

- 검토자: Codex luna
- 작업 범위: 읽기 전용 코드·설계 검토. 코드 및 시험 수정 없음.
- 기준: `origin/main` `fd56aef6db92ab2769524153da531d04aab587b2` → `origin/10/20-dev73-impl` `217da74ed4731eb006ce3c167b17fec835b66155`; diff 대상 17개 파일(+984/-18).
- 대상 코드의 현재 체크아웃 여부: 아님. 검토 브랜치 `10/20-dev73-review`에서 원격 참조를 읽음.
- 참조: `direction-1020/control-review.md` C10 §8, DEV-73 설계 D-175 §8~9, `docs/ai/ARCHITECTURE.md`, `SECURITY_BOUNDARIES.md`, `DECISIONS.md`.
- A/B/C 판정 기준: A=승인, B=중대 수정 뒤 재검토, C=현재 구현 반려.

## 요약 판정

**C — 현재 구현은 배포·PJ1 시험 대상으로 넘기기 전에 재설계·수정이 필요하다.** 게이트웨이의 기존 `_call_upstream` 판정 경로 재사용, 토큰의 `device_id`로 작업 장치 고정, 장치별 조건부 claim, 서명 검증 함수 자체는 합리적이다. 그러나 장치가 검증하는 서명은 매니페스트뿐이고 작업(JSON-RPC 요청)은 게이트웨이가 임의로 만들어 보낼 수 있다. 매니페스트 이미지 자체 서명·내부 미러 검증, 승인 철회/종료와 대기열의 원자적 결속도 없다. 이 세 공백은 C10 필수 제약과 게이트웨이 탈취 위협 모델을 만족하지 못한다.

## 발견 사항

### F1 — 치명적: 서명되지 않은 작업 본문으로 게이트웨이가 사용자 권한의 로컬 도구를 실행시킬 수 있음

- 근거: `full_stack_lab/gateway/app/local_jobs.py:134-141, 210-233`; `endpoint-agent/local-runner.py:163-190`; `full_stack_lab/gateway/app/main.py:1513-1527`.
- 재현/반례: 이미 승인된 파일 MCP 매니페스트와 그 서명을 복사한 게이트웨이 침해자가 `local_jobs`에 `server_id`·유효한 매니페스트·서명은 그대로 둔 `method='tools/call'`, `params={'name':'delete_file','arguments':{'path':'work/…'}}` 행을 삽입한다. 장치는 매니페스트 서명과 digest만 확인하고, 작업은 JSON-RPC 형식과 허용 키만 검사한 뒤 컨테이너에 전달한다. `dispatch_intents`, OPA, 사용자 동의, 도구 입력 제한을 다시 검증하지 않는다. 따라서 DB/API를 장악한 게이트웨이는 정상 승인 도구의 임의 인자를 사용자 권한으로 실행할 수 있다. 이 경로는 새 이미지·명령·마운트 서명 위조를 요구하지 않는다.
- 수정안: 장치가 독립 검증할 수 있는 1회용 작업 승인 증명에 호출자·장치·서버·매니페스트 digest·도구·정규화된 인자 지문·결정/원장 ID·기한·nonce를 묶는다. 서명 키는 게이트웨이 프로세스/DB와 분리하고, 장치는 재사용을 거부한다. 별도 신뢰 검증을 도입하지 않는다면 게이트웨이 탈취는 통제 경계 밖이라고 위협 모델과 화면에 명시하고 DEV-73의 목표 범위를 낮춰야 한다.
- 심각도: **치명적**. 전송 토큰 미전달·게이트웨이 순차 판정 불변식의 독립 효과를 장치가 확인하지 못함.

### F2 — 치명적: 승인에서 제외되거나 종료된 과거 서명 매니페스트가 재생 가능

- 근거: `full_stack_lab/gateway/app/main.py:1480-1484`는 `local_servers`를 `policy_hash` 밖에 두며 목록은 pull/정지 참고용이라고 명시; `endpoint-agent/local-runner.py:141-158, 163-177`은 서명·digest만 확인하며 작업 시 현재 허용 목록 포함 여부, 서버 lifecycle, 종료 케이스를 확인하지 않음; `local_jobs.exchange:137-156`은 호출 시 작업을 행으로 넣고 실행기 정지를 원자적으로 연동하지 않음.
- 재현/반례: 유효 서명된 서버 작업을 큐에 둔 직후 관리자가 등록을 해제하거나 종료 케이스를 연다. 실행기는 다음 정책 조회까지 최대 60초(활성 서비스의 `managed-linux.py:303-345`) 이전 목록을 보유할 수 있다. 목록에서 빠진 뒤에도 claim 루프는 계속 돌고, 대기 작업은 목록 membership과 무관하게 같은 서명을 검증해 실행한다. 이미 제거된 서버의 이전 서명 작업도 만료·폐기 목록이 없어 다시 넣으면 유효하다. 호출 시작 시점의 게이트웨이 재확인은 큐 발행 뒤의 철회를 막지 못한다.
- 수정안: 작업 claim/실행 직전 정책 세대·서버 lifecycle·승인 manifest hash·철회 상태를 장치에서 확인하고, 철회와 큐 취소/실행 잠금을 같은 전환에 결속한다. 서명 키 회전·서명 ID/세대·만료·취소 목록을 장치에서 검증한다. 이미 claim된 작업은 실행 직전 재검사와 종료 시 정지 확인이 필요하다.
- 심각도: **치명적**. 종료의 차단 우선 및 C1~C4 연속성 증거와 충돌.

### F3 — 높음: 이미지 서명·내부 미러·승인 소스와 이미지 digest 연결이 구현되지 않음

- 근거: `endpoint-agent/local-runner.py:64-76, 85-87, 148-151`; `full_stack_lab/field/sign-local-manifest.py:19-41`; 설계의 C10 반영 `dev73-local-isolated-run.md:88-90`, 1차 한계 `:104-107`.
- 재현/반례: 매니페스트 정규식은 임의 레지스트리의 `repo@sha256:…`를 허용한다. 이미지가 없으면 실행기는 그 주소에서 root 서비스 권한으로 `pull`한다. 서명 도구는 JSON 매니페스트만 서명하고 OCI 이미지 서명/provenance를 확인하지 않는다. `--pull=never`는 실행 시 pull을 막지만 앞선 pull 단계는 허용한다. 매니페스트가 승인된 저장소 commit으로부터 빌드된 이미지인지도 확인하지 않는다.
- 수정안: 내부 미러 allowlist·digest 고정·OCI/cosign 서명 필수 검증을 장치에서 시행하고, 검증자/정책 키는 게이트웨이와 분리한다. 이미지 digest를 승인된 빌드·SBOM·출처 증명에 결속한다. pull은 승인된 내부 미러에서 사전 반입할 때만 허용한다.
- 심각도: **높음**. D-175의 알려진 미완료 항목이자 C10 필수 조건 위반.

### F4 — 높음: 경로 검사와 컨테이너 bind mount 사이 심볼릭 링크 교체 경합

- 근거: `endpoint-agent/local-runner.py:48-61, 64-76, 84-89`.
- 재현/반례: 관리 계정이 허용된 `work` 경로를 만들고, 실행기가 `realpath(target)==target` 및 존재 여부를 확인한 직후 컨테이너 엔진이 bind mount를 해석하기 전에 디렉터리를 다른 이름으로 바꾸고 `work`를 다른 위치(예: `~/.ssh`)를 가리키는 심볼릭 링크로 바꾼다. 검사는 통과하지만 엔진은 교체된 경로를 볼 수 있다. 검사와 `Popen`은 원자적이지 않다. rw 허용 경로라면 시작 파일·다른 로컬 작업물 변경 지속성에도 연결된다.
- 수정안: 경로를 실행기에서 안전하게 고정한 디렉터리 FD/openat 방식으로 검증·bind 가능한 실행 인터페이스를 사용하거나 root 소유의 스냅샷/전용 디렉터리로 복사한다. 최소한 모든 부모를 검사하고 실행 시점에 mount namespace 안에서 재검증한다. 경합 시험에 교체 반복을 포함한다.
- 심각도: **높음**. C10 §8의 재검증 요구 및 홈/점 디렉터리 금지의 TOCTOU 공백.

### F5 — 높음: rootful 컨테이너 탈출 시 호스트 root 영향에 대한 완화·표시가 없음

- 근거: `endpoint-agent/local-runner.py:71-76`; D-175 설계 `dev73-local-isolated-run.md:38-41, 66`은 rootful 엔진과 탈출 시 root를 인정; C10 `control-review.md` §8 73-5는 user namespace/idmap을 먼저 실측하고 실패 시 통제 범위에 한계를 표시하도록 요구.
- 재현/반례: 승인 이미지 또는 컨테이너 런타임 취약점이 컨테이너 경계를 탈출하면 rootful Docker/Podman 호스트 root 권한으로 이어진다. `--user UID:GID`, capability drop, no-new-privileges는 컨테이너 안 권한을 줄일 뿐 rootful 엔진 경계의 탈출 결과를 사용자 UID에 제한하지 않는다. 코드에는 `--userns=auto`/idmap이 없고 통제 범위 경고도 이 구현에서 확인되지 않는다.
- 수정안: 지원 엔진/판본에서 userns/idmap을 실측해 적용한다. 적용 불가라면 장치 정책·Console의 통제 범위에 “탈출 시 호스트 root”를 정확히 표시하고 승인·위험 수용을 요구한다. 엔진별 설정 누락은 fail-closed 처리한다.
- 심각도: **높음**. OS 제약이 없는 로컬 컨테이너 격리를 승인 범위보다 강하게 보일 위험.

### F6 — 높음: 컨테이너 stdout을 무제한 메모리 큐에 적재해 root 에이전트 DoS 가능

- 근거: `endpoint-agent/local-runner.py:88-99, 105-124`.
- 재현/반례: MCP 서버가 응답을 내지 않고 stdout에 무한 행을 쓰거나 매우 큰 단일 JSON 행을 출력한다. `_read`는 모든 행을 무제한 `queue.Queue()`에 넣고 행 길이도 제한하지 않는다. 현재 `request`가 필요한 ID를 찾지 못하면 소비보다 빠른 생산으로 root 서비스 메모리가 증가한다. 결과 API의 1MiB 제한은 이 큐에 도달하기 전이라 보호하지 않는다.
- 수정안: stdout byte/line/queue 상한, 응답 최대 크기, 읽기 시간 제한을 두고 초과 시 컨테이너를 종료·세션 폐기한다. stderr 억제 외에 stdout 폭주를 독립 시험한다.
- 심각도: **높음**. 원격에서 승인된 MCP 이미지가 장치 root 서비스의 메모리를 고갈시킬 수 있음.

### F7 — 높음: 무제한 작업 누적과 장치 직렬 처리로 DB·서비스 DoS

- 근거: `local_jobs.exchange:134-156`은 매 MCP 메시지마다 행을 만들고 50ms 폴링; `claim:210-223` 및 runner `:138-159`는 장치당 한 작업씩 직렬 처리; `lifecycle_tables.sql`의 `local_jobs`는 인덱스만 있고 상한·보존·정리 작업이 없음.
- 재현/반례: 하나 이상의 관리형 장치에 대해 허용된 호출을 빠르게 생성하면 initialize/list/call별 행이 쌓인다. 큐 깊이·장치별 동시 처리량·호출률 제한이 이 테이블에 없고 `done`/`expired`도 삭제·보존 상한이 없다. 느린 MCP 작업 하나가 뒤의 작업을 막아 대기·timeout을 늘리고, 결과 행은 계속 PostgreSQL 용량을 사용한다. 게이트웨이 50ms DB 조회도 대기 호출 수에 비례한다.
- 수정안: 계정/장치/서버별 동시·대기열·생성률 상한, 짧은 claim lease, 기한 지난 행 정리와 감사 보존 분리를 둔다. 큐 포화 때 새 호출은 실행 전 차단하고, 장치·서버별 공정성을 보장한다. 지연 N≥100 및 폭주/복구 부하를 측정한다.
- 심각도: **높음**. 현재 대기열은 작업량·저장량 상한이 없다.

### F8 — 중간: 등록 계약 관찰 장치가 신청자가 명시한 장치가 아니라 최근 heartbeat 장치로 자동 선택됨

- 근거: `full_stack_lab/gateway/app/local_jobs.py:102-109`; 등록과 discovery에서 같은 선택 호출 `core.py:544-558, 624-641`.
- 재현/반례: 신청자 계정에 활성 관리형 PC가 둘 이상이면 `ORDER BY heartbeat_at DESC LIMIT 1`이 관찰 PC를 정한다. 신청서/승인 데이터에는 `observer_device` 선택이나 이 선택의 확인 단계가 없다. 어느 PC가 최근 heartbeat를 보냈는지에 따라 등록 계약을 관찰하는 PC가 바뀐다. 이후 호출은 `device_id`로 각 호출자의 PC에서 실행되므로 관찰 환경과 실제 실행 환경이 다를 수 있다(로컬 파일·장치 의존 MCP의 핵심 차이).
- 수정안: 승인된 신청에 관찰 장치 ID를 명시적으로 묶고, 등록 화면에서 해당 PC와 계정 UID를 사람이 확인하게 한다. 관찰·운영 호출의 장치 정책과 계약 지문을 분리 기록하고 장치 간 계약 불일치는 실행 전 차단한다.
- 심각도: **중간**. 다른 계정 장치로 교차 배정되지는 않지만, 신청자 다중 장치에서 선택이 비결정적이고 계약 증거의 적용 범위가 불분명.

### F9 — 중간: 결과는 장치 bearer 자격에만 묶이고 호출/판정/원장 ID와의 job 상관키가 없음

- 근거: `main.py:1519-1527`; `local_jobs.complete:225-234`; `lifecycle_tables.sql`의 `local_jobs` 열(작업 UUID, 장치, 서버, manifest, method/params, 상태; dispatch request/decision ID 없음); 새 DB 시험 `tests/local_jobs_pg_check.py:41-54`.
- 관찰/반례: 일반적인 다른 장치 자격으로 타 장치의 claim/result를 보내면 device_id 조건과 `state='claimed'` 때문에 거부된다. 이는 시험에서도 직접 확인한다. 다만 결과 본문은 오직 `X-Endpoint-Key`로 인증된 장치가 임의 JSON으로 제출할 수 있고 응답 서명/실행기 측정 증명은 없다. 키를 복제한 다른 컴퓨터는 같은 endpoint_id로 인증될 수 있다. job ID는 `decisions`/`dispatch_intents`와 DB 관계가 없어 원장 한 건에서 실제 장치 작업·claim·응답을 독립적으로 추적하기 어렵다.
- 수정안: claim token을 1회용·작업별로 발급해 job ID, endpoint ID, method, manifest hash, deadline에 묶고, 결과에 해당 token 및 응답 hash를 요구한다. dispatch request/decision ID를 job 행에 저장하고 결과 hash·시각을 append-only 감사에 연결한다. 장치 bearer 자격 복제는 하드웨어 증명 범위 밖임을 명시한다.
- 심각도: **중간**. 무자격 타 장치 위조 경로는 확인되지 않았으나 복제된 자격 및 독립 효과 증거 공백이 남음.

### F10 — 중간: 실행 전 미수령과 수령 후 불명확 결과의 구분이 상위 원장에 끝까지 보존되는지 입증되지 않음

- 근거: `local_jobs.exchange:151-156`은 queued 상태에서 timeout이면 `NotStarted`, claimed면 `TimeoutError`를 구분; 하지만 `core.py:1661-1669`는 `call_tool` 직전에 모든 경우 `upstream_attempted=True`로 설정하고 `local_jobs`의 job ID/state를 dispatch record에 전달하지 않음; 원격과 같은 `_call_upstream`은 사용됨.
- 재현/반례: runner가 작업을 claim하기 전에 기한이 지나면 transport는 “실행하지 않았다”고 알 수 있지만 감사 행에는 별도 job state나 원장 참조가 없다. claim 뒤 컨테이너가 실행하고 결과 업로드 전 연결이 끊기면 `TimeoutError`만 보인다. 이 두 경우가 감사 조회·Console·종료 판정에서 각각 `NOT_EXECUTED`와 `UNCONFIRMED`로 구별되는지, 재시도가 없는지 대상 코드/신규 시험으로 확인하지 못했다.
- 수정안: job UUID·claim 시각·완료 시각·상태·결과 hash를 dispatch evidence에 연결하고, `NotStarted`와 `TimeoutError`의 서로 다른 outcome을 검증한다. claim 뒤 불명확 결과는 자동 재실행 금지, 재시도는 새 승인 흐름으로 둔다.
- 심각도: **중간**. 코드 내 예외 구분은 있으나 최종 원장 의미와 재시도 불변식의 증거가 부족.

## 요청한 공격면별 결론

| 공격면 | 결론 |
| --- | --- |
| 서명/정규화 | signer·gateway·runner의 JSON canonical 함수는 모두 UTF-8, `ensure_ascii=False`, key sort, compact separator로 일치한다(`local_jobs.py:83-84`, `local-runner.py:30-32`, `sign-local-manifest.py:19-21`). Ed25519 검증도 gateway와 runner 양쪽에 있다. 테스트가 이 바이트 동일성과 변조 거부를 확인한다. 다만 작업 본문은 서명되지 않고, 서명된 과거 manifest의 폐기·만료 검증은 없다(F1~F2). |
| openssl/base64/임시 파일 | `shell=True`나 사용자 조립 명령은 없다. openssl argv는 고정되고 `TemporaryDirectory` 안에 키·본문·서명을 쓴다(`local-runner.py:35-45`). base64는 `validate=True`로 엄격 디코딩한다. 호출 인자 주입 우회는 확인하지 못했다. |
| 경로/명령/환경 | 엔진 호출은 argv 목록이라 셸 주입은 확인하지 못했다. digest·env 이름·숨김 경로 검사는 있다. 검사 후 bind 사이 링크 교체(F4), OCI 서명/미러 부재(F3), rootful 탈출 범위(F5)는 남는다. |
| 장치 선택·작업 재사용·경합 | 실제 호출은 토큰 `device_id`에서 오며 다른 장치는 자기 queue만 claim, `complete`도 동일 endpoint의 claimed 행만 바꾸도록 되어 있다. 추가된 PostgreSQL 대역 시험에서 동시 claim 4건의 중복 없음과 타 장치 결과 거부를 확인한다. 서버 철회 후 이미 큐에 든 작업, 과거 서명 replay는 막지 않는다(F2). 관찰 장치는 최신 heartbeat로 자동 선택(F8). |
| 컨테이너·외부 연결 | 실행은 `--network=none`, `--read-only`, `--cap-drop=ALL`, `no-new-privileges`, PID/memory 제한, 관리 사용자 UID로 실행한다. 그러나 기기 실제 엔진에서 외부 연결 실패는 시험하지 않았고 rootful 탈출(F5)·stdout DoS(F6)가 남는다. image pull은 runner가 필요 시 수행해 내부 미러 제한이 없다(F3). |
| 게이트웨이 판정/출력/원장 | `_call_upstream` 재사용으로 tools/list 재확인, 스키마 검증, PAC 재판정, dispatch intent, 출력 검사 경로는 같은 함수다(`core.py:1529-1669`). 다만 게이트웨이 침해 시 작업 본문이 이 검사를 우회(F1). local job ID와 decision/audit 상관키 부재 및 outcome 보존은 미입증(F9~F10). |
| 서버 sampling/roots | stdio 요청(`method`와 `id`)은 지원하지 않는다고 응답한다(`local-runner.py:122-124`). 프로토콜 단위의 보안 시험은 없고, 출력 폭주·큰 행은 별도 취약(F6). |
| 오프라인/마감/결과 크기 | 작업 deadline과 `claimed` 전후 timeout 구분, 결과 본문 1MiB 상한은 구현됐다(`local_jobs.py:134-156, 225-233`). 게이트웨이 출력 검사 상한(일반 256KiB)은 기존 경로에 맡긴다. 장치 오프라인·마감 경계·실제 256KiB 초과 동작은 실 MCP/기기에서 미실행. |
| 기존 시험 기대값 | `git diff --name-status`에서 기존 시험 파일 수정은 0건이다. 새 파일 `full_stack_lab/tests/local_jobs_pg_check.py`, `full_stack_lab/tests/local_run_manifest_check.py`만 추가됐다. 기존 기대값 변경 없음. |

## 증거 및 시험 한계

- 이번 검토에서 수행: 원격 참조 존재 확인, `origin/main...origin/10/20-dev73-impl` diff/name-status/stat 검토, 지정 설계·C10·코드·새 시험의 정적 읽기, `git diff --check`(출력 없음).
- 이번 검토에서 미실행: Python 시험, pyflakes, py_compile, OPA, 컨테이너/이미지 실행, 네트워크 egress, OpenSSL 런타임, PostgreSQL 격리 시험, PJ1 실제 하네스.
- 제출된 10/10 PostgreSQL 및 5/5 매니페스트 수치는 설계 파일의 기록이며 이번 독립 실행 결과가 아니다. DB 시험은 MCP 서버/컨테이너를 띄우지 않고 `claim`/`complete`와 사전 구성 응답을 사용한다(`tests/local_jobs_pg_check.py:1-5`). 실제 상용/공개 OSS MCP, Claude·Codex 두 하네스, 각 유형 N≥30(지연 N≥100)의 정상·공격·경계·장애·경합·복구 증거는 없다.
- 보고서만 추가했으며 소스·기존 시험·백로그를 수정하지 않았다. UTF-8, BOM 없음, LF로 작성했다.

## 다음 수정 우선순위

1. F1 작업 단위의 독립 증명 또는 게이트웨이 탈취 위협 범위 결정.
2. F2 승인 철회/종료·장치 격리와 큐/세션/이미지 정지의 원자적 연계 및 재생 방지.
3. F3 이미지 서명·내부 미러·소스 provenance 시행.
4. F4~F7 장치 경로·엔진·stdout·대기열 한계 보강.
5. F8~F10 장치 선택·결과 상관성·dispatch 상태를 검증하는 새 시험 및 실제 OSS MCP/PJ1 시나리오.

## A/B/C 판정

**C — 현재 1차 구현 반려.** B 경로(게이트웨이 경유 + 장치 작업 채널)는 살릴 수 있지만, F1·F2를 닫기 전에는 사용자 승인 밖 행위와 종료 후 실행을 배제할 수 없다. F3은 C10에서 정한 필수 공급망 조건이므로 “알려진 한계” 표기만으로 수용할 수 없다. 수정 뒤 새 적대 검토를 거친 다음에만 실기기 검증으로 진행한다.
