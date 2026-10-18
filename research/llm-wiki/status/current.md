# 개발 현황 — 2026-10-15

## 최신: 협업 콘솔과 통합 시트 CSV 연동 (10-18)

[작업 보고](reports/2026-10-18-sheet-sync.md): `10/18-sheet-sync`, 시작 `558e2a0`. WBS 덮어쓰기·신규 ID·목표별 요약·5분 캐시/실패 대체, 백로그 배열 API, CSV pull CLI와 설정 예시를 추가했다. 콘솔 unittest 32개·CLI self-test·JS 구문 검사 통과. pytest·pyflakes 미설치. 제품 코드·실제 CSV 사본·snapshot·배포 변경과 커밋 없음. 게시 URL은 미제공이며 메인이 runtime 설정 후 실제 Google CSV 반영을 확인한다.

## 최신: 선택적 계약 제한·보안 관제 전달 (DEV-52·61 / D-127·128, 10-18)

[작업 보고](reports/2026-10-17-selective-restriction-siem.md) · [원자 요구사항·근거](../analysis/selective-restriction-siem/README.md): 변경·소멸·위험 설명이 확인된 도구만 목록·판정·최종 dispatch에서 제한하고, 영향 미확정·기존 D-122 중지·공급망·폐기는 전체 차단을 유지했다. 판정·감사·실제 경보 참조를 같은 DB 트랜잭션으로 큐에 넣고 별도 HTTPS 워커가 OCSF JSON을 재전송한다. 로컬 단위/HTTP 14개·콘솔 상태 15개와 구문·인증·화면 문구 검사가 통과했다. Python 3.10/의존성 제약으로 기존 import 기반 회귀·pyflakes는 실패/불가, 실제 DB·TLS·SIEM·배포·PJ1·pj3는 미실행이다. 브랜치 생성·원격 HEAD 확인은 권한/네트워크로 실패하여 기존 작업 브랜치 `10/18-selective-siem`에 미커밋 변경을 남긴다. 검수 점수는 변경하지 않았다.

## 최신: TLS 병합 텍스트 해결·Windows CA 연결 (D-124 후속)

[후속 보고](reports/2026-10-18-field-tls-d124-merge.md): D-118·D-120~123과 TLS 양쪽 기능을 보존해 충돌 7파일의 마커를 제거했다. Windows 키트 14개·TLS 9개 단위, 직원 PC 키트 16개가 통과하고 Docker 검사 1개는 생략했다. Windows 등록·서비스·관측·하네스 프로세스 범위 CA를 연결했고 승인 매니페스트에 CA 파일 해시를 포함했다. 내부 TLS 주소 기본값은 비우고 실제 배포 주소를 요구한다. Git 인덱스가 샌드박스 밖이어서 `git add`가 거부되어 U 상태 해제는 메인이 수행한다. 생성된 위협 매핑·스냅샷도 메인이 재생성한다. 커밋·원격 접속·배포·실기기 설치는 하지 않았다.

## 최신: 현장 TLS 사설 CA 구현·로컬 검증 (DEV-64 / D-124, 10-18)

[작업 보고](reports/2026-10-18-field-tls-d124.md) · [원자 요구사항과 근거](../analysis/field-tls-d124/README.md): Caddy 사설 CA HTTPS·평문 거부, 공개 URL/레지스트리 렌더링 HTTPS, Console ZIP 루트·SHA-256, Linux/직원 PC 도구 지문 검증과 하네스 프로세스 범위 신뢰를 구현했다. TLS 단위 9개·기존 오프라인 회귀 일부 7개·렌더링·Python/셸 정적 검증을 수행했다. Caddy 자체 검사·Windows 전용 소비 통합·솔루션 배포·PJ1 호출/보고는 미실행이다. 위키 정적 매핑을 갱신했으며 전체 검사는 기존 원본 경로 누락 29건으로 미통과다. 커밋·원격 접속·스택 기동 없음. 완료 검수 점수는 변경하지 않았다.

