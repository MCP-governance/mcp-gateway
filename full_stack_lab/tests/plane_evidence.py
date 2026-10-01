"""Drive the real Claude Code and Codex MCP clients through a case file and print, per
ledger row, which plane enforced the call and whether anything reached upstream (D-62).

The harnesses are called through their own control APIs, without a model turn:
  codex app-server                              thread/start -> mcpServer/tool/call
  claude -p --input-format stream-json          control_request mcp_call
Nothing here mocks or wraps an MCP server: the harness uses the MCP configuration of the
machine it runs on (managed files under /etc on a managed device). The Console API
(administrator, read only) supplies the ledger rows.

  python3 plane_evidence.py --console URL --cases cases.json --person emp-ysg --exec 'docker exec -i ws-ysg' < admin.json
  SSHPW=... python3 plane_evidence.py --console URL --cases cases.json --person user --ssh managed-pj1@100.110.81.60 < admin.json

admin.json: {"email": "...", "password": "..."}
cases.json: [{"id", "harness": "codex"|"claude", "server", "tool", "arguments", "parallel": 1, "harness_args": [],
              "expect": {"decision": "Block", "policy_id": "PAC-01", "attempted": false, "executed": false,
                         "response": "masked"}}]
One JSON line per ledger row, then a summary line. Exit 1 when an expectation fails.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shlex
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

CLAUDE = ["claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
          "--tools", "", "--permission-mode", "dontAsk", "--allowedTools", "mcp__*",
          "--no-session-persistence", "--setting-sources", ""]


class Harness:
    """One harness process; requests are matched to answers by id."""

    def __init__(self, args, kind: str, extra: list[str] | None = None):
        self.kind, self.seq, self.pending, self.lock = kind, 0, {}, threading.Lock()
        command = shlex.join((["codex", "app-server"] if kind == "codex" else CLAUDE) + (extra or []))
        if args.ssh:
            import paramiko
            user, host = args.ssh.split("@", 1)
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(host, username=user, password=os.environ["SSHPW"], look_for_keys=False,
                             allow_agent=False, timeout=15)
            # A login shell, so the harness is found where the user's own shell finds it (~/.local/bin).
            self.stdin, out, _ = self.ssh.exec_command("bash -lc " + shlex.quote(command), timeout=300)
            lines = out
            self.close_io = lambda: (self.stdin.channel.shutdown_write(), self.ssh.close())
        else:
            self.proc = subprocess.Popen(shlex.split(args.exec) + ["bash", "-lc", command], stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            self.stdin, lines, self.close_io = self.proc.stdin, self.proc.stdout, self.proc.kill
        threading.Thread(target=self._read, args=(lines,), daemon=True).start()

    def _read(self, lines) -> None:
        for line in lines:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if self.kind == "claude":
                if message.get("type") != "control_response":
                    continue
                message = message["response"]
                key = message.get("request_id")
            else:
                key = message.get("id")
            with self.lock:
                future = self.pending.pop(str(key), None)
            if future:
                future.set_result(message)

    def call(self, method: str, params: dict, timeout: float = 150) -> dict:
        with self.lock:
            self.seq += 1
            key, future = str(self.seq), concurrent.futures.Future()
            self.pending[key] = future
        request = ({"type": "control_request", "request_id": key, "request": {"subtype": method, **params}}
                   if self.kind == "claude" else {"jsonrpc": "2.0", "id": key, "method": method, "params": params})
        self.stdin.write(json.dumps(request) + "\n")
        self.stdin.flush()
        return future.result(timeout=timeout)

    def start(self, cwd: str) -> "Harness":
        if self.kind == "claude":
            assert self.call("initialize", {}).get("subtype") == "success"
            # Claude connects MCP servers in the background; a call while a server is still
            # "pending" fails as "not connected" without ever reaching the Gateway.
            for _ in range(40):
                servers = self.call("mcp_status", {}).get("response", {}).get("mcpServers", [])
                if all(s.get("status") != "pending" for s in servers):
                    break
                time.sleep(1)
            return self
        assert "result" in self.call("initialize", {"clientInfo": {"name": "plane-evidence", "version": "1"},
                                                    "capabilities": {"experimentalApi": True}})
        self.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "initialized"}) + "\n")
        self.stdin.flush()
        thread = self.call("thread/start", {"cwd": cwd, "approvalPolicy": "never", "sandbox": "read-only", "ephemeral": True})
        self.thread = thread["result"]["thread"]["id"]
        return self

    def tool(self, server: str, tool: str, arguments: dict) -> dict:
        if self.kind == "claude":
            return self.call("mcp_call", {"tool": f"mcp__{server}__{tool}", "arguments": arguments})
        return self.call("mcpServer/tool/call", {"threadId": self.thread, "server": server, "tool": tool, "arguments": arguments})


def console(base: str, path: str, token: str | None = None, body: dict | None = None, method: str | None = None) -> dict:
    request = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), method=method,
                                     headers={"content-type": "application/json",
                                              **({"authorization": "Bearer " + token} if token else {})})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=30) as response:
        return json.loads(response.read())


def ledger_after(base: str, token: str, cursor: int, person: str, server: str, tool: str, want: int) -> list[dict]:
    """Rows of this principal after the cursor; the call is synchronous, so its row exists
    when the harness answers. Waiting a little longer exposes extra rows instead of hiding them."""
    deadline = time.time() + (8 if want else 40)
    rows: list[dict] = []
    while time.time() < deadline:
        query = urllib.parse.urlencode({"after": cursor, "limit": 200, "person": person})
        found = console(base, f"/gw/activity?{query}", token)["rows"]
        # A refused connection is recorded under the MCP method that was refused
        # (initialize, server/discover, ...), not under the tool name.
        rows = [r for r in found if r.get("principal") == person and r["server"] == server
                and (r["tool"] == tool or r.get("event_kind") == "mcp-connection")]
        if want and len(rows) > want:
            return rows
        time.sleep(1.5)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--console", required=True)
    parser.add_argument("--cases", required=True, type=argparse.FileType("r"))
    parser.add_argument("--cwd", default="/tmp", help="Codex thread working directory on the harness machine")
    parser.add_argument("--person", required=True, help="principal token the harness authenticates as; only its rows count")
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--exec", help="local command prefix that runs a shell on the harness machine")
    where.add_argument("--ssh", help="user@host of the harness machine (password in $SSHPW)")
    args = parser.parse_args()
    base = args.console.rstrip("/")
    token = console(base, "/auth/mock-login", body=json.load(sys.stdin))["access_token"]
    cases, failures = json.load(args.cases), 0
    for case in cases:
        cursor = console(base, "/gw/activity?limit=1", token)["cursor"]
        count = int(case.get("parallel", 1))
        harnesses = [Harness(args, case["harness"], case.get("harness_args")) for _ in range(count)]
        try:
            with concurrent.futures.ThreadPoolExecutor(count) as pool:
                answers = list(pool.map(lambda h: h.start(args.cwd).tool(case["server"], case["tool"], case.get("arguments", {})),
                                        harnesses))
        except Exception as exc:  # a crash, hang or SSH failure is inconclusive, never "not seen"
            answers = [{"error": f"{type(exc).__name__}: {exc}"[:300], "exception": True}]
        finally:
            for harness in harnesses:
                harness.close_io()
        expect_rows = 0 if case.get("expect", {}).get("transport") == "not seen by Gateway" else count
        rows = ledger_after(base, token, cursor, args.person, case["server"], case["tool"], expect_rows)
        expect = case.get("expect", {})
        for row in rows or [{}]:
            evidence = {"case": case["id"], "harness": case["harness"], "target": f"{case['server']}.{case['tool']}",
                        "transport": "streamable-http via Gateway" if row else "not seen by Gateway",
                        "planes": row.get("planes"), "decision": row.get("decision"), "policy_id": row.get("policy_id"),
                        "attempted": row.get("attempted"), "executed": row.get("executed"), "response": row.get("response"),
                        "pac_failures": row.get("pac_failures"), "decision_id": row.get("id"),
                        "evidence_sha256": row.get("evidence_sha256"), "response_sha256": row.get("response_sha256"),
                        "masked_types": row.get("masked_types"), "mock": False}
            mismatch = {k: v for k, v in expect.items() if evidence.get(k) != v}
            if len(rows) != expect_rows:
                mismatch["ledger_rows"] = f"{len(rows)} != {expect_rows}"
            refused = bool(answers) and "error" in answers[0] and not answers[0].get("exception")
            # Not seen by the Gateway counts only when the harness itself answered with a refusal.
            evidence["ok"] = (bool(row) if expect_rows else refused) and not mismatch
            if not row:  # what the harness itself said is the only evidence of where it stopped
                evidence["harness_answer"] = json.dumps(answers[0], ensure_ascii=False)[:600] if answers else None
            if not evidence["ok"]:
                failures += 1
                evidence["mismatch"] = mismatch or "no ledger row"
                evidence["harness_answer"] = json.dumps(answers[0], ensure_ascii=False)[:400] if answers else None
            print(json.dumps(evidence, ensure_ascii=False), flush=True)
    print(json.dumps({"cases": len(cases), "failed_rows": failures}))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
