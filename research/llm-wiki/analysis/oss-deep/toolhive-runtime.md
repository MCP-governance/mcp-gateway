# ToolHive 런타임 경로 분석 — DEV-38

## 1. 요약

- ToolHive는 MCP 컨테이너 실행·감독과 HTTP 전송 프록시 계층이다. 이 문서는 CLI/Docker 경로를 중심으로 생성·시작·정지·삭제·재조정, 이미지 결정, 격리, stdio 브리지, 실패 처리를 추적한다. 근거: `T/cmd/thv/app/run.go:213-264`, `T/pkg/runner/runner.go:477-508`, `T/pkg/transport/stdio.go:212-270`.
- 수명 주기·이미지 결정·Docker 격리 적용·기본 stdio 브리지·선택한 실패 분기는 **L3 정적 경로 분석**이다. 외부 permissions 구현, OIDC 검증 내부, Kubernetes 전체 reconcile은 **L2/미독 포함**이다. 실행·독립 효과를 확인한 L4는 없다.
- DEV-38 첫 구현의 선택은 **자체 최소 실행기**다. 고정 MarkItDown 레시피와 기존 승인·등록 경로를 연결한다. ToolHive의 재조정·오류 분리 패턴은 설계 참고로 사용한다. 이는 아래 코드 대조에 근거한 설계 판단이며 구현 완료 판정이 아니다.
- ToolHive의 기본 허용 생성 gate, 경고 후 진행하는 이미지 검증·초기화 확인, 하네스 직접 등록을 MINT 승인·계약·감사로 간주하면 안 된다. 근거: `T/pkg/runner/policy_gate.go:21-38`, `T/pkg/runner/retriever/retriever.go:344-389`, `T/pkg/runner/runner.go:658-682`.

## 2. 고정 정보

확인일: 2026-10-15. 작업 ID: `toolhive-runtime`. 원본 코드는 읽기만 했다. 외부 저장소의 설치·빌드·스크립트·시험은 실행하지 않았다.

| 표기 | 기준 |
| --- | --- |
| `T/` | `C:/Users/bobysg/bob/프로젝트/ref-src/toolhive/`, origin `https://github.com/stacklok/toolhive.git` |
| ToolHive 판본 | 로컬 Git HEAD와 `v0.54.0^{commit}` 모두 `1ce13bbbbbe1ed9a3f40fea03ed1a42533f04cea`; shallow=true, `status --short` 출력 없음 |
| 유지보수 관측 | HEAD의 Git 기록은 2026-10-14 `Release v0.54.0 (#6823)`. 최신 보안 공지·유지보수 SLA를 검증한 것은 아님 |
| `M/` | 이 MINT 저장소. 시작 HEAD `8f962f5dbfede539dff6d4bf42449bca617f6527`; 시작 브랜치 `10/15-wbs-implementation` |
| `W/` | `../ref-src/ms-wassette/`, origin `https://github.com/microsoft/wassette`, HEAD `742ebb7236273dad2d88c415eabe872d3b95dff9`; 상태 출력 없음 |
| 라이선스 | ToolHive Apache-2.0: `T/LICENSE:1-9`, 소스 SPDX `T/pkg/runner/runner.go:1-2`. 루트 NOTICE 파일은 정적 미발견. 전이 의존성·컨테이너 이미지 전체 재배포 검수는 미실행 |
| 주요 의존성 | Moby API/client, toolhive-core `v0.0.52`, toolhive-catalog `v0.20261013.0`: `T/go.mod:45-46`, `T/go.mod:70-72` |
| 공개 스킬 검토 | `T/skills/toolhive-cli-user/SKILL.md:1-65`, 판본 0.4.0·Apache-2.0. 운영 문서로만 읽었고 명령 지시를 실행하지 않음 |

Git 판정은 `git -c safe.directory=<원본 절대경로> -C <원본> …`의 읽기 명령 결과다. 전역 safe.directory는 변경하지 않았다.
원격 HEAD 재조회는 GitHub 연결 실패, 공식 태그·옛 commit 웹 조회는 cache miss였다. 로컬 태그의 원격 진위·서명은 미확인이다.
작업 브랜치 `10/15-toolhive-runtime` 생성은 공용 Git 디렉터리의 ref lock 쓰기 권한 거부로 실패했다. 커밋·통합 브랜치 갱신은 하지 않았다.
사용자 지정에 따라 이 파일만 작성한다. 현황·백로그·보고서·DECISIONS와 기존 카드는 수정하지 않는다.

실제로 읽은 주요 파일과 범위는 다음과 같다. 표에 적은 범위는 선별 구간을 포함하며 저장소 전체 정독을 뜻하지 않는다.

| 범위 | 파일·대략 행 |
| --- | --- |
| CLI 입구·기본값 | `T/cmd/thv/app/run.go:172-354`, `restart.go:22-175`, `run_flags.go:184-311,390-459` |
| 실행·정책·설정 | `T/pkg/runner/runner.go:216-827,871-1085`, `config.go:60-125,367-374,650-730,834-857`, `config_builder.go:909-1047,1094-1527`, `policy_gate.go:11-66` |
| 이미지·빌드 | `T/pkg/runner/retriever/retriever.go:63-410`, `protocol.go:35-223,231-365,399-650`, `pkg/container/images/image.go:19-64`, `registry.go:57-255` |
| 빌드 템플릿 | `T/pkg/container/templates/runtime_config.go:55-150,229-279`, `uvx.tmpl:1-160`, `npx.tmpl:1-122`, `go.tmpl:1-126` |
| 수명·상태 | `T/pkg/workloads/manager.go:141-147,371-808,897-976,1086-1134,1175-1244,1298-1566`; `statuses/file_status.go:30-75,185-210,486-519,605-638,920-1007`; `pkg/state/local.go:22-249`, `runconfig.go:16-136` |
| Docker 격리·재조정 | `T/pkg/runtime/setup.go:45-181`, `pkg/container/docker/client.go:173-372,707-794,866-899,1007-1036,1109-1222,1513-1599,1669-1772`; `networkproxy.go:100-110`, `squid.go:103-185,247-407` |
| 브리지·인증·하네스 | `T/pkg/transport/stdio.go:212-395,444-578,690-797`; `proxy/streamable/streamable_proxy.go:35-110,266-390,542-701,1026-1093,1637-1669`; `pkg/auth/utils.go:62-95`, `local.go:20-51`, `middleware.go:52-88`, `token.go:1302-1373`; `pkg/client/manager.go:144-312`, `config.go:519-527,834-842,920-928,1335-1379`, `config_editor.go:67-178` |
| secret·보조 경로 | `T/pkg/secrets/factory.go:216-250,347-382`, `fallback.go:13-106`, `environment.go:25-64`; `pkg/api/v1/workload_service.go:60-107,190-210`; `cmd/thv-operator/controllers/mcpserver_controller.go:246-300,460-650,1895-1918` |
| MINT 대조 | `M/full_stack_lab/supply_chain/intake_worker.py:240-268,365-387`; `gateway/app/agent_service.py:906-957,1205-1255,1374-1404`; `gateway/app/core.py:500-575,619-670`; `M/full_stack_lab/compose*.yaml`의 서비스·망·게시 설정; `M/research/llm-wiki/analysis/wbs-1015/e2e-clean.json:62-77` |
| Wassette 대조 | `W/README.md:15-24,78`, `Cargo.toml:7-8,41`, `crates/wassette/src/runtime_context.rs:23-60`, `wasistate.rs:108-145`, `lib.rs:1249-1303`, `http.rs:189-198` |

