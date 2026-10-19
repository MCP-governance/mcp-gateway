# 2026-10-20 D-123 복원 후 잔존 확인

- 작업자: Codex luna
- 코드 기준: 시작 commit `06379562e3ad625adfd0eda58191c5fbccb38a20`, 기존 작업 트리 변경 보존, 브랜치 `10/20-restore-residual`. 원격 HEAD 재조회는 GitHub 연결 실패.
- 시작 근거: DEV-63 / WBS G07.06 / POL-50, D-123, [종료 판정 모델](../../../../docs/ai/TERMINATION_MODEL.md), [D-120~123 분석](../../analysis/ops-response-d120-d123/README.md), [기존 실험 보고](2026-10-17-ops-response-d120-d123.md).
- 해결할 문제와 완료 조건: DB 복원으로 계정·장치 토큰, 갱신 토큰, 서버·등록 자격 참조가 돌아와도 DB 밖 서명 목록 대조 후 인증·호출과 하네스 관리 설정에서 차단되는지 PostgreSQL 격리 랩에서 확인한다.

## 결과

- `idp.revoke_principal_tokens()`와 `idp.revoke_device_tokens()`가 활성 access token과 refresh token 식별자를 DB 변경 전에 D-123 서명 목록에 기록하도록 보강했다. 기존 `_revoke_family()` 경로와 같은 보관 함수를 쓴다.
- 솔루션 기기 첫 실행에서 `close_case()`가 실제 판정이 없는 케이스를 거부했다. 원인은 시험이 `termination_cases`와 `revocation_targets`를 직접 INSERT하고 `ASSESSED` 상태를 꾸며낸 것이다.
- 시험을 수정해 종료 케이스와 자격 대상을 `decommission.open_case()`로 생성하고, 폐기 뒤 `decommission.assess()` 결과를 사용해 `close_case()`를 호출한다. 이때 공급자 자격 고지를 fixture에 설정해 제품 함수가 자격 대상을 열거하게 했다. 설정 확인은 케이스 개시 전에 수행한다. PostgreSQL 스냅샷·복원 행은 시험 대상 DB를 보존·복구하는 범위에서만 SQL을 쓴다. MCP 프로토콜 호출은 없다.
- 백업은 실험 fixture 행을 대상으로 한 PostgreSQL 논리 행 스냅샷이며 전체 DB `pg_dump` 파일은 아니다. 실제 PostgreSQL에서 이 복구 시나리오를 아직 실행하지 않았다.
- D-123 기존 결정의 구현 보강이므로 새 결정 번호는 추가하지 않았다. `status/current.md`는 변경하지 않았다.

### 변경 파일

- `full_stack_lab/gateway/app/idp.py`
- `full_stack_lab/tests/restore_residual_pg_check.py`
- `research/llm-wiki/status/backlog.md` (DEV-63 행의 마지막 상태 칸)
- `research/llm-wiki/status/reports/2026-10-20-restore-residual.md`

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| Python 구문 | `python -m py_compile full_stack_lab/gateway/app/idp.py full_stack_lab/tests/restore_residual_pg_check.py` (Windows, 2026-10-20) | 수정본 통과. 모듈 import·DB 실행은 확인하지 않음 | 명령 종료 코드 0 |
| 격리 PostgreSQL | 솔루션 기기에서 `restore_residual_pg_check.py` 첫 실행 | 실패: 직접 삽입한 `ASSESSED` 케이스가 제품 판정 검사를 통과하지 못함. 수정 후 기기 재실행 필요 | 사용자 제공 실행 결과 |
| 공백 검사·파일 형식 | `git diff --check`, 변경 Python/Markdown 파일 바이트 검사 (2026-10-20) | 수정본 통과: 공백 오류·UTF-8 BOM·CRLF 없음 | 명령 종료 코드 0 및 바이트 검사 출력 |
| 격리 PostgreSQL 재실행 | `cd full_stack_lab && tests/termination_dispatch_lab.sh up && tests/termination_dispatch_lab.sh run restore_residual_pg_check.py` | Codex 미실행: 이 PC에서 수행하지 말라는 작업 지시 | 솔루션 기기에서 실행 필요 |
| 기존 시험·OPA·실기기·배포 | 기존 기대값은 수정하지 않음 | 미실행 | 솔루션 기기/PJ1 검증 대기 |

## 실패·미완료·한계

- 수정한 PostgreSQL 복원 시험은 아직 재실행하지 않았다. 게이트웨이 이미지에서 DB 구문·제품 함수 상호작용·관리 설정 렌더 결과를 확인해야 한다.
- 시험은 `wbs-c-*` 랩이 제공하는 격리 Gitea 관리 API를 자격 폐기에 사용한다. 이 PC에서는 시험을 실행하지 않아 해당 API 효과와 PostgreSQL 복원을 확인하지 않았다. 공개·실제 서비스와 MCP upstream 요청은 범위 밖이다.
- 원격 HEAD는 네트워크 연결 실패로 재확인하지 못했다. 로컬 기준 commit과 브랜치는 확인했다.
- 기존 시험 파일 및 기대값 변경 없음. 사용자 결정이 필요한 기존 시험 변경도 없음.

## 다음 작업

솔루션 기기에서 다음을 실행해 JSON 체크 결과를 보관한다.

```bash
cd full_stack_lab
tests/termination_dispatch_lab.sh up
tests/termination_dispatch_lab.sh run restore_residual_pg_check.py
tests/termination_dispatch_lab.sh down
```

## 사용자에게 필요한 입력

없음. 지정된 솔루션 기기에서 실험실을 실행하면 된다. 시험은 `wbs-c-*` 전용 랩을 사용하고 제품 스택을 대상으로 하지 않는다.

## 기기 실행 결과 (Claude, 2026-10-20)

- 격리 실험실 `restore_residual_pg_check.py`: 10/10 통과(1.2초). 실행 중 대역 오류 4건은 수정(Claude 2·luna 재작업 1·Claude 1: 동기 함수 `disposal.blocked`에 await).
- 변이 확인: `idp.py` 수정을 빼면 3건 실패 — 서명 목록에 계정·장치 토큰이 없어 DB 복원 뒤 다시 살아난 토큰을 막지 못한다. 제품 공백이 실제였다.
- 기존 실험실 시험 `token_revocation_pg_check.py`는 main에서도 실패한다(D-123 이후 서명 폐기 목록을 초기화하지 않아 `/disposal/journal.jsonl` 없음으로 fail-closed). 이 브랜치에서는 같은 이유로 `device_revocation`도 실패한다. 시험 대역 보정은 적대 검증을 거쳐 별도로 한다. `dispatch_intent_pg_check.py`의 풀 종료 전파 1건 실패도 main과 같다.

