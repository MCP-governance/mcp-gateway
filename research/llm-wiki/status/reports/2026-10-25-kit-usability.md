# 2026-10-25 엔드포인트 키트 편의·자동화 — 간편 모드 기본, 자동 활성화, Windows 같은 계정, TUI (D-239)

- 작업자: Claude Code (Opus 5.5), 세션 `kit-usability`
- 코드 기준: `10/25-policy-sync-split` 끝 `cbc5195`(D-238 포함)에서 분기, 브랜치 `10/25-kit-usability`(통합 브랜치 `10/25-integrate` 위로 rebase).
  1단계 `3090e75`·`532b2d9`, 2단계 실측 수정 `eec3e22`·`cb663ff`·`8bd0040`·`383ee4d`·`9f9d04f`·`0ba8b38`. 기기 배포본은 리더가 4c060ef → 4679160 → 283d93e로 올렸다
- 시작 근거: 소유자 지시(10-25 저녁) 「보안을 좀 느슨하게 하더라도 키트 편의·자동화 극대화, Windows 메인, GUI 못 띄우면 TUI」,
  지시서 `지시서_세션배분_20261025.md` S1, 10-25 제안서 P0-3(이 지시로 대체), 10-23 키트 결함 D-216~D-232
- 완료 조건(지시서): ① 구현·단위·Windows unittest·CI 수용 시험·보고서 1차 → 브랜치 push → ② 리더 배포 뒤 pj2·pj3 실측 → 보고서 최종
- **현재 단계: ①·② 완료.** 재부팅 항목은 소유자 콘솔 로그인 뒤 확인했고, 기기 배포본 main v0.9.0(4edec39) 그대로의 원클릭도 확인했다. 실측은 아래 「2단계 실측」.

## 결과

### 1. 간편 모드가 기본(Linux·Windows)

| 항목 | 간편 모드(기본) | 격리 계정(고급, 기존 코드 그대로) |
| --- | --- | --- |
| 선택 | 기본 | Linux `install.sh --isolated`, Windows 마법사 「고급: 격리 계정」, 콘솔 「내 PC 연결 → 고급: 격리 계정」(`enrollment.json`의 `"isolated": true`) |
| 실행 계정 | 로그인 중인 직원 계정(관리자·표준, 로그아웃 없음) | `managed-<직원>` / `mcpgw-<직원>` |
| 하는 일 | 관리형 설정, 헤더 헬퍼(sh 스크립트), root/SYSTEM 보고 서비스, `mcpgw-status`, CA 환경 | + AppArmor·nft(Windows SID 방화벽)·sudoers·shim·셸 함수·홈 런처·하네스 복사 |
| 안 하는 일 | 관리 계정·AppArmor·nft·sudoers·shim·rc 블록·홈 런처 루프·gcc·하네스 복사·방화벽 | — |
| 패키지 | curl·openssl·컨테이너 엔진 시도(실패해도 계속, D-225) | gcc·nftables·apparmor-utils·curl·openssl 필수 |
| 활성화 | 설치 점검 통과 시 게이트웨이 자동(설정으로 끔) | 관리자 |
| 통제 범위 | `observed_only` 「간편 모드 · 게이트웨이 판정 적용」 | `endpoint_enforced` / `bypass_possible` |

코드: `bootstrap.connect`(모드 분기·이전 설치 원복·격리 계정 정리), `managed-linux.install --mode simple`(헬퍼 스크립트·
`/etc/environment` CA 블록·간편 점검 `protected_configs`), `broker_binding`의 `uid` 결속, `managed-windows.install`(같은 계정·
`previous_installs`·`retire_companion`·CA 사용자 환경·`WM_SETTINGCHANGE`), `windows-oneclick.ps1.in`(`isolated_account=$isolated`),
`windows-worker.ps1`(재설치 거부 제거·트레이 즉시 시작).

### 2. 자동 활성화(게이트웨이)

