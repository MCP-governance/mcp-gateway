# DEV-81 로컬 수신 지점 인증 적대 검토

작성일: 2026-10-21
기준: `main` `f5fa6fd` 정적 코드와 저장된 근거. 제품 코드·시험은 수정하지 않았다.

## 판정 요약

**`열려 있음(제품이 막아야 함)` 지점이 있다.** Linux 헤더 소켓, Windows 이름 있는 파이프, 직원 PC 키트의 헤더 헬퍼는 관리 사용자의 UID/SID로만 접근자를 제한한다. 같은 계정의 다른 프로세스는 활성 MCP bearer를 받을 수 있다. UID/SID와 파일 모드는 프로세스 인증이 아니다. 게이트웨이의 도구·정책 판정은 계속 적용되지만, 프로세스가 관리 직원으로 직접 호출할 수 있게 된다. 심각도는 **높음**으로 평가한다.

`endpoint-agent/local-runner.py`는 현재 체크아웃과 사전 적재된 Git 참조에서 찾지 못했다. DEV-73 실행기와 그 요청·오프라인 경로의 인증 판정은 유보한다. 따라서 DEV-81을 완료로 판정할 수 없다.

## 수신 지점 목록

| 지점 | 여는 코드·설정 | 호출자 인증 | 접근 가능 주체·재현 조건 | 판정 |
| --- | --- | --- | --- | --- |
| Linux 관리형 헤더 브로커 `/run/mcpgw-<user>.sock` | [`managed-linux.py`](../../../../endpoint-agent/managed-linux.py): 265–286, 396–409; [`enforce-linux.py`](../../../../endpoint-agent/enforce-linux.py): 117–159, 385–401 | 소켓 모드 `0600`과 `SO_PEERCRED`의 UID 일치만 검사한다. 커널이 제공하는 PID/GID는 버린다. bearer는 메모리 캐시에서 응답한다. | 다른 UID는 소켓 DAC에서 거부된다. 관리 UID의 다른 프로세스는 설치된 `header-helper`를 호출하거나 해당 UID로 소켓에 연결하면 활성 bearer를 받는다. AppArmor가 헬퍼와 소켓 경로만 허용해도 같은 UID로 실행 가능한 고정 헬퍼가 남는다. 일반 웹 페이지는 AF_UNIX 소켓에 `fetch`할 수 없다. | **열려 있음(제품이 막아야 함)** |
| Windows 관리형 헤더 브로커 `\\.\pipe\mcpgw-<user>` | [`managed-windows.py`](../../../../endpoint-agent/managed-windows.py): 51–52, 405–448, 451–481 | 보호 DACL이 등록 SID에는 읽기를 주고 SYSTEM·생성 소유자에는 전체 권한을 준다. 원격 클라이언트를 거부하고 첫 파이프 인스턴스에서 이름 선점을 거부한다. 요청별 프로세스 확인은 없다. | 다른 SID 및 원격 클라이언트는 거부된다. 등록 SID의 다른 프로세스는 같은 파이프 이름을 열고 응답을 읽을 수 있다. `PIPE_REJECT_REMOTE_CLIENTS`는 로컬 SID를 제한하지 않는다. 웹 페이지는 브라우저 HTTP API로 이름 있는 파이프를 직접 열 수 없다. | **열려 있음(제품이 막아야 함)** |
| 직원 PC 키트의 Claude/Codex 헤더 헬퍼 | [`mcpgw_pc.py`](../../../../full_stack_lab/field/pc/mcpgw_pc.py): 142–150, 282–295, 357–365, 479–485, 837–839 | 별도 호출자 인증 없음. `header` 명령은 저장 토큰을 읽어 `Authorization`을 stdout에 출력한다. 토큰 파일은 POSIX `0600`; Windows는 사용자 프로필 기본 ACL이다. 갱신 잠금은 동시 refresh만 직렬화한다. | 같은 OS 사용자 프로세스는 관리형 헬퍼 명령을 그대로 실행하거나 프로필 토큰 파일을 읽을 수 있다. `header` 호출은 MCP 게이트웨이 토큰을 노출한다. 웹 페이지는 브라우저만으로 로컬 CLI/stdout에 접근할 수 없다. | **열려 있음(제품이 막아야 함)** |
| 직원 PC 키트 `token` 명령 | [`mcpgw_pc.py`](../../../../full_stack_lab/field/pc/mcpgw_pc.py): 475–476, 899 | 현재 로그인한 사용자의 토큰을 명시적으로 출력하는 명령이다. | 같은 사용자 프로세스가 토큰을 얻어 별도 클라이언트에서 사용할 수 있다. 이 경로는 D-170의 개인 토큰 직접 사용 분류에 포함한다. 제품은 이후 게이트웨이 판정을 계속 적용한다. | **조직 통제 의존** |
| 관리 계정의 로컬 TCP egress와 D-119 소유자 예외 | [`enforce-linux.py`](../../../../endpoint-agent/enforce-linux.py): `nft_rules` 및 `profile` 구현; [D-119](../../../../docs/ai/DECISIONS.md): 1339–1345 | 관리 UID가 시작한 새 루프백 연결은 거부한다. 소유자 UID가 시작한 연결에 대한 관리 UID 응답만 connmark `0x100`으로 허용한다. | 승인되지 않은 관리 UID발 로컬 MCP 접근은 기존 정책의 차단 대상이다. 소유자 UID의 브라우저가 관리 하네스의 로그인 리스너로 시작한 연결은 의도된 응답 예외다. 10-15의 399건은 Codex 브라우저 로그인 트래픽으로 정정됐고, E13 7개 반례는 로컬 네트워크 조건이지 악성 웹 Origin 시험이 아니다. | **막혀 있음** — 관리 UID발 비인가 로컬 MCP 연결. 소유자 로그인 응답은 아래 별도 항목 참조 |
| 하네스 자체 로그인 콜백 (외부 구현) | Codex 0.160.0 고정 소스의 `run_login_server`; 과거 근거 [dev35-loopback §3](../dev35-loopback/README.md): 28–37. Claude 콜백도 같은 문서에 버전·근거가 기록돼 있다. | Codex는 `state`와 PKCE를 검사한다. 검토한 고정 Codex 소스에서 HTTP `Origin` 검사는 찾지 못했다. Claude 실행 바이너리의 현재 소스·Origin 처리는 이번 체크아웃에서 확인하지 못했다. | 브라우저 로그인 대체 흐름에서 Codex가 `127.0.0.1:1455/1457`에 바인딩하고 소유자 브라우저가 접속한다. 관리 기본 로그인은 장치 코드다. D-119가 소유자 UID의 로컬 연결을 의도적으로 허용한다. 웹 페이지가 simple request를 보낼 수 있는지, `/cancel` 등이 상태를 바꾸는지는 브라우저·하네스 실행 확인이 없다. CORS는 요청 인증이 아니며 응답 읽기 제한만으로 호출 방지를 입증하지 못한다. | **조직 통제 의존** — 외부 하네스의 의도된 로그인 경로. 웹 Origin 무접근은 입증되지 않음 |
| Linux 오프라인 관측 버퍼와 커서 | [`os-observer.py`](../../../../endpoint-agent/os-observer.py): 123–133; [`offline_buffer.py`](../../../../endpoint-agent/offline_buffer.py): 30–49, 71–90; [`managed-linux.py`](../../../../endpoint-agent/managed-linux.py): 210–230, 287–292 | `/var/lib/mcpgw-managed/<user>` 아래 root 관리 디렉터리(mode `0700`)에 저장한다. 관측기 실행 때 설정 파일·모든 상위 경로의 root 소유와 group/world 쓰기 금지를 확인한다. 임시 파일 생성 후 `0600`, fsync, `os.replace`한다. | 일반 사용자 UID는 부모 디렉터리에 접근·교체할 수 없다. 버퍼 파일의 최종 경로가 심볼릭 링크여도 원자 교체는 링크 대상을 따라 쓰지 않는다. root/admin 조작은 신뢰 경계 안이다. | **막혀 있음** |
| Windows 오프라인 관측 버퍼와 커서 | [`os-observer-windows.py`](../../../../endpoint-agent/os-observer-windows.py): 216–225; [`offline_buffer.py`](../../../../endpoint-agent/offline_buffer.py): 30–49, 71–90; [`managed-windows.py`](../../../../endpoint-agent/managed-windows.py): 169–188, 570–572, 629–637 | `ProgramData\MCPGatewayManaged\<user>` 하위 상태 디렉터리는 SYSTEM·Administrators가 쓰고 일반 사용자는 읽을 수 없도록 고정한다. 파일 교체는 같은 보호 부모 안에서 임시 파일과 `os.replace`를 사용한다. | 같은 일반 SID도 부모 경로를 쓰거나 버퍼 파일을 교체할 ACL이 없다. 관리자/SYSTEM은 신뢰 주체다. 실제 Windows ACL은 실행하지 않고 구현만 확인했다. | **막혀 있음** |
| Windows 트레이 상태 스냅샷 | [`managed-windows.py`](../../../../endpoint-agent/managed-windows.py): 566–568, 639–640, 718–724; [`windows_status.py`](../../../../endpoint-agent/windows_status.py): 1–42; [`tray.ps1`](../../../../endpoint-agent/tray.ps1): 21–35; [`windows-trust.ps1`](../../../../endpoint-agent/windows-trust.ps1): 51–82 | `ProgramData\MCPGatewayManagedTray\<SID>\status.json`; SYSTEM/Admin은 쓰고 해당 SID에는 읽기·실행만 준다. 내용은 자격증명이 아닌 연결 상태와 최근 차단 요약이다. | 해당 사용자와 그 사용자 프로세스는 읽을 수 있게 설계됐다. 다른 표준 SID는 허용 DACL이 없다. 같은 SID에서 상태를 읽는 것은 bearer 전달이나 판정 입력이 아니다. | **조직 통제 의존** — 같은 SID 읽기를 의도적으로 허용한 비밀 없는 상태 정보 |
| Windows 설치 요청·결과 파일 | [`windows-worker.ps1`](../../../../endpoint-agent/windows-worker.ps1): 42–74, 83–92; [`windows-trust.ps1`](../../../../endpoint-agent/windows-trust.ps1): 10–18, 51–82, 161–206, 216–245 | 승격 분기는 승인된 Program Files 설치 경로·해시·보호 ACL을 확인한다. 요청 경로는 등록 SID 프로필의 UUID 하위로 제한한다. 파일을 `FileShare.Read`로 열고 핸들의 최종 경로와 크기를 검증하며, SID·관리 모드·허용 작업을 검사한 뒤 보호된 ProgramData로 복사한다. | 일반 사용자 프로세스가 요청 JSON을 만들거나 바꿔도 관리자 승격 및 승인 경로 검증을 통과해야 한다. 읽기 핸들이 열린 뒤 동시 쓰기·삭제 공유는 허용되지 않는다. 비관리 분기는 현재 사용자의 권한으로만 처리한다. | **막혀 있음** — 승격된 장치 변경 경로 |
| Linux/Windows 일회용 enrollment JSON | [`managed-linux.py`](../../../../endpoint-agent/managed-linux.py): 170–175, 218–230, 261; [`managed-windows.py`](../../../../endpoint-agent/managed-windows.py): 544–548, 578–586, 613 | 별도 로컬 caller 인증이나 파일 핸들 고정은 없다. 설치 명령이 관리자/root 권한으로 읽고, enrollment token 및 HTTPS/CA 설정을 사용한다. | 로컬 사용자가 쓸 수 있는 입력 파일이면 관리자 설치 중 파일 교체 경합이 가능하다. 이 입력만으로 장치 등록이 성공하는 것은 아니며 유효한 일회용 enrollment token이 필요하다. 설치 디렉터리·실행 시점과 입력 파일 ACL은 실기기에서 확인하지 않았다. | **조직 통제 의존** — 관리자 승인·일회용 등록 자격 경계 |
| 관리형 Claude/Codex 서버 주소 설정 | [`registry/catalog.toml`](../../../../full_stack_lab/registry/catalog.toml): 11–13, 80–370; [`registry/field/catalog.toml`](../../../../full_stack_lab/registry/field/catalog.toml): 1–14; [`render.py`](../../../../full_stack_lab/workstation/managed/render.py): 20–43; [`mcpgw_pc.py`](../../../../full_stack_lab/field/pc/mcpgw_pc.py): 61–75, 832–839 | 현재 레지스트리 기본 `gateway_url`은 빈 값이다. 데모 MCP 주소는 `mcp-*` 컨테이너 호스트명이며, field 배포 렌더러는 HTTPS Gateway 주소를 요구한다. PC 키트의 loopback HTTP 허용은 테스트 주소 검증 분기다. | 현재 설정 렌더링에는 직원 PC의 localhost MCP listener가 없다. 주소는 하네스가 Gateway로 보내는 outbound URL이다. 이 설정 검색에서 HTTP 서버/loopback bind는 나오지 않았다. | **막혀 있음** — 현재 관리형 렌더링에 loopback MCP 수신 주소 없음 |
| DEV-73 장치 실행기 `endpoint-agent/local-runner.py`와 로컬 요청 경로 | 요청된 경로는 현재 존재하지 않는다. 이전 분석 [d175-local-run.md](../review-1020/d175-local-run.md)는 이 파일을 인용하지만 원문 코드는 없다. 로컬·사전 적재된 원격 참조를 확인했다. | 확인할 코드가 없다. | 현재 `main`과 체크아웃된 DEV-73 review 및 DEV-80 참조에 파일이 없다. 이전 분석의 코드 인용만으로 listener·권한·버퍼를 추정하지 않는다. | **판정 유보** — 소스 부재 |

