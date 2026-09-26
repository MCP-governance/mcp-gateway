#!/bin/sh
# 솔루션 기기에서 실행한다(저장소 최상위에서): ./field/appliance.sh up | ca | status | add-employee | logs | down
# 값은 .env(.env.example을 복사해 비밀번호·토큰과 APPLIANCE_HOST·APPLIANCE_BIND를 채운 것)에서 읽는다.
set -eu
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
cd "$(dirname "$SELF")/.."
[ -f .env ] || { echo "먼저: cp .env.example .env 후 비밀번호·토큰과 APPLIANCE_HOST·APPLIANCE_BIND를 채운다" >&2; exit 1; }
# .env는 Compose 형식이라 셸로 source하지 않고 필요한 값만 읽는다.
env_value() { sed -n "s/^$1=//p" .env | tail -n 1 | sed 's/^"\(.*\)"$/\1/'; }
APPLIANCE_HOST=$(env_value APPLIANCE_HOST)
APPLIANCE_BIND=$(env_value APPLIANCE_BIND)
[ -n "$APPLIANCE_HOST" ] && [ -n "$APPLIANCE_BIND" ] || { echo ".env에 APPLIANCE_HOST와 APPLIANCE_BIND를 채운다" >&2; exit 1; }
CA=outputs/ca/mcp-gw-root.crt

compose() { docker compose -f compose.yaml -f compose.field.yaml "$@"; }

fingerprint() {
	# 직원 PC 키트(setup --ca)가 보여 주는 것과 같은 SHA-256(DER) 지문.
	python3 -c 'import hashlib, ssl, sys
d = hashlib.sha256(ssl.PEM_cert_to_DER_cert(open(sys.argv[1]).read())).hexdigest().upper()
print(":".join(d[i:i + 2] for i in range(0, len(d), 2)))' "$1"
}

case "${1:-}" in
up)
	# realm import와 Dashboard의 issuer·리다이렉트를 https://$APPLIANCE_HOST 기준으로 렌더링한다(outputs/).
	python3 prepare.py --field
	compose up -d --build --wait --wait-timeout 300
	"$SELF" ca
	"$SELF" status
	;;
ca)
	# Caddy는 첫 인증서를 낼 때 사설 CA를 만든다. 몇 초 기다린다.
	mkdir -p outputs/ca
	for _ in 1 2 3 4 5 6 7 8 9 10; do
		compose cp caddy:/data/caddy/pki/authorities/local/root.crt "$CA" 2>/dev/null && break
		sleep 2
	done
	[ -s "$CA" ] || { echo "CA를 꺼내지 못했다: ./field/appliance.sh logs 로 caddy를 본다" >&2; exit 1; }
	echo "루트 인증서: $CA"
	echo "SHA-256 지문: $(fingerprint "$CA")"
	echo "이 파일과 지문을 관리자 PC로 옮겨 직원에게 준다(지문은 파일과 다른 경로로 알린다)."
	;;
status)
	compose ps
	# 직원 PC와 같은 조건(사설 CA 검증, 사내망 주소)으로 Keycloak이 알리는 issuer를 본다. Keycloak은 기동이 느리다.
	expected="https://$APPLIANCE_HOST/realms/mcp"
	for _ in $(seq 1 60); do
		issuer=$(curl -fsS --cacert "$CA" --resolve "$APPLIANCE_HOST:443:$APPLIANCE_BIND" \
			"$expected/.well-known/openid-configuration" 2>/dev/null \
			| python3 -c 'import json, sys; print(json.load(sys.stdin)["issuer"])' 2>/dev/null) || issuer=""
		if [ "$issuer" = "$expected" ]; then
			echo "issuer: $issuer"
			exit 0
		fi
		sleep 3
	done
	echo "issuer가 $expected 가 아니다(받은 값: ${issuer:-없음}). KC_HOSTNAME·APPLIANCE_HOST를 확인한다" >&2
	exit 1
	;;
add-employee)
	shift
	exec field/admin/add-employee.sh "$@"
	;;
logs)
	compose logs --tail=100 -f
	;;
down)
	# 볼륨(DB·Keycloak·CA)은 남긴다. CA까지 지우면 모든 PC가 새 CA를 다시 신뢰해야 한다.
	compose down
	;;
*)
	echo "사용: $0 up | ca | status | add-employee <username> <email> [user|admin] | logs | down" >&2
	exit 2
	;;
esac