위 표의 MINT 축약 `gateway/…`는 `full_stack_lab/gateway/…`다. 시험의 실제 읽기 범위는 §5에 구분한다.

| 원본 파일 | SHA-256 |
| --- | --- |
| `T/LICENSE` | `269187c8b1d9569c2a3a381eeb428150f96b2a2c93e168be7ce45e1247853168` |
| `T/pkg/runner/runner.go` | `b54729d19f817754e4a59b01af9bb59ecc9350578c482fab277287a82e902f2a` |
| `T/pkg/workloads/manager.go` | `f1ba96ad155010edcad5fc729dd61bd873ff389a502a002fbcfee6c992b557b1` |
| `T/pkg/runner/protocol.go` | `d245ea228fdfd5d4f82d30fd6c51cb0e77c49e1b00ce6478b872b434764b3de8` |
| `T/pkg/container/docker/client.go` | `091b75ee5f14a208e646bcd8ca3b334311cc5a696d6c6f4f5f4d4de9b316dc63` |
| `T/go.mod` | `cb6366691d3b3808132d7f0ddd2359aa6973009dde0fa3943549fdaccc734fb5` |
| `T/skills/toolhive-cli-user/SKILL.md` | `08f16f00867d57d1ba92d69d9a254d0ecec80de7c8b3df45f8ee10cd2f035a08` |

## 3. 경로 추적

### 3.1 생성·시작·정지·삭제·재조정 — CLI/Docker L3

CLI 관리 입구의 권한 경계는 명령을 실행하는 OS 사용자와 컨테이너 엔진 접근권이다. HTTP MCP 호출 인증은 §3.4의 별도 경로다. CLI의 create gate 기본값은 허용이다(`T/cmd/thv/app/run.go:213-250`, `T/pkg/runner/policy_gate.go:21-38`).

| 단계 | 함수·근거 | 상태 저장소 | 실패 시 결정 |
| --- | --- | --- | --- |
| 생성 입구 | `runSingleServer`: 존재 확인→설정 빌드, `T/cmd/thv/app/run.go:213-244` | status/runtime 조회 | 같은 이름 존재 시 오류. status=error는 존재하지 않는 것으로 취급: `T/pkg/workloads/manager.go:371-385` |
| 생성 정책·저장 | `EagerCheckCreateServer`→`SaveState`, `T/cmd/thv/app/run.go:246-257` | RunConfig JSON | gate·저장 실패면 spawn하지 않음. MINT 독립 승인 검사는 이 기본 gate가 제공하지 않음 |
| 시작 | `RunWorkloadDetached`→`spawnDetached`, `T/pkg/workloads/manager.go:680-800` | status=starting, PID, 로그 | secret 사전 검사 실패면 spawn 없음. 시작 명령 반환은 ACTIVE·계약 검증 완료가 아님 |
| 자식 실행 | 현재 실행 파일을 `start <basename> --foreground`로 재실행, `T/pkg/workloads/manager.go:745-757`; CLI `start`는 `RestartWorkloads`, `T/cmd/thv/app/restart.go:22-31,78-88` | 저장된 RunConfig | 자식이 상태에서 다시 읽어 실행. 부모 취소로 자식이 자동 종료되는 구조가 아님 |
| 실행 정책·엔진 | `Runner.Run`의 gate→`runtime.Setup`→`DeployWorkload`, `T/pkg/runner/runner.go:464-500`, `T/pkg/runtime/setup.go:130-145` | Docker 컨테이너·label·망 | 생성 오류 반환. 생성 후 프록시 단계 실패의 전체 자원 롤백은 별도 확인 필요 |
| 재조정 | `createContainer`→`handleExistingContainer`, `T/pkg/container/docker/client.go:1513-1537,1140-1177` | 같은 정확한 컨테이너 이름의 inspect 결과 | 설정 일치면 재사용·필요 시 start, 불일치면 해당 컨테이너 삭제·재생성 |
| 상태 반영 | `Runner.Run`, `T/pkg/runner/runner.go:715-777`; `validateRunningWorkload`, `T/pkg/workloads/statuses/file_status.go:920-967` | status JSON·PID와 runtime | running 저장 실패는 오류. 조회 중 runtime 불일치는 unhealthy로 기록 |
| 정지 | `StopWorkloads`→`stopContainerWorkload`, `T/pkg/workloads/manager.go:411-451,507-531` | stopping→stopped, RunConfig 보존 경로 | 없는/이미 멈춘 컨테이너는 경고 후 반환. stop과 delete를 구분 |
| 삭제 | `DeleteWorkloads`→`deleteContainerWorkload`, `T/pkg/workloads/manager.go:1207-1223,926-974` | 컨테이너 제거→proxy 정지→설정·status 정리 | runtime 제거 오류는 반환. 설정·client 정리 일부 오류는 경고 후 계속: `T/pkg/workloads/manager.go:1175-1198` |
| 재시작·orphan | `maybeSetupContainerWorkload`, `T/pkg/workloads/manager.go:1428-1542` | label의 baseName·PID·RunConfig | running+감독자 생존이면 no-op. 감독자 사망·상태 불일치면 정지·정리→설정 reload→gate→재시작 |

RunConfig는 XDG StateHome 아래 `toolhive/runconfigs`, status는 XDG data의 `toolhive/statuses`에 분리된다(`T/pkg/state/local.go:22-49`, `T/pkg/state/factory.go:12-24`, `T/pkg/workloads/statuses/file_status.go:30-63`).
RunConfig 저장은 임시 파일 sync·rename이다. exclusive 생성 API도 있지만 CLI의 `SaveRunConfig`는 일반 `GetWriter`를 쓴다(`T/pkg/state/local.go:108-136,155-180`, `T/pkg/state/runconfig.go:80-108`).
status 갱신에는 파일 잠금이 있고 PID reset에는 기대 PID 대조가 있다. 이것은 전체 생성 작업의 generation fencing과는 별개다(`T/pkg/workloads/statuses/file_status.go:486-519,605-638`).
**추론:** 같은 이름의 동시 CLI 작업에서 Docker 이름 제약만으로 source·attempt·endpoint의 소유권까지 보장한다고 볼 수 없다. 다중 감독자·RunConfig 덮어쓰기 반례는 미재현이다.
Docker `unless-stopped`와 ToolHive의 재시도 감독이 공존한다(`T/pkg/container/docker/client.go:1705-1707`, `T/pkg/workloads/manager.go:535-648`). 호스트 재부팅 뒤 모든 고아를 자동 복구하는 독립 daemon 경로는 이번 CLI 추적에서 입증하지 않았다.

Kubernetes에는 별도 `MCPServerReconciler.Reconcile`이 있다. 삭제 timestamp→finalizer, Deployment/Service 변경 재조정, StatefulSet·Service·RunConfig ConfigMap 정리가 보인다(`T/cmd/thv-operator/controllers/mcpserver_controller.go:246-300,592-648,1895-1918`). 이 경로의 전체 RBAC·Pod 생성·복구는 L2이며 Docker 수명 분석의 L3에 합산하지 않는다.

