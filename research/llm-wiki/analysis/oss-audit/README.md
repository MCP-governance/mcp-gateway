# OSS 조사 범위·분석 깊이 점검과 보완 계획

확인일: 2026-10-15 · 시작 commit `f84796dbd958a5ae44c54628b35e7e4a36628a50` · 작업 `DEV-47`.

**판정: 실제 클론과 유용한 함수 단위 분석은 있다. 그러나 목표 기능의 구현 결정을 맡길 만큼 종류·호출 경로·실패 조건·비교 검증이 고르게 갖춰지지는 않았다.** 최신 제품 요약은 확인 범위를 비교적 정확하게 표시하지만, 옛 상세 보고서의 과장·오류와 연결되지 않은 자료가 남아 있다. 문서 수나 클론 수로 분석 완료율을 계산하지 않는다.

> **10-15 실행 결과:** 2~5단계를 [심층 코드 분석](../oss-deep/README.md)으로 실행했다(9개 문서, 메인 원본 대조). 1단계의 누락 카드는 [legacy-cards](../oss-deep/legacy-cards.md). 6단계(L4 재현)는 남았다. 목표 기능에 주는 영향은 [재검토](../oss-deep/redesign-2026-10-15.md).

## 이번에 확인한 범위

- 로컬 `C:\Users\bobysg\bob\프로젝트\ref-src`의 9개 Git 저장소와 `분석_litellm\litellm` 1개의 origin·HEAD·shallow·dirty 상태를 읽었다. 모두 clean이며 9개는 shallow, LiteLLM은 shallow가 아니다. 다른 PC·WSL·캐시 전체의 클론 수는 아니다.
- [솔루션 카탈로그](../../catalogs/solutions.json) 9항목, [제품별 요약](../../solutions/README.md), 기존 `docs/ai/BENCHMARK_*`의 관련 절·한계, [제품 대조](../competitor-mapping.json), [OSS 활용](../oss-reuse.json) 8항목과 [연동 시험](../integration-cases.json)을 대조했다.
- [보존 manifest](../../solutions/evidence/manifest.json)의 5개 OSS·21개 파일을 각 클론의 고정 Git blob과 SHA-256으로 대조했다. 불일치 0개. 그중 소스·설정·버전 발췌 14개, 나머지 7개는 LICENSE/NOTICE다. 발췌 줄 합계 982는 보존 범위이지 전체 정독 범위나 분석 품질 점수가 아니다.
- ContextForge 기본 설정/PDP, Microsoft 권한 함수, LiteLLM alias resolver, PyRIT MCP 세션 생성 등을 선별 재독했다. 기존 보고서의 모든 문장을 재검증하거나 전체 코드를 정독한 작업은 아니다. 새 클론·설치·빌드·제품 변경·실행 시험은 하지 않았다.
- 재현 가능한 로컬 관측과 파일 hash는 [감사 정본](audit.json)에 보존했다. 이 파일은 OSS 실행 결과를 포함하지 않는다.

## 깊이를 판단하는 기준

| 단계 | 필요한 증거 |
| --- | --- |
| L0 발견 | URL·용도 후보만 확인 |
| L1 문서 | 공식 문서/README·제공 기능·라이선스/판본 조사. 구현 확인과 분리 |
| L2 소스 | 고정 commit의 관련 함수·설정·파일을 읽고 위치를 제시 |
| L3 경로 | 선택 기능의 입구→인증/정책→실행→결과/감사, 상태·저장소·오류/철회/복구와 상위 호출자·기존 시험까지 연결 |
| L4 재현 | 판본/설정을 고정해 정상·음성·경계·장애·경쟁·복구를 실제 OSS로 실행하고 독립 효과 확인 |

단계는 **제품 전체가 아닌 선택 기능별**로 부여한다. 일부 상세 절에 L3 요소가 있어도 전체 경로가 닫히지 않으면 해당 기능을 L3 완료로 올리지 않는다. MINT에 채택·배포·검수됐는지는 별도 축이다. 예전 AGT 규칙 채택이나 MINT 자체 시험이 있었다는 사실을 경쟁 OSS의 L4 비교 검증으로 바꾸지 않는다.

