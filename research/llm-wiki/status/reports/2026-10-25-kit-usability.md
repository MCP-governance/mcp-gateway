# 2026-10-25 엔드포인트 키트 편의·자동화 — 간편 모드 기본, 자동 활성화, Windows 같은 계정, TUI (D-239)

- 작업자: Claude Code (Opus 5.5), 세션 `kit-usability`
- 코드 기준: `10/25-policy-sync-split` 끝 `cbc5195`(D-238 포함)에서 분기, 브랜치 `10/25-kit-usability`, 코드 커밋 `3090e75`·`532b2d9`. 변경 32개 파일 + 새 시험 2개
- 시작 근거: 소유자 지시(10-25 저녁) 「보안을 좀 느슨하게 하더라도 키트 편의·자동화 극대화, Windows 메인, GUI 못 띄우면 TUI」,
  지시서 `지시서_세션배분_20261025.md` S1, 10-25 제안서 P0-3(이 지시로 대체), 10-23 키트 결함 D-216~D-232
- 완료 조건(지시서): ① 구현·단위·Windows unittest·CI 수용 시험·보고서 1차 → 브랜치 push → ② 리더 배포 뒤 pj2·pj3 실측 → 보고서 최종
- **현재 단계: ① 완료, ② pj2 완료·pj3 결함 수정 뒤 배포 대기**. 실측은 아래 「2단계 실측」.

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

SYSTEM 서비스가 하네스 판본(직원 실행 파일을 실행하지 않고 `~/.local/share/claude/versions`·npm `package.json`에서 읽음), 관리형 설정
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
| 회귀 기준선(작업 전) | `run_local_suite.py`, Windows 노트북 venv 3.12 | 통과 108 · 실패 6 · 외부 의존 17(실패: acceptance_tls·intake_one_click_ast·macos_kit·output_credential_span·sbom_impact·threat_trace_mapping) | scratchpad `baseline.json` |
| 회귀(작업 후) | 같은 명령, 코드 `532b2d9` | 통과 111 · 실패 5(전부 기준선) · 외부 17 · 새 실패 0 | scratchpad `after3.json` |
| 새 시험 | `endpoint_auto_activation_check.py`(3), `kit_simple_mode_check.py`(10) | 통과 | 로컬 |
| 고친 시험 | `kit_continuity_check`(모드·held_from·모드 전환·자동 활성화 상속 금지·다음 할 일), `kit_install_upfront_check`(화면 단계 시간), `user_command_settings_check`, `managed_policy_gap_check`, `macos_kit_check`(Windows 우선) | 통과 | 로컬 |
| Windows 키트 | `py -3 -X utf8 -m unittest discover -s endpoint-agent/tests-windows` | 27 통과(간편 설치·원클릭 같은 계정 추가) | 로컬 |
| PowerShell 구문 | `Parser.ParseFile` 전 ps1·ps1.in | 오류 0 | 로컬 |
| 콘솔 | `node --check console.js`, `node --test tests/*.test.mjs` | 통과(i18n 영어 사전 12개 추가) | 로컬 |
| 정적 | `pyflakes gateway/app/*.py tests/*.py endpoint-agent/*.py tests-windows/*.py`, `open_endpoints.py` | 0건 · PASS | 로컬 |
| 실제 Linux | WSL kali Python 3.13 pty(`script`): `bootstrap.py --self-check`, curses 화면·평문 폴백·상태 글 | OK | 로컬 |
| CI 수용 | `acceptance.py endpoint-simple-mode-auto-activation`(실제 등록·정책·heartbeat·토큰, 설정 원복·장치 폐기) | 미실행(CI 일회용 스택에서 실행) | — |
| 실기기 pj2 | 클린 스냅샷 첫 설치→자동 활성화→Learn/DeepWiki·filesystem Allow, `--isolated` 회귀 | 통과(사람 개입 0, 설치 6초·확인 32초), 결함 2건 수정 | 원장 1272~1275, 「2단계 실측」 |
| 실기기 pj3 | `.cmd` 같은 계정·UAC·트레이·재부팅·재연결·제거·재설치 | 실패 → 원클릭 요청 검사 결함 수정(cb663ff), 재측정은 배포 대기 | 「2단계 실측」 |

