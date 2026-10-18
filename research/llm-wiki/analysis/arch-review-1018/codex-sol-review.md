| 번호 | 쪽 | 심각도(높음/중간/낮음) | 문제 | 근거 파일:행 | 수정안 |
| --- | --- | --- | --- | --- | --- |
| 1 | 1 | 높음 | **브라우저 콘솔의 기본 접속 경로가 빠졌다.** 관리자→콘솔을 `HTTPS`로만 표시한다. D-129의 기본 안내는 Tailscale IP의 HTTP `:8000`이다. HTTPS `:443`에서도 콘솔을 제공하므로 기존 선이 불가능한 것은 아니지만, 현재 그림으로는 두 진입 경로와 보호 방식 차이를 알 수 없다. | 그림 정의 `docs/ai/architecture/build_architecture.py:252-254`; 실제 게시 `full_stack_lab/compose.field.yaml:33-42`; 분기 `full_stack_lab/field/Caddyfile:90-101`; 결정 `docs/ai/DECISIONS.md:1410-1415` | 브라우저→Caddy에 `HTTP :8000 · Tailscale 내부`, 하네스·장치→Caddy에 `HTTPS :443`을 각각 표시한다. 브라우저 선도 Caddy에 연결한다. HTTP 구간의 보호는 TLS가 아닌 Tailscale 터널임을 경계에 적는다. |
| 2 | 1 | 높음 | **허브형 게이트웨이가 실제 실행 전·후 순서를 가린다.** Authlib·OPA·Presidio·Gitleaks로 뻗는 네 화살표는 병렬 검사처럼 보인다. 승인 입력 스키마, 자원 분류, 예약, 실행 직전 재검증, 출력 검사·반환 경로가 없다. 특히 출력 차단도 실행 전 차단으로 오인할 수 있다. | 그림 `docs/ai/architecture/build_architecture.py:191-195,242-245`; 호출 `full_stack_lab/gateway/app/core.py:1725-1726,1773-1803,1816-1869,1909-1939,1959-1967` | 게이트웨이를 번호가 있는 순차 단계로 펼친다. 외부 실행 노드를 사이에 두고 요청·응답을 서로 다른 행으로 그린다. `전송 전 차단`과 `실행 후 응답 보류`를 별도 종점으로 둔다. |
| 3 | 1 | 높음 | **예약과 실행 의도 기록을 구별할 수 없다.** README의 순서도조차 `정책→예약·실행 의도→계약 재확인`으로 묶지만, 현재 코드는 신원·초기 분류 뒤에 먼저 호출을 예약한다. 허용 뒤에는 예약을 갱신하고, 계약·정책 재검증 뒤에 실행 의도를 기록한다. 이 차이는 동시 호출·중복 실행 통제의 의미를 바꾼다. | 비교 대상 `README.md:44-46`; 실제 선행 예약 `full_stack_lab/gateway/app/core.py:1769-1780`; 예약 갱신 `full_stack_lab/gateway/app/core.py:1916-1929`; 최종 의도·전송 `full_stack_lab/gateway/app/core.py:1342-1374` | `호출 예약`을 입력 계약 검사 앞에 둔다. 허용 분기 뒤에 `예약 갱신`, 재검증 뒤에 `실행 의도 기록`을 따로 둔다. 아래 개편안의 기준은 README 요약보다 현재 코드다. |
| 4 | 1 | 높음 | **신원 확인을 Authlib의 매 호출 OIDC 검사로 읽게 한다.** Authlib는 `agent-service`에 설치된 선택형 조직 로그인 경로다. MCP 호출자는 transport Bearer에서 확인하고 관리형 장치 상태도 검사한다. 현재 그림은 로컬 인증·장치 토큰 발급 주체를 생략하고 Authlib를 게이트웨이의 동급 외부 검사기로 배치한다. | 그림 `docs/ai/architecture/build_architecture.py:192,243-247`; OIDC 설치 `full_stack_lab/gateway/app/agent_service.py:127`; Authlib 로그인·콜백 `full_stack_lab/gateway/app/oidc.py:112-165`; MCP 신원 `full_stack_lab/gateway/app/mcp_facade.py:43-53`; 장치 토큰 `full_stack_lab/gateway/app/idp.py:186-209` | `인증·장치 토큰 발급(agent-service)`을 관리면에 두고 Authlib를 내부 라이브러리로 표시한다. `조직 OIDC(선택)`만 고객 IdP와 연결한다. 호출 경로에는 `전송 토큰 검증·현재 계정/장치 상태`를 둔다. |
| 5 | 1 | 높음 | **Console→게이트웨이 관리 API 선이 없다.** 콘솔→DB만 있어 콘솔이 정책·종료·레지스트리를 DB 직접 변경만으로 관리하는 것처럼 보인다. 실제 콘솔은 허용된 `/gw/*` 요청을 인증·역할 확인 후 게이트웨이 API에 전달한다. | 그림 `docs/ai/architecture/build_architecture.py:252-255`; 중계 `full_stack_lab/gateway/app/agent_service.py:816-830,1646-1659`; 등록 사례 `full_stack_lab/gateway/app/agent_service.py:1532-1541` | `브라우저→Caddy→콘솔 서비스→게이트웨이 관리 API`를 추가한다. MCP 도구 호출선과 구별하고, 콘솔이 직접 관리하는 신청·계정 DB 접근만 별도 선으로 남긴다. |
| 6 | 1 | 높음 | **OS 이벤트의 서버측 수신 주체가 틀렸다.** OS 관측기→관리 콘솔 직결로 그렸지만, `/api/endpoint/*`는 HTTPS Caddy가 게이트웨이로 보낸다. 관리형 정책 조회·하트비트의 왕복 경로도 없다. | 그림 `docs/ai/architecture/build_architecture.py:261`; 관측 전송 `endpoint-agent/os-observer.py:134-138`; 라우팅 `full_stack_lab/field/Caddyfile:66-70`; 정책·하트비트 `full_stack_lab/gateway/app/main.py:1267-1287` | `보호 서비스/관측기→Caddy :443→엔드포인트 API(게이트웨이)→DB`로 고친다. 정책 응답은 반대 방향, 콘솔 조회는 관리 API 선으로 표현한다. |
| 7 | 1 | 높음 | **보호 서비스와 자격 경계가 빠졌다.** 관리 계정 안의 헤더 헬퍼만으로 장치 인증을 설명할 수 없다. 실제 장치 키 보유·정책 확인·하트비트·MCP JWT 수령은 root 서비스가 하고, 헬퍼에는 UID를 확인한 로컬 소켓으로 짧은 토큰을 제공한다. | 그림 `docs/ai/architecture/build_architecture.py:154,178-180`; 보호 서비스 `endpoint-agent/managed-linux.py:260-284,295-331`; 발급 `full_stack_lab/gateway/app/idp.py:186-209`; 비교 `README.md:15-17` | 직원 PC를 `일반 직원`, `관리 계정`, `보호 서비스·OS 통제`로 나눈다. `장치 키→발급 API`와 `짧은 MCP 토큰→헬퍼→하네스`를 다른 선으로 그린다. 장치 키를 하네스에 주는 선은 그리지 않는다. |
| 8 | 1 | 높음 | **직원 토큰과 업스트림 자격의 교체 지점이 보이지 않는다.** 하네스에서 등록 MCP까지 같은 노란 선이 이어져 직원 Bearer가 외부 서버까지 전달되는 것으로 읽힌다. 실제 외부 자격은 운영자가 별도로 제공하고 endpoint·허용 주체·기한을 검사한다. | 그림 `docs/ai/architecture/build_architecture.py:238-245`; 자격 선택 `full_stack_lab/gateway/app/upstream.py:39-76`; 설정·마운트 `full_stack_lab/compose.yaml:136,168`; 비교 `README.md:37` | 게이트웨이 안에 `업스트림 자격 선택`을 둔다. 입구에는 `직원 MCP 토큰`, 출구에는 `별도 공급자 자격 또는 무자격 공개 API`를 붙이고 `직원 토큰 미전달`을 명시한다. OpenBao 시험 아이콘을 현재 자격 경로의 대체 증거로 쓰지 않는다. |
| 9 | 1 | 높음 | **도입 검증→내부 Git→실행기의 직렬선이 사람의 승인·등록을 가린다.** 검사 완료만으로 사내 게시·실행·호출 허용까지 이어지는 것처럼 보인다. 실제 소스 검증, 독립 승인·사본 해시 대조, 관리자 실행 요청, 실행 확인, 게이트웨이 등록은 별도 단계다. 원격 MCP는 소스 스캔 대신 계약 심사 경로를 탄다. | 그림 `docs/ai/architecture/build_architecture.py:255-258`; 원격 분기 `full_stack_lab/gateway/app/agent_service.py:1091-1098,1305-1338`; 소스 승인 `full_stack_lab/gateway/app/agent_service.py:1353-1392`; 실행 요청 `full_stack_lab/gateway/app/agent_service.py:1145-1174`; 등록 `full_stack_lab/gateway/app/agent_service.py:1511-1541`; 런타임 확인 `full_stack_lab/runtime/worker.py:400-425` | 호출면 아래에 도입 관리 흐름을 둔다. 소스/원격 분기, `독립 승인`, `실행 요청`, `계약·도구 등록`을 각각 표시한다. 워커는 DB 대기열을 읽고, 내부 Git은 실행기가 읽는 자료 저장소로 그린다. |
| 10 | 1 | 중간 | **승인 계약·레지스트리·이용 관계가 없다.** 보안 정책 50이라는 아이콘은 어떤 승인값을 호출과 비교하는지 설명하지 못한다. 실제 도구별 활성화·설명/스키마 해시·허용 주체·자원·기한·종료 상태가 판정 입력이다. | 그림 `docs/ai/architecture/build_architecture.py:222-225`; 등록 전제 `full_stack_lab/gateway/app/core.py:526-542`; 실시간 계약 `full_stack_lab/gateway/app/core.py:1276-1299`; 이용 관계 `full_stack_lab/gateway/app/core.py:1030-1044`; 저장소 `full_stack_lab/compose.yaml:125-127,162-168` | `승인 카탈로그·계약`과 `조직/자원·이용 관계`를 공유 데이터 그룹에 두고 입력 계약·OPA·실행 직전 재검증에 연결한다. 서버 등록이 자원 접근 전체의 승인이 아님을 이름에 드러낸다. |
| 11 | 1 | 중간 | **검사 도구의 실행 위치·용도가 불분명하고 도입 Gitleaks가 빠졌다.** Gitleaks는 호출 검사에서 게이트웨이 프로세스의 공유 라이브러리이며, 도입 워커에서는 별도 명령으로 실행된다. 도입 검사 그룹에는 Syft·Trivy·Semgrep만 있다. Presidio도 실제로 분석기와 익명화 서비스로 나뉜다. | 그림 `docs/ai/architecture/build_architecture.py:194-195,203-205`; Gitleaks 내장 방식 `full_stack_lab/gateway/app/secret_scan.py:1-8,23-37`; 도입 검사 `full_stack_lab/supply_chain/intake_worker.py:247-255`; Presidio 배치 `full_stack_lab/compose.yaml:91-112,152-153` | 게이트웨이 내부에 `Gitleaks·텍스트 검사`, 서비스 의존성에 `Presidio 분석/마스킹`을 둔다. 도입 워커의 도구 목록에 Gitleaks를 추가한다. 동일 OSS의 재사용은 같은 이름에 실행 위치를 붙여 구별한다. |
| 12 | 1 | 높음 | **실행 전용 출구 프록시가 막다른 노드다.** MarkItDown→프록시만 있고 프록시→심사 목적지 선이 없다. 실행 격리망과 외부 출구망의 두 접속 경계가 생략된다. 실행기가 Docker 제어권을 가진다는 더 강한 관리 권한도 드러나지 않는다. | 그림 `docs/ai/architecture/build_architecture.py:162,202,207-208,258-259`; 실행 망·프록시 `full_stack_lab/runtime/worker.py:116-136,349-374`; 엔진 소켓 `full_stack_lab/compose.field.yaml:127-152` | 격리 실행망에는 승인 MCP와 프록시의 내부 접속면을, 바깥에는 프록시의 출구 접속면과 `심사 목적지`를 둔다. `실행기→Docker Engine→컨테이너/망 생성`은 별도 관리선으로 그린다. 게이트웨이의 호출선과 섞지 않는다. |
| 13 | 1 | 높음 | **서로 다른 배치의 신뢰 영역이 한 장에 섞였다.** 등록 MCP 그룹은 원격 GitHub·Context7과 선택 기동하는 랩 서버를 같은 영역에 둔다. 반대로 LiteLLM·Ollama·OpenBao·회사 시스템 모사는 기업·외부 레인 안에 있지만 목록에는 솔루션 기기/랩으로 적혀 있다. 기능 분류를 물리적 위치로 오인하게 한다. | 그림 `docs/ai/architecture/build_architecture.py:150-166,209-221`; 위치·범위 `docs/ai/architecture/components.psv:45-58`; 기본 field와 랩 분리 `full_stack_lab/console.sh:256-289` | 주 그림은 field 제품 경로로 고정한다. 원격 MCP는 외부 제공자 경계에, 실행 MCP는 솔루션 기기 안 격리망에 둔다. 랩·연동 시험은 별도 작은 삽화로 옮기고 주 호출선에서 제외한다. |
| 14 | 1 | 중간 | **SIEM 워커 입력이 없고 상태도 잘못 읽힌다.** 워커→SIEM 점선만 있어 Jaeger가 원천인지 DB가 원천인지 알 수 없다. 워커는 실선 테두리로 기본 사용 중처럼 보이지만 목록은 `구현(꺼짐)`, 실제 기동은 선택 옵션이다. OCSF는 프로토콜이 아닌 전송 형식이다. | 그림 `docs/ai/architecture/build_architecture.py:196-197,248-249`; 상태 `docs/ai/architecture/components.psv:34-35`; 원천 트리거 `full_stack_lab/gateway/app/siem_tables.sql:3-28`; 전송 `full_stack_lab/gateway/app/siem.py:109-135`; 선택 기동 `full_stack_lab/console.sh:257,266,275` | `DB 원장·승인·경보→영속 전송 대기열→SIEM 워커(선택)→고객 SIEM`을 그린다. 외부 선은 `HTTPS · OCSF JSON`, 워커는 `구현·기본 꺼짐`으로 표시한다. Jaeger는 별도 OTLP 경로다. |
| 15 | 1 | 높음 | **종료·폐기가 연결 없는 휴지통으로 축소됐다.** 이용 관계 중단, 잔존 설정, 조직 자격, 제공자 보유 하위 자격의 회수·증거·등급 연결이 없다. 삭제 아이콘은 자격 제거와 C4 확인을 같은 것으로 오해하게 한다. | 그림 `docs/ai/architecture/build_architecture.py:222-225`; 모델 `docs/ai/TERMINATION_MODEL.md:10-47,69-85`; 실행 직전 종료 거부 `full_stack_lab/gateway/app/core.py:1342-1350`; 실행 자원 정지 `full_stack_lab/runtime/worker.py:450-481` | `종료 케이스·회수 대상·상태 증거·C1~C4/T1~T3 판정`을 관리면에 둔다. 게이트웨이 차단, 실행기 정지, 엔드포인트 잔존 관측, IdP/제공자 자격 확인과 연결한다. 외부 제공자 미확인은 경계 밖에 남긴다. |
| 16 | 1 | 높음 | **비인가 로컬 MCP의 단일 빨간 차단선이 보장 범위를 과장한다.** 계정 그룹에서 곧바로 차단 아이콘으로 연결해 OS·사용자·하네스·권한 차이를 숨긴다. Windows는 시험 중인데 Linux와 같은 확정 차단 모양이다. 일반 직원의 다른 클라이언트·직접 API와 sudo/docker 보유 계정은 별도 경계다. | 그림 `docs/ai/architecture/build_architecture.py:183,187,260`; 보장 한계 `docs/ai/SECURITY_BOUNDARIES.md:11-30`; 상태 `docs/ai/architecture/components.psv:15-17`; Linux 권한 경계 `endpoint-agent/managed-linux.py:2-6` | 빨간 선의 출발점을 실제 AppArmor/nftables 등으로 옮기고 `관리 계정·지원 경로`를 붙인다. Windows는 `시험 중·효과 미확인 범위 별도`로 표시한다. 다른 권한 계정의 우회 가능성은 차단선 바깥에 둔다. |
| 17 | 1 | 중간 | **개발 예정 네 통제가 파이프라인과 단절됐다.** 바닥의 사용자 동의·전송 목적·입력 마스킹·중요정보 전파는 어느 전송을 언제 제한하는지 알 수 없다. 신청 시 동의 이벤트, 기존 입력 탐지, 조회 후 송신 탐지와 새 요구를 혼동할 수 있다. | 그림 `docs/ai/architecture/build_architecture.py:226-230`; 미착수 범위 `research/llm-wiki/status/backlog.md:59,65-67`; 기존 동의 `full_stack_lab/gateway/app/agent_service.py:1048-1065`; 기존 연속 호출 탐지 `full_stack_lab/gateway/app/core.py:1017-1027`; 기존 입력 검사 `full_stack_lab/gateway/app/core.py:1816-1828` | `예정 · POL-08/26/31/33` 꼬리표를 해당 단계와 점선으로 연결한다. POL-33은 출력→다음 입력의 상태 연결도 그린다. 세부 접속점은 아래 제안 표를 따른다. |
| 18 | 1 | 중간 | **제품 경로와 개발 관리 산출물이 같은 거버넌스 그룹에 있다.** 통합 시트는 개발 관리 정본이며 런타임 판정 저장소가 아니다. ToolHive는 실행기 대체 후보, 효과 비교 평가는 제품 외 도구인데 주 배치 안에 섞여 제품 기능으로 읽힌다. | 그림 `docs/ai/architecture/build_architecture.py:206,222-235`; 용도 `docs/ai/architecture/components.psv:44,61,64`; 개발 관리 분리 `docs/ai/DECISIONS.md:1417-1421`; 제품 외 평가 `research/llm-wiki/status/backlog.md:73` | 통합 시트·규제 참고·평가 도구·대체 후보를 본체 밖 `개발·검토 자료`로 옮긴다. 정책 문서 50개를 실행 가능한 규칙 50개의 증거처럼 표시하지 않는다. |
| 19 | 1 | 낮음 | **Playwright가 랩 서버 수에 중복 포함된다.** `랩 MCP 10종`에는 playwright가 포함되는데 옆에 별도 Playwright 노드가 있어 11종 또는 별도 배치로 읽힌다. | 그림 `docs/ai/architecture/build_architecture.py:211-212`; 구성 목록 `docs/ai/architecture/components.psv:48-49`; 기동 목록 `full_stack_lab/console.sh:260-261` | `랩 MCP 10종(Playwright 포함)` 한 노드로 줄이거나, 10종 그룹을 펼쳐 Playwright를 그 안에 한 번만 넣는다. |
| 20 | 1 | 중간 | **큰 컨테이너 테두리에 붙는 선과 반복 교차가 통제 주체를 모호하게 한다.** `gw` 박스가 원장·Jaeger·MarkItDown 선의 출발점이고, `mgmt` 박스가 도입선의 출발점이다. 모델·OIDC 선은 여러 영역을 가로지른다. 심사자가 선을 따라도 어떤 프로세스의 어떤 동작인지 확정하기 어렵다. | 그림의 박스·노드 `docs/ai/architecture/build_architecture.py:157-160,191-202`; 박스 접속선 `docs/ai/architecture/build_architecture.py:247-255`; 계측 주체 `full_stack_lab/gateway/app/core.py:163-175`; 실제 관리 주체 `full_stack_lab/gateway/app/agent_service.py:1024-1065` | 통신선은 이름 있는 노드에만 연결한다. 모델 경로는 위, 요청/응답은 가운데, 도입·운영은 아래에 둔다. 영역을 건너는 긴 선에는 접속 번호를 쓰고 단순 교차에는 접속점을 찍지 않는다. |
| 21 | 2 | 중간 | **통합 시트·Git push 선을 MCP 호출로 분류한다.** 노란색 범례는 MCP지만 Git push와 시트 연동은 그 자체로 MCP라는 근거가 없다. 현재 CSV 조회 구현도 HTTPS 요청이다. | `docs/ai/architecture/build_architecture.py:330-332`; 색 의미 `docs/ai/architecture/README.md:12`; CSV 구현 `research/llm-wiki/tools/sheet_pull.py:13,35-43` | Git/HTTPS 개발 데이터선으로 바꾼다. 별도로 실제 MCP로 수행한 작업이라면 그 클라이언트·서버 경로를 특정한다. |
| 22 | 3 | 높음 | **OS 이벤트가 Caddy를 우회한다.** 엔드포인트 API로 곧장 들어가는 선은 실제 공개 경로와 다르다. | 그림 `docs/ai/architecture/build_architecture.py:401,408`; `full_stack_lab/field/Caddyfile:66-70`; `full_stack_lab/compose.field.yaml:39-42` | 두 OS 관측기→HTTPS :443 Caddy→게이트웨이 엔드포인트 API로 고친다. |
| 23 | 3 | 높음 | **외부 LLM 제공자가 솔루션 기기 안에 있다.** 모델 API의 신뢰 경계·외부 전송이 사라진다. | 그림 `docs/ai/architecture/build_architecture.py:350,381-382,405`; 실제 위치 `docs/ai/architecture/components.psv:52` | 제공자를 솔루션 경계 밖으로 옮기고 모델 프록시 출구에서 경계를 넘긴다. |
| 24 | 3 | 중간 | **키트 발급자를 관리자 하나로 고정한다.** 실제 키트는 로그인한 사용자의 principal에 enrollment를 묶는다. 관리자 별도 활성화와 키트 소유자를 혼동한다. | 그림 `docs/ai/architecture/build_architecture.py:359-363`; `full_stack_lab/gateway/app/agent_service.py:389-411`; 독립 활성화 `full_stack_lab/gateway/app/endpoint_plane.py:895-908` | `직원 로그인·개인 키트 받기→조직 관리자 설치→점검·등록→다른 관리자 활성화`로 역할을 구분한다. Linux의 sudo 표시는 Linux 절차에만 둔다. |
| 25 | 3 | 중간 | **Windows 자격 헬퍼·보호 서비스가 빠지고 확정 차단선만 남았다.** 하네스에 토큰을 주는 실제 named pipe 경로를 설명하지 못한다. | 그림 `docs/ai/architecture/build_architecture.py:383-392,406-409`; `endpoint-agent/managed-windows.py:377-421,544-550,590-599`; 시험 상태 `docs/ai/architecture/components.psv:15-17` | Windows 보호 서비스·헤더 헬퍼와 별도 관리 계정을 추가한다. 방화벽 효과는 시험 상태와 함께 표시한다. |

