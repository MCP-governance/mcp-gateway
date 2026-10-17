# 2026-10-18 보안 검토 반영

앞 구현에는 관리자 작업자가 사용자 쓰기 가능한 원본에서 common/ZIP을 읽는 문제가 있었다. Python ZIP 자체 해시만 확인해도
그 검사를 수행하는 스크립트나 핀 JSON을 함께 바꿀 수 있으므로 관리자/SYSTEM 지속 실행의 출처 인증이 되지 않았다.
개인 트레이 JSON을 Users:RX 프로그램 디렉터리에 둔 점과 제거 시험의 빈 디렉터리 단언도 정정한다.

## Windows 신뢰 경로

1. 조직의 승인 배포 도구가 검토한 설치기 전체를 `%ProgramFiles%\MCPGatewayInstaller`에 배포한다. 이 단계 자체가 신뢰 근거다.
   다운로드 폴더의 코드를 최초 관리자 bootstrap으로 실행하지 않는다. 직원은 이 승인물을 만들거나 갱신하지 못한다.
2. 별도 승인된 `approved-windows-kit.json`을 `%ProgramData%\MCPGatewayInstaller`에 둔다. 기존 인증된 키트 응답은 원자적으로 읽은
   코드/런타임 바이트의 SHA-256 매니페스트와 그 매니페스트의 SHA-256 헤더를 제공한다. 새 API는 없다.
   관리자는 신뢰되는 인증 경로/릴리스 승인에서 별도로 확정한 값을 사용한다. 같은 ZIP 안에서 계산한 값만으로 승인하지 않는다.
3. 마법사의 UAC 경로는 고정된 승인 작업자만 실행한다. 작업자 안의 독립 초기 검사가 helper를 로드하기 전에
   그 helper·작업자·별도 승인물·상위 경로의 ACL/소유자와 해시를 먼저 확인한다. 아직 실행하지 않은 helper가 자기 검증을 맡지 않는다.
   그 뒤 전체 경로·소유자·쓰기 ACL·reparse·정확한 파일 목록·각 해시를 확인한다.
   보호된 코드 및 승인 파일이 없으면 사용자 원본으로 돌아가거나 새 승인 파일을 만들지 않는다.
4. 작업자는 원본 코드/ZIP을 사용자 폴더에서 읽지 않는다. 요청과 등록 JSON만 핸들로 열어 크기·실제 경로를 확인하고 보호된 요청 사본으로 고정한다.
   요청자는 승인된 게이트웨이 주소/노드 ID를 변경할 수 없다. 승격 결과 파일도 사용자 쓰기 경로에 쓰지 않는다.
5. 설치 폴더에 복사한 코드와 압축 해제한 Python 전체를 실행 전 다시 검사한다. 허용되지 않은 실행 파일·DLL/스크립트 추가도 거부한다.
   코드·공식 ZIP·검색 경로 검사에 모두 통과한 뒤에만 포함 Python을 실행한다.

`windows-trust.ps1` 자체도 위 조직 관리 배포물이다. 그 스크립트가 자기 출처를 스스로 확립한다고 주장하지 않는다.
관리자가 임의의 다른 PowerShell 명령을 직접 승인하거나 승인 파일/코드를 교체하는 행위까지 방어하는 OS 정책은 이번 범위가 아니다.
프로세스의 `-ExecutionPolicy Bypass`나 UAC 동의를 출처 인증으로 세지 않는다.
Microsoft의 [실행 정책 문서](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies?view=powershell-7.5)와
[UAC 동작 문서](https://learn.microsoft.com/en-us/windows-server/security/user-account-control/how-user-account-control-works)를 구분해 적용했다.

## 개인 트레이 파일

Program Files에는 공용 코드만 둔다. 설정·상태·교체용 임시 파일은 `%ProgramData%\MCPGatewayManagedTray\<SID>`에 둔다.
상속을 끊은 ACL을 처음 서비스 실행 전에 만든다. Administrators·SYSTEM만 쓰고 대상 SID만 읽는다.
기존 명시적 Users 읽기 ACE도 수리 시 남기지 않는다. 상태 작성기는 폴더가 없다고 공용 기본 ACL로 재생성하지 않는다.
교체 파일이 같은 개인 디렉터리에서 생성되므로 원자 교체 중에도 공용 읽기 구간을 만들지 않는다.

## 검증 범위

- 단위: 스크립트·ZIP·핀 JSON 교체, ZIP 옆 매니페스트 동반 교체, 설치 목적지 교체, 추가 실행 파일, 승인물 누락, 사용자 쓰기 ACL 거부.
- ACL 기술자 단위: 디렉터리/파일 모두 대상 SID·Administrators·SYSTEM만 허용, 대상 SID 쓰기 없음, 상속 해제.
- 파일 단위: 실제 핸들의 경로·크기 검사, report 종료 대기·제거 뒤 지연 report 미재생성, 정확한 report.lock 잔여 조건.
- ACL 조회는 위 변조 시험에서 대역이다. 실제 다중 사용자 파일 접근·UAC·배포·서명 정책·reparse 경쟁은 pj3에서 메인이 확인해야 한다.

## 잔여 위험 LINUX-INSTALL-TRUST

- 근거: `endpoint-agent/install.sh`의 `sudo ... "$HERE/bootstrap.py"` 경로, `endpoint-agent/bootstrap.py`의
  `HERE = Path(__file__).resolve().parent` 및 그 원본에 의존하는 배치 흐름.
- 위험: 직원 쓰기 가능한 디렉터리에서 최초 root 실행 코드를 가져오므로 Windows의 앞 구현과 같은 출처/교체 문제가 있다.
- 상태: **미수정·미검증**. 이번 Windows 수정으로 Linux도 해결됐다고 표시하지 않는다. Linux 파일·실기기·sudo 설정은 변경하지 않았다.
- 후속: Linux도 조직이 승인·배포한 최초 설치기와 ZIP 밖 신뢰 근거, 보호된 스테이징과 실행 전 재검증을 별도 설계/검수한다. DEV-25에서 함께 추적한다.
