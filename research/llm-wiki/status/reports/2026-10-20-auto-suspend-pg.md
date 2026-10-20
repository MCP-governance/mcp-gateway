# 2026-10-20 DEV-62 자동 중지 PostgreSQL 시험

- 작업자: Codex luna
- 코드 기준: 시작 commit `751aee9866585a6797f5d25f3932d63bd58b1e01`, 브랜치 `10/20-auto-suspend-pg`. 작업 시작 시 검사 파일·보고서·DEV-62 백로그 행은 이미 작업 트리에 있었음. 원격 HEAD 재조회는 GitHub 네트워크 연결 실패.
- 시작 근거: DEV-62 / WBS G07.05 / POL-43, D-122, [작업 E 보고](2026-10-17-ops-response-d120-d123.md), [최종 dispatch 경합 시험](../../../../full_stack_lab/tests/dispatch_recheck_pg_check.py), [복원 잔존 PostgreSQL 시험](2026-10-20-restore-residual.md).
- 해결할 문제와 완료 조건: 격리 PostgreSQL에서 선택 제한이 가능한 도구 계약 변경은 해당 도구만 감추고 서버를 유지하며, 제한 범위를 확정할 수 없는 변경만 서버를 중지하는지 확인한다. 또한 목록·최종 intent 차단·다른 서버 독립성·두 경합 순서·관리자 복귀와 이력 보존을 확인한다. PostgreSQL 시험은 솔루션 기기에서 실행한다.

## 결과

- 새 `full_stack_lab/tests/auto_suspend_pg_check.py`를 보강했다. 기존 시험 파일·기대값과 제품 코드는 바꾸지 않았다.
- 재실행 10건 중 8건 통과였던 두 목록 실패는 제품 SQL 결함이 아니었다. 검사는 SQL 복사본이 아니라 제품 `mcp_facade._approved_tools()`를 불렀지만, `auto-suspend-*` fixture 신원은 `pac.scope()`의 합성 주체 허용 목록에 없어 SQL 필터 뒤 제품의 최종 정책 가시성 필터에서 모든 도구가 제외됐다. 시험 주체를 capability 목록의 `acceptance-employee` 및 `acceptance-admin`으로 바꿨다.
- 한 도구의 입력 스키마 변경은 제품 `core.refresh_catalog()`로 유발하며 `_discover` 응답만 대역 처리한다. fixture는 실제 승인 카탈로그의 `gitea.get_me`, `gitea.get_gitea_mcp_server_version`, `filesystem.list_directory`와 일치하는 이름을 쓴다. 도구별 enabled·input schema·승인/관측 스키마·설명 해시를 채우고 각 서버에 도구 수가 맞는 `catalog_snapshots` 행(exact match, 빈 restricted tools)을 추가한다. 드리프트 뒤 제품 목록 함수가 변경 도구를 숨기고 같은 서버의 무관한 도구 및 다른 서버 도구를 노출하는지 검사한다.
- `restricted_tools()`가 `None`을 내는 미분류 변경 증거를 `ops_response.contain_drift()`에 직접 전달해 서버 전체 중지와 증거 기록을 확인한다. 이 미분류 증거는 현재 `refresh_catalog()`가 생성하는 정상 DRIFT 종류가 아니므로, 실제 공개 MCP의 변경이 이 입력을 만든다는 주장은 하지 않는다.
- 반복 이상은 제품 감사 원장 함수 `core._record_decision()`으로 D-122 정책 ID 판정을 기록한 뒤 제품 `ops_response.contain_repeated()`를 호출한다. 기본 임계값 도달 시 전체 서버가 중지되고, 자동 복귀 없이 호출이 거부되며, `ops_response.resume()`에 관리자 행위자·사유를 남긴 뒤 intent가 다시 기록되는지 확인한다.
- 실제 도구 노출 함수 `mcp_facade._approved_tools()`의 승인 해시·스냅샷·활성·스키마·수명주기 조건을 통과한 도구가 영향 범위대로 노출되는지 검사한다. `dispatch.record()` 최종 SQL은 중지 서버 intent 0건과 독립 서버 intent 1건을 비교한다.
- `dispatch_recheck_pg_check.py` 방식을 따라 콜백 장벽과 PostgreSQL 잠금 대기를 관측한다. dispatch가 서버 공유 잠금을 먼저 잡으면 intent 1건 뒤 중지되고, 중지 쓰기가 먼저 잠금 대기열에 서면 중지 commit 뒤 dispatch intent 0건이어야 한다.
- PostgreSQL은 기존 `termination_dispatch_lab.sh`가 만드는 임시 DB를 쓴다. 서명 폐기 저장소는 `isolated_disposal()`로 실행 중 임시 초기화한다. 외부 MCP 요청은 보내지 않는다.
- 선택 제한 가능한 변경의 자동 전체 중지는 D-127과 DEV-52의 범위 제한 원칙에 맞지 않아 제품 변경을 적용하지 않았다. 전체 중지는 `restricted_tools()`가 제한 대상을 결정하지 못하는 입력으로만 확인한다.

