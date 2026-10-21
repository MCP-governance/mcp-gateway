# DEV-73 승인된 로컬 MCP 격리 실행 설계 (D-175)

- 상태: 2026-10-21 반려 판단 반영 재작업. 1차 구현은 반려(C) 이력이며 새 적대 검토 전이다. Linux만, Windows는 [방향 갱신](README.md) 1장 관용.
- 기준 commit: `5b5a134`(main). 근거: 방향 갱신 3장 DEV-73, MCP 공식 Local Server Security(격리·원격 우선·자격 분리), M05 제8항, TC260 4.2.3(a).
- 완료 조건(검증 목표): 승인 매니페스트 밖 로컬 실행 0 · 컨테이너 외부 연결 0 · 철회·종료 뒤 실행 0 · 원격과 같은 형식의 원장. 게이트웨이 침해 시에도 승인 밖 실행 0은 제외한다.

## 1. 지금 코드와 제약

| 항목 | 사실 |
| --- | --- |
| 관리 계정 | 직접 외부 연결 차단(nft UID 규칙), AppArmor 프로필이 승인 실행 파일 외 실행 거부 — PJ1에서 `bwrap` 실행이 막힌 기록(D-62 검증, DECISIONS 843행). docker 그룹 금지. |
| 엔드포인트 에이전트 | Linux에서 root systemd 서비스(`install-linux.sh`, `User=` 없음). 게이트웨이와 `/api/endpoint/*`로 장치 자격 통신(`agent.py` 895행~). |
| 비인가 로컬 MCP | 엔드포인트가 차단·관측(E13). 승인된 로컬 실행 경로는 없음. |
| 게이트웨이 실행 경로 | `core.execute_call` → OPA·PAC·동의·중대 영향 → `upstream.session(spec["endpoint"])`(streamable HTTP) → 출력 통제(DLP·출력 계약·오염) → 원장. |
| 기기 내부 실행기 | DEV-38: 자체 최소 실행기(고정 MarkItDown 레시피, [ToolHive 분석](../oss-deep/toolhive-runtime.md) §1). |
| 토큰 | 하네스 토큰은 장치 결속(`device_id`, D-62). |

## 2. 대안과 선택

### 2.1 판정 경로

| 안 | 내용 | 판단 |
| --- | --- | --- |
| A. 로컬 stdio 중계 + 판정 전용 API | 하네스 → `mcpgw-local` stdio → 중계가 게이트웨이 판정 API에 묻고 컨테이너로 전달, 결과를 다시 출력 통제 API로 | 판정·출력 통제를 둘로 쪼개 `execute_call`과 다른 두 번째 경로가 생긴다. 중계가 로컬 수신 지점(소켓)을 가진다(DEV-81 대상 증가). |
| B. **게이트웨이 경유 + 장치 작업 채널** | 하네스는 원격 서버와 똑같이 게이트웨이 `/mcp/<server>`에 붙는다. `deployment="local"` 서버의 upstream 호출만 "호출한 토큰의 장치"에 작업으로 보내고, 그 장치의 root 실행기가 컨테이너에서 실행해 결과를 돌려준다 | **채택.** 판정·PAC·동의·중대 영향·출력 통제·원장·dispatch_intents가 원격과 한 코드. 장치에 수신 지점이 없다(실행기는 바깥으로 long-poll). 로컬 파일이 게이트웨이를 한 번 거치는 지연·대역폭이 대가. |
| C. PC 수신 MCP 엔드포인트 | 게이트웨이가 PC의 실행기에 직접 HTTP | PC 수신 포트 신설, 고객망에서 PC 도달 보장 없음. 기각. |

방향 문서의 "로컬 중계가 판정 API에 묻는다"는 A를 전제로 했다. B가 같은 완료 조건(판정·원장 동일 형식)을 더 적은 코드로 만족하므로 바꾼다(검토 대상).

### 2.2 실행 주체

