# 로컬 도구·MCP 설치, 위험매핑과 엔드포인트 개선

- 작업자: Luna3개가 설치·기능 수집 및 권한 조사, Codex가 직접 검수·수정·배포·시험.
- 코드 기준: `10/14-local-mcp-endpoint`, 시작 commit `ab6936c64f3578de8360b840f1928681714fa7bb`와 기존 미커밋 파일132개 snapshot. 원본 작업트리는 보존했다.
- 시작 근거: PAC01/02/05/07/11/12/14/15/19/22/23, DEV-03/18/19/20과 실제 로컬 stdio·앱 bridge 경계.
- 완료 조건: 선택한 실제 무료 MCP 설치/연결, 스키마·효과·유형 분류, 원본 위험표 연결, 권한 레퍼런스, 재현된 키트 결함 수정·회귀·가능한 지정 기기 검증.

## 결과

[설치·분류 정본](../../analysis/local-tools/README.md)에 Ghidra·Git·SQLite·Blender·Playwright를 묶었다. 실제 MCP5개에서 initialize·목록·읽기 호출을 확인했고, 이 판본에서 광고된 스키마92개를 보존했다. Ghidra28(읽기20/변경8), Git28, DBHub2, Blender9, Playwright25다. 전체92개를 실행했다는 뜻은 아니다.

Git add/commit은 독립 HEAD 변화와 원복, SQLite INSERT는 별도 DB 연결의 행과 DELETE 원복, Blender는 합성 구 생성 후 mesh1→2 읽기를 확인했다. Ghidra는 합성 ELF를 import/분석했으며 바이너리 코드는 실행하지 않았다. Playwright는 task-local profile/headless와 loopback 합성 한글 페이지만 읽었다. 원본 응답·설치물·lock·소스는 ignored `.task-local-20261014/`에, 공유 정본은 JSON/Markdown에 있다.

무료 상용 후보인 DBeaver Community는 공식 ZIP을 설치했으나 GUI DB 세팅은 미완료다. Burp Community2026.9.2와 공식 MCP BApp1.3.0 파일을 확보했고 공식 SHA·CLI help·Community 호환을 확인했다. UI 활성화와 실제 Burp MCP 호출은 미실행이다. DAST MCP만 보고 desktop 무료판 연동을 부정한 초기 해석은 공식 BApp 근거로 정정했다. native UI 제어가 제공되지 않는 이 세션에서 수동 활성화 절차를 남겼다.

## 검수에서 확인한 권한 반례

- Git `GIT_BASE_DIR` 밖 `git_set_working_dir`는 snapshot 읽기를 했고 `git_clone`도 바깥 합성 경로에 복사했다. 독립 HEAD 일치·프로세스 종료 후 cleanup 성공을 확인했다. 후속 `git_status`의 거부를 전체 경로 통제 성공으로 세지 않았다.
- GhidraMCP의 loopback HTTP Origin/Host 검사, Blender의 인증 없는 raw TCP bridge, Burp BApp의 anti-rebinding 검사는 사용자 인증과 별개다. Blender MCP safe mode는 addon 직접 socket에 적용되지 않는다.
- DBHub readonly INSERT/ATTACH는 정책 거부, extension은 해당 SQLite 빌드에서 거부됐다. readOnlyHint·SQL gate·프로필 분리·headless를 OS sandbox로 표시하지 않았다.
- Playwright unsafe JS·host upload/drop·출력 파일과 외부 asset/telemetry는 별도 권한 유형이며 실제 호출한 기능과 광고된 기능을 구분했다.

[위험매핑10건](../../threats/local-tool-map.md)을 기존 원본 정책24개에 의미로 연결했다. 운영 카탈로그 자동 등록·계약 승인이나 원본 PAC 번호 변경은 없었다. [권한 레퍼런스12개 주제](../../catalogs/endpoint-permission-references.json)는 Linux4·Windows4·앱/MCP4로 묶고 공식 원문·hash·판본·코드·정상/음성 시험 기준을 보존했다. MCP 명세 자료는 기존 카탈로그를 재사용하고 새 논문으로 중복 집계하지 않았다.

