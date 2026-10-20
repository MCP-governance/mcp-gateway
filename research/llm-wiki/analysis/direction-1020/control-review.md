# 통제 방향 검토 — 다른 솔루션 코드·중국 기술 통제·공식 지침 대조 (제안 C10, 2026-10-20)

- 기준: 브랜치 `10/20-control-review`(시작 `origin/main` `5b5a134`). 문서만 작성했고 코드·시험·배포는 하지 않았다.
- 대상: 게이트웨이 순차 판정 P0~P11, 엔드포인트 키트, 도입·계약·종료 수명주기, [10-20 방향 갱신](README.md)(RM-01~03, DEV-72~81), 설계 초안 `origin/10/20-dev72-design`·`origin/10/20-dev73-design`.
- 소유자 결정(방향 갱신, D-170, RM-01 자식 프로세스 관용)은 뒤집지 않는다. 문제가 보이면 `재검토 필요`로만 적었다. 새 D-번호는 붙이지 않았다.
- 확인 수준: `읽음` = 해당 파일·조항·페이지 본문을 이번에 열어 읽음, `요약만` = 위키 요약·검색 결과·2차 기사만 봄.

## 레인 작업 지시서용 요약

1. 게이트웨이 순차 판정·계약 고정·독립 승인·차단 우선 종료는 MCP 공식 지침·중국 기술 조항·다른 OSS 반례와 같은 방향이다. 구조는 바꾸지 않는다.
2. 근거 정정: DEV-72는 M05 제6항(제5항은 윤리 규범), DEV-79는 M05 제2항(제3항은 표준 체계), DEV-80의 GB/T 45654 6.7 b)는 단말 '모델' 조항이라 근거에서 뺀다.
3. TC260 프레임워크 3.0 원문은 확보하지 못했다(CAC 해설 기사만). 3.0 조항 번호를 인용하지 말고 2.0 조항만 쓴다.
4. DEV-72 확인은 콘솔에서만, 확인 직전 재인증(OIDC `max_age`/`prompt=login` 또는 WebAuthn)을 요구한다. 하네스와 브라우저가 같은 OS 계정이면 에이전트가 스스로 확인할 수 있다.
5. DEV-72 확인 화면은 실제 전송 인자(제한·마스킹 적용 후)를 잘림 없이 보여 주고, 그 값의 지문을 대조한다.
6. DEV-72의 동의(`P-CONSENT-001`)·본인 확인·독립 승인 순서를 고정하고, 본인 확인 비율·취소 비율을 지표로 남긴다(확인 피로).
7. DEV-73 도입 신청에는 '로컬 실행이 필요한 이유'(로컬 파일·로컬 도구·장치)를 필수로 받는다. 원격 API 래퍼는 거부하고 원격 등록이나 DEV-38 실행기로 보낸다.
8. DEV-73 마운트: 홈 루트·점 디렉터리(`~/.ssh`·`~/.config`·`~/.claude`·`~/.codex` 등)·심볼릭 링크는 금지. 읽기 전용이 기본이고, 쓰기는 정확한 경로 목록으로만 연다.
9. DEV-73 이미지는 자체 서명을 필수로 한다. DEV-77의 '미제공=표시만'은 적용하지 않는다. digest 고정과 `--pull=never`, 내부 미러에서만 받는다.
10. DEV-73은 게이트웨이가 장치 root에 작업을 보내는 구조다. 매니페스트는 게이트웨이에 없는 키로 서명하고 장치에서 검증한다. 작업 본문은 stdin JSON-RPC만 허용한다.
11. DEV-73 컨테이너·이미지 정지를 종료·중지·격리 증거(C1~C4 대상)에 넣는다. 결과 상한(256KiB)과 기기 오프라인 시 동작은 시험에 넣는다.
12. 축소: D-126의 24시간 재전송 차단을 DEV-72 본인 확인으로 바꾸는 안을 검토한다. DEV-74는 경보와 DEV-79 수동 중지를 기본으로 한다.
13. 축소: DEV-80은 새 버퍼를 만들지 않고 OS 로그(journald 커서·Windows 이벤트 로그)를 재연결 때 다시 보낸다.
14. 강화: DEV-81의 우선순위를 올린다(공식 지침 문구와 같다). '정책 거부'와 '검사기 장애로 인한 차단'을 나눠 기록한다.
15. 재검토 필요(결정은 유지): RM-01 이후 Windows의 '비인가 로컬 MCP 차단'은 OS가 아니라 하네스 관리형 설정에만 의존한다. 통제 범위 표시를 엔드포인트 강제가 아닌 값으로 정정한다.

