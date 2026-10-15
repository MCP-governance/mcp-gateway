# 2026-10-15 도입 출처·최소권한·승인자 독립성·위임 미지원 (작업 B)

- 작업자: Claude Code (Sonnet 5.5 서브에이전트, 메인 에이전트가 조율). 워크트리 `mcp-gateway-wbs-b`.
- 코드 기준: 브랜치 `10/15-wbs-intake-identity`, 시작 commit `8cf3d08`(`10/15-wbs-implementation`). 작업 트리 깨끗(전부 커밋), push·병합 없음.
  커밋 6개: `c7213fb`(출처·신선도 스키마·워커) · `83cea6c`(도구 범위·최소 집합·PAC-05) · `66ab8dd`(승인 기록·독립성·게이트·주석) · `95f679e`(Console) · `78c078f`(문서·D-90~94) · 실제 스캐너 시험과 이 보고서(`git log`의 마지막 커밋, 메시지 `test(v2): real-scanner check…`).
- 시작 근거: WBS G01.01·G01.02·G01.03·G02.01·G02.03·G02.04·G03.02·G08.03, 백로그 DEV-04·DEV-05·DEV-17, D-79(원장 744~800 무효), 보관 태그 `archive/2026-09-29-intake-registration-draft`(60d59b4)의 초안(출처·검토 증거를 등록에 싣는 발상만 참고, 병합하지 않음).
- 해결할 문제와 완료 조건: 위 8개 항목의 `completion_condition`을 코드와 시험으로 닫는다. 실환경(PJ1) 검증은 하지 않았다 — 메인 에이전트가 병합·배포 뒤 한다.

## 결과

구현·설정·활성화·배포를 구분한다. **이번 작업은 모두 "구현 + 격리 시험"까지이며 배포·PJ1 검증은 하지 않았다.**

| 항목 | 무엇이 달라졌나 | 구현 | 검증 수준 |
| --- | --- | --- | --- |
| G01.01 출처·버전·해시 | 워커가 소스 트리의 파일 해시 목록 sha256, 고정 커밋, Trivy `--license-full`이 읽은 라이선스를 `mcp_intake_requests.provenance`에 기록. 승인 때 Gateway가 내부 Gitea 보관본을 받아 같은 방식으로 해시를 다시 계산해 **직원에게 보이기 전에** 대조, 불일치·누락은 `HOLD`. 제공자 운영 원격 서비스는 `kind=provider-hosted`, 해시 없이 "해당 없음"+엔드포인트+광고 버전+계약 해시. 요청 상세에 출처 블록(`출처` 탭) | 완료 | 단위, 격리 DB, **실제 Gitea 1.27.3**, **실제 스캐너(합성 소스)** |
| G01.02 검사 신선도 | 보고서마다 검사기 이름·버전, Trivy 취약점 DB 갱신 시각(`vuln_db_updated_at`) 저장. 검사 실패·보고서 누락·DB 7일 초과(상수 `provenance.VULN_DB_MAX_AGE`)·시각 없음이면 승인·등록 거부(보류). 치명적 발견은 자동 거부 대신 보류, 다른 관리자가 사유·기한(1~30일)으로 `accepted_risks`에 수용해야 통과, 기한이 지나면 `HOLD` 복귀하고 호출은 `MCP-SUPPLY-001`. 등록 때 보고서를 서버 `source_ref`에 연결 | 완료 | 단위, 격리 DB(+OPA), 실제 스캐너 |
| G01.03 최소권한 | 등록 도구마다 목적·자산·행위(승인 r/w/x)·외부 목적지를 사람이 적은 `tool_reviews`. 없는 도구는 `enabled=false` → `tools/list`에서 제외, 호출은 `MCP-REGISTRY-002`. 기존 등록은 `POST /api/registry/servers/{id}/tool-reviews`(신청자 제외)·`tests/tool_scope_review.py`로 채움 | 완료(외부 목적지는 기록·표시만) | 격리 DB(+OPA): 목록·호출 둘 다 |
| G02.01 독립성·기록 | 도입 승인·원격 계약 검토·위험 수용·도구 범위 심사·건별 호출 승인에서 신청자=승인자 거부(서버), 시도도 `refused`로 기록. `approval_events`(append-only 트리거)에 승인자·신청자·사유·범위. `audit_annotations`(append-only)+`POST /api/audit/annotations`(admin, 사유 필수)로 D-79 행을 무효 표시, 활동·감사 화면 "무효 처리" | 완료(D-79 주석은 아직 안 씀) | 격리 DB, 단위 |
| G02.03 재승인 | 만료→`P-APPROVAL-EXPIRY-001`, 철회→`MCP-REGISTRY-001`+목록 제외, 계약 변경→`MCP-CATALOG-001`. `renew_approvals`는 계약 일치에 더해 신청이 `APPROVED`이고 승인한 모든 도구의 범위 심사가 있을 때만 연장, 만료분은 되살리지 않음 | 완료 | 격리 DB(+OPA) |
| G02.04 하네스별 최소 집합 | 관리형 정책(Claude·Codex 파일)의 서버 집합과 `tools/list`가 같은 판단(`pac.visible`/`pac.servers_for`)을 씀. 허용 안 된 사용자·철회·범위 미심사 서버는 설정에서 빠짐 | 완료 | 격리 DB: 렌더링 파일 직접 확인 |
| G03.02 PAC-05 | `act`·`may_act`·`on_behalf_of` 클레임·위임 헤더로 대리 실행을 주장하면 `PAC-05-DELEGATION-UNSUPPORTED`(Rego+Gateway), 관찰 모드에서도 거부. clientInfo·User-Agent는 "검증 안 된 출처"로만 기록. Console 정책 목록 "지원 안 함" | 완료 | Rego 91건, 단위, 격리 DB(+OPA) |
| G08.03 UI | 신청자에게 승인 버튼 없음(서버가 따로 막음), 요청 상세의 범위·출처·승인 기록(사용자 동의/운영자 승인 분리)·검사 기준·위험 수용, 등록 때 도구별 범위 입력, 보류 사유 표시 | 완료 | 브라우저 렌더링(고정 응답) 텍스트 확인 |

