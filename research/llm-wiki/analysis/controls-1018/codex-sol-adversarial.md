# 잔여 통제 적대적 검토 — Codex sol

검토일: 2026-10-18. 브랜치 `10/18-remaining-features`, 기준 `d6679fd`, 최종 검토 HEAD `b9474f6aa63ed16e657c4df0268a57a82a9e6119`. 검토 시작 HEAD는 `fe45bce33058b08b69804cd641dcee28c198e4ec`이며 후속 커밋의 수정도 대조했다.

대상은 `git diff d6679fd..HEAD`의 `full_stack_lab/gateway`, `full_stack_lab/opa`, `full_stack_lab/tests/remaining_controls_check.py`, `full_stack_lab/eval`이다. D-131~D-134와 호출부·실행 직전 검사·원장·기존 실행기 출구 통제를 함께 읽었다. 연결된 기존 코드의 문제는 새 통제에 미치는 영향으로 한정했다. 검토 중 다른 작업의 미커밋 변경과 HEAD 이동이 나타났으므로 최종 범위를 위 커밋으로 고정했다. 그 이후 작업 트리의 classify.py·core.py·review.py·시험·아키텍처 변경은 수정하거나 검증 완료로 취급하지 않았다. 코드는 수정하지 않았고, 이 보고서만 추가한다. 요청에 따라 현황·백로그·별도 작업 보고서와 Git 브랜치·커밋은 변경하지 않는다.

아래의 **코드 확인**은 현재 소스로 성립하는 조건·결과를 뜻한다. **조건부 논증**은 필요한 운영 조건을 명시한 반례이며 실제 외부 효과를 관측했다는 뜻이 아니다. 높음은 정보 반출 또는 명시적 거부 이후 실행 가능성, 중간은 통제·증적·검증 결과의 신뢰성 손상, 낮음은 제한적인 설정 결함이다.

