# L24-B — 반환 상한·멱등 시험 변경 적대 검토

- 검토자: Codex sol, 2026-10-20.
- 결론: **세 hunk 모두 A(채택)**. 기존 기대값과 검사 범위를 유지하면서 D-149 이후 필요한 실제 함수와 의존성을 시험 이름공간에 복원한다. B(수정 후 채택)·C(거부)는 없다.
- 작업 브랜치: `10/20-resource-server-residual`, 시작 HEAD `877a5138574308fd18ee72817f3d9712f6af114e`. 시작 작업 트리는 깨끗했다.
- 후보: `luna/cap` = `01f17018e695ed83b1de322097bf154fe8b5cbb7`, 부모 `bac155a8b78222fc878ff642ea1aa177ddb82fba`.
- 비교 기준: 병합 전 `8983311cfd3589716640351630d13e801d447d50` 및 후보 부모. 원격 HEAD 재조회는 GitHub 연결 실패로 확인하지 못했다. 검토 대상은 이미 확보된 로컬 ref로 고정했다.
- 범위: `git show luna/cap -- full_stack_lab/tests/response_cap_idempotency_test.py`의 세 hunk와 연결 제품 정의, 같은 후보의 변경 이유 보고 Git 객체 `01f17018:research/llm-wiki/status/reports/2026-10-20-response-cap-idempotency.md`(현재 작업 트리에는 없음). 이 브랜치에는 후보를 적용하지 않았다. **이번 변경 파일은 이 리뷰 하나뿐이며 코드·기존 시험·현황·백로그·결정 기록을 수정하지 않았다. 커밋하지 않는다.**

## 변경의 목적과 기준

기존 `guard()`는 제품 `_guarded_result`를 AST로 가져오면서 D-149가 새로 호출하는 `_validate_output`과 `output_contract.for_protocol`을 제공하지 않았다. 이 검토의 로컬 실행에서도 기존 시험과 현재 제품 코드 조합은 `test_byte_boundary_uses_utf8`, `test_raw_count_boundary_and_no_truncation` 두 건에서 `NameError: name '_validate_output' is not defined`로 끝났다.

[시험 설계](../../../../docs/ai/TESTING.md)의 D-125·126 검사는 제품 함수 본문과 DB·검사기 대역을 사용하는 오프라인 시험이다. 따라서 채택 기준은 상한·재전송·검사 실패에 대한 기존 관측을 유지하고 실제 출력 처리 경로에 필요한 이름을 연결하는 것이다. SDK·실제 MCP·출력 스키마 전체의 적합성 승인은 별도다. [D-149 결정](../../../../docs/ai/DECISIONS.md)과 [출력 계약 정책](../../../../docs/ai/POLICY.md)을 함께 확인했다.

## Hunk별 판정

행 번호는 후보 `01f17018`의 시험 파일 기준이다. 아래 제품 파일은 후보와 현재 HEAD의 내용이 동일하다.

| hunk | 후보 행·변경 | 판정 | 기대값·검사 범위 및 근거 |
| --- | --- | --- | --- |
| `@@ -4,6 +4,7 @@` | 7행 `import math` | **A** | 표준 라이브러리다. 실제 `output_contract.check_schema_bounds`의 비유한 실수 검사에 필요한 `math.isfinite`를 제공한다. 입력·상한·예상 예외·단언을 바꾸지 않는다. |
| `@@ -13,6 +14,13 @@` | 17–22행 검증자 import 및 `ModuleNotFoundError` 시 세 이름에 `None` | **A** | 설치 환경에서는 실제 `jsonschema`의 `Draft202012Validator`, `validator_for`와 `referencing.Registry`를 사용한다. 누락 환경에서는 기존의 스키마 없는 상한 검사를 계속 실행한다. 새 skip·항상 성공하는 검증자 대역·제품 분기 수정은 없다. `None`은 스키마 검증을 조용히 통과시키지 않는다. 아래 반례 검증 참조. |
| `@@ -36,9 +44,14 @@` | 47–54행 실제 출력 계약 정의·상수 추출, `_validate_output` 선택, 이름공간 연결 | **A** | `_validate_output`, `_guarded_result`, `check_schema_bounds`, `for_protocol` 모두 실제 소스 AST 정의다. 검사 함수를 no-op이나 항상 참인 함수로 교체하지 않는다. 기존 `MAX_RESULT_ITEMS`·`MAX_RESULT_BYTES`, 분류 함수, 검사기 대역과 증거 대역은 그대로다. 정상 반환의 객체 동일성, 초과 응답 거부, UTF-8 경계, 마스킹 후 팽창·검사 실패, 재전송 거부·DB 실패 관측을 유지한다. |

### 실제 정의와 이름공간 추적