## 0. 근거 범위

| 자료 | 위치 | 확인 수준 |
| --- | --- | --- |
| 우리 정본 | `docs/ai/SECURITY_BOUNDARIES.md`, `docs/ai/ARCHITECTURE.md`, `direction-1020/README.md`, `docs/ai/DECISIONS.md` D-62·D-70·D-119·D-122·D-125·D-126·D-134·D-170·D-172 | 읽음 |
| 설계 초안 | `git show origin/10/20-dev72-design:…/dev72-user-confirmation.md`(D-174), `origin/10/20-dev73-design:…/dev73-local-isolated-run.md`(D-175) | 읽음 |
| P0~P11 정의 | `analysis/arch-review-1018/codex-sol-review.md:59-74` | 읽음(코드 행은 그 문서의 인용이며 이번에 재대조하지 않음) |
| 다른 솔루션 코드 | `analysis/oss-deep/` README·toolhive·litellm·ms-mcp-gateway·contextforge·mcpx·redesign §6~7, `docs/ai/ENDPOINT_ONBOARDING_2026-10-04.md`, `docs/ai/REFERENCES_MCP_SECURITY_2026-10-05.md` | 위키 분석 읽음(원 OSS 코드는 다시 열지 않음) |
| 중국 기술 조항 | `papers/LIB-M05·M28·M29·M31·M32.md`, `analysis/compliance/requirements.json`(REQ-M05/M28/M29/M31/M32), M05 원문 추출 `sources/compliance/LIB-M05/extracts/LIB-M05.md:82,98,104,106,108` | 노트·매트릭스 읽음. M05는 원문 대조. M31·M32 원문은 로컬 전용이라 노트만 봄 |
| TC260 3.0 | CAC 2026-09-17 해설 기사(본문·첨부 없음), 검색 결과 | 요약만 — **원문 미확보** |
| MCP Local Server Security | modelcontextprotocol.io draft 페이지 전문 | 읽음(2026-10-20 접속) |
| Docker MCP Gateway | `docker/mcp-gateway` `docs/security.md` | 읽음(가져오기 요약, 2026-10-20) |
| Cloudflare·Entra GSA·Netskope MCP 통제 | 공식 문서 검색 결과 | 요약만(2026-10-20) |
| OWASP Agentic 2026·LLM 2025, NIST | `papers/LIB-I01.md`(항목명 미검증), `LIB-I04.md`, `catalogs/papers.json`(LIB-L07·LIB-M02) | 요약만 |

## 1. 게이트웨이 순차 판정 P0~P11