`/oauth/device-enroll`이 `mode`를 받아(`simple`/`isolated`, 없으면 isolated) `detail.mode`에 둔다. heartbeat가 ① 간편 모드 ② 대기 중
③ 통제 해시·`protected_configs` 통과 ④ `endpoint_settings.auto_activate`(기본 켬) ⑤ `held_from` 없음이면 같은 UPDATE에서 `active`로
바꾸고 원장에 `activated`(처리 `auto`)를 남긴다. 격리 계정·끈 설정·격리된 장치·보류된 PC 재설치는 관리자. 격리 계정 재설치는 자동
활성화를 이어받지 않는다. 모드 전환(격리→간편)은 이전 동반 계정 장치를 같은 PC의 이전 장치로 찾아 폐기·이어받는다(`companion_names`).
콘솔 사용자·엔드포인트 → 엔드포인트 표 위 「새 PC 활성화: 자동/관리자 확인」(`PUT /api/endpoint/settings`, 관리자), 장치 상태 옆
「간편 모드/격리 계정」. 「내 PC 연결」은 Windows를 먼저 고르고 3단계를 「설치가 끝나면 바로 사용」(끔이면 「관리자 활성화 뒤 사용」)으로 보인다.

### 3. 설치 끝 세 칸(자격 파일 존재로 성공 처리하지 않음)

| 칸 | 측정 | Linux | Windows |
| --- | --- | --- | --- |
| 모델 응답 | 직원(또는 격리 계정) 하네스의 `claude -p "Reply with the single word OK."`(없으면 `codex exec`) 종료 코드·출력 | 설치기 끝, 활성화 대기 중에도 | 트레이 「연결 확인」(첫 활성화 때 1회 자동) |
| 도구 | 직원 하네스와 같은 헤더로 승인 서버마다 `initialize`→`tools/list` 도구 수 | 설치기·`mcpgw-status --check` | 트레이 |
| 서버 연결 | 승인 서버 1건 `initialize` 성공 | 〃 | 〃 |

도구는 호출하지 않는다. 헤더 값·모델 응답 본문은 기록하지 않는다(`agent.connection_check`·`model_check`).

### 4. TUI·GUI

- Linux 설치기·`mcpgw-status`: `curses` 풀화면(단계 ✓/…/✗·초, 세 칸, 「다음 할 일」 반전 줄). 비대화형·UTF-8 로캘 없음이면 한 줄 출력.
  마지막 화면 내용은 끝난 뒤 스크롤백에 남는다. `mcpgw-status`는 2초 갱신, `q` 닫기, `c` 연결 확인. 상태 글 마지막 줄은 항상 「다음 할 일」
  (대기·격리·폐기·서비스 무응답·설치 전 터미널의 CA 변수 없음 → 「새 터미널」).
- Windows 트레이: 상태 창(연결·관리 상태·모드·승인 서버 목록·하네스 판본·세 칸·게이트웨이·다음 할 일), 메뉴(상태 창·연결 확인·모델 로그인
  ▸Claude/Codex·다시 연결·최근 차단·콘솔 열기·English/한국어·제거). 다시 연결은 게이트웨이 점검 후 서비스가 멈췄으면 UAC로 예약 작업 시작.
  첫 보고 전에는 「연결 준비 중」. 설정 마법사: 한/영 전환, 「고급: 격리 계정」 체크, 실패 사유 뒤 「다음: …」 한 줄.
- `windows_status.py <status.json>`: 콘솔 글 상태(embeddable Python에 curses가 없어 TUI 대신).

### 5. Windows 관측(D-220은 Windows 제외)

SYSTEM 서비스가 하네스 판본(직원 실행 파일을 실행하지 않고 `~/.local/share/claude/versions`·npm `package.json`·WinGet·Codex 실행 파일의 버전 리소스에서 읽음 — pj3 claude 2.1.302, codex.exe는 리소스 없음), 관리형 설정
해시(heartbeat 기존), 게이트웨이 연결(heartbeat 기존)을 보고한다. 판본은 heartbeat `host.harnesses`(새 선택 필드)와 트레이 `status.json`에 간다.
Linux도 같은 필드로 `claude/codex --version`(직원 UID로 실행)을 보낸다.

## Linux 10-23 결함의 Windows 대응표

