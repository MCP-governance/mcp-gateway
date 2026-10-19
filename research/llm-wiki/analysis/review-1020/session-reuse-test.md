# 업스트림 세션 재사용 시험 실패 원인 (2026-10-20)

## 판정

`full_stack_lab/tests/upstream_session_reuse_test.py`의 실패는 제품 세션 재사용 결함이 아니라 `DispatchTests`의 AST 함수 로딩 대역이 현재 `_call_upstream`의 의존성 계약에 뒤처진 시험 결함이다. 시험 파일은 요청에 따라 고치지 않았다. 40개 중 8개 오류와 `0 != 3` 실패를 현재 트리에서 재현했다. 시험 픽스처에 계약 해시 대역과 승인된 메타데이터를 메모리에서만 추가해 다시 실행했을 때 40/40 통과했다.

## 근거

- 시험은 `functions("core.py", {"_call_upstream"}, ns)`로 제품 함수 본문만 실행하고 전역 의존성을 `DispatchTests.asyncSetUp`의 `ns`에서 제공한다(시험 27–33, 562–574행). 이 대역의 `registry`는 `server`와 `pinned_protocol`만 포함하고 `tool_hashes`를 제공하지 않는다(563행).
- 제품 함수는 목록에서 도구를 찾고 등록 계약·스키마를 비교한 뒤, `registry.tool_hashes(observed[tool])`를 호출한다(`full_stack_lab/gateway/app/core.py:1371–1374`). 이 심볼은 고정 제품 모듈 `registry.py:266–268`에 존재한다. 대역 호출에서 `AttributeError`가 발생해 7개 오류가 난다. T10 재시도 시험은 첫 목록 오류를 잡아 재시도한 다음 같은 누락 지점에서 여덟 번째 오류를 낸다.
- 메타데이터 검토가 승인 해시와 다를 때만 `poisoning.findings`를 호출한다. 픽스처가 승인 해시를 주지 않으면 그 검사까지 도달해도 제품 의존성 대역을 추가로 요구하게 된다. 제안 수정은 실제 픽스처 도구 값에 대응하는 해시를 승인된 리뷰로 제공해 이 정상 경로를 모델링한다.
- `dispatch.record`가 `principal`·`terminated`·`approval` 거부를 반환하면 제품은 `problem`을 설정하고 `upstream.release_pool(..., "dispatch-recheck")`를 불러야 한다(`core.py:1457–1466`). 대역의 `registry.tool_hashes` 호출이 release 이전에 예외를 던져 release가 0회가 되고 `assertEqual(..., 3)`가 `0 != 3`으로 실패했다. 기대값 3은 그대로 둔다.
- `git show c002fbd:full_stack_lab/gateway/app/core.py`에서도 `registry.tool_hashes` 호출이 있고 같은 시점 시험 대역도 이를 제공하지 않는다. 따라서 보고된 실패는 DEV-48/67/68/69 병합 전에도 재현 가능하며 그 병합들이 원인이 아니다.
- 실제 D-115 세션 풀은 독립 시험으로 같은 파일 안의 pool/wiring 검증 대상이다. 실패 지점은 그 풀의 키·수명·경합 코드가 아니라 core 호출 검증용 픽스처다. D-115의 세션 바인딩 및 호출마다 재확인 규칙을 수정할 근거는 없다.

## 시험 파일에 적용할 수정안 (미적용)

```diff
-            "DispatchRejected": DispatchRejected, "registry": NS(server=lambda _: {"endpoint": "https://a.example/mcp"}, pinned_protocol=lambda _: "2025-11-25"),
+            "DispatchRejected": DispatchRejected, "registry": NS(
+                server=lambda _: {"endpoint": "https://a.example/mcp", "poisoning_review": {
+                    "tool": {"description_sha256": "description", "schema_sha256": {}}}},
+                pinned_protocol=lambda _: "2025-11-25",
+                tool_hashes=lambda _: {"description_sha256": "description", "schema_sha256": {}}),
```

이 수정은 관측 도구의 `description="description"`, `input_schema={}`와 시험 대역의 `canonical_hash=lambda value: value`에 맞는 실제 `registry.tool_hashes` 결과를 채워 대역을 제품 입력 계약과 정렬한다. 기존 거부·재확인·전송 금지·release 횟수의 기대값 및 호출은 변경하지 않는다. 따라서 시험의 성질을 약화하지 않는다. 해시가 일치하는 안전한 기본 픽스처를 명시해 실행 예정 경로로 보내는 수정이다. 계약 변경 사례는 별도 T7 시험이 기존대로 검증한다. 이 diff는 시험 관리자의 적대 검토 전 적용하지 않는다.

## 실행 결과

| 확인 | 결과 |
| --- | --- |
| 현재 시험 `python -X utf8 full_stack_lab/tests/upstream_session_reuse_test.py` | 40건, 1 failure (`0 != 3`), 8 errors (`registry.tool_hashes` 누락) |
| 메모리상 픽스처만 보완해 동일 40건 실행 | 40건 통과. 시험 파일은 수정하지 않음 |
| `python -m py_compile` core·registry·upstream·upstream_sessions·시험 | 통과 |
| Gateway 이미지·실제 MCP·PJ1 | 미실행 |

## 결론과 한계

제품 코드 수정은 하지 않는다. 기존 시험 파일 수정이 필요하며, 위 diff는 보고만 하고 적용하지 않았다. 동적 확인은 고정 제품 함수와 시험 대역을 사용한 단위 실행이지, 실제 MCP·DB·Gateway 이미지 배포나 PJ1 증거가 아니다. 원격 HEAD는 네트워크 연결 실패로 재확인하지 못했다. 시작 브랜치는 `10/20-session-reuse-test`, 시작 기준 commit은 `9761dc6`이다.
