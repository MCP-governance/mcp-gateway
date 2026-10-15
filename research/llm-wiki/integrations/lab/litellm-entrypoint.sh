#!/bin/sh
set -eu

test -s /run/secrets/litellm_master_key
test -s /run/secrets/litellm_salt_key
test -s /run/secrets/postgres_password
export LITELLM_MASTER_KEY="$(cat /run/secrets/litellm_master_key)"
export LITELLM_SALT_KEY="$(cat /run/secrets/litellm_salt_key)"
export DATABASE_URL="$(python -c 'from pathlib import Path; from urllib.parse import quote; p=Path("/run/secrets/postgres_password").read_text().strip(); print("postgresql://interop:" + quote(p, safe="") + "@postgres:5432/litellm")')"

exec /app/docker/prod_entrypoint.sh --config /lab/litellm.yaml --port 4000
