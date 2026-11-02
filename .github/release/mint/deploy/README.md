# MINT 운영 설치 및 관리

이 문서는 MINT 1.0.0을 조직의 서버에 설치하고 운영하는 관리자를 위한 안내입니다. 아래 명령은 별도 표시가 없으면 `mint/deploy`에서 실행합니다.

## 설치 전 준비

| 항목 | 요구 사항 |
| --- | --- |
| 서버 | Linux x86-64, 4 vCPU, 메모리 16 GB, 디스크 40 GB 기준 |
| 소프트웨어 | Docker Engine 24 이상, Docker Compose v2 플러그인, Git, OpenSSL, Python 3. MINT 전용 Docker 데몬과 이에 접근할 권한이 필요합니다. 다른 배포의 MCP 실행 환경과 데몬을 공유하지 않습니다. 기동 시 `mcpgw.runtime` 라벨이 있는 컨테이너와 네트워크를 제거할 수 있습니다. |
| 네트워크 | 직원 PC가 접속할 수 있는 서버의 사내 IPv4와 이미지 빌드·도입 심사에 필요한 인터넷 연결을 준비합니다. `0.0.0.0`과 loopback 주소는 사용할 수 없습니다. |
| 수신 포트 | 지정한 IPv4의 TCP 443은 HTTPS 콘솔·MCP·인증에 사용합니다. TCP 3128은 관리형 PC의 모델 프록시에 사용하며 `MODEL_PROXY_PORT`로 변경할 수 있습니다. 필요한 PC만 접근하도록 방화벽을 설정합니다. |
| 내부 네트워크 | 기본 Docker 네트워크는 `10.246.1.0/24`, `10.246.3.0/24`, `10.246.4.0/24`, `10.246.5.0/24`, `10.246.6.0/24`, `10.246.9.0/24`, `10.246.11.0/24`를 사용합니다. 조직의 네트워크와 겹치면 `.env`의 `MINT_NET_PREFIX`를 변경합니다. |

## 설치와 첫 로그인

```bash
git clone --branch v1.0.0 https://github.com/MCP-governance/mint.git
cd mint/deploy
./install.sh --bind <사내 IPv4>
```

설치기는 `.env.example`을 `.env`로 복사하고 비어 있는 비밀 값과 서명 키를 생성합니다. 기존 `.env`와 키는 유지합니다. 이미지를 빌드하고 서비스를 기동한 뒤 루트 인증서와 지문을 내보냅니다. 설치 전에 설정을 바꾸려면 `.env.example`을 `.env`로 복사하고 필요한 값을 수정한 다음 설치합니다. `.env`는 비밀 값을 포함하므로 접근 권한을 제한하고 안전하게 백업합니다.

| 설치 옵션 | 설명 |
| --- | --- |
| `--bind <IP>` | 서비스가 게시될 서버의 사내 IPv4입니다. 기존 `.env`에 값이 없으면 지정해야 합니다. |
| `--name <DNS 이름>` | 사설 CA 인증서에 추가할 DNS 이름입니다. 직원 PC의 기본 연결 주소는 IP입니다. |
| `--console-tls none\|tailscale\|file` | 콘솔 인증서 방식입니다. 기본값은 `none`입니다. |
| `--console-name <DNS 이름>` | `tailscale` 또는 `file` 방식의 콘솔 DNS 이름입니다. 포트와 경로는 넣지 않습니다. |
| `--console-cert <절대 경로>` | `file` 방식의 PEM 인증서 체인 파일입니다. |
| `--console-key <절대 경로>` | `file` 방식의 PEM 개인 키 파일입니다. |

설치 시 기본 비밀번호가 남은 `root`의 비밀번호는 HTTPS 게시 전에 임의 값으로 변경되어 `initial-admin-password`에 저장됩니다. 기본 비밀번호가 남은 `user`, `admin1`, `admin2`, `admin3` 계정은 중지됩니다. 기존에 변경한 `root` 비밀번호는 유지합니다.

