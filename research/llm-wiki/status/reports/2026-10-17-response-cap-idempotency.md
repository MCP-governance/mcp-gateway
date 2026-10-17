# 2026-10-17 작업 H — 응답 상한·변경 재전송 방지 (실제 작업 2026-10-18)

- 작업자: Codex, 단독 수행. 다른 모델·하위 에이전트 실행 없음.
- 코드 기준: `fd904c24250b6029061283bb8a57fa4efe0b5b17`, 시작 clean, 브랜치 `10/18-response-cap`.
- 요청 브랜치: `10/18-response-cap-idempotency`. `git switch -c`가 공유 `.git/refs/...lock` 쓰기 권한으로 거부됐다. 커밋·스테이징·push 없음.
- 원격 HEAD 재조회: `git ls-remote --symref origin HEAD`는 GitHub 443 연결 실패. 현재 기본 브랜치를 새로 확인했다고 주장하지 않는다.
- 시작 근거: DEV-54/G03.06/POL-35, DEV-55/G03.07/POL-36, [기능명세](../../analysis/feature-spec-2026-10-17/README.md),
  [LIB-K26·K27](../../papers/policy50-gap-references.md), [원자 요구·코드 지문](../../analysis/response-cap-idempotency/requirements.json).
- 해결할 문제: 기존 호출량/누적 접근 제한과 별개인 단일 응답 상한, lease 뒤 사라지던 완료 쓰기의 중복 방지.
- 완료 조건: 정상·음성·경계·장애 함수 검사와 실제 DB/Gitea 독립 효과를 구분해 인계한다. 실제 효과·배포 검수는 미완료다.

## 결과

D-125: 기본 1000건·262144 UTF-8 JSON 바이트, 원문/마스킹 후 검사. 전체 파일/키 선택자와 제한 없는 SQL 조회는
`P-VOLUME-002`로 전송 전에 차단한다. 결과 초과는 기존 `MCP-OUTPUT-001`로 실행 후 응답을 전부 보류한다.
평문은 비어 있지 않은 줄 수, JSON은 배열 원소 합을 사용하므로 임의 평문의 의미상 레코드 수 보장은 아니다.

D-126: 기존 canonical 지문·`dispatch_intents`·주체별 advisory lock을 재사용한다. 완료 쓰기의 같은 인자는 기본 24시간
`P-RATE-003`으로 재전송하지 않으며 마지막 전송 경계에서도 확인한다. lease 만료가 이력을 지우지 않는다.
미확인 쓰기는 시간으로 자동 해제하지 않고 관리자 downstream 확인을 요구한다. 읽기·다른 인자는 완료 이력으로 막지 않는다.
결과 재생·새 MCP 서버·새 의존성은 추가하지 않았다. 의도적 동일 변경도 기간 중 차단되며 exactly-once 보장은 아니다.

수정 범위: `full_stack_lab/gateway/app/{classify,core,dispatch}.py`, `v2_tables.sql`,
`full_stack_lab/opa/{policy.rego,policy_ledger.json}`, `full_stack_lab/tests/{response_cap_idempotency_test,dispatch_intent_pg_check,dispatch_effect_lab}.py`,
공통 시험 준비 `termination_lab_support.py`(ops 스키마와 일회용 실제 서명 저장소 연결),
`docs/ai/{DECISIONS,POLICY,DATA_MODEL,ARCHITECTURE,TESTING}.md`, 이 분석/보고와 DEV-54·55 백로그 행.
코드 기본값 안내 `.env.example`과 정적 위협 매핑·로컬 저장소 스냅샷도 갱신했다. `.env`에만 값을 적어서는 컨테이너 환경값이 바뀌지 않는 기존 배포 방식은 유지한다.
`upstream.py`·`destination.py`는 수정하지 않았다. 공용 `status/current.md`는 병합 담당자가 반영할 문구를 아래에 남긴다.

## 검증

실행 환경: Windows PowerShell, 로컬 Python 3.10, 2026-10-18 KST. 실제 로그는 같은 분석 폴더 `checks.txt`에 보존한다.

| 확인 종류 | 명령·환경 | 결과 | 증거/한계 |
| --- | --- | --- | --- |
| 오프라인 제품 함수 | `python -B -X utf8 -m unittest discover -s full_stack_lab/tests -p response_cap_idempotency_test.py -v` | 10 통과·2 미실행 | pglast 문법·cryptography 서명 fixture 미실행. AST 제품 함수와 DB·scanner·기한 컨텍스트 대역. 실제 MCP/DB 아님 |
| 기존 경계 회귀 | 같은 unittest 명령의 패턴 `dest_pin_credential_redaction_check.py` | 16 통과 | TLS/자격·감사 응답 경계 함수 수준 |
| 기존 세션 회귀 | 패턴 `upstream_session_reuse_test.py` | 40 통과 | SDK/DB 대역, 실제 세션 실행 아님 |
| 기존 운영·폐기 회귀 | 패턴 `ops_response_check.py` | 23 통과 | 대역 환경의 함수 검사. 실제 암호/DB 통합 아님 |
| Python 문법 | 변경 Python 7개를 `compile(..., 'exec')` | 통과 | import/기동 검증 아님 |
| Python lint | `python -m pyflakes` 변경 Python | 미실행 | `No module named pyflakes` |
| JS 문법·상태 | `node --check full_stack_lab/gateway/app/agent_static/console.js`, `node --test full_stack_lab/tests/console-state.test.mjs` | 통과·15 통과 | UI 변경 없음 |
| 무인증 경로 | `python -B -X utf8 full_stack_lab/tests/open_endpoints.py` | 통과 | 무인증 1·인증 필요72(장치 자격8) |
| Rego | OPA 1.20.2 `opa test` | 미실행 | `opa`·`docker` 실행 파일 없음, WSL `E_ACCESSDENIED` |
| 실제 PostgreSQL 경쟁·복구 | `dispatch_intent_pg_check.py` 추가 시나리오 | 미실행 | 완료/lease/기간/미확인·관리자 복구/최종 경쟁을 작성만 함 |
| 실제 Gitea MCP·효과 | `dispatch_effect_lab.py` 추가 시나리오 | 미실행 | 완료 재전송 뒤 issue 1건, 실제 응답 보류·복구, 전체 폴더 미전송을 작성만 함 |
| 모델·하네스·배포 | 솔루션·PJ1·pj3 | 미실행 | 이번 지시대로 원격 접속·compose·스택 기동 없음 |

