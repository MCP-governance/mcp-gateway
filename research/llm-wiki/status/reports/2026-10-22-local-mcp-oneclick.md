# 2026-10-22 로컬 MCP(PC 격리 실행) 원클릭 — 구현·실측

- 작업자: Claude(Opus, 리더 직접) · 기준 `db8cb13` → main `f591d1c`·`bf6cea1`·`38ee658`·`85ead96` · 결정 D-192
- 시작 근거: 소유자 10-22 "엔드포인트 키트랑 local mcp 동작 안 하는 건 중대사항", 시험용 신청·승인 직접 허용(끝나면 철회)

## 문제(기기 실측)
DEV-73 경로는 배포됐으나 로컬 신청·작업 0건. 손 서명·환경변수 수기·PC별 엔진 판본 강제·이미지 사전 반입·콘솔 화면 부재. 저장소형 stdio 서버는 기기 레시피(MarkItDown) 없으면 실행 불가. 기기에는 개인 키 없는 공개 키만 남아 있었다.

## 실측 중 찾아 고친 결함
| 순서 | 증상 | 원인 | 수정 |
| --- | --- | --- | --- |
| 1 | 승인 미리보기 NotStarted(0.1초) | 로컬 작업 허가가 신청 APPROVED 요구 — 원클릭은 승인 전에 관찰 | 관찰(observed=false) 단계만 HOLD·VALIDATED 허용 |
| 2 | 미리보기 RuntimeError(3초), PC 작업 오류 ValueError | docker 29.8.1의 runc가 `/proc/<pid>/fd` 바인드 원천을 EINVAL로 거부 → 컨테이너 시작 실패, 측정 판본 미보존으로 KeyError | docker는 경로 바인드 + 생성 직전 inode 재확인, 측정값 보존 |
| 3 | 재설치 후 관찰 작업이 죽은 장치로 가서 만료 | 재설치 때 이전 장치가 active로 남음(유령), 관찰 PC 영구 결속 | 등록 시 같은 소유자·PC·계정의 이전 장치 폐기, 묶인 장치가 쓸 수 없을 때만 현재 장치로 재결속(F8 결정 유지) |

## 실측 결과 (솔루션 기기 + PJ1, 공식 `mcp/filesystem@sha256:35fcf021…`)
- 관리자 API: 이미지 이름 → digest 고정, 승인 미리보기에서 PJ1(`managed-db36d264`) 관찰 8.5초·도구 11개·차단 사유 0·위험 중간, `read_file`·`list_directory`만 1일 승인 → `READY`.
- PJ1 관리 계정 Claude(sonnet): `claude mcp list`에 연결됨. 동의 전 원장 891·892 `Block P-CONSENT-001` → 직원 동의 → 893·894 `Allow P-AUTHZ-ALLOW-001`, 응답 「로컬 MCP 시험 문서 2026-10-22」(PC 폴더의 파일 내용과 일치). PC 작업 tools/call 2건 done.
- 정리: 서버 철회 `DISABLED`·로컬 승인 회수, PJ1 시험 폴더·임시 파일 삭제. 이전 장치 `managed-5f5407be` 폐기.

## 남은 공백
- 승인 화면 격리 구성이 「확인 안 됨」으로 표시(기기 `LOCAL_ENGINE_SETTINGS` 미설정) — PC가 측정한 엔진·매핑을 표시하도록 후속.
- 마운트 대상이 관리 계정 홈 절대 경로라 실행 인자가 계정 이름에 묶임 — 고정 컨테이너 경로로 후속.
- docker 경로 바인드는 생성~시작 사이 폴더 교체 경쟁이 남음(D-192 한계). Windows·macOS 로컬 실행은 범위 밖. Codex 하네스는 PJ1 Codex 로그인 폐기로 미실행.

## 후속 (10-22, 브랜치 `10/22-local-mcp-followup`)
- 승인 화면 「격리 구성」: 기기 `LOCAL_ENGINE_SETTINGS` 대신 관찰 PC 실행기가 보고한 최신 측정값(엔진·판본·사용자 매핑·범위)으로 표시. 측정이 없을 때만 「확인 안 됨」. 실행기가 `engine`도 함께 보고한다.
- 마운트 대상: 관리 계정 홈 절대경로 → 컨테이너 안 `/workspace/<상대경로>`(podman idmap `--mount`·docker `-v` 둘 다). 실행 인자는 `/workspace/mcp-docs`처럼 PC 계정과 무관. 콘솔 PC 격리 실행 입력(라벨·예시)도 이 경로 기준.
- PJ1 실측(docker 29.8.1, 호스트 매핑): 공식 `mcp/filesystem@sha256:35fcf021…`, 인자 `/workspace/mcp-docs`, 마운트 `/home/managed-pj1/mcp-docs → /workspace/mcp-docs`(ro), 도구 11개, `list_directory`·`read_file` 응답이 PC 폴더 내용과 일치. 시험 폴더·임시 파일 삭제.
- 시험: `dev73_rework_check`·`dev73_integration_check`·`dev73_review2_check`·`local_run_manifest_check` 통과(Linux에서 건너뛰던 항목 포함), pyflakes·`node --check`·`open_endpoints.py` 통과. 기대값 변경 이유는 DECISIONS D-192 후속 항목.
- 남은 것: 기기 배포 후 승인 화면에서 격리 구성 표시 확인(리더). podman PC 실측 없음(단위 시험만).
