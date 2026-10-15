#!/usr/bin/env bash
set -euo pipefail

# PJ1 one-shot, user-only Ghidra runtime bootstrap. Ghidra and JDK stay in
# /dev/shm due to low persistent free space; evidence is durable.
TASK=/home/pj1/mcpgw-ghidra-20261014
SCRATCH=/dev/shm/mcpgw-ghidra-20261014
RUNTIME="$SCRATCH/runtime"
GHIDRA_SHA=ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db
JDK_SHA=ce79869e1307ed8ee1e2baa86a412b1eb5b75d10a01006d788a6f968bcfaee94
MCP_RELEASE_SHA=ebf904fd6782e429e95a60a24fe0724b20c0acb2dedb304135a5281f6b5f2e72
MCP_COMMIT=1e980252087b2479a21b9ca6d82d5829538651a7
UV_SHA=23bf5552d220e0842b65c862097b2ebaeba0064b74eda5e565e77fd25969d8c8

if [[ "$(id -u)" != 1000 || "$(id -un)" != pj1 ]]; then
  echo 'Refusing to install unless running as pj1 UID 1000' >&2
  exit 20
fi
if [[ -e "$TASK" || -e "$SCRATCH" ]]; then
  echo 'Task directory already exists; inspect it before rerunning' >&2
  exit 21
fi
if [[ "$(df -B1 --output=avail /dev/shm | tail -1 | tr -d ' ')" -lt 1700000000 ]]; then
  echo 'Insufficient /dev/shm space for staged official archives' >&2
  exit 22
fi
mkdir -m 700 -p "$TASK/logs" "$TASK/venv" "$TASK/source" "$TASK/artifacts"
mkdir -m 700 -p "$SCRATCH" "$RUNTIME" "$SCRATCH/tmp"
export TMPDIR="$SCRATCH/tmp"

GHIDRA_ZIP="$SCRATCH/ghidra.zip"
GHIDRA_STAGE="$SCRATCH/ghidra-stage"
curl --fail --location --silent --show-error --max-time 300 'https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.4_build/ghidra_12.1.4_PUBLIC_20260921.zip' --output "$GHIDRA_ZIP"
echo "$GHIDRA_SHA  $GHIDRA_ZIP" | sha256sum --check --status
mkdir "$GHIDRA_STAGE"
python3 - "$GHIDRA_ZIP" "$GHIDRA_STAGE" <<'PY'
import pathlib, stat, sys, zipfile
archive, destination = map(pathlib.Path, sys.argv[1:])
root = destination.resolve()
with zipfile.ZipFile(archive) as zf:
    for member in zf.infolist():
        target = (destination / member.filename).resolve()
        if target != root and root not in target.parents:
            raise SystemExit(f"unsafe archive path: {member.filename}")
    zf.extractall(destination)
    for member in zf.infolist():
        mode = member.external_attr >> 16
        target = destination / member.filename
        if stat.S_ISREG(mode) and mode & 0o111 and target.is_file() and not target.is_symlink():
            target.chmod(mode & 0o777)
PY
rm -f -- "$GHIDRA_ZIP"
mv "$GHIDRA_STAGE/ghidra_12.1.4_PUBLIC" "$RUNTIME/ghidra"
rmdir "$GHIDRA_STAGE"

JDK_ARCHIVE="$SCRATCH/temurin21.tar.gz"
curl --fail --location --silent --show-error --max-time 300 'https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk_x64_linux_hotspot_21.0.12.1_1.tar.gz' --output "$JDK_ARCHIVE"
echo "$JDK_SHA  $JDK_ARCHIVE" | sha256sum --check --status
mkdir "$RUNTIME/jdk"
tar --no-same-owner --no-same-permissions -xzf "$JDK_ARCHIVE" --strip-components=1 -C "$RUNTIME/jdk"
rm -f -- "$JDK_ARCHIVE"

