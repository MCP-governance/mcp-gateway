# 2026-10-26 Unix 엔드포인트 키트 재설치 점검

- 작업자: Codex
- 코드 기준: `98f91856133a662c6a0296a436fe1fab4c47c546`, `10/26-linux-kit-reinstall`의 미커밋 변경.
- 시작 근거: Windows 실측 보고의 P0-2·P1-3·P2-5·P2-6 및 Windows 수정 보고. 원본은 작업 폴더의 비추적 입력이며 PR #59 원격 코드는 가져오지 않았다.
- 완료 조건: 등록 실패 시 기존 설치 보존, 반쪽 설치의 안전한 제거, Codex 직원 표 보존, 설치 진단의 지속·비밀 제외. 결정 D-255.

## 결과

`managed-linux.enroll`은 설치 파일 변경 없이 등록·정책 수신을 수행한다. Linux bootstrap과 macOS 설치기는 이 성공 뒤에만 이전 설치를 제거한다. 등록 결과는 Linux의 root 프로세스 메모리로 전달한다. 관측용 `install.py`도 후보 설정으로 1회 보고를 마친 뒤 기존 설정을 교체한다. Linux의 config.json 없는 상태 폴더를 설치 흔적으로 인정하고 제거 실패를 전파한다. macOS는 소유 기록이 없으면 계정·홈을 보존하며 알려진 서비스·anchor·백업을 정리한다. 관리형 설치기 자체에는 사용자 Codex 마커 편집이 없지만 CA 키트에 동봉하는 `field/pc/mcpgw_pc.py`에는 정규식 범위 삭제가 있었다. 정확한 마커 쌍·기록한 렌더링만 제거하고, 불명확하면 원본 바이트 백업 후 실패하도록 수정했다.

진단은 추가 기록하며 알려진 토큰·장치 키와 인증·비밀번호 줄을 제외한다. AppArmor 프로필·관리형 Codex 실행기 D-253 및 리프레시 잠금은 변경하지 않았다. 기존 표준 라이브러리만 사용했다. 외부 GitHub 접근은 연결 실패로 판본을 새로 확인하지 못했다. 적용한 로컬 Ponytail 스킬은 5.3.2, MIT이며 외부 스크립트는 실행하지 않았다.

## 검증

| 확인 종류 | 명령·환경 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 추가 회귀 | Python 3.10.5 Windows, `python -B -X utf8 full_stack_lab/tests/linux_kit_reinstall_check.py` | 17건 통과 | root `REPORT-LINUXRE.md`, 로컬 runtime 로그 |
| 관련 회귀 | run_local_suite.py의 PYTHONPATH와 임시 HOME·CODEX_HOME으로 관련 18파일 실행 | 12파일 정상 종료, 6파일 실패·환경 차단. 실패 6파일은 시작 커밋 사본에서도 동일 원인 재현 | root 보고의 파일별 표 |
| 정적 | 변경 Python AST 및 `git diff --check`, 위키·추적·기업 분석 검사 | 통과. freshness는 기존 날짜·시트 관련 경고 | root 보고 |
| Linux 전용 | `wsl.exe -d kali-linux` | `Wsl/Service/E_ACCESSDENIED`, 미실행 | root 보고 |
| 실제 모델·MCP·OS | 실제 등록·systemd·AppArmor·launchd·PF | 미실행 | 없음 |
| 배포·커밋 | 배포 없음, Git 공용 index.lock 생성 권한 거부 | 커밋 미생성, push·PR 없음 | root 보고 |

## 실패·미완료·한계

서버 등록 성공은 이전 자격을 철회할 수 있다. 정책 수신 실패 시 로컬 파일 보존이 서버 연결 유지를 뜻하지 않으며, 교체 도중의 완전한 원복 트랜잭션도 없다. macOS의 config.json 소실은 PF 활성화 참조 번호를 복구할 수 없고, 소유 저널이 없으면 기존 계정은 보존한다. Linux의 런처 소유 정보·로그인 셸 원복 정보가 소실되면 관련 파일을 보존하고 실패한다. 이 결과는 제품 실측·배포 완료가 아니다.

## 다음 작업

DEV-84·DEV-87: 권한 있는 환경에서 Linux 전용 회귀와 양 OS 실제 재설치·반쪽 설치 제거를 확인한다. 서버 자격 철회와 정책 실패의 복구 절차를 별도 검증한다. Git 인덱스 쓰기 가능한 환경에서 검토 후 `fix(v2): …`로 커밋한다.

## 사용자에게 필요한 입력

새 자격증명은 필요 없다. 남은 실행에는 WSL 접근과 공용 Git 인덱스 쓰기 권한, 지정 Linux 시험 PC 및 macOS 시험 기기가 필요하다.