1. 아래 사설 CA 절차에 따라 브라우저에서 인증서를 신뢰하도록 설정합니다. 이름 기반 인증서를 사용하면 해당 인증서의 신뢰도 확인합니다.
2. `https://<사내 IPv4>/` 또는 설정한 콘솔 DNS 주소에 접속하고 `root`와 `initial-admin-password`의 값으로 로그인합니다.
3. 서버에서 `./mint.sh set-password root`를 실행해 12자 이상의 비밀번호로 변경합니다. 변경이 성공하면 초기 비밀번호 파일이 삭제됩니다.
4. `./mint.sh status`에서 준비 여부와 정책 일치를 확인하고, 독립 승인을 담당할 관리자를 추가합니다.

## 콘솔 인증서

| 방식 | 설정과 조건 |
| --- | --- |
| `none` | 기본 방식입니다. IP HTTPS에 MINT의 사설 CA를 사용합니다. `--name`을 지정하면 해당 이름도 사설 인증서에 포함합니다. |
| `tailscale` | `--console-name`에 `.ts.net` 이름을 지정합니다. 서버에서 Tailscale HTTPS를 활성화하고 로컬 데몬 소켓을 사용할 수 있어야 합니다. `--bind`는 그 서버의 실제 Tailscale IPv4여야 합니다. |
| `file` | `--console-name`, `--console-cert`, `--console-key`를 지정합니다. 이름에 맞는 조직 발급 PEM 체인과 키를 사용합니다. 키 권한은 `0400`, `0600`, `0640` 중 하나여야 하며 콘솔 프로세스가 읽을 수 있어야 합니다. 파일과 상위 경로는 root 또는 실행 사용자 소유이고 그룹·기타 사용자에게 쓰기 권한이 없어야 하며 심볼릭 링크를 사용할 수 없습니다. |

이름 기반 콘솔 주소가 서버의 지정 IP를 가리키도록 DNS를 설정합니다. `tailscale`과 `file`을 사용해도 직원 PC의 MCP·인증 연결은 IP와 MINT 사설 CA를 사용합니다. 인증서나 `.env`를 변경한 뒤 `./mint.sh up`을 실행합니다. `file` 방식의 개인 키는 저장소 밖에 안전하게 보관하고 별도로 백업합니다.

## 주요 설정

`.env`는 한 줄에 `이름=값` 형식입니다. 설정을 변경한 뒤 `./mint.sh up`으로 적용합니다. 전체 항목은 `.env.example`을 확인합니다.

| 값 | 기본값과 용도 |
| --- | --- |
| `MINT_BIND`, `MINT_PUBLIC_NAME` | 게시할 사내 IPv4와 선택적인 인증서 DNS 이름입니다. |
| `FIELD_CONSOLE_TLS`, `FIELD_CONSOLE_NAME`, `FIELD_CONSOLE_CERT_FILE`, `FIELD_CONSOLE_KEY_FILE` | 위 콘솔 인증서 방식과 이름·파일 경로입니다. |
| `MODEL_PROXY_PORT`, `MINT_NET_PREFIX` | 모델 프록시 포트 `3128`, 내부 네트워크 접두부 `10.246`입니다. |
| `ROOT_SOLO_APPROVAL` | 기본 `0`으로 신청자와 다른 관리자가 승인합니다. `1`은 root 단독 승인 모드입니다. |
| `ACCESS_TOKEN_MINUTES`, `REFRESH_TOKEN_HOURS` | 접근 토큰 10분, 갱신 토큰 8시간입니다. |
| `FLOW_MATCH_MODE` | 기본 `coarse`입니다. 중요정보를 읽은 뒤 다른 서버에 쓰기·실행하는 흐름의 판정 방식입니다. |
| `TERMINATION_SLA_DAYS`, `CONNECTOR_REVIEW_DAYS` | 종료 기한과 연결 검토 주기입니다. 각각 기본 14일입니다. |
| `GITHUB_OAUTH_CLIENT_ID` | GitHub 계정 연결에 사용하는 선택적인 OAuth App client ID입니다. 현 판본의 콘솔에는 직원용 계정 연결 화면이 없으므로 이 값만 설정해도 직원이 연결할 수 없습니다. 아래 운영자 자격 파일을 사용할 수 있습니다. |
| `OTEL_SDK_DISABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT` | 외부 OpenTelemetry 수집기 연동 설정입니다. 기본값은 비활성입니다. |
| `SIEM_URL`, `SIEM_TOKEN_FILE`, `SIEM_CA_FILE` | 선택적인 SIEM 전송 설정입니다. 파일은 `deploy/siem/`에 두고 컨테이너 경로 `/run/siem/…`로 지정한 뒤 `./mint.sh up --with-siem`을 실행합니다. |
| 서명 키와 `USER_CREDENTIAL_KEY` | 설치 시 생성합니다. 기존 값을 임의로 바꾸거나 잃으면 서명 검증과 저장된 자격 복구에 문제가 생길 수 있습니다. |