| 안 | 판단 |
| --- | --- |
| 관리 계정의 rootless podman | 관리 계정이 임의 이미지를 띄울 수 있어 비인가 실행 차단이 무너진다. 기각. |
| 관리 계정의 bubblewrap | AppArmor가 막고 있고, 열면 같은 문제. 이미지 digest 고정도 없음. 기각. |
| 별도 실행 계정의 rootless podman | 관리 계정 파일(0700 홈)을 읽지 못해 마운트가 성립하지 않는다. idmap 마운트로 풀 수 있으나 판본 의존. 후속 강화안. |
| ToolHive(`thv run`) | 아래에서 같은 podman/docker를 쓰고, HTTP 프록시 수신 지점·하네스 자동 등록·기본 outbound 허용을 끌 설정이 필요([분석](../oss-deep/toolhive-runtime.md)). 얻는 것이 수명 관리뿐이라 기각, 재조정 패턴만 참고. |
| **root 실행기 → rootful podman, `--user <관리 계정 UID>:<GID>`** | **채택.** 실행 권한은 엔드포인트 에이전트(이미 root)가 쥐고, 관리 계정은 podman·소켓 어디에도 접근하지 않는다. 컨테이너 프로세스는 관리 계정과 같은 UID라 파일 접근이 그 사용자를 넘지 않고, 마운트한 폴더만 보인다. |

컨테이너 옵션(고정): `podman run --rm -i --pull=never --network=none --read-only --tmpfs /tmp --cap-drop=ALL --security-opt=no-new-privileges --pids-limit=128 --memory=512m --user UID:GID --env-file <매니페스트 비밀 아닌 값> -v <허용 폴더>:<컨테이너 경로>:<ro|rw> <이미지@sha256:…> <명령>`.
seccomp·AppArmor는 podman 기본 프로필. 이미지는 내부 미러 allowlist의 digest로 고정하고 관리자가 사전 반입한다. 실행기는 pull하지 않는다. OCI/cosign 검증은 DEV-77이며 현재는 `확인 안 됨`이다.

## 3. 매니페스트·승인

- 도입 신청에 유형 `로컬 실행`: 이미지(`registry/repo@sha256:…`), 명령·인자, 마운트(`~/` 아래 상대 경로만, `..`·심볼릭 링크 해석 뒤 홈 밖 거부, ro 기본), 비밀 아닌 환경 변수. 비밀(API 키)이 필요한 서버는 이번 범위 밖 — 자격 분리 설계가 따로 필요.
- 계약 관찰: 기기 실행기(DEV-38)가 같은 digest를 `--network=none`으로 띄워 `tools/list`를 관찰하고, 사람이 승인(TOFU 금지 불변식 그대로). SBOM(Syft)·서명(DEV-77)은 이미지 기준으로 재사용.
- 배포: 승인되면 `endpoint_plane.managed_policy`에 `local_servers: [{server_id, image_digest, command, mounts, env, manifest_sha256}]`를 넣는다. 실행기는 정책 해시가 맞는 매니페스트만 실행한다.
- 하네스 설정: 원격 서버와 같은 게이트웨이 URL 항목(렌더러 변경 없음).

## 4. 작업 채널

1. 하네스 `tools/call` → 게이트웨이 `execute_call`이 평소대로 판정. `spec.deployment == "local"`이면 upstream 단계에서 `local_jobs`에 `(job_id, device_id=토큰의 장치, account_uid, server_id, manifest_sha256, request, deadline)` 삽입.
2. 장치 실행기: `GET /api/endpoint/local-jobs?wait=25`(장치 자격, `Depends`는 기존 엔드포인트 인증)로 자기 장치 작업만 받는다. 받은 작업을 `claimed`로 조건부 갱신(1회).
3. 실행기: 매니페스트 해시·계정 UID 대조 → (user, server)별 따뜻한 컨테이너에 MCP stdio 세션(공식 Python SDK `stdio_client`)을 열어 두고 `tools/call` 실행. 첫 연결과 재기동 때 `tools/list` 지문을 보고하고, 게이트웨이는 승인 계약과 다르면 그 서버 작업을 막는다(`MCP-CATALOG-001`과 같은 판정).
4. `POST /api/endpoint/local-jobs/{id}`로 결과 → `execute_call`이 기다리던 결과로 이어 받아 출력 통제·원장.
5. 마감 초과·장치 오프라인: 실행 전이면 `NOT_EXECUTED`, 수령 뒤 결과가 없으면 `UNCONFIRMED`(기존 dispatch 의미 그대로).

