# 실제 Claude Sonnet 5.5 독립 검토

모델 응답 claude-sonnet-5-5 확인, effort xhigh 요청. 실제 CLI session eab34c08-d2cb-4a80-9d99-1f23ed48878e. 서버 effort 적용은 독립 확인하지 않음. 아래는 수신한 공개 최종 답변이며 이후 수정/검사는 기업 작업 보고에 별도 기록. 자동 원문 비밀 제거가 적용된 projection이다.

검토 결과입니다. Read/Grep/Glob만 썼고 파일은 수정하지 않았습니다. 테스트와 git diff도 실행하지 않았습니다. 그래서 변경 행을 따로 가리지 못했고 현재 파일 상태를 기준으로 봤습니다.

**읽은 범위**
- core.py 1077–1230, 1394–1694
- privacy.py, secret_scan.py, mcp_facade.py 126–170
- tests/mcp_result_contract_check.py
- preflight.py, check_preflight.py, 예제 JSON
- main.py 435–440, decommission.py 412–435
- 위키 analysis/README.md, integrations/litellm.md

고정된 `mcp==2.2.0`(requirements.txt:3)의 소스는 로컬에 없습니다. 위키 JSON의 수치도 대조하지 않았습니다.

**정상 경로 결론**
- `base_event["result"]`는 core.py:1606의 `_inspected_result` 출력으로만 채워집니다.
- `_render`(mcp_facade.py:142-143)는 Allow/Alert/Restrict이고 disposition이 returned/masked일 때만 content와 structured를 내보냅니다. 둘 다 마스킹된 같은 payload에서 나옵니다.
- 보류는 `result=None`(core.py:1639)입니다. Gitleaks 실패도 InspectionUnavailable로 보류됩니다(secret_scan.py:43).
- 이 경로에서 우회는 확인하지 못했습니다.

## 1) 확인된 문제

**P1. 오류 문구가 출력 통제를 우회합니다.** 코드 경로는 확인했고, 도달은 조건부이며 실제 유출은 확인하지 못했습니다.
- 경로: `client.call_tool`(core.py:1153)이 예외를 내면 `except Exception`(1643-1651)이 `error=_root_cause(exc)`(1162-1165, 400자)를 저장합니다. 이 문자열이 mcp_facade.py:168의 `오류: …`로 클라이언트에 나가고, core.py:1250으로 감사 기록에도 남습니다. `_guarded_result`, 마스킹, Gitleaks를 모두 거치지 않습니다.
- 조건: 업스트림 McpError 메시지이거나 outputSchema 불일치입니다. 설치된 SDK 1.x 사본(`mcp/client/session.py:443`)은 `Invalid structured content … {e}`로 위반 값을 인용합니다. 고정된 2.2.0에서도 같은지는 미확인입니다.
- 최소 수정: 클라이언트와 감사에는 예외 타입과 고정 문구만 남깁니다. 상세는 `mask_text`와 `secret_scan`을 통과한 것만 허용합니다.

**P2. 디코드 검사가 `content`에만 적용됩니다.**
- core.py:1210은 `json.dumps(result)`에 `content` 텍스트만 디코드해 붙입니다. structured 문자열은 이스케이프된 형태로만 Gitleaks에 들어갑니다.
- `_guarded_result`(1190-1199)는 전체를 순회하고 주석(1189)이 같은 이유를 적었는데도 그렇습니다. 시험(tests:81-90)도 `content`만 봅니다.
- 수정: 순회 코드를 `_text_leaves()`로 빼서 키와 값을 모두 scan에 넣고, 다중행 structured 시험을 추가합니다.

**P2. 예외 뒤에 잔여 상태를 정리하지 않습니다.**
- core.py:1606-1619 이후 예외가 나면 1643 분기가 `result`, `result_evidence`, `upstream_executed`를 그대로 둡니다.
- `_render`는 Block이면 반환하지 않지만, main.py:436-438의 승인 REST는 outcome 전체(`result`, `policy_input` 포함)를 응답합니다. 해당 지점에서 실제로 예외가 나는지는 확인하지 못했으니 방어 수정 사안입니다.
- 수정: 그 분기에서 `result=None`과 withheld를 명시합니다. 승인 응답은 `result`와 `policy_input`을 뺀 투영으로 바꿉니다. 승인자에게 결과를 보일지는 설계 결정입니다.

