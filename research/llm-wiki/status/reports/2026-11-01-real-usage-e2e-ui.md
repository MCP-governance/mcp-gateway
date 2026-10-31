# 2026-10-31~11-01 실사용 시험(정식 도입·비인가 설치)과 UI 개편

- 브랜치 `10/31-overhaul`(PR #71, 미병합), 기준 `423c0eff` → `6b1f402d`. :8000 스택·pj3 키트 반영.
- 시험자: Codex gpt-6.1-terra(정식 도입 경로), Claude Sonnet(비인가 Ghidra MCP·화면), 메인이 pj3 Codex gpt-6-luna·Claude haiku로 실제 호출.
- 시험 자료(저장소 밖): `tmp/e2e-1031/`(지시서, 각 보고서 `a-terra/report.md`·`b-sonnet/report.md`, 레퍼런스 `refs/references.md`, 원장 대조 `round2/`).

## 시나리오와 결과
| 단계 | 결과 |
| --- | --- |
| 직원 `mint request`로 Hugging Face 원격 MCP 도입 요청 | 콘솔 「엔드포인트 요청」 표시 |
| root 신청서 작성·승인·등록 | 처음엔 신청자가 root로 기록돼 승인 불가(버그 1) → 수정 후 직원 명의 신청·승인·등록 |
| 직원 Ghidra MCP 비인가 추가(Codex·Claude, 우회 4종) | 두 하네스 모두 로드·호출 차단, 1분 내 미등록 MCP 경보. requirements.toml 직접 수정(로컬 관리자)은 쓰기 성공 → 게이트웨이가 해시 불일치로 격리 |
| 승인 서버 호출(haiku·luna, 데모 프로젝트 `demo-ml-audit`) | 동의 전 P-CONSENT-001 차단, 직원 동의(시험 대행) 후 실행. 판정 원장 18건 중 17건이 엔드포인트 기록과 1:1(1건은 Codex 하네스 실패 호출이라 훅 미발생) |
| 엣지 | 경로 조작 `../` → HF EINVAL, SQL 주입 문자열 → 저장소 없음, 이모지·장문 검색 실행, 큰 응답 37 KB(도구가 74/100으로 절단), 0.9초 연속 호출 제한 없음 |

## 고친 결함
1. 엔드포인트 요청으로 쓴 신청서가 관리자 명의 → 직원 명의·요청 닫기(`endpoint_request_id`). 원격 주소는 원격 MCP로 미리 채움.
2. 격리 PC의 하네스 안내가 「활성화 대기」 → 격리·재활성화 안내.
3. 엔드포인트 격리에 경보 없음 → `endpoint-quarantined` 경보.
4. Codex 훅이 서버 id의 `-`를 `_`로 보고 → 「로컬」 오분류·미등록 경보 → 등록 id 정규화(`tests/endpoint_tool_path_check.py`).
5. PC에 미등록 MCP가 있으면 호출마다 경보(2분 18건) → 사람·정책별 하루 1건.
6. 차단된 호출이 직원 화면·CLI에 「완료」 → 판정 원장과 맞춰 차단·경보·완료·실패, 서버 표시 이름.
7. 호출 상세가 새로고침에 사라짐 → `d=` 주소, `/api/activity?decision_id`.
8. 동의 대기가 직원 PC에 안 보임 → 로컬 화면 배너·`mint servers`(동의는 콘솔에서만, D-301 이유).
9. 커넥터 탭 배지 0 vs 본문 16 → 전체 수.

## 소유자 지시 반영
- D-306: `ROOT_SOLO_APPROVAL=1`에서 root는 강제 집행(본인 신청·높음 2인 조건), 원장 `forced`, 등록 단계는 모드 켜짐+승인자 전원 root일 때만 면제. 현장 기본 관리자 admin1~3(운영 `mint.sh`는 기본 비밀번호면 중지).
- UI 개편 근거: 웹 디자인 16·UX 16 레퍼런스(Carbon, Cloudscape, Polaris, Primer, Atlassian, Fluent 2, M3, Ant, GOV.UK, Cloudflare, Tailscale, Linear, Grafana, Datadog, Okta, KRDS / NN/g 10편, Baymard, Laws of UX, WCAG 2.2, Cloudscape 상태, SOC 경보 피로, 승인 워크플로). 적용: 호출 목록 한 줄 결과 칩, 행 동작 메뉴, 상태·빈 상태·배너, 로컬 화면 콘솔 디자인·자동 새로고침.

## 남은 것·한계
- 시험자 B가 남긴 pj3 Codex 설정의 Ghidra 항목(의도적 유지) → 그 직원의 호출은 계속 MCP-SHADOW-002 경보(하루 1건).
- 수정 전 쌓인 Codex 엔드포인트 기록 2건은 「로컬」로 남음. Codex 훅은 실패한 호출을 보고하지 않음(게이트웨이 원장에는 있음).
- 동의는 시험 대행(winvm 세션을 서버에서 발급)으로 처리 — 실제 운영은 직원 콘솔 로그인.
- 직원 Claude `-p`는 관리형 권한 규칙만 적용돼 Write가 거부됨(대화형은 확인창). 속도 제한 임계값·동시 경합은 미검증.
- 로컬 Windows에서 실패하는 기존 시험 6건(TLS·cp949·grp·libcrypto, local_job_control은 이전부터 실패)은 CI에서 확인 필요.
