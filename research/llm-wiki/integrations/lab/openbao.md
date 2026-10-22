# OpenBao 실제 secret 연동 환경

확인일 2026-10-13. 사용자의 자체 구축 지시에 따라 기존 제품과 분리한 솔루션 기기 lab에 공식 OpenBao를 구성한다. 이 문서 작성 시 서버/SDK 실행은 미검증이고, 실제 기기의 공식 image에서 읽기 전용 one-shot으로 기본 UID100/GID1000만 확인했다. 테스트 MCP나 secret backend를 자체 구현하지 않는다.

## 판본과 저장·통신

[OpenBao2.7.1 정식 release](https://github.com/openbao/openbao/releases/tag/v2.7.1)는 2026-10-01 공개, source commit `a5db72cef75c24b920ade02065b18dd8eb666bac`, MPL-2.0이다. 공식 GHCR index digest `6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf`와 linux/amd64 manifest `a36ea8c27f0dcff5757664ad080425f96d3b6b2f33db3e76c4e2d3112fb17005`를 registry 응답 bytes와 대조했다. 실제 pull/실행 image와 서명 검증은 별도다.

2.7에서 `file` backend가 삭제돼 [공식 PebbleDB](https://openbao.org/docs/configuration/storage/pebbledb/)를 사용한다. `:memory:`가 아닌 보호 directory에 영속 저장한다. 기존 data를 migration/reset하지 않으며 node 하나만 사용한다. backend 변경 이유는 [공식2.7 release notes](https://openbao.org/community/release-notes/2-7-0/)에 있다.

[구성](openbao/server.hcl)은 TLS1.3·인증서 검증·ACME 비활성·UI 비활성이고 dev-mode를 사용하지 않는다. 컨테이너는 명시 UID10000/GID10000, rootfs 읽기 전용, capability 제거, 별도 data/logs만 쓰기 허용이다. OpenBao2.x의 mlock 제거 때문에 IPC_LOCK을 추가하지 않는다. [TCP listener 정본](https://openbao.org/docs/configuration/listener/tcp/)과 실제 판본의 동작을 배포 시 대조한다.

컨테이너 내부 `openbao:8200`은 별도 internal `secret_edge` 망이다. host는 `127.0.0.1:18200`만 게시한다. lab Caddy가 public CA를 `/etc/caddy/openbao-ca.crt`로 읽고 TLS backend를 검증한다. OpenBao CA key나 unseal 자료를 Caddy/PJ1/LLM에 공유하지 않는다. 외부 lab frontend의 CA와 OpenBao backend CA는 서로 다른 역할이다.

## 준비와 초기화

[overlay](openbao/compose.openbao.yaml)는 [lab 기본 Compose](compose.yaml)와 취합한다. 이 lab 외 field Compose에는 얹지 않는다. 모든 Compose 명령은 `-p mcpgw-interop-20261013`과 정확한 두 파일을 명시한다. `OPENBAO_CONFIG_DIR`는 기기의 절대 config directory, `OPENBAO_RUNTIME_DIR`는 Git 밖의 **새 directory**다.

1. 솔루션 기기에서 `sudo -n python3 prepare.py --runtime-dir 새절대경로 --owner-uid 실제운영자UID --owner-gid 실제운영자GID`로 준비한다. 부모 directory는 운영자가 먼저 만들며 기존 runtime이면 거부한다. 이 명령은 인증서·권한만 만들고 서비스는 시작하지 않는다.
2. `OPENBAO_CONFIG_DIR`와 `OPENBAO_RUNTIME_DIR`를 설정하고 해당 lab의 OpenBao만 `up -d openbao`한다. sealed 단계의 healthcheck 실패를 오류 없이 초기화됐다고 해석하지 않는다.
3. lab Docker network의 **실제 source CIDR**를 확인한다. 제안 `172.29.213.0/24`는 기존 망과 충돌하지 않는지 먼저 검사하고 root가 설정한다. role의 CIDR을 임의 `127.0.0.1`로 고정하지 않는다.
4. 별도 venv에 [hash lock](openbao/requirements.lock)을 `python -m pip install --require-hashes -r requirements.lock`으로 설치한다. 공식 hvac2.4.0 API를 사용한다. 전이 package metadata도 [SDK 판본](openbao/sdk-provenance.json)에 보존한다.
5. `python sdk_lab.py bootstrap --ca RUNTIME/tls/ca.pem --private-dir RUNTIME/private --bound-cidr 실제CIDR`를 실행한다. `--seed-secret-file`로 새 제한 LiteLLM 시험 key의 보호 파일을 선택할 수 있다. 미지정이면 합성 값이고 실제 모델 인증 성공으로 세지 않는다.

init/unseal은 [공식 hvac system API](https://python-hvac.org/en/stable/usage/system_backend/init.html)로 수행한다. 처음 받은 Shamir share/root token은 owner-only `private/init-operator.json`에만 기록한다. 파일 mode0600, directory0700을 강제하며 stdout·shell 인자·환경에 token을 넣지 않는다. 초기 설정 후 별도 orphan 제한 operator(2h, 최대4h)를 발급하고 bootstrap root를 revoke-self한 뒤 파일의 root token을 제거한다. root 회수 후 operator가 유효한지도 확인한다. 재시작의 unseal share는 보호 파일에 남는다.

초기화됐는데 자신의 init 파일이 없는 경우나 기존 operator 파일이 있는 부분 실패에서는 중단하고 상태를 보존한다. 자동 reset·재초기화·볼륨 삭제는 없다. 실패 예외 원문/응답을 공개하지 않고 error type만 보고한다. 이 lab의 Shamir1/1과 운영자 한 명의 share 보관은 운영용 key ceremony를 충족하지 않는다.

## 제한된 역할과 시험

[app policy](openbao/app-read.hcl)는 `integration/litellm`과 `integration/smoke` 두 KVv2 경로의 read만 허용한다. AppRole SecretID는1회·10m, workload token은5m·최대10m·실제 lab CIDR로 제한한다. [operator policy](openbao/operator.hcl)는 이 lab prefix와 역할만 관리하며 `sys/*`·임의 mount·일반 secret 관리자 권한이 없다. Vault 호환 `/v1` API와 `X-Vault-Token`은 OpenBao 실제 API/official hvac로 확인하며 모든 Vault 기능의 호환성으로 확대하지 않는다. [AppRole 정본](https://openbao.org/docs/auth/approle/) · [SDK AppRole](https://python-hvac.org/en/stable/usage/auth_methods/approle.html) · [KVv2 SDK](https://python-hvac.org/en/stable/usage/secrets_engines/kv_v2.html).

`python sdk_lab.py check --ca RUNTIME/tls/ca.pem --private-dir RUNTIME/private`는 실제 TLS·AppRole 로그인·KVv2 read, 존재하는 다른 경로403, workload 쓰기403, 사용한 SecretID 재사용 거부, wrong CA 실패, 최신 version 회전·stale CAS 거부·smoke 값 원복, token accessor 회수 후 재읽기403을 검사한다. CAS로 자기 smoke 값만 원복하고 역사·감사 기록은 삭제하지 않는다. SDK 결과는 값 대신 boolean/판본만 출력한다.

CLI 교차 확인은 공식 `bao`의 `version`, 인증 불필요 `status -format=json`, `operator init -status`와 일치시킨다. credential이 필요한 CLI 호출은 token helper/보호된 파일을 통해 처리한다. `bao operator init` 원문·`bao login TOKEN`·`bao write ... secret_id=값`·`curl -H X-Vault-Token:값`을 공개 도구 출력/명령 인자에 쓰지 않는다. 초기화는 SDK 스크립트 한 경로로만 수행한다.

## 남은 검증

- 2026-10-22 만료 관측의 [복구 제안·공개 파일 만료 검사](openbao/tls-recovery.md)를 추가했다. 로컬 회귀만 통과했으며 실제 복구와 고정판 reload 안전성은 미확인이다. 조정자의 독립 검토 전 적용하지 않는다.

- 실제 server/SDK 시작·결과·image digest·TLS fingerprint·독립 audit request IDs는 root 배포 결과로 추가한다. source/config 준비를 실행 통과로 올리지 않는다.
- TTL 실제 만료·CIDR 밖 login/token 거부·sealing/outage·retry/fail-closed·소비자 cache 회전·accessor 철회·재시작 영속성은 후속 케이스다. 현재 SDK check는 기다려서 TTL 만료를 검증하지 않는다.
- OpenBao KV 값 갱신은 해당 LiteLLM virtual key/provider credential의 자동 철회가 아니다. 양쪽 정책·cache·직접 재접근을 따로 시험한다.
- HA/quorum·auto-unseal/HSM/KMS·정식 PKI·백업/복구·DR·감사 외부 전송/보존·key ceremony·운영 부하·SOC/기업 인증은 미완료다. PebbleDB 한 node를 기업 운영 HA로 제공하지 않는다.

원복은 이 새 lab의 자기 token·역할·연결·합성 자원만 대상으로 한다. 기존 field·다른 Docker 프로젝트·기존 PAT·계정·CA·volume은 변경하지 않는다.
