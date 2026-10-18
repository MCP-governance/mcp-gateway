# 2026-10-18 남은 통제 구현 — 사용자 동의·전송 목적 결속·입력 항목/마스킹·서버 간 전달·효과 평가

- 작업자: Claude Code(구현·통합·기기 시험), Codex sol(구조도·변경 적대 검증), Codex luna(평가 도구 초안·구조도 개편)
- 코드 기준: 시작 `main` `d6679fd`, 브랜치 `10/18-remaining-features`. 커밋 `a6a8963`·`a5d7e9f`(평가, luna 작성)·`fe45bce`·`43a734d`·`35234aa`·`b9474f6`·`f799157`·`4857adc`
- 시작 근거: WBS G02.05·G04.05·G04.06·G04.07·G10.05(백로그 DEV-51·57·58·59·65), 정책 POL-08·26·31·33, [기능명세·WBS](../../analysis/feature-spec-2026-10-17/README.md)
- 결정: [D-131~D-135](../../../../docs/ai/DECISIONS.md)
- 완료 조건(WBS): 동의 없는 데이터·기능 호출 차단과 확인 요청 / 목적·수신처·등급 조합이 승인과 다르면 전송 차단 / 허용 밖 입력 항목과 민감정보 미전달 / 승인 없는 서버 간 중요정보 전달 차단 / 같은 시나리오의 적용 전후 결과와 지표 6개 재현

## 결과

도구 범위 심사(`ToolReview`)에 다섯 조건을 더하고 게이트웨이 호출 경로·OPA·콘솔에 연결했다.

| WBS | 구현 | 집행 위치 | 정책 ID |
| --- | --- | --- | --- |
| G04.06 | `inputs`(허용 입력 항목, 고정 계약과 대조·필수 항목 유지), `mask`(Presidio Anonymizer로 가린 뒤 전체 재검사) | 입력 계약 단계, 입력 검사 단계 | `P-INPUT-FIELD-001`, 잔여 개인정보는 기존 `MCP-DATA-EGRESS-001` |
| G04.05 | `grade`(외부 전송 최고 등급), PAC-12 `transfer_pairs`=목적·목적지·등급, 콘솔 등록 서버의 주소형 인자 목적지 추출, 최종 목적지는 실행기 출구 목록⊆도구 심사 목적지일 때만 검증 | OPA PAC-12 | `PAC-12`(심사 밖 목적지는 인자 범위 `PAC-01`이 먼저) |
| G04.07 | `accepts_from`, 같은 주체가 10분 안에 다른 서버에서 중요정보를 읽은 뒤의 쓰기·실행·공급자 호스팅 호출 | OPA | `P-FLOW-001`(우선순위 47, 관찰 모드에서도 집행, 공급자 호스팅은 심사로도 못 풂) |
| G02.05 | `consent`, `user_consents`(도구·등급·심사 조건 해시·90일), 콘솔 「이용 동의」(본인만 동의·거부·철회), 배지 | 정책 판정 뒤 실행 전 | `P-CONSENT-001` |
| G10.05 | `full_stack_lab/eval/before_after.py`(제품 밖), 지표 6개 잠정안, PAC15 재생 사례 10건+POL-33 사례 4건 | 고정 OPA 이미지 | — |

