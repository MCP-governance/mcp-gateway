# 2026-10-20 도입 한 화면 승인

- 작업자: Codex sol
- 코드 기준: `217da74ed4731eb006ce3c167b17fec835b66155`, `10/20-intake-one-click`, 시작 시 깨끗한 작업 트리. 현재 변경은 미커밋이다. 원격 HEAD 조회는 GitHub 연결 실패로 확인하지 못했다.
- 시작 근거: 10-20 소유자의 승인 입력 최소화 지시, DEV-68·69·71·73, [기술 통제 방향](../../analysis/direction-1020/control-review.md), [D-184~187](../../../../docs/ai/DECISIONS.md).
- 해결할 문제와 완료 조건: 신청자가 고른 데이터 등급·도구 범위를 보존하고 솔루션이 계약·출처·행위·위험을 제안한다. 관리자가 한 화면에서 범위를 읽고 승인하면 독립 승인·원격 계약 기록·등록을 연결한다. 계약/검사 변경·자기 승인·2차 승인 부족은 등록 전에 거부한다.

## 결과

구현은 작업 트리에 남겼다. 기존 시험 변경 필요를 확인한 뒤 제품 코드 변경을 중단했다. 전체 회귀·배포·기기 검수 완료가 아니다.

| 화면 항목 | 전 | 후 |
| --- | --- | --- |
| 신청자 입력 | 위험 6항목 | 용도·필요 도구·데이터 등급, 유형·주소·이름. 원격은 실제 목록 선택, 저장소의 빈 도구 선택은 전체 |
| 공급자 보증 | 관리자가 필수 항목 입력 | 출처 메타데이터의 제안값, 없으면 `확인 안 됨`. 선택 보완은 접힘 영역 |
| 도구 계약 | 별도 조회·행위/범위 직접 입력 | 전체 계약 해시 고정, 도구 설명·입출력 스키마·자동 행위·범위·인자 제한 표시. 체크 해제로만 범위 축소 |
| 서버·사용자·등급 | 관리자가 서버 ID·허용 사용자·등급 재입력 | 주소/저장소+신청 식별자의 서버 ID, 신청자 한 명, 신청 등급 보존 |
| 위험 입력·영향평가 | 관리자 입력/수정 단계 | 계약 기반 제안값, 기존 표 산정. 실제 허용 사용자 1명·자율 실행을 기본값으로 사용 |
| 사용 기한 | 등록 단계 입력 | 기본 90일 선택. 첫 승인 때 절대 만료일도 고정, 입력한 EOL 상한 유지 |
| 승인 단계 | 도입 승인→1차 승인→범위→위치→등록 | 한 대화상자 승인. 높음/매우 높음만 다른 관리자 2차 승인, 같은 범위를 재확인 |
| 사유 | 위험 등급·종료 조건 등에 반복 입력 | 새 화면은 치명적 발견 수용 때만 한 줄. 거부도 한 줄 |
| 위치 | 별도 위치 심사·미입력 시 호출 차단 | 기본 관할 팩 꺼짐. 위치는 선택, 켠 배치만 공개 외 등급의 위치/근거 요구 |
| PC 격리 실행 | 별도 매니페스트 입력·조회 | 최소 권한 초안과 미확인 이미지 표시. 외부 키의 서명 묶음 입력은 접힘 영역에 유지 |

`approval-preview`는 실행을 승인하지 않고 표시한 계약/검사/신청 근거 지문과 제안값을 보관한다. `approve-and-register`와 기존 게이트웨이 등록 함수가 이를 다시 확인한다. 첫 승인 범위·기한·선택 정보를 2차 승인에도 고정하고, 재시도로 기한을 늘리지 않는다. 도구별 심사 기록의 확인자는 최종 승인자다. 원격 메타데이터 조회에도 전송 토큰의 주체를 사용해 공급자 자격의 사용자 경계를 확인하며 직원 토큰은 upstream으로 전달하지 않는다.

변경 파일·코드 심볼·시험의 연결은 [요구사항 정본](../../analysis/intake-one-click/requirements.json), 출처/OSS 검토와 한계는 [분석](../../analysis/intake-one-click/README.md)에 있다. 새 의존성·정책 ID는 없고 DB는 `v2_tables.sql` 끝에 두 JSON 열만 추가했다. `status/current.md`는 변경하지 않았다.