**수신점이 아닌 검사 대상:** `endpoint-agent/agent.py:775, 839`는 `127.0.0.1` MCP 포트에 클라이언트로 접속해 관측한다. `os-observer.py`와 `os-observer-windows.py`는 OS 이벤트를 파일 버퍼에 쌓고 Gateway로 전송한다. endpoint-agent·PC 키트·관리형 renderer의 Python/PowerShell 소스 검색에서 그 밖의 HTTP server, TCP `bind/listen`, Uvicorn, named pipe 생성, Unix listener는 나오지 않았다. `install.py`·`bootstrap.py`의 로컬 파일 및 설치 흐름도 명령형 설치 입력이며 상시 수신 서비스는 아니다.

## 발견과 재현 조건

### F1 — UID/SID를 프로세스 인증으로 사용해 bearer 전달 (높음)

**Linux:** `managed-linux.py:273–279`는 `SO_PEERCRED`에서 UID만 대조하고 그 UID에 bearer를 응답한다. 같은 관리 UID에서 승인된 `header-helper` 명령을 실행하면 AppArmor credential profile과 소켓 경로를 통과해 helper가 stdout에 토큰을 낸다(`enforce-linux.py:117–159, 390–395`). 일반 다른 UID는 `0600` DAC에서 차단된다. 이는 계정 분리가 보장하는 범위다.

