"""일회용 DB에서 제품 코드 경로(review.record_event·ops_response.emit_alert)로 승인 이벤트와 실제 경보를 만들고,
제품 siem.py 전달 루프로 실제 SIEM에 보낸다. 필드 DB의 감사 기록을 만들지 않고 ops_alerts 전달만 확인하는 용도다.
합성 경보는 큐에 들어가지 않아야 한다(출력의 "synthetic excluded").

  docker network create probe-net
  docker run -d --name probe-pg --network probe-net -e POSTGRES_USER=mcp -e POSTGRES_DB=probe -e POSTGRES_PASSWORD=<임의> postgres:18-alpine
  docker exec -i probe-pg psql -U mcp -d probe < db/init.sql
  docker run --rm --network probe-net -v <siem-secrets>:/run/siem:ro -v $PWD/siem/ops_alert_probe.py:/probe.py:ro \
    -e DATABASE_URL=postgresql://mcp:<임의>@probe-pg:5432/probe -e PYTHONPATH=/app -e OTEL_SDK_DISABLED=true \
    -e SIEM_URL=https://<SIEM_BIND>:8688/ingest -e SIEM_TOKEN_FILE=/run/siem/token -e SIEM_CA_FILE=/run/siem/ca.pem \
    -w /app <게이트웨이 이미지> python /probe.py
"""
import asyncio
from pathlib import Path
from app import db, review, ops_response, siem
APP = Path("/app/app")

async def main():
    await db.wait_until_ready()
    for name in ("agent_tables.sql", "lifecycle_tables.sql", "v2_tables.sql", "oidc_tables.sql", "ops_tables.sql", "siem_tables.sql"):
        await db.execute((APP / name).read_text(encoding="utf-8"))
    ev = await review.record_event("t1-real-sink", "recorded", "server", "t1-lab", "t1-lab")
    real = await ops_response.emit_alert("unapproved-connection", "t1-lab", "real-path", {"server_id": "t1-lab"})
    synth = await ops_response.emit_alert("unapproved-connection", "t1-lab", "synthetic-path", {}, synthetic=True)
    print("approval_event", ev, "real_alert", real, "synthetic_alert", synth)
    rows = await db.fetch_all("SELECT id,source,source_id FROM siem_outbox ORDER BY id")
    print("outbox", [(r["source"], r["source_id"]) for r in rows], "(synthetic excluded)" if all(r["source_id"] != synth["id"] or r["source"] != "ops_alerts" for r in rows) else "SYNTH-LEAK")
    config = siem.settings()
    while await siem.deliver_one(config):
        pass
    done = await db.fetch_all("SELECT source,source_id,attempts,last_error,delivered_at IS NOT NULL AS ok FROM siem_outbox ORDER BY id")
    print("delivered", [(r["source"], r["source_id"], r["ok"], r["last_error"]) for r in done])
    for r in rows:
        src = await db.fetch_one(f"SELECT {siem.SOURCE_COLUMNS[r['source']]} FROM {r['source']} WHERE id=%s", (r["source_id"],))
        print("uid", siem.event(r["source"], src)["metadata"]["uid"])

asyncio.run(main())
