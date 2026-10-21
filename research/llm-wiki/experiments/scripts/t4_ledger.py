"""Ledger rows for the T4 window (gateway container). usage: python t4_ledger.py START_ISO END_ISO -> JSON lines"""
import asyncio, json, sys
from app import db


async def main(start, end):
    rows = await db.fetch_all(
        """SELECT id, created_at, server_id, tool_name, decision, policy_id, upstream_attempted, upstream_executed,
                  result_preview->>'disposition' disposition, reason, client->>'workstation' workstation,
                  client->'harness'->>'name' harness, conflicts, privacy_types
           FROM decisions WHERE created_at BETWEEN %s AND %s ORDER BY id""", (start, end))
    for r in rows:
        r["created_at"] = r["created_at"].isoformat()
        print(json.dumps(r, default=str, ensure_ascii=False))

asyncio.run(main(*sys.argv[1:3]))
