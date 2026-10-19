# 2026-10-20 DEV-69 서버 처리·저장 위치와 국외 이전 규칙 팩

- 작업자: Codex sol
- 코드 기준: `10/20-data-residency`, 시작 `09220f515bea70a498b921f4e23eafd605e8444b`, 시작 작업 트리 clean. 결과는 미커밋 변경이며 푸시·배포하지 않았다. 원격 HEAD 재조회는 GitHub:443 연결 실패다.
- 변경: `full_stack_lab/gateway/app/{residency,agent_contract,agent_service,core,main,pac,release}.py`, `agent_static/console.js`, `console.sh`, `registry/{catalog.toml,field/catalog.toml,data_residency.json,render_residency.py}`, `opa/{policy.rego,policy_test.rego,policy_ledger.json,residency.json}`, 새 `tests/data_residency_check.py`, D-138·POLICY·본 분석/보고·백로그 DEV-69 상태 칸.
- 시작 근거: [DEV-69 / CAP-4](../../analysis/compliance/dev-plan/README.md), [compliance 매트릭스](../../analysis/compliance/README.md), [시행일](../../analysis/compliance/key-dates.md), [POL 매핑](../../analysis/drive-curation/policy-id-mapping.json), LIB-L01·M06·M29.
- 해결할 문제와 완료 조건: 등급×국가를 허용/승인 필요/금지로 판정하고 내부 이상 등급의 위치 미확인 전송을 차단하며 사유를 기록한다. 코드는 구현했으나 OPA 실행·실제 MCP·PJ1을 포함한 현장 완료 조건은 미검증이다.

## 결과

등록·원격 검토에 처리/저장 국가, 처리 주체, 위치/이전 근거를 더했다. 원격 승인 해시와 등록 비교, 승인 이벤트에 포함되며 기존 등록을 같은 승인으로 다른 위치로 바꿀 수 없다. 내부 실행기는 ACTIVE 실행 조회로만 인정하고 조직 기기 설정을 쓴다. 호스트명·IP로 국가를 추정하지 않는다.

레지스트리 정본에서 OPA 팩을 생성하고 배포 전 일치 검사, 호출 시 정본/생성물 대조, OPA 로드 팩 해시 검사를 연결했다. `P-RESIDENCY-001`(48) 차단·`P-RESIDENCY-002`(83) 승인 필요를 관리대장/POLICY에 추가했다. 국가별 규정의 실제 판단은 잠정이며 기본값은 공개 허용·내부 KR 허용/국외 승인·중요 KR 허용/국외 금지다. 위치 미확인은 내부 이상 차단한다. 국외 이전 근거가 없는 허용 국가도 공개 외에는 승인이 필요하다. 기존 PAC-12·DLP·서버 간 전달 통제를 유지한다.

위치·팩 해시를 PAC baseline에 넣어 기존 건별 승인에 결속하고 기존 실행 직전 재검증에서도 다시 읽는다. 승인 화면은 판정 당시 위치를 표시한다. 서버 등록/상세/원격 검토에 입력·표시를 추가했고 정책 화면 구조는 바꾸지 않았다. 기존 JSON 필드만 써 DB 스키마 변경이나 새 라우트는 없다. 정본 및 경계는 [분석](../../analysis/dev69-data-residency/README.md)·[원자 요구사항](../../analysis/dev69-data-residency/requirements.json)에 기록했다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 순수 함수 | Windows Python 3.10.5, `python -X utf8 full_stack_lab/tests/data_residency_check.py`, 2026-10-20 KST | 8건 통과 | [로그](../../analysis/dev69-data-residency/local-checks.txt) |
| 팩 생성/정적 검사 | `python -X utf8 full_stack_lab/registry/render_residency.py --check`, 변경 Python 9파일 `py_compile`, `node --check …/console.js`, `bash -n full_stack_lab/console.sh` | 통과 | 같은 로그 |
| 기존 콘솔 상태 | `node --test full_stack_lab/tests/console-state.test.mjs`, Node 24.21.0 | 15건 통과 | 같은 로그 |
| 라우트 인증 | `python -X utf8 full_stack_lab/tests/open_endpoints.py` | 무인증 1·인증 73개 문서 대조 통과 | 같은 로그 |
| 기존 시험 보존·문서 | Rego 기존 파일 prefix 대조, 변경 문서 링크, `git diff --check` | 최종 로그 참조 | 같은 로그 |
| 게이트웨이 모듈 통합 | `python -X utf8 full_stack_lab/tests/data_residency_check.py --gateway` | 실패: `ModuleNotFoundError: No module named 'pglast'`; 통합 4건은 실행되지 않음 | 같은 로그 |