| 번호 | 심각도 높음/중간/낮음 | 문제 | 근거 파일:행 | 재현·논증 | 수정안 |
| --- | --- | --- | --- | --- | --- |
| 1 | 높음 | 등록 서버의 목적지가 비어 새 PAC-12 결속을 건너뛴다 | `full_stack_lab/gateway/app/classify.py:800-804` → `full_stack_lab/gateway/app/pac.py:243-246,265` → `full_stack_lab/opa/pac15.rego:268` | **코드 확인·함수 분리 실행.** 등록 서버 `convert`, `data_class=public`, `arguments={"uri":"https://learn.microsoft.com/a"}`는 `destinations=[]`가 된다. `transfer_binding(...,[])=(True,[])`, 요청은 `transfer.enabled=false`이므로 PAC-12가 무조건 충족된다. 심사 등급이 public인데 등록 등급이 nonimportant인 호출도 이 결속에서는 걸리지 않는다. 기존 주소 스키마·실행기 출구가 일부 목적지를 제한하지만 목적·등급 결속을 대신하지 못한다. | 도구 계약에서 심사한 목적지 인자 경로를 분류기에 연결한다. 주소형 입력의 해석 실패는 전송 없음으로 처리하지 않는다. 외부 MCP 수신처와 MCP가 접근하는 하위 목적지를 별도 사실로 만든다. a 절의 부작용도 함께 해결한다. |
| 2 | 높음 | `runtime` 메타데이터만으로 최종 목적지가 검증됐다고 선언한다 | `full_stack_lab/gateway/app/pac.py:163-180`; 연결 근거 `full_stack_lab/runtime/worker.py:110-113,283-294,364-370`; `full_stack_lab/opa/pac15.rego:269-278` | **코드 확인·조건부 논증.** 실행기 출구는 한 도구의 한 목적지가 아니라 같은 도입 신청의 모든 도구 목적지 합집합이다. 도구 A는 host-a, 도구 B는 host-b를 심사받았고 A의 URL이 host-a→host-b로 redirect되면 출구 필터는 둘 다 허용한다. 반면 `transfer_binding`은 최초 host-a와 `bool(runtime)`만 보고 최종 host-a를 검증했다고 한다. 같은 도구에 목적지 둘을 심사한 경우도 실제 입력 목록만 하나면 true다. redirect와 출구 필터 갱신의 실제 효과는 미실행이다. 1번을 고쳐 PAC-12를 활성화해도 남는 문제다. | 실행기 존재와 호출별 최종 목적지 증명을 구별한다. 검증된 최종 host·포트·출구 정책 세대가 없으면 false를 유지한다. 도구별 출구 분리 또는 redirect 각 단계에 대한 목적지 결속을 검증해야 한다. |
| 3 | 높음 | 같은 개인정보 유형 중 하나만 가려도 그 유형의 잔여 원문 전체를 제거된 것으로 간주한다 | `full_stack_lab/gateway/app/core.py:991-1005,1849-1853,1860-1861,1891-1893`; `full_stack_lab/gateway/app/privacy.py:72-75,173-209`; `full_stack_lab/opa/policy.rego:474-485` | **최종 HEAD 코드 확인·대역을 사용한 함수 검증.** 합성 입력 `{"label":"passport_number","value":"M123A4567","note":"passport_number M456B7890"}`를 합치면 여권 두 개가 탐지된다. 문자열별 마스킹에서는 note의 여권만 가려지고 value는 문맥이 없어 원문으로 남는다. 그런데 `sent_types = privacy_types - masked_types`가 유형 KR_PASSPORT 전체를 제거해 정책에는 잔여 개인정보가 없는 것으로 보인다. provider_hosted 읽기는 x 전용 원문 DLP 차단에도 걸리지 않으므로 이 차이가 중요하다. 이전 무조건 findings 초기화는 수정됐지만 유형 단위 차감은 충분하지 않다. 실제 Presidio·MCP 반출은 미확인이다. | 마스킹 후 실제 outbound 전체를 원래와 같은 문맥으로 재검사한다. 일부 유형의 마스킹 성공을 같은 유형의 모든 탐지값 제거 증명으로 쓰지 않는다. 문자열별 변환을 쓸 경우 탐지 위치와 JSON 경로를 연결하고 필드 간 문맥도 보존한다. |
| 4 | 높음 | provider_hosted 읽기는 중요정보 열람 후 외부 전송 경계에서 빠진다 | `full_stack_lab/gateway/app/core.py:1024-1031,1041-1047,1838-1841,1863-1864`; `full_stack_lab/opa/policy.rego:483-510` | **코드 확인·조건부 논증.** 같은 주체가 filesystem 중요자료를 읽은 뒤 GitHub 검색 등 외부 MCP의 `r` 인자에 비정형 기밀 문장을 넣는다. `_flow_sources`는 읽기라 `[]`, `_sequence_flags`는 등록 서버 목적지가 비어 `[]`다. provider_hosted 전용 규칙은 탐지된 PII만 보므로 PII 패턴 없는 기밀 내용은 이 세 통제에 걸리지 않는다. 기존 PAC 권한·계약 등 다른 조건을 충족한 경우의 우회다. 데이터 등급을 외부 MCP의 반환 데이터 등급과 혼동하면 안 된다. | b처럼 provider_hosted 읽기에도 흐름 출처를 생성한다. 기존 외부 전송 금지와의 관계를 명시하여 `accepts_from` 승인이 외부 중요정보 반출 허가로 확대되지 않게 한다. |
| 5 | 높음 | 동의 확인 후 철회·만료되어도 실행 직전에는 재검사하지 않는다 | `full_stack_lab/gateway/app/core.py:1933-1937,1971-1973,1339-1368`; `full_stack_lab/gateway/app/consent.py:33-40,65-70`; 연결 근거 `full_stack_lab/gateway/app/dispatch.py:47-57,69-104` | **코드 확인·경쟁 순서 논증.** T1 `consent.missing`이 GRANTED를 읽는다 → tools/list 또는 잠금에서 대기 → T2 본인 revoke가 커밋된다(또는 유효기간이 지난다) → T1 최종 OPA 검사와 dispatch intent가 통과한다. 최종 입력에는 동의 사실이 없고 dispatch SQL도 동의를 보지 않는다. 동의 철회 완료 뒤 신규 intent가 생길 수 있다. PostgreSQL barrier 재현은 미실행이다. | 사용한 동의 ID·terms_hash·등급·만료를 실행 의도와 결속하고, 철회와 같은 행 잠금/원자 조건으로 전송 허용 시점을 정한다. 단순히 검사 한 번을 추가하는 것만으로 검사와 전송 사이 경쟁을 해결했다고 하지 않는다. |
| 6 | 중간 | P-FLOW 입력이 최초 조회 결과에 고정되어 대기 중 새 중요정보 열람을 놓친다 | `full_stack_lab/gateway/app/core.py:1863-1865,1893-1894,1339-1355`; `full_stack_lab/gateway/app/dispatch.py:75-88` | **코드 확인·경쟁 순서 논증.** T1 쓰기의 최초 `_flow_sources=[]` → 연결/목록/잠금 대기 → 같은 주체의 다른 세션에서 T2 중요 읽기 완료·원장 커밋 → T1 dispatch. 최종 OPA는 기존 `policy_input`의 flow_sources를 재사용한다. 송신 인자가 사전에 준비된 경우에도 D-133의 실행 시점 경계는 우회된다. 이 논증은 T1이 시작할 때 없던 비밀 값을 나중에 인자에 삽입할 수 있다는 주장이 아니다. | 최종 실행 경계에서 최신 출처와 받는 도구의 최신 심사를 대조한다. 중요 읽기의 완료/표지 기록과 쓰기 intent 사이 순서를 주체 기준으로 정의하고 경합 시험으로 검증한다. |
| 7 | 중간 | 사용자는 해시가 결속한 조건을 볼 수 없어 변경 동의를 구분할 수 없다 | `full_stack_lab/gateway/app/consent.py:22-23,44-50,54-59`; `full_stack_lab/gateway/app/review.py:246-248`; `full_stack_lab/gateway/app/agent_static/console.js:1466-1482` | **코드 확인.** 동의에는 목적지만 바뀌어도 새 terms_hash가 생기지만, 저장·조회·화면은 도구·등급·목적·시각 위주다. 같은 목적을 유지하고 외부 목적지를 바꾼 두 요청은 사용자가 구별할 수 없다. `mine`에는 terms_hash와 목적지·허용 입력·마스킹·자산 등 조건 스냅샷도 없다. 오래된 PENDING에 grant해도 현재 해시를 우회하지는 않지만, 새 조건에 대한 충분한 확인 화면이라는 주장은 성립하지 않는다. | 요청 시점의 심사 조건 스냅샷을 동의와 함께 보존하고 라벨·값으로 보여 준다. 현재 조건과 다른 과거 요청은 구분하고 해당 조건에 대해서만 결정하게 한다. |