## 1쪽 개편안

### 검토 기준과 한계

2026-10-18 작업 트리의 기준 커밋은 `d6679fd5454d239778029524e1651d21808baee5`, 시작 브랜치는 `10/18-remaining-features`다. 첨부 PNG 3장, 배치 정의·구성요소 목록, 위 표의 실제 소스를 정적으로 대조했다. 행 번호는 이 작업 트리 기준이며 배포 기기의 현재 바이너리·실행 상태를 입증하지 않는다. 스택 기동·배포·PJ1/pj3 시험은 하지 않았다. 요청의 `full_stack_lab/intake/` 대신 실제 구현 위치인 `full_stack_lab/supply_chain/intake_worker.py`를 확인했다. 검토 중 다른 작업의 `agent_contract.py`·`review.py`·`v2_tables.sql` 변경과 새 `consent.py`가 나타났다. 이 파일들은 보존했다. 새 동의 모듈은 읽었으나 마지막 확인 시점의 `core.py` 등 다른 Python 모듈에서 이 모듈을 호출하는 연결은 확인하지 못했다. 아래의 예정 표기는 배포 완료 판정이 아니며, 동시에 진행 중인 구현을 부재로 단정하지 않는다.

원격 HEAD 조회는 네트워크 연결 차단으로 실패했고, 새 브랜치 `10/18-arch-adversarial-review` 생성은 공통 Git 디렉터리의 ref 쓰기 권한 거부로 실패했다. 기존 브랜치·커밋은 유지한다. 사용자 지시대로 이 보고서 한 파일만 작성하며 현황·백로그·생성물·코드·기존 구조도는 변경하지 않는다.

