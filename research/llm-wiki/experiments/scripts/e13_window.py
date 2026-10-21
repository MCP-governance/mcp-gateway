"""Appliance evidence for one time window: Gateway decisions and endpoint OS events.

Runs in the gateway container (`app.db`). usage: python e13_window.py START_ISO END_ISO
Prints JSON: decisions (id, server, tool, decision, policy, executed, workstation) and
endpoint_os_events (kind, denial_class, executable/destination fields only).
"""
import asyncio, json, sys
from app import db


async def main(start: str, end: str):
    decisions = await db.fetch_all(
        """SELECT id, created_at, request_payload->>'server_id' server, tool_name, decision, policy_id,
                  upstream_attempted, upstream_executed, client->>'workstation' workstation
           FROM decisions WHERE created_at BETWEEN %s AND %s ORDER BY id""", (start, end))
    events = await db.fetch_all(
        """SELECT id, endpoint_id, observed_at, kind, denial_class,
                  details->>'executable' executable, details->>'operation' operation, details->>'profile' profile,
                  details->>'destination' destination, details->>'daddr' daddr, details->>'dport' dport
           FROM endpoint_os_events WHERE observed_at BETWEEN %s AND %s ORDER BY id""", (start, end))
    print(json.dumps({"window": [start, end], "decisions": decisions, "os_events": events}, default=str, ensure_ascii=False))

asyncio.run(main(sys.argv[1], sys.argv[2]))
