# D-62/D-63 통제 범위·응답·실기기 검증

2026-10-01. Claude의 `39db109` → `354117f` → `fc9ed66` 작업을 이어 검토했다.
Gateway에 도착하는 호출, 관리형 일반 계정의 OS 경로, 벤더 계정의 다른 접근을 구분한다.
공급자 MCP나 공식 하네스의 소스를 수정하지 않았다. native 제어 API 시험에는 모델 턴이 없다.

## 적용 구조

| 경계 | 실제 동작 | 증거의 한계 |
| --- | --- | --- |
| Gateway | transport 신원·등록·독립 승인 범위·계약·PII·예약·PAC15를 실행 전에 검사 | 경유한 요청만 판정한다 |
| 응답 | text만 반환, PII 마스킹. 다른 형식/검사 실패/주입 표지는 실행 후 보류 | 공급자에서 이미 발생한 쓰기/전송은 되돌리지 않는다 |
| Endpoint | Linux 일반 UID의 AppArmor·nft·보호 설정·단말 자격/heartbeat | root 에이전트 보고다. root/다른 로그인 계정/WSL/Windows 강제를 입증하지 않는다 |
| Vendor | 벤더 관리 콘솔 상태를 관리자가 기록 | 수기 확인이며 공급자 API로 검증한 상태가 아니다 |

분류는 `gateway_mcp`, `gateway_backend_connector`, `vendor_native_connector`,
`local_plugin_or_stdio`, `shadow_or_unknown`이다. 상태는 `gateway_enforced`,
`endpoint_enforced`, `vendor_enforced`, `observed_only`, `unknown_not_enrolled`, `bypass_possible`이다.
Console은 상태와 증거 종류/시각/원장 번호를 같이 표시한다. Endpoint 180초·수기 기록 14일·자체 보고
6시간의 만료를 표시하고, 호출 당시의 서명 단말 결합과 현재 단말 상태를 구분한다.

PII는 공급자 호스팅 서버의 **읽기 인자**도 검사한다. PAC 거부/승인이 다른 정책 뒤의 conflicts에 있어도
예외나 monitor 모드가 풀지 못한다. 감사 `result_preview`는 응답 본문 대신 처리 결과·해시·크기·형식·
마스킹 유형을 저장한다. 보류한 원문의 해시는 추측 검증에 쓰일 수 있어 저장하지 않는다.
이전 원장 행은 append-only 원칙대로 변경하지 않는다.

## 기존 실기기 증거를 현재 원장과 대조

솔루션 `100.83.175.111`의 `354117f` 배포를 확인하고 원장 **395~429(35행)**과 감사 체인 429행 무결성을
재확인했다. 같은 시나리오의 재실행도 포함된 번호 범위이며 이를 서로 다른 35개 기능으로 세지 않는다.

| 실제 호출/상황 | 원장 번호 | 확인한 결과 |
| --- | --- | --- |
| GitHub `list_commits`/`get_me`, native Codex·Claude | 395~397, 407~409 | upstream 실행, 응답 반환 |
| GitHub 승인 범위 밖 저장소 | 398, 410 | PAC-01, attempted=false·executed=false |
| GitHub 미승인 `search_code` | 399, 411 | MCP-REGISTRY-002, 미전송 |
| GitHub 동일 호출 동시 3건 | 400~402, 412~414 | 1건 실행·2건 P-RATE-003 미전송 |
| Context7 정상 읽기 / 주민번호 형식의 시험 문자열 인자 | 403~404, 415~416 | 정상 반환 / MCP-DATA-EGRESS-001 미전송 |
| Figma `whoami` | 405, 417 | EMAIL_ADDRESS 마스킹 후 반환 |
| 승인되지 않은 root 주체의 GitHub 호출 | 406, 418~419 | MCP-REGISTRY-003, 미전송 |
| Context7 같은 세션의 계약 변경/복구/등록 해제 | 420~427 | MCP-CATALOG-001 미전송 / 정상 실행 / MCP-REGISTRY-001 연결 거부 |
| Supabase `list_projects` / 미승인 `list_organizations` | 428~429 | 정상 반환 / MCP-REGISTRY-002 미전송 |

미전송 근거는 Gateway가 upstream 호출 직전 기록하는 attempted/executed와 판정 경로다.
이번 원격 시험에서 공급자 측 감사 로그를 별도로 수집해 전수 대조한 것은 아니다. 랩의 예약 동시성 시험은
별도로 실제 PostgreSQL 효과를 확인한다. `mock:false`라는 라벨 자체를 공급자 실행 증거로 사용하지 않는다.

## 이어받아 발견한 운영 오류와 수정