| 영역 | 판정 | 근거 | 확인 수준 |
| --- | --- | --- | --- |
| P0 전송 토큰으로만 신원 | 유지 | `ARCHITECTURE.md:132-133`; MCPX 자기 신고 헤더 반례 `oss-deep/mcpx-cisco-scanner.md:99`; MS Gateway `X-Dev-*` 반례 `ms-mcp-gateway-session.md:173`; REQ-M31-13(6.2.5) | 읽음 |
| P1 주체·자원 분류, 모르면 important | 유지 | `ARCHITECTURE.md:134,208`; REQ-M31-06(4.2.3(a)) | 읽음 |
| P2 판정 전 호출 예약(호출량·동시성) | 유지 | `ARCHITECTURE.md:137-138`; REQ-M31-13(6.2.5 API 빈도 제한) | 읽음 |
| P3 입력 스키마·대량 조회 상한 | 유지 | `ARCHITECTURE.md:139-140`, D-125(`DECISIONS.md:1383-1389`) | 읽음 |
| P4 입력 PII·비밀·지시 검사 | 강화 | `언어 고정 "en"`·분할 인코딩 미탐 `oss-deep/deps-presidio-gitleaks.md:39`; REQ-M31-05(4.2.2(b)). 한국어·중국어 표본 미탐률 측정 필요 | 읽음 |
| P5 OPA 판정(PAC·목적 결속·흐름·동의·거주성) | 유지 | `ARCHITECTURE.md:142-145`; REQ-M05-06(제7항 규칙 내장·행동 울타리), REQ-M28-16(제38조 목적·범위 초과 금지) | 읽음 |
| P6 결과 분기(차단/승인 대기/허용·경보·제한) | 강화 | DEV-72가 승인 대기를 '본인'과 '독립'으로 나눈다. REQ-M05-05(제6항 결정 권한 3분류) | 읽음 |
| P7 실행 직전 같은 연결의 `tools/list` 계약 재확인 | 유지 | `ARCHITECTURE.md:146,153`; Local Server Security 'Treat Tool Definitions as Untrusted Input'(rug pull은 1회 동의로 못 막음); MS Gateway 어댑터 단위만 `ms-mcp-gateway-session.md:172` | 읽음 |
| P8 실행 의도 기록·최종 상태 확인 | 유지 | `ARCHITECTURE.md:147-149`; LiteLLM 대조 `litellm-mcp-path.md:203` | 읽음 |
| P8 완료 쓰기 24시간 재전송 차단(D-126) | 축소 | `DECISIONS.md:1391-1395`(의도적 반복도 차단된다고 스스로 적음). 대안은 5장 | 읽음 |
| P9 도구 실행·응답 미확인 구분 | 유지 | `ARCHITECTURE.md:148`; ToolHive는 취소·롤백 보장 없음 `toolhive-runtime.md:175` | 읽음 |
| P10 출력 검사, text 외 형식 보류 | 유지 | `core.py:122` `RESULT_CONTENT_TYPES = {"text"}`; CPEX는 미검사 필드를 통과 `contextforge-hooks.md:157` | 읽음 |
| P11 해시 체인 원장 | 유지 | `ARCHITECTURE.md:157-158`; MCPX 버퍼 유실 반례 `mcpx-cisco-scanner.md:103`; REQ-M05-07(제7항 추적), REQ-M31-17(6.3.6 6개월) | 읽음 |
| 실패는 차단 + 원인 구분 | 강화 | ContextForge `fail_on_plugin_error:false` 반례와 '정책 거부/엔진 장애' 분리 `contextforge-hooks.md:151-152`; 결정 `redesign-2026-10-15.md:45`(DEV-48) — 구현 여부는 이번에 확인 안 함 | 읽음(구현은 요약만) |

## 2. 엔드포인트 키트

| 영역 | 판정 | 근거 | 확인 수준 |
| --- | --- | --- | --- |
| Linux 관리 계정 + nft UID egress + AppArmor 실행 목록 | 유지 | `endpoint-agent/enforce-linux.py:67-82`; Local Server Security 'Going further: … separate user account'; Windows ODR 별도 에이전트 계정 `ENDPOINT_ONBOARDING_2026-10-04.md:11,33` | 읽음 |
| 관리 계정 루프백: 소유자 시작 연결 응답만 | 유지 | D-119 `DECISIONS.md:1339-1345` | 읽음 |
| Windows 계정 SID 전체 방화벽 | 삭제(RM-01대로) | `managed-windows.py:96-104`(SID 범위, 복사본도 가둠); `README.md:36-43` | 읽음 |
| Windows 하네스 프로그램 범위 규칙 + 하네스 샌드박스 네트워크 끔 | 유지(조건) | `README.md:39-42`. 샌드박스는 하네스 안의 통제라 판본별 Windows 지원을 실측해야 함 | 읽음(지원 여부는 미확인) |
| 하네스 관리형 설정(배타적 MCP 목록, Codex requirements) | 유지 | `SECURITY_BOUNDARIES.md:53-73`; Cloudflare Portal도 '승인 경로 + 우회 탐지' 구조(요약만) | 읽음 |
| 하네스 설정 인벤토리·섀도 보고 | 유지 | `ARCHITECTURE.md:228-234`; Local Server Security 'Inventory continuously' | 읽음 |
| 보고 중단 시 일시 격리(180초), 영구 격리 없음 | 유지 | D-172 `DECISIONS.md:1770-1775` | 읽음 |
| 장치 하드웨어 증명 | 조직 통제 의존으로 넘김 | D-170 `DECISIONS.md:1762-1768`; Entra 조건부 접근(요약만) | 읽음 |
| 같은 PC 다른 계정·하네스 복사본·웹 커넥터·개인 토큰 직접 API | 조직 통제 의존으로 넘김 | D-170; Cloudflare·Entra GSA·Netskope가 MCP 트래픽 식별·서버/도구 단위 차단을 제공(요약만) | 읽음/요약만 |
| 통제 상태 표시(`gateway_enforced`…`bypass_possible`) | 강화 | `SECURITY_BOUNDARIES.md:17-21`. D-170 이후 `조직 통제 의존` 값과 Windows 로컬 MCP 행(9장) 반영 필요 | 읽음 |