**Windows:** `managed-windows.py:415–428`의 DACL은 등록 SID에 읽기를 부여하고 `managed-windows.py:437–445`는 pipe client 신원·PID 확인 없이 활성 bearer를 쓴다. 등록 SID로 파이프를 열어 한 응답을 읽는 것으로 재현된다. 다른 SID와 원격 클라이언트는 ACL/플래그에서 거부된다.

**직원 PC 키트:** 하네스 설정이 `header` 명령을 직접 실행하도록 렌더링한다. 같은 사용자 프로세스는 그 명령을 실행해 `Authorization` 값을 얻을 수 있다. `0600`/프로필 ACL과 refresh lock은 같은 UID/SID 프로세스를 구분하지 않는다.

세 경로 모두 브라우저가 직접 Unix socket, named pipe 또는 CLI stdout을 읽는 HTTP endpoint는 없다. 일반 웹 페이지 접근을 이 경로에서 확인한 것은 아니다. 문제는 같은 계정의 로컬 프로세스다. 토큰이 유출되면 호출자는 Gateway에 관리 직원의 MCP bearer로 연결할 수 있고 이후 도구·정책 판정은 계속 적용된다.

**수정 제안:** 재사용 가능한 bearer를 동일한 사용자 보안 주체에게 넓게 반환하지 않도록 설계를 바꾼다. 하네스 실행 단위에 묶인 일회용 capability/응답, 별도 broker principal과 OS 강제 client identity를 검토한다. PID 숫자나 UID/SID 일치만 추가하는 수정은 해결이 아니다. 수정 후에는 서로 다른 UID/SID, 같은 UID/SID의 임의 프로세스, 실제 승인 하네스, 프로세스 종료·재시작·경합을 각각 나눠 검증해야 한다.