이하 레이아웃·새 통제 접속점은 **설계 제안**이다. 현재 구현·배포 완료라는 뜻이 아니다. 표의 높은 심각도는 그림이 신뢰 경계·실행 여부·인가 보장을 잘못 전달할 위험을 뜻하며, 해당 코드의 취약점 확정 등급이 아니다. 2쪽의 DERP는 과거 실측 근거가 있어 오류로 세지 않았다(`research/llm-wiki/status/reports/2026-10-15-wbs-implementation.md:31`). 현재도 같은 중계 경로인지, pj2·팀원 장치가 지금 켜져 있는지는 미확인이다. 정적 코드로 현재 장치 상태를 추측해 오류로 단정하지 않는다.

### 레인·그룹·노드

1쪽의 중심을 아이콘 목록에서 **실행 전 판정과 실행 후 반환**으로 바꾼다. 왼쪽→오른쪽은 위치·신뢰 영역, 위→아래는 흐름 종류로 사용한다. 색으로는 흐름 종류만 구별하고 `구현`, `선택·기본 꺼짐`, `예정`, `시험` 상태는 글자와 테두리로 따로 표시한다.

| 레인 | 그룹·노드 목록 | 경계 표시 |
| --- | --- | --- |
| A 사용자 | 직원, 보안 관리자 브라우저 | 브라우저와 하네스를 별도 시작점으로 둔다. |
| B 직원 PC | 일반 직원 계정·진입 래퍼 / 관리 계정의 지원 하네스·관리형 설정·헤더 헬퍼 / 보호 서비스·장치 키·OS 관측 / AppArmor·nftables 또는 Windows 방화벽 | 일반 계정, 관리 계정, 관리자 권한의 세 구획. Linux·Windows는 대안 표기로 두고 효과 검증 범위를 붙인다. |
| C 사설 전송 | Tailscale 터널 경계 | Tailscale을 MCP 서버 같은 중계 프로세스 노드로 그리지 않는다. 터널 안의 HTTP·HTTPS·프록시 포트를 각각 적는다. |
| D 솔루션 기기 | 상단: 모델 프록시 / 중앙: Caddy, 게이트웨이 요청·응답 파이프라인 / 하단: 콘솔·인증 서비스, 엔드포인트 API, 도입 워커·실행기·내부 Git, 공유 저장소·감사·관측 | Caddy와 모델 프록시만 외부 게시. Authlib·Gitleaks·SDK는 프로세스 내부 의존성으로, OPA·Presidio·DB는 별도 서비스로 표시한다. |
| D 안의 하위 경계 | 승인 MCP별 격리 실행망: MarkItDown 등 승인 OSS MCP, 실행 전용 출구 프록시 | 실행기와 Docker Engine은 격리망 바깥의 권한 있는 제어면. 프록시는 격리망과 출구망의 두 접속면을 가진다. |
| E 외부 서비스 | 원격 MCP(GitHub·Context7), 모델 제공자, 조직 IdP(선택), 고객 SIEM(선택), 승인 MCP의 심사 목적지·하위 업무 API | 원격 MCP는 별도 제공자 경계로 감싼다. 원격 MCP→하위 API/자격은 제공자 영역이며 조직이 전부 관측·회수한다고 그리지 않는다. |
| 본체 밖 작은 삽화 | 랩 MCP 10종, LiteLLM·Ollama·OpenBao 시험, ToolHive 후보 | 실제 제품 요청선과 연결하지 않는다. 통합 시트·평가 도구·규제 참고 자료는 본체에서 빼고 별도 문서 링크로 보낸다. |

