# 2026-10-20 장기 실패 시험 분류

- 작업 브랜치: `10/20-stale-tests`
- 시작 기준: `a7aa43a1970333a28aaf9050ebaa476d8673c098` (작업 시작 시 clean)
- 범위: 사용자 제공 기기 실패 로그 16개와 저장소 코드·시험 설명·실행 구성을 정적으로 대조했다. 제품 코드와 시험 코드는 수정하지 않았다.
- 판정 기준: 실행 환경 누락은 (a), 제품 동작 계약이 바뀐 뒤 테스트 대역이 갱신되지 않은 경우는 (b), 현재 계약과 맞는 시험이 제품 동작 실패를 보여야 (c)로 분류했다. 로그에 HTTP 응답 본문이 없는 경우에는 로그와 소스가 뒷받침하는 범위만 판정했다.

## 파일별 분류

| 파일 | 분류 | 근거와 수리/실행 제안 |
| --- | --- | --- |
| `adversarial_check.py` | (a) 환경 의존 | 상단 문서가 실제 Gateway ingress, 직원 토큰, 실행 중인 랩을 요구한다. `console.sh test` 527–532행도 Compose의 office 망에서 Gateway URL을 지정해 실행한다. 일회용 전체 랩의 절차로 실행한다. |
| `field_release_check.py` | (a) 환경 의존 | 파일 상단이 SSH 검증 VM과 배포된 field Gateway에서 실제 Microsoft Learn 읽기를 명시한다. URL·서버·예상 리비전 인자는 릴리스 검증 입력이다. 누락 오류는 시험 실패가 아니라 잘못된 단독 실행 방식이다. |
| `intake_worker_scanners_check.py` | (a) 환경 의존 | 파일 상단이 intake-worker 이미지, 실제 Syft/Trivy/Semgrep/Gitleaks와 복사한 Trivy cache를 요구한다. `TRIVY_CACHE_DIR` 누락은 환경 미설정이다. |
| `managed_enrollment_check.py` | (a) 환경 의존 | 상단 실행 예가 `docker compose exec gateway`이며 agent-service·IdP·DB 경계를 검사한다. 단독 Gateway 이미지에는 `agent-service` DNS와 공유 DB가 없다. |
| `mcp_result_services_check.py` | (a) 환경 의존 | 상단이 실제 Presidio 서비스와 Gitleaks 실행 파일에 대한 appliance 검사를 선언한다. `InspectionUnavailable`은 검사기 연결 실패뿐 아니라 응답 JSON·형식 오류도 뜻하므로, 제공 로그만으로 연결 장애라고 단정하지 않는다. 이미지 단독 실행은 검사 서비스를 준비하지 않은 조건과 일치한다. |
| `oauth_rotation_check.py` | (b) 시험 대역 갱신 필요 | 이 파일은 10-13에 추가됐다. 10-18의 `8d542ac`(D-123)가 `_revoke_family()`에 서명 폐기 목록 기록을 넣으며 발급된 access token과 refresh digest 조회를 추가했다. 현재 대역이 `SELECT jti,expires_at FROM oauth_issued_tokens WHERE family_id=%s`에서 멈춘다. 아래 제안처럼 해당 SELECT 두 개를 DB 대역이 응답하도록 하며 기대 판정·반환값은 바꾸지 않는다. |
| `pac_boundary_check.py` | (a) 환경 의존 | `pac.capabilities()`는 `REGISTRY_DIR/capabilities.json`을 읽고 파일 없음은 권한 확인 불가로 실패 처리한다. `console.sh test` 520행이 실행 경로다. 해당 경로처럼 `./registry:/registry:ro` mount가 있어야 하며, 이 파일은 다시 `/registry/field`로 바꾸므로 그 하위 정본 파일도 있어야 한다. mount/정본 없이 이미지에 직접 실행한 실패는 제품 회귀 증거가 아니다. |
| `policy_replay_lab_check.py` | (a) 환경 의존 | 상단이 일회용 랩의 OPA를 대상으로 하고 `core.bootstrap()`으로 DB 준비를 호출한다. PostgreSQL·OPA가 연결된 랩에서 실행한다. PostgreSQL 연결 거부는 해당 선행 조건 부재다. |
| `protocol_versions_check.py` | (b) 현재 대역 보정 필요, 기준 실행의 코드 판본 미확정 | 현 HEAD의 `3ea141c`(D-149)는 협상 프로토콜 버전을 `_approved_tools()`의 네 번째 인자로 전달하도록 바꿨지만 `stub_tools`는 세 인자만 받는다. 아래 서명 보정은 D-149 이후 제품 코드와 함께 쓸 때 TypeError를 제거하고 `echo` 기대값을 유지한다. 시험 23행은 `sys.path` 앞에 `/app`을 넣고 25행에서 제품 모듈을 가져오므로 `/repo` 체크아웃에서 실행해도 실제 import는 이미지의 `/app/app` 코드일 수 있다. Dockerfile은 `/app`을 작업 디렉터리로 쓰고 `app`을 이미지에 복사한다. 제공된 baseline 동일 로그만으로 실행 이미지 revision·`mcp_facade.__file__`·오류 본문을 확인할 수 없어 그때도 D-149 대역 오류였는지, 별도 제품/환경 원인이었는지 확정하지 않는다. Jaeger export 경고는 시험 실패 원인이 아니다. |
| `provenance_gitea_check.py` | (a) 환경 의존 | 파일 상단이 폐기 가능한 실제 Gitea와 URL·사용자·암호 환경 변수를 요구한다. 비밀은 출력하지 말고 일회용 랩의 환경 설정에서 전달한다. |
| `real_mcp_check.py` | (a) 환경 의존 | opt-in 실제 공급자 MCP 시험이다. 하위 명령, 외부 네트워크, 공급자 계정과 격리된 자격 프로필을 갖춘 경우에만 실행한다. 빈 명령 오류는 CLI 사용법대로 실행하지 않은 결과다. |
| `real_mcp_gateway_check.py` | (a) 환경 의존 | 실행 중 Gateway, reviewed 계약, URL, 임시 등록 경로와 requester/approver 입력이 필요하다. 파일 상단에 2단계 실행이 기록돼 있다. |
| `real_warning_review_check.py` | (a) 환경 의존 | 별도 opt-in Notion 경고 검토이며 실행 중 Gateway, 사전 review 파일, URL과 두 명의 입력이 필요하다. |
| `reservation_effect_check.py` | (a) 환경 의존 | Docker CLI, Compose 랩, corp PostgreSQL과 실제 PostgreSQL MCP 효과를 필요로 한다. `docker` 실행 파일 부재는 호스트 단독 실행 환경 차이다. |
| `system_metrics_check.py` | (b) 시험 대역 갱신 필요 | 시험이 10-13에 추가된 뒤 `8d542ac`(D-123)가 `authenticated_user()`에 서명 폐기목록 조회를 추가했다. MCP-token 거부 케이스의 대역 claims에는 필수 `jti`가 없어 `claims["jti"]`에서 예외가 난다. 아래처럼 유효한 테스트 `jti`를 더하되 403 기대값은 유지한다. |
| `testbed_network_check.py` | (a) 환경 의존 | 상단이 SSH 시험 VM과 Docker의 fresh testbed를 요구한다. native test 이미지, 실행 중 Gateway, `--out` 인자까지 마련해야 한다. |

