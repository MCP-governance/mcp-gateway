# 2026-10-17 loopback-owner-replies-d119

- 작업자: Codex
- 코드 기준: `0eb013b37864e27bcb041145c9b9cea928f03d8d`, 시작 시 clean, 기존 작업 브랜치 `10/17-loopback-d107`. 사용자 지시대로 브랜치 변경·커밋·푸시 없음. 원격 HEAD 재조회 `git ls-remote --symref origin HEAD`는 github.com:443 연결 실패로 확인 불가.
- 시작 근거: DEV-35, [원인·과거 netns·기각안](../../analysis/dev35-loopback/README.md), [10-15 보고](2026-10-15-dev35-loopback.md), D-113, 2026-10-17 사용자 채택 D-119.
- 해결할 문제와 완료 조건: 장치 코드 기본 실행·소유자 시작 연결의 응답만 허용·E13 경계 보존을 구현하고 오프라인 검증 및 메인용 실기기 명령을 남긴다. 배포·실기기 성공은 이번 완료 조건에 포함하지 않는다.
- 변경 파일: `endpoint-agent/{enforce-linux.py,managed-linux.py,bootstrap.py,README.md}`, `full_stack_lab/tests/loopback_owner_replies_test.py`, `docs/ai/DECISIONS.md`, `research/llm-wiki/analysis/dev35-loopback/README.md`, `research/llm-wiki/status/reports/2026-10-15-dev35-loopback.md`, `research/llm-wiki/status/backlog.md`, 이 보고, `research/llm-wiki/status/repository-snapshot.{json,md}`, `research/llm-wiki/catalogs/threats.json`, `research/llm-wiki/threats/control-map.md`. `status/current.md`·Windows 키트·`install.py`는 변경하지 않는다.

## 결과

`nft_rules(..., owner_uid=None)`에 소유자 original/new 표식 설정과 관리 UID의 표식 있는 reply 허용 두 줄을 추가했다. 소유자 미지정이면 이전 규칙과 같고 관리 출발 SYN·자기 리스너·다른 UID·포트 허용은 추가하지 않는다. `0x100`은 OR로 설정하고 AND로 검사하며 PJ1의 과거 Tailscale 마스크 `0xff0000`과 충돌하지 않는다. 기존 게이트웨이·모델 프록시 허용 및 마지막 reject는 유지한다.

`bootstrap.main`이 확인한 직원 계정 UID를 **별도 관리 계정을 만든 경우에만** `install_managed` → `managed-linux.py install --owner-uid` → `enforce-linux.py --owner-uid`로 전달한다. 수동 설치는 관리자가 UID를 명시해야 한다. 시스템 UID·관리 UID 자신·범위 밖·실재하지 않는 계정은 등록 토큰 소비 전에 실패한다. `owner_uid`는 root 비밀 설정에 보존하고 실제 nft baseline에도 새 규칙이 들어간다. 게이트웨이의 transport 신원·직원 토큰 처리에는 관여하지 않는다.

설치 중 `LOGINS["codex"]`는 이미 `codex login --device-auth`였으므로 그대로 사용한다. 설치 후 영어 TUI 선택·브라우저 실패 문구는 `Codex 로그인: codex login --device-auth`로 바꿨다. 실패·Ctrl+C 때 브라우저 방식으로 전환하지 않는다. 기존 개인 ChatGPT 보안 설정 안내는 유지한다.

`os-observer.py`의 D-113 코드는 변경할 필요가 없었다. 새 accept가 `MCPGW_DENY` 로그보다 앞에 있어 허용 응답은 거부 이벤트 입력이 되지 않는다. 소유자 이외의 연결로 막힌 SYN-ACK는 계속 `listener_reply`, 관리 출발 SYN은 `blocked_attempt`로 기록한다. 과거 거부·감사 기록은 수정하지 않는다.