## 수정한 부분

| 변경 | 수정 전 재현 | 수정 후 |
| --- | --- | --- |
| Linux AppArmor 점검 | 다른 계정의 유사 프로필명으로 정상 판정 | 정확한 profile 행과 enforce 상태만 인정 |
| Windows firewall 점검 | 빈 프로필·누락/비활성/다른 SID 규칙이 baseline과 같으면 정상 | 실제3개 boolean 프로필, 기대 규칙3개·활성·방향/Block/Any/SID·baseline 일치 요구 |
| 인벤토리 gateway 분류 | gateway 이름만 복사한 local/stdio가 registered | 승인된 실제 Gateway URL만 경유로 인정 |
| 인벤토리 비밀 최소화 | URL userinfo/query/fragment와 legacy stdio 원문 저장 | collector·receiver·raw 저장을 정확한 SHA-256 참조로 제한 |
| 로컬 MCP 발견 | 직접 Playwright/DBHub/Blender 실행 표지 누락 | 검수한 표지 추가, 일반 Blender 음성 검사, suspected 유지 |
| Blender 실행 설정 | autoexec 미명시·ambient 자격 환경 상속 | disable-autoexec·자격 환경 제거, 실제 연결/장면 쓰기 재시험 |

상세 변경은 [agent.py](../../../../endpoint-agent/agent.py), [Linux](../../../../endpoint-agent/managed-linux.py), [Windows](../../../../endpoint-agent/managed-windows.py), [수신부](../../../../full_stack_lab/gateway/app/endpoint_plane.py)에 있다. 새 회귀15건과 CI 연결을 추가했다. Windows loopback 일반론은 현재 키트의 실측 미완료로 정정했다.

## 배포와 검증

| 확인 종류 | 환경·결과 | 원본 증거 |
| --- | --- | --- |
| 수정 전 재현 | 키트 점검9개 중6개 실패, 인벤토리6개 중5개 실패(하위 URL 입력3개 포함하면7 failures) | [회귀 전후](2026-10-14-endpoint-regressions.json) |
| 수정 후 로컬 | 신규 점검9+인벤토리6 통과, collector/Windows self-check·pyflakes·무인증 목록 검사 통과 | [회귀 원본](2026-10-14-endpoint-regressions.json) |
| 기존 Linux 키트 | Kali WSL17건 통과. mock IdP는 내부 회귀용이며 실제 MCP 실행 증거와 별도 | [회귀 원본](2026-10-14-endpoint-regressions.json) |
| 실제 OSS MCP | 실제5개 initialize/list/read; Git·SQLite·Blender 합성 쓰기·독립 효과/원복 | [설치 정본](../../analysis/local-tools/README.md) |
| 솔루션 배포 | 지정100.83.175.111에서 field up 완료. 실행 app46개 파일과 source hash 일치, health/readiness200·ready·정책/데이터/Console/Gateway build 일치 | [배포 결과](2026-10-14-solution-deployment.json) |
| 내려받을 키트 | agent-service의 `/endpoint-kit` Linux/Windows/collector hash가 수정본과 일치 | [배포 결과](2026-10-14-solution-deployment.json) |
| PJ1 Linux 적용 | 100.110.81.60의 실제 설치 프로그램2개 hash 조건 확인·root backup·관리 서비스만 재시작. active/compliant 및4개 OS 점검·설정 hash 일치 | [PJ1 결과](2026-10-14-pj1-endpoint-update.json) |
| fresh 프로세스·망 | 실제 AppArmor label, Codex0.160/Claude2.1.288 정상 실행, Node126 거부, 승인 Gateway TCP 성공, 수신측 SSH22가 도달 가능한 IPv4/IPv6 loopback을 managed shell에서 거부 | [PJ1 결과](2026-10-14-pj1-endpoint-update.json) |
| 실제 모델·하네스 MCP | 새 자연어 모델 turn 및92개 도구의 관리 경로 시험 미실행 | 설치/OS/프로토콜 결과와 별도 |