| 결함 | 내용 | Windows | 근거 |
| --- | --- | --- | --- |
| D-216 | 하네스 없을 때 설치 중단 | 수정함(간편 모드) — 하네스가 없어도 설치, 판본만 비움. 격리 계정은 지금처럼 거부 | `managed-windows.install`의 `harness_versions` |
| D-217 | 재설치 연속성 | 수정함 — 작업자의 「기존 엔드포인트 제거 후 재설치 필요」 거부 삭제, 설치가 이전 설치(두 모드)를 먼저 원복, 게이트웨이가 같은 PC 동반 계정 장치도 이전 장치로 처리 | `previous_installs`, `companion_names`, `kit_continuity_check` |
| D-218 | 부분 설치 원복 멱등 | 부분 확인 — `rollback`이 없는 작업·규칙·파일을 건너뜀(코드 검토). 부분 설치 실측은 미실행 | `managed-windows.rollback` |
| D-229 | 옛 코드로 원복 | 해당 없음 — 설치는 새 키트 파일을 `Program Files`에 먼저 쓴 뒤 그 코드로 원복 | `windows-worker.ps1` 순서 |
| D-216 계열 b225285 | 설치 직후 상태 「실패」 | 수정함 — 트레이가 첫 보고 전 「연결 준비 중」 | `tray.ps1` `preparing` |
| D-238 | 상태 안내문이 해시에 | 해당 없음(게이트웨이 수정, 키트 공통) | D-238 |
| 723a369·47c37f7 | 설치 실패 진짜 사유 | 수정함(범위 한정) — 고정 사유 + 「다음: 무엇을 누를지」 한 줄. 하위 프로세스 원문은 개인정보 우려로 기존처럼 비노출 | `Get-EndpointNextAction` |
| D-223 | 승인 폴더 자동 생성 | 해당 없음 — Windows 로컬 MCP 실행 경로 없음 | — |
| 41095eb | 실패 로그에 게이트웨이 사유 | 해당 없음 — 로컬 실행기 Linux 전용 | — |
| (제거 뒤 복원) | 관리형 파일 백업이 키트 자신의 렌더링이면 제거 때 관리형 설정이 원본으로 남음 | 수정함(Linux·Windows) — 키트 렌더링은 백업하지 않음(`ours`) | `kit_simple_mode_check` |

실측(pj3, 「2단계 실측」): 재설치 연속성은 격리된 이전 장치 뒤 재설치가 `held_from`으로 대기(설계대로), 폐기 뒤 재설치는 자동 활성화로 확인.
원복은 작업자 제거 경로에서 예약 작업·관리형 파일·직원 config.toml 블록·CA 환경 변수·프로그램 폴더가 모두 사라짐을 확인(D-218 행 「부분 확인」 → 제거 경로 확인).
실측에서 이 표 밖의 Windows 결함 8건이 더 나왔다(「S1 몫 결함」).

## 간편 모드가 포기하는 것

- 직원 계정의 임의 프로세스(셸·SDK·다른 클라이언트·악성 코드)가 헤더 헬퍼를 불러 MCP 토큰을 받을 수 있다. UID가 유일한 경계다.
- UID egress 차단이 없다. 하네스와 임의 프로세스가 게이트웨이를 거치지 않고 외부 MCP·인터넷으로 직접 나갈 수 있다(Windows SID 방화벽도 없음).
- 직원 설정의 명령 헬퍼(D-148)는 기록만 하고 격리 사유가 아니다. 하네스 바이너리 고정(SHA-256)·실행 파일 제한·셸 분리가 없다.
- 남는 것: 게이트웨이 호출 전 판정·계약 고정·동의·사용 대상·출력 통제·원장, 관리형 설정(미승인 커넥터·웹 도구·계정 플러그인 끔),
  root/SYSTEM만 가진 장치 키, 짧은 토큰·180초 heartbeat 만료·폐기, 통제 해시 불일치 격리(D-238).
- 전제: 엔드포인트 우회는 다른 조직 통제(EDR·DLP·프록시)가 받친다. 그렇지 않은 조직은 「고급: 격리 계정」.

## 검증

