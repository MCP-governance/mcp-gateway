# W5-KIT-MACOS 요구사항과 근거

기준 `1c59a00c91727dfbd9faab37870f274b11e448f5`, 작업 브랜치 `10/22-kit-macos`, 미커밋.
실제 MCP·기기 실행 증거가 아닌 오프라인 코드 분석이다. [작업 보고](../../status/reports/2026-10-22-kit-macos.md).

| 요구 | 구현 심볼 | 조건과 오프라인 증거 | 미확인 |
| --- | --- | --- | --- |
| MAC-01 관리 계정·공식 하네스 | `managed-macos.install`, `bootstrap.search_roots/native/place_harnesses` | Mach-O/ELF 분기·키트 파일 존재·기존 계정 거부 경로 | dscl 실제 계정·실제 배포판 조합 |
| MAC-02 한 줄·암호1회·비밀 분리 | `kit_commands.macos_bootstrap`, `install-macos.sh`, `download_managed_kit` | 명령에 자격 없음·curl config 파일·원자 소비 SQL·5분·PSF 서명 검사·umask022 | 브라우저 다운로드·Gatekeeper·키트 소비 DB 경쟁·Python pkg 실행 |
| MAC-03 허용 목록·상주 | `pf_rules`, `apply_pf`, `daemon_plist`, `start_runtime` | IPv4/IPv6·포트 범위·잘못된 입력 거부·plist 비밀 없음 | pf 파서·시스템 anchor·재부팅·launchd |
| MAC-04 정책·활성화·MCP | `configure_runtime/checks/authorize_peer`, `managed_platform`, `managed_policy`, `DeviceEnrollment` | 별도 체크4개·Linux 체크 유지·등록 UID 검증·기존 헬퍼만 사용 | 실제 getpeereid·활성화·모델 프록시와 실제 MCP 효과 |
| MAC-05 콘솔 OS 우선 | `preferredKitPlatform`, `pc-kit`, `integrations.platform_of` | 브라우저 OS 우선·한글 라벨·기존 콘솔15건 | 실제 브라우저 화면 |
| MAC-06 복구 | `rollback`, `ROLLBACK_ORDER` | OS 명령 대역으로 실제 rollback 함수의 역순·기존 파일 복원·계정 마지막 확인 | 설치 중단·재설치·제거 실기기 |

`full_stack_lab/tests/macos_kit_check.py`는 표준 라이브러리와 제품의 순수 함수/AST 본문을 사용한다.
명령 대역은 macOS 도구 실행을 막기 위한 것이며 새 MCP 대역을 만든 것이 아니다. 기존 시험 기대값 변경 없음.
실제 실행 명령·결과는 `checks.json`과 `checks.log`, 코드 판본·심볼 행·SHA-256은 `code-anchors.json`에 남긴다.

## 공식 자료·OSS·공개 스킬 사전 조사 (2026-10-22)

- [Apple launchd 안내](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html):
  LaunchDaemons·프로그램 인자 plist 구조 확인. 표준 라이브러리 plistlib로 작성하며 외부 스크립트를 가져오지 않았다.
- [Apple TN3165](https://developer.apple.com/documentation/technotes/tn3165-packet-filter-is-not-api):
  PF가 안정 API가 아니며 시스템 규칙과 충돌할 수 있다는 공식 경계 확인. 문서 요약/메타데이터 읽기이며 전체 본문은 JS 렌더 제한.
- [OpenBSD pf.conf](https://man.openbsd.org/pf.conf.5): UID user 매칭의 TCP/UDP 한계와 anchor 구조를 대조했다.
  macOS PF의 동일 판본이라고 간주하지 않는다. 실제 macOS 파서는 미실행이다.
- [PSF macOS 릴리스](https://www.python.org/downloads/macos/),
  [Python3.14.9 파일 목록](https://www.python.org/ftp/python/3.14.9/),
  [PSF 설치 패키지 서명자](https://www.python.org/getit/): 2026-10-21 universal2 pkg 존재와 PSF Team ID 확인.
  공식 런타임은 PSF 라이선스, 배포판은 공급자 HTTPS에서 직접 받는다. 저장소 재배포 없음. 실기기 signature/installer 실행 미확인.
- [macadmins/outset v4.3.0.22031](https://github.com/macadmins/outset/releases/tag/v4.3.0.22031): Apache-2.0,
  릴리스·README·launchd 기반 boot/login 사용 범위를 확인했다. commit 전체 SHA 확보는 네트워크 제한으로 미확인,
  유지보수성 판단은 공개 릴리스 존재 수준이다. 이번에는 설치/로그인 시나리오 실행 플랫폼이 추가 의존성이므로 도입하지 않았다.
- [공개 스킬 카탈로그](https://github.com/majiayu000/claude-skill-registry/commits/main/): MIT 카탈로그,
  열람된 기록 `b8100d8`(2026-08-05), macos-networking 후보 검색. 개별 SKILL 본문·고정 전체 commit·개별 재배포 라이선스는
  확보하지 못했으므로 사용하지 않았다. 카탈로그 라이선스를 개별 스킬 라이선스로 간주하지 않는다.
- 실제 재사용은 저장소 기준 `1c59a00`의 `bootstrap.py`와 `managed-linux.py`다. 외부 스킬·OSS 스크립트 실행/복사 없음.
  원격 HEAD 재확인은 GitHub443 연결 제한으로 실패했으며 로컬 기준만 확인했다.

## 검증 경계

pf 허용 대상은 게이트웨이 IP의 게이트웨이·모델 프록시 TCP 포트이며 나머지 관리 UID TCP/UDP를 막는다.
프로세스 격리·전체 IP 프로토콜·같은 UID 헬퍼 호출 차단은 구현하지 않았다. 침해된 관리자에 대한 보장은 없다.
실제 macOS 설치·활성화·MCP·제거·재부팅은 미실행이다. Python 공유 런타임은 제거하지 않는다.
공식 Codex·Claude는 기존 D-71과 같이 사전 설치 대상이며 새 MCP를 만들지 않는다.
