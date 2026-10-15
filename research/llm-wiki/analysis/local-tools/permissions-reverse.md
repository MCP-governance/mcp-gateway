# Linux 권한·실행 통제 레퍼런스: 역공학 엔드포인트 대조

- 조사일: 2026-10-14
- 범위: AppArmor 실행 전이·loaded policy 상태, nftables `meta skuid`와 IPv4/IPv6 egress, systemd 서비스 격리, Unix socket 권한과 `SO_PEERCRED`를 현재 `endpoint-agent/enforce-linux.py`, `managed-linux.py`에 매핑했다.
- 수행 수준: 공식 원문과 로컬 코드를 읽은 read-only 조사다. 시스템 설정 수정·root/admin 공격·서비스 기동·실시간 네트워크/소켓/커널 정책 시험은 하지 않았다.
- 중복 조사: wiki 카탈로그·analysis·solutions·experiments에서 `AppArmor`, `nftables/skuid`, `SO_PEERCRED`, systemd hardening 용어를 검색했다. E13에는 실제 관리형 launcher UID/AppArmor/hash/heartbeat 요구가 있고 code-structure에는 AppArmor 관찰이 있으나, 아래 4개 공식 원문과 현재 엔드포인트 공백을 잇는 중복 분석은 찾지 못했다.

## 확인한 공식 원문

