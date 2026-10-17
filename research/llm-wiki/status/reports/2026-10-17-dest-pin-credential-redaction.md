# 2026-10-17 dest-pin-credential-redaction

- 작업자: Codex
- 코드 기준: `9537c0b494a0c4d45c615caa4797674f273d270f`, 시작 시 clean, 기존 브랜치 `10/17-dest-transport`. 브랜치 변경·커밋·푸시 없음. 종료 시 변경은 작업 트리에 남겼다.
- 시작 근거: [기능명세 G03.05·G03.08](../../analysis/feature-spec-2026-10-17/README.md), DEV-41·42·53·56, POL-10·14·40, [LIB-K09·10·25](../../papers/policy50-gap-references.md).
- 해결할 문제와 완료 조건: 외부 MCP endpoint의 DNS 재바인딩과 오류/키트의 인증정보 노출을 막는다. 구현·로컬 단위 시험까지 수행했으며 실제 HTTPX 풀·TLS·배포·PJ1은 미검증이다.

## 결과

`destination.PinnedBackend`가 새 TCP 연결 직전 DNS의 모든 주소를 검사하고 첫 검증 숫자 IP로만 접속한다. 외부의 private/loopback/link-local/multicast/reserved/unspecified/mapped 내부 주소, 혼합 응답·해석 실패는 `Block/MCP-EGRESS-001`이다. URL/HTTP origin·Host·TLS SNI와 인증서 검증 이름은 바꾸지 않는다. 메인 검토 후 내부 승인 근거는 등록 endpoint 완전 일치·단일 DNS 라벨의 네트워크 위치 또는 같은 주소의 ACTIVE 실행기로 정정했다. `deployment` 계약 분류는 사용하지 않는다. 직원별 풀에 내부 분류도 결속한다. 탐색·건강 확인·호출 외에 종료 HEAD와 E2 세션 조사도 같은 client를 사용한다.

조직 SSO OIDC 경로가 있어 Authlib discovery/JWKS/토큰과 직접 refresh/introspection/revocation에 동일한 IP 검사를 연결했다. MCP upstream의 자동 OAuth client는 구성되어 있지 않다. Gateway protected-resource metadata는 제공만 하며 이를 외부에서 가져오는 코드는 없다.

`secret_scan.redact_error()`는 기존 Secret 패턴과 Gitleaks 검사에 연결한다. 자격 query/Authorization, 탐지 결과, 검사 장애, 500자 초과는 전체 `[REDACTED]`다. `_record_decision()`에서 event와 INSERT 값을 함께 가린 뒤 해시를 계산하므로 하네스 응답과 원장 error가 일치한다. 기존 원장은 수정하지 않는다. HTTPException/입력 검증/인증 거절, 예상 밖 MCP handler 예외, 카탈로그 진단과 종료 probe 오류의 원문 노출도 막는다.

임시 HOME/CODEX_HOME에서 field kit 설정·관리형 파일·CLI 인자 전체를 검사했다. endpoint 관리 정책의 Linux/Windows 파일 생성·쓰기에도 가짜 토큰이 없음을 확인했다. OS 집행 코드는 읽기만 했고 수정하지 않았다. DEV-64·원격 기기·docker compose는 실행하지 않았다. `status/current.md`는 메인 통합 영역이므로 변경하지 않았다.

변경 파일:

- `full_stack_lab/gateway/app/`: `destination.py`(신규), `upstream.py`, `core.py`, `secret_scan.py`, `mcp_facade.py`, `main.py`, `oidc.py`, `decommission.py`, `experiments.py`.
- `full_stack_lab/tests/`: `dest_pin_credential_redaction_check.py`, `dest_pin_transport_check.py`(모두 신규).
- `full_stack_lab/opa/policy_ledger.json`: 기존 ID의 연결 경계 검사·집행 위치 명시. Rego 판정 로직 변경 없음.
- `docs/ai/DECISIONS.md`(D-116·117), `docs/ai/PAC_MAPPING.md`(분류와 연결 검사 경계 정정).
- `research/llm-wiki/analysis/dest-pin-credential-redaction/README.md`, `validation.json`: 원자 요구·심볼·행·SHA-256·OSS 근거·실제 명령 출력.
- 이 보고서, `status/backlog.md`의 DEV-41·42·53·56 상태. 공통 저장소 스냅샷은 아래 검증 기록에 표시한다.
- 위키 유지 작업: `tools/map_threats.py`의 목적지/오류 경계 연결, 재생성 `catalogs/threats.json`·`threats/control-map.md`, `status/repository-snapshot.json`·`.md`.

## 검증

### 메인 검토 수정 — 2026-10-17

