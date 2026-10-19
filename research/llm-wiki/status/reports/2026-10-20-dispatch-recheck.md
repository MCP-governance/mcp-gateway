# 2026-10-20 최종 전송 직전 재확인

- 작업자: Codex sol
- 코드 기준: `10/20-dispatch-recheck`, 시작/현재 HEAD `78deab0a056050c3da0a39a69b1cfc8d51eefa30`, 시작 시 clean, 결과 미커밋. 원격 HEAD는 `git ls-remote --symref origin HEAD`의 GitHub 연결 실패로 확인하지 못했다. 커밋·푸시·배포 없음.
- 변경 파일: `gateway/app/{core,dispatch,consent}.py`, 새 `tests/dispatch_recheck_check.py`(모두 `full_stack_lab/` 아래), `docs/ai/{DECISIONS,POLICY}.md`, 이 보고서, [원자 요구사항/근거](../../analysis/dispatch-recheck-1020/README.md)와 [검증 원본](../../analysis/dispatch-recheck-1020/verification.json), 백로그 DEV-43 행의 마지막 상태 칸. `status/current.md`와 기존 시험 파일은 변경하지 않았다.
- 시작 근거: DEV-43 / RV-03, `controls-1018/codex-sol-adversarial.md` 5·6번, D-133/D-134/D-139/D-142.
- 해결할 문제와 완료 조건: 판정 이후 주체 중지·동의 철회/만료·새 중요정보 열람이 최종 intent보다 먼저 커밋되면 전송하지 않는다. 일관 잠금 순서·실패 차단과 대역 교차 검증을 구현한다. 실제 PG/PJ1 검수는 메인 레인에서 수행하므로 백로그를 검수 완료로 올리지 않는다.

## 결과

최종 intent 트랜잭션이 주체 행과 현재 조건/등급을 덮는 동의 행을 공유 잠근다. 상태만 고치는 계정 UPDATE 및 동의 UPDATE는 이 잠금과 충돌한다. 동의 만료는 마지막 INSERT의 `clock_timestamp()`로 재확인한다. 전송 호출부는 같은 연결에서 흐름 출처를 다시 조회하고 늘었으면 P-FLOW-001로 차단한다. 중요정보 열람의 원장 append도 같은 주체별 advisory lock에 참여하므로 최종 흐름 조회와 intent 사이에 새 열람 게시가 끼지 않는다. 기존 D-142의 coarse/content 모드는 유지한다.

중지 계정은 P-INPUT-001, 유효 동의 부재는 P-CONSENT-001, 최종 조회/잠금/INSERT/커밋 장애는 P-CONTROL-FAIL-CLOSED다. 이들 실패는 도구 호출 이전에 끝나며 intent 트랜잭션은 롤백한다. 취소는 전파하고 잠금을 해제한다. 새 정책 ID·의존성·테이블·MCP 서버·자동 재시도는 없다. 감사 원장은 append-only이며 기존 행을 바꾸지 않았다. [D-140](../../../../docs/ai/DECISIONS.md)에 잠금 순서와 교착 회피·선형화 경계를 남겼다.

## 검증

