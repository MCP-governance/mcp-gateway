"""Compare the committed MCP contract lock with what the servers advertise now.

    python3 tests/contracts_check.py registry/contracts.lock.json <fresh-lock.json>

`./console.sh contracts --check` produces the fresh lock from the running servers.
Exit 1 lists every server/tool whose package, version, description or schema moved.
The Gateway enforces the same comparison per call (MCP-CATALOG-001); this is the
offline view for a reviewer deciding whether to run `contracts --update`.
"""
import json
import sys


def diff(committed: dict, current: dict) -> list[str]:
    out = []
    old, new = committed.get("servers", {}), current.get("servers", {})
    for sid in sorted(set(old) | set(new)):
        if sid not in new:
            out.append(f"{sid}: 잠금에는 있으나 지금 카탈로그에 없음")
            continue
        if sid not in old:
            out.append(f"{sid}: 잠금에 없는 새 서버")
            continue
        a, b = old[sid], new[sid]
        for key in ("package", "server_version", "protocol_version"):
            if a.get(key) != b.get(key):
                out.append(f"{sid}: {key} {a.get(key)} → {b.get(key)}")
        ta, tb = a.get("tools", {}), b.get("tools", {})
        out += [f"{sid}.{t}: 새로 광고된 도구" for t in sorted(set(tb) - set(ta))]
        out += [f"{sid}.{t}: 광고에서 사라진 도구" for t in sorted(set(ta) - set(tb))]
        for t in sorted(set(ta) & set(tb)):
            for field in ("description_sha256", "schema_sha256"):
                if ta[t].get(field) != tb[t].get(field):
                    out.append(f"{sid}.{t}: {field.split('_')[0]} 변경")
    return out


def main(committed_path: str, current_path: str) -> int:
    with open(committed_path, encoding="utf-8") as a, open(current_path, encoding="utf-8") as b:
        changes = diff(json.load(a), json.load(b))
    if not changes:
        print("계약 일치: 모든 서버의 패키지·버전·도구 설명·스키마가 잠금과 같습니다.")
        return 0
    print(f"계약 변경 {len(changes)}건 — 검토 후 ./console.sh contracts --update")
    for change in changes:
        print(f"  - {change}")
    return 1


if __name__ == "__main__":
    if len(sys.argv) == 3:
        sys.exit(main(sys.argv[1], sys.argv[2]))
    lock = {"servers": {"s": {"package": "p@1", "tools": {"t": {"description_sha256": "a", "schema_sha256": "b"}}}}}
    moved = {"servers": {"s": {"package": "p@2", "tools": {"t": {"description_sha256": "x", "schema_sha256": "b"}}}}}
    assert diff(lock, lock) == []
    assert diff(lock, moved) == ["s: package p@1 → p@2", "s.t: description 변경"]
    print("self-check ok")
