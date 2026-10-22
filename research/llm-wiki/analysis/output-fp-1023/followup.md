# W13 후속: 출력 검사 오탐과 실행 경합

기준 `0f57d0c9c0994faf849544616c6e66939b113fd8`, 같은 `10/23-output-fp`, D-198.
리더의 10-23 02:30 오류 제공으로 D-197의 원인 범위를 갱신한다. **실제 원장의 원문 재생은 아니다.**
[추가 요구 정본](followup-requirements.json), [수정 전 재현](followup-before.json),
[검사 결과](followup-checks.json), [누적 보고](../../status/reports/2026-10-23-output-fp.md).

## 원인·수정·남은 불확실성

| 원장 | 제공된 오류 → 확인한 로컬 결함 | 변경·증거 | 실제 사건과의 연결 한계 |
| --- | --- | --- | --- |
| 906, Cloudflare 68688B | keys/numbers 보류. `0.9901013123456`의 소수부가 `KR_RRN`과 일치한다. | `privacy.mask_payload:203`의 JSON 숫자 토큰 위치와 분석 offset을 대조해 `(-1,1)` 내부 숫자형 식별자 부분 일치만 제외. 68688B results 결과·스키마 보존 통과. | 당시 similarity 값·원문·배포 계약 미확보. 이 값이 실제 906에 있었다고 단정하지 않는다. |
| 868, MarkItDown 16094B | 합성 `키=본문`의 본문 안 `api_key: <your-key>`를 발견하면 결과 전체를 보류했다. | `privacy.mask_payload:183`에서 발견 시작점이 실제 key prefix를 가로지르는지 확인. 문자열 안 발견은 leaf 마스킹. `analyze:125`는 완전 일치하는 유한 placeholder만 CREDENTIAL에서 제외. | 실제 문서의 정확한 예시 문자열 미확보. 합성 형식 기반이다. |
| 919, filesystem 51456B | `secret_scan.labels:78`의 `to_thread` 공용 executor 대기도 5초에 포함되어, 검사가 실행되기 전 실패 가능. | `secret_scan.py:30,87`의 전용 4-thread executor. 공용 풀 1개를 점유하고 51456B 문서를 검사한 시험은 수정 전 같은 일반 오류, 수정 후 통과. | 실제 네이티브 엔진의 실행·초기화 시간과 배포 판본이 없다. **당시 원인 확정은 미완료.** |
| 888, MarkItDown 279610B | 기본 상한 262144B 초과. | 크기·건수·계약·오염 검사와 개별/전체 검사 기한 변경 없음. 새 크기 차단 시험 통과. | 설계 동작으로 유지. |

소수 예외는 JSON 숫자 토큰에 완전히 포함된 **숫자형 개인정보** 발견에만 적용한다. 문자열의 숫자·JSON 키,
`9901013123456` 및 `9901013123456.0`은 계속 가림/보류한다. JSON 숫자로 변형해 소수부에 식별자를 담는
우회는 이 수치 판정의 경계다. 문자열·키의 위장이나 일반 자격증명을 이 예외로 허용하지 않는다.

placeholder는 `<your-key>`, `<YOUR_API_KEY>`, `YOUR_API_KEY_HERE` 같은 유한 문법의 **완전 일치**만이다.
뒤에 토큰·개인정보·추가 문자열이 붙으면 CREDENTIAL 제외에 해당하지 않는다. 다른 SECRET_TOKEN·PII 발견은
같은 문자열 안에서도 유지하며 최종 Gitleaks는 가린 JSON과 디코딩 문자열 모두 검사한다.

## 919 실패 조건 전수 대조

- `scan_text:64`: URL 파싱/인코딩의 ValueError도 같은 오류가 된다. 고정 Python SDK 자료의 Markdown URL
  1866개에서 `urlsplit` 오류는 0개였다. 이는 실제 5개 문서 전체와 동일하다는 증거가 아니다.
- `_engine:34`·`rule_ids:46`: 라이브러리 로드/심볼 실패, null pointer, 잘못된 JSON/규칙 목록, 엔진 error는 차단이다.
  이번 OSError·ValueError 주입 시험과 최종 판정에서 결과가 보류된다. 실제 Linux `.so`는 실행하지 않았다.
- `labels:78`: 수정 전 공용 풀 대기 + 콜드 초기화 + 네이티브 처리에 Python 5초가 걸린다.
  자체 슬롯 획득 대기는 이 5초 밖이며 `core._inspected_result:1953`의 전체 30초 안이다.
  전용 풀은 **다른 작업과의 큐 경쟁만** 제거한다. 기한 증가는 없다.
- 네이티브 `main.go:68`의 `setup.Do(load)`는 Go의 5초 context 생성 전이다. Python 5초와 Go 5초는
  독립 제한이며 초기화·스케줄링도 Python 시간에 포함된다. 콜드 시작의 실제 비용은 미측정이다.
