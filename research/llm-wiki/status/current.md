# 개발 현황 — 2026-10-15

## Team AGI 산출물 위키 반영

[선별 기록](../team-agi-deliverables-2026-10-15.md)과 [작업 보고](reports/2026-10-15-drive-deliverables.md): 드라이브의 정책, 기술 구현, 실증 및 평가 폴더를 확인해 2026-10-14 정책 50개 원본과 색인, 2026-10-03 MVP WBS 원본을 위키에 판본별로 보존했다. 프레임워크 V3.0은 원문 링크와 개발 적용 요약을 남겼다. 평가 폴더에는 현재 결과 보고서가 없고 이전 구성 그림 한 건만 있어 현행 실증 증거로 반영하지 않았다. 새 자료의 요구사항과 기존 코드·시험의 일대일 대조는 미완료다.

## 클린 기기 E2E · MINT 화면 (최신)

[작업 보고](reports/2026-10-15-clean-e2e.md) · [근거](../analysis/wbs-1015/e2e-clean.json): 기기 DB·등록 상태를 백업 후 비우고, `user` 신청 → `root` 검토·승인 → 등록으로 실제 MCP 3개(GitHub 원격, Context7 원격, Microsoft MarkItDown 소스 신청·내부 미러 실행)를 올렸다. PJ1 직원 계정의 관리 Claude Code가 자연어로 GitHub·MarkItDown을 호출해 결과를 받았고, 범위 밖 요청(`file:///etc/passwd`·미심사 호스트)은 실행 전 차단됐다. DEV-31은 실기기에서 해결 확인. E2E가 찾은 결함 3개(런처 PATH, 소스 등록 범위 부재, 배열 structuredContent)를 고쳐 배포했다(D-107~109, 최종 `83269c1`). 콘솔 글자 125%, 로그인 MINT, 원칙 중심 README, WBS 페이지 구현 진행도 표시. WBS **55.2%→57.5%**.

남은 것: Codex E2E(DEV-39), 승인 OSS 실행 경로(DEV-38), Context7 할당량(DEV-40), 팀원 기기 직접 복사(DEV-36), 기본 비밀번호 변경.

## 목표 기능 WBS 구현·통합·저지연화

[작업 보고](reports/2026-10-15-wbs-implementation.md) · [WBS 재산정](../analysis/development-wbs/README.md) · [근거](../analysis/wbs-1015/README.md) · 작업별 보고 [A 엔드포인트 증거](reports/2026-10-15-endpoint-evidence.md) · [B 도입·신원](reports/2026-10-15-intake-identity.md) · [C 종료·전송 경계](reports/2026-10-15-termination-dispatch.md) · [D 검사 코퍼스](reports/2026-10-15-inspection-corpus.md)

Codex 10-13~14 작업·팀원 디자인(기기 직접 수정 5회 포함)·서브에이전트 A–D를 통합 브랜치 `10/15-wbs-implementation`으로 모아 솔루션 기기에 3번 배포했다(최종 `8723cce`, 16:37). 도구 호출 구간별 처리 시간·지연 탭·엔드포인트 망 품질을 화면에 넣었고, 검사 엔진을 프로세스 안 네이티브 코드로 옮겼다(Gitleaks 65.5→1.85 ms, 텍스트 규칙 31개 PCRE2 JIT로 200 KB 74→6.6 ms, re·바이너리와 판정 차이 0). Codex 교차 리뷰 9건과 D가 찾은 U+0000 감사 누락을 고쳤다. 병합본에서 격리 PostgreSQL·실제 Gitea MCP·실제 Presidio 포함 회귀 31건과 로컬 7건이 통과했고, PJ1 실데이터(망 품질 22표본·해시 일치 251건·실제 SDK 호출)로 WBS를 **24.8%→55.2%**(구현 완료 16→34개, 최종 완료 0/40)로 다시 산정했다.

남은 것: 관리 계정 미로그인으로 하네스 자연어 E2E·PJ1 키트 재설치(D-104·D-105) 미실행, 지연의 대부분은 업스트림 SaaS와 Tailscale DERP 중계(솔루션 Tailscale이 WSL2 NAT 안, DEV-37), 관리 계정 루프백 차단이 하네스 로그인 콜백과 충돌(DEV-35), MCP 세션 재사용 결정(DEV-29), 팀원 작업 반영 경로(DEV-36).

## 엔드포인트 로그 수정·PJ1 Linux 검증

