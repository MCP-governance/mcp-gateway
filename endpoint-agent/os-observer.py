"""Root collector of actual AppArmor/nftables denials for one managed UID.

Received events are device observations, not attestation against compromised root.
No argument strings, environment variables, tokens or raw journal text are sent.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

try:
    from offline_buffer import BufferFull, EventBuffer, flush
except ModuleNotFoundError:  # Imported by the source-check harness, which loads this file by path.
    _buffer_spec = importlib.util.spec_from_file_location("endpoint_offline_buffer", Path(__file__).with_name("offline_buffer.py"))
    if _buffer_spec is None or _buffer_spec.loader is None:
        raise
    _buffer_module = importlib.util.module_from_spec(_buffer_spec)
    _buffer_spec.loader.exec_module(_buffer_module)
    BufferFull, EventBuffer, flush = _buffer_module.BufferFull, _buffer_module.EventBuffer, _buffer_module.flush


# Claude Code and Codex start `git` and re-run themselves on every launch, and the profile refuses
# both. That is the harness starting, not someone reaching around the Gateway. A denial counts as
# startup only when the process that tried is the harness itself and the target is one of its own
# helpers outside user-writable directories; any other exec is a blocked attempt, and a record
# without a process or with another operation cannot be told apart.
HARNESS_PARENTS = {"claude", "codex"}
HARNESS_HELPERS = {"git", "claude", "codex"}
USER_WRITABLE = ("/tmp/", "/var/tmp/", "/dev/shm/", "/home/", "/run/user/")


def denial_class(operation: str, path: str, parent: str) -> str:
    if operation != "exec" or not parent:
        return "unknown"
    if parent in HARNESS_PARENTS and Path(path).name in HARNESS_HELPERS and not path.startswith(USER_WRITABLE):
        return "harness_startup"
    return "blocked_attempt"


_AGENT = None


def load_agent():
    global _AGENT
    if _AGENT is None:
        spec = importlib.util.spec_from_file_location("agent", Path(__file__).with_name("agent.py"))
        _AGENT = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_AGENT)
    return _AGENT


def event(record: dict, uid: int, profile: str, raw_line: str | None = None) -> dict | None:
    message = record.get("MESSAGE", "")
    details = None
    denied = "unknown"
    steps = ["journal_field_allowlist", "drop_raw_message"]
    if f'MCPGW_DENY uid={uid} ' in message:
        fields = dict(re.findall(r"\b(SRC|DST|PROTO|SPT|DPT)=([^ ]+)", message))
        flags = sorted(set(re.findall(r"\b(SYN|ACK|FIN|RST|PSH|URG)\b", message)))
        details = {"source_ip": fields.get("SRC", ""), "destination_ip": fields.get("DST", ""),
                   "protocol": fields.get("PROTO", ""), "destination_port": fields.get("DPT", ""),
                   "source_port": fields.get("SPT", ""), "tcp_flags": " ".join(flags)}
        # A SYN-ACK leaving the managed account answers a connection someone else opened to a
        # listener the harness runs (Codex's login callback, DEV-35): not a connection attempt.
        # Without SPT and the flags the 10-15 log read as "connections to ephemeral ports".
        if "SYN" in flags:
            denied = "listener_reply" if "ACK" in flags else "blocked_attempt"
        kind, collector = "network-denied", "journal-nft"
    elif 'apparmor="DENIED"' in message and f"fsuid={uid} " in message:
        fields = dict(re.findall(r'(operation|profile|name|denied_mask|comm)="([^"]*)"', message))
        if fields.get("profile") != profile and not fields.get("profile", "").startswith(profile + "-"):
            return None
        details = {"operation": fields.get("operation", ""), "profile": fields["profile"],
                   "executable": Path(fields.get("name", "")).name, "denied_mask": fields.get("denied_mask", "")}
        if fields.get("comm"):
            details["parent_executable"] = fields["comm"][:64]
        denied = denial_class(fields.get("operation", ""), fields.get("name", ""), fields.get("comm", ""))
        kind, collector = "execution-denied", "journal-apparmor"
        steps.append("path_to_basename")
    if details is None:
        return None
    found = {"event_id": record["_BOOT_ID"] + ":" + record["__CURSOR"],
             "observed_at": datetime.fromtimestamp(int(record["__REALTIME_TIMESTAMP"]) / 1e6, timezone.utc).isoformat(),
             "kind": kind, "details": details, "denial_class": denied}
    return load_agent().seal_os_event(found, raw_line if raw_line is not None else json.dumps(record, sort_keys=True),
                                      collector, steps)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--uid", type=int, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        sample = {"_BOOT_ID": "boot", "__CURSOR": "cursor", "__REALTIME_TIMESTAMP": "1700000000000000",
                  "MESSAGE": 'apparmor="DENIED" operation="exec" profile="mcpgw-u" name="/usr/bin/git" pid=7 comm="claude" fsuid=1001 ouid=0'}
        assert event(sample, 1001, "mcpgw-u")["details"]["executable"] == "git"
        assert event(sample, 1001, "mcpgw-u")["denial_class"] == "harness_startup"
        assert event(sample, 1001, "mcpgw-u")["details"]["parent_executable"] == "claude"
        assert denial_class("exec", "/usr/bin/curl", "bash") == "blocked_attempt"
        assert denial_class("exec", "/usr/bin/git", "bash") == "blocked_attempt"
        assert denial_class("exec", "/tmp/git", "claude") == "blocked_attempt"
        assert denial_class("exec", "/usr/bin/git", "") == "unknown" and denial_class("file_inherit", "/x", "claude") == "unknown"
        assert event(sample, 1002, "mcpgw-u") is None
        reply = {**sample, "MESSAGE": "MCPGW_DENY uid=1001 IN= OUT=lo SRC=127.0.0.1 DST=127.0.0.1 PROTO=TCP"
                                      " SPT=1455 DPT=46846 WINDOW=65483 RES=0x00 ACK SYN URGP=0"}
        found = event(reply, 1001, "mcpgw-u")
        assert found["denial_class"] == "listener_reply" and found["details"]["source_port"] == "1455"
        assert found["details"]["tcp_flags"] == "ACK SYN"
        attempt = {**reply, "MESSAGE": reply["MESSAGE"].replace("SPT=1455 DPT=46846", "SPT=40000 DPT=3015")
                                                       .replace("ACK SYN", "SYN")}
        assert event(attempt, 1001, "mcpgw-u")["denial_class"] == "blocked_attempt"
        assert event(sample, 1001, "mcpgw-v") is None
        print("OS observation parser check OK")
        return
    if os.geteuid() != 0 or args.uid < 1000:
        parser.error("root로 실제 일반 계정 UID를 지정하세요")
    for path in (Path(__file__).resolve(), args.config.resolve()):
        if any(p.stat().st_uid != 0 or p.stat().st_mode & 0o022 for p in (path, *path.parents)):
            parser.error("프로그램·설정·상위 경로가 root 관리 경로여야 합니다")
    agent = load_agent()
    agent.validate_gateway()
    cursor = args.config.with_suffix(".journal-cursor")
    buffer_cursor = args.config.with_suffix(".journal-buffer-cursor")
    buffer = EventBuffer(args.config.with_suffix(".os-buffer.jsonl"))
    sent = 0
    delivery_ok = True
    try:
        sent += flush(buffer, lambda batch: agent.call("POST", "/api/endpoint/os-events",
                                                       {"endpoint_id": agent.endpoint_id(), "events": batch}))
    except (OSError, ValueError, subprocess.SubprocessError):
        delivery_ok = False
    command = ["journalctl", "-k", "-o", "json", "--no-pager"]
    command += ["--after-cursor", buffer_cursor.read_text().strip()] if buffer_cursor.exists() else ["--since", "-1 hour"]
    state, count, error = "success", 0, ""
    recent_blocks = []
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=20)
        batch = []
        last = None
        for line in result.stdout.splitlines():
            record = json.loads(line)
            last = record["__CURSOR"]
            found = event(record, args.uid, args.profile, line)
            if found:
                batch.append(found)
                recent_blocks.append({"id": found["event_id"], "at": found["observed_at"]})
                recent_blocks = recent_blocks[-5:]
            if len(batch) == 100:
                buffer.enqueue(batch)
                batch.clear()
        if batch:
            buffer.enqueue(batch)
        try:
            sent += flush(buffer, lambda events: agent.call("POST", "/api/endpoint/os-events",
                                                            {"endpoint_id": agent.endpoint_id(), "events": events}))
            delivery_ok = True
        except (OSError, ValueError, subprocess.SubprocessError):
            delivery_ok = False  # Durable rows remain queued until the Gateway answers.
        if last:
            temporary = buffer_cursor.with_suffix(".tmp")
            temporary.write_text(last)
            temporary.chmod(0o600)
            temporary.replace(buffer_cursor)
    except BufferFull:
        state, error = "partial", "offline_buffer_full"
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        state, error = "failed", "journal_or_delivery_failed"
    pending = buffer.pending()
    if delivery_ok and not pending and buffer_cursor.exists():
        temporary = cursor.with_suffix(".tmp")
        temporary.write_text(buffer_cursor.read_text())
        temporary.chmod(0o600)
        temporary.replace(cursor)
    dropped = buffer.dropped_count()
    if state == "success" and (pending or dropped):
        state, error = "partial", "offline_delivery_pending" if pending else "offline_buffer_dropped"
    count = sent
    try:
        agent.report_status("os", state, min(count, 500), error, **(buffer.drop_report() or {}))
        if dropped:
            buffer.clear_dropped()
    except (OSError, ValueError, subprocess.SubprocessError):
        state, error = "failed", "delivery_failed"
    print(json.dumps({"observation": {"os": {"state": state, "accepted_count": min(count, 500), "error_code": error}},
                      "recent_blocks": recent_blocks}), flush=True)
    if state == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