| 확인 종류 | 명령·환경·실행 시각(10-25) | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 회귀 기준선(작업 전) | `run_local_suite.py`, Windows 노트북 venv 3.12 | 통과 108 · 실패 6 · 외부 의존 17 | scratchpad `baseline.json` |
| 회귀(최종) | 같은 명령, 코드 9f9d04f(통합 브랜치 283d93e 위) | 통과 116 · 실패 4(acceptance_tls·output_credential_span·sbom_impact·threat_trace_mapping — 전부 기준선 실패) · 외부 17 · **새 실패 0** | scratchpad `after4.json` |
| 새 시험 | `endpoint_auto_activation_check`(4: 자동 활성화·끈 설정·격리·보류·격리 장치·점검 실패·옛 키트·간편 장치 관리형 설정 CA), `kit_simple_mode_check`(11: 모드 분기·CA 블록·간편 점검·백업 금지·설치 확인 HTTP 대역·모델 응답·하네스 명령줄 S4-03·브로커 UID) | 통과 | 로컬 |
| 고친 시험 | `kit_continuity_check`(모드·held_from·두 방향 모드 전환·자동 활성화 상속 금지·다음 할 일·철회 서버 S4-11), `kit_install_upfront_check`, `user_command_settings_check`, `managed_policy_gap_check`, `macos_kit_check`, `connector_control_check`, `loopback_owner_replies_test`, `notion-bugs-ui.test.mjs` | 통과 | 로컬 |
| Windows 키트 | `py -3 -X utf8 -m unittest discover -s endpoint-agent/tests-windows` | 31 통과(따뜻한 실행). 첫 냉실행에서 `test_managed_request_is_snapshotted…`가 PowerShell 30초 한도에 걸리는 기존 간헐 오류 | 로컬 |
| PowerShell 실행 시험 | `REMOVE_COMPANION`·`STOP_SERVICE`를 실제 PowerShell로(없는 계정·없는 규칙), `Read-EndpointManagedRequest` 원클릭 모양 요청(옛 코드에서 실패 확인), runtime-check 모듈 집합(옛 코드에서 실패 확인) | 통과 | 로컬 |
| 콘솔·정적 | `node --check`, `node --test tests/*.test.mjs`, pyflakes 전체, `open_endpoints.py` | 통과·0건·PASS | 로컬 |
| 실제 Linux | WSL pty: `bootstrap.py --self-check`, curses 화면·평문 폴백 | OK | 로컬 |
| 위키 | `refresh_generated.py`, `check_trace.py`·`check_enterprise_analysis.py` rc 0, `check_wiki.py` 오류 29(전부 Git 제외 `local-sources/compliance/*` 부재, 기존·새 오류 0) | — | — |
| CI 수용 | `acceptance.py endpoint-simple-mode-auto-activation` | 리더 통합 CI에서 실행(이 세션 미실행) | — |
| 실기기 pj2 | 아래 「2단계 실측」 | **통과**: 사람 개입 0, 설치 6초·확인까지 32초·자동 활성화 4초, Learn·DeepWiki·filesystem Allow | 원장 1272~1275 |
| 실기기 pj3 | 아래 「2단계 실측」 | **통과**: UAC 1회 대행, 설치 15초·활성 17초, 트레이 자동 확인 정상, Learn·DeepWiki 실행, 끊김 복귀 6초, 제거·재설치, 재부팅 뒤 서비스 자동 재연결(부팅 28초)·트레이 로그온 시작, 배포본 원클릭 23초 | 원장 1284·1285·1287~1289 |

## S1 몫 결함(실측·S4에서 나온 것)

| ID | 내용 | 처리 |
| --- | --- | --- |
| pj2-① | 격리 모드 무인 설치가 모델 장치 코드 로그인에서 최대 15분 멈춤 | eec3e22 |
| pj2-② | 간편→격리 전환 뒤 직원 계정 장치가 활성으로 남음 | eec3e22 |
| pj2-③ | 설치 전 터미널의 Claude가 사설 CA를 몰라 MCP 연결 실패 | eec3e22(관리형 설정 `env`), Codex는 새 터미널 안내 |
| pj3-① | 원클릭 요청 검사가 없는 속성에 대입 → 모든 원클릭 설치 실패(10-18부터) | cb663ff |
| pj3-② | 원클릭으로 설치한 PC가 새 판본 원클릭을 거부 | cb663ff(표식 승인 갱신) |
| pj3-③ | runtime-check가 tomli·toml을 요구 → 모든 Windows 설치 실패(10-23 D-232부터) | 8bd0040 |
| pj3-④ | 동반 계정이 없으면 PowerShell 종료 코드 1로 간편 설치·제거 실패 | 8bd0040 |
| pj3-⑤ | 자동 활성화 직후 최대 60초 「활성화 대기」 안내문(Linux·Windows) | 8bd0040 |
| pj3-⑥ | 재설치가 실행 중 서비스의 런타임을 덮어써 python.exe 소실 | 9f9d04f |
| pj3-⑦ | 직원 Codex 앱이 config.toml을 다시 쓰면 블록 해시 불일치로 PC 격리 | 383ee4d(간편 모드는 heartbeat 전 블록 복원) |
| pj3-⑧ | WinGet Claude 판본 「—」 | 8bd0040(실행 파일 버전 리소스) |
| S4-03 | 하네스 명령줄의 직원 프롬프트(`modelcontextprotocol…`)가 섀도 stdio MCP로 → `MCP-SHADOW-002` 오탐 | 9f9d04f(claude·codex 실행 파일과 그 npm 패키지를 실행하는 node는 제외, 하네스가 띄운 서버는 그대로 검사) |
| S4-11 | `mcpgw-status`가 1시간 안에 철회된 서버를 「새로 반영된 서버」로 표시 | 9f9d04f |
| pj3 `node_repl` | pj3 호출이 Alert `MCP-SHADOW-002` — 원인은 직원 `~/.codex/config.toml`에 Codex 앱이 둔 실제 stdio MCP 항목(설정 인벤토리) | 결함 아님(간편 모드는 직원 계정 설정을 그대로 관측한다). 실행은 됐다. Codex 앱 기본 항목을 허용 목록으로 둘지는 소유자 판단 |
| 자기 회귀 | eec3e22의 `managed_mode` 호출이 `managed_policy`만 적재하는 시험 3개를 깨뜨림(통합 브랜치에 들어감) | 9f9d04f |

