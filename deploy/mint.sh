#!/usr/bin/env bash
# MINT 운영 배포 관리. 사용법은 ./mint.sh help, 절차는 deploy/README.md.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$DEPLOY_DIR")"
cd "$DEPLOY_DIR"

usage() {
  cat <<'EOF'
./mint.sh install [--bind IP] [--name DNS]   처음 설치(설정 생성 → 빌드 → 기동 → 첫 관리자 → 루트 인증서)
  [--console-tls none|tailscale|file] [--console-name DNS] [--console-cert PEM] [--console-key PEM]
./mint.sh up [--with-siem]                   현재 판본으로 기동·재기동(업그레이드·롤백 뒤에도 이것)
./mint.sh status                             서비스 상태·판본·준비 여부
./mint.sh ca                                 루트 인증서와 SHA-256 지문 내보내기(ca/root.crt)
./mint.sh backup [디렉터리]                  DB·폐기 목록·내부 Git·인증서·설정 백업
./mint.sh restore <백업 디렉터리>            백업에서 복구(현재 데이터를 덮어씀)
./mint.sh upgrade                            백업 뒤 현재 체크아웃 판본으로 빌드·기동
./mint.sh set-password <아이디>              비밀번호 변경(표준 입력 또는 프롬프트)
./mint.sh add-account <아이디> --role 관리자|직원 [--department 부서] [--ai-gateway]
./mint.sh litellm enable --url <관리 origin> --bindings <매핑.json> [--ca <PEM>] [--route mint|direct] < 관리 키 파일
./mint.sh litellm check | status | rotate-key < 새 키 파일 | disable
./mint.sh logs [서비스]                      로그
./mint.sh down                               정지(데이터 유지)
./mint.sh compose <인자…>                    같은 설정으로 docker compose 실행
EOF
}

die() { echo "mint: $*" >&2; exit 1; }

env_value() { sed -n "s/^$1=//p" .env 2>/dev/null | tail -n1; }
source "$REPO_DIR/full_stack_lab/field/console-tls.sh"

