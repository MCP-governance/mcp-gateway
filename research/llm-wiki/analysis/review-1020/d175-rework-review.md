미커밋

What this change does: DEV-73 adds a gateway-routed local MCP runner with signed manifests, per-job containers, device-side revalidation, queue controls, and termination hooks. It limits its security claim to a trusted gateway and records local-job evidence.

# DEV-73 재작업 적대 검토 — 2차

## 판정

**B — 중대 수정 뒤 재검토.** F1의 위협 범위 조정과 F3·F4·F6·F8의 주요 구현은 판단 문서에 부합한다. 그러나 F2의 정지 표식 복귀 결함, F7의 무제한 요청 인자, F9의 결과 해시 불일치가 남아 승인할 수 없다.

## 기준과 확인 범위

- 기준: `origin/main` `d86bf16`; 대상 `dev73-target` `cdba06f`.
- 반드시 `git diff origin/main...dev73-target`의 세 점 변경과 `git show dev73-target:<경로>`의 대상 내용을 사용했다. 1차 검토와 항목별 판단은 `origin/main`에서 읽고, 대상 보고서는 `dev73-target`에서 읽었다.
- 세 점 변경 중 시험 파일은 신규 4개뿐이다. main에 이미 있던 시험 파일의 기대값·AST 변경은 없다.
- 메인이 제공한 Linux 결과: `dev73_rework_check.py` 21/21, `runtime_worker_check.py` 7/7. `local_run_manifest_check.py`는 `고정된 마운트가 필요합니다` 오류 1건. 두 PostgreSQL 시험은 격리 DB 실험실 미기동으로 미실행이다. 이 검토에서는 시험을 실행하지 않았다.

## F1~F10 처리 대조

| 항목 | 상태 | 근거와 판단 |
|---|---|---|
| F1 게이트웨이 탈취 후 작업 본문 | **표시만** | 중재대로 별도 작업 서명을 만들지 않고, 게이트웨이·OPA를 신뢰 기준점으로 두며 침해 게이트웨이는 위협 모델 밖이라고 명시했다. 완료 조건에서도 해당 주장을 뺐다. `docs/ai/SECURITY_BOUNDARIES.md:102-107`, `docs/ai/DECISIONS.md:1817-1822` |
| F2 철회·종료·격리와 큐/실행 정지 | **미흡** | 세대·만료·정책·장치 상태를 claim/start에서 재검증하고, 전환 트리거는 미확인 실행이 남으면 전환을 거부한다. 서버 자동중지 복귀가 정지 표식을 지우지 않으며, 토큰 철회 제어 요청은 철회 트랜잭션이 보유한 같은 advisory lock을 기다린다. 자세한 경합은 아래 F2 항목 참조. `local_jobs.py:313-338,405-507,539-580`, `local_run_tables.sql:105-148` |
| F3 이미지 공급망 | **구현됨** | 승인 시 내부 미러 allowlist와 digest를 확인하고, 실행기는 별도 allowlist·digest를 재검증하며 로컬 이미지가 없으면 실패한다. pull 경로는 `--pull=never`뿐이다. cosign은 의도대로 DEV-77에 남기고 `확인 안 됨`으로 표시한다. `local_jobs.py:159-185`, `local-runner.py:52-53,141-160`, `local-runner.py:127-138` |
| F4 마운트 경로 교체 경합 | **구현됨** | 전체 부모를 `O_NOFOLLOW`로 열어 inode FD를 유지하고, 실행 직전 경로 inode를 대조한 뒤 FD 경로를 bind 원본으로 준다. Linux 경로 경합 시험은 메인 제공 결과와 부합하나 Podman/Docker가 FD 경로를 실제로 어떻게 bind하는지는 미측정이다. 실패한 기존 fixture는 제품 회귀가 아니다. `local-runner.py:56-105,175-180`, `tests/dev73_rework_check.py:162-212` |
| F5 엔진 격리 실측·표시 | **미흡** | 설정·판본을 요구하고 컨테이너 `uid_map`을 읽지만, 관찰 화면은 모든 구성에 `탈출 시 호스트 root`를 고정 표시하고 `user_mapping`은 항상 `확인 안 됨`이다. 실측 증거는 `local_job_events`에 쓰일 뿐 화면에서 읽지 않는다. `local-runner.py:141-160,192-209,343-344`, `core.py:565-566`, `console.js:2681-2685`, `local_jobs.py:533-535` |
| F6 stdout 메모리·시간 상한 | **구현됨** | 행 256 KiB, 총 1 MiB, 1,024행, 큐 32행, 읽기 20초와 실행 deadline을 둔다. 초과·무응답 시 세션을 멈춘다. `local-runner.py:26-30,211-234,242-265,321-337` |
| F7 큐·저장 상한 | **미흡** | 건수·생성률·운영 행·결과 저장 상한은 있으나, 호출 `params`의 바이트/직렬화 크기 상한은 없다. 건수 상한만으로 큰 인자 저장을 제한하지 못한다. `local_jobs.py:31-37,207-245,513-524` |
| F8 관찰 장치 고정 | **구현됨** | 신청 장치를 compare-and-set으로 한 번 묶고, 이후 heartbeat 순서로 바꾸지 않는다. 실제 호출에서 도구 계약을 다시 대조한다. `local_jobs.py:130-146,475-507`, `local-runner.py:357-367` |
| F9 job·dispatch 증거 결속 | **미흡** | UUID·시각·상태·해시를 decision client 및 이벤트에 연결한다. 다만 전체 결과 저장 상한에서 결과를 바꾼 뒤 해시를 다시 계산하지 않아 실제 저장 결과와 해시가 달라진다. `local_jobs.py:275-291,510-535` |
| F10 미수령·미확인 결과 구분과 재실행 금지 | **구현됨(정적 경로)** | 수령 전은 `NotStarted`, claim 뒤 응답 불명은 `TimeoutError`로 구분하고, `upstream_attempted`로 `confirmed_not_executed`/`uncertain`을 정산한다. 실행기 재시작 복구는 제거·정지 확인만 하고 재실행하지 않는다. 단, PostgreSQL 통합 시험은 미실행이다. `local_jobs.py:258-272,275-283`, `local-runner.py:387-406,409-423`, `core.py:143-145` |