## 실패·미완료·한계

- pj3 재부팅 뒤 SSH(들어오는 연결)는 소유자가 콘솔에 로그인할 때까지 닿지 않았다(원인 미확인 — 로그인 전 네트워크 프로필·방화벽 또는
  Tailscale 들어오는 연결로 추정). 관리형 서비스의 나가는 연결은 로그인 없이 부팅 28초 뒤 다시 붙었다.
- pj3 원클릭 5차는 이 브랜치 키트를 기기 다운로드 파일에 다시 묶은 것이다(그때 9f9d04f가 기기에 없었다). 기기 배포본 그대로(4edec39)의 원클릭은 뒤에 따로 확인했다.
- UAC 「예」는 사람이 눌러야 한다. SSH 비대화형 세션은 보안 데스크톱에 닿지 않아, 직원 세션의 관리자 권한 예약 작업으로 대행했다.
- 트레이 상태 창·언어 전환·콘솔 열기·모델 로그인 단추는 클릭 자동화 없이 화면 렌더링을 보지 못했다(백엔드 명령·구문 검사·캡처의 완료 대화 상자만).
- Windows 관리형 Codex 블록은 직원 파일이라 간편 모드는 되돌리기만 한다. Codex 앱이 표식을 지우고 표를 남기는 식으로 다시 쓰면 표가 겹칠 수 있다(관찰되지 않음).
- `/etc/environment`·사용자 환경 변수는 새 로그인·새 프로세스부터다. Claude는 관리형 설정 `env`로 해결했고 Codex는 새 터미널이 필요하다.
- 같은 PC의 서로 다른 두 직원을 모두 관리형으로 연결하면 기계 공용 Claude 설정을 서로 덮어쓴다(pj3의 옛 `pj3user` 설치). 한 PC 한 직원을 전제로 한다.
- Windows 서비스의 설정 인벤토리 관측기(`agent.py --once`)가 프로세스 스냅숏 「partial」 때 종료 코드 1이라 로그에 `CalledProcessError`가 간헐로 남는다(보고는 됨, 기존 동작).
- 옛 게이트웨이는 등록 `mode`·heartbeat `host.harnesses`를 422로 거부한다 — 게이트웨이를 먼저 배포한다.
- `research/llm-wiki/status/current.md`·`backlog.md`는 S3 소유라 고치지 않았다.

## 방향 제안

- Codex 데스크톱 앱 기본 MCP(`node_repl` 등)를 섀도에서 「벤더 내장」으로 분류할지 소유자 결정이 필요하다(지금은 Alert, 실행은 됨).
- 설치 끝 모델 응답 측정은 모델 호출 1회를 쓴다. 조직 설정으로 끌 수 있게 하는 것을 다음 작업으로 둔다.
- 자동 활성화를 「같은 직원의 두 번째 PC부터 관리자 확인」처럼 수량으로 제한하는 안.

## 2단계 실측(10-25)

기기·하네스·원장은 실제다. 키트는 비밀번호 로그인 없이 agent-service 내부 함수(`download_managed_kit`, 직원 `user` 명의)로 받았다.
관리자 활성화(격리 회귀)도 내부 함수 `activate_managed`(처리 root)로 대행했다. 원장 시각은 UTC, 기기 표시는 KST.
pj2 측정은 배포본 4c060ef(키트 1단계 코드), pj3는 4679160·283d93e와 이 브랜치 키트다.