첫 UI 배포는 `fc9ed66`으로 Gateway·SSE·Console 세 이미지를 재빌드했다. DB·장치 키·OAuth 자격·볼륨은 유지했다.
새 UI 이후 native 시험의 GitHub·Figma·Supabase는 성공했지만 **Context7 두 사례는 실패**했다.
CLI는 `unknown MCP server`/`not connected`를 반환했고 해당 tools/call 원장 행도 없었다.

확인 결과 Context7은 DB `DISABLED`, runtime registry에서 제거, 관리 설정에서도 제거된 상태였다.
이전 등록 해제 시험의 원복이 빠진 것이다. 인증을 다시 띄우거나 성공으로 처리하지 않았다.
`user` 신청·`root` 독립 승인된 도입 **3e902b4a-f97a-4f78-abbb-0d231336aebf**의 기존 계약과 인자 범위,
사용 주체, **2026-10-31T10:16:18Z** 기한 그대로 정상 `/api/mcp-requests/{id}/register` 경로로 복구했다.
새 권한이나 기한을 자동 생성하지 않았다.

`plane_sequence.py`는 계약/등록 원복을 `finally`에서 실행하도록 고쳤다. 시작 전에 해당 등록의 기존 독립 승인
신청을 확보하고 정상 register API로 동일 범위를 원복한다. 이 승인 근거가 없으면 시작하지 않는다.
`plane_evidence.py`는 SSH 호스트 키를 검증하고,
동시 시험에 실행 **1**·중복 거부 **2**를 필수 기대값으로 추가했다. 통제 상태 self-check도 전체 시험에 넣었다.

## 배포 후 UI와 새 native 시험

- 실제 가입 승인된 임시 일반 계정으로 `/login`부터 들어가 **내 PC 연결** 안내가 자동으로 열린 것을 확인했다.
  권한별 첫 화면으로 이동하던 지연 hashchange가 안내를 닫는 문제가 `history.replaceState`로 해결됐다.
- 실제 관리자 화면에서 독립 통제 범위 메뉴, 여섯 열 호출 목록, 상태/증거 표시를 확인했다.
- 개요가 `account_state`를 세면서 "Endpoint 강제 단말 1/3"으로 표시하던 문구를
  **강제된 관리 계정 1**로 바로잡았다. 폐기된 시험 장치 두 건을 실제 단말 수로 세거나 관리 계정 강제를
  단말 전체 강제로 표시하지 않는다.
- 실기기 결과 파일: `full_stack_lab/reports/control-planes-native-release.jsonl`.
  최초 실행은 종료 코드 1, failed_rows=2이며 Context7 실패를 보존한다.
  복구 후 `control-planes-native-restored.jsonl`은 **11사례·13원장 행, failed_rows=0, 종료 코드 0**이다.
- 전체 시험: `/tmp/planes-test.log`의 UI 커밋 후 시험은 19:43 종료 코드 0이다.
  시험 보강 후 `full_stack_lab/reports/control-planes-release-test.txt`도 종료 코드 0이다.
  최종 UI 문구 변경 후 `control-planes-final-test.txt`도 종료 코드 0이다.
  Rego **103/103**, 인수 **23/23**, 보안 회귀 **55/55**, 적대적 공격 **42/42**·정상 **16/16**,
  네 하네스×네 사용자×실제 내부 MCP 10종 연결, 업무 시나리오, E1~E3가 통과했다.

| 복구 후 실제 native 호출 | 원장 번호 | 결과 |
| --- | --- | --- |
| GitHub 승인 읽기(Codex·Claude) | 441~443 | 실행/반환 |
| GitHub 범위 밖 / 미승인 도구 | 444~445 | PAC-01 / MCP-REGISTRY-002, 모두 미전송 |
| 동일 GitHub 호출 동시 3건 | 446~448 | P-RATE-003 미전송 2건, 실행 1건. 검사기가 이 비율도 확인 |
| Context7 승인 읽기 / PII 인자 | 449~450 | 실행/반환 / MCP-DATA-EGRESS-001 미전송 |
| Figma `whoami` | 451 | EMAIL_ADDRESS 마스킹 |
| Supabase 승인 / 미승인 도구 | 452~453 | 실행/반환 / MCP-REGISTRY-002 미전송 |

임시 가입 시험 계정은 제품의 soft-delete API로 정리했다. 가입/승인 감사 이력은 보존했다.

