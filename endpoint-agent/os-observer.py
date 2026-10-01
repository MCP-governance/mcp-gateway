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
from datetime import UTC, datetime
from pathlib import Path


def event(record: dict, uid: int, profile: str) -> dict | None:
    message = record.get("MESSAGE", "")
    details = None
    if f'MCPGW_DENY uid={uid} ' in message:
        fields = dict(re.findall(r"\b(SRC|DST|PROTO|SPT|DPT)=([^ ]+)", message))
        details = {"source_ip": fields.get("SRC", ""), "destination_ip": fields.get("DST", ""),
                   "protocol": fields.get("PROTO", ""), "destination_port": fields.get("DPT", "")}
        kind = "network-denied"
    elif 'apparmor="DENIED"' in message and f"fsuid={uid} " in message:
        fields = dict(re.findall(r'(operation|profile|name|denied_mask)="([^"]*)"', message))
        if fields.get("profile") != profile and not fields.get("profile", "").startswith(profile + "-"):
            return None
        details = {"operation": fields.get("operation", ""), "profile": fields["profile"],
                   "executable": Path(fields.get("name", "")).name, "denied_mask": fields.get("denied_mask", "")}
        kind = "execution-denied"
    if details is None:
        return None
    return {"event_id": record["_BOOT_ID"] + ":" + record["__CURSOR"],
            "observed_at": datetime.fromtimestamp(int(record["__REALTIME_TIMESTAMP"]) / 1e6, UTC).isoformat(),
            "kind": kind, "details": details}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--uid", type=int, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        sample = {"_BOOT_ID": "boot", "__CURSOR": "cursor", "__REALTIME_TIMESTAMP": "1700000000000000",
                  "MESSAGE": 'apparmor="DENIED" operation="exec" profile="mcpgw-u" name="/usr/bin/git" fsuid=1001 ouid=0'}
        assert event(sample, 1001, "mcpgw-u")["details"]["executable"] == "git"
        assert event(sample, 1002, "mcpgw-u") is None
        assert event(sample, 1001, "mcpgw-v") is None
        print("OS observation parser check OK")
        return
    if os.geteuid() != 0 or args.uid < 1000:
        parser.error("root로 실제 일반 계정 UID를 지정하세요")
    for path in (Path(__file__).resolve(), args.config.resolve()):
        if any(p.stat().st_uid != 0 or p.stat().st_mode & 0o022 for p in (path, *path.parents)):
            parser.error("프로그램·설정·상위 경로가 root 관리 경로여야 합니다")
    spec = importlib.util.spec_from_file_location("agent", Path(__file__).with_name("agent.py"))
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)
    agent.validate_gateway()
    cursor = args.config.with_suffix(".journal-cursor")
    command = ["journalctl", "-k", "-o", "json", "--no-pager"]
    command += ["--after-cursor", cursor.read_text().strip()] if cursor.exists() else ["--since", "-1 hour"]
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=20)
    batch = []
    last = None
    for line in result.stdout.splitlines():
        record = json.loads(line)
        last = record["__CURSOR"]
        found = event(record, args.uid, args.profile)
        if found:
            batch.append(found)
        if len(batch) == 100:
            agent.call("POST", "/api/endpoint/os-events", {"endpoint_id": agent.endpoint_id(), "events": batch})
            batch.clear()
    if batch:
        agent.call("POST", "/api/endpoint/os-events", {"endpoint_id": agent.endpoint_id(), "events": batch})
    if last:
        temporary = cursor.with_suffix(".tmp")
        temporary.write_text(last)
        temporary.chmod(0o600)
        temporary.replace(cursor)
    print("Actual kernel journal received; cursor advances only after successful delivery")


if __name__ == "__main__":
    main()
