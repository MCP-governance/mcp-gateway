# 2026-11-02 팀 정책 시트 11-01판 PaC 반영

- 작업자: Claude Code
- 코드 기준: main `a4cc662c` → 브랜치 `11/02-pac-policy-update`
- 시작 근거: 사용자 지시 「드라이브의 최신 정책을 PaC로, 전체 재작성이 아니라 기존 정책과 대조해 수정」, D-261(10-27 PaC)
- 해결할 문제와 완료 조건: 시트 11-01판과 10-27판의 차이를 PaC·콘솔 정책 목록에 반영하고, Rego 시험·추적 검사·콘솔 시험이 통과한다.

## 원본

| 판 | 파일 | SHA-256 | 확보 |
| --- | --- | --- | --- |
| 10-27 | `MCP_보안_관리_정책_20261027-0639.xlsm` | `a912e9d1e1fb00ea…` | 10-27 |
| 11-01 | 드라이브 「D3-1. MCP 보안 관리 정책.xlsm」(수정 2026-11-01T04:45:04Z) → `MCP_보안_관리_정책_20261101-0445.xlsm` | `1604359f5f395401244f4323fffb89da14eb5effb21ea925a70968c6d33ac691` | 11-02, Drive 커넥터 내려받기 |

원본 xlsm은 이전 판처럼 저장소에 넣지 않았다. 「보안 정책」·「정책 실행 규칙」 두 탭의 추출본이 `policy/source/sheet.json`이다.

## 대조 결과

- 정책 수 90개는 같다. 번호가 단계별로 바뀌었다: 도입 검토 `POL-I-01`~`11`, 등록 및 연결 `POL-R-01`~`22`, 실행 `POL-E-01`~`29`, 관리 `POL-O-01`~`19`, 연결 해제 및 폐기 `POL-D-01`~`09`. 위험(`RSK-I-01` …)·보안 요구사항(`SR-I-01` …) 번호도 같은 방식이다.
- 행 순서가 같아 옛 번호를 순서대로 대응했다. 정책 본문이 같은 것이 83건이다. 대응표는 `policy/source/renumbering.json`.
- 모든 행에서 바뀐 것: 「통제 대상」 열이 분류명(MCP Host 및 MCP Client 33·MCP Server 19·Tool / Resource 18·Agent 8·관리자 7·사용자 5)으로 바뀌었다. 위험도가 Critical·High·Medium·Low로 다시 매겨졌다(우선순위 P1→P2 9건, P2→P3 10건). 단계 이름 「실행 및 통제」→「실행」, 「운영 및 변경」→「관리」.
- 문장·실행 규칙이 바뀐 9건:

| 새 번호(옛) | 바뀐 내용 | PaC 반영 |
| --- | --- | --- |
| POL-R-07(018) | OAuth 인증 서버 발급자 → MCP 연결 응답의 발신 대상 일반 | 솔루션 기능 유지, 사유 수정 |
| POL-R-08(019) | 「별도 인증 서버를 사용하는 경우」로 문구 한정 | 규칙 그대로(`oauth` 단계가 곧 별도 인증 서버 사용) |
| POL-R-09(020) | 인증 결과 반환 주소 → 인증 결과 수신처 | 솔루션 기능 유지, 사유 수정 |
| POL-R-10(021) | 로그인 확인값 → 현재 사용자·세션 요청과의 일치·재사용 거부 | 솔루션 기능 유지, 사유 수정 |
| POL-R-15(026) | OAuth scope → 사용자·Agent에게 주는 Tool·자료 접근권한(scope 포함) | `connect` 단계 `requested_access` ⊆ 등록부 `approved_access` 추가, 시험 4건 |
| POL-O-07(069) | 참조 번호만(POL-070 → POL-O-08) | 없음 |
| POL-O-08(070) | 문장 부호만 | 없음 |
| POL-O-15(077) | OAuth 범위 → 인증정보 사용 범위 | 입력 `oauth_scopes` → `credential_scopes` |
| POL-D-09(090) | 실행 규칙이 비어 있던 행이 채워짐 | 제외 → PaC. `connect`에 `restore` 단계, 시험 10건 |

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | `opa check --strict`, `opa test policy/pac`(OPA 1.20.2, WSL) | 519/519 통과 | 터미널 |
| 정적 검사 | `build_catalog.py build --check`, `trace.py --check`, `build_console_catalog.py --check` | 통과(판정 정책 66개) | 터미널 |
| 정적 검사 | `organization_policy_catalog_check`·`policy_ledger_evidence_check`·`audit_call_filter_check`, Node `tests/*.test.mjs` 15개 파일 | 통과 | 터미널 |
| 정적 검사 | `check_trace.py --self-test`·`check_trace.py`, `deploy/check.py` | 오류 0·통과 | 터미널 |
| 배포·화면 | 기기 콘솔 「전체 보안 정책」 | 미실행 | — |

## 실패·미완료·한계

- 게이트웨이는 아직 이 패키지로 질의하지 않는다. 새 규칙(R-15·D-09)의 입력을 만드는 기능도 없다.
- 새 규칙의 독립 반례 시험(`zz_adversarial_test.rego`)은 쓰지 않았다.
- 시트의 위험도 값이 영문(Critical 등)이다. PaC 카탈로그와 콘솔 목록에는 위험도를 싣지 않아 화면 영향은 없다.

## 다음 작업

- 기기 배포 후 콘솔 「전체 보안 정책」 목록이 새 번호·시트 순서로 보이는지 확인.
- 시트 담당자에게 확인: 「통제 대상」이 분류명으로 바뀌어 정책 제목으로 쓸 열이 없어졌다.

## 사용자에게 필요한 입력

없음