## 최신: AI 컴플라이언스 근거 문서 61건과 규제 근거 개발 착수 계획 (10-17)

[작업 보고](reports/2026-10-17-compliance-references.md) · [근거·요구사항 매트릭스](../analysis/compliance/README.md) · [개발 착수 계획](../analysis/compliance/dev-plan/README.md) · [핵심 일정](../analysis/compliance/key-dates.md): 사용자가 준 AI 컴플라이언스 문서 모음(12건)을 위키와 대조해 채우고(3건은 기존 항목과 연결·정정), 한국·미국·EU·중국·캐나다·싱가포르·영국·일본·호주·인도·국제 문서 49건을 공식 원문에서 확보해 총 61건, 조항 1,223건(구속력 문서의 의무 조항 425건)으로 정리했다. 61건 전부를 작성자와 다른 에이전트가 원문과 다시 대조해 결함 835건(상 36)을 고쳤다. 원문은 재배포 근거가 확인된 32건만 `sources/compliance/`에 두고 29건은 git 제외 로컬 경로에 둔다. 이 자료로 개발 항목 DEV-66~71(사고 증빙·기한 타이머, 원장 보존·폐기, 공급자 보증 필드, 처리 위치·국외 이전 규칙, 중대 영향 결정 증빙, 위험 등급·영향평가 입력)과 RES-01을 제안했고 모두 미착수다. 법률 자문이 아니며 통제 후보가 구현·승인을 뜻하지 않는다. 미확보: LIB-M23(PDF 403). 결정 후보 RQ-01~08은 팀 확정 전이다.

## 최신: 기능명세서·개발 WBS와 리뷰 반영 (10-17)

[작업 보고](reports/2026-10-17-feature-spec-wbs.md) · [기능명세·WBS](../analysis/feature-spec-2026-10-17/README.md): 기능 64개(구현 완료(검수 전) 34·일부 구현 4·개발 예정 16·자동화 범위 제외 10), WBS 57개(현재 41·추가 16), 기술통제 35개의 현재/개발 후 대응을 한 통합 문서로 만들고 재생성 도구를 남겼다. 정책 구현 비율은 현재 68.6%, 추가 개발 후 90.0%이며 최종 검수 완료는 0건이다. 팀 리뷰 9건을 코드와 대조해 중계·판정 결과·판정 증적을 명세에 넣고, 선택적 제한·SIEM 전달·적용 전후 평가 도구를 추가 개발(DEV-50~65 중)로 등록했다. 리뷰의 "4가지 결과"는 실제 5종과 관리대장 우선순위 선택으로 정정했다. 제품 코드·배포 변경 없음. 팀 Drive 파일의 새 버전 업로드는 남았다.

## 최신: 정책 번호 체계 대응 정본과 OPA 규칙 레이블 시험 (10-17)

[작업 보고](reports/2026-10-17-pol-pac-mapping-opa-labels.md) · [대응 정본](../analysis/drive-curation/policy-id-mapping.json) · [OPA 시험](../analysis/drive-curation/opa-labels-probe/README.md): POL-01~50·독스용 PAC50·원본 PAC24·런타임 PAC-01~15를 이름·본문·의미로 이었다. POL 49개 중 47개가 독스용 PAC와 번호가 다르고, (본) POL의 `PAC26`·`PAC45`는 `POL-26`·`POL-45`로 읽어야 하며, 독스용에만 있는 요구가 5개 정책(POL-21·22·26·31·37)에 있다. 기술통제 35개 중 런타임 PAC 대응이 없는 정책이 10개다(런타임 PAC 대응 판단은 Claude의 검토 전 의미 판단). 게이트웨이와 같은 OPA 1.20.2에서 규칙 `labels`는 발화한 규칙에 한해 결정 로그 `rule_labels`로 남고 `id` 주석은 `ids`로 남지 않았다. 코드·정책·배포 변경 없음, 커밋 전.

