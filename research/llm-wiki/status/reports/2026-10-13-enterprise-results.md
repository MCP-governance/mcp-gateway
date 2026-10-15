# 기업 품질 기준·연동 분석과 구현 결과

작업 브랜치 `10/13-enterprise-interoperability`, 기준 커밋 `ab6936c64f3578de8360b840f1928681714fa7bb`. 팀원 작업과 분리해 진행한다. 코드·자료 분석, 회귀 검사, 실제 검사기 연동, 관리형 MCP 호출, 새 호환성 랩은 각각의 증거로 기록한다.

## 개발·자료 환경

| 정본 | 범위와 사용 방법 |
| --- | --- |
| [요구사항](../../analysis/requirements.json) | 16영역·80조건. ID·통과/음성 조건·우선순위·실제 함수/행/hash·시험 심볼·단언 행·run 근거·공백 |
| [코드 구조](../../analysis/code-structure.json) · [실제 경로 분석](../../analysis/README-code.md) | 40모듈·640함수 AST와 16단계 실제 신원→PAC→정책→공식 SDK→출력 검사→원장 경로. AST는 모든 본문 정독/보안 감사가 아님 |
| [제품 대조](../../analysis/competitor-mapping.json) | 8제품의 21개 구체 관찰. 고정 commit/file/line·공식 문서·우리 조건과 부분 대응. 같은 기능의 실행/보안 우위를 주장하지 않음 |
| [연동 제품](../../analysis/integrations.json) · [50조건](../../analysis/integration-cases.json) | LiteLLM34·secret16. 각기 다른 절차·전제·음성·실패 수정·공식 출처·코드 근거130개. 모두 acceptance 미실행 |
| [Excel](../../analysis/outputs/01a13365-enterprise/MCP_기업호환성_검증대장.xlsx) | 10시트, 필터·식별 열/행 고정·상태/우선순위 선택·COUNTIFS 집계. JSON 정본에서 재생성 |
| [MCP 후보](../../analysis/mcp-candidates.json) · [13실험](../../experiments/README.md) | 실제 상용/OSS만. 로컬 stdio/loopback, 자체 호스팅 HTTP, 원격 서비스 포함. 자체/mock MCP 서버 계획 폐기 |
| [위협표](../../threats/README.md) | 기존 두 XLSM 원본과 hash·24정책을 보존. 새 코드 통제 후보로 재연결; 실제 충족 자동 주장 없음 |

현재 새 요구사항 대장은 소스 후보56, 미충족19, 지정 단위 조건5, 실기기 전체조건 통과0이다. 단위 시험 수와 충족 조건 수는 다르다. 현황·백로그·실험 실패 수정안을 ID와 연결해 팀원이 같은 자료를 이어서 갱신한다. 구조/hash 갱신기는 기존 사람의 조건·결과·상태를 보존한다. 연동 생성기의 `--seed`는 기존 파일을 거부하고 `--refresh-evidence`는 기존 실행 결과를 보존한다.

## 이번 코드 변화와 한계

기준 커밋의 기존 구현에는 CPU·메모리·내부 DNS/TCP 연결 시간 표시, 계약 A→B→A 관측 일관성, 새 원장 v7 시각 무결성, refresh 경쟁 수정이 이미 있다. 이번에 추가한 변화는 아래와 같다.

| 변경 | 이유·검증 |
| --- | --- |
| 공식 MCP SDK `structuredContent` 보존·구형 client text fallback | 기존 façade가 검사된 구조화 결과를 버렸다. text/structured가 같은 안전 결과를 사용하도록 변경 |
| JSON 객체·NaN/Inf·rich 결과 경계 | 유효 JSON 객체만 구조화 반환. image/audio/resource/link는 검사 미지원으로 보류 유지 |
| key·숫자·key/value 문맥 검사 | 공식 Presidio ad-hoc recognizer로 sensitive key/숫자는 schema 변경 없이 보류. 저엔트로피 password/client_secret의 문맥도 검사 |
| 전체 결과 Gitleaks·decoded key/값 주입 검사 | JSON 전체 및 실제 줄바꿈 문자열을 검사해 text-only/escaped 결과 경계를 보강 |
| 반환·진단·실행 상태 | Block/Approval/withheld/unknown 잔여 payload 미반환. SDK 예외값 대신 타입/고정 문구, 오류 뒤 `result=None`, 실제 응답 직후 실행 상태 보존 |
| tracing·검사 기한 | Gateway/upstream span 자동 raw 예외 기록 비활성화와 정제 기록. 출력 대기/처리 전체30초 기한, 실패/초과 시 보류 |
| LiteLLM preflight | 실제 httpx·공식 MCP Client 사용. 병렬 경로/HTTPS/별도 보호 자격/구성 판본 검사와 선택적 private CA. 모델 응답·MCP initialize/list를 E2E 업무 성공과 구분 |

구조화된 결과의 추가 반환을 검토하면서 찾은 비밀/숫자/키 경계는 배포 전 확장 위험을 보강한 것이다. 기존 배포에서 실제 구조화 비밀 유출을 관찰했다고 주장하지 않는다. [단위 기록](2026-10-13-enterprise-unit-results.json), [실제 검사기 기록](2026-10-13-real-inspectors-results.json), [독립 경계 검토](2026-10-13-result-boundary-review.md)와 [실제 Claude 검토](2026-10-13-enterprise-claude-review.md)를 확인한다. 실제 검사기는 기존 기기의 별도 프로세스에 해당 소스 함수와 recognizer를 로드해 실행하며 서비스/배포 코드는 변경하지 않았다.

