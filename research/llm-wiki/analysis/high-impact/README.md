# DEV-70 · 중대 영향 호출의 인적 개입 증빙

- 작업자: Codex sol, 2026-10-20, 결정 D-139
- 기준: `10/20-high-impact`, 시작 `a020458ca723b735c6e286a0e70b15a4b485f749`. 미커밋 구현이며 배포 증거가 아니다.
- 현재 변경 소스/시험의 원본·LF 해시: [소스 스냅샷](source-snapshot.json). [실행 명령·검사 원본](local-checks.json).
- 근거: [개발 계획 DEV-70](../compliance/dev-plan/README.md#dev-70--중대-영향-결정-호출-분류와-인적-개입설명-증빙), [자동화된 결정 매트릭스](../compliance/by-theme/automated_decision_rights.md), [POL 의미 매핑](../drive-curation/policy-id-mapping.json).

## 판단과 범위

POL-27은 민감한 작업의 개별 승인, POL-38은 호출과 권한 변경 이력 관리, POL-22는 요청마다 실행 권한 확인이다. 독스용 PAC의 같은 번호와 혼동하지 않는다.
매트릭스의 REQ-M06-12(법적 효과·채용·신용), REQ-M29-10(중대한 권익 영향), REQ-M48-04(급부·계약·서비스 접근), REQ-M46-04 및 REQ-M14-25(사람 개입·재검토)를 통제 후보의 근거로 사용했다.
원문을 이번 작업에서 다시 법률 검토하지 않았다. 관할별 적용 범위·시행 상태는 기존 매트릭스 판본의 사실이며, 라벨이나 승인 클릭이 법률상 의미 있는 인적 개입을 자동 충족한다는 주장이 아니다.

독립 도입 심사자가 도구 범위에 `high_impact`와 `impact_domains`를 설정한다. 영역은 `employment`(고용·급여), `credit`(신용), `legal`(법적 효력), `benefits`(급부), `contract`(계약), `service_access`(서비스 접근)다.
true에는 1개 이상의 유효한 영역이 필요하고 false에 영역이 있으면 거부한다. 누락은 기존 도구와 호환되도록 false다. 모델이나 도구 인자가 라벨을 정하지 않는다. 기존 등록 도구는 범위 화면의 「중대 영향 심사」에서 개별 변경한다.

## 원자 요구사항과 검증 연결

코드는 저장소 루트의 `full_stack_lab/gateway/app/`, 시험은 `full_stack_lab/tests/` 기준이다. 시작 커밋과 변경 파일은 작업 보고에 기록한다. 아래 행은 2026-10-20 미커밋 구현의 시작 행이다.

| 파일 | 심볼·행 |
| --- | --- |
| `agent_contract.py` | `ToolReview:30` |
| `review.py` | `record_event:34`, `normalize_tool_reviews:211` |
| `core.py` | `review_tool_scopes:723`, `_call_upstream:1290`, `execute_call:1749`, `approve_request:2065`, `approval_evidence:2121`, `revoke_approval:2150`, `reject_request:2224` |
| `dispatch.py` | `record:61` |

| 요구 ID | 조건·동작 | 코드 심볼 | 새 시험 조건 | 현재 증거 |
| --- | --- | --- | --- | --- |
| HI-01 | 라벨·영역의 일관성, 임의 범주·문자 불리언 거부 | `agent_contract.ToolReview.impact_scope`, `review.normalize_tool_reviews`, `high_impact.normalize` | 6개 영역·누락·음성·중복, 실제 요청 모델 | 순수 시험 통과, 요청 모델 import 미실행 |
| HI-02 | 집행 중인 선행 차단 유지, 나머지 중대 영향 호출은 관찰 모드에서도 승인 | `core.execute_call`, `ALWAYS_ENFORCED` | 허용·경고·제한·차단 × 집행·관찰, 위조 approval_granted | 실제 함수 전체 실행 시험은 이미지에서 실행 필요 |
| HI-03 | 자가 승인·만료·중복 처리·열람 없는 승인 거부 | `core.approve_request`, `review.require_independent`, `_require_explanation` | 자가 승인 오류·만료·경쟁 패자·설명 해시 불일치·미열람 | 생산 함수 추출+DB 대역 통과, 실제 DB 경쟁 미실행 |
| HI-04 | 재실행과 전송 전 요청·현재 범위·승인 사건·단일 소비 재검증 | `high_impact.bound`, `core._call_upstream`, `dispatch.record` | 요청/범위 변경·철회·재사용·승인 사건 누락·라벨 없는 정상 | 순수/전송 함수 대역 통과, 연결 전 거부 시험은 이미지에서 실행 필요 |
| HI-05 | 설명·열람·승인·거부·번복의 append-only 사건 | `core.approval_evidence`, `approve_request`, `reject_request`, `revoke_approval`, `review.record_event` | 처리자·설명 스냅샷·해시·원장 수정 없음 | 함수+DB 대역 통과, PostgreSQL 트리거 미실행 |
| HI-06 | 원문 없는 결정 증빙 내보내기 | `high_impact.explanation`, `core.approval_evidence` | 개인정보가 든 인자 키·값·심사 산문·거부 산문 배제 | 순수/함수 시험 통과 |
| HI-07 | 한국어 라벨·값·안전한 HTML·개별 라벨 변경 | `scopeFields`, `collectScopes`, `scopeTable`, `impactExplanation`, `ACTIONS` | 공통/개별 선택·한국어·HTML 주입 이스케이프 | Node 함수 3건·기존 문구 검사 통과, 실제 화면 렌더링 미실행 |

시험 파일: `high_impact_check.py`(로컬 기본 실행, 이미지 `--gateway` 추가), `high-impact-console.test.mjs`.

## 실행 경로와 경쟁 경계

1. 인증된 ingress가 전송 토큰에서 정한 주체만 `execute_call`로 넘긴다. 도구 인자·클라이언트 보고값은 신원으로 쓰지 않는다.
   정적 호출자 대조: `mcp_facade.call_tool`은 이 경로로만 도구 호출을 전달하고, 종료 증거 수집 `decommission.collect`도 같은 함수를 사용한다. `acceptance.call`의 client.call_tool은 게이트웨이 MCP URL로 보내는 시험 호출이며 우회 upstream 전송이 아니다. 실제 클라이언트 송신은 `core._call_upstream → dispatch.record → client.call_tool` 순서다.
2. 기존 신원·계약·스키마·분류·검사·권한·동의 통제를 유지한다. 관찰 투영 전의 OPA 판정을 설명의 선행 정책으로 보존한다.
3. 유효한 중대 영향 승인 행이 없으면 `P-HIGH-IMPACT-001 / Approval`. 승인 행과 `call-request` 설명 사건을 같은 트랜잭션으로 쓴다. 이 분기는 `_call_upstream`을 호출하지 않는다.
4. `/api/approvals/{id}/evidence`는 관리자 전용이다. 설명 해시의 열람 사건을 append하고 번들을 돌려준다. 승인·거부는 같은 사람의 같은 설명 열람과 고정 검토 사유를 요구한다. 본인 요청 승인은 기존 독립 심사 규칙으로 거부한다.
5. 승인 선점과 `call-approve` 사건을 같은 트랜잭션으로 쓴 뒤 `execute_call`로 다시 진입한다. 승인 불리언만으로는 통과하지 않으며, 원래 주체·서버·도구·인자·범위 해시와 승인 상태·기한을 대조한다.
6. `_call_upstream`도 중대 영향 승인 상태를 연결 전에 확인한다. 목록·계약·현재 권한은 기존 경로로 다시 확인한다.
7. 최종 `dispatch.record`는 서버 공유 잠금 뒤 도구 행 공유 잠금으로 현재 DB 범위를 읽고, 승인 행의 `FOR UPDATE` 잠금 아래 승인 사건의 설명과 요청 지문을 확인한다. 기존 요청 지문 대조와 `APPROVED → UNCONFIRMED` 1회 소비가 intent와 같은 트랜잭션에 있다. 범위 추가/변경의 DB 반영·승인 철회가 먼저 완료되면 전송하지 않는다.
8. 번복은 원승인자만 한다. 같은 승인 행을 잠그는 UPDATE가 `revoked_at`·`revoked_by`를 기록하고 `call-revoke / recorded`를 append한다. 기존 상태·결정 원장을 고치지 않고 조회에서 「승인 번복」으로 표시한다. intent 커밋 이후에는 이미 전송됐을 수 있으므로 번복이 실행 취소나 외부 효과 복구를 뜻하지 않는다.

DB 확장은 `v2_tables.sql` 끝의 nullable `approvals.explanation`, `revoked_at`, `revoked_by` 추가뿐이다. 새 상태 CHECK·테이블·정책 엔진·의존성은 없다.
영역 수정은 기존 `tool_reviews`와 `mcp_tools.scope_review`를 재사용한다. 등록/범위 심사 이벤트에도 라벨·영역을 기록한다.

## 설명과 개인정보 경계

설명은 요청 요약, 서버/도구, 영향 영역, 인자의 JSON 유형별 건수, 행위·등급, 선행 정책 ID·판정·정책 판본, 적용 정책으로 구성한다.
인자 **키도** 개인정보일 수 있으므로 키·값·자유 산문·결과 본문·부분 미리보기는 번들에 넣지 않는다. 승인자와 열람자의 내부 주체 식별자·시각은 책임 추적을 위해 포함한다.
승인/거부/번복 사유는 고정된 검토 사유로 기록한다. 과거 또는 자가 승인 거부의 자유 산문은 내보내지 않는다. 결과는 기존 네 축과 실행 시도/응답 확인만 포함한다.
원래 실행 인자는 기존 승인 테이블과 판정 원장 보존 규칙을 따른다. 이번 개인정보 본문 제외 보장은 **이 설명·내보내기 번들** 범위다. 모델 내부 추론이나 업무 결정의 실제 타당성을 설명하는 기능은 아니다.

## OSS·공개 스킬 사전 검토

- 기존 MCP Python SDK `mcp==2.2.0`, 고정 commit `9972c21aa42054fb1450c5fc614761ed11847ec6` 및 실패 경로는 [기존 소스 분석](../oss-deep/deps-sdk-authlib-opa.md)을 재사용했다. 현재 사용 pin은 `gateway/requirements.txt`로 재확인했다. [공식 라이선스](https://github.com/modelcontextprotocol/python-sdk/blob/main/LICENSE)는 MIT다. 프로토콜 연결/도구 실행만 기존 SDK에 맡기며 조직별 승인 증빙을 SDK에 위임하지 않는다.
- [Anthropic 공개 스킬 저장소](https://github.com/anthropics/skills?ref=retn.kr)와 [공식 소개](https://www.anthropic.com/research/skills)를 웹 검색으로 먼저 확인했다. 스킬 본문·현재 commit·배포물별 라이선스·최근 유지보수 이력은 확인하지 못했으므로 코드·스크립트·지시를 채택하지 않았다. 새 설치·다운로드·스킬 실행 없음.
- SDK 최신 판본/유지보수 상태의 독립 재평가는 이번 범위 밖이다. 새 의존성 없이 표준 라이브러리와 기존 승인·DB·SDK·HTML 이스케이프를 재사용한다.

## 미확인과 다음 검증

실제 PostgreSQL의 잠금·롤백·스키마 적용, OPA 관리대장 회귀, 솔루션 기기 배포, PJ1의 실제 OSS MCP 정상/음성/동시 호출, 브라우저 렌더링은 미실행이다.
무라벨 정상 호출의 기존 최종 서버 조회에 도구 범위를 결합해 별도 DB 왕복을 추가하지 않는다. 도구 행 공유 잠금의 비용까지 지연 불변을 실측했다고 주장하지 않으며, 추가 승인 대기 없이 기존 판정 경로를 유지한다.
라벨 미지정/오분류·고객의 법적 판단·관리자 로그인 탈취·승인자의 실질적 숙고 여부는 자동 검증하지 않는다. 열람 이벤트는 인증된 요청에 설명을 제공했다는 증거다.
기기 검증에서는 기존 공개 OSS MCP에 합성 자료·격리 계정만 사용하고 원장 정책 ID와 독립 효과를 대조한다. 자체 MCP 서버는 만들지 않는다.