## 3. 도입·계약·종료 수명주기

| 영역 | 판정 | 근거 | 확인 수준 |
| --- | --- | --- | --- |
| 신청자≠승인자, 동의와 승인 분리 기록 | 유지 | `SECURITY_BOUNDARIES.md:292-294`; REQ-M31-15(6.3.1) | 읽음 |
| 도입물 출처·고정 커밋·해시, 내부 사본 재해시 | 유지 | `SECURITY_BOUNDARIES.md:295-296`; REQ-M31-12(6.2.2-6.2.3); Local Server Security 'Check Provenance' | 읽음 |
| 검사 신선도(7일)·치명 발견 기한부 수용 | 유지 | `SECURITY_BOUNDARIES.md:297-298`; D-120 `DECISIONS.md:1347-1351` | 읽음 |
| 계약 사람 승인(TOFU 금지)·도구 단위 제한 | 유지 | `AGENTS.md` 불변식; Local Server Security 'Prefer clients that pin tool definitions'; D-127 | 읽음 |
| 계약 범위 = 전체 목록·협상 판본·outputSchema | 강화 | `redesign-2026-10-15.md:9,18`; LiteLLM 원본 필드 손실 `litellm-mcp-path.md:199`; D-149 일부 반영 | 읽음 |
| 자동 기한 연장(D-70) | 유지(DEV-75와 결합) | `DECISIONS.md:873-881`; 연장 조건에 사용 이력 `README.md:68` | 읽음 |
| 종료: 차단 먼저, C1~C4 최저 등급 | 유지 | `ARCHITECTURE.md:248-251`; MS Gateway 삭제 시 세션 미정리 `oss-deep/README.md:24` | 읽음 |
| 종료 증거에 실행물 정지 추가 | 강화 | `redesign-2026-10-15.md:11`; DEV-73 컨테이너가 새 대상(8장) | 읽음 |
| 원장 보존 하한·봉인 폐기 | 유지 | `SECURITY_BOUNDARIES.md:302-308`; REQ-M31-17(6.3.6 6개월 이상) | 읽음 |
| 사고 대응(SBOM 영향 조회·egress 차단·자격 회전) | 강화(DEV-76) | Local Server Security 'Plan for the fleet incident'; REQ-M05-09(제9항) | 읽음 |

## 4. 10-20 방향 갱신

| 영역 | 판정 | 근거 | 확인 수준 |
| --- | --- | --- | --- |
| D-170 관용 원칙 | 유지 | Local Server Security '로컬 서버는 조직의 엔드포인트·소프트웨어 관리 책임'; Cloudflare Portal 출시 글이 직접 접근 차단은 원 서버 인가에 의존한다고 밝힘(요약만) | 읽음 |
| RM-01 프로그램 범위 규칙 | 유지(재검토 필요 1건, 9장) | `README.md:36-43` | 읽음 |
| RM-02 일시 격리 + 재활성화 | 유지 | `README.md:45-48`, D-172 | 읽음 |
| RM-03 국외 처리 심사를 등록 시점으로 | 유지 | `README.md:50-55`; REQ-M28-16(제38조 평가 범위 초과 금지)·REQ-M29-13(제39조 국외 제공 고지·단독 동의 — DLP가 개인정보 전송은 계속 막아야 함) | 읽음 |
| DEV-72 사용자 확인 단계 | 강화(제약 7장) | REQ-M05-05(제6항), REQ-M31-15(6.3.1), REQ-M05-10(제10항 인간-기계 협업 심사). README·초안의 'M05 제5항'은 정정 | 읽음 |
| DEV-73 승인 로컬 MCP 격리 실행 | 강화(제약 8장) | Local Server Security 'Run Servers in an Isolated Environment'·'Limit Filesystem Access'·'Control Network Egress'; REQ-M31-06(4.2.3(a)) | 읽음 |
| DEV-74 반복 위반 자동 일시 중지 | 축소 | GB/T 45654 6.5 a)는 생성형 서비스의 위법 '입력' 반복에 대한 조항(REQ-M32-14). 기존 서버 단위 자동 중지 D-122 `DECISIONS.md:1361-1365`와 중복 | 읽음 |
| DEV-75 미사용 도구 자동 비활성 | 유지 | REQ-M31-03(4.2.1(b) 불필요한 서비스 끄기); Local Server Security 첫 Tip(쓰지 않는 서버 제거) | 읽음 |
| DEV-76 SBOM 영향 조회·전사 대응 | 유지(우선순위 2→1 검토) | Local Server Security 'Plan for the fleet incident'(찾기·egress 차단·자격 회전·고정 판본 배포); REQ-M05-09 | 읽음 |
| DEV-77 서명·증명 검증 | 강화 | Local Server Security 'verify … rather than just noting their presence'; Docker MCP Gateway `--verify-signatures` 기본 켜짐(`mcp/` 이미지); ToolHive `warn`이 provenance 없으면 통과 `oss-deep/README.md:22` | 읽음 |
| DEV-78 승인 판본 되돌리기 | 유지 | REQ-M31-11(6.1.10) | 읽음 |
| DEV-79 직원별 MCP 즉시 중지 | 유지 | REQ-M31-07(4.2.3(b)-(c) 서킷 브레이커·원클릭 통제), REQ-M05-03(**제2항**). README의 '제3항'은 정정 | 읽음 |
| DEV-80 오프라인 관측 버퍼 | 축소 | 근거 조항 GB/T 45654 6.7 b)는 단말 '모델' 로그이며 REQ-M32-16이 '해당 없음'으로 적음. Local Server Security 'Keep an audit trail'은 일반 근거로만 | 읽음 |
| DEV-81 로컬 수신 지점 인증 점검 | 강화(우선순위 2→1) | Local Server Security 'Binding to 127.0.0.1 is not an authentication boundary … real authentication and origin validation' | 읽음 |
| 미채택(신고·등록·보고 서식) | 유지 | `README.md:76` | 읽음 |

