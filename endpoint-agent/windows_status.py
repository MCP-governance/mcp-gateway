"""Credential-free local tray snapshot; never a source of authorization decisions."""
import importlib.util
import json
import os
import time
from pathlib import Path

spec = importlib.util.spec_from_file_location("kit_screen", Path(__file__).with_name("kit_screen.py"))
screen_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screen_module)

# What the tray may show beside the connection (D-239): names and versions only, never a key or token.
DETAILS = {"state", "servers", "server_names", "mode", "harnesses", "gateway", "protected_configs"}


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


def render(document, now=None, language="ko"):
    """The same status as the tray, as text for a console (python windows_status.py <status.json>)."""
    now = time.time() if now is None else now
    age = now - float(document.get("updated") or 0)
    connected = bool(document.get("connected")) and 0 <= age <= 150
    servers = document.get("server_names") or document.get("servers") or []
    versions = document.get("harnesses") or {}
    t = lambda value: screen_module.translate(value, language)
    return "\n".join([
        t("연결 상태: ") + t("연결됨" if connected else "연결 끊김"),
        t("관리 상태: ") + t(screen_module.STATES.get(document.get("state"), document.get("management") or "—")),
        t("연결 방식: ") + t({"simple": "간편 모드 (게이트웨이 판정)", "isolated": "격리 계정"}.get(document.get("mode"), "—")),
        t("승인 서버: ") + (t(f"{len(servers)}개 · ") + ", ".join(servers) if servers else "—"),
        t("하네스: ") + (", ".join(f"{k} {v or t('설치됨')}" for k, v in sorted(versions.items())) or "—"),
        t("최근 보고: ") + (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(document["updated"])) if document.get("updated") else "—"),
    ]) + "\n"


def main():
    import argparse
    import subprocess
    import sys
    access = None
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-") and not sys.argv[1].lower().endswith(".json"):
        spec = importlib.util.spec_from_file_location("kit_access", Path(__file__).with_name("kit_access.py"))
        access = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(access)
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sid = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True).stdout.strip().split(",")[-1].strip('"')
        settings_path = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "MCPGatewayManagedTray" / sid / "settings.json"
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            status_path = Path(settings["status_path"])
        except (OSError, ValueError, KeyError):
            print("이 계정에 설치된 엔드포인트가 없습니다")
            raise SystemExit(1)

        def probe():
            try:
                done = subprocess.run([sys.executable, "-X", "utf8", "-B", "-I", "-S", str(Path(__file__).with_name("managed-windows.py")),
                                       "probe", "--settings", str(settings_path)], capture_output=True, text=True, encoding="utf-8",
                                      timeout=180, check=True)
                return screen_module.check_cells(json.loads(done.stdout.strip().splitlines()[-1]))
            except (OSError, ValueError, IndexError, subprocess.SubprocessError):
                return [("하네스 응답", "실패"), ("게이트웨이 MCP 목록", "실패")]
        raise SystemExit(access.mint_command(
            sys.argv[1:], "\\\\.\\pipe\\mcpgw-" + str(settings.get("user", "")).lower() + "-source",
            lambda: render(json.loads(status_path.read_text(encoding="utf-8"))).splitlines(), probe))
    parser = argparse.ArgumentParser(prog="mint", description="MINT 엔드포인트 상태 화면",
                                     epilog="명령: servers · logs · request · login · ui  (mint <명령> -h)")
    parser.add_argument("status", type=Path, nargs="?", help=argparse.SUPPRESS)
    parser.add_argument("--settings", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--probe", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--check", action="store_true", help="게이트웨이 연결 확인")
    parser.add_argument("--language", choices=("ko", "en"), default="ko")
    args = parser.parse_args()
    for stream in (sys.stdout,):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if args.status is None:
        # `mint` typed in a terminal: the signed-in account's own tray folder, as the tray opens it.
        sid = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True).stdout.strip().split(",")[-1].strip('"')
        args.settings = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "MCPGatewayManagedTray" / sid / "settings.json"
        try:
            args.status = Path(json.loads(args.settings.read_text(encoding="utf-8"))["status_path"])
        except (OSError, ValueError, KeyError):
            print(screen_module.translate("이 계정에 설치된 엔드포인트가 없습니다", args.language))
            raise SystemExit(1)
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

    if args.check:
        print(render(json.loads(args.status.read_text(encoding="utf-8")), language=args.language), end="")
        for label, value in check(None):
            print(f"{screen_module.translate(label, args.language)}: {screen_module.translate(value, args.language)}")
        return
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(render(json.loads(args.status.read_text(encoding="utf-8")), language=args.language), end="")
        return
    if args.settings is None:
        for name in ("settings.json", "tray-settings.json"):
            if args.status.with_name(name).is_file():
                args.settings = args.status.with_name(name)
                break
    screen = screen_module.Screen(language=args.language)
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

    try:
        def sources():
            settings = json.loads(args.settings.read_text(encoding="utf-8")) if args.settings else {}
            return screen_module.source_menu("\\\\.\\pipe\\mcpgw-" + settings.get("user", "").lower() + "-source")
        screen_module.live(read, check, screen, sources=sources)
    finally:
        screen.stop()


if __name__ == "__main__":
    main()