env_set() {
  local key="$1" value="$2"
  if grep -q "^$key=" .env; then
    local rest; rest="$(grep -v "^$key=" .env)"
    printf '%s\n%s=%s\n' "$rest" "$key" "$value" > .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

# 판본은 저장소 최상위 VERSION 하나에서 온다. 이미지 태그와 /api/health의 build.revision이 같은 값을 보인다.
load_env() {
  [[ -f .env ]] || die ".env가 없습니다. ./mint.sh install을 먼저 실행하세요."
  MINT_VERSION="$(tr -d '[:space:]' < "$REPO_DIR/VERSION")"
  [[ "$MINT_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]] || die "VERSION 형식이 잘못됐습니다: $MINT_VERSION"
  local commit; commit="$(git -C "$REPO_DIR" rev-parse --short=12 HEAD 2>/dev/null || true)"
  MCP_BUILD_REVISION="$MINT_VERSION${commit:++g$commit}"
  MINT_BIND="$(env_value MINT_BIND)"
  [[ "$MINT_BIND" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || die ".env의 MINT_BIND에 이 서버의 사내 IPv4를 적으세요."
  [[ "$MINT_BIND" != 0.0.0.0 && "$MINT_BIND" != 127.* ]] || die "MINT_BIND는 모든 인터페이스나 loopback이 될 수 없습니다."
  CONSOLE_URL="https://${MINT_BIND}"
  console_tls_configure
  MINT_TLS_ADDRESSES="https://${MINT_BIND}:8080"
  local name; name="$(env_value MINT_PUBLIC_NAME)"
  if [[ -n "$name" ]]; then
    [[ "$name" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] || die "MINT_PUBLIC_NAME은 호스트 이름이어야 합니다."
    if [[ "$FIELD_CONSOLE_TLS" == none || "${name,,}" != "$FIELD_CONSOLE_NAME" ]]; then
      MINT_TLS_ADDRESSES+=", https://${name}:8080"
    fi
  fi
  export MINT_VERSION MCP_BUILD_REVISION MINT_TLS_ADDRESSES
}

dc() { docker compose --env-file .env -f compose.yaml "${CONSOLE_TLS_COMPOSE[@]}" "$@"; }

project() { local p; p="$(env_value MINT_PROJECT)"; echo "${p:-mint}"; }

preflight() {
  command -v docker >/dev/null || die "Docker가 없습니다(Docker Engine 24 이상)."
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 플러그인이 없습니다."
  command -v openssl >/dev/null || die "openssl이 없습니다."
  docker info >/dev/null 2>&1 || die "Docker 데몬에 접근할 수 없습니다(root 또는 docker 그룹)."
}

# 비어 있는 비밀 값만 채운다. 이미 있는 값은 바꾸지 않는다(키를 바꾸면 서명·암호화된 데이터를 못 읽는다).
generate_secrets() {
  local key
  for key in POSTGRES_PASSWORD GITEA_ADMIN_PASSWORD MOCK_SSO_PASSWORD; do
    [[ -n "$(env_value $key)" ]] || env_set "$key" "$(openssl rand -hex 24)"
  done
  [[ -n "$(env_value FLOW_FINGERPRINT_PEPPER)" ]] || env_set FLOW_FINGERPRINT_PEPPER "fp-$(openssl rand -hex 24)"
  [[ -n "$(env_value USER_CREDENTIAL_KEY)" ]] \
    || env_set USER_CREDENTIAL_KEY "$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n')"
  if [[ -z "$(env_value LOCAL_MANIFEST_PUBKEY)" && -z "$(env_value LOCAL_MANIFEST_PRIVATE_KEY)" ]]; then
    local pem; pem="$(openssl genpkey -algorithm ed25519)"
    env_set LOCAL_MANIFEST_PRIVATE_KEY "$(printf '%s\n' "$pem" | awk '{printf "%s\\n", $0}')"
    env_set LOCAL_MANIFEST_PUBKEY "$(printf '%s\n' "$pem" | openssl pkey -pubout | awk '{printf "%s\\n", $0}')"
  fi
}

# 서명 키는 게이트웨이 이미지 안에서 만든다(서버에 암호 라이브러리가 없어도 된다).
generate_keys() {
  local kind prefix line
  for kind in agent disposal; do
    prefix=AGENT_JWT; [[ $kind == disposal ]] && prefix=DISPOSAL
    [[ -z "$(env_value ${prefix}_PRIVATE_KEY)" ]] || continue
    [[ -z "$(env_value ${prefix}_PUBLIC_KEY)" ]] || die "${prefix}_PRIVATE_KEY가 없습니다. 백업한 키를 복구하세요."
    while IFS= read -r line; do env_set "${line%%=*}" "${line#*=}"; done < <(
      AGENT_JWT_PRIVATE_KEY=x AGENT_JWT_PUBLIC_KEY=x DISPOSAL_PRIVATE_KEY=x DISPOSAL_PUBLIC_KEY=x \
        dc run --rm --no-deps -T --entrypoint python gateway -m app.keygen ${kind/agent/} | tr -d '\r')
  done
}

console_get() {
  dc exec -T agent-service python -c 'import sys, urllib.request
print(urllib.request.urlopen("http://127.0.0.1:8000" + sys.argv[1], timeout=5).read().decode())' "$1"
}

wait_ready() {
  local i
  for i in $(seq 1 120); do
    if console_get /api/readiness 2>/dev/null | python3 -c 'import json,sys; sys.exit(json.load(sys.stdin)["status"] != "ready")' 2>/dev/null; then
      return 0
    fi
    sleep 3
  done
  dc ps
  die "6분 안에 게이트웨이·콘솔이 준비되지 않았습니다. ./mint.sh logs gateway 로 확인하세요."
}

# 비밀번호는 명령줄이 아니라 표준 입력으로 넘긴다(프로세스 목록에 남지 않게). 해시는 로그인과 같은 bcrypt.
store_password() {
  dc exec -T agent-service python -c '
import os, sys, psycopg
with psycopg.connect(os.environ["DATABASE_URL"]) as db:
    n = db.execute("UPDATE principals SET password_hash = crypt(%s, gen_salt(%s, 12)) WHERE lower(email) = lower(%s)",
                   (sys.stdin.read(), "bf", sys.argv[1])).rowcount
sys.exit(0 if n else 1)' "$1"
}

read_password() {
  local pw again
  if [[ -t 0 ]]; then
    read -r -s -p "새 비밀번호(12자 이상): " pw; echo >&2
    read -r -s -p "비밀번호 확인: " again; echo >&2
    [[ "$pw" == "$again" ]] || die "두 비밀번호가 다릅니다."
  else
    IFS= read -r pw || true
  fi
  [[ ${#pw} -ge 12 ]] || die "비밀번호는 12자 이상이어야 합니다."
  printf '%s' "$pw"
}

# 콘솔은 기동할 때마다 root(관리자)·user(직원) 기본 계정을 아이디와 같은 비밀번호로 만든다(이미 있으면 그대로).
# 게시 포트를 열기 전에, 기본 비밀번호가 남은 root는 임의 값으로 바꾸고 기본 직원 계정은 중지한다.
# 비밀번호를 이미 바꾼 서버(업그레이드·복구)에서는 아무것도 바꾸지 않는다.
first_admin() {
  local pw; pw="$(openssl rand -base64 18 | tr '+/' '-_')"
  local rotated
  rotated="$(printf '%s' "$pw" | dc exec -T agent-service python -c '
import os, sys, psycopg
with psycopg.connect(os.environ["DATABASE_URL"]) as db:
    n = db.execute("""UPDATE principals SET password_hash = crypt(%s, gen_salt(%s, 12))
                      WHERE token = %s AND password_hash = crypt(token, password_hash)""",
                   (sys.stdin.read(), "bf", "root")).rowcount
    db.execute("""UPDATE principals SET status = %s
                  WHERE token = %s AND role <> %s AND password_hash = crypt(token, password_hash)""",
               ("disabled", "user", "admin"))
print(n)')"
  if [[ "$rotated" == 1 ]]; then
    (umask 077; printf '%s\n' "$pw" > "$DEPLOY_DIR/initial-admin-password")
  fi
}

export_ca() {
  local tmp i; tmp="$(mktemp)"
  for i in $(seq 1 30); do
    dc exec -T caddy cat /data/caddy/pki/authorities/local/root.crt > "$tmp" 2>/dev/null && break
    sleep 1
  done
  openssl x509 -in "$tmp" -noout >/dev/null 2>&1 || { rm -f "$tmp"; die "Caddy 루트 인증서를 읽지 못했습니다."; }
  cp "$tmp" ca/root.crt && chmod 644 ca/root.crt; rm -f "$tmp"
  openssl x509 -in ca/root.crt -noout -fingerprint -sha256 | cut -d= -f2 > ca/root.sha256
  echo "루트 인증서: $DEPLOY_DIR/ca/root.crt"
  echo "SHA-256    : $(cat ca/root.sha256)"
}

# 컨테이너(UID 10001)가 읽을 디렉터리. litellm/은 목록을 숨기고 통과만 허용한다(관리 키는 0400, 소유 10001).
prepare_dirs() {
  mkdir -p ca siem litellm
  chmod 711 litellm
  [[ -f litellm/bindings.json ]] || printf '{"users": [], "teams": [], "workers": []}\n' > litellm/bindings.json
  chmod 644 litellm/bindings.json
}

up() {
  local with_siem=0 a
  for a in "$@"; do
    case "$a" in --with-siem) with_siem=1 ;; *) die "알 수 없는 옵션: $a" ;; esac
  done
  load_env
  prepare_dirs
  echo "[1/4] 이미지 빌드 ($MCP_BUILD_REVISION)"
  dc build -q
  echo "[2/4] 게이트웨이·콘솔·검사기"
  # OPA와 게이트웨이는 정책 파일을 기동할 때만 읽는다. 정책이 바뀐 판본에서도 반영되게 다시 만든다.
  dc up -d --force-recreate opa gateway
  dc up -d db presidio-analyzer presidio-anonymizer agent-service intake-worker runtime-worker corp-git
  wait_ready
  first_admin
  echo "[3/4] HTTPS 앞단·모델 프록시 ($MINT_BIND)"
  dc up -d --force-recreate caddy
  dc up -d model-proxy
  if [[ $with_siem == 1 ]]; then dc --profile siem up -d siem-worker; fi
  echo "[4/4] 루트 인증서"
  export_ca
}

install_stack() {
  local bind="" name="" console_tls="" console_name="" console_cert="" console_key=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --bind) bind="${2:-}"; shift 2 ;;
      --name) name="${2:-}"; shift 2 ;;
      --console-tls) console_tls="${2:?인증서 방식을 지정하세요}"; shift 2 ;;
      --console-name) console_name="${2:?콘솔 DNS 이름을 지정하세요}"; shift 2 ;;
      --console-cert) console_cert="${2:?인증서 절대 경로를 지정하세요}"; shift 2 ;;
      --console-key) console_key="${2:?개인 키 절대 경로를 지정하세요}"; shift 2 ;;
      *) die "알 수 없는 옵션: $1" ;;
    esac
  done
  preflight
  if [[ ! -f .env ]]; then (umask 077; cp .env.example .env); fi
  chmod 600 .env
  [[ -z "$bind" ]] || env_set MINT_BIND "$bind"
  [[ -z "$name" ]] || env_set MINT_PUBLIC_NAME "$name"
  [[ -z "$console_tls" ]] || env_set FIELD_CONSOLE_TLS "$console_tls"
  [[ -z "$console_name" ]] || env_set FIELD_CONSOLE_NAME "$console_name"
  [[ -z "$console_cert" ]] || env_set FIELD_CONSOLE_CERT_FILE "$console_cert"
  [[ -z "$console_key" ]] || env_set FIELD_CONSOLE_KEY_FILE "$console_key"
  load_env
  # compose가 없는 마운트 원본을 root 소유 디렉터리로 만들기 전에 준비한다.
  prepare_dirs
  generate_secrets
  echo "[준비] 서명 키·폐기 목록"
  # 키를 만들기 전에는 compose가 빈 키 값을 거절하므로 이 두 명령에만 자리표시 값을 준다.
  AGENT_JWT_PRIVATE_KEY=x AGENT_JWT_PUBLIC_KEY=x DISPOSAL_PRIVATE_KEY=x DISPOSAL_PUBLIC_KEY=x dc build -q gateway
  generate_keys
  load_env
  # 폐기 목록은 첫 설치에서 한 번만 시작한다. 볼륨은 위 키 생성 때 이미 생기므로 목록 파일로 판정한다.
  dc run --rm --no-deps -T --entrypoint sh gateway -c \
    'test -e /disposal/journal.jsonl || test -e /disposal/head.json || python -m app.disposal init'
  up
  echo
  echo "콘솔        : ${CONSOLE_URL}/"
  echo "관리자      : root  (초기 비밀번호: $DEPLOY_DIR/initial-admin-password — 로그인 뒤 ./mint.sh set-password root)"
  echo "직원 PC 키트: 콘솔 로그인 → 내 PC 연결"
  echo "백업        : ./mint.sh backup  (.env와 백업 디렉터리를 서버 밖 안전한 곳에 보관)"
}

