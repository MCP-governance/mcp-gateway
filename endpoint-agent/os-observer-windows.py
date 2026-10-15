#!/usr/bin/env python3
"""Read already-enabled Windows denial events for the exact managed SID.

This collector never changes audit policy. WFP events without an event-time user SID are
counted as un-attributable and discarded; PID-to-current-owner lookups are not identity proof.
"""
from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import json
import os
import re
import subprocess
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}
PROVIDER_SECURITY = "Microsoft-Windows-Security-Auditing"
PROVIDER_APPLOCKER = "Microsoft-Windows-AppLocker"
CHANNELS = (
    ("Security", (5152, 5157), "wfp"),
    ("Microsoft-Windows-AppLocker/EXE and DLL", (8004,), "applocker"),
    ("Microsoft-Windows-AppLocker/MSI and Script", (8007,), "applocker"),
    ("Microsoft-Windows-AppLocker/Packaged app-Execution", (8022,), "applocker"),
    ("Microsoft-Windows-AppLocker/Packaged app-Deployment", (8025,), "applocker"),
)
MAX_QUERY = 501
MAX_EVENTS = 500
MAX_BATCH = 100

POWERSHELL_QUERY = r"""$ErrorActionPreference = 'Stop'
$q = $env:MCPGW_QUERY | ConvertFrom-Json
$out = @{ state='success'; events=@(); newest=0; oldest=0; error_code='' }
try {
  $log = Get-WinEvent -ListLog $q.channel -ErrorAction Stop
} catch {
  if ([int]$_.Exception.HResult -eq -2147024891 -or $_.Exception.Message -match 'Access is denied|UnauthorizedAccess') {
    $out.state='unauthorized'; $out.error_code='access_denied'
  } else {
    $out.state='unsupported'; $out.error_code='channel_missing'
  }
  $out | ConvertTo-Json -Compress -Depth 4; exit 0
}
if (-not $log.IsEnabled) {
  $out.state='disabled'; $out.error_code='channel_disabled'
  $out | ConvertTo-Json -Compress -Depth 4; exit 0
}
try {
  $latest = Get-WinEvent -LogName $q.channel -MaxEvents 1 -ErrorAction SilentlyContinue
  if ($latest) { $out.newest=[long]$latest.RecordId }
  if ($log.OldestRecordNumber) { $out.oldest=[long]$log.OldestRecordNumber }
  if ($q.initialize -or ($q.after -gt $out.newest)) {
    $out.reset=([bool](-not $q.initialize))
    $out | ConvertTo-Json -Compress -Depth 4; exit 0
  }
  $idExpr = (@($q.ids | ForEach-Object { 'EventID=' + [int]$_ }) -join ' or ')
  $xpath = '*[System[(' + $idExpr + ') and (EventRecordID > ' + [long]$q.after + ')]]'
  try {
    $rows = @(Get-WinEvent -LogName $q.channel -FilterXPath $xpath -Oldest -MaxEvents 501 -ErrorAction Stop)
    $out.events = @($rows | ForEach-Object { $_.ToXml() })
  } catch {
    if ($_.FullyQualifiedErrorId -notlike 'NoMatchingEventsFound,*') { throw }
  }
  $out | ConvertTo-Json -Compress -Depth 5
} catch {
  $hr = [int]$_.Exception.HResult
  if ($hr -eq -2147024891 -or $_.Exception.Message -match 'Access is denied|UnauthorizedAccess') {
    $out.state='unauthorized'; $out.error_code='access_denied'
  } else {
    $out.state='failed'; $out.error_code='query_failed'
  }
  $out.events=@(); $out | ConvertTo-Json -Compress -Depth 4
}
"""


def _xml_fields(root: ET.Element) -> dict[str, str]:
    fields = {item.attrib.get("Name", ""): item.text or ""
              for item in root.findall(".//e:EventData/e:Data", NS) if item.attrib.get("Name")}
    # AppLocker uses UserData/RuleAndFileData rather than EventData/Data.
    for item in root.findall(".//e:UserData//*", NS):
        name = item.tag.rsplit("}", 1)[-1]
        if item.text and name:
            fields[name] = item.text
    return fields