## 5. 과잉·방향 의심 항목 — 대안과 변경 영향

| 항목 | 문제 | 대안 | 변경 영향 |
| --- | --- | --- | --- |
| D-126 완료 쓰기 24시간 재전송 차단 | 정당한 반복 쓰기(같은 알림·같은 줄 추가)도 하루 동안 막히고 관리자만 풀 수 있다(`DECISIONS.md:1396`) | `P-RATE-003` 대상 중 **definite 완료 쓰기**는 차단 대신 DEV-72 본인 확인(`P-CONFIRM-001`과 같은 경로)으로 보낸다. `pending`·`uncertain`은 지금처럼 차단 | OPA 기대값·`P-RATE-003` 시험 변경 → 기존 시험 변경 규칙대로 적대 검증. DEV-72 구현 뒤에만 가능. 정책 ID 유지 여부 결정 필요 |
| DEV-74 사용자 자동 일시 중지 | 오탐 누적으로 정상 사용자가 멈춘다(README도 인정). D-122 서버 중지와 키가 달라 중지 원인이 두 갈래 | 기본값을 '경보 + 관리자에게 DEV-79 중지 제안'으로 하고, 자동 중지는 우회 시도·오염 탐지처럼 오탐이 낮은 정책 ID만 설정으로 켠다 | DEV-74 범위 감소, DEV-79와 같은 상태 값 재사용. 새 상태·화면 하나 줄어듦 |
| DEV-80 오프라인 버퍼 | 근거 조항 불일치. 게이트웨이가 끊기면 MCP 호출 자체가 불가해 버퍼 대상이 OS 차단 기록뿐 | 새 보호 버퍼 대신 journald 커서·Windows 이벤트 로그 레코드 번호를 저장하고 재연결 때 그 뒤 기록을 기존 원본 해시 중복 규칙으로 보냄 | 버퍼 상한·보존 설계 불필요. OS 로그 회전으로 잃는 구간은 '누락 구간'으로 보고 |
| DEV-73 방향 문서의 '로컬 중계 + 판정 전용 API'(안 A) | 판정·출력 통제가 둘로 갈라지고 로컬 수신 지점이 생긴다(초안 `dev73…md:24`) | 초안의 안 B(게이트웨이 경유 + 장치 작업 채널)에 동의. 장치에 수신 포트가 없고 DEV-81 대상이 늘지 않는다 | 방향 문서 DEV-73 문구 정정 필요(소유자 결정인 '승인된 것만 격리 실행'은 그대로) |
| DEV-77 '미제공=표시만'을 내부 이미지에도 적용 | ToolHive `warn` 통과와 같은 실패 모드 | 외부 원격 공급자는 표시만, **우리가 빌드·배포하는 이미지(DEV-38·DEV-73)는 자체 서명 필수·불일치 차단** | cosign 키 관리 범위가 실행기·장치로 넓어짐 |

## 6. 빠진 것