status() {
  load_env
  echo "콘솔: ${CONSOLE_URL}/"
  dc ps
  echo "판본: $MCP_BUILD_REVISION"
  console_get /api/readiness | python3 -c 'import json,sys
d = json.load(sys.stdin)
print("준비:", "예" if d["status"] == "ready" else "아니오", "| 게이트웨이:", d["build"]["gateway"] and d["build"]["gateway"].get("revision"),
      "| 정책 일치:", (d.get("policy") or {}).get("matches"))'
}

# 볼륨을 게이트웨이 이미지의 tar로 묶는다(서버에 다른 도구가 없어도 된다).
volume_tar() {
  local mode="$1" volume="$2" dir="$3"
  local image="mcpgw/gateway:$MINT_VERSION" vol="$(project)_$volume"
  if [[ $mode == save ]]; then
    docker run --rm --user 0 --entrypoint tar -v "$vol:/v:ro" -v "$dir:/b" "$image" -C /v -czf "/b/$volume.tgz" .
  else
    docker volume create "$vol" >/dev/null
    docker run --rm --user 0 --entrypoint sh -v "$vol:/v" -v "$dir:/b:ro" "$image" \
      -c 'find /v -mindepth 1 -delete && tar -C /v -xzf "/b/$0.tgz"' "$volume"
  fi
}

