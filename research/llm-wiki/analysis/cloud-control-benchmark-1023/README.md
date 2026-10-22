# 클라우드 감사·LLM·MCP 통제 방식의 온프레미스 차용 벤치마크

확인일: 2026-10-23. 사용자 질문: "CloudTrail 같은 상용 솔루션처럼 클라우드의 방식을 온프레미스에 차용할 수는 없는가? CloudTrail 외의 클라우드 MCP·LLM 통제 솔루션 기능을 벤치마킹하라." 제품 설계 변경·배포 지시가 아니며 구현하지 않았다.

## 판단

**차용할 수 있다. 단, 차용 대상은 "기록 모델"과 "증거 신뢰 모델"이고, 관리형 분석 서비스와 클라우드 분류기 API는 차용 대상이 아니다.**

| 층 | 클라우드가 하는 일 | 온프레미스 차용 |
| --- | --- | --- |
| 기록 모델 | 제어 평면·데이터 평면 이벤트를 나눠 제어 평면은 항상 기록, 데이터 평면은 선택 기록 | 가능. MINT는 이미 두 테이블로 나눠 항상 기록한다. 부족한 것은 제어 평면 기록의 완전성과 해시 연결이다 |
| 증거 신뢰 모델 | 서명한 정기 digest를 로그와 분리해 보관하고 이전 digest 서명을 다음 digest에 넣는다 | 가능. 다만 클라우드와 달리 운영자와 관리자가 같은 조직이므로 서명 키·보관 위치를 DB 밖에 따로 둬야 효과가 있다 |
| 분석·분류 서비스 | 관리형 SQL 레이크, 호출률 기준선 탐지, 프롬프트 공격·유해 콘텐츠 분류 API | 서비스 자체는 불가. 기준선 탐지와 조회는 이미 배포한 OpenSearch·PostgreSQL로 대체 가능. 분류 API는 프롬프트·도구 응답이 조직 밖으로 나가므로 기본 경로에 넣지 않는다 |

우선 차용 순위(근거는 마지막 절): ① 제어 평면 변경 이벤트의 완전 기록·해시 연결, ② 서명 정기 digest와 오프라인 검증, ③ 정책 단위 그림자 모드와 승격 흐름, ④ 호출률·오류율 기준선 탐지, ⑤ "유효 정책·what-if" 조회.

가장 눈에 띄는 발견은 두 가지다. 첫째 `PUT /api/enforcement`(enforce↔monitor 전환)는 마지막 값만 덮어쓰고 변경 이력을 원장에 남기지 않는 것으로 코드에서 읽힌다. AWS 문서가 지적하듯 이 전환은 보호 장치를 끄는 가장 위험한 제어 평면 변경이다. 둘째 감사 체인의 head가 같은 PostgreSQL 안에만 있어서, 앞부분 폐기 봉인(서명 저널)을 제외하면 DB를 일관되게 다시 쓰는 경우를 구별하는 외부 증거를 코드에서 찾지 못했다(추론이며 실험하지 않았다).

## 읽은 근거와 판본

- 위키 재사용: 기존 `solutions/`·`catalogs/`·`analysis/competitor-mapping.json`에는 CloudTrail·Bedrock·Azure·Google·Cloudflare 제품 분석이 없었다(규제 문헌 속 단순 언급만 있었다). 중복 조사는 없고, Kong은 [기존 요약](../../solutions/kong-ai-gateway.md)을 재사용하며 이번에 다시 읽은 내용만 보강했다. LiteLLM·Microsoft 게이트웨이·AGT는 이번 질문(클라우드 방식)과 겹치지 않아 다시 읽지 않았다.
- 공식 문서 45건(문서 38건, 오픈소스 메타데이터 7건)의 URL·확보 시각·SHA-256·열람 범위는 [출처 manifest](cloud-control-benchmark-1023.sources.json)에 있다. 원본 HTML은 ignored `local-sources/cloud-control-benchmark-1023/`에 보존한다. 클라우드 관리형 서비스는 판본 번호가 없으므로 "문서 날짜 + 확보 시각"이 기준이다. AWS 페이지는 날짜를 표시하지 않아 확보 시각(2026-10-23)만 기준이다.
- 열람 수준: 대부분 도입부·핵심 기능·관련 절 읽기다. 전문 정독이 아니며 실제 서비스 시험은 하지 않았다. 항목별 열람 범위는 manifest의 `reading`에 있다.
- MINT 코드: `origin/main 7b7ad6d`. 경로는 `full_stack_lab/` 기준이며 아래 행 번호는 그 커밋의 파일이다. 코드 존재를 배포·활성화·실기기 통과로 세지 않았다.
- 제품별 요약: [클라우드 감사·AI 통제 제품 요약](../../solutions/cloud-control-planes.md).

