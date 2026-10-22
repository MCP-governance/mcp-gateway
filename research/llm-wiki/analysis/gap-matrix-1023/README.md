# 발표용 경쟁·갭 매트릭스 — 2026-10-23

MINT와 8개 상용·OSS 제품을 10개 통제 기능으로 비교한다. 각 칸은 **구현 / 배포 / 실측** 순서다. 근거 없는 단계는 **미확인**으로 남긴다.

MINT 기준 `e30be961a9a00d7982dd8565e4412c7289e85f4d` · 작업 브랜치 `10/23-gap-matrix` · 정본 [근거 JSON](evidence.json) · [작업 보고](../../status/reports/2026-10-23-gap-matrix.md).

구현의 `코드`는 정적 구현 근거, `공식`은 공급자 기능 설명 또는 기업의 1차 사용 사례다. `부분`은 행의 일부 범위만 대응한다. 배포·실측의 `부분·보고`는 10-23 MINT 보고의 해당 경로, `부분·자사`는 공급자 자사 운영 서술이다. 셋은 보증 수준이 다르며 자동 승격하지 않는다. `미확인`은 기능 부재나 실패를 뜻하지 않는다.

MINT의 실측은 PJ1 Claude의 filesystem→memory→sequentialthinking 정상 업무와 memory 저장·재조회 보고에 한정한다. 기존 보고 재사용이며 이번 재실행은 없다. 최종 원장 3허용·5경보·0차단은 공격 방어율·격리 강도·전체 기능 검수가 아니다.

## OSS·개발자 환경

