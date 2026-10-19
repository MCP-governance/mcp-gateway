# 2026-10-20 OAuth 음성 시험

- 작업자: Codex luna
- 코드 기준: `554307444dfc8dcb91c281c1a282427ee83e2efc`, 시작 시 clean, 브랜치 `10/20-oauth-negative`; 원격 HEAD 조회는 네트워크 차단으로 실패
- 변경 파일: `full_stack_lab/gateway/app/agent_contract.py`, `full_stack_lab/tests/oauth_negative_pg_check.py`, `docs/ai/DECISIONS.md`, `research/llm-wiki/status/backlog.md`, 이 보고서
- 시작 근거: DEV-05, D-10, D-123, `restore_residual_pg_check.py`, `termination_dispatch_lab.sh`
- 해결할 문제와 완료 조건: 실제 IdP 토큰의 정상 수용과 audience·scope·만료·철회·발급키·알고리즘 음성 입력이 MCP 호출 전 거부되고 dispatch intent가 0인지 격리 PostgreSQL에서 확인한다.

## 결과

`authenticated_user(..., require_mcp=True)`에 `mcp` scope 검사(없으면 403)를 추가했다. 새 `oauth_negative_pg_check.py`는 실제 `idp.token()` 발급·실제 `mcp_facade._caller()` 검증 경로를 사용해 정상군과 다음 공격군을 확인한다: 다른 audience, `mcp` 없는 `console` scope, 만료, `idp.revoke()`로 철회된 jti, 다른 EdDSA 키, `alg=none`, HS256 혼동. 각 거부 직전/직후 `dispatch_intents`를 확인해 해당 principal intent 0을 요구한다. 서명 폐기 목록은 `isolated_disposal()`로 임시 폴더와 시험용 키를 준비한다. 외부 MCP 호출은 시험 코드에 없다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | `python -m py_compile full_stack_lab/gateway/app/agent_contract.py full_stack_lab/tests/oauth_negative_pg_check.py` | 통과 | 로컬 종료 코드 0 |
| 정적 검사 | `git diff --check` | 통과 | 로컬 종료 코드 0 |
| PostgreSQL 실험 | `cd full_stack_lab && tests/termination_dispatch_lab.sh run oauth_negative_pg_check.py` | 미실행 — 솔루션 기기에서만 | 솔루션 기기 실행 로그 |
| 실제 모델·하네스 | PJ1 실제 하네스 | 미실행 | 없음 |
| upstream 효과 | 외부 MCP 서버 전송 | 미확인, 이 시험은 외부 연결을 하지 않음 | 없음 |
| 배포·정책 해시 | 솔루션 기기 배포 | 미실행 | 없음 |

## 기존 시험 변경 필요

`full_stack_lab/tests/token_revocation_pg_check.py`는 D-123 이후 새 임시 서명 폐기 목록 genesis가 없어 인증 첫 단계에서 `IntegrityError("폐기 목록 누락 또는 손상")`를 낼 수 있다. 사용자 지시에 따라 기존 시험에는 손대지 않았다. Codex 적대 검증 후 적용할 최소 diff는 다음과 같다.

```diff
-from termination_lab_support import Checks, add_principal, apply_schema, run, signing_keys
+from termination_lab_support import Checks, add_principal, apply_schema, isolated_disposal, run, signing_keys
@@
-    for case in (family_revocation, issue_against_revoke, issuance_rolls_back, device_revocation):
-        await CHECKS.case(case.__name__, case())
+    with isolated_disposal():
+        for case in (family_revocation, issue_against_revoke, issuance_rolls_back, device_revocation):
+            await CHECKS.case(case.__name__, case())
```

이는 제품/시험의 변경이 아니라 검토용 제안이다. PostgreSQL 체크들은 같은 `DISPOSAL_DIR`을 공유하므로 케이스 네 개 전체를 감싸면 fixture 초기화 한 번으로 연속 시험을 수행한다.

## 실패·미완료·한계

로컬에서는 pyflakes/DB 드라이버가 없어 gateway import 실행은 불가하며, 이 PC에서 PostgreSQL 실험도 하지 않는다. `mcp_facade._caller()`가 거부한 뒤 intent 0이라는 증거는 실제 upstream 연결의 독립 관측과 다르다. 기기에서 이 파일을 실행하고 별도 Gateway 이미지·PJ1 실기기 단계를 확인해야 한다. 커밋·배포하지 않았다.

## 다음 작업

DEV-05의 다음 단계는 솔루션 기기에서 `oauth_negative_pg_check.py` 실행, 새 시험 결과 검토, 제안된 `token_revocation_pg_check.py` fixture diff의 Codex 적대 검증 및 필요 시 적용이다.

## 사용자에게 필요한 입력

없음. 기기 실행은 저장소 소유자의 배포·시험 흐름에 따른다.

## 기기 실행 결과 (Claude, 2026-10-20)

- 격리 실험실 `oauth_negative_pg_check.py`: 11/11 통과. Claude가 "실제 콘솔 세션 토큰" 사례를 더했다 — 위조한 console scope 토큰은 콘솔 세션 행이 없어 `validate_session`에서 이미 막히므로 scope 검사를 증명하지 못했다.
- 변이 확인: `agent_contract.py`의 mcp scope 검사를 빼면 실제 콘솔 로그인 토큰이 MCP 인입을 통과한다(status 200). 제품 공백이 실제였다.