## (b) 적용한 최소 대역 보정

아래 세 파일의 대역 보정을 적용했다. 기존 시험의 기대값과 assertion은 바꾸지 않았다.

```diff
diff --git a/full_stack_lab/tests/oauth_rotation_check.py b/full_stack_lab/tests/oauth_rotation_check.py
@@ class Cursor:
-    def __init__(self, row=None):
+    def __init__(self, row=None, rows=None):
         self.row = row
+        self.rows = rows or []
+
+    async def fetchall(self):
+        return deepcopy(self.rows)
@@ class RotationDB:
+        if compact.startswith("SELECT jti,expires_at FROM oauth_issued_tokens WHERE family_id=%s"):
+            return Cursor(rows=[{"jti": token, "expires_at": row["expires_at"]}
+                                for token, row in state["issued"].items() if row["family_id"] == params[0]])
+        if compact.startswith("SELECT token_sha256 FROM oauth_refresh_tokens WHERE family_id=%s"):
+            return Cursor(rows=[{"token_sha256": digest} for digest, row in state["refresh"].items()
+                                if row["family_id"] == params[0]])
@@ asyncSetUp:
+        self.patches.enter_context(isolated_disposal())
```

기존 `termination_lab_support.isolated_disposal()`이 임시 키와 폐기 디렉터리를 준비하므로 실제 signed-list 동작을 유지하면서 시험 간 파일 상태를 격리한다. SQL 대역 결과는 시험 상태의 토큰·digest를 사용한다.

```diff
diff --git a/full_stack_lab/tests/protocol_versions_check.py b/full_stack_lab/tests/protocol_versions_check.py
-async def stub_tools(role, server=None, principal=""):
+async def stub_tools(role, server=None, principal="", protocol_version=None):
```

```diff
diff --git a/full_stack_lab/tests/system_metrics_check.py b/full_stack_lab/tests/system_metrics_check.py
@@
-        with patch.object(agent_contract, "authenticate", return_value=({"user_id": "root"}, {"sub": "root", "scope": "mcp"})), \
+        with patch.object(agent_contract, "authenticate", return_value=({"user_id": "root"}, {"sub": "root", "scope": "mcp", "jti": "00000000-0000-4000-8000-000000000001"})), \
             patch.object(oidc, "validate_session", AsyncMock()), \
+            patch("app.disposal.blocked", return_value=False), \
             patch.object(agent_service.system_metrics_sampler, "sample", self.sample), \
             patch.object(agent_contract.db, "fetch_one", AsyncMock()) as fetch:
```

