#!/usr/bin/env bash
# field와 운영 배포가 같은 인증서 선택·마운트 검증을 사용한다.
console_tls_configure() {
  local key value directory mode
  directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  CONSOLE_TLS_COMPOSE=()
  for key in FIELD_CONSOLE_TLS FIELD_CONSOLE_NAME FIELD_CONSOLE_CERT_FILE FIELD_CONSOLE_KEY_FILE; do
    value="${!key:-}"
    [[ -n "$value" ]] || value="$(env_value "$key")"
    printf -v "$key" '%s' "$value"
    export "$key"
  done
  FIELD_CONSOLE_TLS="${FIELD_CONSOLE_TLS:-none}"
  case "$FIELD_CONSOLE_TLS" in
    none) return 0 ;;
    tailscale|file) ;;
    *) echo "FIELD_CONSOLE_TLS는 none, tailscale, file 중 하나여야 합니다." >&2; return 1 ;;
  esac
  FIELD_CONSOLE_NAME="${FIELD_CONSOLE_NAME,,}"
  [[ ${#FIELD_CONSOLE_NAME} -le 253 && "$FIELD_CONSOLE_NAME" =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]([a-z0-9-]{0,61}[a-z0-9])?$ ]] || {
    echo "FIELD_CONSOLE_NAME에 포트·경로 없는 DNS 이름을 지정하세요." >&2; return 1;
  }
  if [[ "$FIELD_CONSOLE_TLS" == tailscale ]]; then
    [[ "$FIELD_CONSOLE_NAME" == *.ts.net && -S /var/run/tailscale/tailscaled.sock ]] || {
      echo "tailscale 방식에는 .ts.net 이름과 tailscaled 소켓이 필요합니다." >&2; return 1;
    }
  else
    for key in FIELD_CONSOLE_CERT_FILE FIELD_CONSOLE_KEY_FILE; do
      value="${!key}"
      [[ "$value" == /* && -f "$value" && -s "$value" && -r "$value" ]] || {
        echo "$key 에 읽을 수 있는 PEM 파일의 절대 경로를 지정하세요." >&2; return 1;
      }
    done
    mode="$(stat -c %a "$FIELD_CONSOLE_KEY_FILE")" || return 1
    (( (8#$mode & 077) == 0 )) || {
      echo "콘솔 개인 키의 그룹·기타 사용자 권한을 제거하세요(chmod 600)." >&2; return 1;
    }
  fi
  CONSOLE_TLS_COMPOSE=(-f "$directory/compose.console-${FIELD_CONSOLE_TLS}.yaml")
  CONSOLE_URL="https://${FIELD_CONSOLE_NAME}"
}