- 현 경로는 subprocess·stdin 임시 보고서·임시 디렉터리를 쓰지 않는다. `MaxArchiveDepth=0`,
  `sources.File{Content: bytes.NewReader(data)}`다. 현재 소스에서 임시 파일 장애를 원인으로 볼 근거가 없다.
- 취소/시간 초과 뒤 스레드는 중단되지 않는다. `shield`·완료 callback으로 종료 때까지 슬롯을 점유하며,
  다섯 번째 호출 대기, 실행 중 취소, 대기 중 취소, 복구와 제출 실패의 슬롯 반환을 확인했다.
- 오류 문구는 여전히 여러 실패를 합친다. 기존 오류 원문 하나로 919의 네이티브 시간 초과·로드 실패·공용 큐
  경합을 구분할 수 없다. 당시 검사 실행 근거와 원장/배포 판본 대조가 필요하다.

## 외부 자료·OSS·공개 스킬 검토

기존 [의존성 분석](../oss-deep/deps-presidio-gitleaks.md)과 [스킬 카탈로그](../skill-candidates.json)를
먼저 확인했다. 새 의존성·MCP 구현·외부 스킬 설치는 없다. 아래 자료의 해시는 [검사 결과](followup-checks.json)에 둔다.

| 자료 | 고정 판본·라이선스·읽은 범위 | 유지보수/적용 범위·한계 |
| --- | --- | --- |
| Gitleaks | commit `83d9cd684c87d95d656c1458ef04895a7f1cbd8e`, v8.30.1, MIT. `sources/file.go`·LICENSE와 우리 Go 바인딩/lock 대조. [고정 소스](https://github.com/gitleaks/gitleaks/blob/83d9cd684c87d95d656c1458ef04895a7f1cbd8e/sources/file.go) | 기존 의존성 유지. 고정 commit 2026-03-12, 현재 upstream HEAD/배포 동일성 미확인. 직접 실행 없음. |
| Presidio | commit `779dbd286d5ef4d1fbe2514275fb1bce358f2417`, 2.2.364, MIT. 기존 분석과 로컬 LICENSE/commit, HTTP 경계 대조. | 고정 commit 2026-07-22. 우리 요청의 ad-hoc 정규식만 오프라인 HTTP 대역에서 적용. 실제 NLP·기본 recognizer·서비스 지연 미검증. |
| MCP Python SDK | 로컬 commit `9972c21aa42054fb1450c5fc614761ed11847ec6`, MIT. Markdown URL 구문·LICENSE 확인. | 고정 commit 2026-09-07. 실제 919의 5문서 식별/동일성은 미확인. 코드 실행 없음. |
| Python asyncio | [공식 executor API](https://docs.python.org/3.12/library/asyncio-eventloop.html#executing-code-in-thread-or-process-pools) | 공용 풀과 명시적 ThreadPoolExecutor의 차이를 적용. 새 패키지 대신 표준 라이브러리 사용. |
| OWASP 공개 secrets-scan play 후보 | [공개 파일](https://github.com/OWASP/secure-agent-playbook/blob/main/plugins/code-security-skills/plays/secrets-scan.md) 검색 결과·저장소 메타데이터 검토 | commit·파일별 라이선스·유지보수 이력은 미확보. 검증 불충분으로 채택/설치/실행하지 않음. 기존 제품의 내장 Gitleaks를 유지. |

외부 전문은 재배포하지 않고 URL·자체 분석·로컬 파일 hash만 기록한다. 기존 의존성 분석 중
`rule_ids`의 null pointer 검증이 없다는 문장은 현재 `secret_scan.py:50`과 맞지 않는다. 이번에는 null을
검증하는 실제 코드를 기준으로 보았으며 과거 분석을 메모리 오류 재현 증거로 사용하지 않았다.

## 시험과 재현 범위

새 시험은 [output_inspection_fp_check.py](../../../../full_stack_lab/tests/output_inspection_fp_check.py) 15건이다.
정상/음성/경계/실패/경쟁/복구를 포함한다. 정상 문서 및 실제 형식의 합성 토큰/이메일을 포함한 문서는
최종 `Allow/P-AUTHZ-ALLOW-001`과 민감 값 제거를, 검사 오류·잔여 Secret은 `Block/MCP-OUTPUT-001`과
`upstream_executed=True`, `result=None`, `disposition=withheld`를 단언한다.
HTTP는 생산 ad-hoc 정규식 중 Python re로 실행 가능한 부분만 적용하는 대역이고 네이티브 검사 결과도 대역이다.
검사 서비스의 탐지율·실제 처리 시간·OSS MCP 실행 증거로 세지 않는다.

수정 전 증거는 별도 Python 프로세스에서 `git show HEAD:…/privacy.py`와 `secret_scan.py`를
기존 모듈 namespace에만 compile/exec하고 새 시험의 네 가지 원인 재현 항목만 실행했다.
작업 파일·Git 상태는 바꾸지 않았다. 네 항목 모두 예상 오류가 발생했으며 원문은 `followup-before.json`에 보존한다.
기존 시험과 기대값은 변경하지 않았다.
