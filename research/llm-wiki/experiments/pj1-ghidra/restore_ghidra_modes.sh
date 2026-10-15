#!/usr/bin/env bash
set -euo pipefail
TASK=/home/pj1/mcpgw-ghidra-20261014
SCRATCH=/dev/shm/mcpgw-ghidra-20261014
GHIDRA_ROOT="$SCRATCH/runtime/ghidra"
ZIP="$SCRATCH/ghidra-mode-source.zip"
EXPECTED=ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db

[[ "$(id -u)" == 1000 && "$(id -un)" == pj1 ]] || { echo 'wrong uid' >&2; exit 20; }
[[ -d "$GHIDRA_ROOT/support" ]] || { echo 'missing task runtime' >&2; exit 21; }
curl --fail --location --silent --show-error --max-time 300 'https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.4_build/ghidra_12.1.4_PUBLIC_20260921.zip' --output "$ZIP"
echo "$EXPECTED  $ZIP" | sha256sum --check --status
python3 - "$ZIP" "$GHIDRA_ROOT" "$TASK/logs/ghidra-executable-modes.json" <<'PY'
import hashlib, json, pathlib, stat, sys
from datetime import datetime
from zoneinfo import ZoneInfo
archive, root, out = map(pathlib.Path, sys.argv[1:])
changed = []
with __import__('zipfile').ZipFile(archive) as zf:
    for entry in zf.infolist():
        mode = entry.external_attr >> 16
        if not stat.S_ISREG(mode) or not mode & 0o111:
            continue
        parts = pathlib.PurePosixPath(entry.filename).parts
        if not parts or parts[0] != 'ghidra_12.1.4_PUBLIC':
            raise SystemExit(f'unexpected Ghidra archive root: {entry.filename}')
        relative = pathlib.Path(*parts[1:])
        target = (root / relative).resolve()
        if target != root.resolve() and root.resolve() not in target.parents:
            raise SystemExit(f'unsafe archive path: {entry.filename}')
        if target.is_file() and not target.is_symlink():
            target.chmod(mode & 0o777)
            changed.append({'path': relative.as_posix(), 'mode': oct(mode & 0o777)})
required = ['support/analyzeHeadless', 'ghidraRun']
missing = [name for name in required if not (root / name).is_file() or not (root / name).stat().st_mode & 0o111]
record = {
    'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    'mode_entries_applied': len(changed),
    'required_launchers': required,
    'required_launchers_executable': not missing,
    'missing_launchers': missing,
    'applied': changed,
    'time_kst': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
}
out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
if missing:
    raise SystemExit(f'missing executable launcher metadata: {missing}')
print(json.dumps({k: record[k] for k in ('sha256', 'mode_entries_applied', 'required_launchers_executable', 'time_kst')}))
PY
rm -f -- "$ZIP"
test ! -e "$ZIP"