def parse_event(xml_text: str, channel: str, family: str, managed_sid: str) -> tuple[dict | None, str | None]:
    """Return a safe OS-event contract row and an attribution limitation, if any."""
    try:
        root = ET.fromstring(xml_text)
        system = root.find("e:System", NS)
        if system is None:
            return None, "query_failed"
        provider = system.find("e:Provider", NS)
        event_id_node = system.find("e:EventID", NS)
        record_node = system.find("e:EventRecordID", NS)
        created = system.find("e:TimeCreated", NS)
        channel_node = system.find("e:Channel", NS)
        if not all((provider is not None, event_id_node is not None, record_node is not None,
                    created is not None, channel_node is not None)):
            return None, "query_failed"
        expected_provider = PROVIDER_SECURITY if family == "wfp" else PROVIDER_APPLOCKER
        event_id = int(event_id_node.text or "0")
        record_id = int(record_node.text or "0")
        if provider.attrib.get("Name") != expected_provider or channel_node.text != channel:
            return None, "query_failed"
        timestamp = created.attrib.get("SystemTime", "")
        observed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            return None, "query_failed"
        fields = _xml_fields(root)

        # Only explicit subject/target SID fields qualify. System/Security/@UserID is
        # the event provider context and PID ownership at collection time is not equivalent.
        sid_names = (("SubjectUserSid", "SubjectUserSID", "UserSid", "UserSID") if family == "wfp"
                     else ("TargetUser", "UserSid", "UserSID"))
        event_sid = next((fields[name] for name in sid_names if fields.get(name)), "")
        if not event_sid:
            return None, "sid_unavailable"
        if event_sid.casefold() != managed_sid.casefold():
            return None, None

        if family == "wfp":
            details: dict[str, str | int] = {"source": "windows-wfp", "channel": "Security", "event_id": event_id}
            for field, key in (("SourceAddress", "source_ip"), ("DestAddress", "destination_ip")):
                value = fields.get(field, "")
                try:
                    details[key] = str(ipaddress.ip_address(value))
                except ValueError:
                    pass
            for field, key in (("SourcePort", "source_port"), ("DestPort", "destination_port"), ("Protocol", "protocol")):
                try:
                    value = int(fields.get(field, ""))
                    if field == "Protocol" or 0 <= value <= 65535:
                        details[key] = value
                except ValueError:
                    pass
            kind = "network-denied"
        else:
            channel_kind = channel.rsplit("/", 1)[-1].lower().replace(" ", "-")
            details = {"source": "windows-applocker", "channel": channel_kind, "event_id": event_id}
            file_value = next((fields.get(key, "") for key in ("FilePath", "FileName", "TargetFilePath", "PackageName")
                               if fields.get(key)), "")
            if file_value:
                basename = re.split(r"[\\/]", file_value)[-1][:120]
                if basename:
                    details["application"] = basename
            kind = "execution-denied"
        return {"event_id": f"windows:{channel}:{record_id}", "observed_at": observed.astimezone(timezone.utc).isoformat(),
                "kind": kind, "details": details}, None
    except (ET.ParseError, ValueError, TypeError, OverflowError):
        return None, "query_failed"