### 확인된 실제 사실
- 솔루션 기기 Trivy 캐시의 취약점 DB는 `UpdatedAt 2026-10-06T01:08:27Z`(오늘 기준 9일). **새 기준(7일)이면 지금 기기에서는 소스 도입 승인이 전부 보류된다.** 워커의 DB 갱신 경로(네트워크)를 먼저 확인해야 한다.
- 기존 Console 등록(범위 심사가 없는 것)은 배포 즉시 도구가 모두 꺼진다. 의도한 fail-closed이며 위 도구로 채운다.

## 검증

실행 환경: Windows 11 로컬(정적·단위), 솔루션 기기 격리 랩(`wbs-b-*` 컨테이너·네트워크·/tmp 디렉터리, 실행마다 제거 확인; 운영 컨테이너·DB·자격 파일·`~/mcp-gateway` 접근 없음, PJ1 미사용).

| 확인 종류 | 명령·환경 | 결과 | 수준 |
| --- | --- | --- | --- |
| 정적 검사 | `python -m pyflakes gateway/app/*.py tests/*.py supply_chain/*.py` · `node --check agent_static/console.js` · `node --test tests/console-state.test.mjs` · `python tests/open_endpoints.py` · `python tests/schema_check.py` | 모두 통과(Node 10건, 무인증 1·인증 60개 라우트, CHECK 12개 일치) | 정적 |
| Rego | WSL docker `openpolicyagent/opa:1.20.2-static test /policy` | 91/91 (위임 4경우 추가 + 기존 86) | 단위 |
| 단위 | `python -m unittest tests/provenance_check.py tests/intake_identity_test.py tests/pac_delegation_check.py tests/intake_validation_test.py` (Linux 이미지에서도 같은 파일) | 12·18·7·16건 통과. Windows 로컬은 `intake_validation_test`의 심볼릭 링크 2건이 권한 때문에 오류 — 기준 commit에서도 동일(기존 문제) | 단위(대역) |
| 격리 DB+OPA | `bash wbs-b-lab.sh intake_identity_pg_check.py` — 새 PostgreSQL 18 + 이 저장소 `opa/`를 서빙하는 OPA + Gateway 이미지 | **27건 통과** (독립성 거부 기록, 출처·신선도 보류, 위험 수용 만료, 만료·철회·계약 변경 거부와 갱신 불가, 범위 없는 도구 제외, 하네스 설정 집합, 위임 거부, 무효 처리·append-only) | 실제 SQL·트리거·정책 판정. **MCP 서버(tools/list·최종 전달)·PII 분석기·내부 Git 호출·워커 산출물은 대역** |
| 실제 Gitea | 임시 `gitea/gitea:1.27.3-rootless`에서 `provenance_gitea_check.py` | 3건 통과: Gitea가 내는 `archive/<sha>.tar.gz`의 해시 = Git 객체(tree+blob)로 계산한 해시(한글 파일명·빈 파일·중첩·바이너리 포함), 파일 변경 시 해시 변경, 없는 보관본은 오류 | 실제 제품. 소스는 합성 저장소 |
| 실제 스캐너 | 기기의 `intake-worker` 이미지(네트워크 없음, Trivy 캐시 사본, 이 작업의 `supply_chain/`)에서 `intake_worker_scanners_check.py` | 3건 통과 — (1) 합성 소스에 실제 Syft·Trivy·Semgrep·Gitleaks를 돌려 출처 기록(공급 주소·고정 커밋·파일 해시 = 독립 계산값과 일치·`LICENSE`에서 MIT를 Trivy가 판별)을 확인, (2) 검사기 버전 `Syft v1.51.1 · Trivy 0.74.0 · Semgrep 1.172.0 · Gitleaks 8.30.1`과 기기 캐시의 실제 DB 시각(2026-10-06, 9일)이 `vuln_db_updated_at`에 저장됨, (3) 알려진 취약 의존성(`PyYAML==5.3`·`Django==1.11.0`)에서 실제 치명적 발견 6건(CVE-2019-14234 등) → `HOLD`/`CRITICAL`, 취약 핀 없는 쪽은 `VALIDATED` | 실제 Syft·Trivy·Semgrep·Gitleaks. **소스는 합성 트리, clone은 대역(GitHub 필요)** |
| 정책 재생 | `policy_replay_lab_check.py`(격리 OPA) | `replay_cases_pac15.json` 10건: 공격 미탐 0·정상 오탐 0 | 합성 사례 |
| 기존 회귀 | 격리 랩의 `pac_boundary_check.py`·`security_edges_check.py`·`catalog_refresh_check.py`·`credential_binding_check.py`·`field_account_git_test.py` · 로컬 `endpoint_inventory_check`·`endpoint_snapshot_check` | 통과 | 단위/격리 |
| 실제 모델·하네스 | — | **미실행** | |
| upstream 효과(독립) | — | **미확인** | |
| 배포·정책 해시 | — | **미확인** (병합·배포 전) | |