| ID | 원문·판본 | 적용에 사용한 내용 | SHA-256 |
|---|---|---|---|
| APPARMOR-EXEC-POLICY | [AppArmor upstream techdoc, `apparmor-4.0`](https://gitlab.com/apparmor/apparmor/-/raw/apparmor-4.0/parser/techdoc.tex); [AppArmor `apparmor.d(5)` 3.0](https://apparmor.net/man/3.0/apparmor.d/) | `ix`/`px`, px environment 주의, securityfs의 loaded label과 mode | `f67fa88c…a544128`; 보조 HTML `af8d183b…8396470` |
| NFT-SKUID-EGRESS | [Netfilter nftables manual](https://netfilter.org/projects/nftables/manpage.html), page says Updated 07/02/2026 | `skuid`는 originating socket UID, local output hook, inet의 IPv4/IPv6 지원, reject | `7d67d796…414cb5e` |
| SYSTEMD-SERVICE-HARDENING | [systemd.exec.xml](https://github.com/systemd/systemd/blob/195a17c59b22f5b0fa626fdb4917107cdc281bac/man/systemd.exec.xml), upstream commit `195a17c59b22f5b0fa626fdb4917107cdc281bac` | ProtectSystem/Home, PrivateTmp, NoNewPrivileges, RestrictAddressFamilies 및 우회/지원 한계 | `10b21a8b…ee524ffd` |
| UNIX-SOCKET-PEER-CREDENTIALS | [Linux man-pages `unix(7)`](https://github.com/mkerrisk/man-pages/blob/ae6b221882ce71ba82fcdbe02419a225111502f0/man7/unix.7), commit `ae6b221882ce71ba82fcdbe02419a225111502f0` | pathname socket DAC/mode/umask, connect 시점 `SO_PEERCRED` snapshot | `b7f555f0…34750b09` |

문서 원문 snapshot, 전체 SHA-256, 읽은 부분은 ignored `.task-local-20261014/reverse/permissions/`에 있다. nftables man page는 문서 자체에 2026-07-02 갱신일이 표기된다. AppArmor upstream tag와 systemd/man-pages commit은 URL과 JSON에 고정했다.

## 구현과 대조한 핵심 공백

### AppArmor profile transition과 확인

`enforce-linux.py`의 `profile()`은 launcher/client/helper에 명시적 `px`를 지정하고 일부 작은 시스템 명령에 `ix`, Codex companion에 `mrix`를 생성한다. `px`는 별도 프로필 없이는 전이를 거부하는 적절한 경계지만 환경 변수를 자동 정리하지 않는다. 같은 파일의 native wrapper는 `clearenv()`를 별도로 수행하므로 두 경로를 함께 검증해야 한다. (원문: AppArmor techdoc 357-372, `apparmor.d(5)` 3625-3630.)

`managed-linux.py:98-119`은 `/sys/kernel/security/apparmor/profiles`에서 기대한 이름에 `(enforce)`가 있는지 확인한다. AppArmor 문서는 이 파일이 kernel에 로드된 프로필 이름과 enforce/complain 모드를 나타낸다고 설명한다. 현재 코드는 이 값의 해시를 제공하지 않는다. `configuration_hashes`도 코드상 네 개 Claude/Codex 관리 설정만 SHA-256으로 만들므로 생성된 프로필 원문이나 특정 프로세스의 실제 label은 증명하지 않는다. 같은 이름/모드로 다른 정책이 적재된 경우를 잡지 못하는 검증 공백이다.

개선 제안은 profile source SHA-256 + AppArmor parser/kernel ABI + load 성공 증거를 저장하고, heartbeat 때 root-owned source hash 및 fresh launcher/harness PID의 `/proc/<pid>/attr/current` label을 기대값과 대조하는 것이다. 이를 kernel 정책의 cryptographic fingerprint나 root attestation이라고 부르면 안 된다. 정상군은 px 전이/예상 enforce labels/실제 process label을 확인하고, 음성군은 profile 제거, 동일 label의 바뀐 policy, unconfined 또는 오라벨 process를 구분해 실패해야 한다. 이 시험들은 실행하지 않았다.

### nftables UID 범위와 loopback

`enforce-linux.py:67-78`은 특정 단일 UID를 `meta skuid`로 고정하고 주소별 `ip`/`ip6`, TCP와 허용 포트만 선허용한 다음 그 UID의 나머지를 reject한다. Netfilter manual에서 `skuid`는 originating socket의 UID이고 output hook은 local process 발신 패킷을 다룬다. `inet`은 IPv4/IPv6를 같은 hook에서 처리할 수 있다. 따라서 이 표는 정확히 그 client UID의 로컬 egress 경로에 한정된다. 다른 UID, forwarded traffic, host 전역 모든 네트워크에 대한 보장은 아니다.

지금 구현은 UID 한 개만 다루며 range selector 동작을 생성/검증하지 않는다. 범위 지원을 늘릴 때는 하한·상한 및 바깥 인접 UID, root·service·65534/특권 UID를 경계 시험해야 한다. `127.0.0.1`과 `::1`은 별도 금지 규칙이 아니라 허용 주소 목록에 들어갈 때만 TCP/지정 포트로 허용되고, 그렇지 않으면 UID-wide reject에 잡혀야 한다. 코드의 기존 `--self-check`는 샘플 IPv4/IPv6와 포트 문자열만 검사하고 kernel 적용/실패 효과는 검증하지 않는다. 관리형 서비스는 root로 동작하므로 이 client UID 규칙으로는 그 서비스 자체의 Gateway outbound가 필터링되지 않는 별도 경계도 있다.

필요한 정상군은 등록 UID의 승인 IPv4/IPv6 Gateway 주소·TCP 포트 통과, 정책으로 의도한 loopback Gateway만 정확히 통과, 설치 직후 ruleset과 현재 kernel JSON baseline 일치다. 음성군은 다른 UID, 127.0.0.1/::1 기본 차단, UDP/다른 포트, 다른 원격 주소 차단, range 경계(향후 range 기능이 생길 때)를 둔다. 이번에는 nft를 실행하거나 packet을 보내지 않았다.

### systemd 서비스 hardening

`managed-linux.py:215-220`의 long-running unit은 root 계정 기본값으로 실행되고 `Restart=always`, `RestartSec=10`, `UMask=0077`만 지정한다. `enforce-linux.py:295-299`의 nft oneshot도 별도 사용자/격리 속성이 없다. systemd 문서는 `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, `NoNewPrivileges`, `RestrictAddressFamilies`를 지원하지만 필요한 kernel/mount namespace가 없으면 격리 항목 일부가 적용되지 않을 수 있다고 설명한다. `NoNewPrivileges`는 이미 root로 실행되는 프로세스의 권한을 낮추지 않고, 요청에 따라 호출하는 외부 IPC 서비스도 통제하지 않는다. Read-only path 옵션은 AF_UNIX socket에 접속/통신하는 행위를 차단하지 않는다. Address-family restriction도 이미 전달된 socket FD, `socketpair()`/io_uring 등을 모두 막는 경계가 아니다.

설계 후보는 전용 service UID와 명시적 state/runtime 경로 권한을 먼저 설계한 뒤, `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ProtectHome=read-only`, `PrivateTmp=yes`, `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6`를 적용하는 것이다. 현재 observer는 사용자 설정을 읽으므로 `/home`을 통째로 가리기보다 읽기 전용 최소 경로 또는 별도 observer로 쪼개야 한다. strict filesystem 사용 시 `/var/lib/mcpgw-managed` state와 `/run` socket 등 필요한 쓰기 경로만 허용목록으로 남긴다. 브로커가 root여야만 한다면 먼저 socket activation/권한 모델과 capability 필요를 재설계해야 한다. unit 내용을 고치거나 적용하지 않았다.

정상군은 Gateway heartbeat, read-only 설정 관찰, token socket 생성/접속이 유지되고 실제 `systemctl show`, `/proc/<pid>/status`, mount view, capability 및 socket-family 제한이 의도와 맞는지다. 음성군은 `/etc`/`/usr` 쓰기, 무관한 home 열람, AF_PACKET 생성, SUID privilege gain이 차단되는지며, AF_UNIX 및 HTTPS가 필요한 구성에서는 유지되는지다. systemd/kernel 버전별 실제 효과를 별도 격리 host에서 확인해야 한다.

### Unix socket과 SO_PEERCRED

`managed-linux.py:226-247`은 root service에서 AF_UNIX stream socket을 만들고 사용자 UID/GID로 `chown`, `0600`으로 `chmod` 한 뒤 연결 peer의 `SO_PEERCRED` UID만 config UID와 비교한다. man-pages는 pathname socket permission을 Linux가 적용하며, `SO_PEERCRED`는 연결 시점의 peer credential snapshot이라고 명시한다. PID/GID/실행파일 identity를 검증하는 메커니즘은 아니다. 동일 UID가 공유 principal인 모델에서는 자연스러운 선택이며, 동일 UID 프로세스 간 분리는 이 코드만으로 주장할 수 없다. AppArmor의 client-side peer-label rule은 별도 추가 경계지만, broker 쪽에서 label을 읽는 코드는 확인되지 않았다.

개선 판단은 같은 UID 전체를 한 principal로 정의할지부터 해야 한다. per-process identity가 요구되면 전용 service/client UID, label-aware peer check(배포 커널 지원 확인), AppArmor peer rule을 결합하고 PID 단독 신뢰는 피한다. 정상군은 올바른 UID·socket owner/mode·approved profile·활성 cache 조합에서만 토큰 응답, 음성군은 다른 UID, inactive/expired cache, TCP 접속, 미승인 peer label을 구분한다. 같은 UID/허용 label은 현재 설계상 접속 가능한 정상 shared-principal 조건임을 기록한다. 실제 socket probe는 미실행이다.

## 적용 한계와 범위

Codex 검수: 현재 `managed-linux.py.checks()`는 `nft`로 kernel table을 조회하므로, 이 구성 그대로 `RestrictAddressFamilies`를 적용할 때는 `AF_NETLINK`도 검토해야 한다. AF_UNIX/AF_INET/AF_INET6만 허용하는 제안을 현재 root 서비스에 그대로 적용하면 heartbeat 점검을 깨뜨릴 수 있다. 전용 UID로 낮추는 변경도 nft 조회·kernel journal·사용자 설정 접근과 정책 파일 쓰기의 권한을 먼저 분리해야 한다. 이 제안은 적용하지 않았다.

이 레퍼런스는 설계공백 및 다음 시험 기준이다. systemd hardening/profile load/nft kernel rules/socket credential 검증을 수행하지 않았고, root/admin 공격이나 설치 상태를 증명하지 않았다. 권한 있는 kernel/root는 이 endpoint 범위의 공격자로 다루지 않았다. 구현 제안 또한 service identity, observer 데이터 접근, credential 보관 모델을 함께 설계하고 격리된 Linux 시험기에서 먼저 검증해야 한다.