권장 세로 배치는 `모델 전송` / `MCP 요청` / `MCP 응답` / `도입·운영·종료`의 네 띠다. 요청과 응답은 오른쪽 끝의 같은 MCP 노드에서 연결한다. 응답 화살표가 요청 검사기를 역으로 통과하는 모양은 피한다.

### 게이트웨이 노드와 현재 코드 순서

다음 P 번호는 **새 그림의 단계 식별자**이며 POL/PAC 정책 번호가 아니다. 게이트웨이 내부의 처리 단계와 별도 서버를 같은 크기의 제품 아이콘으로 나열하지 않는다. 각 단계 아래에 호출하는 라이브러리·저장소를 작은 종속 노드로 둔다.

| 단계 | 노드 라벨·동작 | 코드 근거 |
| --- | --- | --- |
| P0 | **전송 토큰 검증**: MCP 입구의 인증된 principal·claims를 받는다. 인자·User-Agent·clientInfo를 권한 신원으로 쓰지 않는다. | `full_stack_lab/gateway/app/mcp_facade.py:43-53,73-90,216-220` |
| P1 | **주체·자원 분류와 초기 자격 확인**: 계정 조회·초기 자원/행위 분류, 활성 계정·등록 서버·관리형 장치·허용 주체 확인. 코드에서는 분류 계산이 활성 계정 검사보다 앞서지만 이를 인가 완료로 표현하지 않는다. | `full_stack_lab/gateway/app/core.py:1725-1726,1747-1767` |
| P2 | **호출 예약**: 동시성·호출량·중복 판정용 상태를 먼저 확보한다. 저장소 장애는 차단한다. | `full_stack_lab/gateway/app/core.py:1769-1780` |
| P3 | **입력 계약·상한 확인**: 인자 크기·NUL, 승인 입력 스키마, 대량 조회 경계를 확인한다. | `full_stack_lab/gateway/app/core.py:1782-1807` |
| P4 | **입력 검사**: 적용 대상 요청의 PII·Secret·비신뢰 지시를 검사한다. 외부 호스팅 MCP는 읽기 검색어도 전송 인자에 포함된다. | `full_stack_lab/gateway/app/core.py:1809-1833,1858-1859` |
| P5 | **정책 입력·OPA 판정**: 승인 계약·조직/자원·이용 관계·목적지·PAC·예약 문맥을 조립하고 판정한다. | `full_stack_lab/gateway/app/core.py:1835-1896` |
| P6 | **결과 분기**: 차단 / 승인 대기 / 허용·경보·제한 적용. 제한은 실제 전송 인자에 반영한다. 허용 분기만 예약을 갱신한다. 관찰 모드의 예외와 항상 집행되는 판정도 별도 상태값으로 남긴다. | `full_stack_lab/gateway/app/core.py:1875-1923` |
| P7 | **업스트림 연결·실행 직전 재검증**: 별도 자격으로 연결, 같은 연결의 `tools/list`로 계약·실제 전송 인자 스키마 확인, 승인·계정·장치·PAC/정책·제한 조건을 다시 검사한다. 도구 실행은 아직 하지 않았다. | `full_stack_lab/gateway/app/upstream.py:39-76`; `full_stack_lab/gateway/app/core.py:1271-1340` |
| P8 | **실행 의도 기록·최종 상태 확인**: 종료·계정·서버/도구·승인·중복·예약 상태를 마지막으로 확인한다. 이 기록 뒤의 전송은 이미 나갔을 가능성을 보존한다. | `full_stack_lab/gateway/app/core.py:1342-1366` |
| P9 | **MCP 도구 실행**: `call_tool`을 전송한다. 전송 시도, 확정 응답, 응답 미확인을 구별한다. | `full_stack_lab/gateway/app/core.py:1367-1377,1970-1971` |
| P10 | **출력 검사·마스킹·보류**: 반환 형식·비신뢰 지시·크기와 PII/Secret을 검사한다. 여기서의 차단은 이미 실행된 효과의 취소가 아니다. | `full_stack_lab/gateway/app/core.py:1391-1394,1460-1511,1930-1967` |
| P11 | **감사 기록·예약 해제·반환**: 해시 체인 원장에 결정과 실행/응답 처리 상태를 기록한 뒤 예약을 해제한다. 차단·승인 대기도 이 종점에 합류한다. | `full_stack_lab/gateway/app/core.py:1534-1613,1697-1707,1974` |