## 비교표

범례. 열 "MINT 대응"은 코드에서 직접 확인한 것만 "있음"으로 쓰고, 이번 검색에서 못 찾은 것은 "미발견"이다. 미발견은 부재의 증명이 아니다.

| ID | 기능 | 클라우드·상용 근거 (문서 ID) | MINT 대응 (코드 근거) | 차용 판단·방법 |
| --- | --- | --- | --- | --- |
| F1 | 제어/데이터 평면 이벤트 분리 | AWS 관리 이벤트는 기본 기록, 데이터 이벤트는 기본 꺼짐·추가 요금(A3·A2). Azure Activity log는 제어 평면만 기본 수집·변경 불가(B1). GCP Admin Activity는 끌 수 없고 Data Access는 BigQuery 외 기본 꺼짐(C1) | 부분. 호출·연결 판정은 `decisions`(`audit.py:16-23`), 승인·보존 설정 등은 `approval_events`(`v2_tables.sql:218-230`). 둘 다 append-only 트리거(`agent_tables.sql:83-92`, `v2_tables.sql:252-255`). `approval_events`에는 해시 열이 없고, `enforcement` 전환은 `approval_events`를 쓰지 않는다(`core.py:1190-1198`, `main.py:981-987`) | 차용 가능(중). 두 평면을 "관리 변경/호출" 이름으로 한 조회·한 검증으로 묶고, 모든 설정 변경을 기록한다 |
| F2 | 로그 무결성 digest 체인 | AWS는 로그 파일마다 SHA-256, 매시간 digest(로그 해시 목록)를 SHA256withRSA로 서명하고 이전 digest 서명을 포함, 로그와 다른 폴더에 보관, 리전별 키(A1·A9). GCP는 항목 불변이라고만 표시(C1), Azure는 사용자가 변경·삭제 불가(B1). 서명·검증 방식은 둘 다 미확인 | 부분. 행 단위 해시 연결(`core.py:2039-2081`, `contract.py:110-143`), 전체 검증 `GET /api/audit/verify`(`main.py:996-999`), 내보내기 manifest SHA-256(`audit.py:84-96`). 폐기 봉인만 DB 밖 서명 저널(`retention.py:1-8`, `disposal.py:1`). 체인 head는 `audit_chain`(같은 DB)에만 있고(`core.py:2039,2079`), 주기 서명 digest·외부 보관은 미발견 | 차용 가능(소~중). 행 단위 체인은 AWS 파일 단위보다 촘촘하다. 부족한 것은 DB 밖 서명 앵커다 |
| F3 | 조직 단위 중앙 trail·위임 관리자 | AWS 조직 trail, 위임 관리자 최대 3개, 소유는 관리 계정 유지(A6·A8). Bedrock은 조직·OU·계정 단위로 가드레일 강제(D14). Model Armor floor 설정은 최소 보호선(F1). GCP는 폴더·조직 싱크(C2) | 부분. 단일 게이트웨이 전제이며 다중 복제는 "인스턴스별 체인 후 앵커"가 필요하다는 주석만 있다(`core.py:1987-1989`). 읽기 전용 감사자 역할은 미발견 | 단일 거점 온프레미스에는 부적합. 다거점·계열사 배치 때 거점 체인을 중앙 digest로 묶는 용도로 후속. 감사자 역할은 소규모로 차용 가능(사용자 결정 필요) |
| F4 | 이벤트 선택기·고급 필터 | AWS 고급 이벤트 선택기는 이벤트명·리소스·주체·읽기/쓰기 필드로 기록 대상을 고른다(A2). GCP Policy Denied는 제외 필터로 저장 제외 가능(C1) | 부분. 기록 단계 선택은 없고 모든 판정을 기록한다(`core.py:2036-2081`). 조회 필터는 판정·서버·주체·정책·이벤트 종류·실행 여부·시간·trace(`audit.py:25-62`). SIEM 전송 원천은 3개로 고정(`siem.py:15-19`). 전송 필터 유무는 파일 앞부분만 읽어 미확인 | 기록 단계 선택기는 부적합(증거 누락). 조회·SIEM 전달 단계 필드 선택기는 차용 가능(소) |
| F5 | 보존 계층·쿼리 레이크 | AWS 이벤트 이력 90일(A7), CloudTrail Lake는 SQL·ORC·불변 저장소, 보존 3,653일/2,557일, 2026-05-31부터 신규 고객 불가(A4). Azure 90일, 진단 설정으로 최대 12년(B1). GCP 폴더·조직 버킷은 보존 연장 불가(C2) | 있음(2계층). PostgreSQL 원본 + OpenSearch 3.8.0 색인(`siem/compose.yaml:9`, `siem.py:1`). 관할별 보존 하한과 만료 구간 서명 봉인(`retention.py:18-45`). 폐기 단계는 소유자 결정 대기로 모듈 머리글에 명시(`retention.py:7-8`) | 관리형 레이크는 불가·불필요. 장기 보관용 내보내기는 후속. Lake 신규 중단의 이유는 문서에 없어 추정하지 않는다 |
| F6 | 정책 안전 배포(그림자·초안·버전) | AgentCore Policy는 정책 단위 ACTIVE/LOG_ONLY와 엔진 단위 ENFORCE/LOG_ONLY, 결정이 뒤집힐 정책 집합 보고, 승격(D13). 모드 변경이 `UpdateGateway` 한 권한이며 엔진 제거도 같은 권한(D12). Bedrock 가드레일은 작업 초안→버전, 호출에 ID+버전 지정, 테스트 창(D1). Model Armor는 Inspect only→Inspect and block(F1). Cloudflare는 flag/block(G2) | 부분. 전역 enforce/monitor 한 스위치(`core.py:1179-1198`), monitor에서 `would_decision`·`would_policy_id` 기록(`core.py:2008-2009`), 정책 번들 SHA-256 판본(`core.py:480-492`), 기록한 `policy_input`을 후보 OPA에 재생해 `newly_executable` 등으로 분류(`replay.py:21-31,43-60`). 정책 단위 그림자는 미발견 | 차용 가능(중). 정책 단위 그림자와 재생 결과 요약, 승격 승인 기록을 추가한다 |
| F7 | 정책 평가 이유 반환 | AgentCore는 정책 결정 로그·CloudWatch 지표(D3). Model Armor는 발동·미발동 필터 상세 반환(F1). Prompt Shields는 `detected`/`filtered` 주석(E1). Cedar 진단 형식은 이번 확보 범위 밖이라 미확인 | 있음. OPA가 `policy_ids`를 반환(`opa/decision.rego:16-44`), 판정 행에 정책 id·사유·충돌·정책 판본 기록(`core.py:1995-2012`), 사람이 읽는 문장 변환(`activity.py:1-5,27`) | 차용 불필요. 미발동 정책 목록 반환 여부는 미확인 |
| F8 | 콘텐츠·프롬프트 공격 분류(가드레일) | Bedrock Guardrails: 콘텐츠·주제·단어·민감정보·근거성·자동 추론, 독립 `ApplyGuardrail` API(D1). Prompt Shields: 사용자 프롬프트·문서 공격, 에이전트 도구 응답 스캔은 미리보기(E1). Model Armor: 인젝션·PII·악성 URL, 입력/출력 템플릿 분리(F1). Cloudflare Guardrails(G2) | 부분. 입출력 검사·마스킹과 남은 Secret 검사(`core.py:1955-1966`), 도구 설명 poisoning 검사(`poisoning.py`) | 클라우드 분류 API를 기본 경로에 두는 것은 부적합(데이터가 조직 밖으로 나감). 입력/출력 정책 분리와 detected/filtered 이중 표기 개념만 차용 |
| F9 | MCP 게이트웨이 신원·도구 통제 | AgentCore Gateway(인바운드 OAuth, 아웃바운드 자격 주입, 도구 검색)와 Identity(워크로드 신원, 동의 포털)(D2·D5). APIM은 JWT·호출 제한·IP 필터·캐시이며 정책이 서버의 모든 도구에 일괄 적용된다고 읽힘(E2). Cloudflare 포털은 포털별 도구 큐레이션·별칭·서버별 OAuth·Code Mode(G3). Kong은 소비자·그룹별, 도구별 ACL(v3.13+, Enterprise)(H1) | 있음(범위별 상이). 도구 ACL·동의(`consent.py`)·도입 심사(`review.py`)는 기존 위키 분석 범위. 도구 별칭·포털별 큐레이션은 미확인 | 별칭·큐레이션은 정상 기능으로 차용 후보(이번 제안 5개 밖). 신원 기능은 중복 |
| F10 | 세션 인지(temporal) 정책 | AgentCore temporal 정책: 세션 안의 이전 행위(횟수·시간 창·누적합·선행 승인)로 판정. Dogwood 언어이며 Cedar 호환(D8) | 부분. 고정 패턴 하나(`sensitive_read_then_send`, `core.py:1324-1334`)와 호출량 한도. 사용자 정의 세션 규칙은 미발견 | 후속. 규칙 언어 도입은 크고 Dogwood 라이선스·판본은 미확인 |
| F11 | 이상 탐지(Insights) | CloudTrail Insights: 과거 이벤트로 호출률·오류율 기준선을 만들고 이탈 시 별도 이벤트, 별도 요금(A5) | 부분. `P-ANOMALY-*`·`P-VOLUME-*` 신호로 자동 중지(`ops_response.py:20-22,124-126`), 위험 점수(`core.py:1421`). 통계 기준선 방식은 미발견 | 차용 가능(중). SQL 윈도우 집계로 시작, OpenSearch Anomaly Detection(Apache-2.0, 릴리스 3.6.0.0, 배포 3.8.0과 호환 미확인) 검토 |
| F12 | 읽기 전용·교차 공유 접근 | CloudTrail 이벤트 저장소에 리소스 기반 정책으로 교차 계정 읽기(A4). GCP는 Data Access 열람 권한을 별도 역할로 분리(C1) | 미발견. 감사 API는 `admin_caller` 의존(`main.py:996-1067`) | 차용 가능(소). 감사 조회·내보내기·검증만 허용하는 역할. 단독 운영 결정과의 충돌은 사용자 확인 필요 |
| F13 | 페이로드 로깅 통제 | Bedrock 호출 로깅은 기본 꺼짐, 켜면 입출력 전문을 같은 계정·리전의 S3/CloudWatch에 저장(D4). Cloudflare는 기본 켜짐이고 요청 헤더로 로그와 본문 저장을 따로 끈다(G4) | 있음(보수적). 본문 대신 digest·크기·처리 결과만 저장(`core.py:1990-2011`, `audit.py:15-23`) | 본문 저장 옵션은 부적합(개인정보·데이터 거주 원칙 충돌). 현재 방식을 유지 |
| F14 | 서버·에이전트 레지스트리 | AWS는 CloudTrail 리소스 유형에 Agent Registry 항목(A2). APIM+API Center 등록·검색, Foundry 제어 평면은 온프레미스 포함 어디서든 에이전트·MCP 도구 등록(미리보기)(E3). Kong Konnect MCP Registry(기술 미리보기)(H1) | 있음. 도입 심사·레지스트리(`registry.py`, `review.py`) | 차용 불필요. Foundry는 클라우드 제어 평면이 온프레미스 자산을 관리하는 하이브리드이며 "클라우드 방식을 온프레미스에서 쓰는 것"과 다르다 |
| F15 | IAM 정책 시뮬레이터 | 이번에 AWS IAM 문서를 확보하지 않아 미확인. 가까운 근거는 Bedrock `DescribeEffectivePolicy`(계정별 실제 적용 정책 확인)(D14)와 AgentCore의 정책 검증·LOG_ONLY(D7·D13) | 부분. 로드한 정책에 격리 점검을 돌리는 경로(`ops_response.py:1`)와 재생(`replay.py`). 입력을 직접 넣어 보는 what-if API는 미발견 | 차용 가능(중). 호출 없이 판정과 적용 정책·사유를 반환 |
| F16 | 토큰 한도·캐시·부하 분산 | APIM 토큰 한도·시맨틱 캐시·로드 밸런서·서킷 브레이커(E3), Cloudflare 캐시·속도 제한·재시도·폴백(G1) | 범위 밖. LLM 호출 비용 통제는 LiteLLM 연동 영역 | 제외 |