수정한 `plane_sequence.py`도 실제 Claude 연결 하나에서 **4/4 단계, 종료 코드 0**으로 확인했다.
원장 **455~458**은 정상 실행 → 승인 계약 해시 불일치로 MCP-CATALOG-001 미전송 → 계약 복구 후 실행 →
등록 해제 뒤 MCP-REGISTRY-001 연결 거부다. 이 시험의 drift는 **Gateway의 승인된 schema hash에 가한
통제된 오류 주입**이다. Context7 공급자가 실제로 계약을 변경한 사건으로 제시하지 않는다.
공급자 소스와 응답을 수정하지 않았으며 원래 계약 해시를 복구했다. 종료 시 기존 독립 승인 신청으로
같은 기한/범위를 자동 재등록했다. 결과는 `control-planes-sequence-restored.jsonl`에 보존한다.
첫 순서 시험은 드라이버의 Python 모듈 경로 오류로 중단됐고, 변경 전이어서 공급자/등록 상태를 바꾸지 않았다.
통과한 실행 종료에서 발견한 SSH stdin 닫기 경고는 공유 `Harness`에서 stdin을 먼저 닫도록 고쳤다.
그 뒤 **459~462**의 네 공급자 native 응답을 각각 같은 `decision_id`의 원장에 결합했고,
성공한 RPC·비오류·비어 있지 않은 text 응답까지 확인했다(`control-planes-native-bound.jsonl`, 4/4·exit 0).
이 실행의 stderr는 0 byte다. 원장만 쌓이고 하네스에는 오류가 돌아가는 경우를 통과로 세지 않는다.

`695ad5e` 배포 후 네 공급자의 실제 native 호출 **463~466**도 모두 성공했다.
이 재실행 종료에서는 Paramiko 파일 정리 경고가 다시 발생했다. stdin만 먼저 닫는 수정으로는
`Harness`가 자신의 종료 closure를 참조하는 순환과 reader 스레드의 종료 경합이 남았다.
종료 closure가 파일/SSH 핸들을 직접 잡고 reader 종료를 기다리도록 공통 경로를 고쳤다.
`control-planes-native-cleanup.jsonl`의 **467~470, 4/4·exit 0·stderr 0 byte**로 확인했다.
네 응답 모두 같은 원장 ID와 결합된 성공 text이며 Figma 이메일 마스킹도 유지됐다.
SDK나 공급자 MCP를 수정하거나 stderr를 숨기지 않았다.

## 단말과 남은 경계

PJ1의 관리 계정 `managed-pj1`은 UID 1001, 일반 그룹만 보유한다. 같은 장치의 `pj1`은 sudo/docker 권한이 있다.
따라서 **관리 계정 account_state=endpoint_enforced**, **장치 state=bypass_possible**를 동시에 표시한다.
단말 전체를 강제 완료로 발표하지 않는다. 기존 커널 network deny 원장 77~80과 실제 nft/AppArmor 규칙은
Gateway tools/call 원장과 별도다. 단말 설정 발견만으로 실행 차단을 입증하지 않는다.
이어받은 실측에서 PJ1 root 설치기의 SHA-256 `08069bcadf10caa1bc45697fa26da886c1da670c29309e70489ae360ff99715b`가
검토 소스와 일치했다. 실제 호스트에서 검사기를 실행해 AppArmor·nft·보호 파일·일반 계정 네 검사가 모두 참이고,
서버 정책 해시/보호 파일이 일치하며 관리 설정의 서버가 Context7·Figma·GitHub·Supabase임을 확인했다.

Notion·Sentry·Zapier는 인계에서 자격 만료와 refresh 부재가 보고됐다. 이번 재시험은 이 세 서비스를 제외하며
성공으로 집계하지 않는다. 재인증은 PJ1의 실제 하네스에서 한 번 수행하고 root 관리 자격 경로로 옮긴 뒤
계약/독립 승인/실제 호출을 다시 확인해야 한다. 반복 인증 팝업으로 연결 문제를 감추지 않는다.

이번 native 시험은 승인된 읽기 작업이다. 클라우드 모델 추론, 새 Windows/WSL 강제, 새 로컬 IDA/Ghidra/Obsidian
차단 증거, 공급자의 다른 단말/웹 접근 회수는 이 결과의 검증 범위가 아니다. 종료 위험도는 기존
[C1~C4/T1~T3 모델](TERMINATION_MODEL.md)을 사용하며 공급자 잔류 자격 증거 없이 T3 완료로 올리지 않는다.

## 참고·재사용

[고정 소스 UI/조직 분석](BENCHMARK_UI_ONBOARDING_2026-10-01.md),
[IBM 분석](BENCHMARK_IBM_CONTEXTFORGE.md), [Microsoft 분석](BENCHMARK_MICROSOFT.md),
[LiteLLM 분석](BENCHMARK_LITELLM.md), [D-62/D-63 결정](DECISIONS.md), [UI 구조](CONSOLE_UI.md).
벤치마킹은 공개 소스 분석이며 세 제품의 모든 기능을 실제 기동해 성능 우위를 검증한 시험이 아니다.