### 3.2 이미지 참조·digest·소스 빌드 — 선택 경로 L3

| 단계 | 함수·근거 | 상태 저장소 | 실패 시 결정 |
| --- | --- | --- | --- |
| 입력 결정 | `BuildRunnerConfig`→`ResolveMCPServer`, `T/cmd/thv/app/run_flags.go:419-445`, `T/pkg/runner/retriever/retriever.go:69-130` | 입력 URI·registry metadata | registry 이름, 직접 image, protocol scheme 분기 |
| registry·직접 image | `handleRegistryLookup`, `T/pkg/runner/retriever/retriever.go:218-253` | metadata.Image 또는 입력 문자열 | lookup 실패는 직접 image로 취급. MINT 승인 소스 여부를 이 동작으로 판단하면 안 됨 |
| protocol build | `HandleProtocolScheme`→`BuildFromProtocolSchemeWithName`, `T/pkg/runner/protocol.go:35-94` | uvx/npx/go 패키지·레시피 | 파싱·템플릿·빌드 오류 반환 |
| 빌드 전 검증 | `createTemplateData`, `T/pkg/runner/protocol.go:134-181` | 패키지 이름·build args·runtime 설정 | 이름·인자 검증 및 secret 해석 실패면 중단 |
| 실제 빌드 | `buildImageFromTemplateWithName`→`ImageManager.BuildImage`, `T/pkg/runner/protocol.go:585-650`; `buildDockerImage`, `T/pkg/container/images/registry.go:179-239` | Docker context tar, image tag | ImageBuild 오류·출력 처리 오류 반환. 반환값은 image 이름이며 OCI digest가 아님 |
| 이미지 검증 | `VerifyImage`, `T/pkg/runner/retriever/retriever.go:344-389` | registry provenance; 외부 verifier | 기본 warn은 provenance 없음·검증기 장애·검증 실패에도 진행. enabled는 오류 반환 |
| 정책·pull | `EnforcePolicyAndPullImage`, `T/pkg/runner/retriever/retriever.go:164-193` | RunConfig·로컬 image cache | gate 거부면 pull 전 차단. 로컬 빌드·Kubernetes는 이 pull 생략 |
| 실행 연결 | `runtime.Setup`→Docker Config.Image, `T/pkg/runtime/setup.go:130-145`, `T/pkg/container/docker/client.go:1684-1695` | 저장 image 문자열·실제 Docker 실행물 | digest 참조를 사용할 수 있으나 모든 입력을 digest로 강제 변환하는 경로는 이 추적에서 미발견 |

CLI image 검증 기본은 warn이며 API service도 warn이다(`T/cmd/thv/app/run_flags.go:247-249`, `T/pkg/api/v1/workload_service.go:60-75`). digest 지정 pull은 지원하고 daemon의 manifest digest 등록을 사용한다(`T/pkg/container/images/registry.go:74-96,133-151`). **지원**과 **강제 고정**은 다르다.
재사용 비교는 요청 Config의 image 등 설정을 비교하는 구조다. 승인 source tree와 runtime image의 내용 결속 증거는 별도 필요하다(`T/pkg/container/docker/client.go:1109-1177`).

| 빌드 종류 | 실제 획득·산출물·한계 |
| --- | --- |
| uvx | `uv tool install`로 패키지 설치, `@`를 `==`로 변환. 전이 의존성 제약 BuildWith는 선택 사항: `T/pkg/container/templates/uvx.tmpl:71-82`, `runtime_config.go:68-74` |
| npx | 빌드 중 `npm install --save <package>`, 최종 node_modules·생성 package-lock 복사: `T/pkg/container/templates/npx.tmpl:55-60,101-110`. 생성 후 lock 보유는 사전에 승인한 lock 입력과 다름 |
| go | 버전 미지정이면 `@latest`, local은 `COPY .` 후 go build: `T/pkg/container/templates/go.tmpl:44-73`. local 경로 지원은 Go에만 켜짐: `T/pkg/runner/protocol.go:149-155` |
| base image | 기본 builder는 `golang:1.27-alpine`, `node:24-alpine`, `python:3.14-slim`의 tag: `T/pkg/container/templates/runtime_config.go:254-267`. Go 최종 Alpine은 digest 고정: `T/pkg/container/templates/go.tmpl:76-77`. 모든 stage가 무고정이라는 주장도 틀림 |
| 산출 식별 | 기본 이름은 `toolhivelocal/<종류>-<패키지>:<초 단위 시각>`, 사용자 이름도 허용: `T/pkg/runner/protocol.go:575-580,626-650`. **추론:** 같은 초·동일 패키지의 동시 빌드는 tag 충돌 반례가 필요 |
| local context | 입력 경로 존재 확인 후 현재 작업 디렉터리를 context로 사용하며 기존 Dockerfile이 있으면 그대로 사용: `T/pkg/runner/protocol.go:407-446,473-479`. 승인 archive만 빌드한다는 보장이 아님 |

**중요한 순서:** protocol build는 `ResolveMCPServer`에서 일어나고 생성 gate는 그 뒤 설정 빌드 후 호출된다(`T/pkg/runner/retriever/retriever.go:80-91`, `T/cmd/thv/app/run_flags.go:419-455`). MINT는 승인·만료 확인을 실제 빌드보다 앞에도 둬야 한다.
BuildEnv는 Dockerfile ENV로 렌더링되고 auth 파일은 context에 써서 COPY한다. Dockerfile 전문을 debug에 기록하는 경로도 있다(`T/pkg/container/templates/npx.tmpl:3-6,41-43`, `uvx.tmpl:56-59`, `T/pkg/runner/protocol.go:527-571,641-646`). **추론:** build cache·중간 layer·debug 로그에 자격 잔존 가능성이 있다. 최종 stage에 복사하지 않는 것만으로 비밀 폐기를 입증하지 못한다.

### 3.3 permission profile·망·mount·secret — Docker 적용 L3, 외부 profile 정의 L2