## MINT에 이미 있는 것 (코드 근거)

- **append-only 원장과 해시 체인**: `decisions` 변경·삭제 거부 트리거(`gateway/app/agent_tables.sql:83-92`), 행 잠금 아래 `previous + fingerprint`로 다음 해시를 만들고 head를 갱신(`core.py:2039-2081`), 체인 버전과 열 집합(`contract.py:48-84`), 첫 불일치 행을 지목하는 검증(`contract.py:110-143`, `core.py:2151-2170`).
- **본문 미보관 감사 투영**: 조회·내보내기는 요청 본문·결과·정책 입력을 제외(`audit.py:15-23`), 내보내기는 정규화한 JSON의 SHA-256 manifest를 붙인다(`audit.py:84-96`). 이 manifest만으로는 원문 체인을 재검증할 수 없다고 파일에 명시되어 있다.
- **보존·폐기 봉인**: 관할별 하한(`retention.py:18-45`), 두 사람·만료 구간 검증을 거친 서명 저널 봉인(`retention.py:46-88`, `disposal.py:1`). 변경은 `approval_events`에 남는다(`retention.py:108-109`).
- **SIEM 연동**: 삽입 트리거로 `decisions`·`approval_events`·`ops_alerts`를 outbox에 적재(`siem_tables.sql:26-28`), OCSF 이벤트로 전송(`siem.py:1`), Vector→OpenSearch 색인(`siem/vector.yaml`). UID 불일치는 버리지 않고 `rejected` 색인으로 보낸다.
- **판정 사유와 정책 판본**: OPA `policy_ids`(`opa/decision.rego:16-44`), 판정 행의 사유·충돌·`policy_version`(`core.py:1995-2012`), 정책 번들 SHA-256 판본 전환(`core.py:480-492`).
- **그림자 모드와 재생**: monitor 모드와 `would_*` 기록(`core.py:1179-1198`, `2008-2009`), 과거 입력 재생 비교(`replay.py`).
- **이상·연쇄 신호와 자동 대응**: 위험 점수·민감 읽기 후 전송 패턴(`core.py:1324-1334`, `1421`), 이상·호출량 신호 기반 자동 중지(`ops_response.py:20-22`).

