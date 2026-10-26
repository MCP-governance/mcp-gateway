#!/usr/bin/env bash
# field와 운영 배포가 같은 인증서 선택·마운트 검증을 사용한다.
local_tailscale_ip() {
  local address
  address="$(tailscale ip -4 2>/dev/null)" || return 1
  [[ "$address" =~ ^100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.([0-9]{1,3})\.([0-9]{1,3})$ ]] || return 1
  (( 10#${BASH_REMATCH[2]} <= 255 && 10#${BASH_REMATCH[3]} <= 255 )) || return 1
  printf '%s\n' "$address"
}

console_tls_file_safe() {
  local path="$1" owner mode
  while :; do
    [[ ! -L "$path" ]] || { echo "인증서 경로에 심볼릭 링크를 사용할 수 없습니다." >&2; return 1; }
    owner="$(stat -c %u "$path")" && mode="$(stat -c %a "$path")" || return 1
    [[ "$owner" == 0 || "$owner" == "$(id -u)" ]] && (( (8#$mode & 022) == 0 )) || {
      echo "인증서 파일과 상위 경로는 root 또는 설치 사용자 소유이며 그룹·기타 쓰기가 없어야 합니다." >&2; return 1;
    }
    [[ "$path" != / ]] || break
    path="$(dirname "$path")"
  done
}

# 기존 root 소유 CA를 보존하면서 비root 프로세스에 저장소 소유권을 넘긴다. 서비스·포트는 시작하지 않는다.
console_caddy_prepare() {
  # 일회성 컨테이너가 서비스의 고정 IP를 받으므로 실행 중인 Caddy와 겹치지 않게 먼저 내린다. 바로 다시 만든다.
  "$@" rm -sf caddy >/dev/null
  "$@" run --rm --no-deps -T --user 0 --cap-add CHOWN --cap-add DAC_READ_SEARCH --entrypoint sh caddy \
    -c 'chown -R "$1":0 /data /config' sh "$CONSOLE_CADDY_UID"
}

console_tls_configure() {
  local key value directory mode owner group
  directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  export CONSOLE_TLS_DIR="$directory" CONSOLE_CADDY_UID=10001
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
      console_tls_file_safe "$value" || return 1
    done
    mode="$(stat -c %a "$FIELD_CONSOLE_KEY_FILE")" || return 1
    [[ "$mode" == 400 || "$mode" == 600 || "$mode" == 640 ]] || {
      echo "콘솔 개인 키 권한은 0400·0600·0640이어야 합니다." >&2; return 1;
    }
    [[ "$(id -u)" == 0 ]] || CONSOLE_CADDY_UID="$(id -u)"
    for value in "$FIELD_CONSOLE_CERT_FILE" "$FIELD_CONSOLE_KEY_FILE"; do
      owner="$(stat -c %u "$value")"; group="$(stat -c %g "$value")"; mode="$(stat -c %a "$value")"
      if [[ "$owner" == "$CONSOLE_CADDY_UID" ]]; then
        (( (8#$mode & 0400) != 0 )) && continue
      elif [[ "$group" == 0 ]]; then
        (( (8#$mode & 0040) != 0 )) && continue
      else
        (( (8#$mode & 0004) != 0 )) && continue
      fi
      echo "비root 콘솔이 인증서·키를 읽을 수 없습니다. 설치 사용자 소유 0600 또는 root:root 소유 0640을 사용하세요." >&2; return 1
    done
  fi
  CONSOLE_TLS_COMPOSE=(-f "$directory/compose.console-${FIELD_CONSOLE_TLS}.yaml")
  CONSOLE_URL="https://${FIELD_CONSOLE_NAME}"
}