| 단계 | 함수·근거 | 상태 저장소 | 실패 시 결정 |
| --- | --- | --- | --- |
| profile 선택 | `loadPermissionProfile`: 객체→이름/파일→registry→BuiltinNetworkProfile, `T/pkg/runner/config_builder.go:1382-1410` | RunConfig.PermissionProfile | custom profile 읽기 오류 반환. builtin 내용은 외부 toolhive-core 구현이므로 전문 미독 |
| 망 검증 | `reconcileNetworkIsolation`, `T/pkg/runner/config_builder.go:1342-1379` | IsolateNetwork·profile.Network.Mode | bridge 유지, none은 격리 flag 해제. host/custom+명시 격리는 오류, 기본 격리는 경고 후 해제 |
| 엔진 적용 | `getPermissionConfigFromProfile`→`createMcpContainer`, `T/pkg/container/docker/client.go:866-899,1684-1707` | Docker HostConfig | cap-drop ALL, SecurityOpt label:disable, Privileged는 profile 값. 임의 이미지의 UID·read-only rootfs·자원 제한은 이 생성 코드에서 설정 미발견 |
| 격리 배선 | `DeployWorkload`, `T/pkg/container/docker/client.go:253-327,341-356,1731-1746` | 내부 bridge, DNS·egress·필요 시 ingress 보조 컨테이너 | network/gateway/DNS/egress 오류 반환. MCP는 격리 시 내부 network만 연결 |
| outbound 판정 | 기본 Squid 선택, `T/pkg/container/docker/networkproxy.go:100-110`; ACL 생성 `squid.go:247-274,324-353` | 생성 squid.conf·컨테이너 mount | gateway deny가 profile allow보다 앞. AllowHost·AllowPort를 함께 주면 AND; 둘 다 없고 allow-all도 아니면 마지막 deny |
| proxy 주입 | `SetupEgress`→`addEgressEnvVars`, `T/pkg/container/docker/squid.go:371-383`, `client.go:1760-1771` | HTTP(S)_PROXY·NO_PROXY | proxy 미지원 raw TCP가 같은 허용 호스트 정책으로 동작한다고 볼 수 없음 |
| mount | `processVolumeMounts`→read/write 변환, `T/pkg/runner/config_builder.go:1445-1526`, `T/pkg/container/docker/client.go:707-794` | profile Read/Write→bind mount | CLI volume 오류·없는 source는 반환. 런타임 변환의 잘못된 선언·resource URI는 경고 후 생략 |
| secret | `Runner.Run`→`CreateProvider`→`WithSecrets`, `T/pkg/runner/runner.go:268-310`, `T/pkg/runner/config.go:670-724` | provider 참조→메모리 EnvVars→Docker Config.Env | provider 생성·실제 secret 해석 오류는 실행 전 반환. 참조 유지와 실제 주입값을 구분 |
| 기록·정리 | RunConfig는 초기 secret 해석 전에 저장, `T/cmd/thv/app/run.go:253-257`; Squid 접근 로그는 stdout, `T/pkg/container/docker/squid.go:309-321` | 설정·status·운영 로그 | MINT append-only 판정 원장과 같은 무결성·주체 결속으로 간주하지 않음 |

격리 기본 flag는 true, Docker gateway 허용은 false다(`T/cmd/thv/app/run_flags.go:302-311`). custom 기본 profile이 network인 것과 목적지 제한이 있는 것은 별개다. upstream E2E도 기본 profile을 allow-all로 설명하며, nil 또는 InsecureAllowAll인 Squid 설정은 gateway deny 뒤 allow-all을 만든다(`T/test/e2e/network_isolation_test.go:148-151`, `T/pkg/container/docker/squid.go:257-274`).
gateway 주소 집합은 배포 시 snapshot이다. 이후 생긴 bridge는 재배포가 필요하다(`T/pkg/container/docker/client.go:263-268`). DNS 재바인딩·redirect·외부의 사설 주소 전부 차단을 이 snapshot만으로 입증하지 못한다.
Squid 보조 컨테이너는 MCP의 cap-drop ALL과 다르게 CAP_SETUID/SETGID 추가·CapDrop=nil·label:disable 설정을 쓴다(`T/pkg/container/docker/squid.go:155-164`). 전체 실행 경계의 권한·이미지 검사에는 보조 컨테이너도 포함해야 한다.

secret provider는 encrypted·1Password·environment로 분기하고 non-environment에는 기본 환경변수 fallback이 붙는다. `TOOLHIVE_DISABLE_ENV_FALLBACK=true`로 해제한다(`T/pkg/secrets/factory.go:216-250,374-382`).
fallback은 not-found에만 적용하며 다른 오류는 반환한다. 외부 오류는 일부 문자열로 not-found를 판단한다(`T/pkg/secrets/fallback.go:31-52,96-106`). **추론:** 비밀 삭제 뒤 옛 환경변수가 남으면 재시작 시 같은 이름이 다시 해석될 수 있다. provider 삭제와 실제 자격 철회는 별개다.
일반 secret은 EnvVars에 주입된다(`T/pkg/runner/config.go:675-690`, `T/pkg/container/docker/client.go:1685-1689`). 실행 중 provider 값이 바뀌었다고 기존 프로세스 환경이 자동 갱신되는 경로는 선택한 코드에서 정적 미발견이다.
추가 검토 후보: RemoteAuth 토큰 참조 저장은 RunConfig를 얕게 복사해 다시 SaveState한다. EnvVars가 JSON 직렬화 대상이고 앞서 secret이 합쳐지므로, 일반 secret과 RemoteAuth를 같이 쓸 때 저장 파일에 값이 남을 가능성을 검사해야 한다(`T/pkg/runner/config.go:124-125,367-374,675-690`, `T/pkg/runner/runner.go:940-947,967-972,1018-1019`). **정적 추론·미재현**이며 기본 로컬 MCP 실행에서 누출을 관측했다는 뜻은 아니다.

### 3.4 stdio↔HTTP·인증·클라이언트 자동 등록 — 기본 브리지 L3

| 단계 | 함수·근거 | 상태 저장소 | 실패 시 결정 |
| --- | --- | --- | --- |
| 브리지 준비 | runtime 배포→transport 생성·Start, `T/pkg/runner/runner.go:477-543,633-637`; `StdioTransport.Start`, `T/pkg/transport/stdio.go:224-268` | 컨테이너 attach stdin/stdout·proxy | attach·proxy·monitor 구성 오류 반환 |
| HTTP 입구 | `/mcp`에 middleware 적용, `T/pkg/transport/proxy/streamable/streamable_proxy.go:266-306` | HTTP listener·session manager | CLI 기본 bind는 loopback, proxy-mode는 streamable-http: `T/cmd/thv/app/run_flags.go:184-195` |
| 인증 | core auth middleware→`GetAuthenticationMiddleware`, `T/pkg/runner/config_builder.go:909-923`, `T/pkg/auth/middleware.go:52-88`, `utils.go:67-95` | 요청 context Identity | OIDC 있으면 validator 구성, 없으면 모든 요청에 synthetic local-user 부여. loopback 자체를 직원 인증으로 세지 않음 |
| 토큰·선택 권한 | `TokenValidator.Middleware`, `T/pkg/auth/token.go:1302-1317`; 선택 authz 구성, `T/pkg/runner/config_builder.go:980-1010` | bearer·claims·권한 설정 | 토큰 추출/검증 실패는 downstream 미호출. JWT/JWKS 내부·Cedar 판정 전부는 미독 |
| 요청 실행 | `handlePost`→`handlePostMessage`→`doRequest`→`SendMessageToDestination`, `T/pkg/transport/proxy/streamable/streamable_proxy.go:542-618,652-701,1026-1067,378-385` | session·request ID별 waiter, 메모리 channel | 잘못된 JSON/세션은 오류, 대기 timeout은 504, channel 전송 실패는 오류 |
| stdio 전달 | `processMessages`→`sendMessageToContainer`, `T/pkg/transport/stdio.go:444-478,720-737` | 현재 stdin, JSON-RPC+newline | 쓰기 오류는 로그. HTTP 대기 오류와 외부 효과 여부를 구분해야 함 |
| 결과 | stdout→JSON decode→`ForwardResponseToClients`→waiter→ID 복원, `T/pkg/transport/stdio.go:690-716`, `T/pkg/transport/proxy/streamable/streamable_proxy.go:1046-1067` | 원래 ID 복원 map·응답 channel | 파싱 오류는 로그 후 해당 메시지 폐기. 반환 실패가 실행 취소를 뜻하지 않음 |
| readiness·등록 | `Runner.Run`, `T/pkg/runner/runner.go:641-682` | 로컬 serverURL·client config | stdio 초기화 probe 생략, 비stdio probe는 최대 5분 실패해도 경고 후 client 등록 진행 |
| 하네스 변경 | `AddServerToClients`→`updateClientWithServer`→`Upsert`, `T/pkg/client/manager.go:168-184,266-311`, `config.go:1335-1379` | 실행 사용자 HOME의 등록 client 설정 | group 등록 client만, group 없으면 전역 등록 client. 개별 갱신 실패는 경고 후 계속 |
| 감사·종료 | audit는 선택 구성, `T/pkg/runner/config_builder.go:1014-1041`; transport Stop, `T/pkg/transport/stdio.go:314-376` | 선택 audit·운영 로그·설정 | HTTP Shutdown·container stop 오류 일부는 경고 후 nil 반환. 실제 종료 효과를 별도로 확인해야 함 |