MCP_ARCHIVE="$SCRATCH/ghidramcp-release.zip"
curl --fail --location --silent --show-error --max-time 120 'https://github.com/LaurieWired/GhidraMCP/releases/download/2.0/GhidraMCP-release-2-0.zip' --output "$MCP_ARCHIVE"
echo "$MCP_RELEASE_SHA  $MCP_ARCHIVE" | sha256sum --check --status
python3 - "$MCP_ARCHIVE" "$TASK/artifacts" <<'PY'
import hashlib, pathlib, sys, zipfile
archive, destination = map(pathlib.Path, sys.argv[1:])
with zipfile.ZipFile(archive) as outer:
    extension = next(n for n in outer.namelist() if n.endswith('_GhidraMCP.zip'))
    wheel = next(n for n in outer.namelist() if n.endswith('.whl'))
    wheel_path = destination / pathlib.Path(wheel).name
    wheel_path.write_bytes(outer.read(wheel))
    with zipfile.ZipFile(outer.open(extension)) as inner:
        jar = next(n for n in inner.namelist() if n.endswith('/GhidraMCP.jar'))
        jar_path = destination / 'GhidraMCP.jar'
        jar_path.write_bytes(inner.read(jar))
print('wheel_sha256=' + hashlib.sha256(wheel_path.read_bytes()).hexdigest())
print('extension_jar_sha256=' + hashlib.sha256(jar_path.read_bytes()).hexdigest())
PY
rm -f -- "$MCP_ARCHIVE"

git -C "$TASK/source" init -q
git -C "$TASK/source" remote add origin https://github.com/LaurieWired/GhidraMCP.git
git -C "$TASK/source" fetch --quiet --depth=1 origin "$MCP_COMMIT"
git -C "$TASK/source" checkout --quiet --detach FETCH_HEAD
[[ "$(git -C "$TASK/source" rev-parse HEAD)" == "$MCP_COMMIT" ]]
UV_ARCHIVE="$SCRATCH/uv.tar.gz"
curl --fail --location --silent --show-error --max-time 120 'https://github.com/astral-sh/uv/releases/download/0.12.19/uv-x86_64-unknown-linux-gnu.tar.gz' --output "$UV_ARCHIVE"
echo "$UV_SHA  $UV_ARCHIVE" | sha256sum --check --status
mkdir "$RUNTIME/uv"
tar --no-same-owner --no-same-permissions -xzf "$UV_ARCHIVE" --strip-components=1 -C "$RUNTIME/uv"
rm -f -- "$UV_ARCHIVE"
"$RUNTIME/uv/uv" venv --clear --python /usr/bin/python3 "$TASK/venv"
(cd "$TASK/source" && "$RUNTIME/uv/uv" pip install --python "$TASK/venv/bin/python" --no-cache '.[headless]' 'mcp==1.30.0' 'requests==2.34.2' 'pyghidra==3.1.0' 'JPype1==1.5.2')

GHIDRA_BYTES=$(du -s -B1 "$RUNTIME" | awk '{print $1}')
PERSISTENT_BYTES=$(du -s -B1 "$TASK" | awk '{print $1}')
if (( GHIDRA_BYTES > 1500000000 || PERSISTENT_BYTES > 200000000 )); then
  echo "size limit exceeded: runtime=$GHIDRA_BYTES persistent=$PERSISTENT_BYTES" >&2
  exit 23
fi
{
  echo "ghidra_sha256=$GHIDRA_SHA"
  echo "temurin_sha256=$JDK_SHA"
  echo "ghidramcp_release_sha256=$MCP_RELEASE_SHA"
  echo "uv_sha256=$UV_SHA"
  echo "ghidramcp_commit=$MCP_COMMIT"
  echo "ghidra_runtime_bytes=$GHIDRA_BYTES"
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
echo "installed=$TASK runtime_bytes=$GHIDRA_BYTES persistent_bytes=$PERSISTENT_BYTES"
