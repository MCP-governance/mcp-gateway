"""Operational alert insert shared by the incident timer and the operational response loop."""
from psycopg.types.json import Jsonb

from . import db


async def emit_alert(kind, origin, origin_id, evidence, synthetic=False):
    return await db.fetch_one(
        """INSERT INTO ops_alerts(kind,origin,origin_id,evidence,synthetic) VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT DO NOTHING RETURNING id,synthetic""", (kind, origin, str(origin_id), Jsonb(evidence), synthetic))
