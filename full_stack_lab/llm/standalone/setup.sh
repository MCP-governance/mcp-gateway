#!/usr/bin/env bash
# LiteLLM + Ollama + PostgreSQL 기동(제품 스택과 별개 프로젝트 mint-llm). 값은 출력하지 않는다.
set -euo pipefail
cd "$(dirname "$0")"
umask 077
mkdir -p secrets
[[ -s secrets/postgres_password ]] || printf '%s' "$(openssl rand -hex 24)" > secrets/postgres_password
[[ -s secrets/litellm_master_key ]] || printf 'sk-%s' "$(openssl rand -hex 24)" > secrets/litellm_master_key
[[ -s secrets/litellm_salt_key ]] || printf 'sk-%s' "$(openssl rand -hex 24)" > secrets/litellm_salt_key
chmod 644 secrets/*   # 컨테이너 비root가 읽는 Docker secret: 디렉터리 0700이 외부 접근을 막는다
chmod 700 secrets
# MINT 게이트웨이의 공개 루트 인증서(비밀 아님, deploy/ca/root.crt)와 주소. LiteLLM의 유일한 출구(edge-proxy)가 이것으로 TLS를 검증한다.
: "${GATEWAY_ADDR:?GATEWAY_ADDR=<MINT 게이트웨이 IP 또는 이름>:443 을 지정하세요}"; export GATEWAY_ADDR
if [[ ! -s secrets/gateway-ca.pem ]]; then
  : "${GATEWAY_CA_FILE:?GATEWAY_CA_FILE=<MINT 루트 인증서 PEM 경로(./mint.sh ca)> 를 지정하세요}"
  openssl x509 -in "$GATEWAY_CA_FILE" -noout
  cp "$GATEWAY_CA_FILE" secrets/gateway-ca.pem
fi
chmod 644 secrets/gateway-ca.pem
docker compose up -d postgres ollama
# 모델은 인터넷이 열린 일회용 컨테이너로 한 번만 받는다. 런타임 Ollama는 internal 망뿐이라 밖으로 못 나간다.
if ! docker compose exec -T ollama ollama list 2>/dev/null | grep -q '^qwen3:0.6b'; then
  docker run --rm -v mint-llm_ollama_models:/root/.ollama --entrypoint /bin/sh "$(docker compose config --images | grep '^ollama/')" \
    -c 'ollama serve >/tmp/o.log 2>&1 & for i in $(seq 1 30); do ollama list >/dev/null 2>&1 && break; sleep 1; done; ollama pull qwen3:0.6b'
fi
docker compose up -d litellm edge-proxy
echo "LiteLLM: http://127.0.0.1:${LITELLM_PORT:-4010} (기기 loopback, edge-proxy 경유)"