## 온프레미스로 차용 가능한 것

| 차용 | 필요한 OSS·구현량·제약 |
| --- | --- |
| 서명 정기 digest와 오프라인 검증 (F2) | 새 의존성 없음. 이미 쓰는 `cryptography` Ed25519(`disposal.py`의 서명 경로)를 재사용한다. 구현량 소~중. 제약: 서명 키와 digest 저장 위치가 원장 DB와 같은 호스트면 효과가 제한된다. 고객 SIEM·별도 저장소에 사본을 두는 운영 조건을 문서화해야 한다. 외부 투명성 로그로 Sigstore Rekor(Apache-2.0, v1.5.5)·Trillian(Apache-2.0, v1.8.0)이 있으나 운영 부담이 커 선택 항목으로만 본다 |
| 제어 평면 변경 이벤트 완전 기록·해시 연결 (F1) | 새 의존성 없음. `approval_events`에 해시 열을 더하거나 같은 체인에 합류. 구현량 중. 제약: 기존 행은 해시가 없으므로 `walk_chain`이 이미 처리하는 "체인 이전 행"(`contract.py:122-124`) 방식으로 구분한다. 체인 버전 상승과 기존 검증기·SIEM 투영 영향 확인 필요 |
| 정책 단위 그림자·승격 (F6) | OPA finding에 모드 속성. 구현량 중. 제약: 그림자 정책은 판정·호출 효과에 영향이 없어야 하고 `replay.py`와 같은 입력을 쓴다 |
| 기준선 이상 탐지 (F11) | PostgreSQL 윈도우 집계로 시작(새 의존성 없음), 필요 시 OpenSearch Anomaly Detection(Apache-2.0). 제약: 호환 판본과 학습 데이터 양 미확인, 오탐이 자동 중지로 이어지지 않게 알림부터 시작 |
| 유효 정책·what-if 조회 (F15) | 새 의존성 없음. 기존 OPA 호출과 `ops_response`의 격리 점검 경로 재사용. 구현량 소. 제약: 원문 인자 대신 요약 필드를 입력으로 받는다 |
| 읽기 전용 감사자 역할 (F12) | 새 의존성 없음. 구현량 소. 제약: 운영 단순화 결정과의 관계를 사용자와 확인 |
| 입력·출력 정책 분리, detected/filtered 이중 표기 (F8) | 개념만 차용. 구현량 소 |