OPA 실행·프로토콜·실제 모델/하네스·upstream 독립 효과·배포/로드 정책 해시·화면 렌더링은 **미실행/미확인**이다. 로컬 OPA·Docker 실행 도구가 없어 Rego 16건을 실행했다고 세지 않는다.

## 실패·미완료·한계

국가·처리 주체는 공급자 문서와 사람 검토의 선언이다. 실제 저장·하위 처리자·숨은 송신·리디렉션 전체·클라우드 위치 실측이나 적법성 판단을 증명하지 않는다. 초기 KR 기기 설정은 배포자가 확인해야 한다. 외부 목적지는 별도 조직 선언이 없으면 내부 이상 등급에서 차단된다. 기존 provider 서버도 속성이 없으면 기본 차단되므로 생산 사양을 지어내어 채우지 않았다.

최종 재판정 이후 dispatch 사이의 파일 변경 경합·실제 DB 일회용 승인 동시 소비·장애 복구는 현장에서 검증해야 한다. 구 승인에 `residency`가 없거나 변경됐다면 재심사가 필요할 수 있다. 기존 기대값 변경은 없으며 기존 전체 실기기 회귀와 호환되는지는 확인하지 못했다.

## 기존 시험 변경 필요

현재 확인한 기존 시험의 기대값 변경은 없다. `policy_test.rego`는 기존 내용 뒤에 새 사례만 추가했다. 새 정책으로 속성 없는 기존 provider 호출이 차단되는 것은 의도된 변경이다. 현장 회귀에서 기존 허용 fixture와 충돌하면 기대값을 바꾸지 말고 사람의 적대 검토 후 위치 근거·설정을 먼저 검토해야 한다.

## 다음 작업

DEV-69: 솔루션 기기 `full_stack_lab`에서 아래 검사 후 `./console.sh field up`으로 배포하고 PJ1 실제 관리 하네스/승인 OSS MCP로 국내 정상·국외 승인·금지·누락·승인 만료/철회·위치/팩 변경·동시 실행·복구를 확인한다. `decision`·`policy_id`·미시도 및 독립 수신 효과를 대조한다. [명령과 검증 범위](../../analysis/dev69-data-residency/README.md).

```bash
python3 registry/render_residency.py --check
docker run --rm --entrypoint /opa -v "$PWD/opa:/policy:ro" openpolicyagent/opa:1.20.2-static test /policy
docker run --rm --entrypoint python -v "$PWD/tests:/checks/tests:ro" -v "$PWD/registry:/checks/registry:ro" -v "$PWD/opa:/checks/opa:ro" -e PYTHONPATH=/app "$(docker compose images -q gateway)" /checks/tests/data_residency_check.py --gateway
```

## 사용자에게 필요한 입력

코드 구현에 필요한 입력은 없음. 현장 검수에는 운영자의 기기 배치 위치 확인과 각 공급자의 처리/저장 위치·처리 주체·근거 문서, 기존 승인된 시험 MCP/격리 자원과 PJ1 하네스가 필요하다. 비밀 값은 수집·저장하지 않았다. `status/current.md`는 요청에 따라 변경하지 않았다.
