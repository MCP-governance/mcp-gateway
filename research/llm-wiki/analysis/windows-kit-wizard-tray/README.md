# Windows 키트: 마법사·트레이·포함 Python

- 결정: [D-118](../../../../docs/ai/DECISIONS.md), 기존 [D-68](../../../../docs/ai/DECISIONS.md).
- 업무: DEV-25·DEV-26, G08.04·G05.04. 이 작업은 Windows UI/배포·제거 경합이며 WFP 실행/파일 정책을 새로 구현하지 않는다.
- 코드 기준: `0eb013b37864e27bcb041145c9b9cea928f03d8d`에서 시작한 현재 작업 트리. 커밋·푸시·브랜치 변경 없음.
- [원자 요구사항·코드·시험 연결](requirements.json), [검증 명령 실제 결과](validation.json), [공식 근거·OSS 검토](references.json).
- [2026-10-18 보안 검토·신뢰 근거·Linux 잔여 위험](security-review.md).
- [pj3 검수](../../../../endpoint-agent/tests-windows/README.md), [작업 보고](../../status/reports/2026-10-17-windows-kit-wizard-tray.md).

## 구성 경로

`gateway/Dockerfile` → `prepare-windows-python.py` → `/opt/windows-python/{python.zip,windows-python.json}` →
`agent_service.download_managed_kit`의 기존 인증된 Windows ZIP → `install.cmd` → `setup.ps1` → `windows-worker.ps1`.
사용자 관측 경로의 기존 `install-windows.ps1`도 같은 마법사로 진입한다. 관리형 다운로드에서 관측 전용으로 강등하는 선택지는 없다.

마법사·트레이는 Windows의 PowerShell 5.1/WinForms만 쓴다. 한국어 PS1은 UTF-8 BOM을 붙여 5.1의 ANSI 오독을 막는다.
관측 전용은 현재 사용자 설치 위치와 ACL을 사용한다. 관리형은 고정 Program Files와 기존 protected check를 사용한다.
일반 계정·다른 계정 UAC·로그아웃 요건은 기존 보안 경계이며 GUI가 우회하지 않는다.

## 상태와 보존 범위

프로그램/상태 파일은 권한이 다르다. 장치 키가 있는 ProgramData 설정을 트레이에 넘기지 않는다.
SYSTEM 서비스는 키·헤더·원본 이벤트 세부정보 없이 로컬 표시용 스냅샷을 대상 SID만 읽을 수 있는 ProgramData 경로에 쓴다. 이 값은 인가에 쓰지 않는다.
Windows 관측기가 이미 파싱한 실제 이벤트의 시각·종류·식별자만 최근 차단의 입력으로 쓴다. 감사 비활성·SID 미확인을 차단 성공으로 표시하지 않는다.

제거 목록은 ZIP/코드/생성 파일의 명시적 목록이다. 루트·부모·하위 reparse point와 루트 밖 경로는 거부하며 목록 밖 사용자 파일을 지우지 않는다.
예약 작업 종료를 먼저 기다리고, 직원 PC 키트는 report 잠금으로 로그 닫힘과 설정 제거를 직렬화한다.
`report.lock`은 대기자가 다른 inode를 잠그지 못하도록 남기고, `setup.log`는 진단 기록으로 남긴다.

## 현재 증거의 한계

실제 GUI·UAC·ACL·Task Scheduler·포함 Python·차단 알림은 **미실행**이다. 로컬 테스트의 fake 함수/ZIP/이벤트는 단위 대역이다.
python.org 공식 릴리스 메타데이터·SHA는 확인했으나 외부 다운로드는 WinError10013으로 막혀 실제 바이너리/모듈 실행을 확인하지 못했다.
pyflakes 미설치, Windows Python3.10의 tomllib 부재, Linux 공용 시험의 grp 부재를 통과로 세지 않는다.
`status/current.md`는 사용자의 통합 지시대로 변경하지 않았다. 상태 생성기/전체 위키 재생성도 통합 담당자가 수행한다.