## 차용 불가·부적합

| 항목 | 이유 |
| --- | --- |
| CloudTrail Lake 같은 관리형 SQL 레이크 (F5) | 관리형 서비스이며 AWS는 2026-05-31부터 신규 고객을 받지 않는다고 문서에 표시한다(A4). MINT는 PostgreSQL+OpenSearch로 같은 질의 요구를 이미 다룬다. 중단 이유는 문서에 없어 추정하지 않는다 |
| Prompt Shields·Model Armor·Bedrock Guardrails API를 기본 경로에 연결 (F8) | 프롬프트·도구 응답이 조직 밖으로 나가 온프레미스·데이터 거주 원칙과 충돌한다. 고객이 하이브리드를 허용할 때의 선택 연동은 별도 결정 |
| 기록 단계 이벤트 선택기 (F4) | 증거 원장에서 허용 이벤트를 빼면 사후 증명이 불가능하다. 조회·전달 단계에서만 선택한다 |
| 본문 전문 로깅 (F13) | 두 번째 사본이 되어 개인정보·보존 부담이 커진다. 현재 digest 방식을 유지한다 |
| 조직 trail·위임 관리자 (F3) | 단일 거점 온프레미스에는 해당 구조가 없다. 다거점 배치 때만 의미가 있다 |
| immudb 같은 변조 방지 DB | GitHub API가 라이선스를 표시하지 않았고(`NOASSERTION`) LICENSE 첫 줄이 Business Source License 계열이다(O6·O7). 상용 제품 내장에 쓸 수 있는지 확인 전에는 후보에서 제외한다 |