- 수정 파일: `upstream.py`, `oidc.py`, `tests/dest_pin_credential_redaction_check.py`, `tests/dest_pin_transport_check.py`, `opa/policy_ledger.json`, D-116 및 이 보고·분석·검증 근거와 관련 위키 상태/매핑. 앞선 작업 트리를 이어 수정했으며 커밋·푸시·브랜치 변경·원격 접속 없음.
- 초기 deployment 분류는 email/gitea 정상군을 차단하는 결함이었다. 실제 `catalog.toml`에서 두 provider 레코드를 읽어 사설 IP 정상 접속을 검사하고, 외부 GitHub FQDN의 같은 사설 DNS 응답은 `MCP-EGRESS-001`로 차단함을 검사했다. 초기 provider=외부 단정 시험은 제거했다.
- 실제 `compose.keycloak.yaml`의 `OIDC_DISCOVERY_URL`과 동적 백채널 설정을 읽는 회귀를 추가했다. 설정된 `127.0.0.1:18090`·`keycloak:8080`만 내부 예외로 두며 discovery/certs/token/introspection/revoke/userinfo를 사설 IP에 고정해 접속한다. metadata가 지목하는 다른 사설 호스트·포트는 자동 승인하지 않는다.
- `enforced_by`는 `gateway`로 정정했다. 기존 OPA egress 판정은 유지한다.
- `python -X utf8 -m unittest discover -s full_stack_lab/tests -p 'dest_pin*_check.py' -v`: 18개 중 **16개 통과·HTTPX 풀 2개 skip**, 종료 0. skip은 import 대상 `httpx`/`httpx2`가 없을 때만 적용하며 다른 누락 의존성이나 실행 오류를 삼키지 않는다. 현재 코드 해시와 원문 결과는 [review-validation.json](../../analysis/dest-pin-credential-redaction/review-validation.json). 아래 초기 14개/HTTPX import 실패 기록은 이전 이력으로 보존한다.

메인이 **솔루션 기기의 최신 변경이 반영된 gateway 이미지**에서 실행할 명령(이 작업에서는 미실행):

```bash
cd full_stack_lab
docker run --rm --network none -v "$PWD/tests:/tests:ro" --entrypoint python \
  "$(docker compose -f compose.yaml -f compose.field.yaml images -q gateway)" \
  -m unittest discover -s /tests -p dest_pin_transport_check.py -v
```

기대 결과는 풀 시험 **2개 통과·skip 0개**다. 이미지의 `/app/app` 코드를 사용하며 in-memory byte stream·DNS 대역만 쓰고 DB/외부 네트워크에 접속하지 않는다. 이 시험도 실제 인증서 수락 및 Keycloak 로그인/갱신/검증/로그아웃을 입증하지 않으므로 실제 기능 검증은 메인이 별도로 수행한다.

실행 시각·명령별 실제 stdout/stderr·종료 코드: [validation.json](../../analysis/dest-pin-credential-redaction/validation.json). Windows Python 3.10, 로컬 함수 단위 대역만 사용했다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 네트워크 없는 단위 | `python -X utf8 -m unittest discover -s full_stack_lab/tests -p dest_pin_credential_redaction_check.py -v` | 14개 PASS, 종료 0 | validation.json |
| 정적 인증 경계 | `python -X utf8 full_stack_lab/tests/open_endpoints.py` | PASS, 무인증 1·인증 필요 70(장치 8) | validation.json |
| 정적 구문 | 표준 `ast.parse` 전체 gateway Python+신규 시험 39개, `json.loads` 정책 ledger | PASS | validation.json |
| JS 구문 | `node --check full_stack_lab/gateway/app/agent_static/console.js` | PASS, 종료 0 | validation.json |
| diff | `git diff --check` | PASS, 종료 0 | validation.json |
| pyflakes | `python -X utf8 -m pyflakes` 변경 Python 11개(전체 인자는 validation.json) | 미실행: `No module named pyflakes`, 종료 1 | validation.json |
| 실제 HTTPX 풀 단위 | `python -X utf8 -m unittest discover -s full_stack_lab/tests -p dest_pin_transport_check.py -v` | 미실행: import 시 `No module named httpx`, 종료 1 | validation.json |
| 기존 키트 회귀 | `python -X utf8 -m unittest discover -s full_stack_lab/tests -p field_kit_check.py` | 미실행: import 시 `No module named tomllib`, 종료 1. 네트워크 시험 본문은 실행되지 않음 | 본 세션 명령 출력 |
| Rego | `opa test` | 미실행: 설치된 opa 없음; docker 미사용 | 환경 조회 |
| 위협 매핑 | `python -X utf8 research/llm-wiki/tools/map_threats.py` | 24개 정적 매핑 재생성, 코드 변경 해시 불일치 해소 | validation.json |
| 위키 목록·코드 스냅샷 | `build_wiki.py`, `capture_status.py` | 성공, 로컬 코드 상태만 기록 | validation.json 및 repository-snapshot.* |
| 위키 전체 검사 | `python -X utf8 research/llm-wiki/tools/check_wiki.py` | 실패: 기존 compliance provenance 29개 부재. 통과로 보고하지 않음 | validation.json |
| 실제 네이티브 검사기 | Gitleaks 라이브러리 | 미실행; 장애/규칙 응답 대역과 기존 Secret 패턴만 확인 | 단위 시험 범위 |
| 프로토콜·실제 모델/하네스 | 실제 SDK/MCP/PJ1 | 미실행 | 원격 접속 없음 |
| upstream 효과·배포·정책 해시 | 솔루션 기기 | 미확인/미배포 | 원격 접속 없음 |