| 통제 기능 | MINT | LiteLLM | IBM ContextForge | ToolHive | Docker AI Governance |
| --- | --- | --- | --- | --- | --- |
| 도입 심사 | [코드 / 부분·보고 / 부분·보고](#mint-intake) | [공식·부분 / 미확인 / 미확인](#l-intake) | [미확인](#c-intake) | [미확인](#t-intake) | [공식·부분 / 미확인 / 미확인](#d-intake) |
| 계약 고정 | [코드·부분 / 부분·보고 / 부분·보고](#mint-contract) | [공식·부분 / 미확인 / 미확인](#l-contract) | [미확인](#c-contract) | [미확인](#t-contract) | [미확인](#d-contract) |
| 호출 전 판정 | [코드 / 부분·보고 / 부분·보고](#mint-precall) | [코드 / 미확인 / 미확인](#l-precall) | [코드 / 미확인 / 미확인](#c-precall) | [코드·부분 / 미확인 / 미확인](#t-precall) | [공식·부분 / 미확인 / 미확인](#d-precall) |
| 출력 통제 | [코드 / 부분·보고 / 부분·보고](#mint-output) | [코드 / 미확인 / 미확인](#l-output) | [코드 / 미확인 / 미확인](#c-output) | [미확인](#t-output) | [미확인](#d-output) |
| 동의 | [코드 / 부분·보고 / 부분·보고](#mint-consent) | [미확인](#l-consent) | [미확인](#c-consent) | [미확인](#t-consent) | [미확인](#d-consent) |
| 엔드포인트 강제 | [코드·부분 / 부분·보고 / 미확인](#mint-endpoint) | [미확인](#l-endpoint) | [미확인](#c-endpoint) | [미확인](#t-endpoint) | [공식·부분 / 미확인 / 미확인](#d-endpoint) |
| 로컬 MCP 격리 | [코드 / 부분·보고 / 부분·보고](#mint-isolation) | [미확인](#l-isolation) | [미확인](#c-isolation) | [코드 / 미확인 / 미확인](#t-isolation) | [미확인](#d-isolation) |
| 감사 원장 | [코드·부분 / 부분·보고 / 부분·보고](#mint-audit) | [코드·부분 / 미확인 / 미확인](#l-audit) | [공식·부분 / 미확인 / 미확인](#c-audit) | [코드·부분 / 미확인 / 미확인](#t-audit) | [공식·부분 / 미확인 / 미확인](#d-audit) |
| 종료 판정 | [코드 / 미확인 / 미확인](#mint-termination) | [미확인](#l-termination) | [미확인](#c-termination) | [미확인](#t-termination) | [미확인](#d-termination) |
| AI 게이트웨이 연동 | [코드·부분 / 미확인 / 미확인](#mint-ai) | [코드·부분 / 미확인 / 미확인](#l-ai) | [미확인](#c-ai) | [미확인](#t-ai) | [미확인](#d-ai) |

## 클라우드·AI 게이트웨이·엔드포인트

| 통제 기능 | MINT | AWS AgentCore Policy·Gateway | Cloudflare MCP 포털·Gateway | Kong AI MCP Proxy | CrowdStrike Falcon Guardian |
| --- | --- | --- | --- | --- | --- |
| 도입 심사 | [코드 / 부분·보고 / 부분·보고](#mint-intake) | [미확인](#a-intake) | [공식·부분 / 부분·자사 / 미확인](#cf-intake) | [미확인](#k-intake) | [미확인](#f-intake) |
| 계약 고정 | [코드·부분 / 부분·보고 / 부분·보고](#mint-contract) | [미확인](#a-contract) | [미확인](#cf-contract) | [미확인](#k-contract) | [미확인](#f-contract) |
| 호출 전 판정 | [코드 / 부분·보고 / 부분·보고](#mint-precall) | [공식 / 미확인 / 미확인](#a-precall) | [공식·부분 / 부분·자사 / 미확인](#cf-precall) | [공식 / 미확인 / 미확인](#k-precall) | [미확인](#f-precall) |
| 출력 통제 | [코드 / 부분·보고 / 부분·보고](#mint-output) | [미확인](#a-output) | [공식·부분 / 미확인 / 미확인](#cf-output) | [미확인](#k-output) | [미확인](#f-output) |
| 동의 | [코드 / 부분·보고 / 부분·보고](#mint-consent) | [미확인](#a-consent) | [미확인](#cf-consent) | [미확인](#k-consent) | [미확인](#f-consent) |
| 엔드포인트 강제 | [코드·부분 / 부분·보고 / 미확인](#mint-endpoint) | [미확인](#a-endpoint) | [미확인](#cf-endpoint) | [미확인](#k-endpoint) | [공식·부분 / 미확인 / 미확인](#f-endpoint) |
| 로컬 MCP 격리 | [코드 / 부분·보고 / 부분·보고](#mint-isolation) | [미확인](#a-isolation) | [미확인](#cf-isolation) | [미확인](#k-isolation) | [미확인](#f-isolation) |
| 감사 원장 | [코드·부분 / 부분·보고 / 부분·보고](#mint-audit) | [공식·부분 / 미확인 / 미확인](#a-audit) | [공식·부분 / 미확인 / 미확인](#cf-audit) | [미확인](#k-audit) | [공식·부분 / 미확인 / 미확인](#f-audit) |
| 종료 판정 | [코드 / 미확인 / 미확인](#mint-termination) | [미확인](#a-termination) | [미확인](#cf-termination) | [미확인](#k-termination) | [미확인](#f-termination) |
| AI 게이트웨이 연동 | [코드·부분 / 미확인 / 미확인](#mint-ai) | [미확인](#a-ai) | [미확인](#cf-ai) | [공식·부분 / 미확인 / 미확인](#k-ai) | [미확인](#f-ai) |

## 비교 조건

| 통제 기능 | 행의 의미 |
| --- | --- |
| 도입 심사 | 신규 MCP의 출처·검사·범위를 사람이 검토해 승인한다. 단순 등록/허용 목록은 부분 대응. |
| 계약 고정 | 승인한 도구 정의를 고정하고 변경을 처리한다. pin 노출·live 대조·출력 스키마를 구분. |
| 호출 전 판정 | 실제 도구 전송 전에 인증된 주체·권한·인자·정책을 평가한다. 목록 숨김만으로 충족하지 않음. |
| 출력 통제 | 도구 실행 후 결과를 검사·마스킹·보류한다. 이미 발생한 부수효과 취소와 별개. |
| 동의 | 직원의 데이터 이용 조건 동의·철회와 호출 적용. OAuth 연결 동의·관리자 도입 승인과 구별. |
| 엔드포인트 강제 | 관리 PC의 승인 경로 밖 MCP·프로세스·망 접근을 OS/센서에서 제한한다. 정상 경유만으로 입증 안 됨. |
| 로컬 MCP 격리 | 로컬 MCP 서버 프로세스의 파일·망·자격·자원 경계를 실행기에 적용한다. 에이전트 자체 격리와 구별. |
| 감사 원장 | 호출·조치의 주체/시점/판정/효과를 보존한다. 일반 로그와 append-only·체인·외부 앵커를 구별. |
| 종료 판정 | 중지 조치와 별개로 회수 대상·권한·전파·상태 증거에 따라 종료/부분 종료/판단 불가를 결정한다. |
| AI 게이트웨이 연동 | LLM 경로와 MCP 경로를 구분해 연결·판정·결과를 연계한다. 자사 AI 프록시 기능은 부분 대응. |

각 행의 정상·음성·경계·실패·경쟁·복구 조건 60개는 JSON의 `controls[].verification_conditions`에 있다. 모두 후속 검증 조건이며 이번에는 실행하지 않았다. 표의 부분 실측은 지정 보고의 정상 경로만 가리키며 나머지 조건의 통과를 뜻하지 않는다.

| 제품 | 고정 판본·상용 범위 | 라이선스·근거 |
| --- | --- | --- |
| MINT | e30be961a9a00d7982dd8565e4412c7289e85f4d | 이 저장소; 외부 제품 라이선스 판단 대상 아님 · [M-real](../../status/reports/2026-10-23-real-usage-local-mcp.md#L14) |
| LiteLLM | 코드 1.102.0 f8e456d105af921213267d0ef801ca08b8fdbc0b; 문서 10-22~23/종료 1.103.0 별도 | 분석 코드 MIT; enterprise 별도 상용 · [L-analysis](../oss-deep/litellm-mcp-path.md) |
| IBM ContextForge | 5735c9db7f8f50cd5a55eb7fefe83ecde00b5324; 최신 릴리스 주장을 이 코드에 합치지 않음 | Apache-2.0; CPEX 별도 의존성 · [C-card](../../solutions/ibm-contextforge.md) |
| ToolHive | v0.54.0 1ce13bbbbbe1ed9a3f40fea03ed1a42533f04cea; 10-14 릴리스 관측 | Apache-2.0; 외부 권한 구현 일부 미독 · [T-analysis](../oss-deep/toolhive-runtime.md) |
| Docker AI Governance | 2026-05-12 공식 발표의 4개 통제 표면 | 상용 조건 미확인; OSS Docker MCP Gateway(MIT)와 별도 · [D-governance](https://www.docker.com/blog/docker-ai-governance-unlock-agent-autonomy-safely/) · [확보 기록](../industry-trends-1023/industry-trends-1023.sources.json) |
| AWS AgentCore Policy·Gateway | 2026-10-23 확보 문서; 서비스 판본 번호 미표시 | 상용; 비용·계정 조건 미확인 · [A-policy](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html) · [확보 기록](../cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json) |
| Cloudflare MCP 포털·Gateway | 2026-10-23 확보 문서·자사 사례; 선택 Gateway 경유 포함 | 상용; 플랜 조건 미확인 · [CF-portal](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/) · [확보 기록](../cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json) |
| Kong AI MCP Proxy | 기존 3.x 문서; 도구별 ACL 3.13 이후; Konnect 레지스트리 기술 미리보기 | AI Gateway Enterprise; OSS Kong 전체 기능으로 확대 안 함 · [K-card](../../solutions/kong-ai-gateway.md) |
| CrowdStrike Falcon Guardian | 2026-09-01 발표; 10-23 읽은 공식 글에서 AI Gateway pre-beta | 상용·코드 비공개; OS 지원 자료 불일치 · [F-card](../../solutions/crowdstrike-falcon-guardian.md) |

## 발표에서 말할 수 있는 차이와 남은 갭

- 도입 승인·도구 ACL·pin·출력 검사는 기존 제품에도 있다. LiteLLM을 단순 LLM 프록시로 표현하거나 MINT만의 기능으로 내세우지 않는다.
- MINT의 검토 대상은 직원 PC 경로·로컬 실행·승인 계약·전송 직전 검사·종료 증거를 잇는 구성이다. ToolHive의 로컬 격리, Docker의 파일·망·자격·MCP 통제, Falcon의 센서 통제가 있어 엔드포인트·격리 자체도 독점 기능이 아니다.
- MINT 계약 고정은 로컬 실행기의 실제 대조까지 코드로 연결되지만 출력 승인 해시 NULL의 미고정 예외가 있다. LiteLLM pin과 비교할 때 설명·입력·출력, 모델 노출·실제 전송을 나눠야 한다.
- MINT는 종료 판정 코드를 갖지만 10-23 철회 보고만으로 C1~C4/T1~T3 실측 완료를 주장하지 않는다. LiteLLM 세션 종료·자격 철회와 ToolHive Stop/Delete도 무시하지 않는다.
- AI 게이트웨이 연동은 MINT의 코드 근거가 있으며, 허용된 MINT 근거 안에서는 배포·실측이 미확인이다. LiteLLM 승인·철회 동기화, 애드인 출력 통제, 판정 후 전송 경쟁은 남은 갭이다.
- 감사 기록 존재와 위변조 방지는 별도다. MINT는 decisions append-only·해시 연결이 있으나 외부 앵커·관리 변경 완전성·미리보기 개인정보는 후속 확인 대상이다. CloudTrail의 서명 digest는 차용 기준이며 MCP 통제 기능으로 합산하지 않는다.
- 규제 요구의 문서·판본·고객 적용성, 최신 명세 호환, 교차 고객 데이터 감지·업스트림 사용자 위임·점진 발견은 기존 조사에서 남긴 갭이다. 이 10행의 구현 표시로 규제 준수·모델 안전성·전체 직원 행위 통제를 선언하지 않는다.

## 칸별 근거와 한계

아래 근거 링크의 코드 행·SHA-256·원문 manifest ID·URL·확보 시각·열람 범위는 JSON에 고정했다. MINT의 긍정 판정은 실제 코드·DECISIONS·지정한 10-23 실사용 보고만 참조한다. 다른 조사 속 MINT 평가를 긍정 근거로 가져오지 않았다.

### MINT-intake

**MINT · 도입 심사** — 검사 결과·출처·판본·위험 수용 gate와 사람의 계약 승인. 로컬 이미지는 digest 고정·서명.

로컬 3종 도입·재승인 정상 경로만 보고됨. 4종 스캐너 실패·공급망/원격 SaaS 내부 검증 실측은 미확인.

근거·검토 범위: [M-review](../../../../full_stack_lab/gateway/app/review.py#L144) · [M-intake-worker](../../../../full_stack_lab/supply_chain/intake_worker.py#L216) · [M-approve](../../../../full_stack_lab/gateway/app/core.py#L385) · [D-192](../../../../docs/ai/DECISIONS.md#L1959) · [M-real](../../status/reports/2026-10-23-real-usage-local-mcp.md#L14).

### MINT-contract

**MINT · 계약 고정** — 설명·입력·승인 출력 해시 대조. 로컬 호출은 승인 캐시를 노출하고 PC 실행기가 실제 계약을 대조.

출력 승인 해시 NULL은 재승인 전 미고정. 10-23 보고는 계약 변경 공격/재승인 경합의 실측이 아님.

근거·검토 범위: [M-contract](../../../../full_stack_lab/gateway/app/core.py#L1631) · [M-output-pin](../../../../full_stack_lab/gateway/app/output_contract.py#L70) · [M-local-pin](../../../../endpoint-agent/local-runner.py#L492) · [D-203](../../../../docs/ai/DECISIONS.md#L2070) · [M-real](../../status/reports/2026-10-23-real-usage-local-mcp.md#L14).

### MINT-precall

**MINT · 호출 전 판정** — OPA 호출 전 판정·전송 직전 재검사·요청 지문 결속. OPA 결정 계약 불능은 오류.

관찰 모드와 집행을 구분해야 함. 3허용·5경보·0차단은 최종 정상 실행 결과이며 오탐/미탐률이 아님.

근거·검토 범위: [M-call](../../../../full_stack_lab/gateway/app/core.py#L2200) · [M-policy](../../../../full_stack_lab/gateway/app/core.py#L1617) · [M-contract](../../../../full_stack_lab/gateway/app/core.py#L1631) · [M-real](../../status/reports/2026-10-23-real-usage-local-mcp.md#L14).

### MINT-output

**MINT · 출력 통제** — 결과 검사·개인정보/비밀 마스킹·보류; 구조화 키=값과 문서 예시 구분.

51KB 읽기·문서 보류 오탐 수정 후 정상 성공. 모든 형식의 유출 방지·출력 정확도·LLM 최종 답변 통제는 미확인.

근거·검토 범위: [M-result](../../../../full_stack_lab/gateway/app/core.py#L1934) · [M-mask](../../../../full_stack_lab/gateway/app/privacy.py#L193) · [D-202](../../../../docs/ai/DECISIONS.md#L2059) · [M-real](../../status/reports/2026-10-23-real-usage-local-mcp.md#L14).

### MINT-consent

**MINT · 동의** — 직원×도구×등급×조건 해시의 동의. 서버별 일괄 결정과 도구별 기록·전송 직전 유효성 검사.

D-201 초기 기록은 대역 시험. 후속 10-23 실사용은 적용·정상 완료 보고이며 철회/경합 음성군 실측은 미확인.

근거·검토 범위: [M-consent](../../../../full_stack_lab/gateway/app/consent.py#L33) · [M-contract](../../../../full_stack_lab/gateway/app/core.py#L1631) · [D-201](../../../../docs/ai/DECISIONS.md#L2051) · [M-real](../../status/reports/2026-10-23-real-usage-local-mcp.md#L14).

### MINT-endpoint

**MINT · 엔드포인트 강제** — 관리형 Linux의 UID 망 규칙·보호 설정과 관찰기. 승인 로컬 컨테이너 오탐 제외.

관리형 PJ1 경유 성공·관찰기 적용만 보고됨. 같은 UID/SID bearer 접근, 경고 단계, 관리자·셸/SDK 우회가 남는다. OS 우회 차단 실측으로 세지 않음.

근거·검토 범위: [M-linux](../../../../endpoint-agent/enforce-linux.py#L67) · [D-62](../../../../docs/ai/DECISIONS.md#L715) · [D-183](../../../../docs/ai/DECISIONS.md#L1911) · [D-205](../../../../docs/ai/DECISIONS.md#L2092) · [M-real](../../status/reports/2026-10-23-real-usage-local-mcp.md#L14).

### MINT-isolation

**MINT · 로컬 MCP 격리** — 승인 digest 실행; network=none·읽기 전용 루트·cap-drop·자원 한도·허용 마운트.

정상 컨테이너 실행은 격리 탈출 음성 시험이 아님. userns 미사용 Docker의 호스트 root 위험 수용·비밀 필요한 MCP 범위 밖.

근거·검토 범위: [M-isolation](../../../../endpoint-agent/local-runner.py#L119) · [M-local-pin](../../../../endpoint-agent/local-runner.py#L492) · [D-192](../../../../docs/ai/DECISIONS.md#L1959) · [D-203](../../../../docs/ai/DECISIONS.md#L2070) · [M-real](../../status/reports/2026-10-23-real-usage-local-mcp.md#L14).

### MINT-audit

**MINT · 감사 원장** — 판정·실행 여부·결과 요약 기록, decisions append-only 트리거와 행 해시 연결.

10-23 원장 조회는 기록 존재의 증거. 무결성 파괴/외부 앵커·모든 관리 변경 해시 연결 실측은 미확인. 요청 미리보기를 개인정보 무저장으로 해석하지 않음.

근거·검토 범위: [M-audit](../../../../full_stack_lab/gateway/app/core.py#L2002) · [M-append](../../../../full_stack_lab/gateway/app/agent_tables.sql#L84) · [M-audit-preview](../../../../full_stack_lab/gateway/app/core.py#L1982) · [M-enforcement](../../../../full_stack_lab/gateway/app/core.py#L1200) · [M-real](../../status/reports/2026-10-23-real-usage-local-mcp.md#L14).

### MINT-termination

**MINT · 종료 판정** — C1~C4 기준·대상별 상태 증거·최저 등급으로 T1~T3 판정. 폐기 응답과 상태 증명을 구별.

10-23 시험 뒤 서버 8개 철회는 보고됐지만 종료 케이스·C1~C4/T1~T3 판정·하류 자격 거절/삭제 실측은 미확인.

근거·검토 범위: [M-end](../../../../full_stack_lab/gateway/app/decommission.py#L717) · [M-end-kinds](../../../../full_stack_lab/gateway/app/decommission.py#L65).

### MINT-ai

**MINT · AI 게이트웨이 연동** — LiteLLM의 MINT 업스트림 구성 생성(A), 사전 판정 API·가드레일과 사후 기록(B). 직원 transport 토큰으로만 판정.

허용 근거 D-191은 실제 B 연동 미실행을 명시. 10-23 보고는 로컬 MCP 경로로 A/B 배포·연동 E2E 증거 아님. B는 판정~전송 경쟁·출력 통제 한계; 승인/철회 동기화 근거 없음.

근거·검토 범위: [M-addon](../../../../full_stack_lab/gateway/app/addon.py#L26) · [M-addon-generator](../../../../addons/litellm/gen_mcp_servers.py#L36) · [M-addon-hook](../../../../addons/litellm/mint_guardrail.py#L64) · [D-191](../../../../docs/ai/DECISIONS.md#L1948).

### L-intake

**LiteLLM · 도입 심사** — 서버 제출·관리자 승인 후 노출.

MINT식 공급망 검사·실행 세대 심사를 동일 기능으로 추정하지 않음.

근거·검토 범위: [L-intake](https://docs.litellm.ai/docs/mcp_server_submissions) · [확보 기록](../litellm-mint-opportunities-20261022.sources.json) · [L-update](../litellm-mint-opportunities-20261022.md).

### L-contract

**LiteLLM · 계약 고정** — 도구 목록·설명·입력 스키마 pin, 추가 이름 거절·drift 알림.

annotations·output schema는 pin 밖. 고정본 노출과 live 불일치 실행 차단을 구별; 1.102 소스와 최신 문서를 합치지 않음.

근거·검토 범위: [L-pin](https://docs.litellm.ai/docs/mcp_control) · [확보 기록](../litellm-mint-opportunities-20261022.sources.json) · [L-update](../litellm-mint-opportunities-20261022.md).

### L-precall

**LiteLLM · 호출 전 판정** — 서버/도구 ACL·인자·pre_mcp_call 사전 훅.

f8e456d105: mcp_server_manager.py 5335~5454, server.py 3023~3068. 모든 인증 방식·기본값이 같은 엄격 교집합은 아님.

근거·검토 범위: [L-analysis](../oss-deep/litellm-mcp-path.md) · [intervention](../litellm-intervention-1023/README.md).

### L-output

**LiteLLM · 출력 통제** — post_mcp_call 가드레일과 결과 변환.

server.py 3176~3207·3387~3396, 선택 설정 필요; 이미 실행된 도구 효과 취소가 아님.

근거·검토 범위: [L-analysis](../oss-deep/litellm-mcp-path.md) · [L-output](https://docs.litellm.ai/docs/mcp_guardrail) · [확보 기록](../litellm-mint-opportunities-20261022.sources.json).

### L-consent

**LiteLLM · 동의** — 근거를 확보하지 못함

사용자별 OAuth 연결 동의는 확인되나 직원 데이터 이용 조건 동의와 동일하지 않음(L-auth).

근거·검토 범위: [L-analysis](../oss-deep/litellm-mcp-path.md) · [L-auth](https://docs.litellm.ai/docs/mcp_per_user_auth) · [확보 기록](../litellm-mint-opportunities-20261022.sources.json) · [L-end](https://docs.litellm.ai/release_notes/v1.103.0/v1-103-0) · [확보 기록](../litellm-mint-opportunities-20261022.sources.json).

### L-endpoint

**LiteLLM · 엔드포인트 강제** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [L-analysis](../oss-deep/litellm-mcp-path.md) · [L-auth](https://docs.litellm.ai/docs/mcp_per_user_auth) · [확보 기록](../litellm-mint-opportunities-20261022.sources.json) · [L-end](https://docs.litellm.ai/release_notes/v1.103.0/v1-103-0) · [확보 기록](../litellm-mint-opportunities-20261022.sources.json).

### L-isolation

**LiteLLM · 로컬 MCP 격리** — 중앙 stdio 실행 지원과 직원 PC 로컬 MCP의 격리 경계는 별개.

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [L-analysis](../oss-deep/litellm-mcp-path.md) · [L-auth](https://docs.litellm.ai/docs/mcp_per_user_auth) · [확보 기록](../litellm-mint-opportunities-20261022.sources.json) · [L-end](https://docs.litellm.ai/release_notes/v1.103.0/v1-103-0) · [확보 기록](../litellm-mint-opportunities-20261022.sources.json).

### L-audit

**LiteLLM · 감사 원장** — 공통 MCP 호출 로깅 훅·관측 경로.

server.py 3176~3283·3387~3396. 로그 최종 내구성·append-only/체인·외부 앵커는 미확인.

근거·검토 범위: [L-analysis](../oss-deep/litellm-mcp-path.md).

### L-termination

**LiteLLM · 종료 판정** — 1.103.0 세션 종료·저장 자격 철회 문서(L-end)는 있으나 C1~C4에 해당하는 종료 판정은 미확인.

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [L-analysis](../oss-deep/litellm-mcp-path.md) · [L-auth](https://docs.litellm.ai/docs/mcp_per_user_auth) · [확보 기록](../litellm-mint-opportunities-20261022.sources.json) · [L-end](https://docs.litellm.ai/release_notes/v1.103.0/v1-103-0) · [확보 기록](../litellm-mint-opportunities-20261022.sources.json).

### L-ai

**LiteLLM · AI 게이트웨이 연동** — LLM 프록시와 별도 MCP 집계/실행이 인증·로깅·훅을 공유.

자체 두 경로의 존재이며 MINT와의 연동 실측이 아님. enterprise·판본별 조건 분리.

근거·검토 범위: [L-analysis](../oss-deep/litellm-mcp-path.md) · [intervention](../litellm-intervention-1023/README.md).

### C-intake

**IBM ContextForge · 도입 심사** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [C-analysis](../oss-deep/contextforge-hooks.md) · [C-case](https://brunch.co.kr/@ably-team/62) · [확보 기록](../mcp-enterprise-cases-1023/mcp-enterprise-cases-1023.sources.json).

### C-contract

**IBM ContextForge · 계약 고정** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [C-analysis](../oss-deep/contextforge-hooks.md) · [C-case](https://brunch.co.kr/@ably-team/62) · [확보 기록](../mcp-enterprise-cases-1023/mcp-enterprise-cases-1023.sources.json).

### C-precall

**IBM ContextForge · 호출 전 판정** — tool_pre_invoke PDP 및 호출부의 사전 훅.

unified_pdp.py 234~312; 기본 PDP 플러그인 disabled. 플러그인별 mode/on_error와 CPEX 엔진 경계; 기존 분석 머리의 fail-open 과장 정정이 우선.

근거·검토 범위: [C-card](../../solutions/ibm-contextforge.md) · [C-analysis](../oss-deep/contextforge-hooks.md).

### C-output

**IBM ContextForge · 출력 통제** — tool_post_invoke·PII/비밀 탐지 및 수정 payload.

tool_service.py 7455~7467·plugins/config.yaml 88~115. 필터 enforce 설정이 배포/실측 증거는 아님.

근거·검토 범위: [C-card](../../solutions/ibm-contextforge.md) · [C-analysis](../oss-deep/contextforge-hooks.md).

### C-consent

**IBM ContextForge · 동의** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [C-analysis](../oss-deep/contextforge-hooks.md) · [C-case](https://brunch.co.kr/@ably-team/62) · [확보 기록](../mcp-enterprise-cases-1023/mcp-enterprise-cases-1023.sources.json).

### C-endpoint

**IBM ContextForge · 엔드포인트 강제** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [C-analysis](../oss-deep/contextforge-hooks.md) · [C-case](https://brunch.co.kr/@ably-team/62) · [확보 기록](../mcp-enterprise-cases-1023/mcp-enterprise-cases-1023.sources.json).

### C-isolation

**IBM ContextForge · 로컬 MCP 격리** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [C-analysis](../oss-deep/contextforge-hooks.md) · [C-case](https://brunch.co.kr/@ably-team/62) · [확보 기록](../mcp-enterprise-cases-1023/mcp-enterprise-cases-1023.sources.json).

### C-audit

**IBM ContextForge · 감사 원장** — 에이블리가 ContextForge 포크의 감사 로그 운영을 보고.

자사 공급자 문서가 아닌 사용자 기업의 1차 사례. 이 고정 판본의 기능별 활성·로그 불변성은 미확인이라 배포 축은 승격하지 않음.

근거·검토 범위: [C-case](https://brunch.co.kr/@ably-team/62) · [확보 기록](../mcp-enterprise-cases-1023/mcp-enterprise-cases-1023.sources.json) · [cases](../mcp-enterprise-cases-1023/README.md).

### C-termination

**IBM ContextForge · 종료 판정** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [C-analysis](../oss-deep/contextforge-hooks.md) · [C-case](https://brunch.co.kr/@ably-team/62) · [확보 기록](../mcp-enterprise-cases-1023/mcp-enterprise-cases-1023.sources.json).

### C-ai

**IBM ContextForge · AI 게이트웨이 연동** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [C-analysis](../oss-deep/contextforge-hooks.md) · [C-case](https://brunch.co.kr/@ably-team/62) · [확보 기록](../mcp-enterprise-cases-1023/mcp-enterprise-cases-1023.sources.json).

### T-intake

**ToolHive · 도입 심사** — 생성 gate·이미지 검증 코드는 있으나 독립 사람 심사 workflow는 미확인. 기본 gate 허용·검증 warn을 승인 심사로 세지 않음.

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [T-analysis](../oss-deep/toolhive-runtime.md).

### T-contract

**ToolHive · 계약 고정** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [T-analysis](../oss-deep/toolhive-runtime.md).

### T-precall

**ToolHive · 호출 전 판정** — HTTP 입구의 인증 middleware와 선택 authz 구성.

pkg/auth/token.go 1302~1317·config_builder.go 980~1010. OIDC 미구성 시 synthetic local-user; Cedar 판정 전체·인자 정책은 미독.

근거·검토 범위: [T-analysis](../oss-deep/toolhive-runtime.md).

### T-output

**ToolHive · 출력 통제** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [T-analysis](../oss-deep/toolhive-runtime.md).

### T-consent

**ToolHive · 동의** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [T-analysis](../oss-deep/toolhive-runtime.md).

### T-endpoint

**ToolHive · 엔드포인트 강제** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [T-analysis](../oss-deep/toolhive-runtime.md).

### T-isolation

**ToolHive · 로컬 MCP 격리** — 로컬 MCP Docker 격리·cap-drop·내부 bridge·Squid 목적지/포트·마운트 경계.

v0.54.0 pkg/container/docker/client.go 253~356·866~899·1684~1772. 외부 toolhive-core 권한 구현 일부 미독; 모든 이미지 digest 강제·검증 실패 차단 기본값 아님.

근거·검토 범위: [T-analysis](../oss-deep/toolhive-runtime.md).

### T-audit

**ToolHive · 감사 원장** — 선택 audit 구성과 운영 로그.

pkg/runner/config_builder.go 1014~1041. 구성 경계의 코드이며 활성·불변 원장·독립 내구성은 미확인.

근거·검토 범위: [T-analysis](../oss-deep/toolhive-runtime.md).

### T-termination

**ToolHive · 종료 판정** — Stop/Delete 수명 API는 있으나 종료 효과의 증거 등급 판정은 미확인.

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [T-analysis](../oss-deep/toolhive-runtime.md).

### T-ai

**ToolHive · AI 게이트웨이 연동** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [T-analysis](../oss-deep/toolhive-runtime.md).

### D-intake

**Docker AI Governance · 도입 심사** — 관리자가 MCP 서버/도구 허용 정책을 배포하고 미승인 서버를 제한.

공급자 설명, 실제 설치·정책 활성·우회 차단·원장 무결성 미검증. OSS MCP Gateway의 기능/라이선스로 전이하지 않음.

근거·검토 범위: [D-governance](https://www.docker.com/blog/docker-ai-governance-unlock-agent-autonomy-safely/) · [확보 기록](../industry-trends-1023/industry-trends-1023.sources.json) · [industry](../industry-trends-1023/README.md).

### D-contract

**Docker AI Governance · 계약 고정** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [D-governance](https://www.docker.com/blog/docker-ai-governance-unlock-agent-autonomy-safely/) · [확보 기록](../industry-trends-1023/industry-trends-1023.sources.json).

### D-precall

**Docker AI Governance · 호출 전 판정** — MCP 호출을 인증·인가·정책 엔진 경유로 설명.

공급자 설명, 실제 설치·정책 활성·우회 차단·원장 무결성 미검증. OSS MCP Gateway의 기능/라이선스로 전이하지 않음.

근거·검토 범위: [D-governance](https://www.docker.com/blog/docker-ai-governance-unlock-agent-autonomy-safely/) · [확보 기록](../industry-trends-1023/industry-trends-1023.sources.json) · [industry](../industry-trends-1023/README.md).

### D-output

**Docker AI Governance · 출력 통제** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [D-governance](https://www.docker.com/blog/docker-ai-governance-unlock-agent-autonomy-safely/) · [확보 기록](../industry-trends-1023/industry-trends-1023.sources.json).

### D-consent

**Docker AI Governance · 동의** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [D-governance](https://www.docker.com/blog/docker-ai-governance-unlock-agent-autonomy-safely/) · [확보 기록](../industry-trends-1023/industry-trends-1023.sources.json).

### D-endpoint

**Docker AI Governance · 엔드포인트 강제** — 에이전트 sandbox의 파일·망·자격·MCP 정책을 노트북/실행 환경에 적용한다고 설명.

공급자 설명, 실제 설치·정책 활성·우회 차단·원장 무결성 미검증. OSS MCP Gateway의 기능/라이선스로 전이하지 않음.

근거·검토 범위: [D-governance](https://www.docker.com/blog/docker-ai-governance-unlock-agent-autonomy-safely/) · [확보 기록](../industry-trends-1023/industry-trends-1023.sources.json) · [industry](../industry-trends-1023/README.md).

### D-isolation

**Docker AI Governance · 로컬 MCP 격리** — 에이전트 microVM sandbox 설명은 로컬 MCP 서버 자체의 격리 경계를 입증하지 않아 미확인 유지.

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [D-governance](https://www.docker.com/blog/docker-ai-governance-unlock-agent-autonomy-safely/) · [확보 기록](../industry-trends-1023/industry-trends-1023.sources.json).

### D-audit

**Docker AI Governance · 감사 원장** — 주체·시점·세션·적용 규칙의 구조화 사건과 SIEM 내보내기 설명.

공급자 설명, 실제 설치·정책 활성·우회 차단·원장 무결성 미검증. OSS MCP Gateway의 기능/라이선스로 전이하지 않음.

근거·검토 범위: [D-governance](https://www.docker.com/blog/docker-ai-governance-unlock-agent-autonomy-safely/) · [확보 기록](../industry-trends-1023/industry-trends-1023.sources.json) · [industry](../industry-trends-1023/README.md).

### D-termination

**Docker AI Governance · 종료 판정** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [D-governance](https://www.docker.com/blog/docker-ai-governance-unlock-agent-autonomy-safely/) · [확보 기록](../industry-trends-1023/industry-trends-1023.sources.json).

### D-ai

**Docker AI Governance · AI 게이트웨이 연동** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [D-governance](https://www.docker.com/blog/docker-ai-governance-unlock-agent-autonomy-safely/) · [확보 기록](../industry-trends-1023/industry-trends-1023.sources.json).

### A-intake

**AWS AgentCore Policy·Gateway · 도입 심사** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [cloud](../cloud-control-benchmark-1023/README.md).

### A-contract

**AWS AgentCore Policy·Gateway · 계약 고정** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [cloud](../cloud-control-benchmark-1023/README.md).

### A-precall

**AWS AgentCore Policy·Gateway · 호출 전 판정** — AgentCore Gateway의 매 도구 요청을 Cedar 정책 엔진이 실행 전에 평가.

ENFORCE/LOG_ONLY 선택·정책 엔진 부착 필요. Bedrock 모델 가드레일의 출력 통제를 MCP 결과 통제로 합산하지 않음.

근거·검토 범위: [A-policy](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html) · [확보 기록](../cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json) · [A-modes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-enforcement-modes.html) · [확보 기록](../cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json).

### A-output

**AWS AgentCore Policy·Gateway · 출력 통제** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [cloud](../cloud-control-benchmark-1023/README.md).

### A-consent

**AWS AgentCore Policy·Gateway · 동의** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [cloud](../cloud-control-benchmark-1023/README.md).

### A-endpoint

**AWS AgentCore Policy·Gateway · 엔드포인트 강제** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [cloud](../cloud-control-benchmark-1023/README.md).

### A-isolation

**AWS AgentCore Policy·Gateway · 로컬 MCP 격리** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [cloud](../cloud-control-benchmark-1023/README.md).

### A-audit

**AWS AgentCore Policy·Gateway · 감사 원장** — 정책 결정 로그·CloudWatch 지표 설명.

Cedar 진단 상세·판정/효과 결속·append-only 원장·외부 앵커는 미확인. CloudTrail 기능을 자동 상속한다고 세지 않음.

근거·검토 범위: [A-policy](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html) · [확보 기록](../cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json) · [cloud](../cloud-control-benchmark-1023/README.md).

### A-termination

**AWS AgentCore Policy·Gateway · 종료 판정** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [cloud](../cloud-control-benchmark-1023/README.md).

### A-ai

**AWS AgentCore Policy·Gateway · AI 게이트웨이 연동** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [cloud](../cloud-control-benchmark-1023/README.md).

### CF-intake

**Cloudflare MCP 포털·Gateway · 도입 심사** — 자사 신규 MCP 거버넌스 승인·포털별 서버/도구 선정.

공급자 자사 사례이며 제품의 범용 공급망 검사 workflow와 같다고 추정하지 않음.

근거·검토 범위: [CF-case](https://blog.cloudflare.com/enterprise-mcp) · [확보 기록](../mcp-enterprise-cases-1023/mcp-enterprise-cases-1023.sources.json) · [CF-portal](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/) · [확보 기록](../cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json).

### CF-contract

**Cloudflare MCP 포털·Gateway · 계약 고정** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [CF-portal](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/) · [확보 기록](../cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json) · [CF-case](https://blog.cloudflare.com/enterprise-mcp) · [확보 기록](../mcp-enterprise-cases-1023/mcp-enterprise-cases-1023.sources.json).

### CF-precall

**Cloudflare MCP 포털·Gateway · 호출 전 판정** — Access 신원·기기 조건·노출 도구 선택, 선택 Gateway DLP 경유.

도구별 인자 정책과 MINT 조건 동의는 미확인. Gateway 경유/검사 예외 설정에 의존.

근거·검토 범위: [CF-portal](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/) · [확보 기록](../cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json) · [CF-case](https://blog.cloudflare.com/enterprise-mcp) · [확보 기록](../mcp-enterprise-cases-1023/mcp-enterprise-cases-1023.sources.json).

### CF-output

**Cloudflare MCP 포털·Gateway · 출력 통제** — 선택 Gateway 경유의 DLP로 요청·응답에서 민감 자료를 차단.

Gateway routing·DLP 정책 필요; Do Not Inspect·SSE 제한. 일반 AI Gateway 모델 가드레일과 구별.

근거·검토 범위: [CF-portal](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/) · [확보 기록](../cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json).

### CF-consent

**Cloudflare MCP 포털·Gateway · 동의** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [CF-portal](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/) · [확보 기록](../cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json) · [CF-case](https://blog.cloudflare.com/enterprise-mcp) · [확보 기록](../mcp-enterprise-cases-1023/mcp-enterprise-cases-1023.sources.json).

### CF-endpoint

**Cloudflare MCP 포털·Gateway · 엔드포인트 강제** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [CF-portal](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/) · [확보 기록](../cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json) · [CF-case](https://blog.cloudflare.com/enterprise-mcp) · [확보 기록](../mcp-enterprise-cases-1023/mcp-enterprise-cases-1023.sources.json).

### CF-isolation

**Cloudflare MCP 포털·Gateway · 로컬 MCP 격리** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [CF-portal](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/) · [확보 기록](../cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json) · [CF-case](https://blog.cloudflare.com/enterprise-mcp) · [확보 기록](../mcp-enterprise-cases-1023/mcp-enterprise-cases-1023.sources.json).

### CF-audit

**Cloudflare MCP 포털·Gateway · 감사 원장** — Access의 도구 요청 기록과 선택 Gateway HTTP 로그.

로그 보존 설명을 append-only/해시 연결·외부 앵커 보장으로 해석하지 않음.

근거·검토 범위: [CF-portal](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/) · [확보 기록](../cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json).

### CF-termination

**Cloudflare MCP 포털·Gateway · 종료 판정** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [CF-portal](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/) · [확보 기록](../cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json) · [CF-case](https://blog.cloudflare.com/enterprise-mcp) · [확보 기록](../mcp-enterprise-cases-1023/mcp-enterprise-cases-1023.sources.json).

### CF-ai

**Cloudflare MCP 포털·Gateway · AI 게이트웨이 연동** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [CF-portal](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/) · [확보 기록](../cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json) · [CF-case](https://blog.cloudflare.com/enterprise-mcp) · [확보 기록](../mcp-enterprise-cases-1023/mcp-enterprise-cases-1023.sources.json).

### K-intake

**Kong AI MCP Proxy · 도입 심사** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [K-card](../../solutions/kong-ai-gateway.md).

### K-contract

**Kong AI MCP Proxy · 계약 고정** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [K-card](../../solutions/kong-ai-gateway.md).

### K-precall

**Kong AI MCP Proxy · 호출 전 판정** — Consumer/Group·도구별 ACL과 목록/호출 접근 판정.

3.13 이후 도구별 ACL·Enterprise. ACL 미구성 허용; Konnect 레지스트리 기술 미리보기를 도입 심사 실구현으로 세지 않음.

근거·검토 범위: [K-acl](https://developer.konghq.com/plugins/ai-mcp-proxy/) · [확보 기록](../cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json) · [K-card](../../solutions/kong-ai-gateway.md).

### K-output

**Kong AI MCP Proxy · 출력 통제** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [K-card](../../solutions/kong-ai-gateway.md).

### K-consent

**Kong AI MCP Proxy · 동의** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [K-card](../../solutions/kong-ai-gateway.md).

### K-endpoint

**Kong AI MCP Proxy · 엔드포인트 강제** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [K-card](../../solutions/kong-ai-gateway.md).

### K-isolation

**Kong AI MCP Proxy · 로컬 MCP 격리** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [K-card](../../solutions/kong-ai-gateway.md).

### K-audit

**Kong AI MCP Proxy · 감사 원장** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [K-card](../../solutions/kong-ai-gateway.md).

### K-termination

**Kong AI MCP Proxy · 종료 판정** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [K-card](../../solutions/kong-ai-gateway.md).

### K-ai

**Kong AI MCP Proxy · AI 게이트웨이 연동** — 기존 AI Gateway의 MCP 프록시 플러그인.

LLM 프록시 전체 경로·MINT 연동·호출 단위 정책의 동등성 실측은 미확인.

근거·검토 범위: [K-acl](https://developer.konghq.com/plugins/ai-mcp-proxy/) · [확보 기록](../cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json) · [K-card](../../solutions/kong-ai-gateway.md).

### F-intake

**CrowdStrike Falcon Guardian · 도입 심사** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [F-card](../../solutions/crowdstrike-falcon-guardian.md).

### F-contract

**CrowdStrike Falcon Guardian · 계약 고정** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [F-card](../../solutions/crowdstrike-falcon-guardian.md).

### F-precall

**CrowdStrike Falcon Guardian · 호출 전 판정** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [F-card](../../solutions/crowdstrike-falcon-guardian.md).

### F-output

**CrowdStrike Falcon Guardian · 출력 통제** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [F-card](../../solutions/crowdstrike-falcon-guardian.md).

### F-consent

**CrowdStrike Falcon Guardian · 동의** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [F-card](../../solutions/crowdstrike-falcon-guardian.md).

### F-endpoint

**CrowdStrike Falcon Guardian · 엔드포인트 강제** — OS 센서의 허용 에이전트 종류 제한·런타임 탐지/차단.

개별 MCP 호출 전 판정 방식·현재 Linux 지원은 미확인. 가시성만으로 차단 성공을 세지 않음.

근거·검토 범위: [F-announcement](https://www.crowdstrike.com/en-us/press-releases/crowdstrike-unveils-falcon-guardian-ai-agent-security/) · [확보 기록](../references-1023/sources.json) · [F-blog](https://www.crowdstrike.com/en-us/blog/falcon-guardian-defines-next-generation-of-ai-security) · [확보 기록](../references-1023/sources.json).

### F-isolation

**CrowdStrike Falcon Guardian · 로컬 MCP 격리** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [F-card](../../solutions/crowdstrike-falcon-guardian.md).

### F-audit

**CrowdStrike Falcon Guardian · 감사 원장** — 에이전트 세션·도구 실행 인과 텔레메트리를 Next-Gen SIEM으로 전달한다고 설명.

인과 가시성은 공급자 설명. 호출 판정/효과의 완전성·append-only·외부 앵커·실제 연동은 미확인.

근거·검토 범위: [F-blog](https://www.crowdstrike.com/en-us/blog/falcon-guardian-defines-next-generation-of-ai-security) · [확보 기록](../references-1023/sources.json) · [F-card](../../solutions/crowdstrike-falcon-guardian.md).

### F-termination

**CrowdStrike Falcon Guardian · 종료 판정** — 근거를 확보하지 못함

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [F-card](../../solutions/crowdstrike-falcon-guardian.md).

### F-ai

**CrowdStrike Falcon Guardian · AI 게이트웨이 연동** — 공식 블로그의 AI Gateway pre-beta·Q4 계획. GA/실구현·배포·실측은 미확인.

검토 범위에서 미확인. 기능 부재·미배포·실패의 판정이 아니다.

근거·검토 범위: [F-card](../../solutions/crowdstrike-falcon-guardian.md).

## 종합에 쓴 기존 조사

| 조사 | 이번 반영 범위 |
| --- | --- |
| [cloud](../cloud-control-benchmark-1023/README.md) | 통제 평면·서명 digest·정책 모드; 클라우드 문서 기능과 실행 증거 구분 |
| [references](../references-1023/README.md) | Falcon의 엔드포인트 통제·AI Gateway 예고; 자체 개발 사례·가상 데모를 경쟁 제품 실측에서 제외 |
| [regulation](../regulation-gap-1023/README.md) | 원자 요구·조건별 검증·법적 역할·미리보기 잔존의 한계; 규제 충족/인증 점수 없음 |
| [refs](../refs-update-1023/README.md) | 고정 코드와 최신 릴리스·권고 분리; 초록만 읽은 연구를 실증 방법으로 채택하지 않음 |
| [cases](../mcp-enterprise-cases-1023/README.md) | 실제 운영 사례의 자기 보고 구분; Cloudflare 자사 사례·ContextForge 포크를 제품 일반 실측으로 확대하지 않음 |
| [industry](../industry-trends-1023/README.md) | 클라우드/신원/개발자/OSS 데이터 평면 구분; Docker 상용과 OSS Gateway 분리 |
| [intervention](../litellm-intervention-1023/README.md) | LLM·MCP 경로 및 업스트림/애드인 보장 구분; MINT 칸의 증거로 직접 사용하지 않음 |

Microsoft Agent 365·Snowflake·NetScaler·agentgateway·Agent Router는 기존 조사에 있으나 이번 10개 통제의 기능별 근거가 부족해 열에서 제외했다. GensOps는 사내 운영·가상 데모, 젠아이랩스 사례는 자체 업무 기록이어서 비교 제품 실측으로 세지 않았다. AWS Bedrock·Google Model Armor·Cloudflare AI Gateway의 모델 출력 가드레일을 MCP 응답 통제로 옮겨 쓰지 않았다.

공개 GitHub 스킬·OSS는 기존 ToolHive 고정 조사(스킬 0.4.0·Apache-2.0·commit·해시)를 재사용했다. 추가 공개 탐색은 후보 확인에만 썼고 외부 스킬·스크립트는 설치·실행하지 않았다. 기존 상용 원문은 재배포하지 않고 자체 요약·URL·manifest만 연결한다.

ToolHive v0.54.0 등 고정 코드 분석은 최신 보안 수정 전 판본을 포함한다. 후속 릴리스·권고를 구분하며 안전한 배포 판본 추천으로 사용하지 않는다. 기업 포크의 사용 사례도 upstream 고정 판본의 동일 동작을 증명하지 않는다.

## 재생성과 검증

```powershell
py -3 -B -X utf8 research/llm-wiki/analysis/gap-matrix-1023/build.py
py -3 -B -X utf8 research/llm-wiki/analysis/gap-matrix-1023/build.py --check
py -3 -B -X utf8 research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources
```

`--check`는 10×9=90칸·3개 독립 축·출처·MINT 증거 제한·판본/파일 해시·생성물 일치를 검사한다. baseline HEAD에서 생성하며, 제품 기능·배포·PJ1 검증을 실행하는 검사는 아니다. 원격 HEAD 조회는 네트워크 제한으로 실패했으며 로컬 origin/main과 시작 HEAD 일치만 확인했다.