## 최신: 정책50 구현 공백 보강 레퍼런스 36건 (10-17)

[작업 보고](reports/2026-10-17-policy50-gap-references.md) · [공백 지도](../papers/policy50-gap-references.md) · [검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json): 정책50의 부분 구현 공백(목적지 DNS·서버 outbound, 전송 TLS, 에이전트 신원, 데이터 등급, 대량 조회, 중복 실행, 공급자 측 자격 회수, 경보·자동 대응, 복원 후 재활성화)과 정책 번호 표류를 메울 문헌 36건(`LIB-K01`~`K36`, 카탈로그 167→203건)을 공식 원문에서 확인해 등록했다. 후보 중 BOD 22-01은 2026-06-10 폐지(BOD 26-04로 대체)되어 교체했고 CSAF 2.1·SP 800-52 Rev. 3은 표준·존재 미확인으로 등록하지 않았다. 엑셀 근거 열의 개인정보 보호법·인공지능기본법·ISMS-P 인용은 현행본과 맞는 것을 확인했고 ISO 42001 조항 번호 8건은 검증하지 못했다. **문헌으로 못 메우는 공백**(복원 뒤 폐기 연결 재활성화 거부, LLM 에이전트 위임 증명, MCP용 중복 실행 키)은 우리 설계·시험이 필요하다. 코드·정책·배포 변경 없음, 커밋 전.

## 최신: 승인 소스 MCP 실행기 (DEV-38, 10-15 밤)

[작업 보고](reports/2026-10-15-dev38-runtime.md) · [근거](../analysis/wbs-1015/dev38-runtime.json): 사용자 결정대로 자체 최소 실행기를 구현·배포했다(D-114, 기기 `b639432`). `runtime-worker`가 승인 재확인 → 내부 미러 커밋 해시 대조 → 고정 레시피 빌드 → 이미지 ID로 격리 실행(전용 망, 심사 목적지만 나가는 프록시) → 응답 확인 → ACTIVE를 처리하고, 실행 중인 신청은 그 주소로만 등록된다. MarkItDown을 수동 컨테이너에서 실행기로 옮겼고 PJ1 관리 Claude 정상·`file:` 차단, egress 프로브 5종, 중복·동시 시작·중지·worker SIGKILL·이미지 바꿔치기 시험을 통과했다. 등록 해제·종료·빌드 중 승인 철회의 실기기 정지 시험은 남았다.

## OSS 심층 분석과 경계 보강 (10-15 저녁)

[작업 보고](reports/2026-10-15-oss-deep-analysis.md) · [심층 분석 9건](../analysis/oss-deep/README.md) · [목표 기능 재검토](../analysis/oss-deep/redesign-2026-10-15.md): Codex 작업(문서만)을 확인하고 DEV-29·35 서브세션을 통합했다. Sonnet·sol·Haiku로 ToolHive·LiteLLM·MS Gateway·ContextForge/CPEX·MCPX/Cisco·SDK/Authlib/OPA·Presidio/Gitleaks를 고정 commit에서 L3까지 추적하고 메인이 원본 대조로 정정했다. 분석이 찾은 결함 2건(`tools/list` 첫 페이지만 읽음, OIDC `aud` 미확인)과 검토 RV-01·02·04, DEV-29 1단계를 고쳐 배포했다(D-110~113). 신형 서버 연결 구간 660~800 ms→약 4 ms. 원칙은 그대로이고, 재검토가 제안한 변화는 "승인과 실행 분리(DEV-38 자체 실행기)", "목적지 통제 두 층", "계약에 목록 완결성·판본·outputSchema", "결과 4갈래 기록"이다. 결정 대기 3건은 재검토 문서 끝에 있다.

## 코드·문서·실행 기준

