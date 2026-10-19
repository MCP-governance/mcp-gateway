# 2026-10-20 중대 영향 호출과 인적 개입 증빙

- 작업자: Codex sol
- 코드 기준: 브랜치 `10/20-high-impact`, 시작 `a020458ca723b735c6e286a0e70b15a4b485f749`, 시작 작업 트리 clean. 커밋·푸시 없음, 아래 변경은 작업 트리에 남겼다.
- 시작 근거: DEV-70, [개발 계획](../../analysis/compliance/dev-plan/README.md#dev-70--중대-영향-결정-호출-분류와-인적-개입설명-증빙), 자동화된 결정 매트릭스, POL-27·38·22, 기존 D-131~136.
- 해결할 문제와 완료 조건: 중대 영향 도구를 사람 승인 경로로 강제하고 승인자·거부·번복·설명 제공 증빙을 append-only로 남긴다. 증빙 번들에 개인정보 본문을 포함하지 않는다. 이번 결과는 구현·로컬 검증이며 실제 기기 수용 완료가 아니다.

## 결과

1. 도구 범위 심사에 중대 영향 여부와 6개 영향 영역을 추가했다. 기존 도구의 개별 라벨 수정도 기존 인증·독립 심사 API로 연결했다. 라벨/영역 불일치는 거부한다.
2. `P-HIGH-IMPACT-001`을 게이트웨이 로컬 판정으로 추가했다. priority 2013은 기존 항목과 중복되지 않으며 관리대장·POLICY 목록을 함께 갱신했다. Rego 규칙은 바꾸지 않았다.
3. 관찰 모드에서도 중대 영향 호출은 승인 없이 전송하지 않는다. 승인 재실행·연결 전·최종 intent에서 원래 요청/주체·현재 심사 범위·기한·승인 사건·철회를 확인하고, 기존 1회 소비와 모든 권한/계약/검사 통제를 유지한다.
4. 요청·설명 제공·승인·거부·번복은 기존 `approval_events`를 재사용한다. 승인 사건에 요청 지문과 설명 스냅샷을 함께 남기고 최종 전송에서 대조한다. 번복 시 원래 실행 상태는 보존한다.
5. 관리자 전용 설명/내보내기·번복 라우트를 추가했다. 콘솔은 중대 영향·영향 영역·인자 유형/건수·선행 정책/판정·개입 이력을 한국어 라벨·값으로 표시한다. 번복은 「기존 실행 효과 복구: 미지원」으로 명시했다.
6. DB는 `v2_tables.sql` 끝에 nullable `approvals.explanation`, `revoked_at`, `revoked_by` 열만 추가했다. 새 의존성·자체 MCP 서버·감사 원장 수정·로컬 스택 기동은 없다.

변경 파일:

- 제품: `full_stack_lab/gateway/app/{high_impact.py,agent_contract.py,review.py,registry.py,core.py,dispatch.py,main.py,agent_service.py,v2_tables.sql,agent_static/console.js}`
- 정책 메타데이터: `full_stack_lab/opa/policy_ledger.json`
- 새 시험: `full_stack_lab/tests/high_impact_check.py`, `full_stack_lab/tests/high-impact-console.test.mjs`
- 문서: `docs/ai/{DECISIONS.md,POLICY.md,DATA_MODEL.md}`, [원자 요구사항·호출 경로·근거](../../analysis/high-impact/README.md), 이 보고서
- 상태: `status/backlog.md`의 DEV-70 마지막 칸만 변경. `status/current.md`는 변경하지 않았다.

## 검증

실행 환경은 Windows Python 3.10·Node이며 2026-10-20 KST에 수행했다. 최종 명령·종료 코드·표준 출력/오류는 [로컬 검사 원본](../../analysis/high-impact/local-checks.json)에, 변경 소스/시험의 원본·LF 해시는 [소스 스냅샷](../../analysis/high-impact/source-snapshot.json)에 보존한다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 새 순수/DB 대역 단위 | `python -X utf8 full_stack_lab/tests/high_impact_check.py` | 16건 통과, 이미지용 3건 명시적 생략 | local-checks.json |
| 새 화면 함수 | `node --test full_stack_lab/tests/high-impact-console.test.mjs` | 3건 통과 | local-checks.json |
| 기존 결과 축 | `python -X utf8 full_stack_lab/tests/outcome_axes_check.py` | 8건 통과, 기대값/시험 파일 변경 없음 | local-checks.json |
| 기존 콘솔 상태·결과 화면 | `node --test full_stack_lab/tests/console-state.test.mjs full_stack_lab/tests/outcome-console.test.mjs` | 17건 통과 | local-checks.json |
| Python/화면 구문 | 변경 Python 9개 `python -m py_compile`, `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과 | local-checks.json |
| 인증·제품 문구 | `python -X utf8 full_stack_lab/tests/open_endpoints.py`, `console_copy_check.py` | 무인증 1개 문서 일치·인증 필요 78개, 문구 위반 0개 | local-checks.json |
| 실제 게이트웨이 import 시험 시도 | `python -X utf8 full_stack_lab/tests/high_impact_check.py --gateway` | 환경으로 실행 불가: Python 3.10의 datetime.UTC 미지원 | local-checks.json |
| 기존 통제 import 시험 시도 | `python -X utf8 full_stack_lab/tests/remaining_controls_check.py` | 환경으로 실행 불가: pglast 미설치 | local-checks.json |
| pyflakes 시도 | 변경 Python 파일 `python -m pyflakes ...` | 모듈 미설치로 실행 불가 | local-checks.json |
| Git 변경 검사 | `git diff --check` | 통과 | local-checks.json |
| 위키·정책 매핑 검사 | `check_wiki.py --ci-ignored-local-sources`, `check_policy_id_mapping.py` | 미통과: 소스 후보 해시 13건·기존 POL/PAC 대응 8건 불일치. 시작 커밋에도 같은 13개 소스 관찰 불일치가 있으며, 기존 관리대장 행/PAC 소속은 이번에 바꾸지 않은 것을 별도 대조 | local-checks.json의 wiki-baseline-comparison |
| 원격 기본 브랜치 조회 시도 | `git ls-remote --symref origin HEAD` | github.com:443 연결 실패, 기존 원격 HEAD를 현재값으로 단정하지 않음 | 작업 중 도구 출력 |
| 실제 PostgreSQL·OPA | 스키마/잠금/롤백/트리거·OPA 관리대장 회귀 | 미실행 | — |
| 프로토콜·실제 모델/하네스 | 솔루션 기기·PJ1의 실제 공개 OSS MCP | 미실행 | — |
| upstream 독립 효과·배포·화면 | 기기 revision/정책 해시·외부 효과·브라우저 렌더링 | 미실행 | — |

## 기존 시험 변경 필요

이번 변경 때문에 기존 시험의 기대값을 바꿔야 한다고 확인된 항목은 없다. 기존 시험 파일은 수정하지 않았다. import 실패는 기대값 변경의 근거가 아니다.
시작 판본의 D-136 보고에 이미 적힌 자격정보 경계 AST 시험 2건의 주입 누락은 이번 레인에서 수정·재실행하지 않았다. 전체 회귀 통과를 주장하지 않는다.

## 실패·미완료·한계

- 라벨 부여의 법적/업무적 타당성·라벨 누락·실질적 숙고 여부는 자동 보장하지 않는다. 설명 열람 사건은 인증된 요청에 설명을 제공한 증거다.
- 설명은 인자 유형·건수와 정책 근거이며 모델 내부 논리나 실제 업무 결론의 의미 있는 설명을 대신하지 않는다. 승인/열람자의 내부 식별자는 책임 추적용으로 포함한다. 원래 승인·판정 테이블의 개인정보 보존 범위는 그대로다.
- 최종 intent 커밋 뒤의 번복은 이미 전송된 효과를 되돌리지 않는다. 승인/거부의 추가 자유 산문 대신 고정 검토 사유를 기록해 번들에 개인정보 본문이 섞이는 경로를 줄였다.
- 무라벨 호출은 기존 최종 서버 조회에 도구 범위를 함께 읽어 별도 DB 왕복과 추가 승인 대기를 넣지 않았다. 도구 행 공유 잠금 비용을 포함한 지연 불변은 실측하지 않았다.
- 새 시험의 DB/HTTP 대역과 생산 함수 추출은 실제 DB 경쟁·SDK·MCP 실행 증거가 아니다. 이미지용 3건은 이번 PC에서 실행하지 못했다.
- 전체 위키 검사는 기존 매핑 불일치로 통과하지 않았다. 이번 근거 문서는 새 소스 스냅샷을 제공하며 과거 관찰 해시·시험 결과를 새 통과 증거로 덮어쓰지 않았다. 통합 시 기존 매핑의 정정·대체 이력을 검토해야 한다.
- GitHub 공개 스킬은 사전 검색만 했고 현재 commit/라이선스/유지보수 이력을 고정하지 못해 채택하지 않았다. 기존 MCP SDK pin/분석을 재사용하며 신규 외부 코드는 없다.

## 다음 작업

DEV-70의 기기 수용 검증을 수행한다. 아래는 **솔루션 기기**의 해당 checkout에서 실행할 명령이며 이번에 실행하지 않았다.

```bash
cd full_stack_lab
./console.sh field up
docker compose cp tests/high_impact_check.py gateway:/tmp/high_impact_check.py
docker compose exec -T gateway python -X utf8 /tmp/high_impact_check.py --gateway
docker run --rm --entrypoint /opa -v "$PWD/opa:/policy:ro" openpolicyagent/opa:1.20.2-static test /policy
```

이어서 격리 DB에서 기존 `dispatch_intent_pg_check.py`와 스키마/append-only 트리거를 확인하고, PJ1 실제 하네스로 기존 공개 OSS MCP의 라벨/무라벨 정상·미승인·자가 승인·인자 변경·재사용·동시 승인·범위 변경·철회·장애·복구를 실행한다. 도구 호출은 합성 자료·격리 계정으로 제한하며 `decision`·`policy_id`와 독립 효과를 함께 확인한다. 콘솔 승인/거부/번복·내보내기도 실제 렌더링으로 확인한다.

## 사용자에게 필요한 입력

없음. 지정 레인에 따라 배포·실기기 검증은 사람이 솔루션 기기와 PJ1에서 수행한다. 비밀 값은 수집/기록하지 않았다.