## 종류와 프로젝트별 판정

아래 10개는 clone HEAD를 이번에 확인했다. `L2/부분 L3`는 유용한 구현 분석이 있지만 끝까지 연결한 증거가 부족하다는 뜻이다.

| 대상·고정 HEAD 앞 7자리 | 기존 조사와 깊이 | 핵심 공백 / 보완 방향 |
| --- | --- | --- |
| IBM ContextForge `5735c9d` | PDP·OAuth·가드레일·캐시·감사·수명 관리, L2/부분 L3 | 훅 실행 엔진의 실제 패키지·활성 설정·예외/timeout 배선, 회수 뒤 캐시와 진행 호출 효과 |
| IBM CPEX `ae26938` | Rust 탐지기·Redis Lua·Python bridge, L2 | ContextForge가 고정한 패키지와 이 clone의 버전 대응, 최종 fail_mode·Redis 장애/다중 worker·클러스터 조건 |
| Microsoft MCP Gateway `3594c4e` | Entra·소유권/역할·세션 프록시·K8s 수명, L2/부분 L3 | 관리 API와 실제 tools/call 권한의 연결, 세션 주체 결속·삭제 후 진행 호출·재시작 |
| Microsoft Wassette `742ebb7` | WASI·HTTP host·파일 권한, L2 | 정책 파싱→runtime 적용 전 경로, allow/deny 우선순위·redirect/DNS·실행 중 회수와 취소 재현 |
| Azure AI-Gateway `1679e31` | APIM XML·DCR/PKCE 관련 랩 선별, L2 | 소스 예제와 비공개 APIM 서비스 경계, 읽지 않은 랩, 정책 오류/동의/철회 경로 |
| Azure remote-mcp-apim `130c553` | OAuth 프록시 XML, L2 | 복제된 AI-Gateway 예제와 중복 제거, 원 토큰 보관/회수·배포판 대응. 독립 게이트웨이 1종으로 부풀리지 않음 |
| Microsoft agent-framework `4b1c231` | MCP approval_mode·도구 로딩 선별, L2 | 승인 인자 결속·재개/중복/취소·세션 소유권. 하네스 SDK 승인과 원격 Gateway 강제 통제를 구분 |
| Microsoft PyRIT `ea9d0b4` | MCP target/세션·주입 시드, L2의 좁은 범위 | scorer·converter·공격 실행 루프·오탐·정상 과업·독립 효과. 시드 보유만으로 레드팀 체계 완료 아님 |
| Microsoft AGT `5233029` | scanner·훅·규칙 후보와 과거 부분 채택, L2 | 제품 우열 표의 동일 조건 근거 부족. 서명/HMAC/해시·발견/차단의 서로 다른 보장을 다시 분리 |
| LiteLLM `f8e456d` | MCP 권한·alias·서버/팀/키·관리 API, L2/부분 L3 | 인증 resolver 전체 호출자, 목록/실행 일치, 세션·OAuth 회수·fallback·사후 결과·다중 worker, LLM 경로와 MCP 경로 각각 추적 |

9/10 clone이 IBM 또는 Microsoft/Azure 계열이다. Python·Rust·C#·APIM·SDK·레드팀까지 분야는 있지만, 컨테이너 MCP 운영과 별도 공급자의 집계/스캐너는 소스 분석이 약하다. **클론된 10개 중 최신 solutions 카탈로그에 들어 있는 것은 5개**다. 나머지 Azure 2개·agent-framework·PyRIT·AGT는 상세 문서에 흩어져 있어 요약만 읽는 Claude가 놓칠 수 있다.

## 요약의 품질과 신뢰성

