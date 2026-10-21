"""Gateway-side stage timings (core._Laps, kept in decisions.timings) for one server and time window.
Runs in the gateway container. usage: python t3_timings.py SERVER START_ISO END_ISO  -> JSON lines
"""
import asyncio, json, sys
from app import db


async def main(server, start, end):
    rows = await db.fetch_all(
        """SELECT id, created_at, decision, policy_id, upstream_executed, timings, client->>'workstation' workstation
           FROM decisions WHERE server_id=%s AND created_at BETWEEN %s AND %s ORDER BY id""", (server, start, end))
    for r in rows:
        print(json.dumps(r, default=str))

asyncio.run(main(*sys.argv[1:4]))