def _powershell(config: dict, channel: str, ids: tuple[int, ...], cursor: dict | None) -> dict:
    query = {"channel": channel, "ids": list(ids), "after": int((cursor or {}).get("record_id", 0)),
             "initialize": cursor is None}
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    executable = Path(system_root) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    if not executable.is_file():
        raise FileNotFoundError("powershell_unavailable")
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "PATH") if os.environ.get(key)}
    env["MCPGW_QUERY"] = json.dumps(query, separators=(",", ":"))
    completed = subprocess.run([str(executable), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", POWERSHELL_QUERY],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25, env=env)
    if completed.returncode:
        raise RuntimeError("query_failed")
    try:
        result = json.loads(completed.stdout.strip())
        if not isinstance(result, dict):
            raise ValueError("not_object")
        return result
    except (ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("query_failed") from exc


def _load_agent():
    path = Path(__file__).with_name("agent.py")
    spec = importlib.util.spec_from_file_location("endpoint_agent_windows_observer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("transport_unavailable")
    module = importlib.util.module_from_spec(spec)
    # agent.py uses the protected observer config and owns URL validation + device-key transport.
    spec.loader.exec_module(module)
    return module


def _write_cursor(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, path)


def _report_status(agent: Any, state: str, accepted: int, error_code: str) -> None:
    agent.call("POST", "/api/endpoint/observation-status", {
        "endpoint_id": agent.endpoint_id(), "channel": "os", "state": state,
        "accepted_count": max(0, min(500, accepted)), "error_code": error_code[:48]})


def collect(config_path: Path, self_check: bool = False) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    managed_sid = str(config.get("ENDPOINT_MANAGED_SID", ""))
    if not re.fullmatch(r"S-1-5-(?:\d+-){1,14}\d+", managed_sid):
        raise ValueError("managed_sid_missing")
    agent = _load_agent()
    agent.validate_gateway()
    cursor_path = config_path.with_suffix(".os-cursor.json")
    cursors = json.loads(cursor_path.read_text(encoding="utf-8")) if cursor_path.exists() else {}
    counts: dict[str, int] = {"success": 0, "partial": 0, "failed": 0, "disabled": 0, "unauthorized": 0, "unsupported": 0}
    error_codes: list[str] = []
    accepted = 0
    for channel, ids, family in CHANNELS:
        current = cursors.get(channel)
        try:
            result = _powershell(config, channel, ids, current)
        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError):
            counts["failed"] += 1
            error_codes.append("query_failed")
            continue
        state = result.get("state", "failed")
        if state not in counts:
            state = "failed"
        if state in ("disabled", "unauthorized", "unsupported", "failed"):
            counts[state] += 1
            error_codes.append(str(result.get("error_code") or "query_failed"))
            continue
        if current is None:
            # Establish a live-only baseline; never backfill the account's old event history.
            cursors[channel] = {"record_id": int(result.get("newest", 0)), "epoch": 0}
            _write_cursor(cursor_path, cursors)
            counts["success"] += 1
            continue
        epoch = int(current.get("epoch", 0))
        if result.get("reset"):
            epoch += 1
            current = {"record_id": int(result.get("newest", 0)), "epoch": epoch}
            cursors[channel] = current
            _write_cursor(cursor_path, cursors)
            counts["partial"] += 1
            error_codes.append("cursor_reset")
            continue

        raw_rows = result.get("events", [])
        if not isinstance(raw_rows, list):
            counts["failed"] += 1
            error_codes.append("query_failed")
            continue
        record_ids = []
        try:
            for xml_text in raw_rows:
                record = ET.fromstring(xml_text)
                node = record.find("e:System/e:EventRecordID", NS)
                if node is None or not node.text:
                    raise ValueError("missing_record_id")
                record_ids.append(int(node.text))
        except (ET.ParseError, TypeError, ValueError):
            counts["failed"] += 1
            error_codes.append("query_failed")
            continue
        limited = len(raw_rows) > MAX_EVENTS
        raw_rows = raw_rows[:MAX_EVENTS]
        record_ids = record_ids[:MAX_EVENTS]
        events, missing_sid, malformed = [], 0, 0
        for xml_text in raw_rows:
            if not isinstance(xml_text, str):
                malformed += 1
                continue
            row, issue = parse_event(xml_text, channel, family, managed_sid)
            if issue == "sid_unavailable":
                missing_sid += 1
            elif issue:
                malformed += 1
            elif row:
                row["event_id"] += f":{epoch}"
                events.append(row)
        try:
            for start in range(0, len(events), MAX_BATCH):
                agent.call("POST", "/api/endpoint/os-events", {
                    "endpoint_id": agent.endpoint_id(), "events": events[start:start + MAX_BATCH]})
        except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError):
            counts["failed"] += 1
            error_codes.append("delivery_failed")
            # The cursor is deliberately not committed: a retry may resubmit rows; the endpoint
            # event key (endpoint_id,event_id) is expected to make that idempotent.
            continue

        last_record = record_ids[-1] if record_ids else int(result.get("newest", current.get("record_id", 0)))
        gap = int(result.get("oldest", 0)) > int(current.get("record_id", 0)) + 1
        if limited:
            last_record = record_ids[-1]
        elif gap and not raw_rows:
            last_record = int(result.get("newest", current.get("record_id", 0)))
        cursors[channel] = {"record_id": max(int(current.get("record_id", 0)), last_record), "epoch": epoch}
        _write_cursor(cursor_path, cursors)
        accepted += len(events)
        partial_reasons = []
        if missing_sid:
            partial_reasons.append("sid_unavailable")
        if malformed:
            partial_reasons.append("query_failed")
        if gap:
            partial_reasons.append("cursor_gap")
        if limited:
            partial_reasons.append("batch_limit")
        if partial_reasons:
            counts["partial"] += 1
            error_codes.extend(partial_reasons)
        else:
            counts["success"] += 1

    active = sum(counts.values())
    if counts["failed"] and counts["success"] + counts["partial"] == 0:
        final_state = "failed"
    elif counts["unauthorized"] and counts["success"] + counts["partial"] == 0:
        final_state = "unauthorized"
    elif counts["success"] + counts["partial"]:
        final_state = "partial" if counts["partial"] or counts["failed"] or counts["disabled"] or counts["unauthorized"] or counts["unsupported"] else "success"
    elif counts["disabled"] == active:
        final_state = "disabled"
    elif counts["unsupported"] == active:
        final_state = "unsupported"
    else:
        final_state = "unknown"
    error_code = next((code for code in error_codes if code), "")
    try:
        _report_status(agent, final_state, accepted, error_code)
    except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError):
        final_state, error_code = "failed", "transport_unavailable"
    return {"channel": "os", "state": final_state, "accepted_count": accepted, "error_code": error_code}


def self_check() -> None:
    fixture = '''<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><System><Provider Name="Microsoft-Windows-AppLocker"/><EventID>8004</EventID><TimeCreated SystemTime="2026-10-14T00:00:00.000Z"/><EventRecordID>5</EventRecordID><Channel>Microsoft-Windows-AppLocker/EXE and DLL</Channel></System><EventData><Data Name="TargetUser">S-1-5-21-1-2-3-1001</Data><Data Name="FilePath">C:\\Users\\tester\\blocked.exe</Data></EventData></Event>'''
    accepted, issue = parse_event(fixture, CHANNELS[1][0], "applocker", "S-1-5-21-1-2-3-1001")
    assert issue is None and accepted and accepted["kind"] == "execution-denied"
    assert accepted["details"]["application"] == "blocked.exe"
    assert parse_event(fixture, CHANNELS[1][0], "applocker", "S-1-5-21-1-2-3-1002")[0] is None
    wfp = (f'<Event xmlns="{NS["e"]}"><System><Provider Name="{PROVIDER_SECURITY}"/>'
           '<EventID>5157</EventID><TimeCreated SystemTime="2026-10-14T00:00:00Z"/>'
           '<EventRecordID>6</EventRecordID><Channel>Security</Channel></System><EventData>'
           '<Data Name="ProcessID">45</Data></EventData></Event>')
    no_sid, issue = parse_event(wfp, "Security", "wfp", "S-1-5-21-1-2-3-1001")
    assert no_sid is None and issue == "sid_unavailable"
    print("Windows OS observer parser check OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return
    try:
        summary = collect(args.config)
        print(json.dumps(summary, separators=(",", ":")), flush=True)
    except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
        summary = {"channel": "os", "state": "failed", "accepted_count": 0,
                   "error_code": str(exc) if re.fullmatch(r"[a-z_]{1,48}", str(exc)) else "collector_failed"}
        print(json.dumps(summary, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
