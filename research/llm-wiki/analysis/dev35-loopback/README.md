# 관리 계정 루프백 차단과 하네스 로컬 통신 (DEV-35, 2026-10-15)

[작업 보고](../../status/reports/2026-10-15-dev35-loopback.md)의 근거 폴더다. 기준 코드: 통합 브랜치 `10/15-wbs-implementation` `b301e42`(작업 브랜치 `10/15-dev35-loopback`).
대상 장치: PJ1 `managed-8eea9cf7-ff2f-450f-8100-2bf20ac8126c`, 관리 계정 `managed-pj1`(UID 1001), 데스크톱 사용자 `pj1`(UID 1000).

## 결론

1. **10-15에 기록된 루프백 거부 399건은 전부 Codex의 ChatGPT 브라우저 로그인**이다. Claude Code 거부는 0건, 하네스 내부 IPC 거부도 0건이다.
   - 392건: PJ1 `pj1` 계정의 Firefox가 관리 계정 Codex 로그인 서버(127.0.0.1:1455·1457)에 연결했고, 그 서버가 보낸 **SYN-ACK 응답**(`SPT=1455|1457 … ACK SYN`)을 관리 UID 규칙이 거부했다.
   - 7건: 관리 계정 Codex가 이미 떠 있는 자기 로그인 서버에 `GET /cancel`을 보내려고 1455로 연 SYN(`DPT=1455 SYN`).
2. **정정**: 10-15 보고의 "Claude·Codex가 연 임시 포트 쌍(예: 57492/57506)"은 틀렸다. 그 포트는 Firefox가 연 두 연결의 **출발 포트**이고, 거부된 패킷은 Codex가 그쪽으로 보낸 응답이다.
   솔루션 DB `endpoint_os_events.details`가 nft 로그의 `SPT`와 TCP 플래그를 버리고 `DPT`만 남겨(`endpoint-agent/os-observer.py:52-54`) 응답 패킷이 "임시 포트로 가는 연결"처럼 보였다.
3. 현재 규칙은 관리 UID의 **모든** 루프백 패킷을 막으므로, 다른 UID가 관리 하네스의 리스너에 연결해도 응답이 막힌다. 그래서 브라우저 콜백 로그인은 구조적으로 실패한다.
4. 추천: **장치 코드 로그인 기본화(규칙 변경 없음)** + **소유자 UID가 시작한 루프백 연결에 한해 관리 UID의 응답 허용**(ct mark 2줄). PJ1 커널에서 일회용 netns로 시험해 E13 반례 7종이 그대로 막히는 것을 확인했다. 포트·기간 허용과 같은 UID 근사 규칙은 반례 때문에 기각한다. **적용·재설치는 하지 않았다(사용자 승인 대기).**

## 포트별 프로세스·목적

| 포트(거부 로그 원문) | 연 프로세스 | 목적 | 근거 |
| --- | --- | --- | --- |
| `SPT=1455 DPT=<임시> ACK SYN` 16쌍 352건 | 관리 계정 `/opt/mcpgw-approved/codex --no-daemon`(0.160.0)의 로그인 서버. 현재도 pid 5370이 `127.0.0.1:1455` LISTEN, UID 1001 | ChatGPT OAuth 콜백 `http://127.0.0.1:1455/auth/callback` | `ss -ltnpe`(17:11), `pj1-kernel-loopback-deny.log`, Codex `login/src/server.rs:77,193` |
| 위 `DPT=<임시>`(46846/46862, 57492/57506 등) | `pj1`(UID 1000)의 Firefox(pid 3898, 16:16 기동). 거부 로그에 UID 1000은 찍히지 않으므로 **간접 근거**: 관리 Codex가 브라우저를 못 열어(`No valid browsers detected`) URL을 사람이 데스크톱 브라우저에 붙였고, 각 시도가 TUI 로그인 시작 24–59초 뒤 두 연결로 들어왔다 | 브라우저의 콜백 요청 | `pj1-codex-login-log.txt`(15:07:58→15:08:57, 16:07:19→16:07:43, 16:17:25→16:17:49) |
| `SPT=1457 … ACK SYN` 1쌍 40건 | 같은 Codex의 **등록된 대체 포트** 로그인 서버 | 1455가 아직 점유 중일 때의 대체 콜백 | `server.rs:79`("Keep in sync with the Codex CLI Hydra redirect URI allow-list"), 로그 15:16:17 `falling back to the registered fallback port` |
| `DPT=1455 SYN` UID 1001 7건 | 관리 계정 Codex 자신 | 이전 로그인 서버 종료 요청 `GET /cancel`(재시도 전 1회). 실패하면 200ms×10회 재바인드 뒤 1457로 넘어간다 | `server.rs:618-690`, 로그 15:16:13 `Cancel onboarding auth step` 직후 SYN 3건 → 15:16:17 대체 포트 |
| (10-14) `DPT=22·3015·3016` 14건 | 관리 계정 시험 프로세스 | 10-14 E13 시험에서 `pj1`의 `ssh -L` 리스너로 가려던 연결. **정상 차단**(E13) | [10-14 E13 로그](../pj1-local-mcp-e13/README.md) |