### 회귀 결과

`run_local_suite.py`(코드 `532b2d9`): 통과 111 · 실패 5 · 외부 의존 17. **새 실패 0.** 남은 실패 5개(acceptance_tls·intake_one_click_ast·output_credential_span·sbom_impact·threat_trace_mapping)는 기준선과 같은 기존 실패다. `macos_kit_check`는 기준선 실패에서 통과로 바뀌었다(Windows 우선 콘솔에 맞춰 시험을 고침). 새 시험 `endpoint_auto_activation_check`·`kit_simple_mode_check` 통과. 중간 실행에서 새로 실패한 3개(console_copy_check — 콘솔 주석의 D-번호, connector_control_check — 판본 수집 이름, loopback_owner_replies_test — `install_managed` 인자)는 `532b2d9`에서 고쳤다.

`check_wiki.py`: 오류 29개, 전부 `Missing local file: local-sources/compliance/LIB-M*/provenance.json` — 기존 분석 파일(`consent-per-server-1023`, `dest-pin-credential-redaction`)이 가리키는 Git 제외(`.gitignore`) 로컬 원본이 이 노트북에 없어서다. 이 작업의 변경과 무관하며 새 오류는 0이다. `map_threats.py`·`build_enterprise_analysis.py --refresh-code-only`·`capture_status.py`·`build_wiki.py`는 재생성했다.

## 실패·미완료·한계

- 기기 배포 전이라 실제 설치·자동 활성화·세 칸·Windows GUI는 전부 미실행이다. 대역 시험 통과는 동작 증거가 아니다.
- `/etc/environment`(Linux)·사용자 환경 변수(Windows)는 새 로그인·새 프로세스부터 적용된다. 설치 전에 열린 터미널의 하네스는 사설 CA를
  모르고 게이트웨이 TLS에 실패할 수 있다 → `mcpgw-status`·트레이가 「새 터미널」을 안내(pj2에서 확인 예정).
- Claude Code가 관리형 설정 `env`의 프록시를 쓰는지, `NODE_EXTRA_CA_CERTS`를 세션 환경에서 읽는지는 격리 모드 실측(래퍼 환경)으로만 확인됐다.
  간편 모드 경로는 pj2·pj3에서 확인한다. Windows Codex는 프록시 환경을 받지 않는다.
- Windows 비대화형 SSH에서 `.cmd`의 `Start-Process -Verb RunAs`는 UAC 보안 데스크톱을 띄울 수 없다(측정 예정). 그 경우 소유자 1회 클릭 지점을
  ②단계 보고에 적는다.
- 트레이 「다시 연결」은 서비스 재시작에 UAC가 필요하다(표준 직원이면 관리자 자격 입력). 자동 재시작은 예약 작업의 1분 재시작 설정에 맡긴다.
- 간편 모드 Windows의 판본 수집은 native 설치기·npm 경로만 읽는다(WinGet·기타 경로는 「—」).
- `main.py`(heartbeat `host.harnesses`, `/api/endpoint/settings`)·`idp.py`(`mode`)·`lifecycle_tables.sql`·`integrations.py`·`i18n-en.mjs`는
  지시서 소유 목록 밖이지만 자동 활성화·통제 범위 표시에 필요한 최소 변경이다. 옛 게이트웨이는 `mode`·`host.harnesses`를 422로 거부하므로
  **게이트웨이를 먼저 배포**한다(키트는 heartbeat 422에서 `host`를 빼고 다시 보낸다. 등록 `mode`는 다시 보내지 않으므로 옛 게이트웨이에 새 키트로 등록하면 실패).
- `research/llm-wiki/status/current.md`·`backlog.md`는 S3(위키 세션) 소유라 이 브랜치에서 고치지 않았다. 병합 뒤 리더가 갱신한다.

## 방향 제안

- 간편 모드에서도 Windows SID 방화벽을 「게이트웨이 + 모델 프록시 + 일반 인터넷 허용, 다른 MCP 포트 차단」 같은 좁은 규칙으로 둘 수 있으나
  MCP를 포트로 구분할 수 없어 효과가 없다고 판단해 넣지 않았다.