## 정정과 한계

- 클라우드 문서의 기능 목록은 MINT가 이를 본뜬 구현을 갖췄다는 뜻이 아니며, MINT 코드의 존재는 활성화·실기기 통과를 뜻하지 않는다. PostgreSQL 실제 경합·배포·PJ1 시험은 하지 않았다.
- "enforce 전환 이력 없음"과 "체인 head 외부 앵커 없음"은 지정한 파일들을 grep으로 읽은 결과다. 다른 경로(운영 스크립트·인프라 설정)에서 보완하는지는 확인하지 못했다.
- `PUT /api/enforcement` 설명 문자열은 "인증되고 기록된다"고 쓰여 있으나 기록 코드는 `gateway_settings`의 `updated_by`·`updated_at` 덮어쓰기뿐이다. 설명과 동작의 차이이므로 개발 시 확인한다.
- **미확인**: AWS IAM 정책 시뮬레이터 문서, Cedar 진단(결정에 기여한 정책) 형식, GCP 보존 수치(필요한 절을 읽지 않음), Entra 감사 로그 보존, Azure APIM의 도구별 정책 차등 여부(문서는 모든 도구에 일괄 적용이라고 읽힘), Bedrock·AgentCore 가격, Dogwood 라이선스·판본, OpenSearch 3.8.0과 Anomaly Detection 호환성, Cloudflare·Kong의 감사 로그 무결성 보장, 모든 제품의 실제 동작.
- 확보했으나 읽지 않은 문서: D11(AgentCore 정책 핵심 개념)·E4(Foundry 개요). 결론에 사용하지 않았다.
- 클라우드 제품 일부는 이름과 위치가 바뀌었다. Google의 Vertex AI Agent Engine 문서가 "Gemini Enterprise Agent Platform" 이름으로 제공되며(F2), 기존 명칭을 쓰는 자료와 섞지 않는다.

## MINT 개발 제안

정상 기능과 운영 편의를 우선했고, 모두 구현하지 않았다. 완료 조건은 제안 시점의 검수 기준이다.