### 이번에 일부러 확인하지 않은 것·기존 문제 (거짓 성공으로 세지 않음)
- `field_kit_check.py`의 `test_doctor_and_uninstall_against_the_fake`는 Windows에서 오류 — 기준 commit(`git archive 8cf3d08`)에서도 동일.
- `oss_audit_test.py::test_missing_scanner_fails_closed`가 격리 랩에서 실패 — 기준 commit 소스로 같은 랩에서도 동일(`secret_scan`·워커 변경과 무관, 실행 환경 차이로 추정, 원인 미조사).
- `replay_cases.json`(예전 코퍼스)은 `pac` 문서가 없어 `INPUT_CONTRACT`로 막힌다. `console.sh test`가 쓰는 코퍼스는 `replay_cases_pac15.json`이다.
- 위키 `check_wiki.py`는 23건 오류다 — 모두 "코드가 매핑 뒤에 바뀜(map_threats.py 재실행 필요)"·로컬 도구 원본 변경 유형이며 이 보고서의 링크·출처 오류는 없다. `map_threats.py`는 위키의 다른 파일을 다시 쓰므로 (허용 범위 밖) 실행하지 않았다. 병합 뒤 메인 에이전트가 한 번 돌려야 한다.
- `app.acceptance`(전체 스택)와 `console.sh test` 전체는 돌리지 않았다. `acceptance.py`의 원격 등록 시험은 새 규칙(도구 범위 필수, 신청자의 계약 검토 거부)에 맞게 고쳤지만 실행하지 않았다.