- 설치 끝 모델 응답 측정은 모델 호출 1회(토큰 소량)를 쓴다. 조직이 원하면 설정으로 끌 수 있게 하는 것을 다음 작업으로 둔다.
- 자동 활성화를 「같은 직원의 두 번째 PC부터 관리자 확인」처럼 수량으로 제한하는 안을 검토할 만하다(지금은 PC 수 제한 없음).

## 2단계 실측(10-25, 기기 배포본 `10/25-integrate` 4c060ef)

기기·하네스·원장은 실제다. 키트는 비밀번호 로그인 없이 agent-service 내부 함수(`download_managed_kit`, 직원 `user` 명의)로 받았다.
관리자 활성화(격리 회귀)도 내부 함수 `activate_managed`(처리 root)로 대행했다. 시각은 UTC.

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

### pj3 (Windows 11 26300, 관리자 `pj3` 콘솔 로그인 중, SSH 토큰 High, Claude WinGet·Codex 로그인됨)

| 단계 | 결과 | 비고 |
| --- | --- | --- |
| 키 접속 | 성공(BatchMode) | — |
| 이전 상태 | 10-22 시험의 표준 계정 `pj3user` 관리형 설치가 남아 있었다 | 같은 PC의 다른 직원 설치와 기계 공용 Claude 설정이 겹쳐 서로 덮어쓴다 — 롤백·트레이 작업·승인 설치기를 정리(이 세션 소유 시험 상태) |
| 원클릭 실행 | 콘솔 세션 1에서 관리자 권한 예약 작업으로 `.cmd` 실행(UAC 클릭 대신) | SSH는 UAC 보안 데스크톱에 닿지 않는다. 실제 사용자는 `.cmd` 더블클릭 → UAC 「예」 1회가 유일한 클릭 지점 |
| 결과 | **실패** — 작업자가 결과 파일 없이 끝나고 템플릿이 실패 대화 상자에서 대기 | `Read-EndpointManagedRequest`가 원클릭 요청에 없는 `gateway_url`에 대입해 예외(10-18부터 있던 결함). 수정·시험(cb663ff) — 배포 필요 |
| 결함 ③ | 원클릭으로 한 번 설치한 PC는 새 판본 원클릭을 「IT must update the approved installer」로 거부 | 수정(cb663ff): 원클릭이 만든 승인에 표식을 남겨 새 원클릭으로 갱신 가능. 표식 이전 설치는 한 번 정리 필요, IT 승인은 그대로 |
| 같은 계정 설치·세 칸·트레이·재부팅·재연결·제거·재설치 | **미실행** | 위 결함 수정본 배포 대기 |

## 2단계 실측 계획(리더 배포 뒤)

1. pj2: `vmrun revertToSnapshot … clean-sudo-1023` → 콘솔 대신 SSH 키 경로로 키트 받기(리더가 준 방법) → `./install.sh`(NOPASSWD sudo,
   비대화형) → JSON의 `checks`·`install_seconds`·`total_seconds` 기록 → 직원 계정 `claude -p`로 Microsoft Learn(또는 DeepWiki) 호출·filesystem
   로컬 MCP 읽기 → 원장 Allow·policy_id 확인. 사람 개입 횟수·소요 시간. 설치 전 연 SSH 세션에서 `mcpgw-status`(새 터미널 안내).
2. pj2 `--isolated` 회귀: 같은 키트를 `--isolated`로 → 격리 계정 생성·AppArmor·nft·대기 상태 → 관리자 활성화를 서버 내부 함수로 대행 → 호출 확인 →
   다시 간편 모드로 전환(격리 계정 삭제·홈 유지·장치 이어받기).
3. pj3: `.cmd` 업로드·실행 → UAC 측정 → 트레이 상태 창·연결 확인·재부팅 뒤 자동 시작·네트워크 끊김 복귀·제거·재설치·메뉴 전부 표.
4. GitHub(D-235 「내 연결」 필요)는 별도 항목.

## 다음 작업

②단계 실측(위 계획). 실패하면 같은 브랜치에서 고치고 보고서 최종본에 반영한다.

## 사용자에게 필요한 입력

없음(①단계). ②단계에서 pj3 UAC가 비대화형으로 안 되면 소유자의 화면 클릭 1회가 필요할 수 있다.
