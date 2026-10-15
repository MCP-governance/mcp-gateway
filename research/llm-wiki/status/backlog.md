# 개발 백로그

완료 조건이 있는 개발 작업을 이 목록에만 유지합니다. 지금의 상태는 연구·시험 설계 기준이며 솔루션 코드·운영 시험 완료를 뜻하지 않습니다.

| ID | 작업 | 근거 | 완료 조건 | 상태 |
| --- | --- | --- | --- | --- |
| WIKI-01 | 개발 위키와 공유 보고 체계 | [위키](../README.md), [협업 콘솔](../../collaboration-console/README.md) | 자료 분류·원본·해시·MD·Claude 규칙·실제 협업 기록·검사 통과 | MD 정본·협업 콘솔 구축, 실제 Claude 분석 수신; 수정 후 Claude 리뷰는 계정 한도로 미완료 |
| DEV-01 | 실제 관리형 하네스 증거 연결 | [실기기 결과](reports/2026-10-13-development-results.md), [통제 증거](../methodology/control-design.md) | 활성화 상태와 fresh 신원, model→MCP→원장 IDs, 정상/차단의 독립 효과 | 새 PJ1 Codex 세션2개·원장3건 일치. 공급자 quota 응답·PII 차단 확인; 정상 문서·독립 수신 trace는 미완료 |
| DEV-02 | 계약 변경·오염 탐지 코퍼스 | [분석](../solutions/README.md), [실험](../experiments/README.md) | 다국어 정상/공격/인코딩 표본, 오탐·미탐 및 계약 diff, 검사기 장애 차단 | 조사·설계 |
| DEV-03 | 원본 위협표와 구현 추적 검토 | [위협 매핑](../threats/README.md) | 24개 정책의 통제 위치·코드·실험·한계별 리뷰와 근거 | 매핑 초안, 독립 리뷰 필요 |
| DEV-04 | 승인 재사용·경쟁 조건 | [PAC 설계](../../../docs/ai/PAC_RUNTIME_2026-10-01.md) | 변형 요청·중복 동시 호출·철회 경쟁의 정확한 효과 수와 판정 | 설계·새 실험 미실행 |
| DEV-05 | OAuth 대상·scope·철회 검증 | [논문·명세](../papers/README.md) | 다른 audience·scope·만료·철회 입력의 전송 전 차단과 정상군 | 조사·설계 |
| DEV-06 | 응답 통제와 실행 증거 분리 | [통제 설계](../methodology/control-design.md) | masked/held/released 결과와 upstream 실제 실행을 별도 보고 | 설계·새 실험 미실행 |
| DEV-07 | 상용·OSS 비교 재현 | [제품 분석](../solutions/README.md) | 같은 도구·정상군·공격군·검사기 장애·독립 효과의 비교표 | 소스/문서 분석 완료, 실행 미실행 |
| DEV-08 | 종료 C3/C4의 자원 서버 차이 | [종료 모델](../../../docs/ai/TERMINATION_MODEL.md) | introspection TTL·캐시·발급 토큰의 재접근과 T1~T3 증거 | 문서·설계 |
| DEV-09 | 한국어 PII/Secret 평가 | [PII/Secret 도입](../../../docs/ai/OSS_ADOPTION_2026-10-03.md) | 합성 한국어 표본의 탐지·마스킹·성능·scanner fail closed | 설계 |
| DEV-10 | field 포트 배치와 CI 기대값 대조 | [실패 CI](https://github.com/MCP-governance/mcp-gateway/actions/runs/38346569656), [이전 동일 실패](https://github.com/MCP-governance/mcp-gateway/actions/runs/37201934077) | Caddy+모델 프록시의 정확한 서비스·Tailnet 주소·포트·프로토콜 집합, 임의 게시 거부 | 수정·양/음성 포함 17건 로컬 통과; 새 CI 결과는 작업 보고 참조 |
| DEV-11 | CPU·메모리·연결 지연 | [설계](reports/2026-10-13-feature-design.md) | 관리자·Console scope, 실제 /proc·고정 TCP 경로, 결측·오래된 값·CPU 긴 간격 제외 | API/UI 구현·백엔드/표시 회귀 통과, 실기기 결과는 작업 보고 참조 |
| DEV-12 | 계약 A→B→A 관측값 일관성 | [코드](../../../full_stack_lab/gateway/app/core.py), [회귀](../../../full_stack_lab/tests/catalog_refresh_check.py) | 복귀 시 관측값 A, 재승인도 A, 동일 연속 조회 최적화·서버 격리 | 수정 전 2/4 실패 재현, 수정 후 4/4 통과 |
| DEV-13 | 새 감사 기록 시각 무결성 | [회귀](../../../full_stack_lab/tests/security_edges_check.py) | 새 v7의 created_at 변조 검출·UTC 정규화, 기존 v1~6 검증 유지 | 수정·회귀 통과; 과거 체인의 시각 무결성은 소급 보장 불가 |
| DEV-14 | 결과의 디코딩된 줄바꿈 검사 | [회귀](../../../full_stack_lab/tests/security_edges_check.py) | MCP text와 structuredContent의 위조 대화록, 정상 로그·크기/형식 대조 | 수정 전 우회 재현, 수정 후 통과 |
| DEV-15 | 목적지 정책 데이터 실패 차단 | [회귀](../../../full_stack_lab/tests/security_edges_check.py) | None/결측/잘못된 타입은 거부, 명시적 빈 목록·허용 호스트 정상군 | 수정 전 잘못된 허용 재현, 수정 후 통과 |
| DEV-16 | refresh 회전·계열 철회 경쟁 | [실기기 결과](reports/2026-10-13-development-results.md), [Claude 후보 B5](reports/2026-10-13-claude-code-review.md) | 동일 계열의 회전·발급·재사용/철회를 트랜잭션 안에서 직렬화, 실패 롤백 | 수정·단위7건·솔루션 실제 PostgreSQL3건·전체CI 통과 |
| DEV-17 | 승인 후 신선한 요청자 인증 | [Claude 후보 B2](reports/2026-10-13-claude-code-review.md) | 만료 검증을 완화하지 않고 승인과 새 요청자의 실행을 연결, 현재 권한·철회 재검증 | 설계; 만료 토큰 거부는 유지 |
| DEV-18 | 엔드포인트 수집 신선도·전체 집계 | [최신 수정](reports/2026-10-14-endpoint-telemetry-fix.md) | 최근200건/전체 집계 구분, 채널 last-success·실패·freshness·감사 경로 | 채널 상태·freshness·listener 상세 및 Linux 오류/복구 검증; 전체 누적집계·페이지 이동·장기 offline는 후속 |
| DEV-19 | PJ1 로컬 stdio·loopback 우회 | [E13](../experiments/E13-local-bypass.md) | 관리형 실제 시도·UID/profile 거부·독립 수신/효과0와 승인 정상군; IPv4/IPv6 구분 | 전용 카드·통과/실패 기준 설계, 미실행 |
| DEV-20 | MCP 서버의 외부 API 통신 | [Lunar 분석](../solutions/lunar-mcpx.md), [팀 시험 계획](reports/2026-10-13-mcp-validation-plan.md) | 서버 egress의 목적지·자격·재시도·허용/차단과 독립 외부 효과 연결 | 관측·집행 범위 설계, 미실행 |
| DEV-21 | 크래시 실행 의도·불확실성 기록 | [CPEX 분석](../solutions/ibm-cpex.md), [팀 시험 계획](reports/2026-10-13-mcp-validation-plan.md) | dispatch 전 durable intent, worker 사망 시 uncertain 보존, 중복 쓰기 자동 재시도 금지와 효과 대조 | 설계, 미실행 |
| DEV-22 | PJ1→솔루션 연결 품질 | [팀 시험 계획](reports/2026-10-13-mcp-validation-plan.md) | 고정 Gateway 대상의 endpoint 측정 ms·jitter·접속 실패율·신선도·권한, packet loss는 별도 실제 측정일 때만 표기 | 현재 내부 DNS/TCP 지표와 구분한 후속 설계 |
| DEV-23 | 실제 로컬 앱·MCP 권한 경계 | [2026-10-14 결과](reports/2026-10-14-local-mcp-endpoint.md) | 공개MCP 설치·실제 schema·read/write 효과·권한 반례·위험표·원복 | 5개 설치/연결·92개 스키마·위험10건 완료; 도구 전부의 managed 실행·Burp UI 활성화·DBeaver GUI는 후속 |
| DEV-24 | 엔드포인트 정상 점검·인벤토리 최소정보 | [수정·배포](reports/2026-10-14-local-mcp-endpoint.md) | 정확한 Linux profile·Windows 규칙/SID·Gateway URL 경유·민감 ref hash·새 marker의 양/음성 | 신규 회귀15개·Linux 키트17개·솔루션/PJ1 배포·선택 Linux 실제 경계 통과 |
| DEV-25 | Windows 실행/loopback·root broker 격리 | [권한 레퍼런스](../catalogs/endpoint-permission-references.json) | 격리 Windows 실기기 WFP·실행 정책·file scope, Linux unit/AF_NETLINK/observer/loaded policy 검증 | 공식12개 주제·적용조건 수집; 새 정책 집행 미실행 |
| DEV-26 | 사용자 PC 키트 Windows 제거 경합 | [관찰한 실패](reports/2026-10-14-local-mcp-endpoint.md) | background report의 종료/제거 잠금, WinError32 및 늦은 설정 재생성 회귀 | Windows17개 회귀 중 report.log 경합1개 관찰; Linux 통과와 분리해 후속 |

| DEV-27 | 관리 장치 상태·감사기록 원자성 | [3단계 시험·배포](reports/2026-10-14-risk-scenarios.md) | 활성화/철회의 기록 실패 주입, 독립 상태·이벤트 확인, 정상군·경합·원복 | 부분 commit2경로 재현·단일transaction 수정·실제PG/재빌드image각5개 통과·배포. 감사장애시철회실패/재시도, 별도긴급deny는 후속 |
| DEV-28 | 비인가 로컬 MCP의 PJ1 자연어 시험 (E13 변형) | [작업 보고](reports/2026-10-14-e13-local-mcp-natural-language.md), [로그](../analysis/pj1-local-mcp-e13/README.md), [무효 처리한 1차](reports/2026-10-14-pj1-nine-tools.md) | 등록하지 않은 실제 OSS 로컬 MCP를 관리 계정으로 시도해 막는 계층·독립 수신0·대조군·원장/이벤트를 대조 | Claude Code로 관리15·대조12건 실행: 관리 성공0·수신0, 대조 9개 도구 전부 성공(통제 밖 비가시). Codex 하네스·E13 전체 조건(공식 filesystem·실제 stdio)·Windows·반복은 미실행 |
| DEV-29 | 상태 의존 MCP의 업스트림 세션 | [보고 문제 파악](reports/2026-10-14-pj1-nine-tools.md), [upstream.py](../../../full_stack_lab/gateway/app/upstream.py) | 세션 바인딩(주체·다운스트림 세션·서버, TTL, 철회·종료 시 닫기)·경고·미지원 중 결정, 목록 화면에서 도구 오류 구분 | Playwright 탭 유실을 Gateway 호출별 세션으로 재현·원인 분리. 설계 결정 대기(코드 미변경) |
| DEV-30 | 정상 사용 거부 이벤트 잡음 | [보고 문제 3·4](reports/2026-10-14-e13-local-mcp-natural-language.md), [os-observer.py](../../../endpoint-agent/os-observer.py) | 하네스 기동 거부(`git`·`claude`)를 정상 사용과 구분, 이벤트에 프로세스 정보, 우회 시도는 그대로 노출 | 시험 창 68건 중 62%가 잡음 재현. 설계 결정 대기(프로파일 완화 아님) |
| DEV-31 | 헬퍼 토큰의 Bash 자식 접근 | [보고 문제 1](reports/2026-10-14-e13-local-mcp-natural-language.md), [enforce-linux.py](../../../endpoint-agent/enforce-linux.py) | Bash 자식이 `header-helper`를 실행하지 못하게 분리, 대화·로그에 토큰이 남지 않음을 시험 | Bash 자식의 헬퍼 실행·토큰 획득·Gateway 직접 요청 재현. 수정 대기 |
| DEV-32 | 통제 밖 계정·PC의 로컬 MCP 가시성 | [보고 문제 2](reports/2026-10-14-e13-local-mcp-natural-language.md) | 범위 명시, 리스너 발견(`ENDPOINT_NETSCAN`) 활용 여부 결정 | 대조군에서 쓰기 포함 성공·원장/이벤트 0 재현. 범위 결정 대기 |

| DEV-33 | PJ1 Ghidra 설치 지속성과 process-only 자동 관측 | [설치 이력](reports/2026-10-14-pj1-ghidra-logs.md), [자동 수집 수정](reports/2026-10-14-endpoint-telemetry-fix.md) | 영구디스크확보·process/network 분리·UID귀속·실제MCP 검증 | 관리UID process-only 자동 수집/대조군 제외 확인. Ghidra UID1000은 통제 밖이며 영구설치/실제관리형Ghidra/자연어는 미완료 |

| DEV-34 | 엔드포인트 로그 수집·표시 계약 및 검수 WBS | [최신 수정](reports/2026-10-14-endpoint-telemetry-fix.md), [40개 산정표](../analysis/development-wbs/README.md) | 채널 상태·신선도·listener 표/집계·complete만 삭제·process scope·지원OS 전달 | 솔루션/PJ1 Linux 수정 배포·자동 수신/실패/원복 복구·PG8조건 PASS. WBS24.8%/전체0개. Windows 실기기·전체집계·실제MCP 자동관측/장기offline 후속 |

변경할 때 작업 보고서를 연결하고 `완료`의 검증 층을 함께 씁니다. 소스·문서 확인만 끝났으면 실행 검증 완료로 올리지 않습니다.