정상 숫자·boolean·빈 객체·null, 실제 string PII 마스킹, 민감 key·숫자 보류, 고/저 엔트로피 합성 Secret을 실제 Presidio/Gitleaks로 대조했다. 이 결과는 실제 MCP 서버 호출/기업 다국어 코퍼스 평가가 아니다. 이름·주소·계좌·선행0 소실, 동기 guard CPU 기한, outputSchema 승인·잠금, resources/prompts/sampling/tasks, rich content, 승인 REST projection과 SDK/서버의 전체 로그 경계는 미완료다.

## 실제 기기 관찰

[현재 readiness](2026-10-13-current-appliance-readiness.json)의 실행 revision은 `2e36095+dirty`, `llm_gateway=false`다. 기존 원격 repo의 endpoint3파일와 activity/main/console2파일, 총7개 미커밋 변경을 확인했다. 이 변경을 덮어쓰거나 새 Gateway 코드를 그 위에 배포하지 않았다. 현재 기기의 실측 available RAM 약9.6GiB,12vCPU, 디스크 여유922GiB를 기준으로 새 호환성 랩을 별도 경로·Compose project에서 구축한다.

PJ1의 fresh 보호 UID/프로필 Codex 세션 `01a13514-6aac-7331-9219-c91e7acc57fd`에서 공식 GitHub `list_commits`를 정확히1회 호출했다. 원장743, `PAC-01`, attempted/executed=false. 요청한 정상 공개 commit 읽기는 실패했으며 계약/권한을 완화해 재호출하지 않았다. 독립 수신 측 증거가 없으므로 Gateway의 전송 전 거부 증거와 구분한다. 13개 설계 카드를 이 표본으로 완료시키지 않는다.

사용자가 실제 LiteLLM/secret 환경이 없어 직접 구축하도록 지시했다. 새 랩의 실행 판본·TLS·모델·제한 자격·OpenBao SDK 결과는 별도 랩 보고에 추가한다. 준비/구성만으로 호환성 성공을 쓰지 않는다. 기존 보호 하네스의 CONNECT/managed 신원 경계는 그대로 유지한다.

## 먼저 보강할 조건과 실패 시 수정

| 우선 | 조건 | 현재 공백·실패 시 수정 |
| --- | --- | --- |
| P0 | 기업 LiteLLM 모델 API와 private CA | 새 실제 모델·TLS 환경에서 정상/잘못된 CA·키·모델/stream/error를 확인. 고객 host와 managed CONNECT 정책을 명시 구성; 임의 host/shared token 우회 금지 |
| P0 | LiteLLM MCP aggregation 신원 | verified employee/device·audience·scope 교집합/OBO가 아직 연결되지 않음. session resource cap·unknown/empty scope를 official source pattern과 대조해 설계하고 전송 전 재검증 |
| P0 | secret 필수·expiry/회전 | 기존 credential path 미설정/endpoint 미매칭은 anonymous 반환, expires_at=0 허용. protected upstream의 credential_required 계약·유한 만료·조회 신선도·회전/철회·장애 거부를 추가해야 함 |
| P0 | outputSchema와 오류 전파 | 승인 계약에 출력 schema를 저장/검증, 고정 SDK2.2.0의 mismatch 예외·로그·원장·wire를 실제 OSS MCP로 검증 |
| P0 | 실제 MCP 정상·음성·복구 | E01~E13를 실제 판본·합성 자산·독립 효과로 실행. 정책 우선순위로 다른 거부가 나면 해당 통제의 성공으로 집계하지 않음 |
| P1 | approval freshness·cache/revoke·crash | fresh 요청자/권한, durable intent/uncertain, 중복 쓰기 재시도·예약 기한/worker 사망을 독립 효과와 대조 |
| P1 | 서버 outbound·OS 우회·관측 신선도 | Gateway 경유 통제와 endpoint 직접 stdio/IPv4·IPv6·MCP 서버 egress를 별도 검증. collector 전체 집계/성공·실패 시각 추가 |
| P1 | 운영 품질·HA | CPU/메모리·내부 연결 ms와 PC→기기 jitter/접속 실패/실제 packet loss를 구분. backup/restore/다중 replica는 독립 운영 시험 필요 |

## 문헌·OSS·스킬 반영

새 정식 저널3건은 Crossref/공급자 metadata·읽을 수 있는 초록/발췌까지만 확보했다. 정식 학회 MCPTox는 기존 확보 본문의 legitimate tool misuse/정상 질의·오염 설명 대조 방법을 검토했고, official GitHub 설정 override를 쓰는 실험으로 차용한다. RealFaultsMCP는 게재처 미확인 preprint로 분리했다. 유료/403 원문을 확보했다고 쓰지 않는다. [근거 방법론](../../methodology/evidence-methodology.md)에 판본·읽은 범위·비교 정상군·독립 효과·confidence interval·한계를 남겼다.

[공개 스킬/OSS](../../methodology/oss-and-skills.md)는 인기·commit·라이선스·읽은 범위를 기록했다. Microsoft wiki-researcher/wiki-architect의 원문→근거→통합 지식·출처/반례 방법을 적용했으며 전체 plugin 설치는 하지 않았다. Presidio·Gitleaks·OPA·공식 MCP SDK·httpx를 실제 변경에 사용하고 Toxiproxy·hvac·cloud SDK는 후보/실제 사용을 구분한다. stars를 신뢰성/성능의 증명으로 사용하지 않는다. 배포물과 검토용 HEAD·metadata hash·SRI·서명 검증·설치 상태를 분리한다.
