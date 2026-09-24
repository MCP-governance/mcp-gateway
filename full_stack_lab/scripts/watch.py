"""Follow Gateway decisions as readable lines: `./console.sh watch`.

    10:31:05  차단   권노경(협력사 A) @ws-nkk · filesystem.read_text_file /shared/confidential/... [P-333-DENY-001] ...
"""
import json
import sys
import time
import urllib.request

GATEWAY = "http://127.0.0.1:8080"
COLOR = {"ok": "\033[32m", "warn": "\033[33m", "info": "\033[36m", "hold": "\033[35m", "stop": "\033[31m"}


def fetch(token: str, after: int) -> dict:
    request = urllib.request.Request(f"{GATEWAY}/api/activity?after={after}&limit=100",
                                     headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def main() -> int:
    token = sys.argv[1]
    color = sys.stdout.isatty()
    after = 0
    print("Gateway 판정 흐름 — Ctrl+C로 종료", flush=True)
    first = fetch(token, 0)  # the last screenful for context
    rows, after = first["rows"][-20:], first["cursor"]
    while True:
        for row in rows:
            line = row["line"]
            print(f"{COLOR.get(row['tone'], '')}{line}\033[0m" if color else line, flush=True)
        time.sleep(2)
        try:
            data = fetch(token, after)
        except Exception as exc:  # gateway restarting: keep following
            print(f"(연결 대기: {exc})", file=sys.stderr, flush=True)
            time.sleep(3)
            continue
        rows, after = data["rows"], data["cursor"]


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