## 검토 중 반영된 수정과 원장 범위

시작 HEAD의 다음 문제는 후속 커밋에서 수정되어 위의 현재 결함 표에서 제외했다. 실제 DB·OPA 서비스 시험 통과를 의미하지 않는다.

- `35234aa`: 동의 UPDATE와 approval_events INSERT를 한 트랜잭션으로 묶고 허용된 outcome 값으로 바꿨다. 최종 `consent.py:63-79`에서 같은 connection을 전달함을 확인했다. 따라서 상태만 커밋되고 감사가 실패하는 이전 경로는 현재 결함으로 세지 않는다. 실행 직전 철회 경합(5번)은 별개로 남는다.
- `43a734d`: 마스킹 유형을 원장에 저장되는 `policy_input.request.masked_types`로 옮겼다(`core.py:1891-1893,1584`). 이전의 classification.masked_inputs 증적 누락은 해소됐다. 입력 마스킹은 외부 송신 처리이며 **감사 원문 제거 기능은 아니다**. 원문은 decisions.request_payload, decisions.policy_input.pac.request.arguments·parameter_bindings, approvals.request_payload에 남는다(`core.py:1567,1584,1943-1949`, `pac.py:198-220,257-264`). request_payload는 300자 초과 문자열의 앞 120자도 남기고 깊이 4 이후에는 축약하지 않으며, policy_input에는 그 축약도 없다(`core.py:1535-1549`). D-131에 원문 보관 선택이 명시돼 있으므로 유지 자체를 새 결함으로 세지 않는다. 접근·보존 기한과 실제 송신 digest는 별도 검증 대상이다.
- `b9474f6`: 두 eval 시나리오를 PAC 사실이 있는 자료로 교체하고 pac15_replay 입력을 지원했다. 최종 JSON에는 baseline 10건·controls 4건 모두 pac가 있다. 다만 load_cases의 expect.decision은 형식 검사이고 사례별 불일치 검증/실패 기능은 아니다(`before_after.py:154-161,245-266,356-375`). before none도 실제 MCP 호출 없는 전부 Allow 계산 기준선이다. 이 지표를 실제 방어/업무 성공으로 확대하지 않는다.
- 마스킹의 무조건 findings 초기화도 후속 변경에서 제거됐지만, 3번의 같은 유형 내 부분 마스킹 반례는 남았다.

