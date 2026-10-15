# 개발 현황 — 2026-10-15

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