1. **제어 평면 변경 이벤트의 완전 기록과 해시 연결** (CloudTrail 관리 이벤트, GCP Admin Activity).
   - 이유: 보호 장치 전환(`enforcement`)이 이력 없이 덮어써지고, `approval_events`는 변조 탐지가 없다. 운영자가 "누가 언제 무엇을 바꿨나"를 한 화면에서 보려면 필요하다.
   - 완료 조건: `gateway_settings` 쓰기 전부(최소 `enforcement`·`ledger_retention`·`contracts_lock_digest`)와 정책 판본 전환이 이전 값·새 값·행위자와 함께 승인 이벤트로 남는다. `approval_events`가 해시 연결되고 `/api/audit/verify`가 호출 이벤트와 관리 이벤트를 모두 검증해 첫 불일치 행을 지목한다. 변조·삭제 음성 시험이 통과한다. 감사 화면에 "관리 변경/호출" 구분 필터가 생긴다. 기존 행은 "체인 이전 행"으로 구분해 기존 검증이 깨지지 않는다.
2. **서명 정기 digest와 오프라인 검증** (CloudTrail 로그 무결성 검증).
   - 이유: 감사인에게 "이 기간 로그가 변하지 않았다"를 DB 접근 없이 증명하고, DB를 통째로 다시 쓰는 경우를 탐지한다.
   - 완료 조건: 설정 주기(기본 1시간)마다 구간 id 범위·head 해시·항목 수·이전 digest 해시·서명·정책 번들 해시를 담은 digest를 Ed25519로 서명해 DB 밖 저널과 SIEM 사본에 남긴다. 검증 도구가 내보낸 파일과 digest 체인만으로 ① 행 변조 ② 끝부분 절단 ③ 전체 재작성 ④ "구간에 이벤트 없음"을 판정하고, 앞의 세 경우는 음성 시험에서 탐지한다. 서명 키·저장 위치 분리 조건을 운영 문서에 적는다.
3. **정책 단위 그림자 모드와 승격 흐름** (AgentCore LOG_ONLY, Bedrock 초안→버전, Model Armor Inspect only).
   - 이유: 새 정책을 전역 monitor 전환 없이 실제 트래픽에 시험하고 영향 수를 보고 켤 수 있다. 운영자의 정책 변경 부담이 크게 줄어든다.
   - 완료 조건: 정책 단위로 `active`/`shadow`를 지정하고 shadow 정책은 판정·호출 효과에 영향이 없다는 시험이 통과한다. 재생 결과가 정책별 "새로 차단/새로 실행 가능" 건수 요약으로 API와 Console에 나온다. 승격은 두 사람 승인과 관리 이벤트 기록을 거친다.
4. **호출률·오류율 기준선 이상 탐지** (CloudTrail Insights).
   - 이유: 고정 임계값 신호에서 한 단계 나아가 주체·서버별 평소 대비 이탈을 알린다.
   - 완료 조건: 주체×서버(또는 도구)별 시간당 호출 수·오류율의 최근 N일 기준선과 이탈 배수를 `P-ANOMALY-*` 신호와 사람이 읽는 문장으로 낸다. 합성 정상 업무 패턴과 이상 패턴으로 오탐·미탐을 측정해 보고한다. 기본 동작은 알림이며 자동 중지는 별도 설정이다.
5. **유효 정책·what-if 조회** (Bedrock `DescribeEffectivePolicy`, IAM 시뮬레이터 개념은 문서 미확인).
   - 이유: "왜 막혔나, 이 입력이면 어떻게 되나"를 운영자가 호출 없이 바로 확인한다.
   - 완료 조건: (주체, 서버, 도구, 인자 요약)을 받아 MCP 호출 없이 OPA 판정, 적용 정책 id·사유·승인 필요 여부·정책 판본을 반환한다. 판정 행의 기록과 같은 입력 형식을 쓰며 원문 인자를 받지 않는다. 막힌 판정 상세 화면에서 같은 조회로 이동한다.

이번 제안에서 뺀 후속 후보: 읽기 전용 감사자 역할(F12), 도구 별칭·포털별 큐레이션(F9), 다거점 중앙 digest(F3), 사용자 정의 세션 규칙(F10).