## 계정과 직원 PC

```bash
./mint.sh add-account <아이디> --role 관리자
./mint.sh add-account <아이디> --role 직원 --department <부서>
./mint.sh add-account <아이디> --role 직원 --ai-gateway
./mint.sh set-password <아이디>
```

아이디는 영문 소문자로 시작하는 3~32자이며 숫자와 `.`, `_`, `-`를 사용할 수 있습니다. 부서를 생략하면 `운영`입니다. `--ai-gateway`는 PC 키트 없이 AI 게이트웨이를 사용하는 직원에게만 지정합니다. 비밀번호는 프롬프트 또는 표준 입력으로 전달하며 12자 이상이어야 합니다. 명령줄 인자에 비밀번호를 적지 않습니다. 계정 상태와 승인 업무는 콘솔에서 관리합니다.

직원은 콘솔 **PC 연결 설정**에서 자신의 운영체제에 맞는 설치 파일을 받습니다. Windows의 `mcp-managed-setup-windows.exe`는 서명되지 않았으므로 알 수 없는 게시자 경고가 나타나면 실행을 한 번 더 선택하고 UAC를 승인합니다. Linux x86-64의 `mcp-managed-setup-linux`는 `chmod +x` 후 터미널에서 실행하고 관리자 암호를 입력합니다. macOS의 `mcp-connect-macos.command`는 터미널에서 `/bin/bash`로 실행합니다. 세부 절차는 [직원 PC 안내](../endpoint-agent/README.md)를 확인합니다.

## 사설 CA 배포

```bash
./mint.sh ca
openssl x509 -in ca/root.crt -noout -fingerprint -sha256
```

서버에서 출력한 지문을 `ca/root.sha256` 및 신뢰할 수 있는 별도 경로로 전달된 지문과 대조합니다. 확인한 공개 인증서 `ca/root.crt`를 조직의 기기 관리 도구 또는 안전한 배포 경로로 관리자와 직원 PC에 전달하고, 조직의 운영체제·브라우저 정책에 따라 신뢰할 수 있는 루트 인증 기관 저장소에 등록합니다. 브라우저가 별도 인증서 저장소를 쓰면 그 저장소에도 등록합니다. 중앙 배포가 불가능하면 해당 운영체제와 브라우저의 인증서 가져오기 기능에서 같은 지문을 확인하고 신뢰할 루트로 등록합니다.

직원 PC 설치 파일에는 루트 인증서와 지문이 포함됩니다. CA 개인 키는 내보내지 않습니다. CA 볼륨을 유지하고 백업하십시오. 루트가 바뀌면 새 지문을 안전하게 배포하고 직원 PC에 새 설치 파일을 적용해야 합니다.

## 운영자 원격 MCP 자격 파일

운영자가 원격 MCP 자격 파일을 사용하는 경우 `upstream_credentials` Docker 볼륨에 파일을 배치하고 `.env`에 컨테이너 경로를 지정합니다. 예를 들어 `MCP_UPSTREAM_CREDENTIALS_FILE=/run/upstream-credentials/credentials.json`으로 설정한 뒤 `./mint.sh up`을 실행합니다. 볼륨은 게이트웨이에 읽기 전용으로 마운트됩니다.

파일은 아래 형식의 JSON입니다. `endpoint`는 자격을 사용할 정확한 HTTPS 주소이고, `allowed_principals`는 허용할 사용자의 관리대장 `token` 값 배열입니다. 위 `add-account` 명령으로 만든 직원 `alice`는 `emp-alice`, 관리자는 해당 아이디를 사용합니다. `*`는 승인된 모든 호출자와 공유합니다. `expires_at`은 Unix 초 단위 만료 시각이며 `0`은 만료 없음입니다. 토큰은 실제 값으로 안전하게 등록합니다.