## a·b 판단

### a. 등록 서버의 목적지 추출

**진단에는 찬성한다.** 분리 실행에서 분류 목적지 `[]`와 결속 결과 `(True, [])`를 확인했다(1번). 새 함수에 수동으로 `['learn.microsoft.com']`을 주는 단위 시험은 이 단절을 검사하지 못한다. 기존 스키마가 주소를 묶는다는 사실과 PAC-12가 실행된다는 주장은 별개다.

**주소 이름 또는 http(s) URL 값으로 추출하는 방안은 보조 수단으로 조건부 찬성한다.** 다음 부작용을 처리하지 않은 일괄 적용에는 반대한다.

| 쟁점 | 현재 코드와 예상 부작용 | 적용 조건 |
| --- | --- | --- |
| 주소와 본문 구별 | `_ADDRESS_ARG`는 계약의 주소형 인자 제한을 위한 휴리스틱이다. 아무 문자열에서 URL 값을 모으면 issue 본문의 출처 링크·검색 질의·문서 내용도 실제 접속 목적지가 된다. 서로 다른 링크가 둘이면 `len(destinations)!=1`로 차단될 수 있다. 반대로 `target`, `host`, 웹훅 식별자·서버 내부 설정·인코딩된 URL은 놓친다. | 심사한 인자 JSON 경로/형식을 정본으로 하고 휴리스틱은 미심사 후보 탐지로 쓴다. 중첩 객체·배열·주소형 필드의 잘못된 값을 포함한다. |
| 행위 승격 | URL이 외부라는 이유로 등록 도구 `r`를 무조건 `x`로 바꾸면 `pac.scope`의 `action == spec.tools[tool]`가 깨진다(`pac.py:77`). 변환·검색 같은 기존 정상 읽기를 일괄 거부할 수 있다. | 전송 사실과 r/w/x를 구별한다. 실제 기능의 위험 승격이 필요한 경우 심사·승인 범위도 함께 일치시킨다. |
| 공급자 MCP 수신처 | 검색어에 URL이 없어도 외부 MCP의 endpoint로 모든 인자가 나간다. 하위 URL 추출만으로 provider 경계를 해결하지 못한다. 단순히 endpoint도 같은 목록에 더하면 항상 2개 목적지가 되는 정상 호출이 생긴다. | MCP 수신처와 도구의 최종 접속처를 서로 다른 필드로 취급한다. |
| 포트·대소문자 | `url_destination`은 호스트 소문자화·끝점 제거를 하지만 포트를 버린다(`classify.py:307-317`). 심사 `example.com:443`와 실제 host `example.com`는 결속이 불일치하고, 심사 `example.com`는 함수 수준에서 `:8443`도 같은 host다. 다만 현재 파생 스키마는 대체로 HTTPS/443만 허용하므로 모든 도구에서 즉시 비표준 포트 우회가 된다고 주장하지 않는다. 파생 URL 정규식은 소문자 심사와 달리 대소문자를 구별한다. | 스킴·정규화 host·포트의 일관된 목적지 ID를 쓰고 기존 스키마·출구 정책과 대조한다. 파서의 호스트와 userinfo를 혼동하지 않는다. |
| IDN·와일드카드 | 심사 정규식은 Unicode IDN을 받지 않고 punycode만 표현할 수 있다. URL 분류에는 IDNA 변환이 없어 동등 이름이 불일치한다. helper의 `*.example.com` suffix 비교는 apex와 `example.com.evil.net`를 포함하지 않지만, `review.derived_constraints`는 `*`를 문자 그대로 escape하고 실행기 `egress_filter`는 유효 HOST만 받는다. helper 단독 wildcard 성공을 실제 전송 성공으로 해석하면 안 된다. | IDNA/끝점/포트 정규화와 wildcard 범위를 한곳에서 정의하고, 스키마·PAC·출구에 같은 의미로 반영한다. 지원하지 않는 표현은 심사 시 거부한다. |
| 반복 목적지·최종 목적지 | 같은 host URL 두 개를 배열에서 발견해 그대로 넣으면 서로 다른 목적지 둘처럼 차단된다. 하나로 중복 제거해도 redirect·다운로드 부가 요청·도구별 출구 합집합 문제는 남는다(2번). | 정규화한 목적지 ID로 중복 제거한다. 추출한 최초 목적지를 최종 목적지 검증으로 승격하지 않는다. |

