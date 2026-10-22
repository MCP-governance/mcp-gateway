"""The in-process Gitleaks library must decide exactly like the gitleaks binary it replaced.

Run inside a gateway image (it ships both the binary and libmcpgw_gitleaks.so):
    docker exec -i <gateway-container> python - < tests/secret_engine_parity_check.py
or with the source mounted: python tests/secret_engine_parity_check.py

Every sample goes through the old path (`gitleaks stdin` with the flags the Gateway
used) and the library on the same scan text; the rule-id sets must be equal. All
tokens are generated here at random and match vendor formats only; none is real.
Also prints per-call latency of both paths. Exit code 1 on any difference.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import statistics
import string
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

if __file__ != "<stdin>":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
sys.path.append("/app")  # inside the gateway image
from app import secret_scan

ALNUM = string.ascii_letters + string.digits
UPPER = string.ascii_uppercase + string.digits


def pick(alphabet: str, n: int) -> str:
    return "".join(secrets.choice(alphabet) for _ in range(n))


def tokens() -> dict[str, str]:
    b64 = string.ascii_letters + string.digits + "+/"
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("=")
    claims = base64.urlsafe_b64encode(json.dumps({"sub": pick(ALNUM, 12), "iat": 1760000000}).encode()).decode().rstrip("=")
    key_body = "\n".join(pick(b64, 64) for _ in range(8))
    return {
        "aws": "AKIA" + pick("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567", 16),
        "aws_secret": pick(b64, 40),
        "github_pat": "ghp_" + pick(ALNUM, 36),
        "github_fine": "github_pat_" + pick(ALNUM + "_", 82),
        "gitlab": "glpat-" + pick(ALNUM + "-_", 20),
        "slack_bot": f"xoxb-{pick(string.digits, 12)}-{pick(string.digits, 13)}-{pick(ALNUM, 24)}",
        "stripe": "sk_live_" + pick(ALNUM, 24),
        "openai": "sk-proj-" + pick(ALNUM + "-_", 74) + "T3BlbkFJ" + pick(ALNUM + "-_", 74),
        "anthropic": "sk-ant-api03-" + pick(ALNUM + "-_", 93) + "AA",
        "gcp": "AIza" + pick(ALNUM + "-_", 35),
        "npm": "npm_" + pick(ALNUM, 36),
        "hf": "hf_" + pick(string.ascii_letters, 34),
        "sendgrid": "SG." + pick(ALNUM + "-_", 22) + "." + pick(ALNUM + "-_", 43),
        "do": "dop_v1_" + pick("0123456789abcdef", 64),
        "shopify": "shpat_" + pick("0123456789abcdef", 32),
        "jwt": f"{header}.{claims}.{pick(ALNUM + '-_', 43)}",
        "rsa": f"-----BEGIN RSA PRIVATE KEY-----\n{key_body}\n-----END RSA PRIVATE KEY-----",
        "generic": pick(ALNUM, 40),
    }


def corpus() -> list[str]:
    t = tokens()
    samples = [
        json.dumps({"query": "select * from orders where id = 7"}),
        json.dumps({"path": "/srv/report.md", "content": "분기 보고서 초안입니다. 담당자 확인 후 배포합니다."}),
        json.dumps({"id": "3f1c9b2e-8a51-4c0d-9d6e-2b7f6a1e4c90", "sha256": pick("0123456789abcdef", 64)}),
        "plain text without anything sensitive " * 20,
        json.dumps({"url": "https://example.com/search?q=mcp+gateway&page=2"}),
    ]
    for name, value in t.items():
        samples += [
            value,
            json.dumps({"config": {f"{name}_token": value}}),
            f'export {name.upper()}_KEY="{value}"',
            f"api_key = {value}\n",
            json.dumps({"url": f"https://api.example.com/v1/items?access_token={quote(value)}&x=1"}),
            json.dumps({"note": base64.b64encode(f"token: {value}".encode()).decode()}),
            json.dumps({"client_secret": value, "aws_secret_access_key": t["aws_secret"]}),
        ]
    samples.append("\n".join(samples[5:40]))
    return samples


def old_path(scan: str) -> list[str]:
    """The previous secret_scan.labels body, verbatim flags and environment."""
    with tempfile.TemporaryDirectory(prefix="mcpgw-secret-") as folder:
        report = Path(folder) / "report.json"
        process = subprocess.run(
            [os.getenv("GITLEAKS_BINARY", "/usr/local/bin/gitleaks"), "stdin", "--no-banner",
             "--redact=100", "--exit-code=0", "--report-format=json", f"--report-path={report}",
             "--ignore-gitleaks-allow"],
            input=scan.encode(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": folder}, timeout=10, cwd="/app" if Path("/app").is_dir() else None)
        if process.returncode != 0:
            raise RuntimeError("gitleaks binary failed")
        return sorted({f["RuleID"] for f in json.loads(report.read_text())})


def slot_check() -> dict:
    """A scan past its time limit keeps its slot until its thread ends; a fifth one waits."""
    import asyncio
    import threading
    gate = threading.Event()
    real, limit = secret_scan.rule_ids, secret_scan.TIMEOUT_SECONDS
    secret_scan.rule_ids, secret_scan.TIMEOUT_SECONDS = (lambda data: gate.wait(10) and []), 0.05

    async def run() -> dict:
        outcomes = await asyncio.gather(*(secret_scan.labels("x" * 10) for _ in range(4)), return_exceptions=True)
        held = secret_scan._slots._value
        try:
            await asyncio.wait_for(secret_scan.labels("x" * 10), 0.2)
            waited = False
        except asyncio.TimeoutError:
            waited = True
        except secret_scan.InspectionUnavailable:
            waited = False
        gate.set()
        await asyncio.sleep(0.3)
        return {"timed_out": sum(isinstance(o, secret_scan.InspectionUnavailable) for o in outcomes),
                "free_while_running": held, "fifth_waited": waited, "free_after": secret_scan._slots._value}
    try:
        return asyncio.run(run())
    finally:
        secret_scan.rule_ids, secret_scan.TIMEOUT_SECONDS = real, limit


def main() -> int:
    slots = slot_check()
    slots_ok = slots == {"timed_out": 4, "free_while_running": 0, "fifth_waited": True, "free_after": 4}
    samples = corpus()
    differences, detected, old_ms, new_ms = [], 0, [], []
    for index, text in enumerate(samples):
        scan = secret_scan.scan_text(text)
        started = time.perf_counter()
        old = old_path(scan)
        old_ms.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        new = sorted(secret_scan.rule_ids(scan.encode()))
        new_ms.append((time.perf_counter() - started) * 1000)
        detected += bool(new)
        if old != new:
            differences.append({"sample": index, "binary": old, "library": new})
    # A failing engine must not read as "nothing found".
    try:
        secret_scan.rule_ids(b"\xff" * 4)
        broken_input_ok = True
    except ValueError:
        broken_input_ok = False
    # A malformed link (urlsplit raises "Invalid IPv6 URL") must not make a document uninspectable.
    malformed_link_ok = secret_scan.scan_text('see http://[::1 or "https://h/p?k=v"').endswith("\nv")

    def stats(values: list[float]) -> dict:
        ordered = sorted(values)
        return {"p50_ms": round(statistics.median(ordered), 2),
                "p95_ms": round(ordered[int(len(ordered) * 0.95) - 1], 2), "max_ms": round(ordered[-1], 2)}

    print(json.dumps({"samples": len(samples), "with_findings": detected, "differences": differences,
                      "binary": stats(old_ms), "library": stats(new_ms), "non_utf8_input_scanned": broken_input_ok,
                      "malformed_link_scanned": malformed_link_ok,
                      "slots": slots},
                     ensure_ascii=False, indent=1))
    return 1 if differences or not detected or not slots_ok or not malformed_link_ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
