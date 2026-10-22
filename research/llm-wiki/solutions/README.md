# 상용 솔루션 및 오픈소스 분석

확인일: 2026-10-13. 이 영역은 개발 선택과 실험 설계용이다. 다른 제품의 기능 부재·제품 우열을 저장소 검색 결과만으로 단정하지 않는다.

2026-10-15 [조사 깊이 감사·보완 계획](../analysis/oss-audit/README.md): 확인한 로컬 clone은 10개이며 이 목록과 직접 연결된 clone 카드는 5개다. Azure 예제2개·agent-framework·PyRIT·AGT의 기존 분석은 상세 문서에 흩어져 있다. 아래 제품 요약만으로 전체 OSS 조사 범위나 심층 분석 완료를 판단하지 않는다.

2026-10-15 [심층 코드 분석](../analysis/oss-deep/README.md): 아래 카드의 선택 기능을 고정 commit에서 입구→권한→실행→실패 경로(L3)까지 다시 추적했다. 카드에 없던 5개 클론(Azure AI-Gateway·remote-mcp-apim·agent-framework·PyRIT·AGT)은 [누락 카드](../analysis/oss-deep/legacy-cards.md)에 있다. 카드와 심층 분석이 다르면 심층 분석의 "정정" 절이 우선이다.

| 구분 | 분석 | 확인 수준 | 개발에 참고할 부분 |
| --- | --- | --- | --- |
| OSS | [IBM ContextForge](ibm-contextforge.md) · [훅·오류 처리 심층](../analysis/oss-deep/contextforge-hooks.md) | 고정 커밋 코드·설정 | 사전 실행 훅, PDP 입력, OAuth 위임 |
| OSS | [IBM CPEX](ibm-cpex.md) | 고정 커밋 Rust 코드 | Redis 원자 호출량 처리, 탐지기와 실행 엔진 구분 |
| OSS | [Microsoft MCP Gateway](ms-mcp-gateway.md) · [세션·수명 심층](../analysis/oss-deep/ms-mcp-gateway-session.md) | 고정 커밋 C# 코드 | 역할·소유권을 함께 보는 권한 평가 |
| OSS | [Microsoft Wassette](ms-wassette.md) | 고정 커밋 Rust 코드 | 도구 실행의 Wasm/WASI 자원 경계 |
| OSS | [LiteLLM](litellm.md) · [MCP 경로 심층](../analysis/oss-deep/litellm-mcp-path.md) | 고정 커밋 Python 코드 | 명시한 MCP 서버 범위가 넓어지지 않는 처리 |
| 상용 | [Kong AI Gateway MCP](kong-ai-gateway.md) | 공식 문서 재확인 | 도구 ACL·토큰 audience·프로토콜 호환성 |
| 상용(클라우드) | [AWS CloudTrail·Bedrock·AgentCore, Azure Monitor·Foundry·APIM, Google Audit Logs·Model Armor, Cloudflare AI Gateway·MCP 포털](cloud-control-planes.md) · [온프레미스 차용 벤치마크](../analysis/cloud-control-benchmark-1023/README.md) | 공식 문서 선택 열람(2026-10-23) | 제어/데이터 평면 기록 분리, 서명 digest 체인, 정책 그림자 모드, 기준선 이상 탐지 |
| 상용 | [BeyondTrust Pathfinder MCP](beyondtrust-pathfinder.md) | 공식 문서 재확인 | 사이트 활성화·기한 있는 사용자 토큰 |
| 상용+OSS 생태계 | [Lunar MCPX + AI Gateway](lunar-mcpx.md) · [MCPX·스캐너 심층](../analysis/oss-deep/mcpx-cisco-scanner.md) | 공급자 공식 설명 | MCP 서버가 실행한 외부 API 호출의 별도 통제 |
| OSS 후보 | [ToolHive runtime](toolhive-runtime.md) · [런타임 심층](../analysis/oss-deep/toolhive-runtime.md) | v0.54.0(`1ce13bbb`) 고정 소스 L3 | DEV-38 수명 관리와 명시적 목적지 제한. 설치·실행 미검증 |
| 상용 | [CrowdStrike Falcon Guardian](crowdstrike-falcon-guardian.md) | 공식 보도자료·블로그 읽기(10-23) | 엔드포인트 에이전트 인벤토리, 프롬프트→실행 인과 조사, 허용 에이전트 종류 통제. 호출 단위 MCP 통제는 미확인 |
| 사례 | [젠아이랩스 AI-native 개발](genailabs-ai-native-dev.md) | 회사 사례 글(자체 기록, 10-23) | 승인 지점·규약 저장소·실수 전수조사를 검사로 전환·틀린 가설 기록. 코드 미공개 |
| 상용 | [GensOps 운영 관제](genailabs-gensops.md) | 제품 페이지·데모 첫 화면(10-23) | 한 화면 관제, 제안→승인→실행→기록 조치 흐름. 사내 운영·데모는 가상 데이터, 코드 미공개 |
| OSS·상용 | [OSS 게이트웨이·스캐너 최신 릴리스와 공시](oss-gateway-scanner-releases-1023.md) · [최신 레퍼런스 갱신](../analysis/refs-update-1023/README.md) | GitHub 릴리스 노트·보안 권고·공식 글 선택 열람(10-23) | agentgateway·Agent Router·Docker MCP Gateway·스캐너 판본, ContextForge·ToolHive·Microsoft·MCP Inspector 권고에서 게이트웨이 자체 fail-open·기본 비밀·이름 충돌 시험 후보. 코드·실행 미확인 |

## 증거 파일을 다시 확인하는 방법

`evidence/manifest.json`은 저장소 URL, 40자리 커밋, 원본 파일 경로·줄 범위, 원본 파일 SHA-256, 발췌 파일 SHA-256을 기록한다. `*.excerpt.txt`는 실행하지 않는 정적 발췌이며, 원래 줄 번호를 유지한다. 오픈소스의 라이선스와 존재하는 NOTICE도 함께 보관했다. 대형 클론·의존성·Enterprise 코드를 복제하지 않았다.

로컬 발췌는 라이선스가 확인된 코드만 보관한다. 상용 자료는 링크와 자체 요약을 보관하며, 라이선스를 확인하지 못한 문서의 전체 복제본은 넣지 않는다. 상용 제품의 공개 기능 설명, OSS 코드의 존재, 실제 배포 활성화, 실제 하네스 실험 성공은 서로 다른 확인 수준이다.

## 기존 분석에서 바로잡은 내용

기존 `docs/ai/BENCHMARK_IBM_CONTEXTFORGE.md`의 “기본값 전 항목 disabled”는 이 커밋의 실제 설정과 다르다. `plugins/config.yaml:99`의 PII 필터는 `enforce`다. 다른 플러그인도 항목별로 확인해야 한다. 문서의 해당 표현을 현재 제품 비교에 재사용하지 않는다.

이전 LiteLLM 문서가 분석한 버전과 여기 확보한 로컬 커밋도 다르다. 여기서는 `f8e456d105af921213267d0ef801ca08b8fdbc0b`의 `pyproject.toml`에 적힌 1.102.0만 분석했다. 이전 1.89.4/1.104.0 결과와 합쳐 단일 버전의 기능으로 쓰지 않는다.

## 다음 검증

후보 기능을 채택하기 전에는 활성 설정, 검사기 오류·타임아웃, 다중 프로세스, 토큰 만료·회수, 실제 도구 부수효과를 [실험 영역](../experiments/README.md)의 증거 규칙으로 확인한다. 현재 분석은 모두 정적 검토 또는 문서 검토다.