호스트 suffix 검사 자체에 대해 `evil-example.com`, `example.com.evil.net`를 허용하는 결함은 확인하지 못했다. 포트·IDN 사례는 현재 검사의 불일치/부족을 뜻하며 실제 하위 서버 접속 우회는 별도 시험 대상이다.

### b. provider_hosted 읽기에도 흐름 출처 적용

**방향에 찬성한다.** `r`는 반환 기능의 성격이지 인자가 외부로 나가지 않는다는 뜻이 아니다. 기존 core도 provider_hosted 읽기의 비밀·PII 검사는 수행한다. 같은 전송 경계에 흐름 출처도 적용해야 한다(4번). 다만 다음 조건이 필요하다.

- provider_hosted 판정을 조회 조건에 정확히 전달한다. 단순히 모든 `r`에 적용하면 내부 서버의 독립적인 읽기까지 막는다. 실제 호출 인자에 기밀이 있는지를 추적하는 방식이 아니므로, 같은 주체가 다른 작업에서 중요자료를 읽었을 뿐인 외부 문서 조회도 10분 동안 차단된다. D-133이 명시한 거친 표지의 오탐이 외부 읽기로 확대되는 **알려진 설계 비용**이다.
- 같은 주체의 여러 하네스·세션·엔드포인트를 합치는 현재 범위는 세션을 새로 열어 표지를 지우는 공격을 줄인다. 반대로 공유 계정에서는 사람 간 간섭이 생긴다. 세션별로 좁히면 우회가 쉬워지므로 무조건 세션 범위로 바꾸지 않는다.
- `accepts_from`를 채웠다는 이유로 외부 중요정보 전송이 허용되지 않게 한다. 현재 목적지 없는 provider 읽기는 P-CHAIN 입력도 비어 있다. b만 고치면 `accepts_from`에 승인한 출처의 중요자료를 provider 읽기로 보내는 경로가 남는다. D-132의 외부 중요정보 금지와 D-133의 서버 간 수신 승인을 구분해야 한다.
- 동일 서버 제외(`server_id<>%s`)는 b에서도 남는다. 공급자가 이미 가진 자료를 같은 공급자에게 질의하는 것까지 새 서버 간 전달로 볼지는 별도 범위 결정이다. 다중 별칭 ID는 반대로 오탐을 만들 수 있다.
- 표지는 원장상 `important/r/upstream_executed`와 10분 창에만 있다. 10분 경과 후 보관한 정보를 재전송하거나, 쓰기·실행 응답에서 얻은 중요정보는 이 모델이 막지 못한다. 전자는 명시된 창의 한계, 후자는 현재 출처 정의의 한계다. b로 완전한 정보흐름 추적이 된다고 주장하면 안 된다.
- 실행 직전 새 표지를 반영하는 6번도 함께 검증한다. 처음 조회할 때만 b를 적용해도 경합은 해결되지 않는다.

## 시험 공백

### 이번에 실행한 검증과 한계