| 항목 | 근거 | 확인 수준 |
| --- | --- | --- |
| DEV-73 도입 심사의 '로컬 실행 필요' 판단 | Local Server Security 'Ask Whether It Needs to Run Locally', 'Deploy centrally where local access is not required' | 읽음 |
| 확인·승인 피로 지표(본인 확인 비율·취소 비율·평균 대기) | OWASP Agentic 2026(항목명 미검증), DEV-72 초안 `dev72…md:70`이 '운영 데이터로 임계 조정'만 적음 | 요약만 |
| 정책 거부/검사기 장애/공급자 실패 분리 기록의 구현 확인 | `redesign-2026-10-15.md:10,45` | 읽음(구현은 미확인) |
| 입력 검사 언어 범위(한국어·중국어) 미탐률 | `deps-presidio-gitleaks.md:39` | 읽음 |
| 실행 중 이미지 egress 허용 목록(서버 자신의 외부 통신) | `redesign-2026-10-15.md:8`; Docker MCP Gateway `--block-network`는 선택 옵션(기본 전체 차단 아님) | 읽음 |

## 7. DEV-72 사용자 확인 — 제약과 반례

초안(`origin/10/20-dev72-design`)의 `kind` 열·`P-CONFIRM-001` 하나에서만 `self`·독립 승인 규칙을 `independent_approval`로 묶는 방식(`dev72…md:23,29-35,41-45`)은 옳다. 새 판정 값을 만들지 않는 선택도 맞다. 아래는 구현 레인이 지켜야 할 조건이다.

| # | 제약·반례 | 근거 |
| --- | --- | --- |
| 72-1 | 근거 표기를 'M05 제6항·제10항, TC260 2.0 6.3.1'로 고친다(초안 4행·방향 문서 65행의 '제5항'은 윤리 규범 조항) | `sources/…/LIB-M05.md:96-98` |
| 72-2 | **같은 OS 계정 반례**: Windows에서 하네스가 직원 계정으로 돌면 셸 자식 프로세스가 브라우저 세션을 쓰거나 브라우저를 조작해 `console` 토큰으로 스스로 확인할 수 있다. 초안은 이를 D-170으로 넘기지만(`dev72…md:65`) 콘솔 쪽에서 막을 수 있다 → 확인 API는 최근 재인증(OIDC `max_age`/`prompt=login`, 가능하면 WebAuthn 사용자 존재 확인)을 요구한다 | `dev72…md:50,65`; `README.md:36-42`; 9장 |
| 72-3 | 확인 화면은 **실제 전송 인자**(OPA 제한·입력 마스킹 적용 후, D-131) 전체를 잘림 없이 보이고, 지문은 그 값으로 계산한다. 화면에 보인 값과 실행 값이 다르면 거부 | SEP-1024(명령·인자 잘림 없이 표시, `papers/LIB-A08.md:16`); `ARCHITECTURE.md:140-141` |
| 72-4 | 순서 고정: 동의(`P-CONSENT-001`) → 본인 확인 → 실행. 동의가 없으면 확인 행을 만들지 않거나, 확인 화면에서 동의를 같이 받는다(왕복 두 번 방지). 동의는 90일·도구 단위, 확인은 1회·호출 단위로 서로 대체하지 않는다 | D-134 `DECISIONS.md:1452-1456` |
| 72-5 | 하네스 `mcp` 토큰 거부만으로는 부족하다. 확인 API는 장치 결속 토큰·`agent` 경로·`/gw` 프록시의 비관리자 허용 목록(`activity`·`health`)과도 겹치지 않는지 `open_endpoints` 검사에 넣는다 | `ARCHITECTURE.md:238-239`; `dev72…md:49-50` |
| 72-6 | 확인 뒤 재판정에서 다른 승인 규칙이 걸리면 새 **독립** 행이 생기고 실행 0이어야 한다(초안 시험 계획에 있음). 중대 영향 도구는 `confirm` 지정이 있어도 독립 승인 | `dev72…md:45,75` |
| 72-7 | 하네스 안 되묻기(elicitation)는 증거로 쓰지 않는다(초안과 같음). 결과 기록은 `확인 경로` 필드로 구분 | `dev72…md:59`; D-134 근거 절 |
| 72-8 | `tier == medium` 서버의 w/x 전체를 확인 대상으로 하면 확인 피로가 생긴다. 첫 배포는 도구 지정(`confirm: true`)만 켜고 등급 조건은 지표를 본 뒤 켠다 | `dev72…md:32,70` |
| 72-9 | 원장·SIEM에서 본인 확인과 독립 승인이 같은 `Approval`로 집계된다. 대시보드·내보내기는 `policy_id`와 `kind`로 나눠 보여야 한다 | `dev72…md:24` |