### F2 — D-119 loopback 증거는 웹 Origin 인증 증거가 아님

현재 제품 소스에서 MINT 관리 구성요소가 여는 TCP HTTP listener는 찾지 못했다. 확인된 제품 IPC는 Linux Unix socket과 Windows named pipe다. 이 경계에는 HTTP `Origin`·`Host`, CORS preflight, DNS rebinding 검사가 적용되지 않는다. Browser fetch가 이 socket/pipe에 직접 연결하지 않는다.

D-119는 관리 UID가 시작한 로컬 새 연결을 차단하고 소유자 UID가 시작한 연결의 응답만 허용한다. `dev35-loopback/README.md:8–14, 41–49`는 399건의 의미를 바로잡고 E13 반례를 기록한다. `DECISIONS.md:1345`는 D-119의 현재 검증이 순수 Python 단위 검증이며 이번 판본의 PJ1·netns/E13은 미실행이라고 명시한다. 따라서 이를 현재 기기에서 “모든 다른 프로세스/웹 페이지 0”으로 확장하지 않는다.

Codex 0.160.0 browser-login fallback은 HTTP loopback listener를 두고 `state`·PKCE를 검사한다. 검토한 [고정 소스](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/login/src/server.rs)에서 `Origin` 검사는 찾지 못했다. D-119가 소유자 브라우저 연결을 위해 응답 예외를 열어 두므로 웹 페이지에서 온 simple request가 실제로 차단되는지, 취소 등 상태 변경이 가능한지 이 정적 검토로 판정할 수 없다. 로그인 기본 경로는 장치 코드다. Codex/Claude의 이 외부 listener는 MINT가 소유한 MCP endpoint가 아니며 조직 통제 범위로 분류하되, **DEV-81의 웹 접근 0을 입증한 것으로 세지 않는다.**

