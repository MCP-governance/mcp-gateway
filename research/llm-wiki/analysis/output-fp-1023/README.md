# Cloudflare 문서 응답 보류 조사

**후속 정정(D-198)**: 리더가 906·919·868의 오류 원문을 제공하여 [후속 분석](followup.md)과
[추가 요구·시험 정본](followup-requirements.json)을 추가했다. 소수 점수 오탐·문서 예시 전체 보류·공용 executor
경합은 합성 오프라인 재현 후 `privacy.py`·`secret_scan.py`를 수정했다. 실제 세 원장의 원문/배포 계약 재생과
919 당시의 원인 확정은 미완료다. 아래 D-197의 **미수정** 판단은 상세 오류를 받기 전의 이력이다.

## 초기 조사 (D-197, 오류 원문 제공 전)

기준: `0f57d0c9c0994faf849544616c6e66939b113fd8`, 작업 `W13-OUTPUT-FP`, 결정 D-197.
결함은 **미해결**이다. 원장 906의 제공된 preview는 `ResultRejected` 처리 경로와 맞지만,
해당 응답이 어떤 검사에서 실패했는지는 보존된 preview만으로 특정할 수 없다.
제품 통제 코드·계약 잠금·승인 해시는 수정하지 않았다.

## 확인한 계약과 확인하지 못한 계약

- `full_stack_lab/registry/contracts.lock.json`: 기본 카탈로그 계약이며 대상 등록 ID가 없다.
- `full_stack_lab/registry/field/contracts.lock.json`: `{"servers":{}}`. field 카탈로그에도 대상이 없다.
- `compose.field.yaml:79,89`: 컨테이너 `/registry-field`는 `./registry/field`의 마운트다.
- Console 등록은 별도로 `registry.py:13,35`의 `REGISTRY_RUNTIME_DIR/servers.json`에서 읽는다.
  **대상 등록의 이 파일과 실 DB `mcp_tools.approved_output_schema_hash`는 이 체크아웃에 없다.**
  같은 이름의 과거 `analysis/real-env-20261020/install/servers.json`은 로컬 MCP 설치 목록으로 대상이 없다.
- 재사용한 실제 10-20 도구 목록: [t4-catalog-remote.jsonl](../real-env-20261020/t4/t4-catalog-remote.jsonl):4.
  파일 SHA-256 `6b02227f6253830c001544e371183bc47d7926dbffe85e0144e965a987decb84`.
  `outputSchema`의 MINT 정규 해시는 `ada291be066eeac1c38e667407442f5dcca58f74ec2233ab673de135adb1c44b`.
  **이는 관찰한 과거 스키마의 계산값이며 승인 해시가 아니다.**

관찰한 스키마는 최상위 객체 `results`(필수 배열), 각 원소는 `similarity`(number), `url`·`title`·`text`(string)를
모두 요구한다. 최상위와 원소의 추가 속성은 불허한다. `{"results":[...]}`는 맞고,
최상위 배열·문자열·`{"data":...}`·누락 필드·문자열 점수·추가 속성은 맞지 않는다.

## 출력 통제 분기 전수 대조

아래 행은 모두 기준 commit의 `full_stack_lab/gateway/app/` 기준이다. 배포 판본은 이번에 확인하지 않았다.

| 코드 | 조건 → 결과 | 원장 906 preview로 판별 가능한 범위 |
| --- | --- | --- |
| `upstream.py:323`, `core.py:1871` | SDK wire 형식 위반 → `MCP-OUTPUT-001` | 이 경로는 disposition만 기록한다. 제공된 bytes/structured/types 및 일반 보류 문구는 `core.py:2535` 경로와 맞는다. |
| `core.py:1928` | JSON 직렬화 실패 → `ResultRejected` | payload 없는 예외이므로 이 분기 단독으로 상세 preview가 생기지 않는다. |
| `core.py:1932` | 직렬화 결과가 `MAX_RESULT_BYTES` 초과 | 기본 262144라면 68688은 이 원문 크기 분기에 해당하지 않는다. 실제 배포 환경값은 미확인이다. |
| `core.py:1934`, `classify.py:572` | `MAX_RESULT_ITEMS` 초과 | 배열 원소와 문서의 비어 있지 않은 줄도 센다. bytes만으로 배제할 수 없다. 기본 1000. |
| `core.py:1936` | content가 배열이 아니거나 원소가 객체가 아님 | preview는 content 전체 형식·원소 유효성을 보증하지 않는다. |
| `core.py:1905–1919,1939` | 승인 출력 스키마와 structured 불일치·누락, 미지원 dialect, 잘못된/과도한 schema, 해석 불가 참조 | 유력 후보지만 preview의 structured=true는 키 존재만 뜻한다. 값·타입·필드 일치는 미확인이다. |
| `core.py:1942,1944` | text 외 블록 또는 문자열 text 없음 | `[text]`만으로 문자열 본문 누락까지 배제할 수 없다. |
| `core.py:1946–1949`, `poisoning.py:57,301` | 직렬화 본문과 디코딩한 키·문자열에서 오염 규칙 적중 | 스키마가 맞는 문서도 이 분기에서 보류된다. 조회가 정상이라는 사실은 반환된 문서의 규칙 적중 여부를 말하지 않는다. |
| `privacy.py:110–150,153–170`, `core.py:2507–2511` | 분석기·마스킹기 장애/잘못된 반환/마스킹 잔여 → `InspectionUnavailable`을 `ResultRejected`로 변환 | 같은 상세 preview를 만든다. `outcome.policy`가 통제 장애 차단인지 함께 볼 수 있다. |
| `privacy.py:173–195` | 키/숫자의 PII 또는 구조화 대입 문맥의 자격 검출 | 스키마를 바꾸지 못하므로 보류. 같은 상세 preview를 만든다. |
| `core.py:1956,1966`, `secret_scan.py:labels` | 전체 출력 검사 30초 또는 Gitleaks 5초 초과·검사기 실패 | 출력 검사 실패로 보류. 같은 상세 preview를 만든다. |
| `core.py:1960` | 마스킹 후 Gitleaks 잔여 | `ResultRejected`. 같은 상세 preview를 만든다. |
| `core.py:1963` | 마스킹 후 bytes/items 상한 초과 | 변환 후 크기이므로 원문 preview만으로 배제할 수 없다. |
| `core.py:2504–2506` | 마스킹 후 계약 재검증, 클라이언트 판본 변환 후 guard 재검사 | 마스킹이 정상이어도 계약 불일치는 차단. 판본 변환 후 크기·건수·오염도 다시 검사한다. |
| `core.py:2535–2544` | 위 `ResultRejected` 공통 처리 | `Block/MCP-OUTPUT-001`, 실행됨, 결과 없음, `exc.evidence`가 result_preview가 된다. |