## 8. DEV-73 승인 로컬 MCP 격리 실행 — 제약과 반례

초안(`origin/10/20-dev73-design`)의 안 B(게이트웨이 경유 + 장치 작업 채널), root 실행기 → rootful podman `--user`, `--network=none --read-only --cap-drop=ALL --pull=never`(`dev73…md:25,38,40-41`)는 공식 지침의 Baseline과 맞다. 관리 계정 rootless podman·bubblewrap·ToolHive를 기각한 이유(`dev73…md:34-37`)도 근거가 있다.

| # | 제약·반례 | 근거 |
| --- | --- | --- |
| 73-1 | 도입 신청에 '로컬 실행 필요 이유'(로컬 파일·로컬 도구·장치 중 하나)를 필수로 받는다. 원격 API만 감싸는 서버는 거부하고 원격 등록이나 DEV-38 실행기로 보낸다 | Local Server Security 'Ask Whether It Needs to Run Locally' |
| 73-2 | 마운트: `~` 자체·점 디렉터리(`.ssh`·`.aws`·`.config`·`.claude`·`.codex`·`.gnupg`·키트 디렉터리)·심볼릭 링크·하드 링크 대상 금지. 읽기 전용 기본, 쓰기는 정확한 경로 목록. 마운트 판정은 실행 시점에 다시 한다(신청 뒤 링크 교체) | 'never your home directory', 'Remember files count too'; Docker MCP Gateway 쓰기 바인드는 정확 경로 목록·기본 읽기 전용 |
| 73-3 | **게이트웨이 → 장치 root 경로 반례**: 게이트웨이가 탈취되면 `managed_policy`로 새 매니페스트를 내려 모든 장치에서 root 실행기를 움직일 수 있다. 매니페스트는 게이트웨이에 없는 키(두 사람 승인, D-123처럼 키 분리)로 서명하고 장치가 검증한다. 작업 본문은 stdin JSON-RPC 메시지만 받고 이미지·명령·마운트·환경 값을 바꾸지 못한다 | `dev73…md:47,53`; D-123 `DECISIONS.md:1369-1373` |
| 73-4 | 이미지: 내부 미러에서만 받고 자체 서명 필수(DEV-77 '표시만' 예외 금지). digest 불일치·서명 불일치는 차단 | ToolHive `warn` 통과 `oss-deep/README.md:22`; Docker `--verify-signatures` |
| 73-5 | rootful 엔진 탈출 = root(초안 인정). 첫 구현에도 `--userns=auto`나 idmap 마운트를 실측해 둘 중 되는 것을 기본으로 하고, 안 되면 '컨테이너 탈출 시 root' 한계를 통제 범위 표시에 남긴다 | `dev73…md:66`; Local Server Security 'A container is not an impenetrable boundary' |
| 73-6 | 따뜻한 컨테이너(사용자·서버별 세션)는 승인 철회·계약 변경·장치 격리·주체 중지·종료 케이스 시작 때 즉시 정지하고, 정지·이미지 제거를 종료 증거(C1~C4 대상)로 남긴다. 유휴 시간 제한도 둔다 | `dev73…md:54`; `redesign-2026-10-15.md:11` |
| 73-7 | 작업 API는 기존 장치 인증 의존성(`endpoint_device("enforcement")`, `main.py:1463-1464`)을 쓰고 `open_endpoints` 분류에 들어가야 한다. 일시 격리(180초) 장치에는 작업을 배정하지 않는다 | `AGENTS.md` 불변식; D-172 |
| 73-8 | 게이트웨이가 장치 결과를 기다리는 동안 예약(P2)·작업 마감·장치 long-poll(25초) 시간의 관계를 정한다. 마감이 예약 lease보다 길면 동시 실행 한도가 무너진다. 수령 뒤 무응답은 `UNCONFIRMED`이고 같은 쓰기는 자동 재시도하지 않는다 | `dev73…md:52-56`; `ARCHITECTURE.md:148-149` |
| 73-9 | 로컬 파일 결과가 게이트웨이를 거치므로 `MAX_RESULT_BYTES`(기본 256KiB)·건수 상한·DLP가 그대로 적용된다. 큰 파일 읽기는 `MCP-OUTPUT-001`로 막히는 것이 정상 동작임을 시험·안내에 넣는다 | `core.py:58`; D-125 |
| 73-10 | 실행기가 MCP stdio 클라이언트를 품으면 엔드포인트 에이전트(현재 표준 라이브러리만 import, `agent.py:50-69`)에 SDK 의존이 생긴다. 키트 크기·판본 고정·라이선스를 기록하거나 실행기를 별도 root 서비스로 나눈다 | `dev73…md:54`; 방향 문서 '키트 크기' `README.md:66` |
| 73-11 | 비밀이 필요한 로컬 서버는 범위 밖(초안과 같음). 범위를 넓힐 때는 서버별 좁은 자격·짧은 수명·OS 비밀 저장소가 조건 | Local Server Security 'Isolate Credentials' |
| 73-12 | 실기기 시험은 공개 OSS(`@modelcontextprotocol/server-filesystem` 고정 digest)로 하고, 음성 대조로 컨테이너 외부 연결·매니페스트 밖 폴더·관리 계정 `podman` 실행·서명 바꾼 이미지·게이트웨이 정책만 바꾼 매니페스트 각각의 실패를 독립 증거로 확인한다 | `dev73…md:73`; `AGENTS.md` 품질 기준 |