### F3 — 설치·임시·파일 교환 경계

- Linux offline buffer는 root 관리 상태 경로 아래 놓이고, 경로·소유자 검사를 통과한 root 관측기만 쓴다. 임시 파일은 같은 디렉터리에 만들고 `0600`으로 설정해 fsync 후 교체한다. 정상 UID가 상위 디렉터리나 임시 파일을 바꾸는 경합은 코드에서 막힌다.
- Windows offline buffer는 SYSTEM/Administrators 보호 아래 놓인다. 임시 파일명은 생성 시 유일값을 사용하고 동일 경로에서 교체한다. 표준 SID에는 버퍼 디렉터리 쓰기 권한이 없다. 실제 장치 ACL은 이번 검토에서 측정하지 않았다.
- Windows 승격 요청 파일은 재분석 지점·ACL·설치 루트·허용 경로·요청 SID·요청 크기·작업을 검사한다. 요청 파일을 공유 쓰기 없이 열고 핸들의 최종 경로를 다시 확인한 뒤 SYSTEM/Admin 전용 상태 디렉터리로 옮긴다.
- Linux/Windows enrollment JSON은 root/관리자 설치 명령이 일반 파일 경로에서 읽는다. 코드에 파일 핸들 고정·심볼릭 링크 거부는 보이지 않는다. 악성 같은 사용자 프로세스가 관리자 설치 도중 입력 경로를 바꾸려면 writable 입력과 설치 타이밍이 모두 필요하며, Gateway가 발급한 유효 등록 token도 필요하다. 설치 UI/현장 ACL과 이 경합은 확인하지 않았다. 후속 설치 hardening에서 승인 입력을 보호 디렉터리에 고정 사본으로 먼저 스테이징하는 방안을 검토한다.
- Windows tray snapshot은 지정 SID가 읽을 수 있는 무자격 상태 파일이다. 같은 계정 프로세스에 상태가 보인다는 점을 기록하되, bearer/관리 권한/판정 입력을 제공하지 않는다.

## D-170 적용

