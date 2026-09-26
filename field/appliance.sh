#!/bin/sh
# 솔루션 기기에서 실행한다(저장소 최상위에서): ./field/appliance.sh up | ca | status | logs | down
# 값은 .env(field/field.env.example을 복사)에서 읽는다.
set -eu
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
cd "$(dirname "$SELF")/.."
[ -f .env ] || { echo "먼저: cp field/field.env.example .env 후 값을 채운다" >&2; exit 1; }
# .env는 Compose 형식이라 셸로 source하지 않고 필요한 값만 읽는다(공백이 든 ADMIN_CIDR 등).
env_value() { sed -n "s/^$1=//p" .env | tail -n 1 | sed 's/^"\(.*\)"$/\1/'; }
APPLIANCE_HOST=$(env_value APPLIANCE_HOST)
APPLIANCE_BIND=$(env_value APPLIANCE_BIND)
CA=field/ca/mcp-gw-root.crt

compose() { docker compose -f compose.yaml -f compose.field.yaml "$@"; }

fingerprint() {
	# 직원이 setup에서 보는 값과 같은 SHA-256(DER) 지문.
	python3 -c 'import hashlib, ssl, sys
d = hashlib.sha256(ssl.PEM_cert_to_DER_cert(open(sys.argv[1]).read())).hexdigest().upper()
print(":".join(d[i:i + 2] for i in range(0, len(d), 2)))' "$1"
}

case "${1:-}" in
up)
	compose up -d --build --wait
	"$SELF" ca
	"$SELF" status
	;;
ca)
	# Caddy는 첫 인증서를 낼 때 사설 CA를 만든다. 몇 초 기다린다.
	mkdir -p field/ca
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
	# 직원 PC와 같은 조건(사설 CA 검증, 사내망 주소)으로 본다. 프록시의 첫 도달 확인이 upstream보다 먼저 돌면
	# 다음 확인(30초)까지 down이라, 잠깐 기다린다.
	for _ in $(seq 1 25); do
		if curl -fsS --cacert "$CA" --resolve "$APPLIANCE_HOST:443:$APPLIANCE_BIND" "https://$APPLIANCE_HOST/api/ready"; then
			echo
			exit 0
		fi
		sleep 2
	done
	curl -sS --cacert "$CA" --resolve "$APPLIANCE_HOST:443:$APPLIANCE_BIND" "https://$APPLIANCE_HOST/api/ready"
	echo
	exit 1
	;;
logs)
	compose logs --tail=100 -f
	;;
down)
	# 볼륨(기록·CA)은 남긴다. CA까지 지우면 모든 PC가 새 CA를 다시 신뢰해야 한다.
	compose down
	;;
*)
	echo "사용: $0 up | ca | status | logs | down" >&2
	exit 2
	;;
esac