- `python -B -X utf8 full_stack_lab/eval/before_after.py --self-test`: 통과. 지표 산술과 레거시 사례 변환만 확인한다.
- `python -B -X utf8 full_stack_lab/tests/remaining_controls_check.py`: `ModuleNotFoundError: No module named 'pglast'`로 import 중 실패. 시험 0건 실행이며 통과로 세지 않는다. 로컬에는 jsonschema/httpx도 없다. 의존성 설치·로컬 스택 기동은 하지 않았다.
- 실제 제품 함수 본문을 AST로 메모리에 분리하여 등록 서버 분류→transfer_binding 결과를 확인했다. registry·분류 주변 의존성은 대역이다. 이는 실제 MCP 실행 시험이 아니다.
- 최종 HEAD에서 여권 인식기 정규식 원문을 V8 RegExp로 평가하여 합친 문자열의 두 여권 양성, value 단독 음성, note 단독 양성을 확인했다. 같은 HEAD의 `privacy.mask_payload` 본문에는 문맥 의존 analyzer/mask_text 대역을 사용했다. 결과는 value 원문 유지·note만 [REDACTED], masked_types=[KR_PASSPORT], core의 유형 차감 후 sent_types=[]였다. **Presidio의 실제 정규식 엔진·서비스 결과는 미검증**이며 3번의 실제 반출 효과는 추측/검증 대상이다.
- 평가 자료는 시작 HEAD에서 baseline 10/10·controls 4/4에 pac가 없었으나 최종 HEAD에서는 각각 0건으로 수정됐다. Git 객체의 JSON을 직접 집계했다. 최종 자료의 OPA 판정은 실행하지 않았다. 로컬 Docker CLI가 없어 Rego 3건도 미실행이다.
- 동의 함수에 `important=GRANTED`, `nonimportant=DENIED` 대역 행을 함께 주면 `missing(...,nonimportant)`는 None을 반환한다. 현재 등록 서버는 보통 고정 등급이므로 이런 복수 등급 상태가 실운영에서 생성되는 경로까지 입증하지 않았다. **잠재 경계 사례**이며 확인된 권한 상승으로 표에 올리지 않았다.
- 원격 HEAD 조회는 GitHub 연결 실패로 확인하지 못했다. 검토 범위는 로컬 고정 HEAD다. 솔루션 기기/PJ1, PostgreSQL 경합, 실제 Presidio·OSS MCP·독립 외부 효과는 시험하지 않았다.

### 새 시험이 실제로 잡는 범위

`remaining_controls_check.py`는 13개 시험으로, 정규화 기본값/형식·심사 조건 해시 3개, 입력 스키마 축소 2개, transfer helper 3개, flow 조회 1개, 동의 조회 분기 4개다. 도구 실행 전체를 호출하는 시험은 없다. 입력 `mask=True`의 실제 마스킹 호출·결과 검사도 없다.

