# DEV-73 승인된 로컬 MCP 격리 실행 설계 (D-175)

- 상태: 설계 초안(2026-10-20, Claude 레인). 적대 검토(luna) 후 구현. Linux만, Windows는 [방향 갱신](README.md) 1장 관용.
- 기준 commit: `5b5a134`(main). 근거: 방향 갱신 3장 DEV-73, MCP 공식 Local Server Security(격리·원격 우선·자격 분리), M05 제8항, TC260 4.2.3(a).
- 완료 조건: 승인 매니페스트 밖 로컬 실행 0, 컨테이너의 외부 연결 0, 판정·원장이 원격 호출과 같은 형식.

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
seccomp·AppArmor는 podman 기본 프로필. 이미지는 실행기가 digest로만 당긴다(태그 금지, `--pull=never`로 실행 시점 재해석 차단).

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
- **매니페스트 서명**: 게이트웨이가 탈취되면 모든 장치의 root 실행기를 움직일 수 있다. 매니페스트는 게이트웨이에 없는 승인 서명 키(오프라인 관리)로 서명하고, 실행기가 키트에 고정된 공개키로 검증한다. 작업 본문은 그 매니페스트 서버에 보내는 stdin JSON-RPC 메시지 하나만 허용한다(명령·마운트·이미지는 작업이 바꿀 수 없다).
- **이미지 서명 필수**: 로컬 실행 이미지는 자체 서명(cosign)을 필수로 한다. DEV-77의 `미제공=표시만`은 적용하지 않는다. digest 고정·`--pull=never`·내부 미러에서만 받는다.
- **종료 증거**: 컨테이너·이미지 정지와 제거를 종료·중지·격리 증거(C1~C4 대상)에 넣는다. 결과 상한(256KiB)·장치 오프라인 동작을 시험에 넣는다.

## 9. 1차 구현 (2026-10-20, 브랜치 `10/20-dev73-impl`)

| 부분 | 위치 | 내용 |
| --- | --- | --- |
| 작업 채널 | `gateway/app/local_jobs.py`, `lifecycle_tables.sql` `local_jobs` | `upstream.session`이 `local:<id>` 주소에서 `LocalClient`를 돌려준다. `_call_upstream`의 계약 재확인·입력 검증·철회·관리형 확인·출력 통제·원장은 원격과 같은 코드다. 작업은 호출 토큰의 `device_id`에만, 관찰(등록 전 discover)은 신청자의 활성 관리형 PC에만 간다. 수령 전 만료=미실행(`NotStarted`), 수령 뒤 무응답=결과 불명(`TimeoutError`). |
| 장치 API | `main.py` `GET/POST /api/endpoint/local-jobs` | 장치 자격(`enforcement`)만. 다른 장치의 작업·결과는 거부, 1회 점유(`FOR UPDATE SKIP LOCKED`), 결과 1MiB 상한. |
| 서명 | `field/sign-local-manifest.py`, `local_jobs.verify`, `local-runner.signed` | Ed25519. 개인 키는 승인자 PC에만. 작업 행이 매니페스트·서명을 함께 실어 가고, 실행기는 설치 때 고정한 공개키(`config.json` `manifest_pubkey`)로만 확인한다. 게이트웨이도 `LOCAL_MANIFEST_PUBKEY`로 등록 때 확인한다. |
| 실행기 | `endpoint-agent/local-runner.py`, `managed-linux.py serve` 스레드 | podman 또는 docker. `--network=none --read-only --cap-drop=ALL --security-opt=no-new-privileges --pull=never --pids-limit --memory --user <관리 계정 UID>`, 마운트는 홈 아래 실경로(심볼릭 링크·점 디렉터리 거부). stdio JSON-RPC는 표준 라이브러리로 직접(루트 서비스 의존성 최소), 서버가 거는 sampling·roots·elicitation 요청은 거부. 정책에서 빠지거나 바뀐 매니페스트의 컨테이너는 정지, 관찰용 세션은 유휴 60초 뒤 정지. |
| 등록 | `core.register_server`·`discover_for_registration`, 콘솔 등록 창 「PC 격리 실행 매니페스트」 | 저장소 신청만. 서명 묶음(`{"manifest","signature"}`)을 붙이면 주소가 `local:<server_id>`로 정해지고 서버 ID는 매니페스트 값으로 고정된다. |

시험: 격리 PG 랩 `local_jobs_pg_check.py` 10/10, 단위 `local_run_manifest_check.py` 5/5(규칙·서명·실행 명령·링크 거부).

### 알려진 한계(1차)

- 이미지는 승인 커밋에서 직접 빌드하지 않는다(예: `mcp/filesystem`은 Docker가 빌드한 공개 이미지). 자동 검사 커밋과 실행 이미지의 연결은 기록만 하며, 기기 빌드(DEV-38 레시피)·내부 미러·cosign 서명 필수(C10 §8)는 2차.
- 공개키는 설치 때 키트로 들어오므로 설치 시점의 게이트웨이를 믿는다(trust on install). 이후 정책으로는 바꿀 수 없다.
- 네트워크 없음이라 호스트 앱에 붙는 서버(GhidraMCP 브리지는 Ghidra의 로컬 HTTP에 접속)와 웹을 여는 서버(Playwright)는 기능이 막힌다. 이 유형의 허용은 별도 결정이 필요하다.
- 실행기는 장치당 작업을 순서대로 처리한다(동시 호출은 대기). 게이트웨이는 결과 행을 50ms 간격으로 확인한다.
- Windows 미구현(방향 갱신 1장 관용).
