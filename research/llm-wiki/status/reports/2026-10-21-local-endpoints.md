# DEV-81 로컬 수신 지점 인증 적대 검토 보고

작성일: 2026-10-21
기준: `main` `f5fa6fd`
분석: [수신 지점 목록·판정·수정 제안](../../analysis/local-endpoints-1021/README.md)

## 결과

Linux Unix 소켓, Windows 이름 있는 파이프, 직원 PC 키트 헤더 명령은 같은 관리 UID/SID의 다른 프로세스를 프로세스 단위로 인증하지 않는다. 같은 계정 프로세스가 관리 사용자용 MCP bearer를 받을 수 있어 세 지점을 `열려 있음(제품이 막아야 함)`으로 판정했다. 심각도는 높음이다. 게이트웨이 정책 판정은 토큰 유출 뒤에도 적용된다.

D-119의 관리 계정발 비인가 로컬 MCP 차단은 기존 코드·기록을 유지했다. 소유자 브라우저 로그인 callback 예외는 D-119의 의도된 범위이며 악성 웹 Origin 접근을 막는 증거가 아니다. 웹 브라우저로부터의 단순 요청 0은 정적 근거로 확인하지 못했다.

DEV-73 `endpoint-agent/local-runner.py`와 그 로컬 교환 파일은 현재 체크아웃 및 사전 적재 참조에서 찾지 못해 판정 유보다. 이 부재 때문에 DEV-81 전체 완료는 판정하지 않는다.

## 확인한 것

- 작업 기준 원문 `analysis/direction-1020/README.md` §3의 DEV-81 조건을 적용했다. 백로그 요약 대신 이 원문을 기준으로 삼았다.
- `endpoint-agent/`, `full_stack_lab/field/pc/`, 관리형 설정 렌더러, 두 catalog, named pipe·Unix socket·loopback URL·임시 파일 경로를 정적으로 검색했다. 제품 TCP HTTP listener는 발견하지 못했다. 확인된 제품 IPC는 Linux AF_UNIX 헤더 브로커와 Windows named pipe다.
- Linux broker의 `SO_PEERCRED`가 UID만 비교하고 bearer를 응답하는 것, Windows pipe DACL이 등록 SID 전체에 읽기를 허용하는 것, PC 키트 `header` 명령이 stdout으로 bearer를 내는 것을 확인했다.
- managed renderer/catalog의 Gateway 기본 주소가 비어 있으며 field 배포 주소는 HTTPS다. demo MCP endpoint는 컨테이너 호스트명이다. 이 설정에서 직원 PC용 localhost MCP listener는 구성되지 않는다.
- D-119, D-124, D-147, D-148, D-170 및 `dev35-loopback`과 2026-10-20 E13 자료를 기존 근거로 대조했다. **사용자 지시의 D-124 번호는 TLS 결정이다. 소유자 루프백 응답 예외는 D-119다.** 이 번호 정정은 새로운 결함 판정이 아니다.
- 오프라인 버퍼의 root/SYSTEM 보호 경로와 원자 교체, Windows 승격 요청 파일의 승인 경로·SID·핸들 확인을 읽었다. 상태 스냅샷은 자격증명 없는 읽기 전용 정보로 구분했다.
- Codex 0.160.0 고정 소스에서 browser OAuth localhost callback, state/PKCE 확인, Origin 검사 부재를 확인했다. 이 소스는 MINT 제품 코드가 아니다. Claude의 현재 바이너리 구현은 이번 검토에서 확인하지 못했다.
- 전체 분석·재현 조건·수정안·D-170 분류는 [분석 문서](../../analysis/local-endpoints-1021/README.md)에 기록했다.

## 확인하지 못한 것

- DEV-73 `endpoint-agent/local-runner.py` 소스와 실행기 요청/결과 파일. 현재 경로에 없고 사전 적재 `origin/10/20-dev73-review` 및 DEV-80 작업 참조에도 파일이 없었다. 이전 `d175-local-run.md`의 코드 인용만으로 동작을 추정하지 않았다.
- 현재 배포 장치의 실제 listener 목록, Linux AppArmor/nft 런타임, Windows ACL 실측, pipe 접근, 실제 토큰 노출 효과.
- 브라우저의 `fetch`·form·img/script 요청이 현재 OS/브라우저 정책을 통과하는지, Codex/Claude callback이 특정 simple request로 상태를 바꾸는지. Origin/CORS/DNS rebinding 실제 공격은 실행하지 않았다.
- enrollment 입력 파일의 설치 시점 ACL과 경합 가능성. 설치 명령이 root/Admin으로 파일 경로를 읽는 부분은 보았으나 현장 ACL/타이밍은 확인하지 않았다.
- D-119 적용 이후 현 판본의 PJ1 실행 효과. 과거 E13·10-15 관찰을 이번 판본의 재실행 증거로 세지 않았다.

## 실행하지 않은 시험과 변경

- 솔루션 기기, PJ1, compose stack, live listener/pipe/socket, 브라우저 요청을 실행하지 않았다.
- 시험·정적 검사 명령을 실행하거나 추가하지 않았다. 보고서와 분석 문서만 작성했다.
- 제품 코드, 시험, `status/current.md`, backlog, D-number 기록은 수정하지 않았다.
- 이 작업은 읽기 전용 적대 검토로 진행했다. 작업 트리에 미커밋 문서 두 개만 남긴다.

## 방향 제안

동일 UID/SID helper에서 재사용 bearer를 임의의 같은 계정 프로세스에 반환하지 않는 별도 구현 작업을 발행한다. 이 작업에는 Linux broker, Windows pipe, field PC CLI를 각각 포함하고, 동일 UID/SID 프로세스·다른 계정·실제 하네스 호출을 서로 구분한 검증 근거를 요구한다. DEV-73 실행기 원문이 정본 체크아웃에 들어온 뒤 그 수신·버퍼 경계를 추가 검토한다. 브라우저 callback의 Origin·simple-request 제한은 하네스 소유자/버전 범위를 정한 별도 검토로 다루며, 현재 근거로 접근 0을 선언하지 않는다.