- 후보 `selected()` 27–37행은 대상 소스를 읽고 선택된 최상위 함수·클래스·대입 노드만 그대로 컴파일한다. 요구한 이름이 하나라도 없으면 33행에서 실패한다. 미래 타입 주석 처리만 추가하며 함수 본문은 바꾸지 않는다. 이 추출기는 이번 diff에서 변경되지 않았다.
- [core.py](../../../../full_stack_lab/gateway/app/core.py) 1735–1753행의 `_validate_output`을 그대로 선택한다. [output_contract.py](../../../../full_stack_lab/gateway/app/output_contract.py) 10–14행의 프로토콜 집합·자원 상한, 21–57행의 예외·경계 함수, 79–97행의 판본별 변환 함수도 실제 정의다.
- `check_schema_bounds`의 추가 외부 참조는 `math`다. `for_protocol`의 `json`은 함수 안에서 실제 import하므로 별도 주입 누락이 없다. 선택하지 않은 `canonical_hash`, 승인 해시 함수는 이번 선택 함수의 실행 의존성이 아니다. 계약 승인·해시 고정 자체를 이 시험이 검증한다는 뜻은 아니다.
- `_guarded_result` 1763–1769행의 JSON 직렬화·바이트·건수 검사는 검증자 호출보다 앞에 그대로 있다. 1773행에서 실제 `_validate_output`을 호출한 뒤 1774행에서 실제 `for_protocol`을 호출한다. 기존 상한 시험의 인자는 모두 `output_schema=None`이고 payload에는 `structured`가 없어 판본 변환도 원래 payload를 돌려준다. 따라서 새 출력 검사 때문에 상한의 음성 사례가 다른 이유로 거부되어 통과하는 상황은 이 입력들에서 발생하지 않는다.

### `jsonschema` 누락 시 조용한 생략 여부

**누락된 검증자를 검사 없이 성공으로 바꾸는 분기는 없다.** 다만 이 파일은 처음부터 스키마 검증 성공·실패를 검사하지 않는다는 한계가 있다.

1. 스키마가 `None`이면 `_validate_output` 1739–1740행이 반환한다. 이것은 제품의 원래 조건이며 패키지 가용성 분기가 아니다. 기존 시험은 이 경로를 쓴다.
2. 스키마가 있고 `$schema`가 없으면 `Draft202012Validator=None`이다. 1744–1745행에서 `ValueError`가 나고 1751–1753행이 이를 `ResultRejected`로 감싼다. **유효한 결과도 거부되며 통과하지 않는다.**
3. `$schema`가 있으면 `validator_for=None`을 호출하여 `TypeError`가 발생하고 똑같이 `ResultRejected`가 된다. `Registry=None`도 이보다 뒤에서 실행될 뿐 성공 반환을 만들지 못한다.
4. `is_error=true`이고 `structured`가 없는 도구 오류는 스키마가 있어도 1739행에서 반환한다. 이는 설치 환경에도 적용되는 제품의 명시적 예외다. 같은 오류에 `structured`가 있으면 검증하며, 의존성 누락 시 거부된다.

로컬 Python에는 `jsonschema`·`referencing` 둘 다 없었다. 위 조건 1–4를 메모리에서 후보 `guard()`에 직접 입력하여 확인했다. 추가로 `_validate_output` 이름에 호출 시 예외를 내는 표식을 메모리에서만 넣었을 때 `_guarded_result`가 그 예외를 전달해 실제 호출 지점에 도달함을 확인했다.

`except ModuleNotFoundError`는 최상위 패키지뿐 아니라 그 내부 의존성 누락도 잡고 세 이름을 모두 `None`으로 만든다. 따라서 이미지의 패키지 구성이 깨져도 스키마 없는 이 시험 10건만으로는 탐지할 수 없다. 이는 이번 범위에서 허용하는 오프라인 실행 조건이며 **검증자 설치 상태나 D-149 스키마 검증 성공의 증거로 쓰면 안 된다.** 이후 스키마 시험이 이 헬퍼를 재사용할 경우 유효 스키마 양성 사례와 필수 의존성 확인이 필요하다. 거부 사례만 검사하면 의존성 장애를 정상적인 스키마 불일치로 오인할 수 있다.

## 기대값·범위 보존 검증

- 후보 부모·후보·`8983311`의 12개 `test_*` 메서드는 행 속성을 제외한 `ast.dump` 전체가 동일했다. 단언뿐 아니라 입력값·반복·예상 예외·기존 skip 조건까지 같다.
- `ast.Assert`와 `self.assert*` 호출의 합은 각 판본 모두 **38개**다. 후보의 `selected()`·`classifier()`도 부모와 동일하며 변경은 import와 `guard()` 의존성 연결에 한정된다.
- 후보를 메모리에서 실행하고, 제품 AST의 건수 상한 조건만 `False`로 바꾸면 건수 시험이 `ResultRejected not raised`로 실패했다. 바이트 상한 조건만 같은 방식으로 제거하면 UTF-8 경계 시험이 같은 이유로 실패했다. 두 실행 모두 오류 0·실패 1로, 해당 상한 제거를 기존 단언이 계속 탐지했다. 소스 파일은 변경하지 않았다.
- 멱등 시험의 `duplicate`, advisory lock, intent 삽입 횟수, 읽기 반복, DB 실패 기대값은 메서드 전체 동일성으로 보존된다. 실제 PostgreSQL 경합·업스트림 효과를 새로 검증한 것은 아니다.

