#!/usr/bin/env bash
# 솔루션 기기(또는 그 기기에 SSH 터널로 접속한 관리자 PC)에서, 이 브랜치의 작업 디렉터리에서 실행한다.
# kcadm.sh를 keycloak 컨테이너 안에서 실행해 직원 계정을 만든다(README '② 관리자 PC' 참고).
#
# 사용법: field/admin/add-employee.sh <username> <email> [user|admin]
set -euo pipefail

USERNAME="${1:?사용법: add-employee.sh <username> <email> [user|admin]}"
EMAIL="${2:?사용법: add-employee.sh <username> <email> [user|admin]}"
ROLE="${3:-user}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
[ -f "$ROOT/.env" ] && source "$ROOT/.env"
: "${KEYCLOAK_ADMIN_PASSWORD:?ROOT/.env에 KEYCLOAK_ADMIN_PASSWORD가 필요합니다}"

KC=(docker compose -f "$ROOT/compose.yaml" exec -T keycloak /opt/keycloak/bin/kcadm.sh)

"${KC[@]}" config credentials --server http://localhost:8080 --realm master \
  --user bootstrap-admin --password "$KEYCLOAK_ADMIN_PASSWORD"

USER_ID="$("${KC[@]}" create users -r mcp -s username="$USERNAME" -s email="$EMAIL" \
  -s enabled=true -s emailVerified=true -i)"

"${KC[@]}" add-roles -r mcp --uusername "$USERNAME" --rolename "$ROLE"

TEMP_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')"
"${KC[@]}" set-password -r mcp --userid "$USER_ID" --new-password "$TEMP_PASSWORD" --temporary

echo "생성됨: $USERNAME ($ROLE 역할, user id=$USER_ID)"
echo "임시 비밀번호(최초 로그인 시 변경 요구됨): $TEMP_PASSWORD"
echo "이 값을 직원에게 안전한 채널로 전달하세요(이 스크립트는 저장하지 않습니다)."