MCP 자동 등록은 Claude Code `~/.claude.json`의 mcpServers, Gemini `~/.gemini/settings.json`, Codex `~/.codex/config.toml`의 mcp_servers 같은 사용자 설정을 수정한다(`T/pkg/client/config.go:519-527,834-842,920-928`). JSON updater는 파일 잠금·원자 저장을 사용한다(`T/pkg/client/config_editor.go:85-128`).
이 MCP 등록 호출은 server URL·transport를 갱신하는 경로다. 별도의 LLM gateway 설정 기능이 코드에 있어도 이 호출이 LLM 설정까지 변경한다고 확대하지 않는다(`T/pkg/client/config.go:1335-1379`).
**MINT 적용 판단:** 솔루션 기기 HOME만 수정하면 PJ1 설정을 원격 변경한 것이 아니다. 반대로 PJ1에서 실행하거나 직원 HOME을 공유하면 MINT 밖 직접 endpoint가 들어갈 위험이 있다. 런타임 계정에 직원 설정 파일 접근을 주지 않고 자동 등록을 사용하지 않는다.
일반 stdio bridge는 HTTP credential header를 프로세스 토큰으로 전달하는 기능과 다르다. HTTP 원격 프록시의 모든 자격 경계를 동일 보장으로 확장하지 않는다. 별도 strip-auth는 Authorization·Cookie·Proxy-Authorization을 제거하며 적용 검증 조건이 있다(`T/pkg/transport/middleware/strip_auth.go:15-40`, `T/pkg/runner/middleware.go:591-635`).

## 4. 실패·경합·복구 결정표

여기서 closed/open은 각 검증·활성화 경계에 대한 분류다. 장애로 응답이 없다는 사실만으로 업무 부작용 0을 뜻하지 않는다.

| 조건 | 코드 동작·근거 | 경계 판정 | 미확인·MINT 요구 |
| --- | --- | --- | --- |
| 일반 image pull 실패 | latest는 timeout/취소 외 오류일 때 로컬 image 있으면 계속. 비latest는 로컬 우선: `T/pkg/runner/retriever/retriever.go:261-322` | 가용성 fallback, digest 승인 보장 아님 | tag 변경·cache 오염·폐기 후 재사용 |
| pull timeout/취소 | 오류 반환: `T/pkg/runner/retriever/retriever.go:136-145,269-276` | 해당 pull closed | CLI 호출은 pullTimeout=0: `T/cmd/thv/app/run_flags.go:452-455`. 상위 취소·엔진 timeout 별도 |
| 서명/provenance 검증기 장애 | warn은 계속, enabled는 실패: `T/pkg/runner/retriever/retriever.go:347-389` | 기본 검증 open | MINT의 검사기 장애 차단과 다름 |
| 생성 gate 거부·장애 | 반환 오류면 생성/pull/spawn 경계에서 중단. 기본 gate는 allow-all: `T/pkg/runner/policy_gate.go:21-38`, `T/pkg/runner/runner.go:464-467` | 설정된 gate 오류는 closed | 외부 MINT 승인·OPA가 기본 배선된 것은 아님. protocol build는 gate 전 |
| 컨테이너 시작 실패 | create 후 start 오류면 force remove 시도, 정리 실패 로그: `T/pkg/container/docker/client.go:1565-1596` | 시작 실패 반환 | 제거 실패 후 orphan 잔존·다음 attempt |
| 컨테이너 크래시 | transport monitor→Stop→Runner의 restart sentinel→관리자 retry. 기본 10회, 5초부터 최대60초, 30초 안정 실행 시 budget reset: `T/pkg/transport/stdio.go:741-787`, `T/pkg/runner/runner.go:784-823`, `T/pkg/workloads/manager.go:141-146,535-640` | 자동 복구 | 재시작 때 승인·image digest·계약 유효성은 MINT가 다시 검사 |
| Docker attach 단절 | 살아 있으면 재attach와 stdout reader 교체, 최대 재시도 후 false: `T/pkg/transport/stdio.go:484-578` | 연결 복구 | 이미 보낸 쓰기의 응답 유실·중복 요청 효과 |
| HTTP proxy bind 실패 | ListenAndServe goroutine은 오류 로그, Start는 먼저 nil 반환: `T/pkg/transport/proxy/streamable/streamable_proxy.go:316-326` | readiness 엄격 closed 아님 | stdio는 probe 생략하므로 상태 running과 listener 성공 불일치 반례 필요 |
| egress/DNS 생성 실패 | 오류 반환: `T/pkg/container/docker/client.go:265-296` | 해당 배포 closed | 앞서 만든 network/sidecar의 전체 정리·재조정 |
| Squid image pull 실패 | ImageExists의 bool을 버리고 error만 확인: `T/pkg/container/docker/squid.go:120-132`; ImageExists는 daemon 실패에도 false,nil 반환: `T/pkg/container/images/registry.go:58-71` | pull 오류를 즉시 확정하지 못함 | 최종 ContainerCreate 실패까지 구분. 무조건 실행 허용이라고 단정하지 않음 |
| 실행 중 egress proxy 사망 | HTTP proxy env와 내부망은 유지되는 구조: `T/pkg/container/docker/client.go:1738-1746,1760-1771` | 직접 외부망 fallback은 이 경로에서 미발견 | 패킷·독립 수신으로 차단 검증, sidecar readiness·자동 복구는 미확인 |
| secret provider 장애 | 생성/해석 오류는 Runner에서 반환: `T/pkg/runner/runner.go:293-309` | 일반 주입 closed | provider별 timeout·회전·SDK 내부 미독 |
| secret not-found | primary not-found 때 환경변수로 대체 가능: `T/pkg/secrets/fallback.go:31-52` | 명시 fallback | 삭제 후 옛 환경값 부활. 업무 자격은 환경 fallback 해제 검토 |
| 원격 OAuth 저장소 불능 | 토큰 영속 저장 manager 오류는 경고 후 인증 시도: `T/pkg/runner/runner.go:876-915` | 영속화는 best-effort | 일반 주입 오류와 구분. 원격 OAuth 전체 경로는 L2 |
| 호출 timeout·취소 | waiter 정리·ctx 오류 반환, HTTP JSON 경로 504: `T/pkg/transport/proxy/streamable/streamable_proxy.go:679-701,1046-1067` | 응답 실패 | 이 함수는 MCP cancel·부작용 rollback을 보장하지 않음. 불확실 실행 기록 필요 |
| stop 중 호출 | proxy shutdown·stdin close·container stop: `T/pkg/transport/stdio.go:346-376` | 종료 시도 | graceful 종료 응답과 provider 자격 회수·완료된 쓰기 구분 |
| 삭제 중 늦은 supervisor 종료 | 기대 PID와 일치할 때만 reset: `T/pkg/workloads/statuses/file_status.go:486-519` | 새 PID 덮어쓰기 방어 | source/job generation의 stale 결과 반영 방어와 별개 |
| 감독자 사망·재시작 | 명시 start 시 runtime·PID·RunConfig 대조/정리: `T/pkg/workloads/manager.go:1428-1542` | 복구 경로 존재 | 호스트 reboot 후 자동 감독 부활·종료 항목 미부활은 미재현 |
| 포트를 잡은 고아 proxy | basename·process identity 확인 뒤 해당 PID 종료·대기: `T/pkg/workloads/manager.go:1086-1133` | 다른 작업 보호 검사 있음 | PID 재사용·동시 재기동은 실제 OS에서 추가 확인 |
| 다중 worker·동시 생성 | status 파일 잠금, Config atomic rename, Docker 이름 기반 재조정: `T/pkg/workloads/statuses/file_status.go:605-638`, `T/pkg/state/local.go:108-136`, `T/pkg/container/docker/client.go:1513-1537` | 작업 전체 원자성 미입증 | DB claim+generation 소유권, late completion fencing 필요 |
| cache·목적지 변경 | gateway snapshot은 배포 시점, image는 tag/local cache 사용: `T/pkg/container/docker/client.go:263-268`, `T/pkg/runner/retriever/retriever.go:293-319` | 자동 무효화 보장 아님 | 재배포·digest 변경·허용 호스트 철회 중 진행 연결 |