**P3. 미탐 한계와 가용성입니다. 버그로 확정한 것은 아니고, 실데이터 시험도 하지 않았습니다.**
- Gitleaks 일반 규칙은 길이·엔트로피 조건이 있어 `{"password":[REDACTED]}` 같은 값은 미탐일 수 있습니다. 고정 판본의 규칙은 확인이 필요합니다.
- privacy.py:58의 허용목록에 이름·주소·계좌가 없습니다.
- 선행 0이 사라진 숫자 전화(`1012345678`)는 :48 정규식에 맞지 않습니다.
- 리프별 순차 호출(privacy.py:140-150)과 세마포어 2(:32)에 더해, `_inspected_result`에는 timeout이 없습니다(core.py:1601은 업스트림만 감쌉니다). 큰 structured는 오래 걸립니다.
- core.py:1609는 PII 발견을 "출력 검사 실패"로 기록합니다.

**preflight.py에서는 우회 경로를 찾지 못했습니다.**
- mode가 `parallel_harness`가 아니면 거부합니다(:29). 키와 토큰이 같아도 거부합니다(:97). 리다이렉트를 따르지 않고 `trust_env=False`입니다.
- 보완할 점 세 가지입니다.
  1. `REVIEWED_VERSIONS`(:18)에 1.105.0이 있는데 litellm.md:11은 "검증하지 않음"이라고 적습니다. 이름이나 값을 정정해야 합니다.
  2. 자격 전송 대상 호스트가 고정되지 않았습니다(:33-38, `.invalid`만 제외). `mcp_url`을 Gateway 공개 origin에 고정하는 편이 안전합니다.
  3. 직원 JWT와 통합 신원의 구분은 코드가 아니라 절차입니다(litellm.md:23). `--run`은 운영자가 발급한 전용 신원에만 써야 합니다.

## 2) 추가검증 조건
- 실제 Presidio·Gitleaks로 코퍼스(structured 다중행, 민감 키 아래 값, 숫자 PII)를 돌려야 합니다. 현재 시험은 `analyze`와 `labels`를 mock하므로(tests:67, 75, 84) 탐지 자체는 증명하지 못합니다.
- 상용/OSS MCP에서 outputSchema 일치·불일치·누락 시 wire, 감사, 로그에 값이 남지 않는지 확인해야 합니다.
- 승인 REST 응답 내용을 확인해야 합니다.
- PJ1 관리형 하네스에서 모델 선택→MCP→원장→독립 효과까지 연결해야 합니다.

## 3) 배포 가능 범위와 미완료
- P1·P2를 고친 뒤 솔루션 기기(`field up`)에 배포하고 PJ1에서 시험할 수 있습니다.
- 증거 수준은 결과 통제가 `verified_unit`(mock 단위)까지이고, preflight는 `source_only`와 설정 검사까지입니다. LiteLLM 34조건은 `not_run`을 유지하며 실기기 증거는 0입니다(analysis/README.md:17, litellm.md:33).
- litellm.md:19의 "잔존 payload 미반환"은 MCP façade 한정입니다. 승인 REST 경로를 포함하지 않으니 범위를 한정해서 써야 합니다.
- 미완료: 기업 LiteLLM(미제공), outputSchema 승인·잠금, rich content, PJ1 관리형 E2E, 실제 OSS MCP의 structuredContent 실행.
- AST 목록은 전체 함수 의미 감사가 아니고, 이 검토도 그 대체가 아닙니다.

계획 모드라서 계획 파일에 정리하려 했지만 Write 도구가 이 환경에서 꺼져 있었습니다. 그래서 결과를 이 답변에만 담았습니다.