잘된 부분은 commit/라이선스/소스 위치와 채택 후보·미검증 범위를 구분하는 최신 `solutions/*.md`, 실제 루틴의 오류 처리와 상태 저장소까지 적은 옛 상세 절이다. 현재 소스 발췌 21개는 원본 blob과 일치한다.

보완할 부분은 다음과 같다.

1. **상충 결론**: 옛 IBM 문서의 “기본값 전 항목 disabled”는 같은 commit `plugins/config.yaml:99`의 PII `enforce`와 모순된다. 최신 IBM 요약은 이미 정정했지만 옛 본문이 남아 있었다. 이번에는 상세 보고서 입구에 정정/우선 참조를 추가했고, 본문 전체를 새로 검증했다고 표시하지 않았다.
2. **부재·우위 단정**: grep 0건을 제품 전체의 “없음”으로, 서로 다른 계층을 “동등 이상/우리가 앞섬”으로 쓰는 옛 표가 있다. 검색 범위·관련 호출 경로·동일 조건 결과를 갖추기 전에는 정적 미발견/비교 미확인으로 다룬다.
3. **판본 혼합**: LiteLLM 설치 소스 1.89.4·과거 1.104 조사·고정 clone 1.102.0·Compose 1.102.1·후보 1.105.0은 별개다. 검토 release·실제 이미지/package·보안 패치 이력을 연결해야 한다. shallow clone 자체는 정적 분석 결함이 아니며, 관련 수정 이력이 필요할 때만 추가 fetch한다.
4. **경로와 시험의 단절**: 제품 대조 21건은 부분 소스/문서 대응이며 동등 시험이 아니다. 연동 조건 50건은 모두 `not_run`이다. 별도 과거 MINT 시험이 없는 뜻이 아니라, 이 비교/조건에 연결된 실행 근거가 부족하다는 뜻이다.
5. **재사용 의존성의 깊이**: `oss-reuse.json` 8개는 메타데이터 또는 기존 로컬 연동 확인이 주다. OPA·Presidio·Gitleaks·Authlib를 사용한다는 사실과 upstream 오류/기본값까지 분석했다는 사실을 분리해야 한다. 제품 전체를 다 읽는 대신 실제 사용 API·설정·장애 경계에 집중한다.
6. **요약→구현 연결**: 각 핵심 관찰마다 우리 코드 심볼·REQ/DEV·채택/보류 이유·남은 반례가 필요하다. 상세 문서와 최신 카드의 정정 관계, 미독 범위도 카드에서 바로 보여야 한다.

## 보완 작업 순서와 완료 조건

담당·전체 상태는 [단일 백로그 DEV-47](../../status/backlog.md)에 둔다. 아래는 그 작업의 세부 수행 순서다. 기간 추정이나 자동 실행 약속은 아니다.