통과한 14개는 DNS 전체/혼합/재바인딩·내부 승인·정확한 차단 ID·OIDC 새 transport·토큰/자격 문맥·검사기 장애·원장 해시 전 가림·응답·MCP 예외·키트 파일/인자 시험이다. AST로 선택한 실제 함수를 실행하며 DB/검사기/OS 권한 대역을 실제 MCP 실행 증거로 세지 않는다.

## 실패·미완료·한계

- 새 시험 작성 중 AST 위치 메타데이터, 필수 CLI 인자 및 OS 경로 검사 대역 누락으로 실패했고 수정 후 14개가 통과했다. 긴 오류를 자를 때 토큰 조각이 남는 경우를 확인해 500자 초과 전체 가림으로 고쳤다.
- HTTPX/HTTPX2의 `_pool._network_backend`는 비공개 접점이다. 기존 고정 판본의 실제 import/풀·TLS·SDK 확인이 필요하다. 외부 main 소스는 읽었으나 commit SHA 및 설치판과의 바이트 일치는 미확인이다. `git ls-remote --symref origin HEAD`도 github.com:443 연결 실패로 원격 HEAD를 확인하지 못했다.
- 첫 검증 IP만 사용한다. 해당 주소가 불통인 다중 주소 서비스의 가용성은 미확인이다. 내부 예외도 metadata/link-local·멀티캐스트·예약 주소는 차단한다.
- 위키 전체 검사는 `local-sources/compliance/*/provenance.json` 29개 부재로 실패한다. 해당 원본/카탈로그는 이 작업에서 변경하지 않았다. 초기 매핑 재생성은 신규 미커밋 파일에 대한 `git show HEAD:path`가 실패해 중단됐으며, 신규 파일 증거는 이번 analysis에 두고 기존 추적 파일의 매핑을 재생성했다.
- 초기 loopback issuer 전용 예외는 Keycloak 백채널을 막아 메인 검토 후 정정했다. 현재는 설정된 discovery의 단일 라벨 호스트/포트도 허용한다. 설정되지 않은 사설 host/port는 계속 차단하며 실제 Keycloak 기능 검증은 미실행이다.
- MCP 서버가 fetch/browser 도구의 인자 URL로 수행하는 outbound는 이 변경으로 고정되지 않는다. DEV-41에 남긴다.
- 오류 전체 가림은 진단의 상세를 줄이며 임의 형식 비밀의 완전 탐지를 보장하지 않는다. 기존 원장·사용자가 직접 만든 설정/인자의 비밀을 일괄 삭제하는 작업은 하지 않았다.

## 다음 작업

메인이 다음 순서로 검증한다. 기기/하네스 시험은 실제 OSS MCP와 격리 계정·합성 데이터로 수행하며 자체 MCP를 만들지 않는다.

1. 의존성이 있는 환경에서 pyflakes, `dest_pin_transport_check.py`, 기존 `mcp_result_contract_check.py`·`credential_binding_check.py`·풀 회수/종료 회귀 및 기존 field kit 검사를 실행한다. HTTPX/HTTPX2 실제 pool에서 숫자 IP·원래 Host·SNI·인증서 검증 설정·redirect 비추적을 확인한다.
2. 솔루션 기기에 배포하고 내부 MCP 10종·ACTIVE 실행기 탐색/등록/건강 확인 정상군을 확인한다. 공인 DNS와 TLS가 정상인 기존 원격 MCP도 정상 호출돼야 한다. 주소 분류 변경·credential 회전/철회 시 이전 풀을 재사용하지 않아야 한다.
3. 실제 DNS의 공인→127.0.0.1, metadata, mapped private, 혼합 A/AAAA, NXDOMAIN/timeout에서 `Block/MCP-EGRESS-001`, 접속·upstream 효과 0을 대조한다. TLS 정상 인증서 성공, 호스트 불일치/신뢰 불가 인증서 실패도 확인한다.
4. OIDC discovery/JWKS/토큰/갱신/introspection/revocation의 정상군과 metadata 내부 목적지·redirect 반례를 확인한다. metadata 요청과 AS 대상의 실제 접속 IP를 기록한다.
5. PJ1 fresh 관리형 하네스에서 가짜 GitHub/JWT/sk·Authorization/query가 포함된 공급자 오류와 네이티브 검사기 장애를 재현한다. MCP/HTTP 오류·`decisions.error`·해시 체인에 원문이 없어야 한다. 정상 오류 코드·정책 ID·실행 여부는 보존돼야 한다.
6. Linux/Windows 실제 키트 설정·하네스 프로세스 인자·회전/철회를 확인한다. DEV-41 서버 outbound와 DEV-42의 다른 셸 실행 표면은 별도 미완료로 유지한다.

## 사용자에게 필요한 입력

없음. 메인 통합 후 의존성이 갖춰진 로컬 검사 환경과 기존 솔루션/PJ1 검증 절차를 사용한다. 비밀값 입력·새 업무 권한은 요청하지 않는다.
