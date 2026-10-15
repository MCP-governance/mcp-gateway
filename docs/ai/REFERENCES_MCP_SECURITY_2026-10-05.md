# MCP 보안·거버넌스 참고자료 모음 — 2026-10-05

> 다음 작업에서 "이런 거 비슷한 거 뭐 있었지"를 다시 검색하지 않으려고 모은 목록이다. 이 저장소의 방향
> (하네스를 고치지 않고 Gateway·OS로 강제, 손코드보다 오픈소스, 설명 문구는 UI에 안 넣음)에 맞춰 골랐다.
> 이미 읽은 AGT(`microsoft/agent-governance-toolkit`)는 [BENCHMARK_AGT_2026-10-05.md](BENCHMARK_AGT_2026-10-05.md)에 있으므로 여기서 뺐다.
>
> **확인 수준**: ◎ 페이지·README를 직접 읽음(요약 모델 경유, 스타 수 같은 숫자는 2026-10-05 시점 근사) /
> ○ 검색 결과 설명만 봄(들어가서 읽지 않았음). ○는 쓰기 전에 원문을 먼저 확인할 것.

## 1. 표준·위협 모델 (우리 대응표의 근거로 인용)

| # | 자료 | 확인 | 내용 | 쓸 곳 |
| --- | --- | --- | --- | --- |
| 1 | [OWASP MCP Top 10](https://owasp.github.io/www-project-mcp-top-10/) | ○ | MCP01~10, 2025 beta | 우리 정본 대응표 [PAC_RUNTIME](PAC_RUNTIME_2026-10-01.md)의 출처. 정식판이 나오면 항목명이 바뀔 수 있으니 대응표 갱신 |
| 2 | [MCP Security Best Practices (2026-07-28 문서판)](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices) | ◎ | confused deputy, token passthrough 금지, SSRF(사설 IP·리디렉션·DNS TOCTOU), **state handle hijacking**(새 판은 프로토콜 세션이 없고 서버가 만든 핸들을 인자로 받음), 로컬 서버 침해, mix-up, 범위 최소화 | 우리 Gateway와의 대응은 확인함(D-74). 새 판의 상태 핸들·SSRF 항목은 공급자 점검표로 쓸 수 있음 |
| 3 | [CSA Agentic MCP Security Best Practices Guide](https://labs.cloudsecurityalliance.org/agentic/agentic-mcp-security-best-practices-v1/) | ○ | 위협 6범주, 통제 영역별 요구사항, **4단계 성숙도 모델**, OWASP Agentic Top 10·AICM·MITRE ATLAS 대응 | 논문·보고서에서 우리 단계를 성숙도 수준으로 설명할 때. CoSAI 백서(요약: [adversa.ai](https://adversa.ai/blog/mcp-security-whitepaper-2026-cosai-top-insights/))와 같은 계열 |

## 2. 연구·벤치마크 (시험 입력·비교 기준)

| # | 자료 | 확인 | 내용 | 쓸 곳 |
| --- | --- | --- | --- | --- |
| 4 | [MCPTox (arXiv 2508.14925)](https://arxiv.org/abs/2508.14925) | ○ | 실제 MCP 서버 45개·도구 353개 기반 도구 오염 시험 1,312건, 10개 위험 범주. 모델 20종 중 최고 성공률 72.8%, 거부율 3% 미만 | `poisoning.py` 탐지율을 재는 **시험 코퍼스** 후보(지금은 garak latent-injection으로 쟀음). 2026-10-15 확인: 공개 저장소 `zhiqiangwang4/MCPTox-Benchmark`(커밋 f85189f, 라이선스 파일 없음 → 읽기만 하고 재배포하지 않음)에 오염 설명 485건과 정상 서버 45개의 정상 설명 342건이 있어 `tests/inspection_corpus_eval.py`가 계약 규칙을 잰다(탐지 0.272 → 0.524, 정상 오탐 0/342, D-100) |
| 5 | [MCP Security Bench (arXiv 2510.15994)](https://arxiv.org/html/2510.15994v1) | ○ | MCP 대상 공격 벤치마크 | 공격 분류 체계 비교 |
| 6 | [CASCADE (arXiv 2604.17125)](https://arxiv.org/pdf/2604.17125) | ○ | MCP 시스템용 **계층형 로컬 방어**의 구성요소 제거 실험과 코퍼스 감사 | 우리 다층 구조(계약 해시→poisoning→PAC→DLP)의 계층별 기여도를 같은 방식으로 재는 설계 참고 |
| 7 | [Five-Plane Reference Architecture (arXiv 2606.12320)](https://arxiv.org/pdf/2606.12320) | ○ | 운영 AI 에이전트 런타임 거버넌스 5평면 참조 구조 | 우리 "평면" 설계([CONTROL_PLANES](CONTROL_PLANES_2026-10-01.md))와 용어·분할 비교 |

## 3. 오픈소스 도구 (가져오거나 비교할 것)

| # | 자료 | 확인 | 라이선스 | 요점 | 쓸 곳·주의 |
| --- | --- | --- | --- | --- | --- |
| 8 | [cisco-ai-defense/mcp-scanner](https://github.com/cisco-ai-defense/mcp-scanner) | ◎ | Apache-2.0 | Python 3.11+, ★약 1.1k. **YARA 규칙** + LLM 판정 + (선택) Cisco API. 사전 배포용 | YARA 규칙 파일을 도입 검사(`supply_chain/`)나 `poisoning.py` 규칙 보강의 참고로. 외부 API·VirusTotal은 폐쇄 환경에선 끈다 |
| 9 | [agentgateway/agentgateway](https://github.com/agentgateway/agentgateway) | ◎ | Apache-2.0 | Rust, ★약 5.2k, Linux Foundation. MCP·A2A·LLM 프록시, **CEL 기반 RBAC**, JWT·OAuth, 도구 연합, OTel | "오픈소스를 통으로" 원칙의 대체 데이터 평면 후보. 우리 OPA 계약·원장과 어떻게 붙을지는 미검토 |
| 10 | [provnai/McpVanguard](https://github.com/provnai/McpVanguard) | ◎ | MIT | Python, ★13. L0 정규화→L1 규칙→L1.5 위장→L2 의도→L3 이상 5계층, **monitor/balanced/strict 프로필** | 우리 monitor 모드·점진 도입과 비교. 소규모 프로젝트라 의존 대상은 아님, 설계 참고 |
| 11 | [ressl/mcp-firewall](https://github.com/ressl/mcp-firewall) | ◎ | **AGPL-3.0** | Python, ★19, 0.2.0 알파. 7단계 파이프라인(킬 스위치→속도 제한→인젝션→반출→위협 피드→정책→체인 탐지), Ed25519 서명 + 해시 체인 감사, SIEM 내보내기(CEF/LEEF) | 감사 **서명**(우리는 해시 체인만)과 SIEM 포맷 참고. **AGPL이라 코드는 복사하지 말 것**, 읽기만 |
| 12 | [snyk/agent-scan](https://github.com/snyk/agent-scan) (옛 Invariant mcp-scan) | ◎ | Apache-2.0 | Python, ★약 3.1k. 도구 오염·toxic flow 탐지 | **SNYK_TOKEN과 외부 API가 필요**하고 설정 스캔 시 명령을 실행한다 → 폐쇄 시험 환경에선 비교 대상으로만. 외부 반출 금지 원칙과 충돌 |

## 4. 더 찾을 때의 출발점 (원문 미확인)

- [awesome-mcp-security](https://github.com/tamish560/awesome-mcp-security): 스캐너·게이트웨이·방화벽·관측·redaction·인증·공격 도구·가이드 10개 분류의 큐레이션(◎). 새 도구를 찾을 때 먼저 볼 목록. 거기서 눈에 띈 것: `mcprobe`(Go 단일 바이너리 스캐너), `observer`(SQLite 트레이스 프록시), `MCP-Guard`(GenTelLab, 다단계 방어 연구), `redact-mcp`(정규식+NER 마스킹).
- [Docker MCP Gateway](https://github.com/docker/mcp-gateway)(MIT, ○): 컨테이너 격리 + `--block-secrets`. 서버 실행 격리 비교용.
- 비교 글(2차 자료, ○): [Pipelab MCP gateway 보안 비교](https://pipelab.org/learn/mcp-gateway/), [Cisco vs Snyk vs Pipelock](https://pipelab.org/blog/mcp-scanner-comparison-2026/).
- AGT 안의 [Agent Control Specification](https://commandline.microsoft.com/agent-control-specification-runtime-governance/)(◎): 훅 지점 8개(`agent_startup`·`input`·`pre/post_model_call`·`pre/post_tool_call`·`output`·`agent_shutdown`)와 Rego 번들·allow/warn/deny/escalate 결과 계약. 우리 `Allow/Alert/Restrict/Approval/Block` 계약과 이름·의미를 맞춰 볼 만하다.

## 5. 다음 작업에서 바로 쓸 연결

1. **poisoning 규칙 보강** — AGT 대조 결과는 반영함([BENCHMARK_AGT](BENCHMARK_AGT_2026-10-05.md), D-73). 남은 것: #8(YARA 규칙)·#4(MCPTox)로
   탐지율을 재는 일. 지금 코퍼스는 garak 26건(21건 탐지)뿐이고, 계약 규칙(`findings`)은 코퍼스가 아직 없다.
2. **새 MCP 규격 대응** — 확인함(D-74, `tests/protocol_versions_check.py`): 두 세대 모두 코드 변경 없이 동작. 남은 것: 하네스가 실제로 붙는 세대 확인,
   `gateway-sse`(Deprecated) 사용처, tasks 확장·stdio·`x-mcp-header` 시험.
3. **감사 서명** → #11 방식(서명 + 해시 체인)을 우리 `verify_audit_chain` 위에 얹을지 판단. 키 관리 비용이 있으니 필요성부터.
4. **데이터 평면 대안** → #9. 지금 Gateway를 갈아엎자는 뜻이 아니라 비교표 한 장.
5. **논문·보고서 근거** → #1·#3·#6·#7.
