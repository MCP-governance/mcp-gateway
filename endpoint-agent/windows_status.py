"""Credential-free local tray snapshot; never a source of authorization decisions."""
import json
import os
import time
from pathlib import Path


def publish(path, connected, blocks=(), management=""):
    path = Path(path)
    recent = []
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
        rows = previous.get("blocks", []) if isinstance(previous, dict) else []
        if isinstance(rows, list):
            recent = [{"id": str(row.get("id", ""))[:180], "at": str(row.get("at", ""))[:40],
                       "label": "엔드포인트에서 차단"} for row in rows[-5:] if isinstance(row, dict)]
    except (OSError, ValueError):
        pass
    for event in blocks:
        if event.get("kind") not in {"execution-denied", "network-denied", "file-denied"}:
            continue
        row = {"id": str(event.get("event_id", ""))[:180], "at": str(event.get("observed_at", ""))[:40],
               "label": "엔드포인트에서 차단"}
        recent = [entry for entry in recent if entry.get("id") != row["id"]] + [row]
    recent.sort(key=lambda entry: entry["at"])
    document = {"updated": time.time(), "connected": bool(connected), "blocks": recent[-5:], "management": management}
    if not path.parent.is_dir():
        raise OSError("tray directory must be provisioned before reporting")
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    # A tray read can overlap the replacement on Windows. Keep the old snapshot on failure.
    try:
        for attempt in range(20):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.05)
    finally:
        temporary.unlink(missing_ok=True)