## 실패·미완료·한계

1. **패키지 레지스트리(npm/PyPI) 도입물**은 이 저장소의 도입 경로에 없다(GitHub 소스와 원격 엔드포인트만). 완료 조건의 "배포 파일 해시 대조"는 GitHub 소스 → 내부 Git 사본으로 구현했다.
2. 보관본 해시는 `.gitattributes`의 `export-ignore`·`export-subst`가 있는 저장소에서 체크아웃과 달라질 수 있다(보류로 끝남 = fail-closed). 승인 뒤 내부 Git 사본이 바뀌는 것을 주기적으로 다시 대조하지는 않는다.
3. 라이선스는 저장소 루트의 라이선스 파일만 읽는다. 읽지 못하면 승인자가 직접 적어야 하며 그 사실이 기록된다.
4. 외부 목적지(도구 범위)는 기록·표시만 한다. 외부 전송은 기존 PAC 전송 검사가 모두 막으므로 허용 목록으로 푸는 집행은 없다.
5. **철회 뒤 같은 승인으로 다시 등록할 수 있다**(기존 설계, `plane_sequence.py`의 복원 경로). 철회가 새 승인을 강제하지는 않는다 — 호출 거부만 증명했다. 새 승인을 강제하려면 복원 경로를 바꿔야 하므로 결정을 남긴다.
6. 자동 연장은 재검사를 하지 않는다(취약점 DB 신선도는 승인·등록 시점에만 본다).
7. D-79 원장 744~800 주석은 **쓰지 않았다**(운영 DB 금지). API는 `admin_caller`+사유 필수이며 격리 DB에서 확인했다.
8. UI는 레이아웃 스크린샷을 얻지 못했다(브라우저 창이 가려져 캡처 시간 초과). 고정 응답으로 렌더링한 뒤 각 화면 텍스트와 대화상자 입력을 읽어 확인했다.
9. `workstation/managed/render.py`(이미지 빌드용 카탈로그 전체 렌더링)는 이 규칙 밖이다.

## 다음 작업

- 병합·배포 순서와 메인 에이전트가 할 일은 아래 "사용자에게 필요한 입력"의 배포 체크리스트를 따른다.
- DEV-04(승인 재사용·경쟁 조건)·DEV-17(승인 후 신선한 요청자 인증)은 이번 작업이 닫지 않았다. 건별 승인의 단일 사용·경쟁은 기존 PAC-13이 맡고 있고 이번에는 독립성과 기록만 더했다.
- 성공 조건(WBS 구현 단계 가중): 위 8개 항목 중 G01.01·G01.02는 실제 도입 1건(공개 OSS)을 PJ1 기기에서 승인·등록하고 해시 대조가 일치하며, 취약점 DB를 일부러 낡게 했을 때 보류되는 것을 보면 된다.

## 사용자에게 필요한 입력

없음(이 작업은 사용자 결정을 기다리지 않는다). 메인 에이전트가 배포할 때의 체크리스트:

1. 병합 뒤 `intake-worker` 이미지를 다시 빌드한다(`supply_chain/provenance.py`를 복사하고 `--license-full`을 쓴다).
2. 취약점 DB가 낡았다(2026-10-06). 워커의 Trivy 캐시를 갱신하지 않으면 소스 도입 승인이 보류된다.
3. 기존 Console 등록의 도구는 배포 직후 꺼진다. 서버마다 `python3 tests/tool_scope_review.py --console … --server-id … --purpose … --asset …`(신청자가 아닌 관리자 계정)로 범위를 기록한다. 시험 대상 MCP의 범위를 에이전트가 승인하면 D-79와 같은 자가 승인이 되므로 사람 계정으로 한다.
4. D-79 무효 표시: 관리자 콘솔 토큰으로 `POST /gw/audit/annotations` `{"first_id":744,"last_id":800,"reason":"D-79: 에이전트가 시험 대상 MCP를 스스로 승인한 시험이라 무효"}` (Gateway `POST /api/audit/annotations`와 같음). 범위에 원장 행이 없으면 422.
5. `acceptance.py`·`console.sh test`를 실제 스택에서 한 번 돌린다(이번에는 못 돌림).
