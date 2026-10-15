#!/usr/bin/env bash
set -euo pipefail
TASK=/home/pj1/mcpgw-ghidra-20261014
SCRATCH=/dev/shm/mcpgw-ghidra-20261014
RUNTIME="$SCRATCH/runtime"
UV_SHA=23bf5552d220e0842b65c862097b2ebaeba0064b74eda5e565e77fd25969d8c8
MCP_COMMIT=1e980252087b2479a21b9ca6d82d5829538651a7
UV_ARCHIVE="$SCRATCH/uv.tar.gz"

[[ "$(id -u)" == 1000 && "$(id -un)" == pj1 ]] || { echo 'wrong uid' >&2; exit 20; }
[[ -x "$RUNTIME/ghidra/support/analyzeHeadless" && -x "$RUNTIME/jdk/bin/java" ]] || { echo 'missing verified runtime' >&2; exit 21; }
[[ "$(git -C "$TASK/source" rev-parse HEAD)" == "$MCP_COMMIT" ]] || { echo 'wrong source commit' >&2; exit 22; }
[[ -f "$TASK/venv/pyvenv.cfg" && ! -x "$TASK/venv/bin/ghidra-mcp" ]] || { echo 'venv is not the expected partial bootstrap' >&2; exit 23; }
[[ ! -e "$RUNTIME/uv/uv" ]] || { echo 'uv binary already exists; inspect before continuing' >&2; exit 24; }

curl --fail --location --silent --show-error --max-time 120 'https://github.com/astral-sh/uv/releases/download/0.12.19/uv-x86_64-unknown-linux-gnu.tar.gz' --output "$UV_ARCHIVE"
echo "$UV_SHA  $UV_ARCHIVE" | sha256sum --check --status
mkdir "$RUNTIME/uv"
tar --no-same-owner --no-same-permissions -xzf "$UV_ARCHIVE" --strip-components=1 -C "$RUNTIME/uv"
rm -f -- "$UV_ARCHIVE"
export UV_CACHE_DIR="$SCRATCH/uv-cache"
"$RUNTIME/uv/uv" venv --clear --python /usr/bin/python3 "$TASK/venv"
(cd "$TASK/source" && "$RUNTIME/uv/uv" pip install --python "$TASK/venv/bin/python" --no-cache '.[headless]' 'mcp==1.30.0' 'requests==2.34.2' 'pyghidra==3.1.0' 'JPype1==1.5.2')

python3 - "$UV_CACHE_DIR" "$SCRATCH" <<'PY'
import pathlib, shutil, sys
cache, scratch = map(pathlib.Path, sys.argv[1:])
if cache.exists():
    if cache.parent.resolve() != scratch.resolve() or cache.name != 'uv-cache':
        raise SystemExit('refusing to remove a cache outside this task scratch')
    shutil.rmtree(cache)
PY

GHIDRA_BYTES=$(du -s -B1 "$RUNTIME" | awk '{print $1}')
PERSISTENT_BYTES=$(du -s -B1 "$TASK" | awk '{print $1}')
if (( GHIDRA_BYTES > 1500000000 || PERSISTENT_BYTES > 200000000 )); then
  echo "size limit exceeded: runtime=$GHIDRA_BYTES persistent=$PERSISTENT_BYTES" >&2
  exit 25
fi
{
  echo "ghidra_sha256=ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db"
  echo "temurin_sha256=ce79869e1307ed8ee1e2baa86a412b1eb5b75d10a01006d788a6f968bcfaee94"
  echo "ghidramcp_release_sha256=ebf904fd6782e429e95a60a24fe0724b20c0acb2dedb304135a5281f6b5f2e72"
  echo "ghidramcp_source_commit=$MCP_COMMIT"
  echo "uv_sha256=$UV_SHA"
  echo "runtime_bytes=$GHIDRA_BYTES"
  echo "persistent_task_bytes=$PERSISTENT_BYTES"
  echo "runtime_root=$RUNTIME"
  echo "persistent_root=$TASK"
  echo "uid=$(id -u)"
  echo "profile=$(cat /proc/self/attr/current 2>/dev/null || true)"
  TZ=Asia/Seoul date --iso-8601=seconds
  "$RUNTIME/jdk/bin/java" -version 2>&1
  "$RUNTIME/uv/uv" --version
  "$TASK/venv/bin/ghidra-mcp" --help
  "$RUNTIME/uv/uv" pip freeze --python "$TASK/venv/bin/python"
} > "$TASK/logs/install-manifest.txt"
sha256sum "$TASK/artifacts/GhidraMCP.jar" "$TASK/artifacts/ghidra_mcp-2.0.0-py3-none-any.whl" > "$TASK/logs/artifact-sha256.txt"
echo "runtime_bytes=$GHIDRA_BYTES persistent_bytes=$PERSISTENT_BYTES"