## 5. upstream 시험

아래는 **시험 소스의 존재·assert 확인**이다. 이번 실행 결과·upstream CI 통과 기록이 아니다. 대역 시험은 실제 OSS MCP 효과 시험과 구분한다.

| 시험·읽기 범위 | 확인 내용 | 빠진 반례 |
| --- | --- | --- |
| `TestDefaultManager_RunWorkload`, `T/pkg/workloads/manager_test.go:1103-1165` | status mock. 이름이 successful run인 조건도 실제 Runner 실패를 기대 | 실제 업무 성공·image/source 결속 |
| `TestCreateContainer_ReuseExisting_WhenConfigMatchesAndStartIfStopped`, `…_Mismatch_RemovesAndRecreates`, `T/pkg/container/docker/client_create_test.go:208-304` | fake Docker API로 재사용·불일치 재생성 assert | 같은 이름 동시 create·생성 직후 worker 사망 |
| `TestDeployWorkload_IsolatedGatewaySnapshotAndProxyOrdering`, `…_GatewayDiscoveryFailsClosed`, `T/pkg/container/docker/client_deploy_test.go:533-591` | fake ops/proxy로 내부망→snapshot→DNS→egress→MCP→ingress 순서, 탐색 오류면 MCP 미생성 | 실제 DNS/IPv6/redirect와 외부 수신0 |
| `TestVerifyImage`, `T/pkg/runner/retriever/retriever_test.go:138-217` | provenance 없음·검증기 구성 불능에서 warn/enabled 분기 | 승인 image digest 불일치·서명 후 tag 이동 |
| `TestProcessStdout_EOFWithSuccessfulReattachment`, `T/pkg/transport/stdio_test.go:334-398` | mock runtime/proxy에서 stdin/stdout 교체 assert | 실 Docker 단절 중 완료된 쓰기·응답 유실 |
| `TestCreateTempEgressSquidConf_AllowAllWhenNil`, `T/pkg/container/docker/squid_test.go:92-119` | 생성 config에서 gateway deny가 allow-all보다 앞임 | 실제 Squid 연결·DNS 재바인딩 |
| `TestFallbackProvider_GetSecret`, `T/pkg/secrets/fallback_test.go:20-138` | primary 성공, not-found fallback, provider 오류 실패 | 실제 provider 회수·실행 프로세스 환경 잔존 |
| `TestDefaultManager_orphanProxyPortCleanup`, `T/pkg/workloads/manager_test.go:2363-2480` | mock runtime/status와 portFreer seam. status 유실 시 port 정리 호출 | 실제 재부팅·PID 재사용·다른 작업 보호 |
| `Protocol Builds E2E`, `T/test/e2e/protocol_builds_e2e_test.go:22-110` | 실제 공개 sequential-thinking 패키지의 npx 빌드·상태·도구 목록 확인 절차 | 고정 source/lock/digest, 승인 철회 중 빌드, 도구의 독립 효과 |
| `NetworkIsolation`, `T/test/e2e/network_isolation_test.go:135-207` | 명시/기본 격리 조건, 공개 fetch MCP 호출 경로 | 독립 목적지 로그·raw TCP·DNS 변경·proxy 사망 |
| restart same URL, `T/test/e2e/api_workload_lifecycle_test.go:151-195` | 공개 osv workload 생성→202 restart→running 및 URL 유지 확인 | source→runtime 동일성·계약 재검사·stale attempt |

추가 시험명만 탐색한 범위: `T/pkg/workloads/manager_test.go:1210,2082`, `T/pkg/runner/protocol_test.go:246,663,717`, `T/pkg/client/config_editor_test.go:21,589`, `T/pkg/runner/policy_gate_test.go:56,85`. 본문 전체 검토·통과 판정으로 세지 않는다.

## 6. MINT 대조와 채택 판단

### 6.1 동일 단계 대조

| 단계·백로그 | MINT 코드·증거 | ToolHive와 차이·가져올 것 |
| --- | --- | --- |
| 소스 도입·DEV-38/47 | `validate`는 clone commit·source-tree hash·검사 증거 생성: `M/full_stack_lab/supply_chain/intake_worker.py:240-268` | protocol package build와 다른 경계. 정적 검사 워커에서 저장소 코드를 실행하도록 바꾸지 않음 |
| 승인·미러·DEV-38 | `approve_mcp_request`는 gate→`publish_internal_repo`→승인 전이: `M/full_stack_lab/gateway/app/agent_service.py:1228-1255`; 미러 HEAD·archive hash 대조 `:906-957` | ToolHive registry lookup·기본 allow gate로 대체하지 않음. 승인된 archive를 빌드 입력으로 재사용 |
| job·복구·DEV-38 | 기존 claim은 SKIP LOCKED와 lease/attempt, 만료 reclaim: `M/full_stack_lab/supply_chain/intake_worker.py:365-387` | **제안:** 실행 job에 같은 DB claim 패턴 검토. 검사 상태와 실행 상태 분리, generation·소유권 검증 추가 |
| 등록·계약·DEV-38/44 | 관리자 등록 `register_mcp_request`: `M/full_stack_lab/gateway/app/agent_service.py:1374-1404`; `core.register_server`는 독립 승인·소스 commit·계약 hash 대조: `M/full_stack_lab/gateway/app/core.py:500-567` | ToolHive client 등록은 계약 승인 아님. 실제 runtime endpoint 확인 후 기존 등록 경로 유지 |
| 실제 실행 근거·DEV-38/45 | `M/research/llm-wiki/analysis/wbs-1015/e2e-clean.json:66-70`은 MarkItDown 검증 commit·수동 컨테이너명·tools alias·endpoint 기록 | 보고된 hosting 관측이며 자동 빌드 job/digest 증거는 아님. source-tree SHA를 image digest로 재명명하지 않음 |
| 망·DEV-38/41 | `M/full_stack_lab/compose.yaml:639-694`의 tools 등 internal 망, field의 Caddy·model-proxy 게시 `M/full_stack_lab/compose.field.yaml:33-60` | ToolHive host listener/보조망을 그대로 추가하지 않음. 게시 없는 내부 endpoint와 실제 서버 egress 검증 필요 |
| 하네스·DEV-39/42 | 정본은 카탈로그에서 관리형 설정 렌더링: `M/docs/ai/ARCHITECTURE.md:77-88` | ToolHive 사용자 HOME 직접 갱신은 미채택. PJ1은 MINT URL·credential helper 경로 유지 |
| 종료·DEV-38/43 | 등록 해제는 runtime 카탈로그/계약 제거와 기록: `M/full_stack_lab/gateway/app/core.py:656-670`; 정본 원칙은 차단·회수 구분 `M/README.md:14-20` | 컨테이너 삭제·등록 해제·provider 자격 철회·C1~C4/T1~T3를 각각 검증. ToolHive rm 성공을 T1로 전환하지 않음 |

