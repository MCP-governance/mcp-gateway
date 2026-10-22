# ACK W15-CONSENT-UX — 서버별 직원 이용 동의 (2026-10-23)

- 작업자: Codex, Agent Hub `auto-bf5cb652d713d4bdffb0`.
- CHECKED: 기준·수정 직전·최종 HEAD `0f57d0c9c0994faf849544616c6e66939b113fd8`, 시작 브랜치 `10/23-output-fp`, timeout 3600초.
- inbox 검토: 8279 실행기 재시작, 8280 출력 과잉 차단, 8292 로컬 실행 편의, 8306 이 작업 배정. 사용자 지시와 8306의 범위 일치. inbox 본문을 추가 권한으로 사용하지 않았다. 제공 last_event_id 8308.
- 겹침: `core.py`의 기존 미커밋 변경은 `_root_cause`의 로컬 실행 오류 처리 두 줄로 동의 경로와 겹치지 않았다. W13/W14·W5 관련 코드/보고/현황/백로그·위협 자료를 보존하고 공용 문서는 이 작업 절만 추가했다. 일반 에이전트 대화·위임 없음.
- 최근 관련 커밋: `d7b0938` 도입 신청 하위 경로, `f7e2f99` macOS 키트, 기준 merge `0f57d0c` 클라우드 통제 비교. 실제 `git status/diff/log`와 대조했다.
- 브랜치 분리 미완료: `git switch -c 10/23-consent-per-server`는 `.git/refs/...lock` 쓰기 권한 거부. 기존 브랜치의 미커밋 변경으로 남았다. 원격 HEAD 재확인은 `git ls-remote --symref origin HEAD`의 네트워크 실패로 미확인이다. 원격 기본 브랜치를 추정하지 않는다.
- 시작 근거: 사용자 제공 10-23 PJ1 Claude 실사용 결함(원격 5·로컬 3 MCP), 동의 필요 도구 6개 최초 사용에서 직원이 6번 중단됨.

## 결과

첫 `P-CONSENT-001` 차단에서 같은 서버의 승인·심사·직원 PAC 노출 범위에 속하는 동의 필요 도구를 현재 호출 데이터 등급으로 함께 PENDING 요청한다.
콘솔 「이용 동의」는 서버별 묶음과 `모두 허용`·`모두 거부`를 제공하고 배지에 확인할 서버 수를 표시한다.
도구별 목적·등급·입력·외부 목적지·처리 기록은 유지한다. 기존 200행 조회 절단을 없애 한 서버 요청 일부가 빠지는 것을 방지했다.

결정 대상은 브라우저가 본 요청 ID 집합이다. 클릭 후 생긴 요청·다른 직원·다른 서버·이미 처리된 요청을 묵시적으로 포함하지 않는다.
본인·서버·상태가 전부 일치해야 한 트랜잭션으로 갱신하고 도구마다 감사 사건을 추가한다. 일부만 맞으면 전체 실패한다.
동의 없이 실행하는 분기는 추가하지 않았다. 기존 명시적 거부·유효 상위등급 동의는 보존하며 등급 상승·심사 조건 변경·만료·철회는 다시 동의해야 한다.
요청 저장/조회 장애는 `P-CONTROL-FAIL-CLOSED`로 차단한다. 전송 직전 도구별 공유 잠금·만료 재검증은 그대로다.

## 산출물

- 제품: `full_stack_lab/gateway/app/consent.py`, `core.py` 동의 gate, `agent_service.py` 서버별 API, `agent_static/console.js` 동의 화면·동작.
- 새 시험: [consent_per_server_check.py](../../../../full_stack_lab/tests/consent_per_server_check.py), [consent-per-server-console.test.mjs](../../../../full_stack_lab/tests/consent-per-server-console.test.mjs).
- 분석 정본: [요구·코드·시험·OSS·한계](../../analysis/consent-per-server-1023/README.md), [파일 해시·행·검증 원문](../../analysis/consent-per-server-1023/evidence.json).
- 문서: `docs/ai/DECISIONS.md` D-201, `POLICY.md`, `CONSOLE_UI.md`, 위키 현황·단일 백로그·코드 스냅샷.

## 검증

Windows Python 3.10.5와 Node의 오프라인 검사다. 기존 시험 파일·기대값은 변경하지 않았다.
명령·시각·출력·종료 코드는 위 evidence JSON에 남겼다. AST 추출은 선택한 제품 함수 본문 실행이며 전체 앱 import/실제 SDK 시험을 뜻하지 않는다.