## 필수 수정

1. **F2 — 자동중지 복귀 뒤 로컬 실행이 영구 차단됨** (`full_stack_lab/gateway/app/ops_response.py:67-86,118-138`; `full_stack_lab/gateway/app/local_jobs.py:318-320,539-562`)
   - **상황/재현:** 로컬 서버가 이상 호출로 자동 중지되면 `suspend()`가 `local_jobs.quiesce()`를 호출해 `local_run_stops(server_id=...)`를 남긴다. 이후 `/api/ops/servers/{id}/resume`은 `ops_response.resume()`만 호출하며 이 표식을 지우지 않는다. 재개 뒤 `authorized()`가 `stopped=true`를 계속 읽으므로 도구 호출이 계속 거부된다.
   - **심각도:** 높음 — 복귀 조작이 로컬 서버에 효력을 주지 않는다.
   - **수정:** 서버 복귀 상태 전환과 같은 복귀 경로에서 해당 범위의 정지 표식을 제거하되, 전환 실패 시 표식만 먼저 제거되지 않도록 원자화한다.

2. **F2 — 토큰 철회가 취소 제어 요청과 같은 잠금에서 교착 대기함** (`full_stack_lab/gateway/app/local_jobs.py:444-455,565-580`; `endpoint-agent/managed-linux.py:64-77`; `endpoint-agent/local-runner.py:327-335`)
   - **상황/재현:** 실행 중 토큰을 철회하면 `prepare_token_revocation()`이 `local:token:<jti>` advisory lock을 잡은 채 `stopped_at`을 기다린다. 실행기의 `/control`은 `validate_job()`→`lock_execution()`에서 같은 lock을 얻어야 `stop_requested`를 확인하므로 정상 취소 응답을 받지 못한다. 현재 장치 HTTP timeout 15초가 watchdog을 깨워 컨테이너를 멈추는 경로가 된다. 즉시 실행 허용 경합은 찾지 못했지만, 정지 자체가 제어 응답이 아니라 timeout에 의존한다. 잠금 대기 한도가 25초다.
   - **심각도:** 중간 — 현재 15초 timeout이 정지를 유도하므로 철회 커밋 뒤 실행되는 창은 확인하지 못했다. 다만 정지 경로가 제어 응답이 아니라 우연한 timeout 순서에 의존한다.
   - **수정:** 정지 확인 중인 작업은 이미 기록된 `stop_requested`를 잠금 순환 없이 읽어 중지할 수 있게 하고, 시작 허용의 직렬화는 최종 철회 커밋까지 유지한다. 두 PostgreSQL 경합 시험에서 실행 중 토큰 철회를 검증해야 한다.