### pj2 (Ubuntu 24.04.5, 커널 7.0, 직원 `pj2` = sudo·docker 그룹, Claude 2.1.309·Codex 0.164.0 로그인된 스냅샷 `clean-sudo-1023`)

| 단계 | 결과 | 시간·증거 |
| --- | --- | --- |
| 준비 | 이전 격리 장치(`managed-ad48cce3`) 자격 폐기 → 스냅샷 복원 | 폐기하지 않으면 재설치가 활성화를 이어받아 자동 활성화를 잴 수 없다 |
| 첫 설치(간편, SSH 비대화형, 질문 0) | 성공. gcc 없음·관리 계정 없음·sudoers/shim/rc 블록 없음, 헬퍼 스크립트·`/etc/environment` CA 블록만 | 설치 6초, 확인까지 32초(`install_seconds`·`total_seconds`) |
| 자동 활성화 | `enrolled` 08:30:06 → `activated`(처리 auto, 「설치 점검 통과로 자동 활성화」) 08:30:10 | 4초, 원장 `endpoint_managed_events` |
| 설치 확인 세 칸 | 모델 응답 claude 정상 9.5초 · 도구 40개(서버 10/10) · 서버 연결 `docs-mcp-cloudflare…` 정상 | 설치 출력 JSON `checks` |
| 로컬 MCP 준비 | filesystem·memory·sequentialthinking 3/3 prepared, 문서 폴더 `/home/pj2/mcp-docs`(직원 홈) | 활성화 뒤 약 50초 |
| 직원 Claude → Microsoft Learn | `microsoft_docs_search` Allow `P-AUTHZ-ALLOW-001`, 실행됨 | 원장 1272, 따로 재실행 11.7초 |
| 직원 Claude → DeepWiki | `read_wiki_structure` Allow | 원장 1273, 12.7초 |
| 직원 Claude → filesystem 로컬 읽기 | `list_allowed_directories`·`read_file` Allow, 파일 내용 그대로 반환 | 원장 1274·1275, 18.9초 |
| 사람 개입 | **0회**(모델 로그인은 스냅샷에 이미 있음) | 설치 시작부터 첫 Allow까지 약 2분 10초(로컬 준비 대기 포함) |
| 설치 전 터미널(CA 변수 없음) | Claude가 `UNABLE_TO_GET_ISSUER_CERT_LOCALLY`로 연결 실패, `mcpgw-status`는 「새 터미널(또는 다시 로그인)」 안내 | 새 SSH 세션(pam_env)은 정상 |
| 〃 해결 확인 | `claude --settings '{"env":{"NODE_EXTRA_CA_CERTS":…}}' mcp list`에서 전부 Connected → 관리형 설정 env로 CA를 렌더링하도록 수정(eec3e22, 배포 필요) | Codex는 세션 변수만 읽어 Codex만 새 터미널 |
| 하네스 판본(D-220 대체 관측) | heartbeat `host.harnesses` = claude 2.1.309·codex 0.164.0 | 장치 detail |
| 격리 회귀(`--isolated` 키트, 간편 위에) | 간편 설치 원복 → gcc 설치 → `managed-pj2` 생성 → AppArmor 8개 enforce·nft `mcpgw_uid_1001` → **대기**(자동 활성화 안 함) → 관리자 활성화 → 하네스 shim으로 10/10 Connected, `mcpgw-status --check` 도구 40개 | 모델 호출은 「Not logged in」(관리 계정은 모델 로그인을 따로 해야 함 — 간편 모드가 없앤 마찰) |
| 결함 ① | 격리 모드 무인 설치가 Codex 장치 코드 로그인을 띄워 멈춤(최대 15분) | 수정(eec3e22): 터미널이 없으면 두 모드 모두 묻지 않고, 모델 칸이 로그인 필요면 다음 할 일에 로그인 명령 |
| 결함 ② | 간편→격리 전환 뒤 간편 장치가 활성으로 남음(유령) | 수정(eec3e22): `companion_names`가 동반 계정에서 직원 이름으로도 찾는다 |
| 격리→간편 전환 | `managed-pj2` 삭제(홈 유지)·AppArmor 0·nft 0·shim·sudoers·rc 없음, 새 장치가 관리자 활성화를 이어받고 이전 두 장치 폐기 | 설치 8초·확인까지 30초 |

