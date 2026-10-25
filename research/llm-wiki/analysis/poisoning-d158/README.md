# DEV-02 계약 오염 정규화 후보와 평가 경계

- 작업일·작업자: 2026-10-20, Codex sol
- 기준: `10/20-poisoning-corpus`, `1c7edc9c7320a4f54ee41e9f058d7d8debd31e20`, 시작 작업 트리 깨끗함.
- 요구사항: 계약 재현율 개선·정상 도구 오탐 0, 기존 분할 유지, dev만 분석·마지막 held-out 1회.
- 결정: [D-158](../../../../docs/ai/decisions/D-151-200.md#d-158-계약-오염-정규화-후보와-held-out-평가-규율-2026-10-20).
- 결과: **구현 후보·로컬 회귀 완료, 공개 코퍼스 수용 판정 대기**. 공개 dev 미탐을 읽지 못했으므로 MCPTox 표현 규칙은 늘리지 않았다. held-out 채점은 0회다.

## 근거와 채택 범위

| 근거 | 판본·라이선스 | 확인·적용 범위와 한계 |
| --- | --- | --- |
| [기존 평가기](../../../../full_stack_lab/tests/inspection_corpus_eval.py), [고정 원문 manifest](../../../../full_stack_lab/tests/inspection_corpus_manifest.json) | 시작 커밋의 파일; MCPTox `f85189f9ad12504c197c7f920ab818a40657b1fa` | 기존 builder·`split_of`를 그대로 호출한다. 원문 SHA-256·바이트 수·URL, 전체 9,463건 및 dev 5,679/held-out 3,784건을 확인한 뒤 평가한다. 원문 캐시 189개가 없어 현재는 평가 불가 |
| [MCPTox 공개 저장소](https://github.com/zhiqiangwang4/MCPTox-Benchmark) | 위 고정 커밋; 기존 기록상 라이선스 파일 없음 | 웹 검색에서 저장소와 2개 커밋의 작은 이력을 확인했다. 이번 원문 다운로드는 `WinError 10013`; 원문·샘플을 재배포하지 않는다. 이전 고정 데이터의 현재 유지보수·라이선스는 새로 검증하지 못함 |
| [기존 AGT 검토](../../../../docs/ai/BENCHMARK_AGT_2026-10-05.md), [현재 공개 규칙](https://github.com/microsoft/agent-governance-toolkit/blob/main/examples/policies/mcp-security.yaml) | 기존 검토 `5233029`, MIT | 기존에 채택한 숨은 주석·base64·전달용 인자 규칙을 유지. 최신 검색에서는 MCP 보안 규칙과 스캐너 경로의 활동을 확인했으나 최신 commit·코드를 채택하지 않음. `you must` 전부 탐지 같은 넓은 표현은 정상 선행 작업과 겹쳐 제외 |
| [공개 스킬 후보 조사 정본](../skill-candidates.json), [새 검색 후보](https://github.com/anthropics/skills/discussions/558) | 정본의 Trail of Bits `e1f86a390d4caf28bf1c377a7d86707b2898669c`, CC-BY-SA-4.0; 새 후보는 제안 게시물 | 기존 자료에서 고정 판본·라이선스·검토 범위를 재사용했다. 새 후보는 게시물 검색만 확인했으며 성능·라이선스·코드 주장은 검증하지 않았다. 외부 스킬 설치·실행·자격 출력·모델 의존성 추가 없음 |
| Python 표준 라이브러리 `codecs`·`re`·문자열 변환 | 검증 인터프리터 CPython 3.12.14, PSF License | 이미 사용하는 정규화 뒤 계약 경로에 해독 4종을 추가한다. 새 런타임 의존성 없음 |

## 변경과 영향 범위

[poisoning.py](../../../../full_stack_lab/gateway/app/poisoning.py)의 `_catalog_variants`는 ROT13, 전체 역순, ASCII 한 글자 사이 공백, `431057 → aeiost`를 별도 읽기로 만든다. 숫자만 있는 토큰은 leetspeak로 바꾸지 않는다. 해독문에 기존 `CATALOG_RULES`를 다시 적용하며 해독 자체를 공격으로 판정하지 않는다. 원문 판정도 남아 기존 탐지의 합집합이다. 반복 해독·변형 조합은 생성하지 않으며 최대 4회 추가 검사다. 입력 크기에 선형인 고정 횟수 작업이지만 전체 카탈로그 검사 지연은 늘어난다.

변경 호출자는 `_scan(..., CATALOG_RULES)` 한 곳이다. `findings()`의 이름·설명·입력 스키마 직렬화에 모두 적용된다. `core.py`의 등록·재검토·목록·실행 전 계약 검토가 이 함수를 공유한다. `text_findings`·`result_findings`에는 새 해독을 적용하지 않는다. 기존 결과 보류의 오탐 비용을 다른 검증 없이 확대하지 않기 위해서다. 계약 적중은 기존 관리자 검토 신호이며 새 정책 ID·인증 경로·DB·감사 기록 갱신·콘솔 변경은 없다.

| 원자 조건 | 코드·시험 심볼(작업 트리 판본) | 확인된 효과·남은 공백 |
| --- | --- | --- |
| 설명·스키마 해독 양성 | `poisoning.py:265 _catalog_variants`, `:276 _scan`, `:321 findings`; 새 시험 `:166 test_encoded_contract_descriptions_and_schemas` | 합성 해독 4종의 설명·중첩 스키마에서 기존 `지시 무시` 라벨 확인; 공개 dev 효과 미검증 |
| 정상·범위 음성 | 새 시험 `:176 test_normal_catalogs`, `:182 test_result_and_argument_scope_unchanged`, `:94 evaluate(local)` | 합성 정상과 실제 OSS 스키마 92개 FP 0; 인자/결과의 추가 해독 0; 운영 3종은 미검증 |
| 경계 | 새 시험 `:189 test_bounded_normalization`, 기존 `poisoning.py` 자체 점검 | 긴 입력의 변형 수 ≤4·각 길이 ≤원문, 기존 병리 입력 시간 제한 통과; 네이티브 지연 미검증 |
| 검사기·원문 실패 | 새 시험 `:195 test_metrics_and_scanner_failure`, `:215 test_missing_cache_fails_before_scoring`, `:220 test_tampered_source_fails_before_scoring` | 예외를 성공으로 세지 않음; 캐시 누락·해시 불일치 거부 |
| 경쟁·재사용·복구 경계 | `:78 consume_held_out`, `:204 test_held_out_is_frozen_and_one_use`, `:232 test_held_out_receipt_race` | 지문 변경 거부, 동시 2개 중 1개만 기록 획득, 재사용 거부; 실제 채점 중 프로세스 강제 종료·기기 파일시스템 복구는 미검증 |

행은 [제품 파일](../../../../full_stack_lab/gateway/app/poisoning.py)과 [새 시험](../../../../full_stack_lab/tests/poisoning_corpus_check.py)의 현재 소스 기준이며 최종 SHA-256은 [검증 실행 기록](validation.json)에 보존한다. 판정은 정책 차단이 아닌 검사 라벨 수준이므로 실제 모델·정책 ID·업스트림 효과를 대신하지 않는다.

## 공개 코퍼스 전후 수치

아래 이전값은 [10-15 측정 JSON](../../status/reports/2026-10-15-inspection-corpus-results.json)의 `totals_after`에서 인용한 **과거 관측값**이다. 이번 기준 재실행값으로 세지 않는다. 현재 비교 평가 명령은 원문 파일 누락으로 실패했고 결과 파일을 만들지 않았다.

| 계약(MCPTox) 분할 | 과거 TP/FN/FP/TN | 과거 재현율 | 과거 정밀도 | 이번 기준·개선 후 재현율/정밀도/오탐 |
| --- | --- | --- | --- | --- |
| dev | 152/136/0/197 | 0.5278 | 1.0000 | 모두 미측정 |
| held-out | 102/95/0/145 | 0.5178 | 1.0000 | 모두 미측정(채점 0회) |
| 전체 | 254/231/0/342 | 0.5237 | 1.0000 | 모두 미측정 |

## 로컬 측정

[재생성 가능한 로컬 결과 JSON](local-results.json). 같은 작성자의 합성 회귀 4개 공격·28개 정상이며 독립 코퍼스·공개 dev·held-out에 포함하지 않는다. 정밀도 분모가 0인 경우 `—`다.

| 합성 유형 | TP/FN(전→후) | 재현율(전→후) | 정밀도(전→후) | 정상 오탐(전→후) |
| --- | --- | --- | --- | --- |
| ROT13 | 0/1 → 1/0 | 0 → 1 | — → 1 | 0/7 → 0/7 |
| 역순 | 0/1 → 1/0 | 0 → 1 | — → 1 | 0/7 → 0/7 |
| 글자 띄우기 | 0/1 → 1/0 | 0 → 1 | — → 1 | 0/7 → 0/7 |
| leetspeak | 0/1 → 1/0 | 0 → 1 | — → 1 | 0/7 → 0/7 |

[실제 OSS 도구 스키마 저장소 사본](../local-tools/tool-capabilities.json)의 ghidra 28·git 28·sqlite 2·blender 9·playwright 25개, 합계 92개의 오탐은 0→0이다. 스냅샷 SHA-256은 `e86eb416fe87acae3d12e261d15fb3d6815003ecd9405599f9655aed467842b8`. `inputSchema`를 제품 입력 키 `input_schema`로 옮겨 설명과 전체 스키마를 검사했다. github·context7·markitdown은 이름·계약 해시만 발견했고 실제 설명·스키마 사본은 발견하지 못했다. 이 92개를 요청된 3종의 대리 검증으로 세지 않는다.

## 실패 유형과 한계

| 구분 | 현재 근거·처리 | 남은 검증 |
| --- | --- | --- |
| 해독하면 기존 지시 무시 패턴이 드러나는 4종 | 합성 회귀에서 전후 차이 확인 | 공개 dev의 해당 유형별 실제 빈도·재현율 |
| 정상 도구의 선행 탐색·업무 호출 안내 | 광범위한 `must/call/before` 규칙 추가하지 않음; 기존 자체 점검 유지 | MCPTox dev의 136개 과거 미탐을 읽고 도구 의존 관계와 오염을 구별 |
| 다국어 의역·설득·명시적 패턴 없는 행동 변경 | 이번 변경으로 해결되지 않음 | 독립 한국어 자료·의미 분류기는 DEV-02/DEV-46 후속; 외부 모델 호출 없음 |
| 조합 인코딩·숫자 `1`의 `l` 해석·비ASCII 글자 띄우기 | 해독을 1층·4종으로 제한 | 별도 정상군·성능 검증 후 확대 판단 |
| 이전 112/182 및 잔여 70/182 | 결과 경로의 과거 측정으로 보존 | 이번 해독은 계약 전용이므로 결과 경로 수치 개선을 주장하지 않음; 공개 26시드 재평가 필요 |
| 실패 시 차단 | 평가 원문 누락·해시 불일치·검사기 예외는 실패 종료; 결과 파일을 성공으로 생성하지 않음 | 네이티브 엔진 동등성·솔루션 이미지·실제 MCP·PJ1 미실행 |

## 재현 순서(솔루션 기기)

저장소 루트에서 기준 파일을 만든다. 아래 `<repo>`는 이 브랜치가 반영된 솔루션 기기 작업 트리다. `.corpus-cache`는 Git 제외다. 기준 파일은 위 시작 커밋의 SHA-256 `bb63b3094567f96315bd302c996fe3fbecf0e608f080874ea1a0a19e9857dc96`과 일치해야 한다.

```bash
mkdir -p full_stack_lab/tests/.corpus-cache
git show 1c7edc9c7320a4f54ee41e9f058d7d8debd31e20:full_stack_lab/gateway/app/poisoning.py > full_stack_lab/tests/.corpus-cache/poisoning-before-d158.py
cd full_stack_lab
# 원문 캐시를 복원하거나, PyYAML이 있는 기존 평가 환경에서 확보한다.
python tests/inspection_corpus_eval.py build --out tests/.corpus-cache/samples.jsonl
# Python 3.12 이상 및 기존 의존성을 갖춘 환경에서 실행한다.
python tests/poisoning_corpus_check.py
python tests/poisoning_corpus_check.py --evaluate local --baseline tests/.corpus-cache/poisoning-before-d158.py --output tests/.corpus-cache/local-review.json
python tests/poisoning_corpus_check.py --evaluate dev --baseline tests/.corpus-cache/poisoning-before-d158.py --output tests/.corpus-cache/dev.json --show-misses
```

`build`는 PyYAML이 필요하고 네트워크 다운로드를 한다. 새 비교기는 네트워크·manifest 변경 없이 모든 원문을 검증해 기존 builder로 다시 만들며 JSONL 임의 교체를 허용하지 않는다. dev 미탐의 원문·탐지 유형·해시만 출력할 수 있다. dev에서 규칙을 고치면 최종 dev 보고서를 새 이름으로 만들고, 그 뒤 코드·시험·원문·Python 판본·검사 엔진을 동결한다. 실제 3종 정상 카탈로그도 이 단계에서 검사한다.

**위 검토가 끝난 후 마지막에만** 다음 명령을 실행한다. 이번 작업에서는 실행하지 않았다.

```bash
python tests/poisoning_corpus_check.py --evaluate held-out --baseline tests/.corpus-cache/poisoning-before-d158.py --dev-report tests/.corpus-cache/dev.json --output tests/.corpus-cache/held-out.json
```

dev 보고서의 코드·시험·builder·원문 manifest·샘플·엔진 지문과 현재값이 다르거나 dev 오탐이 0이 아니거나 재현율 증가가 없으면 실패한다. 채점 전에 `dev.held-out-once.json`을 배타 생성·fsync하고, 같은 dev 보고서의 재채점과 기존 결과 덮어쓰기를 거부한다. 실패해도 기록을 지우지 않는다. 운영자가 보고서를 복제하거나 기록을 지우면 우회 가능한 절차 통제이므로 독립 평가자가 원본 실행 기록을 보존해야 한다. held-out은 집계만 출력하고 미탐 문장·개별 판정을 내보내지 않는다.

게이트웨이 이미지에서는 `gateway /tests/poisoning_corpus_check.py`와 기존 `gateway /tests/textscan_parity_check.py`를 실행한다(`tests`를 읽기 전용 `/tests`로 마운트). 전체 비교 평가에는 Python·PyYAML·기존 app/textscan 및 cache 접근이 모두 필요하다. 새 평가기를 위해 게이트웨이 런타임 의존성을 추가하지 않는다.
