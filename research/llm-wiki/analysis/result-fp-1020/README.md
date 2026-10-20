# 결과 경로 오탐 조사 (2026-10-20)

## 기준과 재현

- 공개 코퍼스 표본은 사용자 제공 임시 JSONL에서 읽기만 했다. 원문은 저장소에 복사하지 않았다. `evaluate.py`는 `core._guarded_result`, `classify.result_items`, 결과 독성 규칙을 AST로 분리해 직접 호출하고 집계 JSON만 쓴다. Python 3.10에서 게이트웨이 의존성·네이티브 스캐너 import가 불가해 표준 `re` 기반으로 적용했다.
- 시작: `dffff32`, 브랜치 `10/20-result-fp`; 표본 SHA-256은 집계 JSON에 기록한다. `baseline-dev.json`은 수정 전, `after-dev.json`은 수정 후 dev 결과다.
- 재현: `python -X utf8 research/llm-wiki/analysis/result-fp-1020/evaluate.py <임시 corpus-samples.jsonl> --split dev`.
- `--split held-out`은 제품 코드·회귀·dev 분석을 동결한 뒤 딱 한 번 실행한다. 원문, 개별 예측, 문맥 조각은 출력하지 않는다.

## 원인 분류

수정 전 dev의 1,194개 정상 표본 가운데 37개가 보류됐다. 34개는 `MAX_RESULT_ITEMS=1000` 초과, 3개는 `OVERRIDE_RULES` 적중이다. 평가기는 보류 이유를 하나의 `size`로 합쳐 상한 보류를 오탐에 포함했다. `00db46e`(D-125)가 `classify.result_items`의 JSON 텍스트 해석과 일반 텍스트 줄 수 대체를 넣었다. BOM이 붙은 pretty JSON은 JSON 파싱이 실패해 들여쓰기 줄을 항목 수로 세는 결함이 확인됐다. D-149 출력 계약은 이 표본의 `structured` 경로가 없어 원인이 아니다. 디코딩·줄바꿈 독성 검사는 별도 규칙 경로이고 BOM 접두만으로 적중하지 않는다.

수정은 `result_items`가 검사 복사본에서 텍스트 맨 앞의 BOM 하나를 제거하고 JSON을 읽게 한다. 원래 응답은 바꾸지 않는다. BOM 제거 뒤에도 실제 배열이 1,000건을 넘으면 보류한다. 바이트 상한, 일반 텍스트 줄 수 상한, 규칙 임계값은 그대로다. 그 결과 dev에서 상한 보류 34→31, 규칙 적중 3→3, 공격 재현율 0.3105→0.3105였다. 코드 동결 후 held-out은 한 번 실행해 31/801이 항목 상한 보류, 규칙 적중 0, 공격 재현율 0.307081이었다. 두 분할 합계는 상한 보류 62, 규칙 적중 3, 정상 65/1,995 보류, 상한 보류 제외 규칙 오탐률 0.15%다. 기존 보고의 66건과 raw 차단 건수는 65건이다. 기준 held-out 분할별 결과는 당시 보존되지 않아 분할별 전후 차이는 주장하지 않는다. 3개 규칙 적중은 OWASP 보안 문서의 공격 예시 문장이다. 문맥 분류로 완화하면 같은 표현의 실제 주입을 통과시킬 위험이 있어 유지했다.

## 요구사항 연결과 한계

| 요구 | 코드·근거 | 확인 범위 |
| --- | --- | --- |
| BOM 포함 JSON을 항목 수대로 계산 | `gateway/app/classify.py:result_items`; D-125, `00db46e` | AST 직접 호출, dev 공개 코퍼스 |
| 실제 항목 상한 유지 | `gateway/app/core.py:_guarded_result`, `classify.result_items` | 합성 회귀와 dev 집계; 솔루션 기기에서 신규 시험 필요 |
| BOM으로 주입 검사 우회 금지 | `gateway/app/poisoning.py:INVISIBLE_TEXT`, `_variants`; D-52 | 합성 회귀 예정; 실제 하네스·기기 미실행 |
| 표본 원문 비저장 | `evaluate.py` 집계 경로 | 집계 JSON에 원문 없음 |

수정 전/후 raw blocked 건수와 의도된 cap hold를 분리한다. cap hold는 시스템 한계에 따른 응답 보류로 별도 집계하며 오탐률 분자에서 제외한다. OWASP 문서의 3개 규칙 적중은 남은 평가 오탐이며, 이 작업에서는 규칙을 좁히지 않는다. Python 3.10 표준 정규식은 이미지의 native scanner와 독립 동등성 증명이 아니며, 게이트웨이 이미지·실제 OSS MCP·Claude/Codex 하네스 효과는 미확인이다. `after-held-out-once.json`의 held-out 채점은 같은 코드 지문으로 한 번만 수행했다.