### pj3 (Windows 11 26300, 관리자 `pj3` 콘솔 로그인 중, SSH 토큰 High, Claude 2.1.302 WinGet·Codex 데스크톱 로그인됨)

기기 배포본은 4679160 → 283d93e. 마지막 원클릭은 283d93e에서 받은 파일의 등록·CA·런타임을 그대로 두고 이 브랜치 키트 파일로 다시 묶은 것이다
(`windows_oneclick.launcher`·매니페스트 해시 재계산, scratchpad `rebuild_oneclick.py`) — 그 뒤 수정(9f9d04f)이 아직 기기에 없어서다.
UAC 클릭은 SSH에서 보안 데스크톱에 닿지 않으므로, 직원 콘솔 세션(세션 1)의 관리자 권한 예약 작업이 `.cmd`를 실행해 대신했다.
**실사용에서 사람 손이 가는 곳은 `.cmd` 더블클릭 → UAC 「예」 1회와, 끝난 뒤 완료 대화 상자의 「확인」뿐이다.**

| 단계 | 결과 | 시간·증거 |
| --- | --- | --- |
| 이전 상태 정리 | 10-22 시험의 표준 계정 `pj3user` 관리형 설치(같은 PC 다른 직원 — 기계 공용 Claude 설정을 서로 덮어씀)와 표식 이전 원클릭 승인을 정리 | 이 세션 소유 시험 상태 |
| 원클릭 1차(4c060ef) | 실패 — 결과 파일 없이 템플릿이 실패 대화 상자에서 대기 | `Read-EndpointManagedRequest`가 원클릭 요청에 없는 속성에 대입(10-18 결함) → cb663ff |
| 원클릭 2차(4679160) | 실패 「실행 파일 준비」 | `runtime-check.py`가 D-232의 tomli·toml을 요구(10-23 이후 모든 Windows 설치) → 8bd0040 |
| Python 단계 직접 실행 | `REMOVE_COMPANION`이 PowerShell 종료 코드 1(동반 계정 없을 때) | 8bd0040, 제거 스크립트도 같은 결함 수정 |
| 원클릭 3차(283d93e) | 실패 「실행 파일 준비」, `python.exe` 사라짐 | 작업자가 실행 중 서비스가 연 런타임을 덮어씀(재설치 거부가 숨기던 경로) → 9f9d04f |
| 원클릭 4차(브랜치 키트) | **완료**(준비 > 설치 위치 확인 > 실행 파일 준비 > 실행 파일 점검 > 연결 등록 > 로그온 시작 등록 > 설치 완료). 표식 승인 갱신 경로로 이전 승인 교체, 망가진 런타임 복구 | 이전 장치가 격리 상태라 새 장치는 `held_from`으로 **대기**(설계대로 사람 확인) |
| 제거(트레이 「제거」의 작업자 경로) | 완료 9초. 예약 작업·관리형 Claude/Codex 파일·직원 config.toml 블록·CA 환경 변수·프로그램 폴더 없음, 트레이 종료 | 승인 설치기(`MCPGatewayInstaller`)는 남김(설계) |
| **재설치(원클릭 5차, 무개입)** | **설치 15초, 활성 17초**(자동 활성화), 트레이 세션 1 실행, CA 사용자 환경·관리형 설정 `env`, 방화벽 규칙 0, 하네스 판본 claude 2.1.302 | 결과 `completed`, 장치 `managed-…`(`activated_by=auto`) |
| 트레이 첫 활성화 자동 확인 | 모델 claude 정상 5.2초 · `initialize` 10/10 · 도구 40 | `%LOCALAPPDATA%\MCPGatewaySetup\tray-<SID>\probe.json` |
| 직원 Claude → Learn·DeepWiki | 실행됨(13초·10초). 판정 Alert `MCP-SHADOW-002` | 원장 1284·1285. 직원 `~/.codex/config.toml`에 Codex 앱이 둔 `node_repl` stdio MCP가 섀도로 보고됨(아래) |
| 활성화 직후 안내문 | 1차(4679160 키트)는 활성화 뒤 최대 60초 「활성화 대기」 안내문으로 Claude가 도구를 안 씀 → 8bd0040 뒤 즉시 활성 안내문 | 「guidance active: True」 |
| 네트워크 끊김·복귀 | 끊김 10초 안에 「연결 끊김」, 그동안 하네스 EACCES, 복구 6초 만에 「활성」(격리 없음) | 방화벽 차단 규칙으로 게이트웨이 호스트 차단·해제 |
| 다시 연결(트레이 명령, 세션 1 비승격) | `completed`(준비 > 게이트웨이 연결 확인) | 트레이와 같은 명령줄 |
| Codex 앱이 config.toml 재작성 | 블록 해시 불일치로 PC 격리(직접 설치 장치) | 383ee4d: 간편 모드는 heartbeat 전에 블록 복원. 재설치 뒤 복원 기록 0회(그 사이 재작성 없음) |
| 재부팅 | 아래 「재부팅」 | — |