3. **F7 — 한 건의 큰 인자가 큐 건수 제한을 우회함** (`full_stack_lab/gateway/app/local_jobs.py:207-245,513-524`)
   - **상황/재현:** 허용된 `tools/call`의 `params`는 크기 검사 없이 `Jsonb(params)`로 저장된다. 현재 대기열·요청률·전체 행 수 검사는 개수만 제한하므로, 대기열이 비어 있을 때 매우 큰 `arguments` 하나도 INSERT 경로를 통과한다. 결과의 256 KiB/64 MiB 제한은 입력 인자를 보호하지 않는다.
   - **심각도:** 높음 — 사용자 호출 한 번으로 큰 DB 행과 게이트웨이 파싱·전송 메모리를 유발할 수 있다.
   - **수정:** MCP 인입과 `exchange()` 양쪽에서 직렬화된 요청 크기 상한을 적용하고, 상한 초과는 INSERT 전에 fail-closed 처리한다. 상한 경계 시험을 새 시험 파일에 추가한다.

4. **F9 — 결과 저장 상한에서 evidence hash가 저장 결과와 달라짐** (`full_stack_lab/gateway/app/local_jobs.py:519-535`)
   - **상황/재현:** `digest`를 먼저 계산한 뒤(519행), 기존 결과 저장량이 64 MiB에 도달하면 결과를 `None`과 상한 오류로 바꾼다(522-524행). 그 뒤 원래 큰 결과의 해시를 `result_sha256`과 `local_job_events`에 기록한다.
   - **심각도:** 중간 — 이 경계에서 dispatch 증거 해시가 실제 저장된 상태를 증명하지 않는다.
   - **수정:** 저장 상한에 따른 결과 변환을 먼저 끝내고, 실제 저장할 결과/오류 값으로 해시를 계산한다. 이 분기를 PostgreSQL 시험으로 확인한다.

## 수정·검증 필요

5. **F5 — 등록 화면이 측정값 대신 고정 위험 문구를 보여 줌** (`full_stack_lab/gateway/app/core.py:565-566`; `full_stack_lab/gateway/app/agent_static/console.js:2681-2685`; `full_stack_lab/gateway/app/local_jobs.py:533-535`)
   - **상황/재현:** 사용자 매핑 모드가 `podman-auto` 또는 `docker-remap`이어도 등록 응답은 `isolation_scope='탈출 시 호스트 root'`, `user_mapping='확인 안 됨'`을 고정 반환한다. 컨테이너 실행 후 보낸 실제 `uid_map` 증거는 저장만 되고 화면 조회 경로가 없다.
   - **심각도:** 중간 — 운영자가 적용된 격리 모드와 실측 결과를 승인 화면에서 구분할 수 없다.
   - **수정:** 기기·엔진 판본에 묶인 측정값을 승인 화면에서 읽을 수 있게 연결하고, 측정 전에는 구성값과 미확인 상태를 정확히 표시한다. host 모드 위험 문구는 host 모드에서만 표시한다.

6. **F4 — 실패한 매니페스트 시험은 낡은 호출 방식이며 경로 검증도 실제로 하지 않음** (`full_stack_lab/tests/local_run_manifest_check.py:78-97`; `endpoint-agent/local-runner.py:123-124,175-180`)
   - **상황/재현:** 시험은 `container_command()`를 `mount_options` 없이 직접 호출해 `고정된 마운트가 필요합니다`에서 멈춘다. 같은 이유로 symlink/missing 경로 시험도 경로 검사 전에 거부되어 실제 거부 조건을 확인하지 않는다. 정상 실행 경로는 `Session`이 `PinnedMounts`를 만들고 FD 옵션을 전달한다.
   - **심각도:** 중간 — 메인 제공 Linux 21/21 결과는 별도 재작업 시험의 통과를 뜻하지만, 이 파일의 회귀 검사는 현재 깨졌고 경로 검증을 입증하지 못한다. 이는 정상 매니페스트를 막는 제품 회귀는 아니다.
   - **수정:** 테스트가 `PinnedMounts`와 `mount_options`를 준비하도록 fixture를 갱신하고, 실제 `PinnedMounts`의 symlink/부재 거부를 별도로 검증한다. 컨테이너 엔진의 FD bind 동작은 별도 실측이 필요하다.

## 경합·재생 결론과 시험 한계