### 변경 파일

- `full_stack_lab/tests/auto_suspend_pg_check.py`
- 시험 보강만 수행했으며 `docs/ai/DECISIONS.md`에는 제품 결정을 추가하지 않았다.
- `research/llm-wiki/status/backlog.md` (DEV-62 상태 칸만)
- 이 작업 보고서

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| Python 문법 | `python -m py_compile full_stack_lab/tests/auto_suspend_pg_check.py` (Windows, 2026-10-20) | 통과. 제품 의존성 import·DB 쿼리는 실행하지 않음 | 명령 종료 코드 0 |
| 공백 검사 | `git diff --check` (Windows, 2026-10-20) | 통과 | 명령 종료 코드 0 |
| 실제 PostgreSQL | `tests/termination_dispatch_lab.sh run auto_suspend_pg_check.py` (솔루션 기기) | 미실행; 이 PC에서는 실행하지 않음 | 기기에서 출력 보관 필요 |
| 외부 MCP·실기기·배포 | 없음 | 미실행 | 없음 |
| 원격 HEAD | `git ls-remote --symref origin HEAD` | 미실행 실패: GitHub 연결 차단 | 명령 출력 |

## 실패·미완료·한계

- 시험은 추가됐지만 PostgreSQL에서 아직 실행되지 않아 DEV-62의 실 DB 검증 완료로 보지 않는다. 공유 잠금 순서, 등록 카탈로그에 맞춘 목록 함수, 복귀 후 전체 정책 경로는 솔루션 기기 실행으로 확인해야 한다.
- `_discover` 대역은 외부 요청을 막고 저장소의 제품 refresh 경로를 통과시키기 위한 경계 대역이다. 탐지 결과가 실제 공개 OSS MCP 계약 변경에서 생긴다는 증거는 아니다. 반복 이상 판정도 게이트웨이의 판정 원장 저장을 사용하지만 OPA·MCP 호출을 재현하지 않는다.
- D-127의 선택 제한과 제품 조회 조건은 일치한다. `_approved_tools()`는 최신 스냅샷의 exact match 또는 제한 목록 제외 여부와 승인/관측 해시·enabled·input schema·서버 상태·수명주기를 확인한다. 제품 결함은 확인되지 않았으며 두 실패는 정책 테스트 주체 fixture 불일치로 설명된다.
- `OPS_AUTO_STOP_SOURCES`에서 `drift`를 제외한 배치는 DRIFT 자동 중지를 사용하지 않는다. 기본 설정과 실제 배포 환경 설정이 같은지는 미확인이다.
- 중지된 서버의 원격 프로세스 정지, 이미 전송된 호출 취소, 배포·PJ1·운영 화면은 확인하지 않는다.
- 기존 시험 기대값 변경은 필요하지 않았다.

## 다음 작업

솔루션 기기에서 다음을 실행하고 전체 JSON 출력을 보관한다.

```bash
cd full_stack_lab
tests/termination_dispatch_lab.sh up
tests/termination_dispatch_lab.sh run auto_suspend_pg_check.py
tests/termination_dispatch_lab.sh down
```

모든 검사가 통과한 뒤 DEV-62의 상태를 실 DB 시험 범위에 맞춰 갱신한다. 기기 시험 전에는 미완료로 둔다.

## 사용자에게 필요한 입력

없음. 지정된 솔루션 기기의 일회용 `wbs-c-*` 실험실에서 실행한다.