JTI는 합성 식별자이며 폐기 확인은 false로 대역해 scope 거부 케이스의 403 기대값을 그대로 검사한다.

## 적용 hunk별 이유

### `oauth_rotation_check.py`

- `termination_lab_support.isolated_disposal` import와 `asyncSetUp()` 컨텍스트 등록: D-123 경로가 서명 폐기 목록을 기록하므로 각 시험에 임시 키·디렉터리를 제공하는 기존 격리 도구를 재사용했다. 폐기 동작 자체를 대역하지 않고 시험 종료 때 임시 상태를 정리한다.
- `Cursor.__init__()`의 `rows`와 `fetchall()`: D-123의 계열 조회가 사용하는 행 목록 커서 인터페이스를 기존 대역에 추가했다. 기존 `fetchone()`과 호출자의 반환값은 유지한다.
- 계열별 access-token `jti`/만료 시각 및 refresh-token digest 조회 분기: 실제 제품 SELECT 두 건을 현재 시험 상태의 발급 토큰·갱신 digest로 응답하게 했다. 미지원 SQL assertion을 제거하고 DB 폐기 상태에 대한 기존 assertion을 유지한다.

### `protocol_versions_check.py`

- `stub_tools()`에 기본값이 있는 `protocol_version` 네 번째 인자 추가: D-149의 `_approved_tools()` 호출 계약과 대역 서명을 맞췄다. 기존 호출과 `echo` 목록 기대값은 동일하다.

### `system_metrics_check.py`

- MCP claims 대역에 합성 `jti` 추가: D-123의 `authenticated_user()` 폐기 조회에 필요한 claim을 채운다. MCP scope 및 기대 권한 결과는 바꾸지 않았다.
- `app.disposal.blocked` false 대역: 이 케이스의 목적은 폐기 여부가 아니라 MCP scope의 관리자 경로 거부다. 폐기 파일 상태를 고정해 기존 403 검사가 해당 범위만 검사하도록 했다.

시험 대역 외 제품 코드·기대값·검사 범위는 변경하지 않았다. `protocol_versions_check.py`는 `/app` 이미지 모듈을 우선 import하므로 과거 실패 로그의 실행 판본 불확실성은 계속 남는다.

## (c) 제품 회귀

제공된 실패 로그와 확인한 시험·제품 계약에서 현재 제품 회귀로 확정할 항목은 없다. 세 (b)는 테스트 더블이 D-123의 조회·필수 claim 및 현 HEAD의 추가 인자를 표현하지 못해 생기는 실패다. `protocol_versions_check.py`는 `/app` 이미지 코드를 우선 import하므로 baseline과 HEAD 비교에 이미지 revision이 필요하다. 기기 로그에 JSON-RPC 오류 본문·`mcp_facade.__file__`·정확한 이미지 revision·registry mount 상태가 없어 실행된 제품 판본의 독립 결함까지 증명하지 않는다.

## 근거 위치

- 실행 구성: [`docs/ai/TESTING.md`](../../../../docs/ai/TESTING.md), [`full_stack_lab/console.sh`](../../../../full_stack_lab/console.sh)
- D-123: `8d542ac` (2026-10-18), [`docs/ai/DECISIONS.md`](../../../../docs/ai/DECISIONS.md)
- D-149: `3ea141c` (2026-10-20), [`docs/ai/DECISIONS.md`](../../../../docs/ai/DECISIONS.md)
- 관련 제품 코드: `gateway/app/idp.py`의 `_revoke_family()`·`authenticated_user()` 경로, `gateway/app/mcp_facade.py`의 tools/list 경로
- 시험/이미지 판본: `protocol_versions_check.py` 23·25행, `full_stack_lab/gateway/Dockerfile`의 `/app` 작업 디렉터리·`app` 복사
- 원격 HEAD 확인: `git ls-remote --symref origin HEAD`는 네트워크 연결 거부로 완료하지 못했다. 작업 브랜치가 가리킨 시작 commit은 위에 기록했다.

## 메인 반영 (Claude, 2026-10-20)

- `protocol_versions_check.py`: 목적지 허용 보정 뒤에도 `provider_asks`가 `WireRejected('도구 응답이 협상된 출력 형식과 일치하지 않습니다.')`로 실패했다. D-149가 공식 SDK의 wire 검증 실패를 보류 예외로 바꾼 정당한 변경이다. 시험의 뜻("어떤 실패든 맞고, 답하면 안 된다")을 유지하며 기대 예외에 `output_contract.WireRejected`를 더했다(기대값 변경 — Codex sol 적대 검증 대상).
- 기기 게이트웨이 이미지: oauth_rotation_check 7/7, system_metrics_check 10/10, protocol_versions_check 오류 없이 종료.