- **claim과 전환 커밋 사이:** `claim()`과 `validate_job()`이 정책·token·사용자 advisory lock 및 서버/계정/장치/승인 행 잠금을 잡는다. lifecycle/승인 변경은 대응 원본 행에서 trigger를 실행한다. 전환이 먼저 커밋되면 claim/start 재확인이 작업을 거부한다. claim/start가 먼저면 전환은 대기하거나, 시작된 작업의 정지 회신이 없을 때 `55000`으로 롤백된다. 따라서 현재 소스에서는 철회 커밋 후 장치가 새 작업을 claim/start하는 창을 찾지 못했다.
- **과거 서명 매니페스트:** 현재 승인 digest·세대와 만료를 대조하고, 서버 전환 때 서명 세대를 폐기 목록에 기록한다. 철회된 같은 세대는 `approve_manifest()`가 재승인하지 않는다. 코드는 replay 차단을 구현하지만 DB 경합 시험 2개가 미실행이므로 SQL trigger·잠금 동작은 아직 실행 증거가 없다.
- **중지 전환:** `quiesce()`가 먼저 admission 표식을 커밋하고 대기 작업을 취소한 다음 실행 정지 회신을 기다린다. 이후 lifecycle 전환이 별도 트랜잭션으로 일어나지만 표식이 남아 admission을 닫으므로, 한 트랜잭션은 아니어도 안전한 2단계 장벽으로 설계되어 있다. F2의 복귀 표식 누락과 토큰 철회의 잠금 순환은 이 장벽을 완결하지 못한다.
- **매니페스트 시험 오류 판단:** 정상 production 경로는 `PinnedMounts` FD를 생성하고 `container_command(..., mount_options=...)`로 넘긴다. 오류는 해당 인자를 주지 않는 시험 fixture의 구형 호출 방식에서 발생하므로 정상 매니페스트 거부 회귀가 아니다. 다만 그 파일의 symlink 검사도 같은 선행 오류로 잘못 통과할 수 있다.
- **실행 전 조건 확인:** 임의 레지스트리 pull 경로는 확인하지 못했다. 두 allowlist·digest 검사와 로컬 이미지 inspect 뒤 `--pull=never`를 사용한다. F6 stdout 경로는 행·바이트·행수·큐·시간 상한이 모두 적용된다. F7은 job 개수 상한이 모든 교환 메서드에 공통 적용되지만, `params` 바이트 상한이 빠져 전체 입력 크기는 제한되지 않는다.
- **main 시험 변경:** 세 점 diff의 시험 파일 네 개가 전부 `A`(신규)이며 기존 시험 수정은 0건이다. 신규 `local_run_manifest_check.py`는 main에 있던 기존 시험이 아니다.
- **실행 증거:** 21/21과 7/7은 메인이 제공한 Linux 결과로만 반영했다. PostgreSQL 두 시험이 미실행이므로 F2 전환 경합, F7 동시 포화, F9 결과 hash 경계를 DB 통과로 세지 않았다. 실제 Podman/Docker FD bind·uid_map·외부 연결 차단·정지/복구와 공개 OSS MCP/PJ1 효과는 확인되지 않았다.

Not checked: 이 검토에서 시험·DB·컨테이너 엔진·기기·PJ1을 실행하지 않았다. 위의 Linux 및 단위 시험 수치는 메인이 제공한 결과다.

Verdict: **B — F2 전환 복귀/취소 경로, F7 입력 크기 상한, F9 해시 정합성을 수정하고 PostgreSQL 경합 시험을 통과한 뒤 재검토.**

## 메인 판정 (2026-10-21)

**B를 받는다.** F1·F3·F4(제품)·F6·F8·F10은 판단 문서대로 됐다. 병합 전에 고칠 것:

1. **F2 자동 중지 복귀가 로컬 정지 표식을 지우지 않음(높음)** — 복귀 조작이 효력이 없다. 복귀 상태 전환과 정지 표식 제거를 **같은 트랜잭션**에서 한다.
2. **F7 요청 인자 크기 상한 없음(높음)** — MCP 인입과 `exchange()` 양쪽에서 직렬화 크기 상한, 초과는 INSERT 전에 차단.
3. **F9 결과 저장 상한 뒤 해시 불일치(중간)** — 저장할 값을 확정한 뒤 해시를 계산한다.
4. **F2 토큰 철회 ↔ 취소 제어 잠금 순환(중간)** — 정지 확인 중인 작업은 기록된 `stop_requested`를 잠금 없이 읽어 멈추게 한다. 15초 timeout에 기대지 않는다.
5. **F5 등록 화면 고정 문구(중간)** — 측정 전에는 구성값과 「확인 안 됨」을, host 모드에서만 「탈출 시 호스트 root」를 보인다. 실측값을 화면 조회 경로에 연결한다.
6. **F4 낡은 매니페스트 시험** — 제품 회귀가 아니라 1차 구현 때 시험이다. `PinnedMounts`·`mount_options`를 쓰도록 fixture를 고치고 symlink/부재 거부를 실제로 검증한다(이 파일은 main에 없던 새 시험이라 기대값 변경 규칙에 걸리지 않는다).

수정 뒤에는 **고친 6건만** 대상으로 재확인한다(전체 재검토 불필요). PG 경합 시험 2개는 기기 일회성 실험실에서 메인이 돌린다.