## 검증

실행 시각·정확한 명령·원시 stdout/stderr는 [검증 JSON](../../analysis/intake-one-click/verification.json)에 보관했다. 아래 통과 수는 단위/정적 검사이며 실제 MCP 통제 성공률이 아니다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| Python 구문 | 로컬 Python 3.12.14, 변경 제품·신규 시험 `-m py_compile`, 10-20 | 통과 | 검증 JSON `python_compile` |
| 화면 구문 | `node --check gateway/app/agent_static/console.js` | 통과 | `console_syntax` |
| 기존 콘솔·새 화면 단위 | `node --test tests/console-state.test.mjs tests/intake_one_click_ui_check.mjs` | 21 통과(기존 15+신규 6) | `console_tests` |
| 무인증 경로 | `python tests/open_endpoints.py` | 통과, 무인증 1/인증 87 | `authenticated_routes` |
| 새 순수 함수/이미지용 흐름 | `python tests/intake_one_click_check.py` | 8 통과, 이미지 의존 11 생략 | `new_pure_and_image_cases` |
| 새 승인·등록 함수 본문 | `python tests/intake_one_click_ast_check.py`, 실제 Pydantic+DB/HTTP 대역 | 11 통과. 원격 1건·서명 묶음 형태의 저장소 1건, 자기 승인/계약 변경/검사 실패/2차 승인/동일인 별도 토큰/범위 변조/팩 변경/서명 미제공 | `new_function_bodies_with_doubles` |
| 기존 공급자·위치 회귀 | `supplier_assurance_check.py`, `data_residency_check.py` | 공급자 4 통과/2 생략, 위치 8 통과 | 각 regression 레코드 |
| 기존 위험 회귀 | `intake_risk_tier_check.py` | 10 통과, **기대값 충돌 2 실패**, 의존 13 생략 | `risk_regression_unchanged_expectations` |
| CI pyflakes | 지정한 게이트웨이·시험·공급망·엔드포인트·키트 전체 파일 | 도구 실패: `No module named pyflakes`. 설치 시도도 실패, 경고 0 확인 불가 | `ci_pyflakes` |
| 위협 매핑 | `python research/llm-wiki/tools/map_threats.py` | 실행, 24개 매핑. 변경 코드의 과거 검토는 낡음으로 표시 | 검증 JSON 및 생성된 threats.json |
| 위키 검사 | `python research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | 통과, 오류 0. ignored 원본 등 경고 119 | 검증 JSON `wiki_links` |

최종 `git diff --check`도 통과했고 변경/신규 파일 33개의 UTF-8·BOM 없음·LF 검사는 오류 0이다. 위협 매핑은 24개를 생성했고 과거 검토 파일 7개의 낡음을 표시했다. 기존 검토 해시를 현재 코드로 바꾸어 이전 시험을 재사용하지 않았다.

## 기존 시험 변경 필요

기존 시험 파일의 기대값은 **변경하지 않았다**. 아래 2개가 실제로 실패하여 공통 작업 규칙에 따라 제품 코드 변경을 중단했다. 메인의 적대 검증 뒤 시험 변경 여부를 결정해야 한다.

| 기존 시험 | 기존 기대 | 새 지시와 충돌하는 이유 |
| --- | --- | --- |
| `intake_risk_tier_check.py::RiskTierPureCheck.test_approval_method_per_tier` | 높음은 관리자 1명+사유로 승인, 매우 높음은 사유 없으면 거부 | 높은 등급은 사유 대체 없이 관리자 2명. 치명적 발견이 없으면 사유 불필요 |
| `intake_risk_tier_check.py::RiskTierPureCheck.test_impact_package_maps_the_stated_input_to_assessment_items` | 매우 높음의 승인 방식이 `관리자 2명 및 위험 수용 사유` | 등급 자체의 사유 필수를 없앴으므로 `관리자 2명` |

이미지에서 실행하지 못한 기존 API 시험 중 `supplier_assurance_check.py`의 보증 누락 거부 2건, `intake_risk_tier_check.py`의 사유에 의한 단독 승인/매우 높음 사유 필수 기대도 D-185·187과 대조가 필요하다. 이들은 미실행이므로 실패 건수에 합산하지 않았다. 기존 OPA 사례는 수정하지 않고 끝에 새 사례 3개만 추가했다.

## 실패·미완료·한계

- **실기기 표본 0**: 로컬·원격 MCP 각 5종+기존 승인 3종, Claude·Codex, 반복 N≥30/지연 N≥100은 미실행이다. 요청/판정/원장 ID·시간의 실제 호출 로그가 없으므로 성공률·오탐/미탐·신뢰구간은 산출하지 않았다. 모델 자발적 중단을 통제 증거로 세지 않았다.
- WSL의 SSH 진입 전 `WSL/Service/E_ACCESSDENIED`. 기존 `wbs-c-*` 랩 존재도 미확인이다. `up`이 남의 랩을 내릴 수 있어 랩 드라이버를 실행하지 않았다. 제품 스택·다른 작업 트리·기존 랩은 변경하지 않았다.
- OPA, 게이트웨이 이미지의 정상 모듈 import, 실제 PG 잠금/경합·장애 복구, 공급자 자격 회전, 실제 서명/장치 실행, 콘솔 브라우저 렌더링은 미실행이다. HTML 템플릿 시험은 실제 화면 확인을 대신하지 않는다.
- 저장소는 실행 계약이 있어야 등록된다. 최소 권한 초안에서 이미지가 없으면 `확인 안 됨`이며 서명 묶음 또는 활성 관리 실행이 없으면 승인을 막는다. 이미지 빌드/서명 키를 이번 코드가 새로 제공하지 않는다. 브라우저 WebCrypto 추출 불가 승인 키는 **2차 제안**이다.
- 공급자 메타데이터는 새 검증 워커부터 수집한다. 과거 provenance에 없으면 재검사 전 미확인이다. 개인정보/행위/외부 전송 추정은 공급자가 기술한 이름·계약에 근거한 제안이며 법적 영향평가가 아니다. 임의 외부 URL 목적지는 자동 허용하지 않아 해당 도구가 제한될 수 있다.
- 새 통합 경로는 종료 조건 미확인을 표시하고 별도 종료 보장을 만들지 않는다. 이전 개별 API의 종료 조건·입력 검사 경로는 보존했다. 원격 서비스의 코드 검사를 수행한 것처럼 기록하지 않는다.
- 승인 DB 변경과 게이트웨이 파일 등록 사이에는 분산 원자성이 없다. 등록 실패 때 승인 상태가 남을 수 있으며 같은 범위로 재시도한다. 실제 장애·복구 증거는 없다.
- 커밋/푸시 없음. `.git` 쓰기 제한과 Codex 공통 규칙에 따라 변경을 이 작업 트리에 남긴다.

## 다음 작업

메인이 기존 기대값 2건과 이미지 의존 사례를 적대 검증하고, CI pyflakes·OPA·정상 모듈 회귀를 통과시킨 뒤 배포/PJ1 시험을 수행한다. **먼저 기기의 `docker ps --filter name=wbs-c-`로 다른 랩 여부를 확인**한다. 남의 랩이 있으면 `up`·`down`을 실행하지 않는다. 기기가 비어 있고 이 작업의 랩으로 확인된 경우 WSL의 이 작업 트리 `full_stack_lab/`에서:

```bash
tests/termination_dispatch_lab.sh up
tests/termination_dispatch_lab.sh run intake_one_click_check.py
tests/termination_dispatch_lab.sh run supplier_assurance_check.py
tests/termination_dispatch_lab.sh run data_residency_check.py
tests/termination_dispatch_lab.sh run intake_risk_tier_check.py
tests/termination_dispatch_lab.sh down
```

기기의 OPA 검사: `docker run --rm --entrypoint /opa -v "$PWD/opa:/policy:ro" openpolicyagent/opa:1.20.2-static test /policy`. 위치 기본 해제의 양성, 명시 활성의 음성, 팩 비활성이 계약 차단을 우회하지 않는 사례를 포함한다. 기대값 변경 결정 전 전체 회귀 통과를 선언하지 않는다. 실제 하네스·다수 MCP 시험은 솔루션 기기 배포 뒤 PJ1에서만 수행한다.

## 사용자에게 필요한 입력

새 질문 없음. 메인 레인에 필요한 것은 기존 시험 기대값 결정, WSL/솔루션 기기 실행 권한, 실제 서명 묶음·격리 엔드포인트·승인된 MCP와 두 하네스다. 비밀 값은 보고서나 로그에 기록하지 않는다.