주 요청선은 `P0→P1→P2→P3→P4→P5→P6→P7→P8→P9→MCP`다. 응답선은 `MCP→P10→P11→하네스`로 아래쪽을 돌아간다. 초기 거부·검사 실패·승인 대기는 `P11`로 가며 MCP 실행 노드로 이어지지 않는다. 연결·목록 조회도 외부 통신이므로 P7을 ‘아직 외부 전송 없음’으로 표시해서는 안 된다. **P9 이전 도구 실행 없음**과 구분한다.

승인 대기에서 관리자 승인 후 P7로 바로 넘어가는 지름길도 그리지 않는다. 현재 `approve_request`는 `execute_call`을 다시 호출해 현재 조건을 재평가한다(`full_stack_lab/gateway/app/core.py:1977-2012`).

### 선 목록

| 선 | 출발→도착 | 라벨·표현 |
| --- | --- | --- |
| E01 | 직원→진입 래퍼→관리 계정 하네스 | 로컬 실행. MCP 전송선과 다른 얇은 선. |
| E02 | 보호 서비스→로컬 헬퍼→하네스 | Linux UID 확인 소켓 / Windows named pipe, 짧은 MCP 토큰. 장치 키는 보호 서비스 안에만 둔다. |
| E03 | 하네스→Caddy→P0 | `HTTPS :443 /mcp/<server>/`, 검증된 직원 MCP 토큰. |
| E04 | 관리자/직원 브라우저→Caddy→콘솔 서비스 | 기본 안내 `HTTP :8000 · Tailscale 내부`. HTTPS 콘솔도 제공함을 보조 표기한다. |
| E05 | 콘솔 서비스→게이트웨이 관리 API | 인증·역할 검증 후 관리 요청. MCP 데이터 호출선으로 표시하지 않는다. |
| E06 | 보호 서비스→Caddy→인증 서비스 | `HTTPS :443 /oauth/device-enroll · /oauth/device-token`, 장치 자격 경계. |
| E07 | 보호 서비스/관측기↔Caddy↔엔드포인트 API | `HTTPS :443 /api/endpoint/*`: 정책 조회·하트비트·인벤토리·리스너·OS 이벤트. 응답 방향도 표시한다. |
| E08 | 인증 서비스↔조직 IdP | `OIDC · 선택 설정`, 브라우저 리다이렉트와 서버측 토큰 교환을 구별한다. Authlib는 인증 서비스 안에 둔다. |
| E09 | P5·P7↔OPA | 정책 판정·실행 직전 재판정. P3/P7은 승인 계약을, P1/P5는 관리대장을 읽는 선도 둔다. |
| E10 | P4·P10↔Presidio / 내부 Gitleaks·텍스트 검사 | 입력 탐지와 출력 마스킹·검사를 별도 접속점으로 둔다. |
| E11 | P7/P9↔원격 MCP | `HTTPS · Streamable HTTP · 별도 공급자 자격`. 연결/목록과 도구 실행 단계는 게이트웨이 내부에서 분리한다. |
| E12 | P7/P9↔격리망 승인 MCP | 실행기가 제공한 내부 주소, 레시피에 따른 `HTTP · Streamable HTTP` 등 실제 transport. 원격 HTTPS 선과 구별한다. |
| E13 | 격리망 승인 MCP→실행 출구 프록시→심사 목적지 | 허용 호스트 출구. CONNECT의 암호화된 본문을 게이트웨이가 검사한다는 표시는 하지 않는다. |
| E14 | 하네스→모델 프록시→외부 LLM | `HTTP 프록시 :3128 · HTTPS CONNECT :443`. 목적지 도메인 제한이며 MCP PII/출력 검사선과 연결하지 않는다(`full_stack_lab/model-proxy/tinyproxy.conf:8-13`). |
| E15 | 콘솔 신청→DB 검증 대기열→도입 워커→검사 결과·artifact | 소스 도입용. Syft·Trivy·Semgrep·Gitleaks와 외부 소스 확보선을 워커에 붙인다. 원격 서비스는 계약 심사 가지로 분리한다. |
| E16 | 독립 승인→내부 Git 게시 / 관리자 실행 요청→DB 실행 대기열→실행기 | 실행기→내부 Git은 고정 커밋 사본 읽기, 실행기→Docker는 빌드·망/컨테이너 관리다. 실행 확인 후 별도 등록 단계→승인 카탈로그로 연결한다. |
| E17 | P11→PostgreSQL 감사 원장 / 게이트웨이 계측→Jaeger | 원장과 추적 저장소를 분리한다. 후자는 `OTLP/HTTP :4318`, 전자는 append-only 감사 기록이다. |
| E18 | 원장·승인·경보 DB→SIEM 전송 대기열→워커→외부 SIEM | 선택 기동, `HTTPS · OCSF JSON · 재전송`. 기본 꺼짐을 글자로 적는다. |
| E19 | 종료 관리→관계 차단·실행기 정지·자격 회수 / 관측·제공자 증거→종료 판정 | `C1~C4 / T1~T3` 관리 흐름. 미확인 제공자 자격은 별도 상태로 남긴다. |

