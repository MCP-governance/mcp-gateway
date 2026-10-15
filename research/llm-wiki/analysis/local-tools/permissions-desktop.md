# Desktop/browser MCP 권한·브리지 참고 조사

- 조사일: 2026-10-14 (Asia/Seoul)
- 범위: MCP HTTP/stdIO·도구 annotation, Microsoft Playwright MCP 0.0.83, Chromium 프로세스 격리, Blender 5.2 스크립트 보안의 공식 원문을 읽고 현재 Windows endpoint kit와 실제 task-local MCP 시험에 대조했다.
- 수행 수준: 원문 및 저장소 코드 read-only 조사다. OS 보안·브라우저·Blender 설정 변경, 추가 보안 음성 시험, endpoint runtime 검증은 하지 않았다.
- 중복 확인: `research/llm-wiki/catalogs`, `papers`, `sources`, `analysis/local-tools`, desktop 실험에서 MCP `T01/T02/T21`, annotation, allowed origins/file access/unsafe tools, Chromium sandbox, Blender script security를 검색했다. MCP auth/tools/security 원문은 이미 `T01`, `T02`, `T21`에 있으므로 새 catalog 항목은 만들지 않았다.
- 원문 스냅샷, 해시, 세부 read scope와 적용 판정은 [permissions-desktop.json](permissions-desktop.json)에 있다. 원본은 무시된 `.task-local-20261014/desktop/permissions/originals/` 및 pinned source checkout에 보관했다.

## 공식 원문과 고정 버전

