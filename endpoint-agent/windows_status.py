"""Credential-free local tray snapshot; never a source of authorization decisions."""
import json
import os
import time
from pathlib import Path

# What the tray may show beside the connection (D-239): names and versions only, never a key or token.
DETAILS = {"state", "servers", "mode", "harnesses", "gateway", "protected_configs"}


def publish(path, connected, blocks=(), management="", details=None):
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
    document = {"updated": time.time(), "connected": bool(connected), "blocks": recent[-5:], "management": management,
                **{key: value for key, value in (details or {}).items() if key in DETAILS}}
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


def render(document, now=None):
    """The same status as the tray, as text for a console (python windows_status.py <status.json>)."""
    now = time.time() if now is None else now
    age = now - float(document.get("updated") or 0)
    connected = bool(document.get("connected")) and 0 <= age <= 150
    servers = document.get("servers") or []
    versions = document.get("harnesses") or {}
    return "\n".join([
        "연결 상태: " + ("연결됨" if connected else "연결 끊김"),
        "관리 상태: " + (document.get("management") or "—"),
        "연결 방식: " + {"simple": "간편 모드 (게이트웨이 판정)", "isolated": "격리 계정"}.get(document.get("mode"), "—"),
        "승인 서버: " + (f"{len(servers)}개 · " + ", ".join(servers) if servers else "—"),
        "하네스: " + (", ".join(f"{k} {v}" for k, v in sorted(versions.items())) or "—"),
        "최근 보고: " + (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(document["updated"])) if document.get("updated") else "—"),
    ]) + "\n"


def main():
    import argparse
    import importlib.util
    import subprocess
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument("status", type=Path)
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--probe", type=Path)
    args = parser.parse_args()
    for stream in (sys.stdout,):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(render(json.loads(args.status.read_text(encoding="utf-8"))), end="")
        return
    spec = importlib.util.spec_from_file_location("kit_screen", Path(__file__).with_name("kit_screen.py"))
    screen_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(screen_module)
    if args.settings is None:
        for name in ("settings.json", "tray-settings.json"):
            if args.status.with_name(name).is_file():
                args.settings = args.status.with_name(name)
                break
    screen = screen_module.Screen()
    probe_time = None

    def read():
        nonlocal probe_time
        if args.probe:
            try:
                changed = args.probe.stat().st_mtime_ns
                if changed != probe_time:
                    screen.cells = screen_module.check_cells(json.loads(args.probe.read_text(encoding="utf-8")))
                    probe_time = changed
            except (OSError, ValueError):
                pass
        document = json.loads(args.status.read_text(encoding="utf-8"))
        # The Windows service publishes every minute; the tray uses the same 150-second limit.
        if not 0 <= time.time() - (document.get("updated") or 0) <= 150:
            document = {**document, "connected": False}
        return document

    def check(document):
        if args.settings is None:
            return [("하네스 응답", "—"), ("게이트웨이 MCP 목록", "점검 설정 없음")]
        try:
            done = subprocess.run([sys.executable, "-X", "utf8", "-B", "-I", "-S",
                                   str(Path(__file__).with_name("managed-windows.py")), "probe",
                                   "--settings", str(args.settings)], capture_output=True, text=True,
                                  encoding="utf-8", timeout=180, check=True)
            return screen_module.check_cells(json.loads(done.stdout.strip().splitlines()[-1]))
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            return [("하네스 응답", "실패"), ("게이트웨이 MCP 목록", "실패")]

    try:
        screen_module.live(read, check, screen)
    finally:
        screen.stop()


if __name__ == "__main__":
    main()