```json
{
  "credentials": [
    {"endpoint": "https://mcp.example.com/mcp", "allowed_principals": ["emp-user"], "expires_at": 0, "access_token": "<토큰>"}
  ]
}
```

직원이 해당 서버에 연결한 자격이 있으면 먼저 사용하고, 없으면 사용자와 정확히 일치하는 운영자 자격을 찾은 뒤 공유 자격을 찾습니다. 같은 우선순위의 행이 여러 개면 거부합니다. 파일과 상위 디렉터리는 게이트웨이 실행 사용자 UID `10001` 소유로 배치하고 각각 `0600`, `0700` 권한으로 제한합니다. 자격은 명령줄이나 저장소에 쓰지 말고 안전한 자격 관리 절차로 배치·갱신합니다.

`upstream_credentials` 볼륨은 자동 백업에 포함되지 않습니다. 파일을 별도로 안전하게 백업하고 복구할 때 해당 볼륨에 같은 경로·소유권·권한으로 다시 배치합니다. 토큰의 유효성과 사용자 범위를 확인한 뒤 연결을 점검합니다.

## 백업과 복구

```bash
./mint.sh backup
./mint.sh backup /안전한/백업/경로
./mint.sh restore /안전한/백업/경로
```

기본 백업 위치는 `backups/<UTC 시각>`입니다. DB 덤프, 폐기 목록, 내부 Git, CA, 등록 정보, 검사 보고서, 설정과 판본을 보관합니다. LiteLLM 매핑과 CA가 있으면 함께 보관하며 관리 키는 포함하지 않습니다. 백업 중 일부 서비스가 잠시 중지됩니다. 백업에 서명·암호화 키가 있으므로 접근을 제한하고 서버 밖에 안전하게 보관합니다. 외부 콘솔 인증서 개인 키와 별도 자격 파일도 조직의 절차로 보관합니다.

복구 전에 백업의 `VERSION`을 확인하고 해당 판본 또는 복구 호환성이 확인된 판본을 체크아웃합니다. 복구 명령은 백업과 현재 판본을 표시하지만 일치 여부를 강제하지 않습니다. 복구는 현재 DB와 일부 데이터를 덮어씁니다. 가능하면 복구 전에 현재 상태를 별도로 백업합니다. 같은 서버에 `.env`가 있으면 현재 설정을 유지하며 주요 키가 백업과 다르면 복구를 중단합니다. 기존 폐기 목록과 CA 볼륨은 덮어쓰지 않습니다. 새 서버에서 `.env`가 없으면 백업의 설정을 가져오며, 폐기 목록과 CA 볼륨도 해당 볼륨이 없을 때 가져옵니다. 새 서버는 기존 IP를 사용해야 기존 PC 연결을 유지할 수 있습니다. IP가 바뀌면 백업 사본의 `env`에서 주소를 새 환경에 맞게 수정한 뒤 복구하고 PC에 새 설치 파일을 적용합니다. LiteLLM 관리 키는 복구 후 다시 설정합니다.

감사 기록도 백업 시점으로 돌아가므로 백업 이후 기록이 사라질 수 있습니다. 복구 후 `./mint.sh status`와 콘솔에서 계정·등록 정보 및 연결 상태를 확인합니다.

## 업그레이드와 롤백

업그레이드 전에 변경 사항과 요구 사항을 확인하고 현재 판본과 백업 경로를 기록합니다.

```bash
./mint.sh backup /안전한/업그레이드-전-백업
git fetch --tags
git checkout v<새 판본>
./mint.sh upgrade
./mint.sh status
```

`upgrade`는 현재 체크아웃 판본에서 백업한 다음 빌드·기동합니다. 따라서 위처럼 판본 전환 전에 별도 백업을 확보합니다. 준비 상태와 정책 일치를 확인하고 필요한 경우 직원 PC 설치 파일을 갱신합니다.

이전 판본으로 되돌릴 때는 가능하면 현재 상태도 백업한 뒤 이전 태그를 선택하고 업그레이드 전 백업을 복구합니다.

```bash
./mint.sh backup /안전한/현재-상태-백업
git checkout v<이전 판본>
./mint.sh restore /안전한/업그레이드-전-백업
./mint.sh status
```

복구 시 기존 폐기 목록과 CA는 유지됩니다. 백업 이후 추가된 계정·승인·기록은 복구된 DB에 없으므로 확인하고 필요한 업무를 다시 처리합니다.