| ID | 원문·판본 | 적용에 사용한 핵심 | SHA-256 |
|---|---|---|---|
| MCP-TRANSPORT-AND-TOOL-TRUST | [Authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization), [Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools), [Security Best Practices](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices), 2026-07-28 | HTTP OAuth와 stdio 자격증명 경로를 구분한다. HTTP bearer 토큰은 대상 audience·scope로 검증한다. `readOnlyHint` 같은 tool annotation은 신뢰된 서버 출처가 아니면 신뢰하지 않는다. 로컬 MCP 프로세스는 client 권한으로 실행될 수 있으므로 최소 권한·sandbox가 별도 필요하다. | authorization `B4DD9BC6…AB57C7C`; tools `51D7A3C6…D6C4BAB`; security `5B0515A1…D0B8E42` |
| PLAYWRIGHT-MCP-0.0.83-SECURITY-OPTIONS | [Microsoft Playwright MCP README](https://github.com/microsoft/playwright-mcp/blob/b8b4183e099f136cbec0388a6088d4aa2f6b9685/README.md), Apache-2.0, commit `b8b4183e099f136cbec0388a6088d4aa2f6b9685` | `--allowed-origins`는 보안 경계가 아니고 redirect를 제한하지 않는다. 기본 파일 접근은 workspace/CWD 범위이며 `file://` 탐색은 막힌다. `--isolated`는 프로필 메모리 저장 여부다. `browser_run_code_unsafe`는 MCP 서버 프로세스에서 임의 JS를 실행한다. | pinned checkout README `15E4C957…2A317C6` |
| CHROMIUM-PROCESS-SANDBOX | [Chromium process-sandboxes-by-platform.md](https://chromium.googlesource.com/chromium/src/+/f68f02e31715f9fd8b54fc45d46f94e1e56d2985/docs/security/process-sandboxes-by-platform.md), commit `f68f02e31715f9fd8b54fc45d46f94e1e56d2985`, BSD-style | 원문 표는 Browser 전체와 Windows Network 프로세스를 unsandboxed로, renderer/extension/PDF renderer를 sandboxed로 표기한다. 문서 자체는 표가 M128 기준이라고 쓴다. 이는 Chromium 155의 실행 상태 증명이 아니다. | `3312A97B…FFE12BB0` |
| BLENDER-5.2-SCRIPT-SECURITY | [Blender 5.2 LTS Scripting & Security](https://docs.blender.org/manual/en/5.2/advanced/scripting/security.html), CC BY-SA 4.0 | Blender Python은 스크립트 권한을 제한하지 않는다. blend 파일의 자동 실행은 기본 비활성화이며 `-Y` / `--disable-autoexec`로도 끌 수 있다. 수동 Python 실행은 별도 표면으로 남는다. | `1A5935FB…6152AE` |

## 현재 kit와 실험에 적용되는 경계

MCP protocol 인가와 OS 권한은 서로 다른 통제다. Authorization 명세는 HTTP MCP에 대해 bearer token, audience 및 scope 검증을 설명하고, stdio 구현은 그 OAuth HTTP 흐름을 따르기보다 환경 자격증명을 쓰도록 한다. 그러나 stdio child는 기본적으로 실행한 클라이언트와 같은 OS identity에서 동작한다. Tools 명세도 annotation을 신뢰된 서버가 아닌 경우 신뢰하지 말라고 한다. 따라서 `readOnlyHint`, initialize 응답, command 해시, `stdio` 분류 중 어느 하나도 도구가 읽기만 한다는 증거가 아니다.

현재 `endpoint-agent/agent.py::describe`는 configured HTTP와 stdio 명령을 구분해 인벤토리한다. `probe_mcp`는 HTTP MCP 후보에 initialize 한 번만 보낸다. 이는 서버 탐지·분류의 근거이지 도구 호출 권한이나 child 프로세스 격리 증거가 아니다. Windows named pipe `\\.\pipe\mcpgw-<계정>`은 enrolled 계정에 읽기 권한을 주는 header broker이며 MCP 자식 프로세스의 파일·네트워크·프로세스 권한을 줄이지 않는다.

Playwright MCP의 실제 시험은 stdio, headless Chromium, task-local 프로필, 임의 포트의 loopback 합성 HTML에서 `browser_navigate`와 `browser_snapshot`을 호출한 것이다. 이 시험은 그 경로의 로컬 읽기 성공만 입증한다. Origin redirect, file upload/drop, unsafe JS tool, Chromium OS sandbox를 시험하지 않았다. README의 `--allowed-origins` 설명이 redirect를 명시적으로 제한하지 않으므로, 이를 URL/네트워크 경계로 쓰면 안 된다. 기본 파일 제한을 풀지 말고, 클라이언트 쪽 tool allowlist에서 unsafe-code 및 host-file 도구를 차단하며, redirect를 두 번째 합성 loopback origin으로 보내는 음성 시험을 별도 수행해야 한다.

Chromium은 renderer를 sandboxed로 분류하더라도 브라우저/Windows network process를 동일한 경계라고 말하지 않는다. 더구나 Playwright MCP Node child, Burp 확장 프로세스, Blender bridge는 Chromium renderer가 아니다. `--isolated`, `--headless`, task-local user-data-dir은 프로필과 UI 실행 방식 선택일 뿐 OS sandbox가 아니다. Chromium 참조 표는 M128에 마지막 갱신된 것으로 표시되므로, 설치된 Chromium 155.0.8059.12의 프로세스 token, job, AppContainer, command flags를 확인하지 않고 런타임 샌드박스를 주장하지 않는다.

Blender의 자동 실행 설정은 `.blend` 파일의 암묵적 script auto-run을 다루며 `execute_blender_code`처럼 MCP 호출로 명시 실행되는 Python을 제한하지 않는다. 실제 addon bridge는 `127.0.0.1:9876`에 bind했고, raw TCP bridge에는 caller auth/encryption/Origin check가 없으며 `execute_code`가 Python `exec`까지 간다. Loopback은 원격 라우팅을 줄이지만 같은 PC의 다른 프로세스를 차단하지 않는다. 조사 당시 launcher에는 `--disable-autoexec`가 없었고, Codex 검수 후 `start-blender.ps1`에 추가했다. 자격정보 환경 변수도 MCP child에 전달하지 않도록 줄였으며 새 flag에서 initialize·목록9개·장면 읽기·합성 구 생성/읽기 확인을 재실행했다. 그래도 명시 MCP Python 실행과 직접 raw bridge는 별도 OS 경계로 막아야 한다.

Windows endpoint README는 계정 SID 대상 outbound firewall 규칙과 아직 미설치된 App Control/AppLocker를 구분한다. Codex 검수 후 loopback 일반론도 현재 키트의 실측 미완료로 정정했다. 따라서 계정 egress 제어, pipe ACL, renderer sandbox, stdio 모두 MCP bridge에 대한 독립 권한 강제인 것처럼 표현하지 않는다. 적용 판정에는 해당 MCP 프로세스의 SID/token, binary·command line, 실제 listen address, caller 인증, file/network/process 권한을 각각 확인해야 한다.

## 권장 확인 기준과 아직 안 한 시험

세부 기준은 JSON의 `findings[*].validation_criteria`에 기록했다. 현재 desktop 시험에서 완료된 것은 합성 페이지 읽기와 Blender 합성 오브젝트 생성뿐이다. 미수행 기준은 사용자 데이터나 외부 대상을 건드리지 않고 task-local fixture로만 검증한다.

- HTTP 인가: 정상 audience/minimum scope 요청은 허용하고, token 없음·잘못된 audience·scope 부족은 경계에서 각각 거부되는지 확인한다. read-only annotation을 붙인 prohibited tool도 서버 측 권한 검사를 통과하지 않아야 한다.
- Playwright: 로컬 fixture가 제2 합성 origin으로 redirect할 때 어떤 구성요소가 차단하는지 확인한다. workspace 밖 canary 파일 접근·외부 egress는 restricted identity/OS policy에서 막히는지 별도 확인한다. unsafe code와 upload/drop은 client 정책상 도구 목록에 없는지 확인한다.
- Blender: `--disable-autoexec`로만 제어되는 auto-run과 explicit MCP Python 호출의 차이를 harmless synthetic marker로 확인한다. 별도 same-account 로컬 프로세스가 raw loopback bridge에 접근 가능한지 확인하고 OS 통제 효과를 독립적으로 시험한다.
- OS 경계: client allowlist만 적용한 시험과 OS 파일/네트워크 policy만 적용한 시험을 각각 다른 canary 효과로 수행한다. 둘의 효과를 합쳐 놓고 어느 한쪽 단독 효과로 보고하지 않는다.

`permissions-desktop.json`의 findings는 모두 소스 기반 권장 기준이며, 아직 실행하지 않은 시험은 `not_run`으로 표시했다.