솔루션 시작 source와 running app46개가 이미 일치하는 것을 먼저 확인해 다른 미배포 코드를 함께 올리지 않았다. 필요한4개 source만 hash 조건과 백업으로 교체했다. 처음 field build는 기존 Docker credential helper가 Windows executable을 가리켜 실패했고, 작업 전용 Docker config를 사용해 다시 성공했다. 전역 Docker credential 설정은 바꾸지 않았다. 실행 revision은 기존 `2e36095+dirty`이며 이 작업 commit으로 꾸미지 않고 실제 내용 hash와 정책 hash로 증거를 남겼다.

PJ1도 처음 SSH 시간 초과 후 재접속했으며 별도 승인·자격 재발급·계정/정책 재설치 없이 기존 활성 상태를 유지했다. Linux 설치 파일의 root backup은 `/var/lib/mcpgw-managed/managed-pj1/task-backups-20261014`, 솔루션 source backup은 `/home/user/mcp-gateway/full_stack_lab/reports/local-mcp-endpoint-20261014/source-before`다. device key·token·로그인 비밀번호를 보고서나 Git에 저장하지 않았다.

## 남은 공백과 개선 우선순위

1. Windows는 actual App Control/AppLocker·restricted process·WFP/IPv4/IPv6/loopback·도메인 그룹 검증이 필요하다. 현재 SID outbound 규칙과 pipe ACL만으로 프로세스 sandbox라고 주장하지 않는다.
2. root 관리 서비스는 별도 privilege 분리가 필요하다. systemd strict/NNP 적용 전 정책 파일 쓰기·kernel journal·nft AF_NETLINK·socket 권한을 검토해야 한다. 이름+enforce 점검은 kernel policy 본문이나 승인 binary 무결성의 증명이 아니다.
3. 같은 UID 전체와 개별 process identity를 구분해야 한다. Unix SO_PEERCRED는 현재 UID principal을 확인하며 같은 UID의 모든 프로세스를 독립 인가하지 않는다.
4. 로컬5개 각각의 직접 stdio/bridge와 승인 Gateway 경로를 실제 managed 하네스·정상군·음성군·독립 수신/파일 효과·복구로 시험한다. 현재 Node/loopback 검증은 선택한 Linux 경계만 통과했다.
5. Windows 사용자 PC 키트의 background report와 uninstall 사이에 report.log WinError32 경합을 관찰했다. Linux 회귀 통과로 이 Windows 문제를 숨기지 않았다. 보고 프로세스 수명과 제거 잠금의 후속 수정이 필요하다.
6. 같은 PJ1 username의 과거 active 등록들이 오래된 heartbeat를 유지하고 있다. 새 결과는 현재 신선한 등록1개를 검증했으며 과거 등록을 임의 철회하지 않았다. 등록 상태와 현재 호출 가능성을 별도로 확인한다.

## 부수 상태와 사용자에게 필요한 입력

DBeaver probe 과정에서 사용자 `AppData/Roaming/DBeaverData/.../EBWebView` 캐시가 생성된 정황을 확인했다. 사전 목록/hash가 없어 기존 사용자 파일의 변경 여부는 미확인이다. 해당 경로는 지우지 않았고 [경로·시각·근거](../../analysis/local-tools/data.md)를 보존했다.

Windows 실기기 집행과 Burp 확장 UI 활성화는 격리 시험 환경에서 남아 있다. 업무 자산·새 권한/라이선스를 임의로 추가하지 않았다. 현재 설치·기능표·위험매핑·Linux 개선을 검토하는 데 추가 입력은 없다.
