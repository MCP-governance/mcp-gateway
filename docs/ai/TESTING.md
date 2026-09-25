# 검증 — 무엇이 무엇을 보장하나

> 한 번에: `cd full_stack_lab && ./console.sh test` (스택이 떠 있어야 한다. CI는 `up --no-llm` 후 실행).
> 결과물은 `full_stack_lab/reports/`에 남는다. 실패 하나라도 있으면 종료 코드 1.

## 1. 층별 구성

| 순서 | 무엇 | 파일 | 보장 | 소요 |
| --- | --- | --- | --- | --- |
| 1 | Rego 단위 시험 | `opa/policy_test.rego` (85건) | 333 행렬, MCP-* 통제, 예외(유효기간·범위·자가승인·보완통제), 승인형 예외, 관리대장 필수 항목, 충돌 우선순위 | 수 초 |
| 2 | 분류기 self-check | `gateway/app/classify.py` (`python -m app.classify`) | 경로·SQL·URL·메일·Redis 키 분류, DLP(주민번호·카드 Luhn·휴대폰·AWS 키·개인키·비밀번호), 행위 승격 | 수 초 |
| 3 | Gateway 인수 시험 | `gateway/app/acceptance.py` (9건) | `/mcp/` 401+RFC 9728 챌린지, 역할별 도구 목록, 미승인·미등록 도구 차단, 스키마 검증, 계약 드리프트 차단→복구, 승인 1회 실행, 관찰 모드 기록, 감사 체인 | ~30초 |
| 4 | 직원의 하루 | `workstation/scenarios/*.toml` (21건, scripted) | 실제 워크스테이션이 실제 서버에 보내는 업무 21건이 기대 판정(Allow/Alert/Approval/Block)과 일치 | ~1분 |
| 5 | 종료 판정 흐름 | `tests/termination_flow.py` (21건) | UR-GITEA-DEV T3→T2→T1·종결, UR-EMAIL-ASSIST T3·위험 수용 없는 종결 거부·고지 요청서, 복원 | ~1분 |
| 6 | 보안 회귀 | `tests/security_regression.sh` (45건 안팎) | 망 분리(실제 소켓), loopback 게시, 읽기 API 토큰, Console 역할 경계, 로그아웃 즉시 효력, OPA 정지→`P-CONTROL-FAIL-CLOSED`, 상위 서버 정지→미실행, 감사 변조 탐지, 계약 잠금 일치, 격리 워커 검사기 | ~1분 |
| 7 | 논문 실험 | `gateway/app/experiments.py` + `tests/experiments_check.py` | E1·E2·E3 findings가 논문 주장과 같다 | ~30초 |

정적 검사(CI `static` job, 스택 불필요): pyflakes, `bash -n`, `node --check`, 검사기 self-check,
`tests/open_endpoints.py`(무인증 API 목록 ↔ `full_stack_lab/README.md` 문장), compose 망·포트·서명 키 경계,
Rego 시험. → `.github/workflows/verify.yml`

## 2. 개별 실행

```bash
docker run --rm --entrypoint /opa -v "$PWD/opa:/policy:ro" openpolicyagent/opa:1.20.2-static test /policy -v
docker compose exec -T gateway python -m app.classify
docker compose exec -T gateway python -m app.acceptance
./console.sh workday all --mode scripted --check
python3 tests/termination_flow.py
tests/security_regression.sh
./console.sh experiment e1 && python3 tests/experiments_check.py reports/experiment-e1.json
```

호스트에서 도는 스크립트(`termination_flow.py`, `security_regression.sh`, `watch.py`)는
`LAB_CONSOLE_URL`·`LAB_GATEWAY_URL`로 포트를 받는다. `console.sh`가 `.env`의 포트로 export한다.
직접 돌릴 때는 `export LAB_CONSOLE_URL=http://127.0.0.1:18000 LAB_GATEWAY_URL=http://127.0.0.1:18080`.

## 3. 시험을 쓸 때의 규칙 (여기서 실제로 밟은 것들)

- **거짓 통과 금지.** 검사 도구가 죽으면 실패여야 한다. 예: 포트 검사 파이썬이 문법 오류로 빈 문자열을
  냈고 `${exposed:-none}`이 그걸 "노출 없음"으로 읽었다 → 성공했을 때만 `none`을 출력하게 고침.
- **스스로 원복.** 상태를 바꾸는 시험(OPA 정지, 서버 정지, 감사 트리거 해제, 승인 해시 변조, 관찰 모드)은
  `trap`/`finally`로 되돌린다.
- **남의 절차를 되돌리지 않는다.** 누가 종료 케이스를 열어 둔 서버는 acceptance가 SKIP한다(복원하지 않음).
  workday `--check`는 그 경우 실패한다 — 정상이다. 케이스를 정리한 뒤 다시 돌린다.
- **판정은 결정·정책 id까지 본다.** "Block이면 됨"이 아니라 `MCP-CATALOG-001`인지 본다. 다른 이유로
  막힌 것을 통과로 세면 통제가 사라져도 모른다.
- 새 통제를 넣으면: Rego 시험 + (Gateway 경로면) acceptance 한 건 + (업무 시나리오면) TOML 한 건.

## 4. 알려진 제약
- workday의 llm 모드는 모델 품질에 좌우된다(qwen2.5:1.5b). 기대 판정 대조는 scripted 모드로만 한다.
- 보안 회귀는 OPA와 mcp-git을 잠깐 멈춘다. 다른 사람이 Console을 쓰는 중이면 몇 초간 차단 판정이 난다.