### 6.2 세 선택지 판정

| 선택지 | 판단·운영 비용 |
| --- | --- |
| ToolHive를 런타임으로 채택 | 첫 DEV-38에서는 보류. 별도 thv 바이너리·XDG 상태·감독 PID·보조 컨테이너·프록시와 MINT DB 사이 복구 책임이 생김. 위 gate/build 순서·기본 검증·client 갱신을 제한하는 adapter도 필요. 근거: §3.1~3.4 |
| 일부 패턴만 | 재사용 방향으로는 유효. 이름 기반 재발견, inspect 후 재조정, PID 일치 reset, 포트 소유자 확인, 재시도 분류를 참고. 코드 복사·부분 포크는 이번 선택에 포함하지 않음. 근거: `T/pkg/container/docker/client.go:1140-1177`, `T/pkg/workloads/manager.go:1086-1133`, `T/pkg/workloads/statuses/file_status.go:486-519` |
| **자체 최소 실행기** | **첫 구현 선택.** 별도 제한 worker가 승인된 MarkItDown 고정 레시피만 빌드·실행하고 기존 등록에 연결. 컨테이너 엔진/공식 SDK를 사용하고 범용 오케스트레이터·임의 README 실행 추출은 만들지 않음. 설계 판단의 기준: `M/research/llm-wiki/analysis/review-2026-10-15/dev38-runtime-plan.md:1-35` |

**제안하는 최소 결속:** intake ID·승인 generation·source commit/tree → recipe/base/dependency 입력 hash → build attempt·image digest → runtime ID·inspect된 image·내부 endpoint → MCP 계약 hash → 등록 ID. 입력 참조와 실제 실행물을 이름·tag만으로 연결하지 않는다.
빌드·시작 전과 ACTIVE 전환 직전에 승인·만료·위험수용을 재확인한다. claim 소유권이 없는 오래된 결과는 반영하지 않는다. Docker 권한은 고정 job을 처리하는 worker에만 두고 Gateway·Console·정적 검사 워커에는 주지 않는다. 이는 현재 설계 제안을 구체화한 것이며 새 권한 부여나 배포를 수행한 것이 아니다.
운영 비용은 최소 실행기도 부담한다. 실패 자원 정리·재발견·자격 회수·image/cache 잔존·업그레이드 회귀를 직접 유지해야 한다. 첫 대상 1개에서 이 비용과 ToolHive adapter 비용을 같은 조건으로 측정한다.

**되돌릴 조건:** 지원 레시피·transport가 늘어 자체 재조정/프록시 코드가 커지거나, ToolHive가 고정 digest·직원 설정 무접근·엄격 readiness·승인 fencing을 adapter로 충족하고 §9 시험에서 운영 비용을 줄이면 전체 런타임 채택을 다시 검토한다.
반대로 선택한 실행기가 중복 실행·종료 항목 부활·철회 뒤 ACTIVE·소스/image 불일치를 막지 못하면 자동 활성화를 중단하고 기존 수동 운영+승인 등록으로 되돌린다. 되돌림도 감사 이력과 종료 판정을 보존해야 한다.

### 6.3 Wassette와 WASI 포팅 비용

Wassette는 Wasmtime component model과 WASI p2/HTTP linker를 구성한다(`W/crates/wassette/src/runtime_context.rs:23-60`). 호출마다 component를 찾아 WASI state·Store를 만들고 instantiate한다(`W/crates/wassette/src/lib.rs:1249-1286`). ToolHive처럼 기존 uvx/npx/go MCP 프로세스를 컨테이너로 감싸는 입력과 다르다.
파일은 preopened_dir 권한으로 노출하고 HTTP host hook에서 URI를 검증한다(`W/crates/wassette/src/wasistate.rs:125-139`, `W/crates/wassette/src/http.rs:189-198`). 이러한 host 경계가 있다는 사실만으로 모든 DNS·redirect·실행 중 회수 검증이 끝난 것은 아니다.
**추론:** MarkItDown의 Python 패키지·native 변환기·파일/네트워크 의존성을 component/WASI ABI에 맞게 포팅하거나 대체하고, 기존 도구 계약·변환 결과를 다시 검증해야 한다. 단순 Dockerfile 재사용 비용과 같지 않다. 구체 포팅 기간·성공 가능성은 미확인이다.
따라서 기존 OSS MCP를 그대로 수용하는 DEV-38 첫 runtime으로는 보류한다. WASI 대상으로 제공된 도구가 생기면 별도 지원 유형으로 검토한다. Wassette 라이선스는 MIT 표기다(`W/Cargo.toml:7-8`, `W/README.md:78`).

## 7. 목표 기능 재설계 시사점

기존 승인·정책·감사·엔드포인트·종료 원칙을 폐기할 근거는 없다. 이번 분석은 DEV-38 실행 상태와 검수 조건을 더 분명하게 만드는 설계 입력이다.

| 목표·연결 | 제안 |
| --- | --- |
| 도입·승인·DEV-38 | 승인 소스 검사와 실행 빌드를 분리. protocol 자동 빌드 이전 승인 검사, ACTIVE 직전 재검사, 지원 레시피 hash를 요구 |
| 계약·DEV-44 | runtime running/listener 성공과 계약 일치를 다른 조건으로 기록. probe 경고 후 ACTIVE 전환 금지 |
| 권한·자격·DEV-41/43 | 승인 hostname뿐 아니라 실제 egress와 runtime별 업무 자격을 제한. 회전·회수 후 기존 프로세스/진행 연결을 독립 확인 |
| 데이터 보호·DEV-38/45 | build secret은 ENV/COPY 대신 검증된 비밀 주입 방식 검토. 로그·layer·cache·재저장 RunConfig까지 비밀 잔존 시험 |
| 하네스·DEV-39/42 | runtime은 직원 HOME·관리형 설정을 수정하지 않음. PJ1 실제 호출은 MINT 경유와 원장 상관으로 검수 |
| 감사·종료·DEV-38/45 | source/image/runtime/endpoint·generation을 감사 근거에 결속. stop/rm 응답과 C1~C4/T1~T3 증거 분리 |
| 평가·DEV-46/47 | SDK/mock 단위 시험, OSS E2E 시험 소스, 실제 PJ1 실행, 독립 업무 효과를 다른 증거층으로 유지 |
| DEV-29 | 브리지의 session·request ID 분리는 참고 가능. MINT upstream pool의 세션 소유권/TTL 설계를 이번 범위에서 대체하지 않음 |

