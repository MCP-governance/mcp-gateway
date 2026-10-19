# S7 / DEV-44 출력 계약 적대 검증

- 대상: `10/20-output-contract-review`, 시작 HEAD `3ea141c239080bbd83f8e49911d2c8983d98ffe1` (Codex sol)
- 결정 기준: D-149, `analysis/output-contract-d149/README.md`, `status/reports/2026-10-20-output-contract.md`
- 검토 범위: 출력 스키마 승인 전환, 결과 검증, MCP 판본 호환, 최종 dispatch 재확인, HEAD가 바꾼 기존 시험 4개

## 기존 시험 변경 판정

| 시험 파일 | 판정 | 근거 |
| --- | --- | --- |
| `full_stack_lab/tests/catalog_refresh_check.py` | A — 채택 | 새 `output_schema` 관측 UPDATE를 대역 상태에 저장하고 재승인 SQL에서 관측 해시를 승인 해시로 옮긴다. 기존 drift/rollback 기대값 삭제·완화는 없다. |
| `full_stack_lab/tests/contracts_check.py` | A — 채택 | 레거시 lock의 출력 해시 부재를 canonical null과 동등 처리하고, 추가·변경된 출력 해시는 diff에 나타낸다. 종전 입력 설명/스키마 비교는 유지한다. |
| `full_stack_lab/tests/dispatch_recheck_check.py` | A — 채택 | 새 모듈, 등록부 재검토, `_guarded_result` 인자를 대역에 추가했다. 기존 판정·전송 기대값을 바꾸지 않았다. |
| `full_stack_lab/tests/selective_restriction_siem_check.py` | B — 수정 후 채택 | HEAD 변경은 출력 스키마 관측을 대역에 저장하지만, 버전 승격 대역의 기존 조건은 설명·입력 해시만 비교했다. 운영 SQL과 같게 승인·관측 출력 해시 조건도 추가했다. 기대값 완화는 없었다. |

## 적대 경로 결과

1. **기존 승인 도구 전환:** `output_contract.approved_hash`는 옛 승인 해시 부재를 출력 스키마 부재의 canonical hash로 해석한다. 따라서 outputSchema를 광고하지 않는 기존 도구는 배포만으로 재승인 대기가 되지 않는다. 실제 Context7·GitHub·MarkItDown의 광고 부재는 Codex sol의 현장 확인을 인용한 것이며 이 검토에서는 재측정하지 않았다.
2. **검증 우회와 자원 고갈:** 외부 `$ref`는 네트워크 resolver가 없는 `Registry()`에서 해석되지 않아 실패한다. 출력은 원본 검사 후 마스킹되고 다시 출력 스키마 검사를 받는다. 오류(`is_error`) 응답도 승인 스키마를 적용해 구조화 결과 누락/불일치를 `MCP-OUTPUT-001`로 보류한다. 다만 검사 전 스키마 크기·깊이 제한이 없던 점은 결함으로 판단해 깊이 64, 컨테이너 노드 10,000개, 약 256 KiB 상한을 추가했다. 상한 검사를 도구 목록 변환에도 넣어 카탈로그 해시 계산 전 초과를 거부하고, 실행 전 `MCP-CATALOG-001`로 연결했다. 새 순수 시험과 도구 목록 변환 시험을 추가했다.
3. **판본별 보존:** `2025-06-18`과 `2025-11-25`는 객체형 구조화 결과만 유지하고, `2026-07-28`은 JSON 값과 명시적 null을 보존한다. 구형 판본의 비객체 값은 스키마 검사·마스킹 뒤 JSON text로 내보낸다. 시험은 각 판본의 객체/배열/스칼라/null 분기를 검사한다. 공식 명세 페이지는 [2025-11-25 Tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools), [2026-07-28 Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)다.
4. **최종 전송 경합:** `_call_upstream`이 같은 연결에서 관측 output hash를 승인 hash와 대조한다. `dispatch.CATALOG_OK`가 최종 intent INSERT SQL 안에서 다시 출력 해시를 대조한다. 목록 노출 SQL도 같은 조건을 포함한다. 코드 검토에서 출력 해시 비교 누락 경로는 찾지 못했다. 실제 PostgreSQL 경합은 이번 로컬 검토 범위 밖이다.

## 한계와 잔여 검증

- D-149는 `isError=true` 결과도 검증하도록 선택했다. [공식 TypeScript SDK 오류 문서](https://ts.sdk.modelcontextprotocol.io/v2/servers/errors)와 [공식 PHP SDK 도구 문서](https://php.sdk.modelcontextprotocol.io/servers/tools/)는 오류 응답에서 outputSchema 검증을 생략한다고 설명하므로 MINT가 더 엄격하다. 계약 없는 오류 결과도 보류될 수 있어 모델의 자가 수정·재시도 정보가 줄 수 있으며, 공개 OSS 조합 시험으로 상호운용성을 확인해야 한다.
- 256 KiB/깊이/노드 상한은 정상적이지만 큰 스키마를 거부할 수 있다. Python 정규식의 병적 역추적 비용은 크기 상한만으로 완전히 제한하지 못한다.
- 로컬 환경은 게이트웨이 런타임 의존성이 없을 수 있다. 이 문서의 순수 검증 외에 게이트웨이 이미지 시험, 솔루션 기기 DB 마이그레이션·동시 호출, PJ1 실제 하네스, OSS 서버별 교섭·효과 검증은 수행하지 않았다.
