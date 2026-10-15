"""Root collector of actual AppArmor/nftables denials for one managed UID.

Received events are device observations, not attestation against compromised root.
No argument strings, environment variables, tokens or raw journal text are sent.
"""
import argparse
import importlib.util
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


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
        details = {"source_ip": fields.get("SRC", ""), "destination_ip": fields.get("DST", ""),
                   "protocol": fields.get("PROTO", ""), "destination_port": fields.get("DPT", "")}
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
    command = ["journalctl", "-k", "-o", "json", "--no-pager"]
    command += ["--after-cursor", cursor.read_text().strip()] if cursor.exists() else ["--since", "-1 hour"]
    state, count, error = "success", 0, ""
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
            if len(batch) == 100:
                agent.call("POST", "/api/endpoint/os-events", {"endpoint_id": agent.endpoint_id(), "events": batch})
                count += len(batch)
                batch.clear()
        if batch:
            agent.call("POST", "/api/endpoint/os-events", {"endpoint_id": agent.endpoint_id(), "events": batch})
            count += len(batch)
        if last:
            temporary = cursor.with_suffix(".tmp")
            temporary.write_text(last)
            temporary.chmod(0o600)
            temporary.replace(cursor)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        state, error = "failed", "journal_or_delivery_failed"
    try:
        agent.report_status("os", state, min(count, 500), error)
    except (OSError, ValueError, subprocess.SubprocessError):
        state, error = "failed", "delivery_failed"
    print(json.dumps({"observation": {"os": {"state": state, "accepted_count": min(count, 500), "error_code": error}}}), flush=True)
    if state == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