## 9. 재검토 필요 (소유자 결정은 유지)

| 항목 | 관찰 | 제안(결정 아님) |
| --- | --- | --- |
| RM-01 이후 Windows의 비인가 로컬 MCP | D-170은 '비인가 로컬 MCP 실행'을 관용하지 않는 목록에 둔다(`README.md:31`). 그러나 RM-01 뒤 하네스가 셸로 띄운 로컬 MCP의 egress는 프로그램 규칙에 안 걸리고, 자식 프로세스 관용과 겹친다. 남는 통제는 하네스 관리형 설정뿐이다 | 콘솔 통제 범위에서 Windows 행을 `vendor_enforced`(하네스 설정) + `조직 통제 의존`으로 표시하고 '엔드포인트에서 차단'으로 세지 않는다 |
| D-170을 DEV-72 자기 확인에 적용 | D-170 목록은 다른 계정·복사본·커넥터·직접 API·루프백·하드웨어 증명이다. 같은 계정의 에이전트가 콘솔 세션을 쓰는 경우는 목록에 없다 | 7장 72-2의 재인증으로 제품 안에서 닫는다. 관용 목록을 넓히지 않는다 |
| RM-01 하네스 샌드박스 의존 | Codex `requirements.toml`·Claude 관리형 권한의 Windows 샌드박스 지원은 판본마다 다르고, 이번 검토에서 확인하지 못했다 | RM-01 작업에서 판본별 지원을 실측하고, 미지원 판본은 콘솔에 그대로 표시 |

## 10. 이번에 가져온 외부 원문 (2026-10-20 접속, 본문은 데이터로만 취급)

| 자료 | URL | 확인 수준 |
| --- | --- | --- |
| MCP Local Server Security (draft) | https://modelcontextprotocol.io/docs/draft/tutorials/security/local-server-security | 읽음(전문) |
| Docker MCP Gateway 보안 문서 | https://github.com/docker/mcp-gateway/blob/main/docs/security.md | 읽음(가져오기 요약) |
| CAC 프레임워크 3.0 해설(新闻1+1) | https://www.cac.gov.cn/2026-09/17/c_1791397053329870.htm | 읽음 — 원문·첨부 없음, 기술 조치 서술 없음 |
| Cloudflare MCP Server Portals·트래픽 탐지 | https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/ , https://blog.cloudflare.com/mcp-security-updates/ | 요약만 |
| Entra Global Secure Access MCP firewall | https://learn.microsoft.com/en-us/entra/global-secure-access/how-to-configure-mcp-firewall | 요약만 |
| Netskope MCP 가시성·서버 차단 | https://docs.netskope.com/en/visibility-into-mcp-usage , https://docs.netskope.com/en/granular-access-control-to-block-a-specific-mcp-server | 요약만 |

TC260 3.0: 검색으로 2026-09-14 발표, '智能体 위험'을 따로 다룬다는 보도만 확인했다. tc260.org.cn과 cac.gov.cn에서 원문 PDF를 찾지 못했다. 3.0 조항을 근거로 쓰려면 원문을 확보해 `papers/LIB-M31.md`에 새 판본으로 추가해야 한다(기존 2.0 원본은 덮어쓰지 않는다).