환경은 Windows PowerShell 5.1 / Python 3.10.5 / Node 24.21.0, 2026-10-20 KST 이 작업 세션이다. 아래 실행 결과와 코드 SHA-256은 [verification.json](../../analysis/dispatch-recheck-1020/verification.json)에 보관했다. stdout/stderr와 반환 코드를 함께 기록하며 생략 건수를 통과 수에 합산하지 않는다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 신규 교차·실패 시험 | `python -B -X utf8 full_stack_lab/tests/dispatch_recheck_check.py` | 15/15 통과. 중지/철회 선커밋·대기 중 커밋·행 잠금 대기, INSERT 시각 만료, 새 출처·content 경계, 7단계 장애·취소. 차단 건 intent/클라이언트 호출 0·decision/policy_id 확인 | 검증 JSON의 첫 검사, 새 시험 파일 |
| 기존 중대 영향 회귀 | `python -B -X utf8 full_stack_lab/tests/high_impact_check.py` | 17 통과, 이미지 전용 7 생략 | 검증 JSON |
| 기존 흐름 지문 회귀 | `python -B -X utf8 full_stack_lab/tests/flow_fingerprint_check.py` | 순수 함수 17 통과, 이미지 전용 15 생략 | 검증 JSON |
| 기존 원장 결과 축 회귀 | `python -B -X utf8 full_stack_lab/tests/outcome_axes_check.py` | 8/8 통과 | 검증 JSON |
| Python 정적 구문 | `python -m py_compile` + 변경 Python 4파일 | 통과 | 검증 JSON |
| JS 정적 구문 | `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과, 화면 변경 없음 | 검증 JSON |
| 인증 경계 | `python -B -X utf8 full_stack_lab/tests/open_endpoints.py` | 통과. 무인증 1개·인증 필요 84개 문서 일치 | 검증 JSON |
| 공백·패치 | `git diff --check` | 통과 | 검증 JSON |
| 린트 | `python -m pyflakes` + 변경 Python 4파일 | 실행 불가, `No module named pyflakes` | 검증 JSON, rc=1 |
| 기존 통제 통합 단위 | `python -B -X utf8 full_stack_lab/tests/remaining_controls_check.py` | import 실패, `No module named pglast`, 시험 0건 실행 | 검증 JSON, rc=1 |
| 위키 목록/전체 검사 | `build_wiki.py`, `check_wiki.py --ci-ignored-local-sources` | 목록 생성 통과. 전체 검사는 코드 매핑 해시 불일치 19건으로 미통과(기존 매핑과 이번 core 변경 포함). 제외된 로컬 원본 경고도 있음 | 검증 JSON에 추가 기록 |
| 프로토콜·실제 PG 경쟁 | 실행하지 않음 | 미실행 | 없음 |
| 실제 모델·PJ1 하네스·OSS MCP | 실행하지 않음 | 미실행 | 없음 |
| 독립 upstream 효과·배포/정책 해시 | 실행하지 않음 | 미확인 | 없음 |

## 실패·미완료·한계

대역 시험은 PostgreSQL 스냅샷·EvalPlanQual·실제 교착·커밋 응답 소실을 재현하는 DB 엔진이 아니다. 실제 sender 함수 본문을 실행해도 클라이언트는 AsyncMock 단위 대역이며 실제 MCP 실행/외부 효과 증거가 아니다. 로컬에 스택을 띄우거나 의존성을 설치하지 않았다. 도구가 이미 전송된 뒤 결과를 잃은 경우의 기존 불확실성 처리도 바꾸지 않는다.

intent가 먼저 커밋됐으면 그 호출은 전송 가능 호출로 기록된 것이다. 이때 뒤늦은 중지/철회 writer는 커밋까지 기다리고, 변경 후 다음 요청은 차단된다. 이미 커밋된 호출의 외부 효과 복구 또는 intent와 실제 송신 사이 간격의 취소를 보장하지 않는다. 흐름 출처 증가는 재판정 대신 이번 호출을 차단하므로 첫 요청의 보수적 오탐이 가능하다. 원장상 출처 정의·10분 창·동일 서버 제외·content 변형 미탐은 기존 한계다.

PowerShell의 ASCII 파이프로 추가한 D-140 한글이 깨진 쓰기 오류를 발견해 해당 추가분만 제거하고 apply_patch로 다시 썼다. 최종 파일은 UTF-8(BOM 없음)·LF로 검사한다. 위키 전체 매핑 재생성은 이 레인의 변경 범위를 넘어 수행하지 않았으며 미통과로 남긴다. `capture_status.py --help`가 실제 생성한 스냅샷 두 파일은 시작 clean 기준 바이트로 복원했다.

## 기존 시험 변경 필요

없음. 기존 시험 파일과 기대값은 수정하지 않았다. 로컬 실행 가능 57건 통과, 이미지 전용 22건 생략이며 import 실패 시험은 통과에 포함하지 않는다. 이미지 전용 회귀와 실제 PG가 아직 남아 있으므로 그 범위까지 호환성을 입증한 것은 아니다.

## 다음 작업

DEV-43은 구현·대역 시험 완료, 실제 PG·PJ1 검수 대기다. 아래는 **미실행 명령**이다. 같은 작업 트리를 쓰는 WSL에서 기존 담당 격리랩이 준비된 상태로 실행하면 제품 스택이 아닌 솔루션 기기의 격리 DB/게이트웨이 이미지에서 검사한다. 기존 드라이버의 이미지/네트워크 준비는 담당자가 확인한다.

```bash
cd full_stack_lab
bash tests/termination_dispatch_lab.sh run dispatch_recheck_check.py
bash tests/termination_dispatch_lab.sh run dispatch_intent_pg_check.py
bash tests/termination_dispatch_lab.sh run dispatch_effect_lab.py
bash tests/termination_dispatch_lab.sh run remaining_controls_check.py
bash tests/termination_dispatch_lab.sh run flow_fingerprint_check.py
```

중대 영향의 이미지 전용 시험은 같은 `/app/app`·`/tests` 마운트가 있는 게이트웨이 이미지 안에서 `python /tests/high_impact_check.py --gateway`로 실행한다. 기존 PG 시험은 저장/종료/승인 경계를, effect 시험은 기존 공개 Gitea MCP 효과·계정 중지 경계를 다룬다. 새 동의/흐름의 실제 PG 장벽 시험과 PJ1 실제 하네스 효과는 별도로 교차 순서를 계측해야 한다. 정상·차단 사유·intent 0·독립 효과 0·복구 후 재호출을 같은 request_id로 연결하고 백로그 검수 상태를 올린다. OPA 규칙 변경이 없어 이번에 Rego 시험을 추가하거나 실행하지 않았다.

## 사용자에게 필요한 입력

없음. 기존 솔루션/PJ1 검수 경로를 사용하며 새 업무 권한·실사용 데이터·자격증명은 요구하지 않는다.