| 순서 | 작업·선정 이유 | 분석할 범위 | 완료 산출물·판정 기준 |
| --- | --- | --- | --- |
| 1 / 먼저 | 정본·판본·주장 정리 | 위 10개 clone와 누락된 5개 카드, IBM/AGT/MS/LiteLLM 옛 결론, 관련 라이선스·NOTICE·공식 보안 공지 | 10개가 한 진입점에서 보임. 각 주장에 관찰/추론/미확인, 버전과 정정 관계가 있음. 부재·우위는 검증 근거가 없으면 미확인. 이번 감사/입구 경고는 완료, 상세 재판정은 남음 |
| 2 / 우선 | LiteLLM·ContextForge+CPEX·Microsoft Gateway의 핵심 경로 심화 | 실제 HTTP/MCP 입구부터 사용자→서버/도구 권한→계약/훅→upstream 자격→dispatch→결과/감사. 요청별/프로세스별/DB·Redis별 상태, 활성 설정, timeout·철회·재시작, 관련 upstream 시험 | 선택한 각 경로가 L3. 함수/호출자·설정·상태 전이·성공/실패 결정표, 기존 시험명/빈 곳, 우리 `core.py/upstream.py/mcp_facade.py/dispatch.py` 및 REQ 연결. DEV-29·41·43·44에 바로 쓸 수 있음 |
| 3 / DEV-38 전 | ToolHive 소스 확보·운영 경로, Wassette 재비교 | ToolHive는 기존 v0.54.0 검토 commit부터 clone·라이선스/버전 재확인, create/start/stop/reconcile·image/secret/network·stdio bridge 추적. 기존 Docker 방식과 운영 의존성 비교 | 승인 source→image digest→runtime ID→endpoint 결속, 장애 후 orphan/중복·회수/종료·network 기본값 표. Wassette의 Wasm 포팅 비용과 구분. 자동 client 등록이 MINT 경로를 우회하지 않아야 함. 채택/보류와 되돌릴 조건 제시 |
| 4 / 독립 비교 | MCPX와 전용 MCP 스캐너 조사 | 아래 공식 저장소에서 MCPX·Cisco MCP Scanner를 먼저 소스 고정. Snyk Agent Scan은 로컬/외부 API·라이선스·데이터 전송 범위를 먼저 확인하고 필요한 경로만 심화 | MCPX의 신원/도구 ACL·세션·outbound proxy 경계, scanner의 정적/동적/원격 판정·오류·외부 전송을 L3로 기록. 알려진 위협 이름만 비교하지 않음. DEV-02·41·46 입력/관측 후보를 도출 |
| 5 / 사용 경계 | 현재 쓰는 OSS와 평가 도구의 좁고 깊은 점검 | 실제 설치/lock/image 판본의 MCP SDK pagination/outputSchema/cancel, OPA timeout/비정상 응답, Presidio offset/언어/검사 실패, Gitleaks rule/ignore·exit, Authlib issuer/audience/JWKS·회수. PyRIT scorer/converter는 DEV-46에 필요한 부분 | clone·공식 배포 소스·기존 소스 중 이미 있는 것을 재사용. 매 의존성의 사용 API/설정→우리 호출자→실패 시 최종 결정→회귀 조건 연결. OpenBao/SSO 추가 도입 시 해당 공식 Agent/SDK 경계만 확장 |
| 6 / 채택 전 | 동일 조건 재현과 최종 요약 | 앞선 분석에서 결정에 필요한 기능만 선정하여 아래 공통 조건 실행 | 선택 기능 L4. run ID·commit·image·설정/policy hash·정상/음성·독립 수신/효과·복구 연결. 동일 조건을 만들 수 없으면 비교 불가 이유를 명시. 50조건을 일괄 통과로 올리지 않음 |

2~5는 서로 연결되는 부분만 조사한다. DEV-41~43의 재현·수정은 이 조사 전체 완료를 기다리지 않고 해당 경로의 근거를 먼저 사용한다. 모든 저장소 전체 정독이나 새 플랫폼 통째 이식은 완료 조건이 아니다. 비교를 위해 root 권한·토큰 패스스루·공유 직원 자격·실패 시 통과를 허용하지 않는다.

## 추가 조사 후보의 공식 출처

이번 웹 확인은 공식 소개/README·가이드 수준이다. 아래 후보의 본문 전체·최신 source commit·운영 보장을 확인한 것으로 쓰지 않는다. ToolHive 고정 commit은 [기존 검토 카드](../../solutions/toolhive-runtime.md)의 값이며 이번에는 해당 Git tree를 다시 확보하지 못했다. MCPX 하위 tree도 웹 도구에서 열리지 않아 root README와 폴더 존재까지만 확인했다.