`core.py:129–134,143–154`에서 **모든 `ResultRejected`의 masked_types는 기본 빈 배열**이다.
따라서 `masked_types: []`는 마스킹 시도 없음·PII 없음·Secret 없음·검사기 정상의 증거가 아니다.
`structured: true`도 객체라는 뜻이 아니라 `structured` 키 존재만 뜻한다.
스키마 불일치, 오염 적중, Secret 잔여가 **똑같은 68688-byte preview**를 만드는 새 반례를 확인했다.

반대로 승인 해시와 실행 직전 도구 목록의 스키마 해시가 다르면 `core.py:1672–1684`에서 **실행 전에
`MCP-CATALOG-001`**이다. 그 해시 드리프트 자체를 원장 906의 출력 차단 원인으로 단정할 수 없다.
`output_contract.py:66–76`은 NULL 옛 승인을 관찰값으로 자동 고정하지 않는다.
`core.py:1799–1800`은 승인 해시가 있는 경우에만 일치 확인한 schema를 결과 검사에 넘긴다.
`output_contract.py:79–97`의 판본 변환은 계약 검증 뒤에 수행한다.

## 원자 요구사항과 시험

[구조화 정본](requirements.json), [신규 시험](../../../../full_stack_lab/tests/cloudflare_output_fp_check.py).
새 9개 시험은 과거 실제 도구 목록의 스키마와 **합성 결과·분석/Secret 검사 I/O 대역**을 사용한다.
실제 MCP·원장 906 재생·네이티브 Gitleaks·Presidio 실행 증거가 아니다.

- 정상: 고정 해시 일치, 68688-byte 정상 results 객체, 객체 판본 2종·최신 JSON 판본, facade까지 반환.
- 음성/경계: 구조 불일치 5종, 오염 지시, Secret 잔여, 이미지, bytes/문서 줄 수 상한+1 모두 보류 유지.
  bytes와 문서 줄 수 각각 정확한 상한은 통과한다. 68688-byte 정상 스키마도 1001줄이면 같은 preview로 보류된다.
- 실패/복구: 분석 서비스 실패 전파, 정상 검사 응답의 반환 경로. 실제 서비스 재시작·경쟁은 미실행.
- 마스킹 후 재검증: 바뀐 구조 값이 계약과 어긋나면 보류 유지.

## 공식 자료와 한계

[MCP 2025-11-25 tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)는
outputSchema가 있을 때 structuredContent를 그 스키마에 맞춰 반환하도록 정한다.
이 원칙에 따라 스키마 추론·wrapper 자동 삽입·스키마 검사 생략은 채택하지 않았다.

Cloudflare 공개 저장소의 [도구 구현](https://github.com/cloudflare/mcp-server-cloudflare/blob/main/packages/mcp-common/src/shared-tools/docs-ai-search.tools.ts)
50–72행을 읽었다. 문서 텍스트와 results 객체를 함께 반환하는 구성은 과거 관찰 스키마와 부합한다.
[파일 이력의 commit](https://github.com/cloudflare/mcp-server-cloudflare/commit/1df6213519c030436ae10f0ed1f0332507b81dce)은
2026-07-28 SDK v2 이전 기록이고, 저장소 [라이선스](https://github.com/cloudflare/mcp-server-cloudflare/blob/main/LICENSE)는 Apache-2.0이다.
main 소스는 가변이며 commit 고정 raw URL 확보는 실패했다. **고정 commit의 파일 본문·원격 운영 배포와의 동일성은 미확인**이다.
소스/스크립트를 복제·실행하거나 새 의존성을 추가하지 않았다. 새 기능 도입이 아닌 기존 통제의 좁은 결함 조사다.

## 원장 906 확정에 필요한 증거

리더가 기존 권한으로 원장 906의 `error`, `outcome`, `timings`, `client.upstream_protocol_version`,
`result_preview`, 당시 배포 revision·출력 상한, 대상 도구의 `approved_output_schema_hash`·`observed_output_schema_hash`·
`output_schema` 및 런타임 등록의 계약을 **자격 값 없이** 대조해야 한다.
`error`가 남아 있으면 위 고정 문구로 검사 분기를 좁힐 수 있다. `error`가 `[REDACTED]`라면
그 문자열도 원래 오류 내용을 확정하는 증거가 아니며, 허용된 재시험에서 검사 분기 증거가 필요하다.
원장에는 withheld 본문을 저장하지 않으므로 과거 원문 복구를 약속할 수 없다.