VOLUMES=(disposal_journal git_data caddy_data registry_runtime intake_reports)
# 폐기 목록은 DB와 함께 되돌리지 않는다: 남은 목록이 복원된 DB에서 빠진 철회를 다시 막는다. 사설 CA도 배치 수명 동안
# 유지한다(새 루트는 모든 PC의 연결을 끊는다). 둘은 볼륨이 없는 새 서버로 옮길 때만 백업에서 가져온다.
KEEP_IF_PRESENT=(disposal_journal caddy_data)
KEYS=(AGENT_JWT_PRIVATE_KEY AGENT_JWT_PUBLIC_KEY DISPOSAL_PRIVATE_KEY DISPOSAL_PUBLIC_KEY USER_CREDENTIAL_KEY FLOW_FINGERPRINT_PEPPER)

backup() {
  load_env
  local dir="${1:-$DEPLOY_DIR/backups/$(date -u +%Y%m%dT%H%M%SZ)}"
  mkdir -p "$dir"; chmod 700 "$dir"; dir="$(cd "$dir" && pwd)"
  echo "백업: $dir"
  dc exec -T db pg_dump -U mcp -d mcp_governance -Fc > "$dir/mcp_governance.dump"
  # 폐기 목록·내부 Git은 DB와 같은 시점이어야 하므로 쓰는 서비스를 잠시 멈추고 묶는다.
  dc stop gateway agent-service runtime-worker corp-git >/dev/null
  local v; for v in "${VOLUMES[@]}"; do volume_tar save "$v" "$dir"; done
  dc start corp-git gateway agent-service runtime-worker >/dev/null
  (umask 077; cp .env "$dir/env"; printf '%s\n' "$MCP_BUILD_REVISION" > "$dir/VERSION")
  # LiteLLM 매핑·CA는 함께 둔다. 관리 키는 비밀 저장소가 정본이라 복구 뒤 rotate-key로 다시 넣는다.
  local f; for f in bindings.json ca.pem; do [[ ! -f "litellm/$f" ]] || cp "litellm/$f" "$dir/litellm-$f"; done
  echo "완료. env 파일에 서명·암호화 키가 있습니다 — 백업 디렉터리를 서버 밖 안전한 곳에 보관하세요."
}