| 경로 | 분류 | 범위 해석 |
| --- | --- | --- |
| MDM이 관리하는 다른 OS 계정의 자체 접근, 승인 경로 밖 하네스/커넥터, 사용자 개인 token 직접 호출 | 조직 통제 의존 | D-170이 정한 MDM·AppLocker/WDAC·SSE/CASB·IdP·조직 테넌트 정책의 통제 범위다. 통제가 없는 조직에서 실제 열릴 수 있음을 문서에 남긴다. |
| 같은 관리 UID/SID의 다른 프로세스가 제품 helper/broker에서 bearer를 받는 경우 | **열려 있음(제품이 막아야 함)** | OS 계정 ACL은 같은 보안 주체 내부에서 프로세스 권한을 나누지 않는다. D-170의 다른 계정 분류로 숨기지 않는다. |
| 관리 UID가 직접 비인가 localhost MCP로 연결 | 막혀 있음 | D-119/nft·AppArmor 경계와 과거 E13 근거가 있다. 현재판의 실기기 효과는 미확인으로 남긴다. |
| 소유자 브라우저가 하네스 로그인 callback으로 연결 | 조직 통제 의존 | D-119의 의도된 예외다. E13은 악성 웹 Origin 확인이 아니며 브라우저 접근 0은 입증되지 않았다. |
| 보호된 offline buffer·승격 요청 경로 | 막혀 있음 | 보호 디렉터리·핸들 경로 검증·파일 ACL 범위에서 판단했다. root/Admin은 신뢰 주체다. |

관리 계정 자신의 직접 외부 연결, 비인가 로컬 MCP 실행, 승인 계약 불일치, Gateway로 전달된 호출은 D-170이 제외한 제품 차단 책임에 남는다. 같은 계정의 helper bearer 노출도 이 책임에 해당한다.

## 이미 막혔거나 기록된 것 / 이번에 새로 발견한 것

**기존 근거를 유지한 항목**

- D-119: 관리 계정이 시작한 루프백 연결·비인가 로컬 MCP 연결은 차단 대상이다. 소유자 시작 연결의 응답 예외만 있다. loopback 399건은 Codex 브라우저 로그인 패킷으로 정정됐고, 7개 E13 반례도 과거 기록에 있다.
- D-147: 관리형 훅 잠금과 AppArmor 경계를 적용한다. 자격/관측 helper 및 Codex `notify`는 관리 키로 잠기지 않는 한계가 이미 기록돼 있다.
- D-148/D-151: 사용자 명령 helper 설정을 검사하지만, 실행 시점 잠금이나 모든 프로세스 접근 차단은 아니다. 기본 위치 외 설정·실행 인자 등 한계가 이미 문서화됐다.
- DEV-80 offline buffer: 경로 보호·원자 교체 구현을 이번 수신 지점 검토에 재사용했다. 기존 구현 한계를 반복해 새 위험으로 올리지 않았다.

**새로 확인한 제품 공백**

- Linux/Windows managed header broker는 PID·서명·실행 단위가 아니라 UID/SID만 확인하고 bearer를 반환한다.
- Field PC `header` command도 같은 계정의 임의 프로세스 인증이 없다. 기존 사용자 helper 설정 검사는 호출자를 제한하지 않는다.
- D-119의 기존 시험은 브라우저 악성 Origin/simple-request test가 아니다. 외부 Codex callback source에서 Origin 검사를 찾지 못했고 이 영역의 0 접근은 증명되지 않았다.
- DEV-73 local runner source가 없어 실행기/요청 파일/오프라인 교환 경계가 미검토다.

## 출처