[수정 보고](reports/2026-10-14-endpoint-telemetry-fix.md) · [직접 확인할 로그](../analysis/endpoint-log-fix/README.md) · [웹 WBS](https://mcpgw-status-20261014.sleek-stoat-4347.chatgpt.site): process-only 수집을 network scan과 분리, 채널 상태/last-success·부분 snapshot 보존·listener 상세·freshness·Windows producer를 구현해 솔루션/PJ1에 배포했다. Linux UID1001 합성 process 자동 수신/UID1000 제외/종료 후 자동 정리, 실제 AppArmor 이벤트1388 자동 수신(9.43초), journal 오류 시 last-success/cursor·broker 보존과 원복 후 주기 복구를 확인했다. 전용 새 PG schema8조건·배포 image8조건 PASS, 제품 DB/registry 보존과 실행 SHA 일치. WBS는3개 작업만 재검수하여21.8→24.8%, 전체 완료0/40이다.

Windows는 코드·합성 단위/PowerShell syntax만 확인하고 실기기는 사용자의 Linux 우선 결정에 따라 미검증이다. 실제 Ghidra UID1000, 자연어 MCP call/92개 전체, 장기 offline·rotation·diskfull 무손실, 전체 누적집계/페이지 이동과 DEV29~32는 미완료다. 아래 읽기전용 진단·21.8%와 NETSCAN 때문에 stdio가 꺼진 기록은 수정 전 이력이다.


## 엔드포인트 로그 진단·목표 기능 WBS

[검수 보고](reports/2026-10-14-endpoint-log-wbs.md) · [40개 산정표](../analysis/development-wbs/README.md) · [별도 웹 현황판](../../development-status-site/README.md): G01–G10/원본 PAC01–24를 40개 작업에 의미 매핑해 5단계 동일 가중 진척 **21.8%**를 산정했다(부분/과거 근거0.5, 전체 단계 검수 완료0/40). 구현16개·부분23·미구현1이며 기능 전체가 0이라는 뜻은 아니다. PJ1 현재 NETSCAN0·active service·표본1387 수신 유지·원본/수신 projection SHA 일치, 실제 제공 Console JS의 전용 listener 누락을 확인했다. 6개 로그 공백을 DEV-34에 연결했고 제품 코드/설정/승인/DB는 이번에 변경하지 않았다. 웹은 실시간 제품 로그가 아닌 날짜가 있는 검수 스냅샷이다.

## PJ1 Ghidra 설치·로그 전달 확인

[검수 보고](reports/2026-10-14-pj1-ghidra-logs.md) · [확인할 로그](../analysis/pj1-ghidra/README.md): PJ1에 Ghidra12.1.4/GhidraMCP2.0.0을 task 범위로 구성해 실제stdio initialize·schema28·합성ELF get_program_info를 확인했다(UID1000/unconfined, SDK시험). 기본stdio 관측은 NETSCAN0으로 자동전송0이었고, 명시적 일회성 실제프로세스 보고는 Console shadow/suspected1 수신 후 종료/원복했다. 관리UID1001 Python실행은 exit126, 별도OS거부는 수동전송없이 기존 주기수집기로 약35.84초 뒤 Console1387 수신. 로컬SDK창 Gateway 원장0. Ghidra/JDK는 디스크부족으로 RAM1.24GiB 임시설치라 재부팅시 소실; privatevenv/로그는디스크보존. MCP등록승인·제품정책변경·자연어Ghidra하네스는 수행하지 않았다.


## 비인가 로컬 MCP의 PJ1 자연어 시험 (E13 변형)

[작업 보고](reports/2026-10-14-e13-local-mcp-natural-language.md) · [로그](../analysis/pj1-local-mcp-e13/README.md): 등록하지 않은 실제 OSS MCP(Git·DBHub·Playwright 9개 도구)를 PJ1 관리 계정의 실제 Claude Code(Sonnet 5.5)에게 자연어로 쓰게 했다. 관리 계정은 하네스 정책·AppArmor exec·nft·모델 프록시가 겹쳐 로컬 MCP 사용이 한 건도 성공하지 않았고 수신 서버 요청은 0이었다. 비인가 서버 경로는 Gateway가 `MCP-REGISTRY-001`로 막고 기록했다. 문제: 관리 계정의 Bash가 `header-helper`로 기기 토큰을 얻을 수 있고(DEV-31), 같은 PC의 비관리 계정은 9개 도구 쓰기까지 성공하면서 Gateway·엔드포인트에 0건이며(DEV-32), 정상 사용 거부 이벤트가 62%를 차지한다(DEV-30). Codex 하네스·E13 전체 조건·Windows는 미실행, 제품 코드는 바꾸지 않았다.

같은 날 먼저 한 [9개 도구 1차 시험](reports/2026-10-14-pj1-nine-tools.md)은 에이전트가 시험 대상 서버를 스스로 승인해 등록한 **무효 시험**이라 철회하고 대체했다(D-79). 콘솔에 로그가 없던 원인은 Codex 모델 턴이 사용량 한도로 시작 즉시 실패한 것이었다.

## 위험매핑 3단계 시험·수정

[3단계 보고서](reports/2026-10-14-risk-scenarios.md) · [정본 JSON](reports/2026-10-14-risk-scenarios.json): 정적 검토와 PJ1 DB 보존 동적5개, 전용 PostgreSQL 실제 초기화 후 선별5개를 수행했다. 활성화·철회의 감사 INSERT 실패 시 상태만 commit되는 두 경로를 재현해 같은 transaction으로 수정했다. 수정 코드와 실제 재빌드 image에서 각각5개 통과, 솔루션 배포·운영 DB 시작시각/계정10·장치12·설치grant14 보존 확인. 실제188.91초 heartbeat 만료 뒤 미만료 JWT/새 발급403, 서비스 복구 후200을 확인했다. 새 LOCAL-RISK-11 추가; 실패한 철회는 rollback되므로 재시도가 필요하다. 자연어 하네스 호출·92개 전체 도구·Windows 실기기 시험은 새로 수행하지 않았다.


## 로컬 도구·MCP와 엔드포인트 권한 검수

Luna3개 분업과 Codex 검수로 실제 Ghidra·Git·SQLite·Blender·Playwright MCP5개를 설치·연결하고 광고 스키마92개를 기능 유형별로 보존했다. 권한 반례를 [위험매핑10건](../threats/local-tool-map.md)과 원본24개 정책에 연결했고 [공식 권한 레퍼런스12개 주제](../catalogs/endpoint-permission-references.json)를 추가했다. [설치·기능 정본](../analysis/local-tools/README.md)과 [작업 결과](reports/2026-10-14-local-mcp-endpoint.md)를 읽는다.

Linux 프로필 점검, Windows 방화벽 불완전 상태, Gateway 이름 위장, URL/legacy stdio 비밀 저장과 로컬 MCP 발견을 수정했다. 새 회귀15개와 Linux 키트17개를 통과했고 솔루션 field up 배포의 실제 코드46개/정책/build hash 일치를 확인했다. PJ1도 수정·active/compliant·fresh profile·승인 하네스 실행·비승인 Node·IPv4/IPv6 loopback 거부와 승인 Gateway TCP를 확인했다. 이것은92개 도구 전체의 관리 집행이나 새 자연어 모델 turn을 의미하지 않는다.

Blender disable-autoexec·ambient 자격 제거는 로컬 실제 MCP 재시험을 통과했다. DBeaver GUI 세팅, Burp 공식 MCP UI 활성화, Windows 실제 실행/loopback 통제, root 서비스 권한 분리 및 Windows 사용자 키트 제거 경합은 미완료다. DBeaver 사용자 AppData 캐시 생성 정황은 경로·시각과 기존 변경 미확인 범위를 별도로 보존했다.

아래2026-10-13 결과는 과거 작업 근거로 유지한다. 현재 작업은 `10/14-local-mcp-endpoint`, 기준 `ab6936c+기존 dirty132파일`이며 원본 작업트리를 보존했다.

연구 정본은 Markdown이고 웹은 [Codex × Claude 개발 협업 콘솔](../../collaboration-console/README.md)입니다. 실제 공개 소통·담당 작업·진행·검사 결과를 http://127.0.0.1:18766 에서 확인합니다. 원본 대화·CLI 설정·비밀은 로컬 ignored runtime에만 남깁니다.

## 현재 구현과 검증

| 영역 | 현재 확인 | 남은 확인 |
| --- | --- | --- |
| 개발 연구 위키 | 논문·문서 28건과 주제별 레퍼런스 139건(서지 대조 완료, 요약은 전문 선별 6·초록 대조 81·출처 페이지 대조 49·메타데이터만 3, [보고](reports/2026-10-14-reference-fill.md)), 솔루션 8건, 실험 설계 13건(E13 로컬 stdio/loopback 추가), 위협표 24개 정책과 두 XLSM 원본 | 13개 카드 미실행. 지속적인 새 자료·실험 결과 갱신 |
| 개발 협업 | 실제 WSL claude-sonnet-5-5, 요청 effort xhigh, 공개 최종 분석 수신 | 수정 후 Claude 리뷰는 계정 세션 한도(17:50 KST 재설정 안내)로 미완료. 모델 자동 대체 없음 |
| 기능·설계 | [목표 10개](reports/2026-10-13-development-goals.md), [현재 기능·8개 제품 대조·보강 설계](reports/2026-10-13-feature-design.md), [Claude 검토 원문](reports/2026-10-13-claude-code-review.md) | 후보 재현 결과와 큰 설계 공백은 백로그로 추적 |
| 자원 상태 | 관리자 Console scope API/UI, Linux CPU·메모리·내부 DNS/TCP 연결 지연, 실기기 표본·권한·Chrome 화면 검증 | PC→솔루션 Tailnet 지연·패킷 손실률·개별 컨테이너 지표는 범위 밖 |
| 계약·결과·감사·목적지 | 카탈로그 A→B→A, 디코딩된 결과 지시문, 새 체인 시각 무결성, egress 데이터 실패 회귀와 수정 | 과거 체인 시각 보호는 소급 불가. 동시 카탈로그 경합·크래시 의도 기록 등 후속 |
| 배치 검사 | 정확한 Caddy+모델 프록시 게시 집합과 음성 회귀, 17건 로컬·최종 전체 CI 통과 | 새 배치 변경마다 회귀 유지 |
| 지정 기기 | field up 배포, 이미지·내용/로드 정책 일치, PJ1 실제 새 하네스 호출과 원장740~742·체인v7 대조 | Context7 월간 한도 초과로 정상 문서 조회는 미완료, 독립 수신 측 trace는 미확보 |
| refresh 계열 | 단위7건과 솔루션 실제 PostgreSQL 격리3건, 동시 발급·폐기·롤백 통과 | 현재 완료 조건 검증 유지 |

## 보고와 증거 경계

[최초 위키 구축 보고](reports/2026-10-13-wiki-bootstrap.md)는 위키 구축 당시 범위를 기록합니다. 최초 웹 해석은 사용자 정정에 따라 폐기했습니다. 개발 코드 분석·설계·구현·단위 검사·배포·실제 하네스 호출은 각각의 증거 수준으로 보고합니다. 기존 실험 카드 12개는 이번 단위 검사 결과로 자동 완료하지 않습니다.

[최종 개발·실기기 결과 보고](reports/2026-10-13-development-results.md)에 수정 전 재현, 구현, 검증과 한계를 남겼습니다. 구현6178dd3 배포 검증, 통합 검사c6ab26a의 [전체 CI](https://github.com/MCP-governance/mcp-gateway/actions/runs/38353250953) 정적·완료 조건 검증 모두 통과. 이후 문서·시험 커밋과 실행 이미지의 구현 revision을 구분합니다.

저장소는 MCP-governance/mcp-gateway, 원격 기본 브랜치는 feat/2026-09-v3.1-field-deploy 입니다. 최초 개발 작업 기준은 0df1adf5596161d258536219c8dabde8b16dd532, 팀 개발 계획 기준 최신은 2e36095bf982ffab29ea81b6cdc24bdc435b184f 입니다. 최신 [전체 CI](https://github.com/MCP-governance/mcp-gateway/actions/runs/38355027939) 성공을 재확인했습니다. 기존 docs/ai·엔드포인트·poisoning 미커밋 작업은 보존합니다. 기기 시작 소스6fdd9f6·이미지77c4da0의 차이를 확인해 구현6178dd3을 배포했고, Gateway/Console build와 실제 로드 정책 일치를 확인했습니다. 현재 로컬 코드 관찰은 [스냅샷](repository-snapshot.md)에 있습니다.

사용자의 팀원 합류 지시에 따라 **이후 작업은 작업별 새 브랜치**에서 수행합니다. 현재 `10/13-mcp-validation`을 2e36095에서 만들었습니다. [팀 개발·후보·실험·실패 시 수정 보고](reports/2026-10-13-mcp-validation-plan.md)에 로컬10종·직접 stdio 경로, 구현 변화, 8개 제품 대조와 통과 기준을 정리했습니다. 이번 변경은 문서·설계이며 새 제품 코드·배포·실험 실행은 없습니다.

## 다음 우선순위

[팀 시험 계획](reports/2026-10-13-mcp-validation-plan.md)에 따라 독립 수신·효과를 관찰하는 로컬 fixture의 정상군을 먼저 확보하고, 데이터/계약/권한·직접 stdio/loopback·동시성·종료 시험을 진행합니다. 신선한 요청자 인증을 유지한 승인 실행, 수집기 신선도·전체 집계, 크래시 실행 불확실성, 한국어 PII, OAuth 대상·권한·철회와 서버 outbound 통제를 보강합니다. refresh 계열 경쟁 수정은 기존 회귀를 유지합니다. Gateway 경유 통제와 엔드포인트 우회 집행을 합쳐 모든 경로 통제라고 표현하지 않습니다.
