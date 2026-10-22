# ACK W14-LOCAL-RUNNER — 로컬 MCP 정상 기능 결함 보완

- 작업자: Codex, Agent Hub `auto-82393ac179687673c558`.
- CHECKED: 기준·작업 종료 HEAD `0f57d0c9c0994faf849544616c6e66939b113fd8`, 브랜치 `10/23-output-fp`, 작업 제한 `3600초`.
- CHECKED: 제공 inbox `8265`(이전 출력 오탐 배정), `8279`(실행기 재시작), `8280`(이전 출력 오탐 후속), `8292`(이번 로컬 실행기 배정), 관측 마지막 사건 `8294`. inbox는 근거로만 사용했고 이번 사용자 지시를 작업 권한으로 삼았다.
- CHECKED: 시작 시 W13의 `privacy.py`·`secret_scan.py`·POLICY·출력 오탐 시험/분석/보고서 및 공용 DECISIONS·현황·백로그·매핑/스냅샷 변경이 있었다. 출력 오탐 구현은 건드리지 않았다. 공용 문서는 기존 내용을 보존해 이번 절을 추가했고 파생 매핑·스냅샷은 현재 트리에서 재생성했다. W5 macOS의 미해결 상태는 관찰했으나 macOS 구현 편집·담당 충돌은 발견하지 않았다. 구현 소유권 충돌 없음.
- CHECKED: 최신 관련 커밋 `46d9a68`(D-192 이미지 수신·엔진 측정), `2de9176`(Docker 경로 마운트), `94a58a4`(측정값·고정 컨테이너 경로)을 현재 코드와 대조했다. 쓰기 직전 HEAD를 재확인했고 변동 없음.
- 원격 기본 HEAD 재조회 `git ls-remote --symref origin HEAD`는 GitHub 연결 실패. 새 브랜치·커밋·push 없음. 현재 브랜치 계속 사용은 이번 사용자 지시다.
- 제공 쿼터 관측: Codex 82%(당시 값), 알려진 리셋 `2026-10-23 07:08:54 KST` (`1792706934`). 현재 잔량은 재조회하지 않았다. Claude 잔량/리셋의 신뢰 가능한 최신 값은 미확인이다.

## 결과

사용자가 제공한 10-23 01:50 PJ1 Docker 29.8.1·공식 Docker MCP 이미지 실측 3건을 대상으로 수정했다.
이번 세션에서 원장·이미지 digest·실제 파일 모드를 직접 확인하지 않았으며 기기·PJ1 접속은 하지 않았다.

1. **이미지 준비 중 수령 만료**: 기존 `/control` 조회가 승인·정책·철회·장치·현재 임대를 확인한 뒤
   실행 전 5초 수령 임대를 갱신한다. 승인 관찰 초기화는 준비 최대 180초와 원래 실행 제한을 구분한다.
   일반 호출·상태 점검은 원래 전체 기한을 유지한다. pull 중 제어 실패·철회·기한 초과가 나면 수신 프로세스를
   종료·회수하며 컨테이너를 시작하지 않는다. 허용 저장소·digest 고정·서명 검증은 유지한다.
2. **종료 사유 전달**: 표준 오류 전용 읽기 스레드와 4096바이트 순환 버퍼를 추가했다.
   마지막 5줄·300자만 보내며 긴 행/불완전 행 생략, 알려진 비밀·자격 문맥 마스킹, 게이트웨이 기존 출력 오염·Secret 검사 후
   한국어 사유·종료 코드를 담는다. 전체 진단은 500자다. 검사된 진단을 결과 오류와 append-only 사건에 같은 값으로
   저장·해시하고 해당 사건이 있는 오류만 게이트웨이 공개 진단으로 전달한다. 기존 콘솔 오류 표시는 `textContent`다.
   원시 SDK/기존 장치 예외의 일반 오류 경계는 유지한다.
3. **root 전용 이미지 처리**: 실행 권한 거부를 감지해 「이미지 실행 파일의 권한 때문에 관리 계정으로 실행할 수 없습니다」로
   전달한다. Docker host/remap·Podman auto 모두 관리 UID를 유지하며 root 재시도는 없다.
   `--rm` 자동 삭제로 종료 상태가 사라지지 않도록 실제 생성에서는 이를 빼고 상태 조회 뒤 명시적으로 회수한다.
   정지 확인은 여전히 엔진의 컨테이너 부재 확인이 필요하다. Docker 사용자 재매핑과 rootless Podman 설치 선택지·
   운영 변경 영향·현재 지원 한계를 문서에 남겼다. 권한 거부만으로 root 전용 파일 모드라고 단정하지 않는다.

`local_jobs.run_seconds` 열을 멱등 추가하며 기존 행 기본값은 20초다. 시작 시 원래 실행 제한으로 deadline·lease를
줄여 2.5초 요청을 20초로 늘리지 않는다. 게이트웨이/콘솔 서비스 스키마 적용과 설치된 실행기 갱신을 함께 반영해야 한다.
종료 판정 C1~C4/T1~T3, 토큰 전달 금지, 장치 신원, 계약 승인, 원장의 append-only 규칙은 변경하지 않았다.

산출물:

- 실행기: `endpoint-agent/local-runner.py`.
- 게이트웨이: `full_stack_lab/gateway/app/{local_jobs.py,local_run_tables.sql,main.py,core.py}`.
- 새 시험: [local_runner_usability_check.py](../../../../full_stack_lab/tests/local_runner_usability_check.py).
- 설치·설계·화면/데이터 계약: [endpoint-agent/README.md](../../../../endpoint-agent/README.md),
  [D-199](../../../../docs/ai/DECISIONS.md), [DATA_MODEL](../../../../docs/ai/DATA_MODEL.md),
  [CONSOLE_UI](../../../../docs/ai/CONSOLE_UI.md).
- 분석 정본: [원자 요구사항·공식 자료·OSS/스킬 탐색·한계](../../analysis/local-runner-usability-1023/README.md),
  [파일 SHA-256·심볼/행·명령·검증 원문](../../analysis/local-runner-usability-1023/evidence.json).
- 공용 현황·단일 백로그·현재 위협 후보 매핑·코드 스냅샷 갱신. 과거 독립 검토 해시는 보존했다.

## 검증

Windows의 Python 3.10.5(`py -3 -B -X utf8`)와 Node에서 오프라인으로 수행했다.
생산 코드의 엔진/DB 경로는 대역으로 검사했으며 실제 MCP·엔진 실행 증거로 세지 않는다.
정확한 명령 인자·시각·종료 코드·원문 출력은 구조화 검증 기록에 있다.

| 확인 종류 | 명령·환경 | 결과 |
| --- | --- | --- |
| 새 정상·음성·경계·실패·경쟁·복구 | `py -3 -B -X utf8 full_stack_lab/tests/local_runner_usability_check.py` | 28/28 통과 |
| 기존 DEV-73 | 같은 실행기로 `dev73_rework_check.py` | 19통과·Linux openat/FD 바인드 4건 생략(총 23건) |
| 기존 재검토·원격 서버 보존 | `dev73_review2_check.py`, `dev73_integration_check.py` | 각 5/5·7/7 통과; 기존 기대값 변경 없음 |
| 지정 매니페스트 시험 | `local_run_manifest_check.py` | 시작 실패: `ModuleNotFoundError: cryptography`. 서명 시험 통과로 세지 않음 |
| 지정 lint | `py -3 -m pyflakes` + 변경 Python 5파일 | 시작 실패: pyflakes 모듈 없음. 로컬 ignored 경로에 의존성 확보 시도도 배포원 후보 없음으로 실패 |
| 구문 | 변경 Python 5파일 `ast.parse`; `node --check .../console.js` | 통과; pyflakes·운영 Python 3.12 실행의 대체 증거가 아님 |
| 콘솔 상태 | `node --test full_stack_lab/tests/console-state.test.mjs` | 15/15 통과 |
| 인증 경계 | `py -3 -B -X utf8 full_stack_lab/tests/open_endpoints.py` | 통과: 무인증 1·인증 필요 97, 장치 자격 13 |
| diff 공백 | `git diff --check` | 통과 |
| 위키·추적 | `map_threats.py`, `capture_status.py`, `build_wiki.py`, `check_wiki.py`, CI ignored-source 모드, `check_trace.py --self-test` | 현재 후보 해시 재생성·인벤토리·추적 자체 시험 통과. 일반 검사는 provenance.json 29건 누락으로 실패, CI 모드는 원문·추출 등 누락 119건 경고/오류 0. 구체 결과는 구조화 기록 참조 |
| DB·실제 엔진·모델 하네스·효과·배포 | `dev73_rework_pg_check.py`, `local_jobs_pg_check.py`, 실제 공식 이미지/승인 UI/PJ1 | 미실행. 로컬 compose 및 기기/PJ1 접속 없음 |

WSL 정적 검사 대체 경로도 `E_ACCESSDENIED`로 사용할 수 없었다. 실패 검사를 통과로 바꾸거나
생산 의존성·검사 통제를 우회하지 않았다. 실제 Gitleaks 호출·서명 SDK 실행·PostgreSQL 마이그레이션과 경합,
브라우저 승인 화면 렌더링은 이번 로컬 통과 범위에 포함되지 않는다.

## 미완료·한계

실제 냉시작 수신·권한 거부·종료 회수와 임대 갱신/만료의 DB 경합은 미검증이다. manifest·pyflakes 의존성 공백도 남는다.
따라서 **수정과 오프라인 검증 산출물 완료, 실사용 결함 해소 검수는 미완료**다.
180초보다 긴 수신이나 일반 요청의 원래 기한을 넘는 수신은 계속 차단한다. 상태 조회가 실패하면 종료 코드는 미확인이다.
검사 장애 시 표준 오류를 숨기며 HTTP/감사 경계의 추가 검사 실패는 전체 오류를 보류할 수 있다.
rootless Podman은 현재 root 서비스의 실제 지원 구현이 아니다. Docker 사용자 재매핑을 켜도 관리 UID가 유지되므로
root 전용 실행 파일을 자동으로 실행하지 않는다. D-192의 경로 바인드 경쟁·이미지 서명 미확인 한계는 그대로다.

## 다음 작업

리더가 변경된 게이트웨이·스키마·실행기를 반영한 뒤 PJ1 실제 하네스로 공식 이미지의 냉시작·권한 거부·정지 회수를 재측정한다.

## 사용자에게 필요한 입력

없음. 기기·PJ1 실측은 이번 사용자 지시대로 리더 담당으로 남겼다.
