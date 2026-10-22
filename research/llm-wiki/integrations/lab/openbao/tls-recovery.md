# OPS-TLS-RECOVERY-R2 — OpenBao 인증서 만료 복구 제안

2026-10-22, 기준 `73dfad7884ce3458baeb43ec2fff83ffabd62394`. 로컬 소스 검토·격리 검사만 수행한다. **조정자의 독립 Gemini 검토와 Claude 판단 전에는 통합하지 않는다.** 아래 기기 명령은 운영자가 별도 승인 후 수행할 절차이며 이 작업에서 실행하지 않았다.

## 사건과 인증서 경계

- 사용자 관측: 2026-10-22 12:51 KST, `mcpgw-interop-20261013-openbao-1` unhealthy. `bao status`의 인증서 검증 오류에 `2026-10-20T12:23:18Z` 만료가 보고됐다. 원격 재확인·실제 leaf fingerprint 대조는 미실행이다.
- 내부 OpenBao: `server.hcl`의 `/openbao/tls/server.pem`, `server.key`; `prepare.py`가 만드는 별도 `tls/ca.pem`으로 검증한다. healthcheck는 컨테이너의 `127.0.0.1:8200`에 접속한다.
- interop 외부: Caddy `tls internal`의 `:8448/:8449` 인증서는 위 OpenBao CA와 별개다. `:8449`의 upstream만 OpenBao CA를 신뢰한다.
- 제품 외부 HTTPS: 실제 접속한 URL·포트·leaf·체인·클라이언트 신뢰가 별도 확인 대상이다. Windows Schannel `0x80096004`만으로 만료 또는 OpenBao와 같은 인증서라고 판정하지 않는다.

## 현재 구현에서 확인한 수명

| 근거 (위 기준 commit) | 사실 / 한계 |
| --- | --- |
| `openbao/prepare.py:27-50` | 새 runtime만 허용. CA 30일, server 7일, 음성 시험 wrong CA 7일. 기존 디렉터리 재실행으로 갱신 불가 |
| `openbao/server.hcl:11-19` | TLS 1.3, 파일 경로 고정, ACME 꺼짐. 자동 파일 reload 설정 없음 |
| `openbao/compose.openbao.yaml:3-31` | 판본·digest 고정, `/usr/bin/bao` 직접 entrypoint 설정. TLS 디렉터리 read-only mount, healthcheck는 검증하는 `bao status`. 실제 PID1은 미확인 |
| `provision_appliance.py:11,46-49` | 기본 runtime은 `/home/user/mcpgw-interop-lab-20261013/openbao/runtime`. 복사는 갱신 구현이 아님 |
| `Caddyfile:13-19` | backend 신뢰 파일은 OpenBao 공개 CA. 외부 Caddy CA와 분리 |

확인한 준비·배치·listener 파일에 재발급 스케줄러/명령은 없다. 실행 중인 기기의 별도 자동화 부재까지 입증한 것은 아니다. `full_stack_lab/interop`는 이 체크아웃에 없다. 기존 bootstrap/SDK check는 init·unseal·secret 읽기/쓰기·token 발급/철회를 포함하므로 TLS 복구 확인에 실행하지 않는다.

## 읽기 전용 만료 검사

운영자가 실제 mount와 public 파일 경로를 확인한 뒤 솔루션 기기에서 실행한다. 아래 경로는 소스 기본값이며 기기 증거로 확정한 값이 아니다.

```bash
cd /home/user/mcpgw-interop-lab-20261013
python3 openbao/check_expiry.py --tls-dir /home/user/mcpgw-interop-lab-20261013/openbao/runtime/tls
```

`server.pem`·`ca.pem`만 OpenSSL로 읽는다. 기본 48시간 여유, `notBefore` 미래·현재 만료·경계 포함 임박·누락·파싱/실행/timeout 오류는 종료 1이다. 정상 두 파일만 종료 0, 인자 오류는 2다. JSON은 검사 시각·역할별 UTC 기간·상태만 포함한다. `wrong-ca.pem`은 음성 시험용이므로 감시 대상에서 제외한다.