## 5. 위협과 대응

| 위협 | 대응 | 남는 한계 |
| --- | --- | --- |
| 관리 계정이 승인 밖 서버·이미지 실행 | podman·실행기 소켓 접근 없음, AppArmor 유지, 실행기는 정책 해시가 맞는 매니페스트만 | root 실행기 자체의 취약점 |
| 컨테이너 외부 연결 | `--network=none` | 마운트 폴더에 쓴 파일을 다른 프로세스가 내보내는 것은 기존 엔드포인트 통제 범위 |
| 다른 사용자 파일 접근 | `--user` 호출자 UID, 홈 아래 상대 마운트만, 경로 정규화 뒤 대조 | 공유 PC의 다른 계정은 D-170 관용 |
| 다른 장치·다른 사용자 작업 수령 | 작업은 호출 토큰의 `device_id`·계정에만 배정, 장치 자격으로만 수령, 1회 점유 | — |
| 컨테이너 탈출 | cap 전부 제거·no-new-privileges·seccomp 기본 | rootful 엔진이라 탈출 시 root. userns·idmap 강화는 실측 후 |
| 이미지 바꿔치기 | digest 고정·`--pull=never`·서명 검증(DEV-77) | 레지스트리 가용성 |

## 6. 시험 계획

- 단위: 매니페스트 검증(홈 밖·`..`·심볼릭 링크·절대 경로·태그 이미지 거부), podman 인자 고정 렌더링.
- PostgreSQL 격리 랩: 작업 배정(장치·계정 일치만), 1회 점유 경쟁, 마감·오프라인 상태, 계약 지문 불일치 차단, 원장 형식이 원격과 같은지.
- 실기기(PJ1, Linux): 공개 OSS 로컬 MCP 하나(예: `@modelcontextprotocol/server-filesystem` 고정 digest 이미지)로 승인 → 관리 Claude 호출 → 원장. 컨테이너 안 외부 연결 실패, 매니페스트 밖 폴더 접근 실패, 관리 계정의 `podman` 실행 실패를 각각 확인. 자체/mock MCP는 쓰지 않는다.

## 7. 구현 순서

1. 스키마(`local_jobs`)·도입 유형·매니페스트 검증(단위).
2. `execute_call` upstream 분기와 엔드포인트 작업 API(격리 랩).
3. 실행기(`endpoint-agent`): podman 실행·세션 유지·지문 보고, 설치기에 podman 의존과 rollback.
4. 기기 계약 관찰·콘솔 도입 화면 유형 추가 → PJ1.

## 8. 통제 방향 검토(C10) 반영

[control-review](control-review.md) 요약 7~11항을 이 설계에 더한다. 판정 경로 B(게이트웨이 경유)는 검토에서 지지됐다.

- **도입 심사**: 신청에 `로컬 실행이 필요한 이유`(로컬 파일·로컬 도구·장치 중 하나와 설명)를 필수로 받는다. 원격 API만 감싸는 서버는 로컬 실행으로 승인하지 않고 원격 등록이나 기기 실행기(DEV-38)로 보낸다(MCP Local Server Security).
- **마운트 규칙**: 홈 루트, 점 디렉터리(`~/.ssh`·`~/.config`·`~/.claude`·`~/.codex`·`~/.gnupg` 등)와 그 아래, 심볼릭 링크를 거부한다. 읽기 전용이 기본이고 쓰기는 정확한 폴더 목록으로만 연다(셸 시작 파일 변경을 통한 관리 계정 지속성 차단).
- **매니페스트 서명과 신뢰 경계**: 기존 승인 매니페스트 서명은 이미지·명령·마운트를 고정한다. 장치 실행기는 게이트웨이가 발행한 작업을 신뢰하며, 로컬 격리는 침해된 게이트웨이를 막지 않는다. 작업별 별도 키·1회용 서명 증명은 만들지 않는다(F1 판단 정본).
- **이미지 공급망**: F3 판단 정본이 C10의 이전 서명 필수안을 대체한다. 내부 미러 allowlist·digest 고정·사전 반입만 허용한다. OCI/cosign 서명 검증은 DEV-77로 남기고 미제공은 `확인 안 됨`으로 표시한다.
- **종료 증거**: 컨테이너·이미지 정지와 제거를 종료·중지·격리 증거(C1~C4 대상)에 넣는다. 결과 상한(256KiB)·장치 오프라인 동작을 시험에 넣는다.