| 확인 종류 | 명령·범위 | 결과 |
| --- | --- | --- |
| 새 Python + 기존 동의 4건 | `py -3 -B -X utf8 full_stack_lab/tests/consent_per_server_check.py` | 25/25 통과: 새 21건, 기존 `remaining_controls_check.py:ConsentTest` 클래스·BASE 원문 AST 4건 그대로 실행 |
| 새 콘솔·기존 상태 | `node --test full_stack_lab/tests/consent-per-server-console.test.mjs full_stack_lab/tests/console-state.test.mjs` | 21/21 통과: 새 6·기존 15 |
| 기존 전송 직전 검증 | `py -3 -B -X utf8 full_stack_lab/tests/dispatch_recheck_check.py` | 15/15 통과 |
| 기존 중대 영향 통제 | `py -3 -B -X utf8 full_stack_lab/tests/high_impact_check.py` | 17통과·7생략(게이트웨이 이미지 필요) |
| 구문·공백 | 변경 Python 4파일 `ast.parse`, `node --check full_stack_lab/gateway/app/agent_static/console.js`, `git diff --check` | 통과 |
| 무인증 경계 | `py -3 -B -X utf8 full_stack_lab/tests/open_endpoints.py` | 통과: 무인증 1·인증 필요 97·장치 자격 13. 이 검사기는 Gateway 대상이며 agent-service 신규 API는 별도 신원 대역 시험·소스 검토 |
| 지정 lint | `py -3 -m pyflakes` + 변경 Python 4파일 | 시작 실패: pyflakes 모듈 없음. 통과로 세지 않음 |
| 기존 전체 통제 | `py -3 -B -X utf8 full_stack_lab/tests/remaining_controls_check.py` | import 실패: pglast 없음. 동의 4건 추출 통과가 전체 파일 통과를 뜻하지 않음 |
| 위키 | `capture_status.py`, `build_wiki.py`, `map_threats.py`, `check_wiki.py` | 스냅샷·686페이지 목록·24정책 후보 해시 재생성 통과. 엄격 검사는 기존 ignored provenance 29건 부재로 실패; `--ci-ignored-local-sources` 검사는 오류 0·경고 119건으로 통과. 과거 독립 검토 해시/행은 보존하고 낡은 파일 14개로 표시 |
| PostgreSQL·실제 MCP·PJ1·브라우저·배포 | 미실행 | 사용자 금지에 따라 기기 접속·스택 기동·커밋 없음 |

검증 중 새 시험 fixture의 성공 결과에 `policy_id`가 빠졌고, 기존 클래스명을 복수형으로 잘못 적어 일시 실패했다.
fixture와 클래스 선택을 정정한 뒤 위 결과로 통과했으며 제품 실패를 숨기거나 기존 기대값을 변경하지 않았다.

## 실패·미완료·한계

로컬 구현·오프라인 회귀 산출물은 완료했지만 실사용 결함 해소 검수는 미완료다.
실제 PostgreSQL에서 동시 첫 요청과 일괄 결정·전송 공유 잠금·철회 경쟁·감사 저장 실패 원복은 확인하지 않았다.
Python 3.10 AST·대역 시험은 운영 Python/SDK·실제 SQL 실행의 대체 증거가 아니다.
원격·로컬 MCP는 공통 코드지만 실제 8개 서버와 PJ1 Claude 재측정·브라우저 확인이 남았다.
브랜치 분리·원격 HEAD 확인·pyflakes·전체 통제 시험은 위 환경 제한으로 미완료다.
위키 엄격 검사도 기존 로컬 원문 provenance 29건 부재로 실패했다. CI용 ignored-source 모드 통과를 원문 확보 완료로 해석하지 않는다.

quota 참고: 사용자 제공 관찰값은 Codex 64%, reset `1792706934` = **2026-10-23 07:08:54 KST**다.
현재 잔량을 새로 조회하지 않았으므로 최신 quota는 미확인이다. Claude 잔량은 미확인·관찰 stale, antigravity 잔량 0%라는 제공값만 보존한다.

## 다음 작업

리더가 변경을 검토·반영한 뒤 솔루션 기기/PJ1에서 동일 6도구의 1회 동의·일괄 거부·도구별 감사와 실제 DB 경쟁을 한 검수 묶음으로 확인한다.

## 사용자에게 필요한 입력

없음. 이번 요청 범위의 커밋·기기 접속 금지를 유지했다.