### 개발 예정 통제의 접속점

네 항목은 백로그에서 미착수로 기록되어 있지만(`research/llm-wiki/status/backlog.md:59,65-67`), POL-08은 검토 중 새 동의 모듈·스키마 작업이 나타났으므로 이 상태표가 최신 개발 착수를 반영한다고 단정할 수 없다. 새 모듈에는 도구·등급·조건 해시에 결속된 동의 조회·변경 코드가 있다(`full_stack_lab/gateway/app/consent.py:22-75`). 기존 기능 위에 **예정/구현 중 꼬리표**를 붙이되, 호출 경로 연결·배포·실기기 효과와 구분한다. 아래 ‘기록’은 제안하는 판정 근거이며 새 DB 구현을 이 검토에서 요구하거나 수행하는 것은 아니다.

| 통제 | 파이프라인에 붙일 위치·선 | 기록·재검사할 내용 | 현재 기능과 구별할 점 |
| --- | --- | --- | --- |
| **예정 · POL-08 사용자 동의** | 관리면에 `데이터·기능별 사용자 동의` 기록 노드를 두고 P5의 판정 문맥과 P7의 재검증에 점선으로 연결한다. 미동의 분기는 `동의 확인 요청/보류→P11`, 이후 현재 신원·권한으로 처음부터 재평가한다. | 인증된 주체, 서비스/도구, 데이터 범위, 목적, 유효기간·철회·동의 판본. 동의와 독립 운영자 승인은 별도 기록. | 현재 신청시 `user-consent` 이벤트는 있다. 이것을 데이터·기능별 모든 호출의 동의 강제라고 표시하지 않는다(`agent_service.py:1048-1065`). |
| **예정 · POL-26 전송 목적 결속** | P1의 목적지·등급 분류와 P5의 이용 관계 판정에 붙이고, P7에서 실제 전송 인자·목적지·현재 승인 조건을 재확인한다. 별도로 E13 출구 제한과 점선으로 연계한다. | 승인 목적×수신처×데이터 등급×주체·기한의 조합과 실제 전송 대상. 목적 문자열이 인자에 있다는 이유로 승인된 목적으로 신뢰하지 않는다. | 현재 `_relationship_scope`는 활성 관계의 자원 합집합 범위를 확인한다. 목적·수신처·등급 결속 전부가 구현된 것은 아니다(`core.py:1030-1044`). 프록시 호스트 허용만으로 MCP 서버 내부의 2차 전송 내용·목적을 입증할 수 없다. |
| **예정 · POL-31 입력 항목 허용·마스킹** | P3→P4 사이에 `도구별 허용 항목 확인`, P4 뒤·P5 앞에 `입력 최소화·마스킹`을 점선 삽입한다. 변환 뒤 `재분류·스키마/목적지 재확인→P5`, P7에는 최종 실제 전송 인자의 스키마·승인 결속을 연결한다. | 허용 필드, 제거/마스킹 규칙 판본, 변환 후 인자의 지문, 달라진 분류·목적지, 적용 결과. 원문 민감정보를 새 감사 필드로 저장하지 않는다. | 현재 입력은 주로 탐지 후 정책 판단이며, 일반적인 도구별 입력 마스킹은 별도 요구다. 기존 `apply_restrictions`는 길이·bcc 등의 제한 변환이다(`core.py:1816-1828,1910`; `classify.py:815-834`). 변환이 대상을 바꾸면 재인가해야 하며 승인된 원문 인자의 권한을 그대로 재사용하면 안 된다. |
| **예정 · POL-33 중요정보 표시 전파·서버 간 전달 경계** | P10/P11→`주체·세션별 중요정보/출처 상태`→다음 호출의 P1/P4/P5를 점선으로 연결한다. P7은 실행 직전의 최신 상태를 재확인한다. 원격 MCP끼리 직접 연결되는 새 실선을 만들지 않는다. | 원천 서버/자원·등급·처리 시점, 하네스에 실제로 반환된 표현, 다음 도구·목적지·승인 여부. 동시 호출·토큰 회전·세션 변경의 상태 결합 및 만료 기준도 설계 대상으로 표시한다. | 현재 `_sequence_flags`는 같은 principal의 최근 중요정보 조회 후 외부 송신을 탐지하는 휴리스틱이다. 바이트 단위 데이터 계보나 범용 세션 정보흐름 추적은 아니다(`core.py:1017-1027`). 제공자 내부 서버 간 전달·직접 API·모델 경로는 이 상태선만으로 통제된다고 주장할 수 없다. |

POL-33의 ‘세션’은 도표의 사용자 입력 라벨만으로 권한 경계를 만들지 않는다. 현재 MCP 대화 문맥에도 클라이언트가 보낸 세션 ID와 검증 토큰의 관계를 다루는 코드가 있으므로(`full_stack_lab/gateway/app/mcp_facade.py:56-70`), 추적 단위와 신원·철회 경계의 관계를 설계에서 명시해야 한다. 출력 보류·마스킹과 업스트림의 실제 실행은 별도 상태로 보존한다. `출력 보류→실행 취소` 화살표는 금지한다.

그림의 마지막 판정 표시는 `판정 결과`, `도구 실행 상태`, `응답 처리 상태`의 세 값으로 나눈다. 예를 들어 `차단 / 실행됨 / 응답 보류`와 `차단 / 전송 전 / 반환 없음`이 구별돼야 보안 관리자가 사고 효과와 후속 회수 필요성을 판단할 수 있다. 이는 현재 코드의 `upstream_attempted`, `upstream_executed`, `result_evidence` 구분을 도식에 옮기는 제안이다(`full_stack_lab/gateway/app/core.py:1534-1548,1959-1967`).