## 9. 2026-10-21 반려 판단 반영

[항목별 판단](../review-1020/d175-arbitration.md)이 8장의 이전 C10 요약보다 우선한다. 침해된 게이트웨이에 대한 독립 작업 증명과 OCI 서명 검증을 DEV-73에 추가하지 않는다. 4장의 따뜻한 세션·실행기 SDK 계획은 아래 작업별 컨테이너·표준 라이브러리 구현으로 대체한다.

- 정책·승인: 서명한 `approval.generation`과 `approval.expires_at`, 활성 정책 번들 hash, 장치 epoch/policy hash, 서버별 승인 세대·철회 목록을 작업에 결속한다. claim과 실행 직전에 현재값과 대조하며, 서명만 맞는 과거 세대는 재사용하지 않는다.
- 철회·종료: 먼저 scoped admission을 닫고 queued/미시작 claim을 취소한다. 실행 중 작업은 control 감시와 별도 deadline 감시로 정지한다. 엔진의 컨테이너 부재 확인을 장치가 회신한 뒤 lifecycle/status 전환을 확정한다. source row 잠금과 DB trigger가 정지 미확인 작업이 있는 상태 전환을 거부한다. 장치가 끊기거나 엔진이 고장 나면 상태 전환은 보류되며 자동 재실행하지 않는다. 요청 접수와 완료된 전환의 시각을 혼동하지 않는다.
- 경로: 전체 부모를 `openat`/`O_NOFOLLOW`로 열고 대상 inode FD를 유지한다. 실행 직전에 전체 경로를 다시 열어 inode를 대조하며, 로컬 엔진에는 `/proc/<실행기 PID>/fd/<FD>`를 bind 원본으로 준다. 같은 호스트의 로컬 엔진만 허용한다. 실제 Podman/Docker 판본의 FD bind 수용 여부는 아직 실측하지 않았다.
- 엔진: 엔진·판본·namespace 설정이 없으면 차단한다. Podman은 userns auto와 idmap bind, Docker는 daemon remap 모드를 지정하고 실제 컨테이너 PID의 uid_map을 확인한다. 명시적으로 host 모드를 승인할 때만 `탈출 시 호스트 root`를 받아들이며 화면에도 한계를 표시한다. 이번 세션은 정적 검사만 허용돼 실측은 미완료다.
- 상한: stdout 행 256KiB·누적 1MiB·1,024행·큐 32행·읽기 20초. 계정/장치/서버 각각 동시 1개·대기 8개·60초당 생성 30개, 전체 대기/수령 작업 64개·운영 행 10,000개·결과 저장 64MiB, claim lease 5초·전체 실행 20초. 만료 claim은 queued로 되돌리지 않는다. 종료된 운영 payload는 5분 뒤 정리하되 dispatch/감사 증거는 별도로 남긴다.
- 관찰·원장: 관찰 장치는 신청 행에 compare-and-set으로 한 번 채우고 관리자는 읽고 승인한다. 이후 heartbeat 순서로 바꾸지 않는다. 실제 호출 장치의 요청 도구 계약을 재대조한다. job UUID·request UUID·claim/시작/완료/정지 시각·상태·결과 hash를 decision client와 append-only local_job_events로 연결한다. 미수령은 NOT_EXECUTED(`confirmed_not_executed`), 수령 후 미확인은 UNCONFIRMED(`uncertain`)다.

코드·시험·한계와 원시 출력은 [재작업 근거](../dev73-rework/README.md)와 [보고서](../../status/reports/2026-10-21-dev73-rework.md)를 따른다. 컨테이너 외부 연결 0·전환 뒤 실행 0은 아직 실기기에서 입증하지 않았다. 새 적대 검토 뒤에만 배포·PJ1 검증으로 진행한다.
