# 2026-11-01 Ghidra MCP 정식 도입(pj1 Linux·pj3 Windows)

- 기준: main `7f3ccb5a` → 브랜치 `11/01-local-mcp-windows-profile` (PR #75)
- 요청: 「pj1·pj3에 Ghidra와 Ghidra MCP 다시 세팅」 → 「정식 도입까지」

## 한 일

1. 두 PC에 Ghidra 12.2(공식 SHA-256 대조), JDK 25(Ghidra 12.2 최소 요구), pyghidra-mcp 0.2.7을 설치했다. OS 공통 경로 `/opt/ghidra`(Windows는 `C:\opt\ghidra`)에 설치본·JDK 링크·samples·projects를 두었다.
2. 사용자 설정에 직접 넣은 ghidra(비인가)는 Codex `disabled: requirements`, Claude Code 관리형 독점으로 막혔고, `mint servers`와 콘솔 「발견 항목」에 미등록 MCP로 표시됐다.
3. 정식 도입 흐름:
   - pj1 직원이 `mint request`로 요청했다.
   - root가 저장소형 신청서를 작성했다(clearbluejar/pyghidra-mcp `42d8f805`).
   - 공급망 검증 결과는 보류였다. SBOM 1,197개, Critical 15건.
   - 위험 수용(30일)을 기록했다. 설치 집합의 Critical은 chromadb CVE-2026-45829·45833뿐이고, 둘 다 HTTP 서버 경로다. pyghidra-mcp는 `PersistentClient`(내장 모드)만 쓴다.
   - 엔드포인트 실행 설정은 프로세스 실행, 인자 `--project-path /opt/ghidra/projects /opt/ghidra/samples`, env `GHIDRA_INSTALL_DIR`·`JAVA_HOME_OVERRIDE`로 넣었다.
   - 승인 미리보기는 pj1 실행기에서 도구를 관찰했다.
   - 최소 권한으로 승인했다. 읽기 12개와 `import_binary`(쓰기)를 허용하고, rename·set·save·delete 7개는 제외했다.
   - 직원 동의(시험 대행)를 받았다.
4. 직접 넣었던 사용자 설정 항목은 지웠다. 관리 구간 표식은 보존했다.

## 고친 결함 (D-331~336)

| 결정 | 증상 | 수정 |
| --- | --- | --- |
| D-331 | Windows 실행기가 USERPROFILE·APPDATA·TEMP를 주지 않아 Ghidra가 기동 단계에서 종료 | 직원 토큰 `CreateEnvironmentBlock`에서 위치 변수만 전달 |
| D-332 | Windows 관리형 정책이 로컬 서버를 모두 뺌. 사전 준비가 소스 실행 서버에도 이미지 준비를 불러 실패. 마운트 없는 서버도 폴더를 만들려다 Windows에서 실패 | 컨테이너형만 제외. 사전 준비가 잠금 wheel 설치. 마운트 없으면 폴더 생략 |
| D-333 | 한 호출 상한 20초(DB 제약 포함)로는 JVM 서버가 기동만 하고 끝남 | 60초. `local_jobs.run_seconds` 제약 이전 |
| D-334 | 64자 폴더 이름으로 wheel 경로가 263자가 되어 Windows에서 재검증·실행 실패. `-I -S`로 `.pth`(pywin32)가 빠짐. 재시작 직후 파이프 이름 충돌로 토큰 파이프가 죽음 | 16자 이름. `site.addsitedir`. 파이프 생성 재시도 |
| D-335 | Windows가 호출마다 파일 8천여 개의 ACL·해시를 재검증해 55초 소요 | 검증한 폴더의 지문을 실행기가 기억 |
| D-336 | Python 3.13이 docstring 들여쓰기를 지워, 3.12에서 승인한 도구 5개가 Windows에서 계약 불일치로 거부되고 원장엔 「종료 코드 1」만 남음 | 승인 설명의 cleandoc 해시를 함께 대조. 거부는 `contract`로 기록 |

## 검증

- 로컬 시험:
  - `endpoint_stdio_check` 17개, `kit_install_upfront_check` 33개, `command_surfaces_check` 5개 통과.
  - `dev73_rework_check`, `local_runner_usability_check`, `dev73_integration_check`, `endpoint_source_api_check`, `nested_tx_refactor_check` 통과.
  - `tests-windows/test_endpoint_stdio.py` 9개 통과.
- 기기: 시험 스택(:8000)을 브랜치 `11cc5a6f`로 올렸다. DB 제약이 `run_seconds <= 60`으로 바뀐 것을 확인했다.
- pj1(Codex, Linux): 자연어 요청에서 `list_project_binaries` 1회, `decompile_function` 3회가 실행됐다(원장 #262~263 외, 21:31~21:32). `entry` 요약을 받았다.
- pj3(Codex, Windows 대화형 세션): 원장 #286·#287이 실행됐다. `keycheck`의 `main` 요약을 받았다.
- 증거: `tmp/e2e-1101/ghidra-1101/`(콘솔 캡처, 신청 기록 `intake_log.json`, Codex 로그).

## 남은 것

- pj1이 22:00 무렵부터 Tailscale 오프라인이다. D-336 실행기가 pj1에는 반영되지 않았다(pj1은 3.12라 영향 없음).
- 호출마다 프로세스를 새로 띄우므로 Ghidra는 매 호출 10~15초가 걸린다. 새로 가져온 바이너리의 백그라운드 분석·색인은 호출 사이에 이어지지 않는다. 세션 유지형 로컬 실행은 범위 밖이다.
- 호출 기록에서 로컬 실행 실패가 「원격 서버 통신 실패」로 표시된다. 로컬 경로 문구는 따로 다듬어야 한다.