restore() {
  local dir="${1:?백업 디렉터리를 지정하세요}"
  [[ -f "$dir/mcp_governance.dump" && -f "$dir/env" ]] || die "$dir 에 백업 파일이 없습니다."
  dir="$(cd "$dir" && pwd)"
  local key
  if [[ -f .env ]]; then
    # 같은 서버에서는 지금 설정을 그대로 쓴다. 키가 다르면 백업 데이터의 서명·암호문을 읽을 수 없으므로 멈춘다.
    for key in "${KEYS[@]}"; do
      [[ "$(env_value "$key")" == "$(sed -n "s/^$key=//p" "$dir/env" | tail -n1)" ]] \
        || die "현재 .env의 $key가 백업과 다릅니다. 새 서버라면 .env 없이 복구하세요."
    done
  else
    (umask 077; cp "$dir/env" .env)
  fi
  load_env
  prepare_dirs
  local f; for f in bindings.json ca.pem; do [[ ! -f "$dir/litellm-$f" ]] || { cp "$dir/litellm-$f" "litellm/$f"; chmod 644 "litellm/$f"; }; done
  echo "복구: $dir (백업 판본 $(cat "$dir/VERSION" 2>/dev/null || echo '—'), 현재 체크아웃 $MCP_BUILD_REVISION)"
  dc build -q
  dc stop caddy model-proxy gateway agent-service intake-worker runtime-worker corp-git >/dev/null 2>&1 || true
  local v
  for v in "${VOLUMES[@]}"; do
    if [[ " ${KEEP_IF_PRESENT[*]} " == *" $v "* ]] && docker volume inspect "$(project)_$v" >/dev/null 2>&1; then
      echo "  $v: 이 서버의 현재 내용을 유지"
      continue
    fi
    volume_tar restore "$v" "$dir"
  done
  dc up -d db
  local i; for i in $(seq 1 40); do dc exec -T db pg_isready -U mcp -d mcp_governance >/dev/null 2>&1 && break; sleep 2; done
  dc exec -T db psql -U mcp -d postgres -qc "DROP DATABASE IF EXISTS mcp_governance WITH (FORCE)" -c "CREATE DATABASE mcp_governance OWNER mcp"
  dc exec -T db pg_restore -U mcp -d mcp_governance --no-owner < "$dir/mcp_governance.dump"
  up
}

upgrade() {
  load_env
  backup
  up
}

set_password() {
  local id="${1:?아이디를 지정하세요}"
  load_env
  read_password | store_password "$id" || die "그런 계정이 없습니다: $id"
  echo "바꿨습니다: $id"
  [[ "$id" != root ]] || rm -f "$DEPLOY_DIR/initial-admin-password"
}

add_account() {
  local name="${1:?아이디를 지정하세요}" role="" department="운영" gateway=0
  shift
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --role) role="${2:-}"; shift 2 ;;
      --department) department="${2:-}"; shift 2 ;;
      --ai-gateway) gateway=1; shift ;;
      *) die "알 수 없는 옵션: $1" ;;
    esac
  done
  case "$role" in 관리자|admin) role=admin ;; 직원|user) role=user ;; *) die "--role 관리자 또는 --role 직원을 지정하세요." ;; esac
  [[ $gateway == 0 || $role == user ]] || die "--ai-gateway는 직원 계정에만 씁니다."
  [[ "$name" =~ ^[a-z][a-z0-9]*([._-][a-z0-9]+)*$ && ${#name} -ge 3 && ${#name} -le 32 ]] \
    || die "아이디는 영문 소문자로 시작하는 3~32자(숫자·. _ - 가능)여야 합니다."
  load_env
  # 관리자 토큰은 root와 같은 형식(아이디), 직원은 가입 승인과 같은 형식(emp-아이디)이다.
  read_password | dc exec -T agent-service python -c '
import os, sys, psycopg
name, role, department, gateway = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == "1"
token, db_role = (name, "admin") if role == "admin" else ("emp-" + name, "employee")
with psycopg.connect(os.environ["DATABASE_URL"]) as db:
    if db.execute("SELECT 1 FROM principals WHERE lower(email)=lower(%s) OR user_id=%s OR token=%s", (name, name, token)).fetchone():
        sys.exit("이미 있는 아이디입니다")
    # AI 게이트웨이 전용 직원은 PC 키트 없이 자기 MCP 토큰을 받는다. 판정·원장은 다른 직원과 같다(D-250).
    db.execute("""INSERT INTO principals(token,user_id,email,display_name,role,department,password_hash,managed_required,ai_gateway_only)
                  VALUES (%s,%s,%s,%s,%s,%s,crypt(%s, gen_salt(%s, 12)),%s,%s)""",
               (token, name, name, name, db_role, department, sys.stdin.read(), "bf", db_role != "admin" and not gateway, gateway))
print(("관리자" if db_role == "admin" else "직원") + " 계정을 만들었습니다: " + name)' "$name" "$role" "$department" "$gateway"
}

sync_check() {
  dc run --rm --no-deps -T --entrypoint python gateway -m app.litellm_sync check
}

# 관리 키는 표준 입력으로만 받아 게이트웨이 이미지 안에서 파일로 쓴다(명령줄·.env·로그에 남지 않게).
write_admin_key() {
  local key; IFS= read -r key || true
  [[ -n "$key" && "$key" != *[[:space:]]* ]] || die "관리 키를 표준 입력으로 주세요(한 줄)."
  printf '%s' "$key" | docker run --rm -i --user 0 --entrypoint sh -v "$DEPLOY_DIR/litellm:/d" "mcpgw/gateway:$MINT_VERSION" \
    -c 'umask 077; cat > /d/admin-key.new && chown 10001 /d/admin-key.new && chmod 0400 /d/admin-key.new && mv /d/admin-key.new /d/admin-key'
}

litellm() {
  load_env
  prepare_dirs
  case "${1:-}" in
    enable)
      shift
      local url="" bindings="" ca="" route=mint
      while [[ $# -gt 0 ]]; do
        case "$1" in
          --url) url="${2:-}"; shift 2 ;;
          --bindings) bindings="${2:-}"; shift 2 ;;
          --ca) ca="${2:-}"; shift 2 ;;
          --route) route="${2:-}"; shift 2 ;;
          *) die "알 수 없는 옵션: $1" ;;
        esac
      done
      [[ -n "$url" && -f "$bindings" ]] || die "--url과 --bindings 파일을 지정하세요."
      [[ "$route" == mint || "$route" == direct ]] || die "--route는 mint 또는 direct입니다."
      python3 -m json.tool "$bindings" >/dev/null || die "매핑 파일이 JSON이 아닙니다."
      cp "$bindings" litellm/bindings.json && chmod 644 litellm/bindings.json
      if [[ -n "$ca" ]]; then
        openssl x509 -in "$ca" -noout || die "--ca가 PEM 인증서가 아닙니다."
        cp "$ca" litellm/ca.pem && chmod 644 litellm/ca.pem
        env_set MINT_LITELLM_SYNC_CA_FILE /run/mint-litellm/ca.pem
      else
        env_set MINT_LITELLM_SYNC_CA_FILE ""
      fi
      write_admin_key
      env_set MINT_LITELLM_SYNC_URL "$url"
      env_set MINT_LITELLM_SYNC_KEY_FILE /run/mint-litellm/admin-key
      env_set MINT_LITELLM_ROUTE "$route"
      echo "[점검] 매핑·관리 키·명시적 키 접근 설정·워커 연결"
      sync_check || die "점검이 실패해 적용하지 않았습니다(.env는 바뀌었고 게이트웨이는 그대로입니다). 고친 뒤 다시 실행하세요."
      dc up -d --force-recreate gateway agent-service
      wait_ready
      echo "켰습니다. 상태: ./mint.sh litellm status"
      ;;
    check) sync_check ;;
    rotate-key)
      # 키는 요청마다 다시 읽으므로 재기동하지 않는다. 새 키로 관리 API가 응답하는지 점검한다.
      write_admin_key
      sync_check
      ;;
    status)
      sync_check || true
      dc exec -T db psql -U mcp -d mcp_governance -At -F ' ' -c \
        "SELECT server_id, status, attempts, to_char(updated_at, 'YYYY-MM-DD HH24:MI:SS') FROM litellm_sync_jobs ORDER BY server_id" </dev/null
      ;;
    disable)
      env_set MINT_LITELLM_SYNC_URL ""
      dc up -d --force-recreate gateway agent-service
      wait_ready
      echo "껐습니다. LiteLLM에 이미 반영된 서버·권한은 그대로 남습니다(LiteLLM 관리자가 정리)."
      ;;
    *) usage; exit 2 ;;
  esac
}

case "${1:-help}" in
  install) shift; install_stack "$@" ;;
  up) shift; up "$@" ;;
  status) status ;;
  ca) load_env; export_ca ;;
  backup) shift; backup "$@" ;;
  restore) shift; restore "$@" ;;
  upgrade) upgrade ;;
  set-password) shift; set_password "$@" ;;
  add-account) shift; add_account "$@" ;;
  litellm) shift; litellm "$@" ;;
  logs) shift; load_env; dc logs --tail=300 "$@" ;;
  down) load_env; dc --profile siem stop ;;
  compose) shift; load_env; dc "$@" ;;
  help|-h|--help) usage ;;
  *) usage; exit 2 ;;
esac