이 검사는 파일 유효기간만 판정하며 신뢰·서명·SAN·키 일치·실제로 제공 중인 인증서·health를 증명하지 않는다. 출력 파일이 정상이어도 아래 검증을 생략하지 않는다. 7일 leaf 수명 때문에 운영자 감시는 적어도 매일 실행하고 종료 1/2를 장애로 처리한다. 자동 작업 설치·경보 연결은 이번 범위 밖이다.

## 운영자 확인 단계 — 아직 실행하지 않음

1. 대상 container의 프로젝트·mount·image digest·PID1 실행 명령을 보호된 현장에서 확인한다. 일반 `docker inspect` 전체·Compose 환경 전체·로그 전체를 보고서로 내보내지 않는다. 배치 파일 두 개와 실제 runtime이 위 기본값과 다르면 아래 명령을 실행하지 않는다.
2. 신뢰된 UTC 시각, 현재 CA·leaf의 `-noout -dates -fingerprint -sha256`, SAN(`-noout -ext subjectAltName`)을 비교한다. 인증서 본문·키·환경·비밀 파일은 출력하지 않는다. 현재 leaf의 만료와 사용자 보고가 일치하는지 기록한다.
3. 기존 공개 CA의 승인된 fingerprint와 일치하는지 확인한다. CA 만료·임박, signer/CSR 누락, 키 일치 불명, 실제 판본 불일치는 중단 조건이다. 신뢰 루트 교체·새 runtime·재초기화로 우회하지 않는다.
4. 별도 승인된 보호 백업/기존 운영 절차가 준비돼야 다음 단계로 넘어간다. 이 문서는 init/unseal·자격 복구 절차를 제공하지 않는다.

## 운영자 유지보수 단계 — 승인 후 기존 CA·키 유지

이 블록은 **제안이며 실행하지 않았다**. 운영자가 정확한 mount·소유권과 기존 CSR/CA의 무결성을 검증하고 서명 권한을 승인받은 경우만 수행한다. root가 로컬 보호 파일을 처리하며 키 내용은 열람·출력하지 않는다. 서비스 재시작은 사용하지 않는다.

```bash
set -euo pipefail
cd /home/user/mcpgw-interop-lab-20261013
runtime=/home/user/mcpgw-interop-lab-20261013/openbao/runtime
test -d "$runtime/tls"
test ! -L "$runtime/tls"
# 새 leaf 7일보다 CA가 하루 이상 더 유효해야 한다.
openssl x509 -in "$runtime/tls/ca.pem" -noout -checkend 691200
openssl req -in "$runtime/private/server.csr" -noout -verify
csr_public=$(openssl req -in "$runtime/private/server.csr" -noout -pubkey | openssl pkey -pubin -outform DER | openssl dgst -sha256)
leaf_public=$(openssl x509 -in "$runtime/tls/server.pem" -noout -pubkey | openssl pkey -pubin -outform DER | openssl dgst -sha256)
test "$csr_public" = "$leaf_public"
```

기존 `private/server.ext`가 준비 코드의 SAN 세 개(`openbao`, `localhost`, `127.0.0.1`), `serverAuth`, `CA:FALSE`와 일치하는지 보호된 현장에서 확인한다. 기존 서버 키와 CSR의 공개키 일치는 보호된 운영 절차로 추가 확인한다. 불일치 시 새 키 생성으로 진행하지 않는다.