## 실패·미완료·한계

- 최초 오프라인 시험은 시험용 AST의 위치 정보 누락으로 실패했고 고친 뒤 재실행했다. 제품 판정 통과로 세지 않았다.
- pglast·cryptography·pyflakes·OPA가 없는 현재 환경에서 네이티브 문법·암호 fixture·lint·정책 엔진을 통과했다고 표시하지 않는다.
  실제 서명 fixture 검사는 cryptography 누락으로 실패한 뒤 환경 조건부 미실행으로 명시했다.
- 표준/SDK/공개 스킬 탐색·판본·라이선스·미확인 항목은 [분석](../../analysis/response-cap-idempotency/README.md)에 있다.
  외부 스크립트를 실행하지 않았다. 새 mock MCP도 만들지 않았다.
- `map_threats.py`(24개 정적 후보)·`capture_status.py`·`build_wiki.py`를 실행했다. 위협 매핑은 코드 hash만 갱신하며 실험 결과를 올리지 않는다.
  재검사한 전체 위키는 기존 비공개 원본 provenance 29개 누락으로 실패했다([실제 출력](../../analysis/response-cap-idempotency/wiki-check.json)).
  이번 코드의 매핑 불일치·추가 링크 오류는 남지 않았다. 기존 원본을 임의 생성해 오류를 숨기지 않는다.
- 전송 신원·직원 토큰 upstream 전달 금지·실패 차단·append-only 감사·C1~C4/T1~T3 기준은 유지한다.
  PostgreSQL 잠금·기한 경계·인덱스 비용·실제 OSS 반환 형태는 기기 검수 전이다.

## 다음 작업 — 병합 담당자 실행

권한이 있는 주 작업 환경에서 아래 순서로 수행한다. 이 세션은 아래 명령을 실행하지 않았다.

1. `10/18-response-cap-idempotency` 브랜치를 확보하고 실제 diff를 옮긴다. 기준 commit·다른 작업자 변경을 대조한다.
2. Gateway 의존성이 있는 Python 환경에서 위 unittest를 재실행해 native SQL 문법·실제 서명 fixture까지 확인하고, 변경 Python 7개에 pyflakes를 실행한다.
3. 로컬에서 허용된 일회성 OPA만 실행한다(전체 compose 기동 금지).

```bash
cd full_stack_lab
docker run --rm --entrypoint /opa -v "$PWD/opa:/policy:ro" openpolicyagent/opa:1.20.2-static test /policy
```

4. 기존 격리 랩이 다른 작업에 사용 중인지 확인한 뒤 소유자가 허용한 시간에 실행한다. `up`은 같은 이름의 랩을 정리하므로 남의 실행 중 랩에 쓰지 않는다.

```bash
# WSL에서; 실제 솔루션 기기의 기존 격리 DB/OPA/Presidio/Gitea MCP 설비만 사용
cd full_stack_lab
tests/termination_dispatch_lab.sh up
tests/termination_dispatch_lab.sh run dispatch_intent_pg_check.py
tests/termination_dispatch_lab.sh run dispatch_effect_lab.py
tests/termination_dispatch_lab.sh down
```

각 명령의 종료 코드를 확인하고 실패 시 다음 단계로 진행하지 않는다. 사용한 MCP 이미지 digest·정책 해시·로그·Gitea issue 수를 기록한다.
`dispatch_effect_lab.py`의 기존 Gitleaks 무검출 대역은 자격 탐지 검증이 아니며 보고서에 명시한다.

5. 위키 `map_threats.py`·`capture_status.py`·`build_wiki.py`·`check_wiki.py`를 병합 결과에서 다시 실행한다.
6. 솔루션 기기에서만 `./console.sh field up`으로 배포한 뒤 PJ1 실제 하네스에서 정상 조회/상한/완료 재전송·미확인 복구를 확인한다.
   원장 `decision`·`policy_id`·attempted/executed/disposition과 실제 downstream 쓰기 수를 함께 대조한다. 검수 전 WBS 점수는 올리지 않는다.

공용 현황 반영 문구: **DEV-54·55/D-125·126 로컬 구현, 오프라인 10+16+40+23·콘솔15·경로 검사 통과.
native parser·실제 서명 fixture·pyflakes·OPA·DB/Gitea 독립 효과·배포/PJ1 미검증. 제한된 지문 재전송 방지이며 정확히 한 번 보장 아님.**

## 사용자에게 필요한 입력

새 업무 권한·실사용 데이터·자격증명은 필요 없다. 병합 담당자의 공유 Git 쓰기 환경과 기존 격리 랩 검수 시간이 필요하다.
현재 세션에서 추가 권한 요청이나 원격 실행은 하지 않는다.
