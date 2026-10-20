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
digest() { docker image inspect "$1" --format '{{index .RepoDigests 0}}' 2>/dev/null | sed 's/.*@//' || true; }
for pair in POSTGRES:postgres:18-alpine OLLAMA:ollama/ollama:0.40.3 LITELLM:ghcr.io/berriai/litellm-database:v1.105.0; do
  var="${pair%%:*}_DIGEST"; ref="${pair#*:}"
  d="$(digest "$ref")"; [[ -n "$d" ]] || { docker pull -q "$ref" >/dev/null; d="$(digest "$ref")"; }
  export "$var=$d"
done
docker compose up -d postgres ollama
# 모델은 인터넷이 열린 일회용 컨테이너로 한 번만 받는다. 런타임 Ollama는 internal 망뿐이라 밖으로 못 나간다.
if ! docker compose exec -T ollama ollama list 2>/dev/null | grep -q '^qwen3:0.6b'; then
  docker run --rm -v mint-llm_ollama_models:/root/.ollama --entrypoint /bin/sh "ollama/ollama:0.40.3@${OLLAMA_DIGEST}" \
    -c 'ollama serve >/tmp/o.log 2>&1 & for i in $(seq 1 30); do ollama list >/dev/null 2>&1 && break; sleep 1; done; ollama pull qwen3:0.6b'
fi
docker compose up -d litellm
echo "LiteLLM: http://127.0.0.1:${LITELLM_PORT:-4010} (기기 loopback)"