```bash
# 새 디렉터리를 먼저 예약하므로 기존 stage를 덮어쓰지 않는다.
umask 077
stage="$runtime/tls/.recovery-20261022"
mkdir -m 700 "$stage"
serial=$(openssl rand -hex 16)
openssl x509 -req -in "$runtime/private/server.csr" -CA "$runtime/tls/ca.pem" -CAkey "$runtime/private/ca.key" -set_serial "0x$serial" -out "$stage/server.pem" -days 7 -sha256 -extfile "$runtime/private/server.ext"
openssl verify -CAfile "$runtime/tls/ca.pem" -purpose sslserver -verify_hostname openbao "$stage/server.pem"
openssl verify -CAfile "$runtime/tls/ca.pem" -purpose sslserver -verify_hostname localhost "$stage/server.pem"
openssl verify -CAfile "$runtime/tls/ca.pem" -purpose sslserver -verify_ip 127.0.0.1 "$stage/server.pem"
openssl x509 -in "$stage/server.pem" -noout -checkend 172800
new_public=$(openssl x509 -in "$stage/server.pem" -noout -pubkey | openssl pkey -pubin -outform DER | openssl dgst -sha256)
test "$new_public" = "$csr_public"
cp -p "$runtime/tls/server.pem" "$stage/server.previous.pem"
chown 10000:10000 "$stage/server.pem"
chmod 644 "$stage/server.pem"
mv "$stage/server.pem" "$runtime/tls/server.pem"
```

stage와 최종 파일은 같은 mount 안에서 rename한다. 기존 CA·server.key·data·roles·tokens는 변경하지 않는다. 중간 실패에서는 중단하고 stage를 보존한다. UID/GID는 저장소 Compose의 값이며 실기기가 다르면 적용하지 않는다.