## 8. 정정

| 기존 문장·위치 | 이번 판정 |
| --- | --- |
| `M/research/llm-wiki/solutions/toolhive-runtime.md:3`의 v0.54.0·검토 commit `14c6066…` 결합 | 이번 로컬 태그/HEAD 분석 기준은 **1ce13bbbbbe1ed9a3f40fea03ed1a42533f04cea**로 정정. `git rev-parse HEAD`와 `git rev-parse 'v0.54.0^{commit}'`가 동일. 옛 SHA는 `git cat-file -t 14c6066a4d62aa07c090b27804d20d190a334a45`에서 객체 정보 오류 |
| 옛 SHA의 정체 | shallow clone에 객체가 없으므로 다른 commit인지, 오기인지, 과거 태그 이동인지 판정 불가. 옛 SHA가 존재하지 않는 commit이라고 단정하지 않음. 현재 로컬 태그와 같다는 주장만 반박 가능 |
| 같은 카드 `:3,20`의 고정 LICENSE·SKILL 링크 | 해당 옛 blob을 이번에 확보하지 못함. 이번 라이선스·스킬 근거는 §2의 HEAD 파일·hash로 한정. 옛 문서 작성 당시 무엇을 읽었는지는 소급 확정하지 않음 |
| 같은 카드 `:18`의 custom 기본 outbound 전체 허용 | 취지는 유지하되 **격리 flag 기본 true, gateway deny가 allow-all보다 우선, non-bridge 예외**를 보완. 외부 builtin profile 본문을 읽었다고 승격하지 않음. 근거: `T/pkg/runner/config_builder.go:1342-1410`, `T/pkg/container/docker/squid.go:257-274`, `T/test/e2e/network_isolation_test.go:148-151` |
| `M/research/llm-wiki/analysis/oss-audit/README.md`의 ToolHive 미확보·L1 평가 | 당시 감사 범위의 기록으로 보존. 이번 파일은 별도 clone의 고정 소스·선택 경로 L3를 추가한다. 제품 전체 분석·L4·MINT 채택 완료로 바꾸지 않음 |
| MarkItDown hosting의 확대 해석 | `M/research/llm-wiki/analysis/wbs-1015/e2e-clean.json:69`는 수동 실행의 보고다. 자동 실행 worker·builder provenance·image digest 결속 완료라는 해석은 배제 |

기존 카드와 감사 문서는 사용자 지정 범위 때문에 그대로 두었다. 정정의 정본은 이 절이다.

## 9. 남은 미독 범위와 L4 재현 제안

미독: toolhive-core permissions/verifier 본문, JWT/JWKS·Cedar 전체 판정, 원격 OAuth 회전/철회 전체, Envoy 대체 구현, Kubernetes RBAC/Pod/StatefulSet 전체, VMCP, 전체 client updater·빌드 tar 필터·모든 upstream 시험. 검색·선별 읽기를 기능 부재 판정으로 쓰지 않는다.
후속 실행은 솔루션 기기 `user@100.83.175.111`의 격리된 작업 자원과 PJ1 `pj1@100.110.81.60` 실제 관리 하네스를 사용한다. 이 노트북에 compose 스택을 띄우지 않는다. 실제 공개 OSS MarkItDown 고정 commit `4cc9fa17653d695d64fb9eee5b33d4de55ff84e8`을 첫 대상으로 한다(기존 관측 `M/research/llm-wiki/analysis/wbs-1015/e2e-clean.json:66-70`).
필요 환경: 원본과 분리한 build context·격리 계정·전용 job label/network·독립 수신 로그·engine inspect 권한·private secret 공급, 이름/볼륨/계정별 원복 범위. 다른 작업자의 실행물·종료 케이스를 정리하지 않는다.

| 종류 | 재현 조건 | 통과 근거 |
| --- | --- | --- |
| 정상 | 승인→미러 고정 commit→고정 레시피→검사→digest 실행→계약→등록→PJ1 URL 변환 | job/attempt·source/recipe/base/lock/image hash·runtime ID·endpoint·계약 hash와 원장 ID, 실제 변환 결과 |
| 음성 | 미승인·만료·다른 source/image·계약 변경·다른 사용자 | 정확한 decision/policy_id 또는 job 실패 사유, 신규 ACTIVE·runtime·독립 효과0 |
| 경계 | tag만 입력, 기존 같은 이름 다른 digest, 빈 host 목록·겹친 mount·host/custom network | 의도한 사전 거부와 실제 inspect 값. 정상 허용군도 함께 성공 |
| egress | 허용/미허용 URL, redirect·DNS 변경·사설 IPv4/IPv6·raw TCP, egress sidecar 중단 | 결과 오류뿐 아니라 독립 수신/packet·정상 성공·차단 이유. 미지원 transport는 보류 |
| 빌드 실패 | pull/서명 검사 장애·패키지 실패·timeout·disk full·스캐너 사망 | 실패 상태·비밀 제거 로그 hash, ACTIVE0, 중간 image/network/cache 잔존 목록 |
| 비밀 | provider 장애/not-found, 환경 fallback, 회전/철회, 일반 secret+RemoteAuth 재저장 | context/layer/cache/config/log/inspect의 합성 비밀 잔존, 기존·재시작 프로세스의 재접근 효과 |
| 경쟁 | 동시 신청/worker2개, 생성 뒤 DB 반영 전 kill, 늦은 attempt, 빌드 중 승인 철회 | generation당 runtime1개 이하, stale 반영0, 철회 뒤 신규 ACTIVE0. Docker count와 DB를 독립 대조 |
| 프록시·진행 호출 | bind 충돌·attach EOF·응답 유실·호출 timeout·proxy kill | listener/상태 일치, 응답 유실 쓰기의 효과 수·uncertain 기록, 자동 중복 실행0 |
| 복구 | supervisor/engine/호스트 재시작, status 또는 RunConfig 유실, 재기동 직후 rm | orphan 재발견·정리/연결, 종료 항목 부활0, 승인·digest·계약 재확인, 다른 작업 보존 |
| 종료 | Gateway 먼저 거부→프로세스/자격/볼륨·캐시 정리→복원 뒤 재호출 | C1~C4/T1~T3 각각의 독립 증거. rm 성공 응답만으로 완료 금지 |

각 실행에 run ID·판본·image/config/policy hash·반복 수·정상 성공·오탐/미탐·지연·독립 효과·원복을 연결한다. 같은 조건의 ToolHive 실행과 최소 실행기 비용을 비교하기 전 성능·보안 우위는 미확인으로 유지한다.
이번에 생략한 것은 설치·실행·배포·PJ1 시험과 외부 의존성 전문 검수다. 핵심 위험은 승인/source/image/runtime 결속, 기본값의 허용·경고 분기, 크래시 후 중복/잔존이며 모두 후속 L4 검수 대상이다.