| 후보 | 공식 출처 | 보완하려는 빈 곳 |
| --- | --- | --- |
| ToolHive | [공식 저장소](https://github.com/stacklok/toolhive), [문서](https://docs.stacklok.com/toolhive/) | 컨테이너 MCP 실행·수명·secret/network 운영. 기존 요약은 L1이며 deep source 완료가 아님 |
| MCPX | [Lunar 저장소](https://github.com/TheLunarCompany/lunar), [ACL 문서](https://docs.lunar.dev/mcpx/access_control_list/) | 독립 공급자의 집계/권한과 MCP 서버 outbound 통제를 분리 비교. root 라이선스 표지만 하위/상용 기능에 전이하지 않음 |
| Cisco MCP Scanner | [공식 저장소](https://github.com/cisco-ai-defense/mcp-scanner) | scanner의 입력·엔진·rule·오류 계약과 재현 가능한 비교 입력 |
| Snyk Agent Scan | [공식 저장소](https://github.com/snyk/agent-scan) | 로컬 발견/서버 접속과 서비스 기반 판정 경계. 공식 README는 설정 점검이 stdio 실행/remote 요청을 유발할 수 있고 출력 형식도 변한다고 설명하므로 읽기와 실행을 분리 |
| mcppipe | [공식 governance 설명](https://docs.mcppipe.dev/guides/governance/) | descriptor pinning·warn/block·capture 모드의 비교 조건. 이 조사에서 서버 구현의 OSS 여부는 입증하지 않았으며 clone 완료 대상으로 세지 않음 |
| 실제 의존성 | [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), [OPA](https://github.com/open-policy-agent/opa), [OpenBao](https://github.com/openbao/openbao) | 설치 판본과 공식 소스·지원 API·장애/회수 계약 대조. 공식 README 확인만으로 분석 단계 승격하지 않음 |

## 공통 분석 카드와 실험 조건

각 프로젝트는 1쪽 요약 → 경로별 상세 → 원본/시험 근거 순서로 읽게 한다. 요약은 다음을 빠짐없이 담는다.

1. 어떤 문제/계층인지, 선택한 이유와 제외한 범위.
2. 저장소·release/commit·라이선스/NOTICE·확보 hash·실제 읽은 파일/함수.
3. 입구·인증·권한/정책·실행·출력·감사와 상태 저장소를 연결한 호출/데이터 경로.
4. 기본 활성/설정별 결정, 오류·timeout·취소·회수·경쟁·재시작·복구. 미독 구간 명시.
5. upstream 시험·반례와 남은 실험. “코드가 있다”와 “실행해 효과가 있다” 분리.
6. MINT 코드 심볼·REQ/DEV·채택/보류·대체 가능한 기존 코드와 추가 운영 비용.

선택한 기능의 공통 시험에는 정상 도구 성공, 미등록 alias/빈 권한, 사용자·조직·서버 간 상태 혼선, 도구 계약 변경, 출력 schema/페이지, 정책/Redis/비밀 저장소 장애, 회전/철회와 진행 호출, 응답 유실 후 중복 실행, 재시작/종료 후 잔존 자원을 포함한다. 기능에 맞지 않는 조건은 사유를 적고 제외한다. 응답의 Allow/Block뿐 아니라 독립 DB 변화·수신 로그/패킷·잔여 runtime 및 정상 업무 성공·오탐·지연을 기록한다.

실제 OSS MCP에 합성 데이터와 격리 계정을 사용한다. 소스 읽기용 clone에서 외부 스크립트를 실행하지 않는다. 실행은 솔루션 기기, 관리 하네스는 PJ1이라는 저장소 규칙을 따른다. 현재 프로젝트의 운영 상태를 바꾸는 실행 계획은 해당 DEV 작업과 함께 구체화한다.

## Claude가 다음 작업을 시작할 때

DEV-47의 첫 결과는 “OSS를 더 찾음”이 아니라 **정정 관계와 누락 카드 연결**이다. 그다음 현재 구현에 바로 걸리는 LiteLLM 세션/권한·ContextForge 훅 오류 경로, DEV-38의 ToolHive lifecycle을 먼저 읽는다. 각 결론은 [증거 계약](../../methodology/evidence-contract.md)으로 연결하고 [후속 작업 안내](../review-2026-10-15/claude-next-work.md)의 DEV-41~46 검수와 중복 조사하지 않는다. 실행을 하지 않은 이번 감사로 WBS·요구사항·경쟁 우위의 검증 등급을 올리지 않는다.