| 구분 | 확인 범위 |
| --- | --- |
| 제품 코드 | `b639432`(10-15 밤, [DEV-38 실행기](reports/2026-10-15-dev38-runtime.md)). 그 전 `8906f24`([OSS 심층 분석](reports/2026-10-15-oss-deep-analysis.md)) |
| Drive 문서 | `10/15-drive-wiki-curation`: `c0b6641`·`1ad6395`, 문서 통합 브랜치에 반영 |
| 이번 위키 보강 | `10/15-wiki-consolidation`, [보고](reports/2026-10-15-wiki-consolidation.md). 제품 코드·DB·정책·배포 변경 없음 |
| 최근 실제 하네스 | [10-15 클린 E2E](reports/2026-10-15-clean-e2e.md): PJ1 관리 Claude Code, GitHub·MarkItDown 정상, 범위 밖 2건 미시도 |
| 현재 배포 관측 | 기기 revision `b639432`, 구성 요소 6개 정상·MCP 3개 READY, MarkItDown은 실행기 실행(5세대 ACTIVE). PJ1 관리 Claude 호출 정상(원장 16) |
| WBS | [스냅샷](../analysis/development-wbs/README.md): 57.5%, 구현 35/40·부분 5/40, 전체 검수 0/40. 이번 문서 작업으로 재산정하지 않음 |

현재 동작과 모든 완료 조건 충족은 다르다. Codex 자연어 E2E·endpoint/원장 상관, 승인 소스 자동 실행, 전체 종료/복구, Windows 실기기는 남아 있다. Context7은 정책 허용 뒤 제공자 할당량 오류가 났고 정상 문서 응답을 확인하지 못했다. 기본 계정 복원 기록은 있으나 이번에 현재 비밀번호를 조회·변경하지 않았다.

## 업스트림 MCP 세션 재사용 설계 비교 (DEV-29, 결정 대기)

[설계 비교](../analysis/upstream-session-reuse/README.md) · [작업 보고](reports/2026-10-15-upstream-session-reuse-design.md): 남은 지연의 본체인 업스트림 연결·목록 단계를 줄이는 선택지를 MCP 규격(`86f6e0c`)·SDK 2.2.0·ContextForge·Microsoft mcp-gateway·Lunar MCPX 고정 커밋으로 비교했다. 추천은 ① 카탈로그의 프로토콜 판으로 SDK 연결 모드 고정(경계 변경 없음) → ② `(주체, 다운스트림 세션, 서버, 자격 해시)` 세션 재사용(D-79 개정, 재판정·종료 차단 유지) → ③ 읽기 도구 한정 목록 캐시(≤30초 TOCTOU, 별도 결정). github 한 건 추정 3.0→2.8→2.25→1.0초. 규격 2026-07-28이 세션을 없앴고, SDK 기본 응답 캐시가 세션 재사용 시 재확인을 조용히 낡게 할 수 있음을 찾았다. 제품 코드·배포는 바꾸지 않았고 시험 T1–T12는 미실행이다. `DECISIONS.md`에는 번호 없는 제안으로 기록했다.

## 관리 계정 루프백 차단 원인·설계 (DEV-35)

[작업 보고](reports/2026-10-15-dev35-loopback.md) · [근거](../analysis/dev35-loopback/README.md): 10-15 루프백 거부 399건은 전부 Codex 브라우저 로그인이었다(브라우저→관리 Codex 1455/1457 SYN-ACK 392, 자기 `/cancel` 7). Claude·하네스 내부 IPC 거부는 0건이며, "임시 포트 쌍"은 관측기가 `SPT`·플래그를 버려 생긴 오독이라 정정했다. PJ1 커널 일회용 netns 시험으로 추천안(장치 코드 기본 + 소유자가 시작한 연결의 응답만 허용, ct mark 0x100)이 E13 반례 7종을 그대로 막는 것을 확인했고, 포트 허용은 1455 선점 반례로 기각했다(결정 제안 제안). 키트 변경·PJ1 재설치·회귀 R1–R9는 사용자 승인 대기.

## 이번에 보강한 지식