각 시도는 약 70초간 쌍마다 22번(SYN 재전송과 SYN-ACK 재전송) 거부되고, 약 21초 뒤 사용자가 다시 시도하면 새 쌍이 생긴다. 솔루션 DB 집계(352+40+7=399)와 PJ1 커널 로그(392+7)가 일치한다(`appliance-endpoint_os_events-loopback.txt`).

## 하네스의 루프백 사용처 (공식 문서·고정 소스)

| 하네스 | 루프백 사용 | 관리 계정에서 | 근거 |
| --- | --- | --- | --- |
| Codex 0.160.0 | ChatGPT 브라우저 로그인 콜백 1455, 대체 1457, 재시도 전 `/cancel` 자기 연결 | 이번 거부의 전부 | `openai/codex` `rust-v0.160.0` = `a956835d020762cb2b570053af06f643a11c0ecc`(Apache-2.0) `codex-rs/login/src/server.rs:77-79,193,528,618-690` |
| Codex | 장치 코드 로그인: `auth.openai.com/api/accounts/deviceauth/{usercode,token}` 폴링, 루프백 없음. TUI 두 번째 선택지 "Sign in with Device Code", CLI `codex login --device-auth` | 모델 프록시 허용 도메인 `(^|\.)openai\.com$`에 포함. **PJ1에서 실제 완료는 미확인** | `login/src/device_code_auth.rs:165-206`, `tui/src/onboarding/auth.rs:352-372`, [공식 문서](https://learn.chatgpt.com/docs/auth)(개인 계정은 ChatGPT 보안 설정에서 장치 코드 로그인을 켜야 함, 워크스페이스는 관리자 권한) |
| Codex | TUI ↔ app-server: **in-process**(루프백·소켓 없음), 공유 데몬은 Unix 소켓이라 키트가 `--no-daemon`으로 끔(D-72) | 거부 없음 | `logs_2.sqlite`의 `rpc.transport="in-process"`, `enforce-linux.py` `fixed_options` |
| Codex | MCP OAuth 콜백(`mcp_oauth_callback_port`), `app-server --listen` | 이번에 관찰 없음. 관리 계정의 MCP는 게이트웨이 하나라 OAuth 콜백 불필요 | 바이너리 문자열(설정 키 존재만 확인, 경로 미시험) |
| Claude Code 2.1.288 | 로그인 시 `http://localhost:<임의 포트>/callback` 리스너 + 수동 URL(`https://platform.claude.com/oauth/code/callback`, 화면에 코드 표시 → `Paste code here if prompted`) | 관리 계정은 브라우저를 열 수 없어 수동 URL 경로가 된다. 10-15 Claude 루프백 거부 0건 | 바이너리 문자열(`redirect_uri` = 수동이면 `MANUAL_REDIRECT_URL`, 아니면 localhost), [공식 문서 Log in](https://code.claude.com/docs/en/authentication)("browser can't reach Claude Code's local callback server … paste it") |
| Claude Code | `claude setup-token`(1년 토큰, `CLAUDE_CODE_OAUTH_TOKEN`) | 대안. 다만 토큰을 환경 변수로 넣어야 해 키트의 "토큰을 설정·환경에 쓰지 않는다" 불변식과 충돌 → 채택하지 않음 | 같은 문서 "Generate a long-lived token" |

## 선택지와 반례

시험: PJ1 커널(7.0.0-38-generic)에서 일회용 컨테이너(독립 netns, `--cap-add NET_ADMIN`)에 키트의 `nft_rules()`를 그대로 렌더링해 적용하고 UID 1000(소유자)·1001(관리)·1002(다른 사용자)로 리스너/클라이언트를 돌렸다. PJ1 호스트 규칙은 건드리지 않았다. 원본 `lab/lab.py`·`lab/lab2.py`·`lab/output.txt`.

| 선택지 | 해결 범위 | E13(관리 UID → 비인가 로컬 MCP) 영향 | 반례·한계 | 판정 |
| --- | --- | --- | --- | --- |
| A. 장치 코드 로그인만 | Codex 로그인 전부(브라우저 콜백 불필요). 설치기는 이미 `codex login --device-auth`를 쓴다(`bootstrap.py:371`) | 규칙 변경 없음 → 약화 없음 | 개인 계정은 ChatGPT 보안 설정에서 켜야 하고 조직이 끌 수 있다. 첫 실행 TUI는 브라우저 로그인이 1번이라 사람이 1번을 고르면 지금처럼 실패 | **채택(기본)** |
| B. 소유자가 시작한 루프백 연결의 응답만 허용 (ct mark) | 데스크톱 브라우저 → 관리 Codex 1455/1457 콜백, Claude localhost 콜백 | 시험 7종 그대로 차단: 관리→소유자 리스너(IPv4·IPv6), 관리→다른 UID, 관리→소유자 UDP, 관리→관리(`/cancel`)도 여전히 차단 | 소유자 UID의 아무 프로세스나 관리 하네스 리스너에 붙을 수 있다. 다만 소유자는 이미 NOPASSWD 런처로 관리 하네스를 직접 실행할 수 있어 새 능력은 아니다. 다른 UID(1002)는 여전히 차단. 관리 계정에서 리스너를 여는 것은 승인 하네스 바이너리뿐(AppArmor: 인터프리터 없음, bash는 listen 불가) | **채택(보조, 승인 후)** |
| B′. 같은 관리 UID 소켓으로만 허용 | Codex `/cancel` | nft `meta skuid`는 **보내는 소켓**만 본다. output 훅에서 목적지 소켓 소유자를 고를 수 없다. 근사안(관리 SYN 통과 → 다른 UID의 응답을 RST로 거부)은 관리→관리 성공·관리→소유자 실패였지만 | 관리 UID의 SYN 자체는 다른 UID 리스너의 커널까지 간다(이번 50ms 폴링에서 `SYN_RECV` 관찰은 0건 — 미입증이지 부재 증명 아님). UDP는 같은 방식으로 막을 수 없다. 필요한 경우가 `/cancel` 하나뿐이고 A로 사라진다 | 기각 |
| C. 특정 포트(1455·1457) 허용 | Codex 콜백·`/cancel` | **약화**: 1455가 비어 있을 때 다른 UID가 1455를 열면 관리 UID가 그곳에 연결·송신 가능 | `lab2`: `managed -> OWNER listener squatting 1455` **REACH**(`pong:ping`). 관리 계정 bash `/dev/tcp/127.0.0.1/1455`로 비인가 로컬 서버와 통신 가능. Claude는 임의 포트라 포트로 못 정함 | 기각 |
| D. 기간 허용(로그인 중 몇 분) | 위와 같음 | 그 기간 동안 C와 같은 구멍 | 기간이 반례의 창. 로그인 시점 판단을 하네스 밖에서 해야 함 | 기각 |

PJ1 사실(17:2x 읽기): Tailscale이 `ip mangle`에서 ct mark의 `0xff0000` 비트를 connmark로 저장·복원한다. 그래서 B는 ct mark **전체를 덮어쓰지 않고** `0x100` 한 비트만 OR로 켠다(첫 시험의 `0x4d475731` 덮어쓰기안은 그 필드와 겹쳐 폐기). `net.ipv4.tcp_fastopen = 1`(클라이언트만).

## D-119 채택·구현 (2026-10-17, 배포 전)

2026-10-17 사용자가 추천안을 채택했다. [D-119](../../../../docs/ai/DECISIONS.md)와 [구현·검증 보고](../../status/reports/2026-10-17-loopback-owner-replies-d119.md)가 현재 기준이다. 위의 승인 대기·미적용 설명과 아래 R1~R9는 10-15 조사 시점의 이력이다. `lab/`의 원본·해시는 보존했다. 이번 작업은 로컬 구현·단위 검증까지이며 과거 PJ1 실험을 새 판본 통과로 세지 않는다.

1. `endpoint-agent/bootstrap.py`는 기존 설치 중 `codex login --device-auth` 실행을 유지하고 설치 완료 후에도 같은 명령을 안내한다. 영어 TUI 선택과 브라우저 실패 설명은 제거한다. 장치 코드가 거부되면 기존 ChatGPT 보안 설정 안내로 재시도한다.
2. `endpoint-agent/enforce-linux.py` `nft_rules(uid, …, owner_uid)`: 설치기가 확인한 직원 계정 UID를 별도 관리 계정에만 명시적으로 전달한다(`bootstrap.install_managed` → `managed-linux.py --owner-uid` → 집행기). 원시 `SUDO_UID`를 집행기에서 읽지 않는다. 소유자를 지정하지 않으면 기존 전면 거부를 유지한다. 등록 토큰 소비 전에 소유자 UID·실제 계정 존재를 검사하고 관리 계정 자신을 소유자로 지정하면 실패한다. accept 줄 앞에는 다음만 추가한다.
   ```
   oifname "lo" ct direction original ct state new meta skuid <owner> ct mark set ct mark or 0x00000100
   meta skuid <managed> oifname "lo" ct direction reply ct mark and 0x00000100 == 0x00000100 accept
   ```
   관리 UID가 **시작한** 루프백 연결(원래 방향)은 이 줄과 무관하게 지금처럼 거부된다. 원격 호스트가 관리 리스너에 붙는 경우(`oifname` ≠ `lo`)도 그대로 거부된다.
3. `endpoint-agent/os-observer.py`의 D-113 구현(`SPT`·TCP 플래그·`listener_reply`)은 유지한다. 허용 응답은 앞의 accept에서 끝나 거부 접두사 로그가 생성되지 않는다. 소유자 이외의 연결에 대한 응답 거부는 계속 기록하며, 로그를 숨기거나 원장을 고치지 않는다.

| 원자 요구사항 | 코드 심볼 | 오프라인 검증 | 실기기 확인(미실행) |
| --- | --- | --- | --- |
| DEV35-01 소유자 original/new에만 표식 | `nft_rules` | `OwnerReplies.test_only_owner_original_new_marks_and_managed_reply_accepts` | IPv4·IPv6 콜백 정상, 다른 UID 응답 거부 |
| DEV35-02 0x100만 OR/AND, 기존 비트 보존 | `nft_rules` | `test_mark_is_one_bit_and_preserves_tailscale_and_other_bits` | 실제 Tailscale connmark 전후·마스크 대조 |
| DEV35-03 관리 출발·포트 선점 차단 유지 | `nft_rules` | 허용 규칙 전체 목록·최종 reject 검사, owner 미지정·경계값 거부 | E13 7종·새 SYN·UDP·원격, netns 규칙 적용/실패/재적용 |
| DEV35-04 확인한 직원 UID 전달 | `bootstrap.main`·`install_managed`, `managed-linux.install` | 별도 관리 계정일 때만 전달, 환경 SUDO_UID 미사용 | 저장 owner_uid·설치 egress.nft·커널 baseline·재부팅 일치 |
| DEV35-05 장치 코드 기본·실패 시 경계 유지 | `LOGINS`·`harness_login` | 성공·실패·Ctrl+C 모두 장치 코드만 실행 | R2 실제 로그인, 장치 코드 비활성/폴링 중단 후 재시도 |
| DEV35-06 허용 응답의 거부 오인 방지 | `os-observer.event` | 접두사 없으면 이벤트 없음, 거부 응답·SYN 기존 분류 | R1·R6 커널 원문·관측 이벤트·리스너 수신 세 곳 대조 |

단위 시험 정본은 `full_stack_lab/tests/loopback_owner_replies_test.py`다. 실험 명령·E13 7종의 정확한 구분·경쟁/복구 조건은 새 작업 보고에 있다.

## E13 회귀 시험 계획 (D-119 채택, 메인 실행 대기)

적용 전·후 같은 조건으로 돌리고, 각 줄의 판정 근거는 커널 `MCPGW_DENY` 원문·`endpoint_os_events`·리스너 측 수신 로그 세 곳으로 확인한다.

| ID | 조건 | 기대(적용 후) |
| --- | --- | --- |
| R1 | `pj1` Firefox → 관리 Codex TUI "Sign in with ChatGPT" | 로그인 완료, 1455/1457 SYN-ACK 거부 0건 |
| R2 | 관리 Codex TUI "Sign in with Device Code" (규칙 변경 전에도) | 로그인 완료, 루프백 패킷 0건 |
| R3 | 관리 Claude `/login`, 수동 URL 코드 붙여넣기 | 로그인 완료, 루프백 거부 0건 |
| R4 | `pj1`이 연 비인가 로컬 MCP(10-14 E13과 같은 실제 OSS 서버, 등록·승인하지 않음)에 관리 계정 Claude·Codex가 자연어로 접근 | 수신 0, `DPT=<서버 포트> SYN` 거부 기록 — **10-14 결과와 동일** |
| R5 | 관리 계정 bash `/dev/tcp/127.0.0.1/1455`·`::1`·UDP로 `pj1` 리스너(1455 선점 포함) | 모두 거부 |
| R6 | 다른 로컬 사용자(UID ≠ 소유자) → 관리 Codex 1455 | 거부 |
| R7 | 원격 호스트(tailnet) → PJ1 관리 리스너 | 거부 |
| R8 | 정상군: 승인된 context7·github 호출, 모델 프록시 | 지금과 동일 |
| R9 | 재부팅 후 R1·R4 | 규칙 지속(systemd unit `nft -f`) |

R4·R8의 MCP는 사람이 이미 승인한 정상군과 등록하지 않은 실제 OSS 비인가 서버만 쓴다. 시험 대상 MCP를 에이전트가 신청·승인·등록하지 않는다(D-79).

## 한계

- Firefox가 콜백 연결을 연 주체라는 점은 시간 상관과 `pj1` 프로세스 목록에 기댄 **간접 근거**다(UID 1000 패킷은 로그 대상이 아님). 브라우저 기록은 읽지 않았다.
- PJ1의 Codex 바이너리 해시(`12eb3e81…`)를 공식 릴리스 자산과 대조하지 않았다. 소스 해석은 `rust-v0.160.0` 태그 기준이다.
- Claude Code는 공개 소스가 아니어서 바이너리 문자열과 공식 문서로만 확인했다. Claude의 MCP OAuth·IDE 연동 루프백은 관리 계정 설정상 쓰지 않아 시험하지 않았다.
- B는 일회용 netns 실험이며 PJ1 호스트 규칙에 적용한 결과가 아니다. 장치 코드 로그인의 PJ1 실제 완료도 미확인(사람이 계정에서 해야 함, 자격을 빌려 쓰지 않는다).
- B′의 "SYN이 다른 UID 커널에 닿는다"는 설계상 판단이며, 사용자 공간 관찰은 이번에 0건이었다.

## 원본

| 파일 | 내용 | SHA-256 |
| --- | --- | --- |
| `pj1-kernel-loopback-deny.log` | PJ1 `journalctl -k -b -1/0`의 10-14~15 루프백 `MCPGW_DENY` 413줄(MAC 제거) | `3353f4a7337326ec243bd81239bd9c3c63b9b34133e9b110e90f960628cf0c4e` |
| `pj1-codex-login-log.txt` | 관리 Codex `~/.codex/logs_2.sqlite` 로그인 관련 행(읽기 전용, 코드·state 가림) | `8b582af99ffb1a960d06cf5e91921555db8f6b5329f7e707f162213d412ca8c9` |
| `appliance-endpoint_os_events-loopback.txt` | 솔루션 DB 루프백 거부 집계 | `24cb7e8f4baed4fedb929c23b9f7b9d19da2f552d3ba5fe37ca09221463ba2ee` |
| `lab/lab.py` | 현재·추천 규칙 시험 | `546be1f386a4811b085ce212ff3409e79ef24403540c32673f50882ced9507c9` |
| `lab/lab2.py` | 기각 선택지 반례 | `b5aa5394edf3c797d89bf38ae89f578ca382e88d7ed731c6b6f48d7ca6182b62` |
| `lab/output.txt` | 두 시험 출력 | `8d38ebb6a0609697cbf3e20c8aa2afb225bd715e1b1c826a13c18035a66d8920` |

PJ1 확인은 모두 읽기 전용(`pj1` docker 그룹 nsenter, 비밀번호 미입력)이었고, 사람이 연 관리 계정 세션(pts/3, Codex pid 5370)은 그대로 두었다.