## LiteLLM 연동

선택적으로 LiteLLM의 MCP 연동에 승인·철회 동기화를 설정할 수 있습니다. `./mint.sh litellm enable`, `check`, `status`, `rotate-key`, `disable`을 사용합니다. 관리 키는 표준 입력으로 전달합니다. 연결 방식, 매핑, 설정 및 제한은 [LiteLLM 연동 안내](../addons/litellm/README.md)를 확인합니다. 연동을 꺼도 LiteLLM에 이미 반영된 서버와 권한은 남으므로 LiteLLM 관리자가 정리해야 합니다.

## 운영 명령과 중지·제거

| 명령 | 동작 |
| --- | --- |
| `./mint.sh help` | 전체 명령과 옵션을 표시합니다. |
| `./mint.sh install [옵션]` | `install.sh`와 같은 설치를 수행합니다. |
| `./mint.sh up [--with-siem]` | 현재 판본을 빌드하고 기동 또는 재기동합니다. |
| `./mint.sh status` | 서비스·판본·준비 상태와 정책 일치를 표시합니다. |
| `./mint.sh ca` | 사설 루트 인증서와 지문을 다시 내보냅니다. |
| `./mint.sh backup [디렉터리]` | 운영 데이터와 설정을 백업합니다. |
| `./mint.sh restore <디렉터리>` | 백업을 복구합니다. |
| `./mint.sh upgrade` | 백업 후 현재 판본을 빌드하고 기동합니다. |
| `./mint.sh add-account <아이디> --role 관리자\|직원 [--department 부서] [--ai-gateway]` | 계정을 만듭니다. |
| `./mint.sh set-password <아이디>` | 계정 비밀번호를 바꿉니다. |
| `./mint.sh litellm enable\|check\|status\|rotate-key\|disable` | LiteLLM 연동을 관리합니다. |
| `./mint.sh logs [서비스]` | 최근 로그를 표시합니다. |
| `./mint.sh down` | 서비스를 중지하고 데이터는 유지합니다. |
| `./mint.sh compose <인자>` | 인증서 설정을 포함해 Docker Compose 명령을 실행합니다. |

일시 중지는 `./mint.sh down`, 재기동은 `./mint.sh up`을 사용합니다. 완전 제거가 필요하면 먼저 보존할 백업과 인증서·키를 확인한 후 `./mint.sh compose down --volumes`로 이 배포의 컨테이너와 볼륨을 제거하고, 서버의 배포 디렉터리와 별도 비밀 파일을 조직의 보존 정책에 따라 처리합니다. 볼륨 제거는 DB와 CA를 포함하므로 복구에 백업이 필요합니다.

## 문제 해결

| 증상 | 확인할 내용 |
| --- | --- |
| 설치 전 검사 실패 | Docker 데몬 접근 권한, Compose v2, OpenSSL과 Python 3 설치를 확인합니다. |
| 기동 후 준비되지 않음 | `./mint.sh status`, `./mint.sh logs gateway`, `./mint.sh logs agent-service`로 상태를 확인합니다. 내부 대역 충돌과 이미지 다운로드 연결도 확인합니다. |
| 브라우저 인증서 경고 | 접속 이름과 인증서 이름, CA 지문과 브라우저의 신뢰 저장소를 확인합니다. `file` 방식은 체인·키 권한과 DNS를 확인합니다. |
| 직원 PC 연결 실패 | 직원 PC에서 지정 IP의 443과 모델 프록시 포트에 도달하는지, 사설 CA와 계정·PC 상태가 올바른지 확인합니다. |
| 도구 출력 보류 | 출력 검사는 도구가 실행된 후에도 실패할 수 있습니다. 호출 기록의 실행 여부와 실제 처리 결과를 확인한 뒤 재시도합니다. |
| 복구 시 키 불일치 | 현재 `.env`와 백업 키가 다르면 복구가 중단됩니다. 올바른 백업과 서버를 확인합니다. 키를 임의 생성하지 않습니다. |
| LiteLLM 점검 실패 | `./mint.sh litellm check`와 `status`로 매핑·관리 키·연결을 확인합니다. 활성화 점검이 실패하면 `.env`는 변경되어 있을 수 있습니다. |