### 고정한 소스 지문

Git 객체의 UTF-8/LF 본문 SHA-256이다.

| 파일·판본 | SHA-256 |
| --- | --- |
| 시험 파일, 후보 부모 및 `8983311` | `8cf986fc40f9c31569313087fc11fb0c965a4718aca98998891d78c646949eb1` |
| 시험 파일, `luna/cap` | `e7d7b8996ab748213e29fca7a2ffdb894db5e535a3e7a30f3fecb6d0a5f71b0f` |
| `core.py`, HEAD 및 `luna/cap` | `71375a1144bdd7781c84c2fc411872585ed98854e148a8c51983915ec82ffccb` |
| `output_contract.py`, HEAD 및 `luna/cap` | `e849621211b915b8a4079ecb9e93f7be389ae18a1a406af0e48d0559f5c5a0d8` |

## 실행 검증

이 검토에서 실행한 결과다. 후보 보고서에 이미 기재된 과거 Codex sol 검토·실행 주장을 이번 결과의 증거로 재사용하지 않았다. 시험 소스는 `git show`로 읽어 `__file__`을 원래 시험 위치로 지정한 이름공간에 메모리 컴파일했으며, 기존 파일을 덮어쓰지 않았다. 모든 Python 실행은 `-B -X utf8`를 사용했다.

| 검사·환경 | 결과 |
| --- | --- |
| Windows Python 3.10.5, `8983311` 시험 + 같은 판본 `core.py`·`classify.py` AST를 메모리에서 공급 | 총 12건: 10통과·2생략·오류 0·실패 0 |
| 후보 부모 시험 + 현재 제품 AST | 총 12건: 8통과·2생략·오류 2·실패 0. 위 두 시험의 `_validate_output` NameError 재현 |
| 후보 시험 + 현재 제품 AST | 총 12건: 10통과·2생략·오류 0·실패 0 |
| 후보 import에서 검증 패키지 누락을 명시적으로 강제한 메모리 실행 | 총 12건: 10통과·2생략·오류 0·실패 0. 실제 로컬에도 두 패키지가 없어 설치 환경과의 대조는 아님 |
| 의존성 없는 후보에 스키마/도구 오류 조건 6개 직접 입력 | 스키마 없음·구조화 값 없는 도구 오류만 통과, 나머지 4개 거부. `$schema` 유무별 원인 예외도 확인 |
| 검증자 호출 도달 표식·건수/바이트 상한 제거 반례 | 호출 도달, 상한 제거 각각 기존 시험 실패 확인 |
| 3개 판본 시험 AST·제품 Git 객체 지문 대조 | 시험 메서드 12개 동일·단언 38개 동일, 후보와 HEAD 제품 파일 동일 |
| 후보를 임시 복사한 뒤 `python -m py_compile` | 통과. 임시 파일·바이트코드 제거, 작업 트리 시험 파일 변경 없음 |
| `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과 |
| CI와 같은 파일 목록 170개를 확장하여 `python -m pyflakes` 실행 | 환경 제약으로 미완료: `No module named pyflakes`. 새 경고 0은 확인하지 못함 |
| `python research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | 오류 0·경고 119(ignored 원문 누락), 종료 코드 0 |
| 리뷰 파일 인코딩·줄바꿈 | UTF-8 유효, BOM 없음, CR 없음(LF) |

생략된 2건은 기존 조건인 `cryptography` 서명 저장소 fixture와 `pglast` 실제 SQL 문법 검사다. `jsonschema` 선택 import로 새로 생략된 시험은 없다. 첫 보조 실행에서는 설치 환경이라고 잘못 가정한 검토 실행기의 양성 기대가 실패했고, 실제 패키지 부재를 확인하여 부재 환경의 거부 검증으로 정정했다. 설치 환경 양성 결과로 보고하지 않는다.

## 기존 시험 변경 필요 여부와 남은 검증

검토 요청된 **세 hunk는 그대로 채택 가능**하다. 추가 기대값 수정이나 기존 시험 수정은 필요하지 않으며 이번 작업은 실제 채택을 수행하지 않았다. 후보 커밋의 다른 파일 변경에 대한 판정은 포함하지 않는다.

기기 담당자는 채택된 시험 파일이 포함된 게이트웨이 이미지에서 다음을 실행한다. 현재 브랜치의 미수정 시험을 실행하는 명령과 구분해야 한다.

```bash
python -c 'from jsonschema import Draft202012Validator; from jsonschema.validators import validator_for; from referencing import Registry'
python -B -m unittest discover -s tests -p response_cap_idempotency_test.py -v
python -B -m unittest discover -s tests -p output_contract_check.py -v
```

이미지의 필수 의존성과 유효 스키마 양성·불일치 음성은 별도로 확인해야 한다. 게이트웨이 이미지·실제 PostgreSQL·SDK·실제 MCP·PJ1·배포는 이번 검토에서 **미실행**이다. 새 의존성·정책 ID·DB 변경·D-번호는 없다.