| 대상 | 현재 잡는 결함 | 통과해도 보장하지 않는 내용 |
| --- | --- | --- |
| `ReviewTermsTest` / `InputFieldsTest` (`remaining_controls_check.py:28-66`) | 잘못된 이름·등급, 파생 스키마의 추가 입력 허용, 필수 입력 제거, 원본 스키마 변경 | execute_call의 검사 순서·정확한 `P-INPUT-FIELD-001`, 직접 작성 스키마 경로, 빈 배열 입력, 마스킹 후 스키마·목적지·자산 일치. 원본 계약 스키마 검사가 먼저므로 계약 밖 항목은 FIELD가 아닌 SCHEMA가 나오는 것이 현재 순서다. 둘 다 실행 전 차단이며 그 자체는 우회가 아니다. |
| `TransferBindingTest` (`:69-95`) | 전달해 준 host의 심사 포함 여부, helper 수준의 runtime 유무·등급별 pair 생성 | 실제 classify→pac.build 연결(1번), 실행기 상태/출구 검증(2번), 포트·IDN·다중/반복 host. 음성 검사는 `assertFalse(ok and pairs)`라 ok와 pairs 각각의 정확한 결과를 검증하지 않는다. |
| `FlowSourcesTest` (`:98-109`) | 현재 의도대로 모든 읽기를 제외하고 쓰기에서 DB 결과를 돌려주는지 | b의 결함을 정상 동작으로 고정한다. DB 대역은 SQL WHERE를 실행하지 않는다. 정확한 창·주체·등급·실행 여부·다른 서버 조건, 실제 반환의 오염 표지, 최종 dispatch 경합은 검증하지 않는다. |
| `ConsentTest` (`:112-133`) | 상위 등급 grant, 부족한 grant, 동일 등급 deny, 미지 등급의 important 처리 | `decide`와 `mine`, 사용자 범위 API, 실제 SQL 만료·유일키·재요청 전이, 철회 경합, 감사 원자성, UI 조건 표시. fetch 대역은 SQL의 terms_hash/만료 필터를 검증하지 않는다. |
| Rego 추가 3건 (`full_stack_lab/opa/policy_test.rego:840-869`) | 미승인 출처 Block+ID, 승인 출처의 해당 ID 부재, 여러 출처 중 미승인 하나의 ID | 입력 flow_sources를 직접 주입하므로 실제 조회·주체 검증을 증명하지 않는다. 정상 건은 `policy_id != P-FLOW-001`만 확인해 다른 이유의 Block도 통과한다. 세 번째는 decision을 확인하지 않는다. 외부 읽기·monitor·승인 재실행·창·동시성은 없다. |
| `before_after.py --self-test` (`before_after.py:105-137`) | 고정 수치에 대한 계산과 입력 변환 | 현재 번들에 정상군이 실행 가능하다는 것, 기대 판정의 일치, 원장/하네스/MCP 효과. 반복마다 latency는 남기지만 verdict는 마지막 것만 남긴다(`:244-265`). 판정이 흔들리면 앞선 오허용을 숨길 수 있으므로 반복별 결과/불일치도 필요하다. |

### 우선 추가할 음성·경계·실패 시험