OpenBao [공식 TCP listener 문서](https://openbao.org/docs/configuration/listener/tcp/)는 시작 시 지정한 같은 인증서 경로를 SIGHUP으로 다시 읽는다고 명시한다. 이는 재발급 기능이 아니다. 실기기 2.7.1의 reload 안전성은 미검증이며 [2.5.0 SIGHUP crash 보고](https://github.com/openbao/openbao/issues/3138)도 있어, **독립 검토에서 고정 판본 reload 경로와 대상 PID1을 확인할 때까지 signal을 보내지 않는다**. 확인·승인 후 대상은 `docker kill --signal=HUP mcpgw-interop-20261013-openbao-1` 하나뿐이다. 재시작이나 unseal로 대체하지 않는다.

reload 전에 실패하면 보존한 이전 파일을 같은 경로에 atomic restore한다. 이미 만료된 이전 파일 복원은 TLS 복구 성공이 아니다. reload 후 실패하면 현상·보호된 진단 증거를 유지해 운영자에게 인계하고 재시작·unseal·CA 교체·검증 비활성화로 진행하지 않는다.

## 적용 후 독립 합격 조건 — 운영자가 기록

- 파일: 위 expiry check 종료 0, CA fingerprint 불변, leaf fingerprint 갱신.
- 실통신: loopback 18200을 기존 CA·IP SAN·TLS 1.3으로 검증한다. 예: `openssl s_client -connect 127.0.0.1:18200 -verify_ip 127.0.0.1 -CAfile "$runtime/tls/ca.pem" -verify_return_error -tls1_3 -brief </dev/null`. leaf fingerprint도 별도 대조하고 파일만의 성공과 구분한다.
- 상태: `docker exec mcpgw-interop-20261013-openbao-1 /usr/bin/bao status -format=json`은 인증 불필요다. 종료 0의 active/unsealed를 확인한다. 종료 2의 sealed는 TLS 성공이어도 복구 미완료로 중단하고 unseal하지 않는다. container health 정상 복귀도 별도 확인한다.
- interop `:8449`: 기존 승인된 **Caddy 외부 CA**와 올바른 hostname/IP로 TLS·backend 도달을 확인한다. OpenBao CA를 외부 client root로 대용하지 않는다.
- 제품 HTTPS/Windows: 정확한 URL·포트, 검증을 켠 Schannel 결과, 공개 leaf의 기간·issuer·fingerprint와 체인 검증 결과를 독립 기록한다. `0x80096004`가 남으면 별건으로 다루고 root 교체·TLS 검증 비활성화는 하지 않는다.

## 참조와 확인 범위

확인일 2026-10-22. [OpenSSL x509 공식 문서](https://docs.openssl.org/3.0/man1/openssl-x509/)의 `-dates`/`-checkend`와 OpenBao 2.7.x listener 문서의 reload 절을 확인했다. 위 reload 장애는 구판 issue이며 2.7.1 적용 여부는 미확인이다. 기존 [provenance](provenance.json)는 OpenBao 2.7.1 commit `a5db72cef75c24b920ade02065b18dd8eb666bac` / MPL-2.0을 기록하지만 이번 고정 source URL 조회는 실패해 고정판 reload 구현을 읽지 못했다. 공개 GitHub 관련 skill/OSS 탐색에서 채택할 판본 고정 skill을 확보하지 못해 외부 스크립트는 채택·실행하지 않았다. 새 의존성·비밀 저장소·자동 renewer는 추가하지 않는다. 실행 검사와 한계는 [작업 보고](../../../status/reports/2026-10-22-ops-tls-recovery-r2.md)에 기록한다.

## OPS-TLS-RELOAD-SOURCE 후속 — 고정 구현 확보 차단

2026-10-22, 로컬 기준 `ca368bff78b12608b132bdc98851b035bce542b6`, 기존 `10/22-runtime-recovery` 유지. 공식 공개 자료와 아래 로컬 파일만 대조했다. **고정 reload 구현을 확보하지 못했으므로 signal 적용 보류를 해제하지 않는다.** 이전 검토 PASS는 이 후속의 소스·실기기 검증을 뜻하지 않는다.

### 판본·출처와 실제 읽은 범위

- [공식 v2.7.1 릴리스](https://github.com/openbao/openbao/releases/tag/v2.7.1)의 tag와 commit 표시 `a5db72c`를 확인했다. 전체 commit `a5db72cef75c24b920ade02065b18dd8eb666bac`는 기존 provenance의 값이며, 이번 공개 소스 본문으로 독립 재확인하지 못했다.
- [고정 Dockerfile URL](https://raw.githubusercontent.com/openbao/openbao/a5db72cef75c24b920ade02065b18dd8eb666bac/Dockerfile)의 기존 보존본 [Dockerfile.raw.txt](evidence/Dockerfile.raw.txt)에서 `USER` L48-49, `COPY`·`ENTRYPOINT` L51-54를 읽었다. 기본 이미지는 `docker-entrypoint.sh`를 지정하며, 주석은 dumb-init을 설명한다. 스크립트 본문·signal 전달 구현은 미확보다. SHA-256 `2aab522e524ca90e3342cb31f53668d6ff517e920c609732477c4e3e6c7cc826`은 provenance와 일치했다.
- 라이선스는 [고정 LICENSE URL](https://raw.githubusercontent.com/openbao/openbao/a5db72cef75c24b920ade02065b18dd8eb666bac/LICENSE)의 기존 보존본 [LICENSE.raw.txt](evidence/LICENSE.raw.txt) L1-3의 MPL-2.0 표기다. SHA-256 `d6b1a865f1c8c697d343bd4e0ce61025f91898486a1f00d727f32e8644af77d3`은 provenance와 일치했다. 소스를 새로 복제·실행·재배포하지 않았다.
- 로컬 [Compose](compose.openbao.yaml) L3-6은 이미지 digest·사용자·직접 entrypoint와 server 인자, L20-23은 mount, L26-31은 healthcheck다. [listener](server.hcl) L11-19는 cert/key 경로·TLS 1.3·ACME 비활성이다. 이 설정대로 생성됐다면 기본 스크립트를 대체하는 구성이라는 해석이며, 실제 기기의 Compose override·init·PID1·실행 image 증거는 아니다. `restart: unless-stopped`(L7)도 있어 프로세스 종료를 무중단 reload 실패로 취급할 수 없다.

### 고정 source 확보 실패 기록

| 공식 URL / 접근 | 실제 결과 | 확인하지 못한 것 |
| --- | --- | --- |
| [commit의 listenerutil/listener.go raw](https://raw.githubusercontent.com/openbao/openbao/a5db72cef75c24b920ade02065b18dd8eb666bac/internalshared/listenerutil/listener.go), PowerShell `Invoke-WebRequest` (20초 제한) | 원격 서버 연결 실패 | 본문·경로 존재 여부 |
| 같은 raw URL, 공개 웹 조회 | Cache miss | 본문·행·기호 |
| [같은 commit의 GitHub blob](https://github.com/openbao/openbao/blob/a5db72cef75c24b920ade02065b18dd8eb666bac/internalshared/listenerutil/listener.go) | Cache miss | 본문·행·기호 |
| [tag의 command/server.go raw](https://raw.githubusercontent.com/openbao/openbao/v2.7.1/command/server.go) | 조회 도구가 404 Not Found 반환 | 경로 이동·자료 접근 문제와 실제 부재를 구분 불가 |
| [공식 tag tree](https://github.com/openbao/openbao/tree/v2.7.1), 릴리스 링크에서 조회 | Cache miss | 고정 트리·실제 reload 파일 경로 |

위 결과는 기능 부재의 증거가 아니다. 이 범위에서 재시도를 중단했다. reload 등록·signal dispatch·인증서/키 파싱·캐시 교체·오류 반환/로그·audit reload의 **2.7.1 기호와 행은 모두 미확보**다. 현재 main 소스나 구판 stack trace로 대신하지 않았다.

### 조건별 판단 — 문서 지원과 구현 보증 분리

공식 [TCP listener 문서](https://openbao.org/docs/configuration/listener/tcp/)의 `tls_cert_file`·`tls_key_file`·`tls_auto_reload` 절(조회 화면 L108-113)을 읽었다. 이는 변경 가능한 현재 문서이며 고정 v2.7.1 소스 증거가 아니다.

| 조건 | 지원되는 판단 / 적용 한계 |
| --- | --- |
| 시작 시 경로에 새 PEM을 놓고 같은 키·승인 CA를 유지 | 문서는 SIGHUP 재독해를 지원한다. 재발급·검증 성공과 reload 성공은 별개이며, 2.7.1 무중단 안전성은 보증하지 못함 |
| 실행 중 HCL의 cert/key 경로만 변경 | 문서는 시작 시 경로를 다시 사용한다고 명시. 경로 변경을 reload 복구 방법으로 사용하지 않음 |
| 암호화 키의 passphrase 변경 | 문서는 reload 간 같은 passphrase를 요구. 변경하는 복구는 지원 전제 밖 |
| 누락·권한 오류·잘못된 PEM·키 불일치·만료 leaf | 2.7.1의 반환 오류·기존 인증서 보존·프로세스 생존 여부 미확인. 안전한 실패를 가정하지 않고 적용 보류 |
| 파일 rename 또는 파일 기간 검사만 성공 | 실제 제공 leaf 교체·연결 성공·health 복귀를 입증하지 못함 |
| 자동 reload 기대 | 현재 문서는 별도 `tls_auto_reload` 옵션을 설명하지만 로컬 listener는 설정하지 않음. 기기 활성화나 2.7.1 구현을 추정하지 않음 |
| SIGHUP의 인증서 외 영향 | [issue #3138](https://github.com/openbao/openbao/issues/3138)는 2.5.0 `Core.ReloadAuditLogs`·`MountTable.shallowClone` crash 제보이고 Closed/`cannot reproduce` 표시다. 제보의 기호·행은 2.7.1 소스 검사 결과가 아니며, 해결·잔존 어느 쪽도 입증하지 않음 |

### 다음 운영자 확인 — 하나만

운영자가 대상 컨테이너의 **실제 PID1 실행 경로와 server 인자**를 읽기 전용으로 확인해 로컬 Compose L5-6과 대조하고, 민감 값 없이 일치 여부를 기록한다. 이 확인만으로 고정 구현 공백이 해소되거나 signal이 승인되지는 않는다. 이 작업에서는 기기 접속·컨테이너 호출·signal·인증서/비밀 읽기를 하지 않았다.

후속 상태: `WORK_STATUS: BLOCKED` — 고정 release reload 본문 미확보, 실기기 PID1 미검증.