OSS 우선: 마스킹은 이미 쓰는 Presidio Anonymizer, 입력 범위는 jsonschema, 결속·흐름은 OPA, 평가는 OPA 고정 이미지. 흐름 통제는 Portcullis·MCPGuard(세션 오염 표지+OPA/Rego)와 같은 구조를 새 프로세스 없이 붙였고, Invariant Guardrails·CaMeL·FIDES류는 별도 런타임·추적 형식이 필요해 도입하지 않았다. 동의 확인은 MCP elicitation(2025-06-18) 대신 콘솔(대역 밖)로 받았다(자동 수락 클라이언트 위험, D-134).

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | pyflakes(게이트웨이 변경 파일), `node --check`, `console-state.test.mjs`, `open_endpoints.py` | 통과, 콘솔 15/15, 무인증 1·인증 73 | 터미널 |
| 정책 단위 | 기기 `openpolicyagent/opa:1.20.2-static test`(작업 트리) | 95/95 (P-FLOW-001 4건 추가) | `full_stack_lab/opa/policy_test.rego` |
| 게이트웨이 단위 | 기기 gateway 이미지: `remaining_controls_check` 16, `mcp_result_contract_check` 18, `intake_identity_test` 19, `runtime_worker_check` 7, `app.consent`·`app.classify` 자체 점검 | 모두 통과 | `full_stack_lab/tests/remaining_controls_check.py` |
| 배포 | 기기 `field up` — `fe45bce`→`43a734d`→`f799157`→`4857adc` | 정상 기동 | 기기 `~/mcp-gateway` 브랜치 |
| 실제 하네스·MCP(입력 마스킹) | PJ1 관리 계정 Codex → Context7 `resolve-library-id`, 질의에 이메일·전화번호 | 마스킹 전 #30 `MCP-DATA-EGRESS-001` 미전송 / 마스킹 후 #31·#37 허용·업스트림 실행, `masked_types`=EMAIL_ADDRESS·KR_PHONE, 잔여 0, 송신 인자 해시 기록. Context7은 자체 월 할당량 응답 | [device-e2e.json](../../analysis/controls-1018/device-e2e.json) |
| 실제 하네스·MCP(전송 결속) | PJ1 Codex → MarkItDown(실행기, 출구 프록시) `convert_to_markdown` | 심사 목적지 learn.microsoft.com #34 허용(쌍 {public·목적·목적지}, 최종 목적지 검증) / example.com #35 실행 전 차단 `PAC-01`(PAC-12 사실 불충족) | 같은 파일 |
| 실제 하네스·MCP(동의) | MarkItDown에 `consent` 설정 후 PJ1 Codex, 직원 계정 콘솔 API | #32 `P-CONSENT-001`+PENDING → 동의 → #33 허용·실제 변환 → 철회 → #36 다시 차단·재요청. 관리자(root)의 타인 동의 결정 409 | 같은 파일 |
| 심사 입력 항목 | 기기 재심사(`review_tool_scopes`, actor root) | 필수 `query` 제외·계약 밖 `extra` 거부, 정상 범위 저장 | 터미널 |
| 서버 간 전달(실기기) | — | **미실행**: 현장 등록 서버가 모두 공개·내부 등급이라 중요정보 열람 원장이 생기지 않는다 | — |
| 효과 평가 | 기기 `before_after.py --before d6679fd --after worktree --repeat 5`, 사례 14 | 공격 차단율 0.778→1.000, 정상 허용률 1.000→1.000, 오탐 0→0, 정밀도 1.000, 차단 사유 일치 1.000, 지연 p50/p95 2.28/3.47→2.49/3.74 ms. `--before none` 기준선 0→1.000 | [before-after.json](../../analysis/controls-1018/before-after.json), [none-after.json](../../analysis/controls-1018/none-after.json), [보고](../../analysis/controls-1018/eval-report-before-after.md) |
| 감사 원장 | `verify_audit_chain` | 37/37 무결 | device-e2e.json |
| 적대 검증 | Codex sol(gpt-6.1-sol, high) | 높음 5·중간 5 → 1·2·3·4·7·8·9·10 반영, 5·6 한계 | [codex-sol-adversarial.md](../../analysis/controls-1018/codex-sol-adversarial.md) |

시험용으로 바꾼 Context7·MarkItDown 도구 심사는 끝에 기본값(마스킹·동의 없음)으로 되돌렸다.

## 실패·미완료·한계

- 기기 시험 중 동의 API가 500을 돌려준 결함(이벤트 결과값 CHECK 위반, 상태만 먼저 커밋)을 `35234aa`로 고쳤다. 그 전의 동의 #1 최초 동의(07:42Z)는 이벤트 없이 기록돼 있다(원장 append-only라 그대로 둠). 이후 철회는 이벤트로 남았다.
- 판정과 실제 전송 사이에 일어난 동의 철회·새 중요정보 열람은 그 호출에 반영되지 않는다(sol 5·6번).
- 서버 간 전달 표지는 주체·10분 단위의 거친 표지라 관련 없는 호출도 막을 수 있다. 내용 지문 대조가 다음 단계다.
- 실행(x) 도구는 개인정보를 가려도 원본 DLP 라벨로 `P-DLP-001`이 계속 막는다(보수 판정).
- 콘솔 「이용 동의」·범위 심사 양식은 API·정적 검사까지 확인했다. 비로컬 기기에 브라우저 로그인을 하지 않아 화면 렌더링은 미확인이다.
- 평가 지표 6개는 위키에 정의가 없어 잠정안이다(D-135). 평가는 OPA 판정만 비교한다.

## 다음 작업

- DEV-59(G04.07) 실기기: 중요 등급 서버를 정상 도입 절차로 등록한 뒤 PJ1에서 열람→다른 서버 호출 차단 확인.
- 콘솔 화면 확인(사용자 로그인 세션에서 「이용 동의」·범위 심사 양식).
- 동의·흐름의 전송 직전 재확인(dispatch intent 결속) 설계.

## 사용자에게 필요한 입력

없음.