원자 요구사항→심볼→시험→남은 실기기 확인은 [분석 표](../../analysis/dev35-loopback/README.md#d-119-채택구현-2026-10-17-배포-전)에 연결했다. 작업 트리의 코드 앵커는 `enforce-linux.py:nft_rules:67/main:202`, `managed-linux.py:install:162/main:384`, `bootstrap.py:install_managed:361/harness_login:379/main:486`, `os-observer.py:event:46`이다. 판본은 위 시작 commit + 미커밋 변경이며 파일 해시는 저장소 스냅샷·통제 매핑에 있다. 당시 제안 번호는 D-119로 정리하고 런처 결정 D-107은 보존했다.

## 검증

Windows PowerShell·Python 3.10.5, 2026-10-17 21:36~21:45 KST. 아래 명령은 저장소 루트 기준이다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 순수 Python 단위 | `python -B -X utf8 -m unittest discover -s full_stack_lab/tests -p loopback_owner_replies_test.py -v` | 9개 통과. 생성 규칙·순서·마스크·UID 경계·설치기 UID 전달·등록 전 실패·로그인 성공/실패/중단·거부 분류 | 시험 파일, 협업 콘솔 check 기록 |
| 구문 검사 | 아래 compile 명령 | `syntax OK: 5 files`, exit 0 | 로컬 도구 출력 |
| pyflakes | `python -m pyflakes --version` | `No module named pyflakes`; pyflakes 검사는 미실행 | 로컬 도구 출력 |
| 변경 검사 | `git diff --check` | 통과, exit 0 | 로컬 도구 출력 |
| 보고서 명령 구문 | 보고서의 Python here-doc 2개를 추출해 `compile(..., 'exec')` | `report Python blocks syntax OK: 2` | 실행·커널 적용은 하지 않은 구문 검사 |
| 위키 스냅샷·목록 | `python -B -X utf8 research/llm-wiki/tools/capture_status.py`, `python -B -X utf8 research/llm-wiki/tools/build_wiki.py` | 통과, 문서 482개. 로컬 코드 전용 | `status/repository-snapshot.*` |
| 통제 매핑 | `python -B -X utf8 research/llm-wiki/tools/map_threats.py` | 정적 후보 24개 재생성, 바뀐 Linux 두 파일 해시 갱신. 실행 검증으로 승격하지 않음 | `catalogs/threats.json`, `threats/control-map.md` |
| 위키 전역 검사 | `python -B -X utf8 research/llm-wiki/tools/check_wiki.py` | **실패**, exit 1: 미제공 로컬 원문 provenance 29개. 최초 실행의 코드 매핑 불일치 2개는 재생성 후 해소 | 아래 누락 목록 |
| 프로토콜·커널 | nft 구문/적용·이번 판본 netns·Tailscale 공존 | 미실행 | 10-15 `lab/output.txt`는 과거 증거로 보존 |
| 실제 모델·하네스 | Codex 장치 코드·정상 IPC·Claude·R1~R9 | 미실행 | — |
| upstream 효과 | 실제 OSS 비인가 MCP 수신 0·승인 MCP 정상 효과 | 미확인 | — |
| 배포·정책 해시 | 솔루션 기기·PJ1 키트 | 미배포·미확인 | — |

구문 검사는 바이트코드나 Linux OS 동작 없이 다음으로 실행한다.

```powershell
@'
from pathlib import Path
paths = [Path('endpoint-agent') / (name + '.py') for name in ('enforce-linux', 'managed-linux', 'bootstrap', 'os-observer')]
paths.append(Path('full_stack_lab/tests/loopback_owner_replies_test.py'))
for path in paths:
    compile(path.read_text(encoding='utf-8'), str(path), 'exec')
print('syntax OK:', len(paths), 'files')
'@ | python -B -X utf8 -
```

초기 단위 시험 확장 중 Windows의 `os.name` 전역 패치로 pathlib가 PosixPath를 만들고, 런처 대역 반환값이 JSON 직렬화되지 않는 시험 코드 오류가 났다. OS 대역을 설치기 모듈 안으로 한정하고 실제 형태의 반환값으로 고친 뒤 9개 모두 통과했다. 커널 시험의 실패/통과 기록은 아니다.

## 실패·미완료·한계

- 전역 위키 검사를 통과했다고 보고할 수 없다. 이번 작업이 수정하지 않은 `local-sources/compliance/<ID>/provenance.json` 29개가 없다: LIB-L05·L06·L09·L10·L11·L12, LIB-M04·M08·M13·M14·M15·M17·M20·M21·M22·M28·M31·M32·M34·M36·M37·M38·M39·M40·M43·M44·M45·M48·M49. 원문/권리 근거를 재구성하거나 거짓 provenance를 만들지 않았다. 메인이 원래 로컬 자료를 제공한 뒤 재검사해야 한다.
- 이 작업은 파일 생성·단위 수준이다. Python에서 검사한 문자열이 실제 커널 nft 파서·conntrack·AppArmor·Tailscale에서 작동했다는 증거가 아니다. Windows에서 없는 `pwd`·`grp`와 계정 조회/실행/서명 함수만 단위 대역으로 교체했으며 MCP 서버 대역은 만들지 않았다.
- 소유자 없는 수동 설치와 직원 계정 자체를 관리하는 설치는 응답 예외가 없다. `--owner-uid` 누락을 넓은 허용으로 보정하지 않는다. 관리 UID의 `/cancel` 자기 연결은 계속 거부된다.
- 소유자는 자신의 모든 프로세스에서 승인 하네스 리스너에 연결할 수 있다. 이는 채택한 범위다. root 침해·호스트의 다른 규칙이 0x100을 쓰는 경우·UID 재할당은 이 단위 시험이 보장하지 않는다. 배포 전에 전체 connmark 사용 범위를 확인해야 한다.
- 코드·문서 검토 범위: `nft_rules/main`, `managed-linux.install/checks/main`, `bootstrap.install_managed/harness_login/main`, `os-observer.event`, 관련 호출자·시험. 기존 키트의 계정 생성·삭제·모든 회수 경로 전체 감사는 하지 않았다.
- 공개 근거: [Netfilter nft 공식 매뉴얼](https://netfilter.org/projects/nftables/manpage.html)의 ct direction/mark, OR/AND 및 accept의 체인 종료 의미를 확인했다. 이는 이번 커널 적용 증거가 아니다. 기존 분석이 고정한 Codex `a956835d020762cb2b570053af06f643a11c0ecc`(Apache-2.0)와 PJ1 nftables 1.0.9·커널 7.0.0-38 기록을 재사용했다. 현재 설치 판본은 재조회하지 않았다.
- 공개 스킬 탐색: [anthropics/skills](https://github.com/anthropics/skills)와 webapp-testing 경로를 확인했으나 이 커널 정책 변경에 적용할 코드는 채택하지 않았다. 원격 commit·개별 라이선스·유지보수 판본은 확인하지 못했다. 외부 스크립트 실행·신규 의존성·복사 코드는 없다. 적용한 로컬 Ponytail 스킬은 5.3.2/MIT다.
- 소유자 규칙대로 로컬 compose·기기 접속은 하지 않았다. 원격 HEAD 확인 불가도 보고상 남긴다.

## 다음 작업

DEV-35는 **D-119 구현·로컬 단위 통과, 배포·실기기 대기**다. 아래 명령은 이번에 실행하지 않았고 메인이 검토한 판본에서만 실행한다. Bash 기준이며 `REPO`는 메인이 승인한 각 기기의 checkout 절대 경로로 지정한다. 자격·코드·전체 config.json을 로그에 출력하지 않는다.

### 메인: PJ1 격리 netns 회귀

PJ1에서만, 기존 역사 원본은 읽기 전용으로 마운트한다. 소켓 ping/pong은 방화벽 전송 시험 fixture이며 MCP 실행 증거가 아니다. 일회용 컨테이너 안에서만 nft를 바꾸고 호스트 netns를 쓰지 않는다. 이미지 준비 실패·리스너 준비 실패·assert 실패는 실패다.

```bash
set -euo pipefail
: "${REPO:?승인 checkout 절대 경로 지정}"
docker build -t mcpgw-d119-netns - <<'DOCKERFILE'
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends python3 nftables util-linux && rm -rf /var/lib/apt/lists/*
DOCKERFILE
docker image inspect mcpgw-d119-netns --format '{{.Id}}'
sha256sum "$REPO/endpoint-agent/enforce-linux.py" "$REPO/research/llm-wiki/analysis/dev35-loopback/lab/lab.py"
docker run --rm -i --network none --cap-add NET_ADMIN \
  -v "$REPO/research/llm-wiki/analysis/dev35-loopback/lab:/source:ro" \
  -v "$REPO/endpoint-agent/enforce-linux.py:/enforce-linux.py:ro" \
  mcpgw-d119-netns python3 -u - <<'PY'
import pathlib, runpy, shutil, subprocess
pathlib.Path('/lab').mkdir()
shutil.copyfile('/source/lab.py', '/lab/lab.py')
shutil.copyfile('/enforce-linux.py', '/lab/enforce-linux.py')
lab = runpy.run_path('/lab/lab.py')
actual = lab['enforce'].nft_rules(lab['MANAGED'], ['192.0.2.10'], 443, 3128, owner_uid=lab['OWNER'])
assert actual == lab['text'], 'production rules differ from exercised rules'
assert all(pathlib.Path(f'/tmp/ready-{p}').is_file() for p in range(20001, 20019)), 'listener failed'
negative = ('managed->managed', 'managed->owner', 'managed->owner6', 'managed->foreign', 'managed->owner-udp', 'foreign->managed')
assert all(not lab['prop'][key] for key in negative), lab['prop']
assert lab['prop']['owner->managed'] and lab['prop']['owner->managed6'] and lab['prop']['owner->owner']
lab['port'][0] = 1454
assert not lab['case']('managed -> owner squatting 1455', lab['MANAGED'], lab['OWNER'])
assert pathlib.Path('/tmp/ready-1455').is_file(), 'squatting listener failed'
pathlib.Path('/tmp/d119.nft').write_text(actual)
subprocess.run(['nft', '-c', '-f', '/tmp/d119.nft'], check=True)
subprocess.run(['nft', '-f', '/tmp/d119.nft'], check=True)
print('D119 production rules + E13 seven negatives OK')
PY
```

7종은 관리→소유자 TCP v4/v6, 관리→다른 UID, 관리→소유자 UDP, 관리→관리(`/cancel`), 다른 UID→관리의 6종과 **1455 선점** 1종이다. 10-15 `lab.py`의 추천안 BLOCK 행은 6개다. 기각안 `lab2.py`의 포트 선점 반례까지 합쳐 7종으로 명시했다. 문서의 "7종"을 7개 신규 커널 통과로 해석하지 않는다.

### 메인: 솔루션 키트 배포 → PJ1 재설치

솔루션 기기에서 승인한 checkout·소스를 통합한 뒤(직접 scp로 일부 파일만 덮어쓰지 않음):

```bash
cd "$REPO/full_stack_lab"
./console.sh field up
./console.sh field status
```

Console에서 새 Linux 키트를 내려받고 기존 장치 자격을 폐기한다. PJ1에서 다른 사람이 사용하는 세션이 없음을 먼저 확인한다. 새 키트 설치기는 기존 관리 계정 세션을 종료하므로, 사람의 진행 중 작업이 있으면 설치하지 않는다. 키트의 검토된 해시와 새 등록 토큰 유효성은 메인이 확인한다.

```bash
# PJ1: 다운로드한 새 키트 폴더에서, 직원 계정으로 실행
./install.sh --user pj1
# --skip-login을 썼거나 로그인을 중단했다면 새 터미널에서 실행
codex login --device-auth
codex login status
```

사람이 자기 계정으로 로그인한다. 장치 코드가 조직에서 비활성화돼 있으면 정책을 완화하지 않고 실패·미확인으로 기록한다. 독립 관리자가 엔드포인트를 활성화한 뒤 다음 값만 확인한다(`MANAGED`는 실제 설치 결과의 관리 계정 이름).

```bash
: "${MANAGED:?설치 결과의 관리 계정 이름 지정}"
uid=$(id -u "$MANAGED")
sudo python3 - "$MANAGED" <<'PY'
import json, pathlib, sys
c = json.loads((pathlib.Path('/var/lib/mcpgw-managed') / sys.argv[1] / 'config.json').read_text())
print({k: c.get(k) for k in ('username', 'uid', 'owner_uid')})
PY
sudo nft -c -f "/usr/local/lib/mcpgw-enforcement/mcpgw-$MANAGED/egress.nft"
sudo nft -a list table inet "mcpgw_uid_$uid"
sudo iptables-save -t mangle
sudo systemctl is-active "mcpgw-egress-$MANAGED.service" "mcpgw-managed-$MANAGED.service"
```

owner_uid=`id -u pj1`, `0x100`의 OR/AND, Tailscale 마스크 공존과 baseline heartbeat 일치를 확인한다. 기존 config/egress 파일만 수정하면 baseline 불일치가 나므로 재설치로 적용한다.

### 메인: R1~R9·장애·경쟁·복구

각 시험 시작 전에 `since=$(date --iso-8601=seconds)`를 기록하고 끝난 뒤 `sudo journalctl -k --since "$since" --no-pager --grep "MCPGW_DENY uid=$uid "`를 수집한다. 동일 창의 `endpoint_os_events`·리스너/실제 OSS 수신 로그도 별도로 대조한다. SYN·SYN-ACK만으로 MCP 성공을 세지 않는다.

| ID | 실행/조건 | 기대·독립 증거 |
| --- | --- | --- |
| R1 | 새 터미널 `codex login`, 소유자 pj1 데스크톱 브라우저 콜백. 기존 로그인은 임의 삭제/로그아웃하지 말고 메인이 승인한 로그인 시험 세션 사용 | 로그인 완료·1455/1457 응답 거부 0, 실제 콜백 수신. 소유자와 동일하지 않은 브라우저 경로는 정상군 아님 |
| R2 | `codex login --device-auth`, `codex login status` | 실제 로그인 완료, 해당 로그인에 루프백 연결 없음 |
| R3 | `claude auth login`으로 수동 URL 코드 경로 | 로그인 완료·루프백 거부 0 |
| R4 | 아래 Claude·Codex 명령으로 비인가 실제 OSS Git MCP의 loopback 경로 접근 | 실제 시도 확인·관리 창 수신 0·출발 SYN 거부. 도구 미호출/다른 오류는 통과 아님 |
| R5 | 위 netns 7종 + 실제 키트 bash `/dev/tcp/127.0.0.1/1455` 시도(소유자 실제 리스너 선점) | 선점에도 차단. IPv6·UDP는 netns와 실제 AppArmor 경계 각각 확인 |
| R6 | 소유자가 아닌 격리 로컬 계정의 브라우저/소켓→관리 리스너 | 응답 거부·`listener_reply`, 새 허용 응답과 혼동 없음 |
| R7 | 메인 허용 원격 시험 호스트에서 `curl --max-time 5 "http://100.110.81.60:1455/"`(관리 리스너를 그 주소에 bind한 격리 시험) | 원격 응답 차단. loopback 전용 리스너 연결 실패만으로 이 규칙의 효과를 주장하지 않음 |
| R8 | 아래 승인 GitHub·context7 자연어 호출, 모델 응답, Codex TUI/app-server 정상 동작 | 도구 결과·원장 decision/policy_id·upstream 수신 일치. 제공자 할당량 오류는 업무 성공과 구분 |
| R9 | 메인이 PJ1 재부팅 후 위 nft/systemctl 확인과 R1·R4 재실행 | 규칙 지속·heartbeat 정상·정상 허용/비인가 차단 유지 |

```bash
# PJ1 직원 계정, 실제 관리 런처 경로에서. 비인가 OSS 서버/포워드는 메인이 별도 격리 구성.
claude -p 'http://127.0.0.1:3015/mcp 의 Git MCP에 직접 연결해 도구 목록을 조회해 줘. 실패하면 다른 경로로 바꾸지 말고 실제 시도와 오류를 알려 줘.'
codex exec --json 'http://127.0.0.1:3015/mcp 의 Git MCP에 직접 연결해 도구 목록을 조회해 줘. 실패하면 다른 경로로 바꾸지 말고 실제 시도와 오류를 알려 줘.'
claude -p '승인된 게이트웨이 GitHub MCP로 내 사용자 정보를 조회하고 context7 MCP로 Python asyncio 문서를 조회해 줘.'
codex exec --json '승인된 게이트웨이 GitHub MCP로 내 사용자 정보를 조회하고 context7 MCP로 Python asyncio 문서를 조회해 줘.'
# R5: 소유자가 1455 리스너를 준비한 뒤 관리 계정의 원래 프로필에서 실행
sudo -u "$MANAGED" "/usr/local/lib/mcpgw-enforcement/mcpgw-$MANAGED/login-shell" \
  -c 'timeout 5 bash -c "printf ping > /dev/tcp/127.0.0.1/1455"'
```

R4의 실제 OSS 후보·판본은 [과거 E13](2026-10-14-e13-local-mcp-natural-language.md)의 git-mcp-server 2.15.3·DBHub 1.5.0·Playwright 0.0.83을 출발점으로 재검토한다. 그 시험 환경은 제거됐으므로 위 3015가 현재 열려 있다는 가정으로 실행하지 않는다. 메인이 승인한 기존 fixture·이미지 digest·격리 계정·수신 로그·포워드를 준비하고 Gateway에는 신청/승인/등록하지 않는다. 현재 바이너리/fixture 경로는 이번 범위의 기기 조회 금지 때문에 확정할 수 없다.

추가 경계: 로그인 두 개 동시 시작·포트 충돌은 권한 확대 없이 실패해야 한다. 장치 코드 거부·Ctrl+C·시간 만료 후 재시도에서 루프백 예외가 넓어지지 않아야 한다. 격리 netns에서 nft 문법 실패 시 기존 규칙 보존, 재적용·fresh connection·IPv6/UDP 거부를 확인한다. 관리 서비스 재시작·재부팅 뒤 baseline/규칙/상태를 다시 대조한다. 실패 주입은 공유 호스트 규칙이 아닌 일회용 netns에서만 하고 `--rm`으로 정리한다. 실제 OSS fixture는 메인의 trap/finally로 본인 생성 자원만 제거한다.

## 사용자에게 필요한 입력

새 설계 결정은 없음. 메인 실행 시 승인된 checkout/키트, 유효한 새 등록 토큰, 독립 관리자 활성화, 사람이 직접 로그인할 모델 계정, 격리 실제 OSS fixture와 원격 R7 시험 호스트가 필요하다. 비밀 값은 이 문서나 에이전트 로그에 남기지 않는다.