- DEV-81 원문: [direction-1020 README](../direction-1020/README.md) §3, line 74
- 기존 루프백 분석과 E13: [dev35-loopback](../dev35-loopback/README.md)
- 실기기 2026-10-20 E13 자료: [원시 결과 인덱스](../real-env-20261020/e13/index.jsonl)
- D-119, D-124, D-147, D-148, D-170: [DECISIONS.md](../../../../docs/ai/DECISIONS.md)
- 공식 MCP 지침: [Local Server Security](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/docs/2026-07-28/tutorials/security/local-server-security.mdx), [Streamable HTTP Origin 검증](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- 관련 작업 보고: [2026-10-21 로컬 수신 지점](../../status/reports/2026-10-21-local-endpoints.md)

## 메인 판단 (2026-10-21)

**F1은 맞다. DEV-81은 완료가 아니다.** 다만 고칠 수 있는 범위와 없는 범위를 정확히 나눈다.

- **같은 OS 보안 주체 안에서는 사용자 공간 장치만으로 토큰 탈취를 완전히 막을 수 없다.** 같은 UID/SID 프로세스는 하네스 프로세스 메모리를 읽거나(ptrace·디버그 권한) 하네스가 받은 응답을 가로챌 수 있다. 따라서 "PID·실행 파일 경로 확인을 붙이면 해결"이라고 적지 않는다(검토의 지적과 같다).
- **지금 실제 노출 범위**: 탈취한 bearer는 5분 수명(D-159)이고 게이트웨이의 신원·도구·정책 판정은 그대로 적용된다. 새로 생기는 능력은 **하네스 쪽 통제(D-147 명령 표면 잠금·관리형 설정·훅)를 건너뛰고 게이트웨이를 직접 부르는 것**이다. 가장 현실적인 경로는 프롬프트 주입된 에이전트가 자기 셸 도구로 `header-helper`를 실행하는 것이다.
- **처리**
  1. **관리형 Linux(우리가 OS 통제를 가진 경로)**: AppArmor로 소켓 연결과 `header-helper` 실행을 **하네스 실행 파일 프로필에만** 허용하고, 하네스가 띄우는 자식 프로세스(셸 도구·MCP 서버)는 그 권한이 없는 프로필로 전이시킨다. ptrace는 Yama/AppArmor로 막는다. 이것이 "OS 강제 client identity"이며 구현 대상이다(sol 설계 작업으로 낸다).
  2. **관리형 Windows**: 같은 수준의 OS 강제 수단을 실측해 되면 적용하고, 안 되면 통제 범위에 「같은 계정의 다른 프로세스가 토큰을 받을 수 있음」을 표시한다.
  3. **직원 PC 키트(관리되지 않는 개인 계정)**: 같은 사용자 권한의 악성 프로세스를 키트가 막을 수 없다. 짧은 토큰 수명과 게이트웨이 판정으로 피해를 줄이는 것이 한계이며, `SECURITY_BOUNDARIES.md`에 **막지 못함으로 명시**한다. D-170의 「조직 통제 의존」으로 분류해 숨기지 않는다(다른 계정이 아니라 같은 계정 문제이므로 검토 판단을 따른다).
- **F2(웹 Origin)**: 세 지점 모두 브라우저가 직접 열 수 없는 전송이라는 정적 판단은 받는다. 그러나 「웹 페이지 접근 0」은 실기기에서 루프백 HTTP 수신 지점 전체를 대상으로 확인해야 완료다. PJ1 시험 항목으로 둔다.
- 백로그 DEV-81 상태: **열림 — 관리형 Linux AppArmor 프로세스 결속 구현·Windows 실측·키트 한계 명시·PJ1 Origin 시험 남음.**

## 구현 (2026-10-21, D-183, 미커밋)

**단계 전환을 포함한 부분 구현이며 F1은 아직 열림이다.** 기존 PJ1을 그대로 강제 모드로 전환하면 정상 헤더 명령도 차단된다. 배포·기기 실행은 하지 않았다. [작업 보고와 PJ1 절차](../../status/reports/2026-10-21-broker-process-binding.md)를 먼저 읽는다.

| 요구사항 | 구현·검증 | 남은 조건 |
| --- | --- | --- |
| BIND-01 커널이 강제한 클라이언트 신원 | `endpoint-agent/broker_binding.py`의 `authorize_peer`·`peer_label`: 기존 UID 검사에 `SO_PEERSEC`의 정확한 프로필 일치를 추가. `-bound-codex`, `-bound-claude`, 두 하네스에서만 직접 전이 가능한 고정 헬퍼 `-bound-credential`을 승인한다. 임의 credential 프로필·접두 일치·complain·stacked 레이블은 거부한다. | 고정 헬퍼는 토큰을 stdout으로 하네스에 돌려주는 최소 위임 예외다. 하네스 임의 자식 전체에 자격을 주는 것이 아니다. 실제 PJ1 레이블은 미확인. |
| BIND-02 자식 권한 분리 | `enforce-linux.py`의 `bound_profile`: 하네스의 bash/dash/sh·기존 명령·Codex companion은 모두 `px`로 `-bound-<하네스>-tool`에 전이. 도구·로그인·진입 프로필은 헬퍼 실행과 소켓 접근을 명시적으로 거부한다. 허용되지 않은 실행 파일은 기본 거부. | **현재의 `sh -c` 헤더 명령도 도구 프로필로 간다.** `dash ix`를 되살리면 F1이 재발하므로 호환성 우회로 채택하지 않는다. |
| BIND-03 메모리·디버그 경로 | 강제 프로필 모두에 `deny ptrace (trace, read, tracedby, readby)`, `deny capability sys_ptrace`, proc mem/environ 읽기 거부. AppArmor ptrace 기능도 브로커에서 확인한다. Yama 값은 운영 절차에서 읽어 기록하며 전역 sysctl은 변경하지 않는다. | 커널 효과·하네스 진단 기능 호환성 미검증. |
| BIND-04 실패 시 차단·PID 재사용 | 연결마다 AppArmor enabled, 정확한 필수 프로필 enforce 상태, Unix/ptrace 중재 기능을 확인. 읽기 실패·미로드·레이블 오류 시 활성 캐시가 있어도 강제 모드에서 응답하지 않는다. `/proc/<pid>/attr/current` fallback은 없고 PID는 커널 제공 감사 값으로만 쓴다. | `SO_PEERSEC` 미지원 기기는 강제 모드에서 차단된다. 커널 레이블은 연결의 보안 문맥이며 프로세스 내용이나 원격 증명이 아니다. |
| BIND-05 무중단 전환 | root 설정 `broker_binding=warn|enforce`. 기본·기존 설정 누락은 `warn`; 기존 프로필과 응답을 유지하고 레이블·고정 사유를 서비스 journal에 기록한다. 오타는 차단. 강제 프로필과 브로커 모드는 함께 전환해야 한다. | **경고 단계에서는 F1 노출이 유지된다.** 직접 실행 가능한 헤더 인증 경로와 두 실제 하네스 정상군을 먼저 확보해야 한다. 자동 강제 승격 없음. |
| BIND-06 설치·회귀 범위 | 설치기·Linux 다운로드 매니페스트에 모듈 포함, 프로필 로드 전에 `apparmor_parser -Q -T` 추가. 새 시험 `full_stack_lab/tests/header_broker_label_check.py` **20건 통과**. 기존 시험 파일·기대값·AST는 수정하지 않았다. | parser 없음·WSL 접근 거부로 실제 문법 검사는 **미완료**. 기존 회귀의 실패·생략은 아래 원시 기록 참조. |

재현: `python -B -X utf8 research/llm-wiki/analysis/local-endpoints-1021/verify_binding.py`.
[원시 명령·시각·출력·SHA-256](binding-checks.json), [합성 경로로 렌더링한 강제 프로필](binding-profile.apparmor). 수집기는 실패·도구 부재가 있으면 종료 코드 1을 낸다. 이 결과는 대역 단위/정적 검사이며 실제 MCP·커널 효과 증거가 아니다.

공식 근거: [AppArmor 4.0 정책 문법](https://gitlab.com/apparmor/apparmor/-/blob/v4.0.0/parser/apparmor.d.pod)의 실행 전이·Unix·ptrace 절, [Yama](https://docs.kernel.org/admin-guide/LSM/Yama.html). 공개 스킬/OSS 탐색과 판본·라이선스 확인 범위는 작업 보고에 기록했다. 외부 코드·설치 스크립트는 가져와 실행하지 않았다.

**범위 밖:** 관리형 Windows는 구현하지 않았다. 직원 PC 키트도 변경하지 않았다. 키트는 같은 사용자 프로세스의 헬퍼 실행·토큰 파일/메모리 읽기를 막지 못한다. [경계 문서](../../../../docs/ai/SECURITY_BOUNDARIES.md)의 D-183 절을 따른다. DEV-81의 Windows·웹 Origin·실제 하네스 검증은 계속 열림이다.
