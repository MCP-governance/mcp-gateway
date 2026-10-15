# IBM ContextForge — 실행 훅·PDP·OAuth 위임

확인일: 2026-10-13 · 확인 수준: 고정 커밋 정적 코드 검토 · 라이선스: Apache-2.0.

[검토 커밋](https://github.com/IBM/mcp-context-forge/tree/5735c9db7f8f50cd5a55eb7fefe83ecde00b5324): `5735c9db7f8f50cd5a55eb7fefe83ecde00b5324`. 기존 `docs/ai/BENCHMARK_IBM_CONTEXTFORGE.md`를 길잡이로 쓰고, 아래 근거를 실제 Git blob에서 다시 읽었다. 통합 실행은 하지 않았다.

## 코드로 확인한 사실

| 관찰 | 코드 근거 | 우리 개발에 주는 의미 |
| --- | --- | --- |
| `tool_pre_invoke`에서 PDP를 호출하고 DENY면 `continue_processing=False`와 위반 결과를 반환한다 | [unified_pdp.py:234–312](https://github.com/IBM/mcp-context-forge/blob/5735c9db7f8f50cd5a55eb7fefe83ecde00b5324/plugins/unified_pdp/unified_pdp.py#L234-L312) | 실행 전 정책 훅이라는 패턴은 기존 솔루션도 다룬다. 이를 우리만의 차별점으로 쓰지 않는다 |
| 기본 PDP 결정은 deny, 캐시는 기본 활성·60초이며 다중 엔진 구성이 가능하다 | [unified_pdp.py:123–164](https://github.com/IBM/mcp-context-forge/blob/5735c9db7f8f50cd5a55eb7fefe83ecde00b5324/plugins/unified_pdp/unified_pdp.py#L123-L164) | 우리 승인·종료·회수처럼 시간이 판정에 영향을 주는 입력에 결정 캐시를 붙일 때 무효화 근거가 필요하다 |
| RFC 8693 token exchange 요청에 subject token, audience, scope를 조립한다 | [oauth_manager.py:771–852](https://github.com/IBM/mcp-context-forge/blob/5735c9db7f8f50cd5a55eb7fefe83ecde00b5324/mcpgateway/services/oauth_manager.py#L771-L852) | 공급자별 자격 파일과 사용자별 OAuth 위임은 별도 방식이다. 우리 방식이 RFC 8693 OBO를 구현했다는 표현을 피한다 |
| PII 필터는 `enforce`, unified PDP는 `disabled`로 적혀 있다 | [config.yaml:88–115](https://github.com/IBM/mcp-context-forge/blob/5735c9db7f8f50cd5a55eb7fefe83ecde00b5324/plugins/config.yaml#L88-L115), [1259–1303](https://github.com/IBM/mcp-context-forge/blob/5735c9db7f8f50cd5a55eb7fefe83ecde00b5324/plugins/config.yaml#L1259-L1303) | 플러그인 존재와 기본 활성은 항목별로 확인한다. 과거 “모두 disabled” 결론을 정정한다 |
| watchdog은 pre 훅에서 시작시각을 기록하고 post 훅에서 경과시간 위반을 계산한다 | [watchdog.py:77–116](https://github.com/IBM/mcp-context-forge/blob/5735c9db7f8f50cd5a55eb7fefe83ecde00b5324/plugins/watchdog/watchdog.py#L77-L116) | 이 코드만으로 실행 중인 도구를 중단하는 강제 타임아웃을 입증할 수 없다 |

## 채택 판단

PDP 입력 계약과 사전 실행 훅은 비교 기준으로 유지한다. 새로운 다중 정책 엔진·결정 캐시는 지금 도입할 이유가 확인되지 않았다. OAuth 위임은 공급자 자격을 사용자 단위로 제한해야 할 때 별도 설계·시험 후보다. source search에서 못 찾은 기능을 제품 전체에 없다고 판정하지 않는다.

## 확보 증거와 한계

[설정 발췌](evidence/ibm-contextforge/plugins__config.yaml.excerpt.txt), [PDP 발췌](evidence/ibm-contextforge/plugins__unified_pdp__unified_pdp.py.excerpt.txt), [OAuth 발췌](evidence/ibm-contextforge/mcpgateway__services__oauth_manager.py.excerpt.txt), [watchdog 발췌](evidence/ibm-contextforge/plugins__watchdog__watchdog.py.excerpt.txt), [라이선스](evidence/ibm-contextforge/LICENSE.txt). 검토 커밋 루트에 NOTICE 파일은 없다.

실제 플러그인 엔진의 예외 처리·훅 배선·활성 여부, 통합 성능, 사용자별 upstream 권한 회수는 이 정적 검토로 확인하지 못했다. 최신 main 전체의 기능을 대표하지 않는다.

## 업스트림 세션 처리 (2026-10-15 추가)

같은 커밋 `5735c9d`에서 [`upstream_session_registry.py`](https://github.com/IBM/mcp-context-forge/blob/5735c9db7f8f50cd5a55eb7fefe83ecde00b5324/mcpgateway/services/upstream_session_registry.py#L750-L904)와 [ADR-032](https://github.com/IBM/mcp-context-forge/blob/5735c9db7f8f50cd5a55eb7fefe83ecde00b5324/docs/docs/architecture/adr/032-mcp-session-pool.md#L1-L21)를 읽었다. 신원 키 세션 풀이 같은 사용자의 다운스트림 세션 사이로 상태를 흘려(#4205) `(다운스트림 Mcp-Session-Id, gateway_id)` 1:1 레지스트리로 대체됐다. 벽시계 TTL 없이 유휴 60초 뒤 재사용 전 건강 확인, 세션 사용 직렬화, 전송 오류·다운스트림 세션 삭제·게이트웨이 인증 변경 때 축출한다. 호출 경로에는 실행 전 업스트림 `tools/list` 재확인이 없다. 10-14 보고의 "레지스트리 소스 미열람"을 이 확인으로 대체한다. 적용 검토는 [세션 재사용 설계 비교](../analysis/upstream-session-reuse/README.md).