- [OSS 종류·깊이·요약 품질 감사](../analysis/oss-audit/README.md): 로컬 clone10개 clean·그중 최신 카드 연결5개, 5개 OSS의 보존21파일 원본/발췌 hash 일치. 선택 함수 분석은 있으나 전체 호출/오류/회수 경로·동등 비교 실행은 부족하다. DEV-47에 정본 정리→핵심 경로→runtime/scanner→사용 의존성→재현 계획을 추가했다. 새 clone·제품 코드·실행 변경 없음.
- [읽기 전용 검토의 누적 정리](../analysis/review-2026-10-15/README.md): 코드 관찰과 미재현 위험을 구분한 RV-01~10, 공식 근거 19건, 목표 G01~10과 검수 조건.
- [Claude 인계](../analysis/review-2026-10-15/claude-next-work.md)와 [DEV-38 최소 실행 경로](../analysis/review-2026-10-15/dev38-runtime-plan.md): 승인 소스·image·runtime·endpoint 연결, 경합·철회·복구·종료.
- [Drive 대조](../analysis/drive-curation/README.md): 두 원본의 셀·수식/저장 캐시·SHA 보존, 50개 이름/본문 동일성, 정책50의 코드 후보/DEV/검수 질문과 MVP24의 G목표 연결.
- [작업별 읽기 지도](../papers/development-reading-guide.md), [ToolHive 실행 후보](../solutions/toolhive-runtime.md), [기업 연동](../integrations/README.md), [증거 계약](../methodology/evidence-contract.md).
- [위키 점검](../analysis/review-2026-10-15/wiki-audit.json): 전체 Markdown 구조와 카탈로그/링크, 각 영역 진입 문서 검토. 연구 문헌 전문 전체 재검토는 아님.

기업 분석의 기존 53개 코드/시험 해시 불일치를 확인했다. 구조적 코드 근거는 현재 판본으로 갱신하고, 바뀐 시험의 과거 통과 5개 조건은 [이전 시험 근거](../analysis/review-2026-10-15/historical-test-anchors.json)와 각 레코드의 historical_test_evidence에 보존했다. 새 실행으로 간주하지 않는다. 판본이 달라진 현재 조건은 재검수 대상으로 표시한다. 공식 검사 결과는 작업 보고에서 확인한다.

## 다음 작업

담당·상태·완료 조건은 [백로그](backlog.md) 한 곳에 유지한다.

1. DEV-41·42·43: 목적지·하네스 명령/헬퍼·계정 철회 경쟁을 재현/반박하고 보강.
2. DEV-38: MarkItDown 한 개를 수동 Docker 명령 없이 신청→승인→실행→등록→PJ1→종료까지 연결.
3. DEV-44·39: 명세 판본/출력·복합 스키마·목록 페이지, 두 하네스의 증거 상관.
4. DEV-45·46·36: 실행 ID/최신성·독립 평가·기기 직접 복사 없는 배포 절차.
5. DEV-29·35·37: 세션·루프백·망 품질. DEV-29·35 별도 조사 브랜치는 아직 통합하지 않았고 제안 D-107 번호 충돌도 정리해야 한다.
6. DEV-47: [OSS 분석 보완](../analysis/oss-audit/README.md). 옛 비교 결론·누락 카드부터 정리하고 DEV-29/38/41/43/44/46에 필요한 경로를 먼저 심화한다. 문서/정적 단계와 실행 검증 등급을 분리한다.

## 과거 결과를 찾을 때

이전 current.md의 상세 결과·정정·과거 판본은 [변경 이력](history-2026-10-15.md)에 그대로 보존했다. [10-15 구현 통합 보고](reports/2026-10-15-wbs-implementation.md), [검사 코퍼스](reports/2026-10-15-inspection-corpus.md), [10-14 엔드포인트 수정](reports/2026-10-14-endpoint-telemetry-fix.md), [Drive 선별 보고](reports/2026-10-15-drive-deliverables.md)는 해당 날짜의 범위로 읽는다. 과거 SDK/선별 실험을 E01~E13 카드 전체 통과로 올리지 않는다.
