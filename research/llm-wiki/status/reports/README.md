# 작업 보고서 색인

`build_report_index.py`가 만든 생성 파일이다. 직접 고치지 않는다. 작업 ID나 결정 번호는 이 파일에서 검색하거나 `build_report_index.py --find DEV-89`로 찾는다. 새 보고서를 쓴 뒤에는 도구를 다시 실행한다. 「관련 ID」는 본문에서 많이 언급된 순이며 그 보고서가 정의한 ID라는 뜻은 아니다.

보고서 191개(최신순). 원본 증거 파일 23개(JSON·JSONL·패치)는 같은 폴더에 있다.

| 날짜 | 보고서 | 첫 문장 | 관련 ID |
| --- | --- | --- | --- |
| 2026-10-31 | [2026-10-31 정책 정의와 집행 근거 조회 보완](2026-10-31-policy-evidence-ui.md) | 정책 목록에 정책 식별자와 집행 주체, 관리 상태, 정의된 결과, 최근 원장 기록 여부 및 명시적 POL 연결을 표시한다. | — |
| 2026-10-31 | [2026-10-31 조직 보안 정책 탭](2026-10-31-organization-policy-tab.md) | POL-001~090의 정책 원문과 구현 분류에서 재생성 가능한 제품 카탈로그를 만들었다. | — |
| 2026-10-31 | [2026-10-31 통제 현황 기능 재배치](2026-10-31-control-page-consolidation.md) | MCP 서버 메뉴를 AI 연결 관리로 바꾸고 연결 목록, 벤더 커넥터, 정책 내보내기를 옮겼다. | — |
| 2026-10-28 | [MINT 엔드포인트 키트(Linux) 직원 경로 점검 결과 (2026-10-28)](2026-10-28-kit-troubleshoot.md) | 브랜치 10/28-windows-kit · 수정 커밋 471ab440(+ 결정 D-295 문서 커밋) · :8000 시험 스택에 배포 · 확인 … | D-295 |
| 2026-10-28 | [키트 터미널 화면 카드 배치 재설계 (2026-10-28)](2026-10-28-kit-terminal-cards.md) | 브랜치 10/28-windows-kit(2dde7d39·eaf586c9) → PR #67 브랜치에 같은 변경(979dbd28·2a557fa1). | D-296 D-297 |
| 2026-10-28 | [키트 설치 결과·재실행 수정 — 2026-10-28](2026-10-28-kit-install-result.md) | D-271은 Linux·Windows·macOS 결과를 등록 당시 값 대신 서비스 보고에 맞추고, 보고가 없으면 확인 불가로 둔다. | D-271 D-272 D-251 |
| 2026-10-28 | [2026-10-28 설정 섀도 집계·모델 로그인 안내·설치 연결 복구](2026-10-28-fix5-config-login-retry.md) | core.py:2419가 endpoint_plane.shadow_count_for(endpoint_plane.py:487)의 값을 princip… | D-279 |
| 2026-10-28 | [npm Codex 경로·실행 장애·토큰 갱신 실패 수정 — 2026-10-28](2026-10-28-fix4-npm-auth.md) | 정책·신원·계약 승인·감사 기록·토큰 전달은 변경하지 않았다. | D-273 D-278 D-275 |
| 2026-10-28 | [하네스 진입 파일·설치 연결부·모델 인증 표시 수정 — 2026-10-28](2026-10-28-fix3-entry-auth.md) | Windows Python 3.10에서 python -B -X utf8로 실행했다. | D-271 D-273 D-274 |
| 2026-10-28 | [2026-10-28 사용자 관리와 엔드포인트 관리 분리](2026-10-28-console-management-split.md) | 사용자 관리에는 사용자, 삭제된 사용자, 이용 중지, 가입 요청, 조건부 SSO를 배치했다. | — |
| 2026-10-27 | [2026-10-27 Windows GUI 별도 프로그램 실행·바탕화면 바로가기](2026-10-27-windows-gui-launcher.md) | 트레이는 설치 때 만들어지는 MCPGateway.exe(콘솔 없는 실행 파일, 방패 아이콘)가 같은 폴더의 tray.ps1을 자기 프로세스에서 … | D-260 |
| 2026-10-27 | [2026-10-27 Codex gpt-6.1-terra(high) 시험 결과 — :8000 시험 배치·PJ1·pj3](2026-10-27-terra-test.md) | 대상: 솔루션 기기의 :8000 시험 배치와 PJ1, pj3. | D-267 |
| 2026-10-27 | [2026-10-27 게이트웨이 수정본 PJ1 재시험과 수동 시험 매뉴얼](2026-10-27-retest-pj1.md) | PJ1 없이, field 게이트웨이 컨테이너(7df769c) 안에서 배포 코드의 core._inspected_result·_guarded_res… | D-243 D-248 D-214 |
| 2026-10-27 | [2026-10-27 정책 90개 PaC 구현](2026-10-27-pac-policy90.md) | 정책 90개 중 65개에 Rego 판정, 25개는 솔루션·제외(사유 기록). | D-251 D-261 |
| 2026-10-27 | [2026-10-27 보안정책 89개 PaC 구현 분석](2026-10-27-pac-policy89.md) | 89개 중 64개(72%)는 판정을 Rego로 쓸 수 있다(Rego 단독 23, 솔루션 센서 필요 41). | — |
| 2026-10-27 | [2026-10-27 사내 저장소 직접 접근 차단·콘솔 HTTPS (D-262)](2026-10-27-internal-repo-console-only.md) | 출처: 10-27 개발 온보딩 회의 3번(내부저장소 관리 / 소스코드 관리) | D-262 D-48 D-129 |
| 2026-10-27 | [2026-10-27 콘솔 메뉴 통합](2026-10-27-console-ia.md) | 승인 대기에 이용 동의, 호출·감사 기록에 감사 원장·사고 보고 기한·보안 관제 전달, MCP 서버에 MCP·커넥터·미등록·잔존·벤더 커넥터, … | DEV-93 D-265 |
| 2026-10-27 | [2026-10-27 S4 잔여 결함 1회차 수정](2026-10-27-bugfix-round1.md) | D-269: 기존 하네스 제외가 빠진 소켓 관찰과 공백 경로 Node 하네스의 섀도 오탐을 수정했다. | D-269 D-270 D-268 |
| 2026-10-26 | [2026-10-26 Windows 키트 화면·진단 수정](2026-10-26-windows-tray-ux.md) | windows-common.ps1·tray.ps1: 상태 enum 대신 현재 언어의 값 표시, 저장된 게이트웨이 정상 결과·하네스 없음·건너뜀 … | DEV-84 DEV-89 D-255 |
| 2026-10-26 | [2026-10-26 리팩토링 0단계 — 측정·안전망 (DEV-91)](2026-10-26-refactor-stage0.md) | 구현·병합·배포를 분리하면 다음과 같다. | DEV-91 D-252 D-251 D-253 |
| 2026-10-26 | [2026-10-26 Unix 엔드포인트 키트 재설치 점검](2026-10-26-linux-kit-reinstall.md) | managed-linux.enroll은 설치 파일 변경 없이 등록·정책 수신을 수행한다. | DEV-84 DEV-87 D-255 D-253 |
| 2026-10-25 | [2026-10-25 위키 구조·최신화 점검 (WIKI-08)](2026-10-25-wiki-structure.md) | 읽기량은 줄었고, 낡음을 재는 도구가 생겼다. | WIKI-08 DEV-72 WIKI-04 AIG-02 D-237 D-230 D-238 |
| 2026-10-25 | [2026-10-25 릴리스 판본·기업 적용 패키징·위생·브랜치 정리](2026-10-25-release-packaging.md) | VERSION = 0.9.0, CHANGELOG.md(Keep a Changelog, 한국어). | DEV-73 DEV-38 DEV-71 DEV-69 D-242 D-59 D-241 |
| 2026-10-25 | [2026-10-25 리팩토링·최적화 제안서 — main v0.9.0 진단, 3평면 재설계, 설치 편의, 외부 레퍼런스 보강](2026-10-25-refactor-proposal.md) | 제안서 analysis/refactor-proposal-1025/README.md: 진단(규모·커밋 비율·실측 지연·구조 문제 10개) → 3평… | WIKI-09 D-243 |
| 2026-10-25 | [2026-10-25 정책 동기화 모델 교체 (P0-1, D-238)](2026-10-25-policy-sync-split.md) | 판정 모델. | DEV-90 D-198 D-212 D-238 |
| 2026-10-25 | [2026-10-25 LiteLLM 애드온 — 기업 적용·정상 기능(S5)](2026-10-25-litellm-addon.md) | 대역이 가렸던 실제 결함 다섯 가지(CI 반복으로 찾아 모두 정정) — ① 1.105는 require_key_mcp_access_defined를… | D-208 D-250 D-249 |
| 2026-10-25 | [2026-10-25 엔드포인트 키트 편의·자동화 — 간편 모드 기본, 자동 활성화, Windows 같은 계정, TUI (D-239)](2026-10-25-kit-usability.md) | 코드: bootstrap.connect(모드 분기·이전 설치 원복·격리 계정 정리), managed-linux.install --mode sim… | D-238 D-216 D-217 |
| 2026-10-25 | [2026-10-25 게이트웨이 결함 수정 — 실사용 버그 시험(S4) 후속](2026-10-25-gw-bugfix.md) | S4-03(관찰기 명령줄 표지)·S4-11(mcpgw-status 표시)은 endpoint-agent/(S1 소유)라 손대지 않았다. | D-238 D-246 D-214 |
| 2026-10-25 | [2026-10-25 GitHub 직원별 계정 연결 (D-235)](2026-10-25-github-per-user.md) | 구현됨: 암호화 저장(AES-GCM, USER_CREDENTIAL_KEY), 선택 순서(직원 연결 → 운영자 파일의 그 직원 행 → 없음, 같은… | D-235 |
| 2026-10-25 | [2026-10-25 PJ1·솔루션 기기 실사용 버그 시험 (S4)](2026-10-25-bugbash-pj1.md) | S4-04는 번호를 비웠다(조사 중 S4-01의 부수 결함으로 합침: 아래 S4-01 「부수」). | D-238 D-198 D-213 |
| 2026-10-23 | [2026-10-23 Windows 원클릭 설치 구현](2026-10-23-windows-oneclick.md) | 콘솔 Windows 버튼은 ZIP 대신 mcp-managed-setup-windows.cmd 한 파일을 받는다. | D-68 D-71 D-72 |
| 2026-10-23 | [2026-10-23 시트·위키 동기 점검과 위키 첫 화면 정리](2026-10-23-wiki-sheet-sync.md) | main --since=2026-10-21 커밋 로그에서 시트에 없던 항목: 회원가입 수정 1c59a00, 애드온 db8cb13, 로컬 MCP … | WIKI-07 DEV-72 OPS-01 AIG-01 D-130 D-131 D-176 |
| 2026-10-23 | [ACK WBS-EVIDENCE — WBS 단계 값 증거 감사 (2026-10-23)](2026-10-23-wbs-evidence.md) | 감사 정본에 상향 10칸·하향 8칸·변경 대상 17개 ID, 전체 57행 점검표, D-185~D-213 연결표, 후속 PJ1/pj3 시험 상위 … | AIG-02 D-185 D-213 D-212 |
| 2026-10-23 | [2026-10-23 오늘 기능의 수용 시험 항목 추가 (W7)](2026-10-23-w7-acceptance-today.md) | acceptance.py에 항목 3개를 추가했다(console-registration-pins-and-expires 바로 뒤, 같은 실제 fet… | D-199 D-201 D-206 |
| 2026-10-23 | [2026-10-23 루트 전용 공식 이미지(git·time) 격리 실행 불가 — W14](2026-10-23-root-only-images.md) | /app/.venv/bin/mcp-server-*는 -rwxr-xr-x root로 실행 권한이 있다. | D-206 D-207 |
| 2026-10-23 | [2026-10-23 조사 묶음 — 최신 레퍼런스·기업 사례·업계 동향](2026-10-23-research-bundle.md) | MINT 갭 상위 5(문서 기준 후보, 구현 아님): ① 업스트림 사용자 위임(RFC 8693) ② 공급자 다회전(input_required) … | — |
| 2026-10-23 | [ACK RES-REGS — 2026-10-23 국내외 규제 갭 분석](2026-10-23-regulation-gap.md) | 분석 README에 국내외 요구·위협 74개를 조항/항목 → 코드 파일:행 → 충족/부분/미충족/미확인 → 개발 제안으로 연결했다. | DEV-66 |
| 2026-10-23 | [2026-10-23 레퍼런스 3종 조사 (Falcon Guardian · 젠아이랩스 · GensOps)](2026-10-23-references-3.md) | 추가 카드 3개: Falcon Guardian, 젠아이랩스 AI-native 개발, GensOps. | — |
| 2026-10-23 | [2026-10-23 실사용 시험 — 로컬 MCP 3종을 PJ1 실제 하네스로 끝까지](2026-10-23-real-usage-local-mcp.md) | 시나리오가 PJ1 관리형 계정의 실제 Claude Code에서 끝까지 통과했다(마지막 실행: 허용 3건·경보 5건·차단 0건, 저장 그래프를 다… | D-198 D-199 D-201 |
| 2026-10-23 | [서버 승인 직후 기존 MCP가 끊기는 결함 — 2026-10-23](2026-10-23-policy-refresh-gap.md) | full_stack_lab/gateway/app/endpoint_plane.py managed_policy(777행~)가 서버 경로·허용 목록·… | D-198 |
| 2026-10-23 | [ACK W14-LOCAL-RUNNER — 로컬 MCP 정상 기능 결함 보완](2026-10-23-local-runner-usability.md) | 사용자가 제공한 10-23 01:50 PJ1 Docker 29.8.1·공식 Docker MCP 이미지 실측 3건을 대상으로 수정했다. | DEV-73 D-192 D-200 |
| 2026-10-23 | [2026-10-23 공식 MCP 격리 실행 기본값 제안](2026-10-23-local-run-presets.md) | intake_proposal.LOCAL_RUN_PRESETS와 local_run_preset(row): 공식 저장소(modelcontextpro… | D-206 |
| 2026-10-23 | [2026-10-23 LiteLLM 승인·철회 동기화](2026-10-23-litellm-sync.md) | CHECKED: baseline e30be961a9a00d7982dd8565e4412c7289e85f4d; 실제 브랜치 10/23-litellm… | AIG-01 D-208 |
| 2026-10-23 | [ACK RES-GAP — 2026-10-23 발표용 경쟁·갭 매트릭스](2026-10-23-gap-matrix.md) | 발표용 매트릭스: 10행×9열(90칸)을 읽기 편하게 2개 표로 나눴다. | DEV-07 |
| 2026-10-23 | [2026-10-23 콘솔 영어 화면·언어 전환·글자 90%·화면 문구 정리](2026-10-23-console-i18n.md) | 문구(의미가 바뀌는 수정 없음, 대표 예): | D-211 |
| 2026-10-23 | [2026-10-23 콘솔 불필요 요소 정리](2026-10-23-console-declutter.md) | 요소 수는 렌더링한 화면의 DOM 기준(KPI 카드 / 탭 / 패널 / 차트 / 접힘 영역)이다. | D-136 |
| 2026-10-23 | [ACK W15-CONSENT-UX — 서버별 직원 이용 동의 (2026-10-23)](2026-10-23-consent-per-server.md) | 첫 P-CONSENT-001 차단에서 같은 서버의 승인·심사·직원 PAC 노출 범위에 속하는 동의 필요 도구를 현재 호출 데이터 등급으로 함께 … | D-201 |
| 2026-10-23 | [2026-10-23 클라우드 감사·AI 통제 벤치마크](2026-10-23-cloud-control-benchmark.md) | 벤치마크 README: 기능 16행 비교표, MINT 코드 근거, 차용 가능·부적합 표, 개발 제안 5개. | — |
| 2026-10-22 | [2026-10-22 콘솔 정상 기능 점검 (W7)](2026-10-22-w7-console-check.md) | acceptance.py에 4개를 마지막(audit-chain-intact 뒤)에 추가했다. | — |
| 2026-10-22 | [2026-10-22 정상 사용 불편 두 가지 수정 (PAC-01 사유, 활성화 직후 연결 지연)](2026-10-22-w10-ux.md) | 원인: full_stack_lab/opa/policy.rego:253이 승인된 PAC 실행 범위를 충족하지 못했습니다: <ID> 고정 문장만 만… | — |
| 2026-10-22 | [2026-10-22 위협 추적 변경 경계 독립 재대조](2026-10-22-threat-trace-delta-review.md) | 변경별 정본에 제품 경계와 한계를 기록했다. | — |
| 2026-10-22 | [2026-10-22 로컬 MCP(PC 격리 실행) 원클릭 — 구현·실측](2026-10-22-local-mcp-oneclick.md) | DEV-73 경로는 배포됐으나 로컬 신청·작업 0건. | DEV-73 D-192 |
| 2026-10-22 | [2026-10-22 LiteLLM 중앙 MCP에서 MINT 추가 역할 분석](2026-10-22-litellm-mint-opportunities.md) | 정본 분석에 읽기 범위·판본·기능 중복·세 후보·접점·한계·포기 조건을 기록했다. | DEV-47 DEV-43 DEV-38 |
| 2026-10-22 | [2026-10-22 macOS 직원 PC 키트](2026-10-22-kit-macos.md) | endpoint-agent/managed-macos.py, install-macos.sh를 추가했다. | D-68 D-196 |
| 2026-10-22 | [2026-10-22 엔드포인트 키트 정상 경로 실측](2026-10-22-kit-e2e.md) | 시각은 기기 시계(KST) 기준. | D-192 D-68 |
| 2026-10-22 | [2026-10-22 ID 추적 규칙·검사기·추적표](2026-10-22-id-trace.md) | 규칙 전문은 trace/README.md, 예약·폐기 번호는 trace/reserved.md다. | WIKI-02 WIKI-04 RES-01 DEV-73 D-190 D-174 D-160 |
| 2026-10-22 | [2026-10-22 전체 CI 후속 검증](2026-10-22-ci-completion.md) | 06a3142는 이용 관계 범위 시험의 두 집계 SQL에 LIMIT 1을 명시한다. | — |
| 2026-10-22 | [2026-10-22 AI 게이트웨이 애드온 (LiteLLM 중앙 MCP 연동)](2026-10-22-ai-gateway-addon.md) | 구현·단위 시험: 완료. | AIG-01 D-191 |
| 2026-10-21 | [위키 검사 실행 결과와 경고 분류 (10-21)](2026-10-21-wiki-check.md) | 기준: origin/main a52d661, 브랜치 10/21-wiki-check, 실행 2026-10-21 12:46 KST | D-157 |
| 2026-10-21 | [2026-10-21 직원별 MCP 서버 이용 중지·재개 (DEV-79, D-181)](2026-10-21-user-server-suspend.md) | 구현·로컬 대역 시험·로컬 일회성 PostgreSQL 확인까지 했다. | DEV-79 DEV-74 D-181 D-122 |
| 2026-10-21 | [2026-10-21 사용자별 로컬 실행 중지 경로 통합](2026-10-21-user-local-suspend.md) | user_suspend.suspend()가 사용자와 서버의 등록 여부를 확인한 뒤 로컬 서버이면 local_jobs.quiesce()로 (ser… | DEV-73 DEV-79 DEV-74 |
| 2026-10-21 | [DEV-75 미사용 도구 자동 비활성·재심사](2026-10-21-tool-sunset.md) | decisions 원장에서 서버·도구별 실제 실행 이력을 읽어 미사용 승인 도구를 기한에 따라 비활성화하도록 구현했다. | DEV-75 D-149 D-172 D-176 |
| 2026-10-21 | [2026-10-21 시험 상태 분류](2026-10-21-test-triage.md) | 추가 발견: field_account_git_test.py에는 if __name__ == "__main__": 블록이 없다. | DEV-80 DEV-79 DEV-74 D-182 D-176 D-181 |
| 2026-10-21 | [2026-10-21 직원 단위 MCP 전체 중지·재개 (D-181 편의 기능)](2026-10-21-suspend-all.md) | 한 직원의 운영 중 서버 전체를 한 번의 요청으로 중지·재개한다. | D-181 |
| 2026-10-21 | [2026-10-21 최신 통합 시트 기준 잔여 구현](2026-10-21-sheet-runtime-completion.md) | 시작 기준: main의 204579981ac02956a3ee40301f251ee99af9de6e | DEV-76 DEV-45 RM-03 DEV-73 |
| 2026-10-21 | [2026-10-21 SBOM 영향 조회·서버 대응](2026-10-21-sbom-impact.md) | 관리자 전용 POST /api/supply-chain/impact와 /impact/stop을 추가했다. | DEV-76 D-179 D-180 |
| 2026-10-21 | [2026-10-21 SBOM 일괄 중지 중복 처리 보강](2026-10-21-sbom-idempotency.md) | ops_response.suspend()가 이미 중지된 서버를 읽기 단계에서 거르고, 동시 중지 상황에서는 서버 행 잠금과 중지 행 삽입 결과를… | DEV-76 D-178 |
| 2026-10-21 | [2026-10-21 DEV-78 실행기 이전 승인 판본 되돌리기](2026-10-21-runtime-rollback.md) | 실행이 ACTIVE가 될 때 도구별 승인 설명·입력 스키마·출력 스키마 해시, 서버 판본, 합성 계약 SHA-256, 마지막 사람 승인자·시각을… | DEV-78 D-149 D-114 D-144 |
| 2026-10-21 | [2026-10-21 root 단독 운영 모드 재검토](2026-10-21-root-solo.md) | 원본 클론에서 10/20-root-solo를 가져온 뒤 main 추적 스냅샷에서 새 브랜치를 만들었다. | DEV-73 D-188 D-143 |
| 2026-10-21 | [2026-10-21 국외 처리 심사의 등록별 재사용](2026-10-21-residency-transfer-review.md) | core.review_server_residency가 기존 독립성 검사를 통과한 위치 심사에 현재 서버, 엔드포인트, 도입 신청, 정규화 위치,… | RM-03 DEV-69 D-173 |
| 2026-10-21 | [2026-10-21 DEV-77 출처 서명·빌드 증명 검증](2026-10-21-provenance-verify.md) | 기존 cryptography==50.0.1로 DSSE PAE의 Ed25519 서명을 검증하는 모듈을 추가했다. | DEV-77 DEV-73 D-114 D-179 D-137 |
| 2026-10-21 | [2026-10-21 DEV-77 OCI referrer 수집과 되돌림 증명 재검증](2026-10-21-provenance-referrer.md) | artifact_provenance.py에 표준 라이브러리 OCI Distribution referrer 조회와 sha256-<hex> tag … | DEV-77 D-179 |
| 2026-10-21 | [2026-10-21 로컬 회귀 입력과 플랫폼 조건 정정](2026-10-21-local-regression-fixtures.md) | intake_one_click_check.py의 공급자 파일 시험은 TemporaryDirectory 경로를 정규 경로로 바꾼다. | DEV-73 |
| 2026-10-21 | [DEV-81 로컬 수신 지점 인증 적대 검토 보고](2026-10-21-local-endpoints.md) | Linux Unix 소켓, Windows 이름 있는 파이프, 직원 PC 키트 헤더 명령은 같은 관리 UID/SID의 다른 프로세스를 프로세스 단… | DEV-81 DEV-73 DEV-80 D-119 D-124 D-170 |
| 2026-10-21 | [2026-10-21 도입 한 화면 승인 — main 기준 재배치 후보](2026-10-21-intake-one-click.md) | main에 있는 D-175 적대 검토와 메인 판단을 읽었다. | DEV-73 D-175 D-185 D-184 |
| 2026-10-21 | [2026-10-21 도입 위험 등급 승인 방식 적용 (D-189)](2026-10-21-intake-d189.md) | 구현·시험(로컬 정적·모의 DB)까지 했다. | DEV-71 D-189 D-143 D-188 |
| 2026-10-21 | [2026-10-21 기업 분석 CI의 현재 소스 참조 갱신](2026-10-21-enterprise-source-refresh.md) | Research workflow의 check_enterprise_analysis.py는 최신 작업 262f5eb와 시작 기준 2045799에서 … | — |
| 2026-10-21 | [2026-10-21 엔드포인트 오프라인 관측 버퍼](2026-10-21-endpoint-offline-buffer.md) | endpoint-agent/offline_buffer.py에 표준 라이브러리 기반 내구 JSONL 큐를 추가했다. | DEV-80 D-182 D-128 D-157 |
| 2026-10-21 | [2026-10-21 DEV-73 반려 판단 반영 재작업](2026-10-21-dev73-rework.md) | 코드 심볼·행·SHA-256·새 시험 지점은 원자 요구사항 정본, 근거·한계는 분석 문서에 있다. | DEV-73 D-189 D-188 D-175 |
| 2026-10-21 | [2026-10-21 DEV-45 실행 근거 결속](2026-10-21-dev45-evidence-gate.md) | rescore_1015.py는 명시된 증거 manifest 없이는 재산정하지 않는다. | DEV-45 DEV-46 |
| 2026-10-21 | [2026-10-21 DEV-03 위협표 현 판본 검토 갱신](2026-10-21-dev03-review-refresh.md) | 20개 파일·71개 낡은 참조를 기준 커밋 이후 diff 및 함수 AST/호출 경계와 대조했다. | DEV-03 DEV-81 |
| 2026-10-21 | [10-21 병합 기능의 완료 조건 대비 증거 감사](2026-10-21-criteria-audit.md) | 성격: 읽기 전용 감사. | DEV-80 DEV-77 DEV-78 DEV-79 D-176 D-177 D-189 |
| 2026-10-21 | [2026-10-21 GitHub CI 실패 진단과 수정](2026-10-21-ci-recovery.md) | 사용자의 실패 메일 제보 뒤 실제 Actions 기록을 확인했다. | — |
| 2026-10-21 | [DEV-81 F1 — 관리형 Linux 헤더 브로커의 AppArmor 프로세스 결속 (D-183)](2026-10-21-broker-process-binding.md) | 변경 파일은 endpoint-agent/managed-linux.py, endpoint-agent/enforce-linux.py, 새 endpo… | DEV-81 DEV-35 DEV-73 D-183 D-147 D-61 |
| 2026-10-21 | [2026-10-21 DEV-74 반복 위반 사용자 자동 일시 중지](2026-10-21-auto-suspend.md) | D-181 user_server_suspensions와 P-SUSPEND-001을 재사용했다. | DEV-74 D-181 D-176 D-172 |
| 2026-10-20 | [2026-10-20 Windows 관리 계정 환경의 설정 폴더 변수 검사](2026-10-20-windows-config-env.md) | Windows checks가 HKEY_USERS\<SID>\Environment에서 두 변수의 존재만 읽는다. | DEV-42 D-148 D-151 |
| 2026-10-20 | [2026-10-20 사용자 명령 헬퍼 준수 검사](2026-10-20-user-command-settings.md) | Linux 등록 계정의 pw_dir, Windows 등록 프로필에서 .claude/settings.json·settings.local.json,… | DEV-42 D-148 D-147 |
| 2026-10-20 | [2026-10-20 사용자 명령 헬퍼 검사 PJ1 실기기 시험 (D-148)](2026-10-20-user-command-settings-pj1.md) | 격리 중 헤더 헬퍼가 자격 없이 종료하면 Claude Code는 인증 없이 연결해 401을 받고 OAuth 서버로 판단해 캐시한다. | D-148 |
| 2026-10-20 | [2026-10-20 업스트림 세션 재사용 시험 원인 조사](2026-10-20-upstream-session-reuse-test.md) | 실패는 제품 결함이 아니라 DispatchTests AST 실행 픽스처가 registry.tool_hashes와 승인된 메타데이터를 제공하지 않… | DEV-29 D-115 D-79 |
| 2026-10-20 | [2026-10-20 token_revocation_pg_check 복구와 회전 기록 순서 (D-154)](2026-10-20-token-revocation-fixture.md) | 기준: main 751aee9, 브랜치 10/20-token-revocation-fixture(Claude, Codex 한도 중). | D-154 D-123 |
| 2026-10-20 | [2026-10-20 오래 실패한 시험 분류](2026-10-20-stale-tests.md) | 16개 중 환경 의존 13개, 기존 제품 계약 변경을 반영하지 못한 대역 3개, 확인된 제품 회귀 0개로 분류했다. | D-123 D-149 |
| 2026-10-20 | [2026-10-20 낡은 시험 대역 보정](2026-10-20-stale-test-fixtures.md) | oauth_rotation_check.py에 D-123 계열 조회 커서 대역과 기존 isolated_disposal() 도구를 연결했다. | DEV-44 D-123 D-149 D-116 |
| 2026-10-20 | [2026-10-20 SIEM·LiteLLM 실환경 연동 시험 (T1)](2026-10-20-siem-litellm-real.md) | 솔루션 기기 user@100.83.175.111(WSL2, 12코어, RAM 11.4GB 중 시작 시 가용 약 8.5GB, 디스크 908GB 여… | D-67 |
| 2026-10-20 | [2026-10-20 SIEM UID·실제 DB 큐 재시작 시험](2026-10-20-siem-dedup.md) | 판정 UID를 원장 행 ID·사슬 해시에 결속했다. | DEV-61 D-128 D-157 |
| 2026-10-20 | [2026-10-20 T5 선언 한계·섀도 MCP 통제 분석](2026-10-20-shadow-controls.md) | 분석 정본에 선언 계약의 한계, DEV-38·DEV-73·D-155·DLP/poisoning·출력 계약·변경 경보·SBOM의 잡는 것/못 잡는 … | DEV-73 DEV-38 DEV-76 D-155 D-170 |
| 2026-10-20 | [2026-10-20 활성 MCP 세션 종료와 재접근 차단 (G07.02)](2026-10-20-session-termination.md) | 초기화 응답의 Mcp-Session-Id 원문 대신 SHA-256과 검증된 주체·토큰 jti·장치·개별 서버 경로를 mcp_client_sess… | DEV-08 D-115 D-79 D-146 |
| 2026-10-20 | [2026-10-20 세션 종료 토큰 교체 회귀 수정](2026-10-20-session-termination-token-binding.md) | 세션의 활성 확인은 ID 해시·전송 토큰에서 검증된 주체·장치·서버 경로 및 미종료 상태로 한다. | DEV-08 D-146 D-115 D-79 |
| 2026-10-20 | [2026-10-20 서버 외부 통신 사건과 호출 상관](2026-10-20-server-egress.md) | 실행기가 엔진 소유 tinyproxy의 연결·필터 거부·접속 실패 로그에서 목적지와 관측 시각을 추출하고 기존 append-only 감사 사건에… | DEV-20 D-145 D-114 D-111 |
| 2026-10-20 | [2026-10-20 S9b·S10-B 요청자 재검증 적대 검토](2026-10-20-s9b-s10b.md) | S10-B의 3개 hunk는 모두 A(채택)다. | DEV-17 D-152 |
| 2026-10-20 | [2026-10-20 S7b 기존 시험 대역 보정 적대 검토](2026-10-20-s7b-fixtures-review.md) | S7b hunk 판정에 7개 hunk를 기록했다. | DEV-44 D-149 |
| 2026-10-20 | [2026-10-20 S7 출력 계약 적대 검증](2026-10-20-s7-output-contract-review.md) | 기존 시험 변경은 catalog_refresh_check.py A, contracts_check.py A, dispatch_recheck_che… | DEV-44 D-149 |
| 2026-10-20 | [2026-10-20 S6 사용자 명령 설정 적대 검증](2026-10-20-s6-user-command-settings-review.md) | 실제 임시 파일과 소스 경로로 하드 링크를 재현했다. | DEV-42 D-148 D-147 |
| 2026-10-20 | [2026-10-20 S5 전송 재확인 적대 검토](2026-10-20-s5-dispatch-recheck-review.md) | 네 가설에서 확실한 코드 결함은 확인되지 않았다. | DEV-43 D-140 |
| 2026-10-20 | [2026-10-20 결과 네 축 기록 (DEV-48 / D-136)](2026-10-20-result-outcomes.md) | 순수 함수가 한국어 네 축을 생성한다. | DEV-48 D-136 |
| 2026-10-20 | [2026-10-20 결과 경로 오탐 분류·BOM 처리 (D-161)](2026-10-20-result-fp.md) | 00db46e(D-125)가 classify.result_items에 JSON 파싱 실패 시 비어 있지 않은 줄 수를 항목으로 세는 fallba… | DEV-02 D-125 D-149 D-161 |
| 2026-10-20 | [2026-10-20 D-123 복원 후 잔존 확인](2026-10-20-restore-residual.md) | idp.revoke_principal_tokens()와 idp.revoke_device_tokens()가 활성 access token과 refr… | DEV-63 D-123 D-120 |
| 2026-10-20 | [2026-10-20 response cap 멱등성 시험 대역 보정](2026-10-20-response-cap-idempotency.md) | guard()가 core.py의 _validate_output과 실제 output_contract.py의 프로토콜·스키마 경계 함수/상수를 AS… | DEV-44 D-149 D-155 |
| 2026-10-20 | [2026-10-20 DEV-54 응답 상한 경계 보강](2026-10-20-response-cap-boundaries.md) | 영향 경로를 확인했다. | DEV-54 D-125 |
| 2026-10-20 | [2026-10-20 DEV-08 자원 서버 잔존 재접근](2026-10-20-resource-server-residual.md) | 1. | DEV-08 D-154 D-146 D-123 |
| 2026-10-20 | [2026-10-20 배포 직후 관리형 MCP 첫 호출 401](2026-10-20-post-deploy-401.md) | managed-linux.py는 토큰 발급 뒤 관측기 두 개(각 최대 40초)를 순차 실행하고 활성 상태에서 60초 쉰다. | DEV-42 D-148 D-146 |
| 2026-10-20 | [2026-10-20 정책 배포 후 경보 자체 시험 실험실](2026-10-20-policy-selftest-lab.md) | ops_response.self_test의 정책 정보 조회 예외도 실패 행으로 보존하고, 모든 자체 시험 실패에 synthetic=true인 p… | DEV-60 D-121 |
| 2026-10-20 | [2026-10-20 DEV-02 계약 오염 정규화 후보·보류 평가 규율](2026-10-20-poisoning-corpus.md) | 계약 검토에만 ROT13·역순·글자 띄우기·leetspeak를 해독해 기존 규칙으로 다시 읽는다. | DEV-02 DEV-61 D-158 D-100 |
| 2026-10-20 | [2026-10-20 PJ1 실제 공개 MCP 설치·도입 신청·비인가 실행 시험(T2)](2026-10-20-pj1-real-mcp.md) | 설치 전에 디스크를 확인했고, 단계마다 필요한 여유 용량을 검사했다. | DEV-73 DEV-30 |
| 2026-10-20 | [2026-10-20 도구 출력 계약](2026-10-20-output-contract.md) | output_schema_sha256 잠금 항목과 DB 출력 스키마/승인·관측 해시를 추가했다. | DEV-44 D-149 D-109 |
| 2026-10-20 | [2026-10-20 OAuth 음성 시험](2026-10-20-oauth-negative.md) | authenticated_user(..., require_mcp=True)에 mcp scope 검사(없으면 403)를 추가했다. | DEV-05 D-123 D-10 |
| 2026-10-20 | [2026-10-20 loopback owner replies 시험 원인 조사](2026-10-20-loopback-test.md) | 실패는 제품의 loopback 규칙 회귀가 아니라 D-119 시험이 이후 D-124의 설치 전송 검증 및 현재 설치 함수 호출 계약을 반영하지 … | DEV-35 D-119 D-124 |
| 2026-10-20 | [2026-10-20 LiteLLM 호환 (게이트웨이 신원·권한 경계 유지) — 미완료 (소유자 중단 지시로 저장)](2026-10-20-litellm-compat.md) | 브랜치 10/20-litellm-compat, 시작 origin/main e1839f8. | D-190 |
| 2026-10-20 | [2026-10-20 원장 보존 정책과 만료 구간 봉인](2026-10-20-ledger-retention.md) | 보존 기간 설정: GET/PUT /api/audit/retention(관리자 인증). | DEV-67 DEV-63 DEV-66 D-123 D-141 D-131 |
| 2026-10-20 | [2026-10-20 관리 하네스 런처 설정 경로 고정 (D-150)](2026-10-20-launcher-pin.md) | Linux C 래퍼는 Codex -c·--config(값 분리·=·짧은 옵션 묶음 포함)와 Claude --settings(분리·=)를 하네스 … | DEV-42 D-150 D-147 D-148 |
| 2026-10-20 | [2026-10-20 DEV-71 도입 신청의 위험 등급과 영향평가 입력 패키지](2026-10-20-intake-risk-tier.md) | 구현·로컬 정적 검사·일회성 컨테이너 단위 시험까지 했다. | DEV-71 DEV-68 D-143 D-137 |
| 2026-10-20 | [2026-10-20 도입 한 화면 승인](2026-10-20-intake-one-click.md) | 구현은 작업 트리에 남겼다. | DEV-68 D-184 D-185 |
| 2026-10-20 | [2026-10-20 사고 증빙 패키지와 관할별 보고 기한 타이머](2026-10-20-incident-pack.md) | incident_cases와 기존 추가 전용 approval_events를 사용해 관리자 인증 API에서 사고 생성·목록·상세 패키지·보고 완료… | DEV-66 D-144 |
| 2026-10-20 | [2026-10-20 사고 증빙 패키지 적대 검토 수정](2026-10-20-incident-pack-revision.md) | DECISIONS.md·main.py·v2_tables.sql의 충돌 텍스트를 양쪽 기능을 보존하여 합쳤다. | DEV-66 D-144 |
| 2026-10-20 | [2026-10-20 사고 증빙 패키지 오류 수정](2026-10-20-incident-pack-fix.md) | 평가 전 사고에서는 assessed_at이 NULL일 수 있으며, 과거 행/대역 데이터에서는 열 키가 없을 수도 있어 list_cases, de… | DEV-66 D-144 |
| 2026-10-20 | [2026-10-20 변경 요청 멱등 PostgreSQL 경합 시험](2026-10-20-idempotency-pg.md) | 새 dispatch_idempotency_pg_check.py는 기존 실험실의 격리 PostgreSQL과 합성 DB fixture를 사용한다. | DEV-55 D-126 |
| 2026-10-20 | [2026-10-20 중대 영향 호출과 인적 개입 증빙](2026-10-20-high-impact.md) | 1. | DEV-70 D-131 D-136 |
| 2026-10-20 | [2026-10-20 DEV-70 main 병합 충돌 해결](2026-10-20-high-impact-main-merge.md) | 자동 병합된 POLICY.md의 양쪽 기능 설명도 보존하고 주요 정책 표에 48·83의 위치 규칙을 추가해 2013의 중대 영향 규칙과 우선순위… | DEV-70 DEV-69 DEV-71 D-139 D-138 D-143 |
| 2026-10-20 | [2026-10-20 DEV-17 승인 실행 시 저장 요청자 토큰의 현재 유효성 재검증](2026-10-20-fresh-requester.md) | core._call_upstream의 도구 탐색·승인 유효성 확인 뒤에 13줄을 추가했다. | DEV-17 D-152 D-154 D-140 |
| 2026-10-20 | [2026-10-20 서버 간 전달 지문 대조 보강](2026-10-20-flow-hardening.md) | full_stack_lab/console.sh:61의 기존 ensure_env가 .env 생성·갱신 때 chmod 600을 실행함을 확인했다. | DEV-59 D-142 |
| 2026-10-20 | [2026-10-20 서버 간 중요정보 전달 경계의 내용 지문 대조](2026-10-20-flow-fingerprint.md) | 구현·시험 단계까지다. | DEV-59 D-142 D-133 |
| 2026-10-20 | [2026-10-20 이벤트 상관 조회 보강](2026-10-20-event-correlation.md) | event_correlation.py에 DB 의존성 없는 상관 투영 함수를 추가했다. | DEV-34 |
| 2026-10-20 | [2026-10-20 효과 평가 사례 확장](2026-10-20-eval-scenarios.md) | scenarios/controls-2026-10-20.json에 10건(공격 6, 정상 4)을 추가했다. | DEV-65 |
| 2026-10-20 | [2026-10-20 최종 전송 직전 재확인](2026-10-20-dispatch-recheck.md) | 최종 intent 트랜잭션이 주체 행과 현재 조건/등급을 덮는 동의 행을 공유 잠근다. | DEV-43 D-140 D-133 D-134 |
| 2026-10-20 | [2026-10-20 D-140 실제 PostgreSQL 경합 검사](2026-10-20-dispatch-recheck-pg.md) | 새 dispatch_recheck_pg_check.py는 제품 dispatch.record, consent.decide, core._record… | DEV-43 D-140 |
| 2026-10-20 | [2026-10-20 DEV-69 서버 처리·저장 위치와 국외 이전 규칙 팩](2026-10-20-dev69-data-residency.md) | 등록·원격 검토에 처리/저장 국가, 처리 주체, 위치/이전 근거를 더했다. | DEV-69 D-138 |
| 2026-10-20 | [2026-10-20 DEV-68 공급자 보증·등록부 내보내기·지원 종료 경보](2026-10-20-dev-68-supplier-assurance.md) | 승인 시 공급자 법인명, 공급자 연락처, 보안 연락처, 지원 종료일, 취약점 공개 정책 HTTPS URL을 필수 검사한다. | DEV-68 |
| 2026-10-20 | [2026-10-20 D-156 자원 잔존 적대 검토](2026-10-20-d156-resource-residual-review.md) | 지정한 네 항목에서 D-156이 만든 확실한 결함은 확인되지 않았다. | DEV-08 D-156 |
| 2026-10-20 | [2026-10-20 D-151 Windows 설정 환경 적대 검증](2026-10-20-d151-windows-config-env-review.md) | B: 수정 후 채택으로 판정했다. | DEV-42 D-151 D-148 |
| 2026-10-20 | [2026-10-20 D-150 관리 하네스 런처 고정 적대 검토](2026-10-20-d150-launcher-pin-review.md) | 검토 정본에 LP-01~07의 심각도·재현·수정안과 모든 요청 표면의 근거/추정/미실행을 분리했다. | DEV-42 D-150 D-147 D-148 |
| 2026-10-20 | [2026-10-20 D-150 정정 — Linux 옵션 파싱·Windows 런처 변경 철회](2026-10-20-d150-launcher-pin-correction.md) | Linux C 가드는 고정 Codex 0.160.0의 값 옵션 표로 argv를 순회한다. | DEV-42 D-150 |
| 2026-10-20 | [2026-10-20 D-149 전환 정정 적대 검증](2026-10-20-d149-transition.md) | refresh_catalog·registry sync·판본 이월·목록 SQL·같은 연결 재확인·최종 dispatch SQL을 대조했다. | DEV-44 D-149 |
| 2026-10-20 | [2026-10-20 하네스 명령 표면 잠금 (DEV-49·DEV-42, D-147)](2026-10-20-command-surfaces.md) | 목적: 하네스가 셸로 시작하는 명령 표면을 판본별로 정리하고, 공식 관리 키로 잠글 수 있는 것은 잠근다. | DEV-49 DEV-42 D-147 |
| 2026-10-20 | [2026-10-20 CI field TLS 및 위키 검사](2026-10-20-ci-field-tls.md) | verify.yml에서 field ca로 공개 루트와 지문을 가져와 키트 setup, Claude/Codex 환경, curl, Git HTTPS… | DEV-10 D-124 D-129 |
| 2026-10-20 | [2026-10-20 DEV-62 자동 중지 PostgreSQL 시험](2026-10-20-auto-suspend-pg.md) | 새 full_stack_lab/tests/auto_suspend_pg_check.py를 보강했다. | DEV-62 D-122 |
| 2026-10-18 | [2026-10-18 협업 콘솔 통합 시트 연동](2026-10-18-sheet-sync.md) | console.py의 /api/wbs가 저장소 스냅샷에 시트 값을 덮어쓰고 신규 ID·목표를 추가한다. | — |
| 2026-10-18 | [2026-10-18 남은 통제 구현 — 사용자 동의·전송 목적 결속·입력 항목/마스킹·서버 간 전달·효과 평가](2026-10-18-remaining-controls.md) | 도구 범위 심사(ToolReview)에 다섯 조건을 더하고 게이트웨이 호출 경로·OPA·콘솔에 연결했다. | DEV-51 DEV-59 DEV-35 D-135 D-131 D-134 |
| 2026-10-18 | [2026-10-18 field-tls-d124](2026-10-18-field-tls-d124.md) | 현장 Caddy를 사설 CA HTTPS로 바꾸고 IP 바인딩을 유지했다. | DEV-64 D-124 |
| 2026-10-18 | [2026-10-18 field-tls-d124 병합 후 보강](2026-10-18-field-tls-d124-merge.md) | 근거: D-118과 D-120~123을 보존하는 D-124 후속 리뷰. | DEV-62 D-124 D-120 D-118 |
| 2026-10-18 | [2026-10-18 통제 적용 전후 효과 비교 평가 도구](2026-10-18-eval-tool.md) | full_stack_lab/eval/before_after.py에 표준 라이브러리 기반 평가기, 기존 replay_cases.json의 base… | DEV-65 |
| 2026-10-17 | [2026-10-17 windows-kit-wizard-tray](2026-10-17-windows-kit-wizard-tray.md) | Windows ZIP 생성 경로는 full_stack_lab/gateway/app/agent_service.py의 기존 인증된 /api/pc-k… | DEV-25 DEV-26 D-118 D-68 |
| 2026-10-17 | [2026-10-17 upstream-session-reuse-stage2](2026-10-17-upstream-session-reuse-stage2.md) | 이 절은 아래 최초 구현 기록을 정정·대체한다. | DEV-29 D-115 D-110 D-79 |
| 2026-10-17 | [2026-10-17 작업 I — 선택적 제한·SIEM 전달](2026-10-17-selective-restriction-siem.md) | D-127: selective.py가 변경·소멸·위험 설명의 도구 범위를 계산하고 catalog_snapshots.restricted_tools… | DEV-52 DEV-61 D-122 D-69 D-127 |
| 2026-10-17 | [2026-10-17 작업 H — 응답 상한·변경 재전송 방지 (실제 작업 2026-10-18)](2026-10-17-response-cap-idempotency.md) | D-125: 기본 1000건·262144 UTF-8 JSON 바이트, 원문/마스킹 후 검사. | DEV-54 DEV-55 D-125 D-126 |
| 2026-10-17 | [2026-10-17 정책50 구현 공백 보강 레퍼런스](2026-10-17-policy50-gap-references.md) | 36건을 등록했다(LIB-K01~LIB-K36, 카탈로그 167 → 203건). | DEV-38 DEV-41 DEV-39 DEV-43 |
| 2026-10-17 | [2026-10-17 정책 번호 체계 대응 정본과 OPA 규칙 레이블 시험](2026-10-17-pol-pac-mapping-opa-labels.md) | POL 50개 모두에 독스용 PAC·원본 PAC24 대응(원본 시트 이름·본문 비교로 자동 도출)과, 기술통제 35개에는 런타임 PAC-01~1… | DEV-45 DEV-38 |
| 2026-10-17 | [2026-10-17 ops-response-d120-d123](2026-10-17-ops-response-d120-d123.md) | 구현과 로컬 단위 검증을 수행했다. | DEV-50 DEV-60 DEV-62 DEV-63 D-120 D-121 D-122 |
| 2026-10-17 | [2026-10-17 loopback-owner-replies-d119](2026-10-17-loopback-owner-replies-d119.md) | nft_rules(..., owner_uid=None)에 소유자 original/new 표식 설정과 관리 UID의 표식 있는 reply 허용 두… | DEV-35 D-113 D-119 |
| 2026-10-17 | [2026-10-17 기능명세서·개발 WBS와 리뷰 반영](2026-10-17-feature-spec-wbs.md) | 기능명세서·개발 WBS: 기능 64개(구현 완료(검수 전) 34·일부 구현 4·개발 예정 16·자동화 범위 제외 10), WBS 57개(현재 4… | DEV-50 DEV-41 DEV-42 DEV-53 D-69 |
| 2026-10-17 | [2026-10-17 dest-pin-credential-redaction](2026-10-17-dest-pin-credential-redaction.md) | destination.PinnedBackend가 새 TCP 연결 직전 DNS의 모든 주소를 검사하고 첫 검증 숫자 IP로만 접속한다. | DEV-41 DEV-64 D-116 |
| 2026-10-17 | [2026-10-17 AI 컴플라이언스 근거 문서 확보와 개발 착수 계획](2026-10-17-compliance-references.md) | ZIP 12건 중 3건은 이미 위키에 선별 수준으로 있었다(K36 개인정보 보호법, I16 AI 기본법, K34 ISO/IEC 42001). | DEV-66 RES-01 |
| 2026-10-15 | [2026-10-15 Drive 문서 통합과 개발 위키 보강](2026-10-15-wiki-consolidation.md) | 1. | DEV-41 DEV-38 DEV-44 DEV-45 |
| 2026-10-15 | [2026-10-15 목표 기능 WBS 구현·통합·저지연화](2026-10-15-wbs-implementation.md) | Codex 10-13~14 작업, 10-14 레퍼런스 보강, 팀원 디자인 브랜치 feat/web-ui, 서브에이전트 A·B·C·D를 통합 브랜치… | DEV-35 DEV-02 DEV-37 DEV-29 D-105 D-72 D-106 |
| 2026-10-15 | [2026-10-15 업스트림 MCP 세션 재사용 설계 비교](2026-10-15-upstream-session-reuse-design.md) | 선택지 4개를 비교했다. | DEV-29 D-79 |
| 2026-10-15 | [2026-10-15 호출 예약 원자성·전송 의도·종료 (작업 C)](2026-10-15-termination-dispatch.md) | C1–C4/T1–T3 기록: 격리 랩 케이스(경로·호출자·제공자 보유 자격 2건)는 모든 대상 T1, 케이스 T1, 차단 후 실행 0·미확인 0… | DEV-04 DEV-21 DEV-29 DEV-08 D-96 D-99 D-78 |
| 2026-10-15 | [2026-10-15 OSS 심층 코드 분석·서브세션 통합·경계 보강](2026-10-15-oss-deep-analysis.md) | Codex 작업 확인. | DEV-29 DEV-38 DEV-35 DEV-41 D-107 D-110 D-111 |
| 2026-10-15 | [2026-10-15 OSS 조사 종류·깊이·요약 감사와 보완 계획](2026-10-15-oss-analysis-audit.md) | 감사 및 6단계 보완 계획과 관측 정본을 추가했다. | DEV-47 DEV-38 DEV-29 |
| 2026-10-15 | [2026-10-15 도입 출처·최소권한·승인자 독립성·위임 미지원 (작업 B)](2026-10-15-intake-identity.md) | 구현·설정·활성화·배포를 구분한다. | DEV-04 DEV-17 DEV-05 D-79 D-90 |
| 2026-10-15 | [2026-10-15 검사 규칙 코퍼스 측정·한국어 개인정보·협업 콘솔 실행 기록 (작업 D)](2026-10-15-inspection-corpus.md) | tests/inspection_corpus_eval.py가 고정 커밋·SHA-256을 확인한 공개 파일 189개(43 MiB, 저장소에 넣지 않… | DEV-09 DEV-02 D-100 D-103 |
| 2026-10-15 | [2026-10-15 엔드포인트 증거·완전성·망 품질 (작업 A)](2026-10-15-endpoint-evidence.md) | 구현 위치와 계약만 적는다. | DEV-18 DEV-22 DEV-30 D-85 D-89 |
| 2026-10-15 | [2026-10-15 Team AGI 드라이브 산출물 선별](2026-10-15-drive-deliverables.md) | 정책 폴더의 새 MCP_보안정책50.xlsm을 원본 바이트로 보존하고 본 시트의 POL-01~50 내용을 탐색용 Markdown으로 추출했다. | — |
| 2026-10-15 | [2026-10-15 DEV-38 승인 소스 MCP 실행기](2026-10-15-dev38-runtime.md) | 구성(D-114). | DEV-38 DEV-39 DEV-48 DEV-41 D-114 |
| 2026-10-15 | [2026-10-15 관리 계정 루프백 차단과 하네스 로컬 통신 (DEV-35)](2026-10-15-dev35-loopback.md) | 근거 페이지에 표·원본·해시를 모았다. | DEV-35 DEV-30 D-119 D-79 |
| 2026-10-15 | [2026-10-15 클린 기기 E2E · MINT 화면 · 원칙 중심 README](2026-10-15-clean-e2e.md) | 콘솔 글자를 전부 125%로 키웠다(CSS 변수·직접 지정 크기·차트 글자). | DEV-29 DEV-39 DEV-40 DEV-38 D-107 D-108 D-109 |
| 2026-10-14 | [2026-10-14 위험매핑 기반 3단계 시험과 수정](2026-10-14-risk-scenarios.md) | 정적검토 → DB 보존 동적시험 → 전용 DB 초기화 후 선별시험을 수행했다. | DEV-23 |
| 2026-10-14 | [2026-10-14 레퍼런스 보강과 정리](2026-10-14-reference-fill.md) | 139건(LIB-A01~LIB-J15, 결번 LIB-D15). | DEV-02 DEV-05 |
| 2026-10-14 | [2026-10-14 PJ1 9개 도구 자연어 하네스 시험 — 무효 처리](2026-10-14-pj1-nine-tools.md) | 정정 (2026-10-14 오후, 사용자 지적). | DEV-29 DEV-28 |
| 2026-10-14 | [2026-10-14 PJ1 Ghidra·GhidraMCP 설치와 로그 전달 확인](2026-10-14-pj1-ghidra-logs.md) | PJ1에서 Ghidra12.1.4·GhidraMCP2.0.0·Temurin21.0.12.1+1·private Python3.12 venv를 구성… | DEV-32 DEV-33 D-79 |
| 2026-10-14 | [로컬 도구·MCP 설치, 위험매핑과 엔드포인트 개선](2026-10-14-local-mcp-endpoint.md) | 설치·분류 정본에 Ghidra·Git·SQLite·Blender·Playwright를 묶었다. | DEV-03 |
| 2026-10-14 | [2026-10-14 엔드포인트 로그 경로 수정·PJ1 Linux 검증](2026-10-14-endpoint-telemetry-fix.md) | 서버 /api/endpoint/observation-status는 장치 key·inventory 권한을 요구한다. | DEV-18 DEV-33 DEV-29 DEV-30 D-82 |
| 2026-10-14 | [엔드포인트 로그 전달 진단·목표 기능 WBS — 2026-10-14](2026-10-14-endpoint-log-wbs.md) | 목표 10개를 40개 원자 작업으로 나눴다. | DEV-18 DEV-34 D-79 |
| 2026-10-14 | [2026-10-14 비인가 로컬 MCP의 PJ1 자연어 시험 (E13 변형)](2026-10-14-e13-local-mcp-natural-language.md) | 수신 서버 요청 0건: Git 수신 서버 로그는 세 관리 시험 창 모두 0줄. | DEV-28 DEV-30 DEV-31 DEV-32 |
| 2026-10-13 | [2026-10-13 개발 연구 위키 구축](2026-10-13-wiki-bootstrap.md) | 자료 원본의 SHA-256과 복사본을 대조하고 전체 추출 MD의 UTF-8, 출처·판본·로컬 링크·원본 존재를 검사했습니다. | — |
| 2026-10-13 | [2026-10-13 결과 반환 경계 독립 검토](2026-10-13-result-boundary-review.md) | 확인 범위: core.py의 dispatch·결과 검사·예외·감사 연결, privacy.py의 마스킹과 타입 유지, mcp_facade.py의 … | — |
| 2026-10-13 | [팀 개발 브랜치·MCP 후보·검증 및 실패 시 수정 계획](2026-10-13-mcp-validation-plan.md) | 이전 계획 기록입니다. | — |
| 2026-10-13 | [기업 연동 자료와 preflight 독립 검토 — 2026-10-13](2026-10-13-interop-review.md) | 2026-10-13 공식 GitHub API에서 실제 Compose tag v1.102.1의 commit을 d09bbae1c6df463e4255… | — |
| 2026-10-13 | [현재 기능, 목표 기능과 보강 설계 — 2026-10-13](2026-10-13-feature-design.md) | 개발 목표 10개를 기존 코드와 8개 솔루션 조사에 대조했습니다. | — |
| 2026-10-13 | [기업 품질 기준·연동 분석과 구현 결과](2026-10-13-enterprise-results.md) | 작업 브랜치 10/13-enterprise-interoperability, 기준 커밋 ab6936c64f3578de8360b840f1928681… | — |
| 2026-10-13 | [실제 Claude Sonnet 5.5 독립 검토](2026-10-13-enterprise-claude-review.md) | 모델 응답 claude-sonnet-5-5 확인, effort xhigh 요청. | — |
| 2026-10-13 | [코드 분석·보강 구현·실기기 검증 결과 — 2026-10-13](2026-10-13-development-results.md) | 연구 위키는 Markdown 정본으로 유지하고, 웹을 실제 Codex × Claude 개발 협업 콘솔로 변경했습니다. | — |
| 2026-10-13 | [2026-10-13 개발 목표와 검토 기준](2026-10-13-development-goals.md) | 사용자 요청과 기존 설계에서 목표를 도출했습니다. | — |
| 2026-10-13 | [Claude 독립 코드 검토 원문 — 2026-10-13](2026-10-13-claude-code-review.md) | WSL Claude CLI 실제 세션의 공개 최종 응답입니다. | — |