#### 트레이 메뉴(사람 클릭 없이 확인한 범위)

| 메뉴 | 확인 | 방법 |
| --- | --- | --- |
| 상태 창 | 상태 파일 내용(연결·관리 상태·모드·서버 10개 이름·하네스 판본·게이트웨이) | `status.json`, 창 렌더링은 미확인 |
| 연결 확인 | 통과(위 자동 확인과 같은 `managed-windows.py probe`) | `probe.json` |
| 모델 로그인 | 미실행(누르면 `cmd /k claude auth login` — 브라우저 OAuth라 사람 필요) | 코드 |
| 다시 연결 | 통과 | 세션 1 비승격 작업 |
| 콘솔 열기·English/한국어 | 미실행(창·클릭 필요) | PowerShell 구문 검사·Windows 시험 |
| 제거 | 통과(작업자 경로, 마법사 단추 클릭은 대행) | 위 제거 행 |
| 최근 차단 | 간편 모드는 커널 차단 기록이 없어 「—」 | — |

화면: 세션 1 캡처에 완료 대화 상자(단계·「지금 계정 그대로 사용」·「트레이 아이콘 > 연결 확인/모델 로그인」 한글 정상)와 작업 표시줄 숨김 영역의 트레이를 확인했다(scratchpad `pj3-desktop.png`).

#### 재부팅(소유자 콘솔 로그인 뒤 확인, 기기 4edec39)

| 항목 | 결과 | 증거 |
| --- | --- | --- |
| 서비스 자동 재연결 | 부팅 18:53:11 → 18:53:39부터 `active`(로그인 없이, SYSTEM 부팅 작업) | `service.log` `active` 78건 |
| 트레이 자동 시작 | 소유자 로그인(20:10) 직후 20:10:15 세션 1에서 시작(로그온 예약 작업) | 프로세스 시작 시각 |
| 재부팅 뒤 호출 | 직원 Claude → Learn 15초, 실행됨(Alert `MCP-SHADOW-002`, `node_repl`) | 원장 1287 |
| SSH(들어오는 연결) | 로그인 전에는 닿지 않음 — 원인 미확인 | 18:52~20:10 |

#### 기기 배포본 그대로의 원클릭(main v0.9.0, 4edec39)

| 항목 | 결과 | 증거 |
| --- | --- | --- |
| 활성 설치 위에 다시 설치(갱신) | `completed` 23초, 표식 승인 갱신·런타임 교체(서비스 정지 뒤)·트레이 유지 | 결과 파일 |
| 장치 | 같은 PC 재설치로 활성화 이어받음(D-217), 이전 장치 폐기 | `managed-f5f4f5db`, 이전 `managed-477ff458` revoked |
| 호출 | Learn 14초·DeepWiki 10초, 실행됨 | 원장 1288·1289 |
| 남은 점 | 이미 떠 있던 트레이는 다음 로그인까지 옛 `tray.ps1`로 돈다(예약 작업 `IgnoreNew`) | 같은 pid 5992 |

## 다음 작업

- 갱신 설치 뒤 이미 떠 있는 트레이를 새 판으로 바꿔 띄우기(지금은 다음 로그인 때 바뀜).
- pj3 로그인 전 SSH 불가 원인 확인(현장 원격 지원에 영향, 키트 동작과는 무관).
- GitHub(D-235 「내 연결」 필요) 호출은 별도 항목으로 남았다.

## 사용자에게 필요한 입력

- Codex 데스크톱 앱 기본 MCP(`node_repl`)를 섀도로 둘지(지금 Alert, 실행은 됨) 결정.