1. **목적지 통합:** 실제 공개 OSS 변환 MCP의 계약으로 정상 public/심사 host, nonimportant→public-only, 미심사 host, 주소형 잘못된 값, URL 없는 provider 읽기를 `classify → pac.build → OPA`까지 연결한다. helper 반환뿐 아니라 `transfer.enabled`, final_destination_verified, pair, 최종 decision·policy_id를 각각 확인한다. 같은 host 두 번/서로 다른 host 둘, 대문자·끝점·443·비표준 포트·Unicode/punycode·wildcard apex/하위/유사 도메인도 대조한다.
2. **최종 목적지:** 실행기 존재만 있고 proxy 미갱신/중지인 상태, 도구 A→도구 B의 허용 host로 redirect, 단일 도구의 여러 심사 host 사이 redirect, 재심사로 host 제거 후 진행 중 호출을 시험한다. 실제 접속 로그/수신 효과로 final 검증 주장을 확인한다. 자체 mock MCP는 만들지 않는다.
3. **마스킹:** 동일 입력의 mask false/true 대조와 실제 outbound 캡처. 독립 문자열 PII와 3번의 필드 간 문맥, key/value 계좌·여권, 키·숫자·중첩·배열, 원문 Gitleaks 자격 탐지, analyzer/anonymizer 오류·잘못된 JSON·잔여 탐지값을 포함한다. 검사기 장애 시 `P-DATA-INSPECTION-001`, upstream_attempted=false와 독립 효과 0을 요구한다. 마스킹 후 형식/enum/pattern 불일치도 실행 전 실패해야 한다.
4. **원문 정책 보존:** `mask=True`여도 원문 비신뢰 지시·자격 증명 차단은 유지해야 한다. 반면 원문 `cls.dlp`의 kr-mobile/kr-rrn도 그대로 남고 `P-DLP-001`은 x에서 모든 DLP 유형을 막으므로, PII를 성공적으로 가려도 x는 계속 차단될 수 있다(`core.py:1846-1855`, `policy.rego:380-387`). 의도한 보수적 거부인지 D-131의 기능 불충족인지 명시하고, 비밀 라벨과 마스킹 완료 PII 라벨의 기대를 구별한다.
5. **동의 전이:** 다른 사용자/관리자의 타인 consent_id 결정·목록 조회, MCP 범위 토큰의 콘솔 API 접근 거부, PENDING의 동시 grant/deny, grant→revoke→다음 호출 PENDING→grant, 만료 직전/정각/이후, DENIED 재호출 시 요청 미갱신, terms_hash 변경 뒤 이전 grant 무효와 새 pending, 해시가 같은 재심사, 오래된 pending 결정, 상·하위 등급 grant/deny/revoke 충돌을 검증한다. 만료된 GRANTED는 직접 grant가 안 되고 다음 호출이 PENDING으로 되돌리는 현재 순서도 확인한다. 모든 전이에는 실제 SQL과 감사 이벤트를 대조한다.
6. **동의 경쟁·장애:** consent 검사 뒤 tools/list를 멈추고 철회/만료/조건 변경을 커밋한 후 재개한다. intent와 외부 효과 0을 확인한다. 상태 UPDATE 뒤 감사 INSERT 실패를 주입하여 둘 다 롤백되는지도 검사한다. 단순 `missing` 대역 시험으로 대체할 수 없다.
7. **흐름 범위:** 중요/일반/공개, 실행/미실행/결과 보류, r/w/x 응답, 같은/다른 서버, 같은 주체의 다른 세션·엔드포인트 및 다른 주체, 창의 직전/정각/직후, 복수 출처와 부분 승인, provider_hosted r의 패턴 없는 기밀·무관한 정상 검색을 대조한다. 쓰기 최초 검사 뒤 읽기가 완료되는 6번 경합도 포함한다. 창 만료 후 반출은 현 설계의 미탐으로 기록한다.
8. **monitor·Approval:** 새 FIELD 검사는 모드 변환 전 return, P-FLOW/PAC은 ALWAYS_ENFORCED, consent는 monitor 변환 뒤 검사이므로 **정적 경로상 새 통제가 monitor에서 일괄 꺼지지는 않는다**(`core.py:71,1825-1829,1910-1937`). 다른 정책이 먼저 선택되어도 conflicts에 P-FLOW Block이 있는 경우 집행되는지 확인한다. `approve_request → execute_call` 재진입(`core.py:2055`)은 마스킹·동의를 다시 적용하므로 단순 승인 우회는 확인하지 못했다. 승인 대기 중 조건 변경·철회·만료, 재실행 후 `P-CONSENT-001`로 NOT_EXECUTED가 되는 경우, 실제 가려진 outbound까지 시험한다.
9. **원장·평가:** 마스킹 성공 호출의 DB 행에서 원문 위치와 마스킹 유형 보존 여부를 직접 확인한다. 평가에는 유효 PAC 정상군, 의도한 policy_id와 다른 차단, 기대 Block인데 Allow인 사례를 넣는다. 현재 차단 사유 일치율은 **이미 차단된 공격만 분모**로 삼는다(`before_after.py:91-100`, README의 명시된 정의). 두 공격 중 하나가 새면 차단율 0.5지만 사유 일치율은 1.0이 될 수 있으므로 전체 기대 공격 중 정책 일치율도 별도로 제공해야 한다. 이 조건부 지표를 전체 방어 성공률로 읽지 않는다.

### 결함으로 단정하지 않은 사항

`decide`의 UPDATE는 `id AND user_token AND status`를 조건으로 하고 API는 `current_identity`의 콘솔 범위 인증을 사용한다(`agent_service.py:282-283,1576-1598`). 인자/본문의 사용자 ID로 타인 동의를 결정하는 직접 권한 상승은 발견하지 못했다. 만료 grant의 재요청·REVOKED의 PENDING 재전환·조건 변경 후 새 해시 사용도 소스에 있다. 실제 DB 경합과 API 음성 시험을 하지 않았으므로 검증 완료로 표현하지 않는다.

P-FLOW의 주체 전체 오탐, 10분 후 표지 소멸, 본문 지문을 비교하지 않는 점은 D-133의 명시된 모델/한계다. 완전한 비밀 반출 방지로 해석하지 않는다. 이 보고서의 실행 경로·함수 검증을 배포 완료나 PJ1 실제 하네스 검증으로 확대하지 않는다.
