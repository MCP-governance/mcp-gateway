"""엔드포인트가 보고한 미등록 MCP가 호출 판정 없이도 경보로 남는지 본다(실제 PostgreSQL).

Lab only: tests/termination_dispatch_lab.sh run endpoint_shadow_alert_pg_check.py
Rows here are synthetic endpoints; nothing calls MCP.
"""
from __future__ import annotations

import json

from app import db, endpoint_plane, ops_response
from termination_lab_support import Checks, apply_schema, run

CHECKS = Checks("엔드포인트 미등록 MCP 경보")
ENDPOINT = "managed-shadow-alert-lab"


async def alerts():
    return await db.fetch_all("SELECT origin,origin_id,evidence FROM ops_alerts WHERE kind='unapproved-endpoint-mcp' ORDER BY id")


async def main() -> int:
    await apply_schema()
    await db.execute("""INSERT INTO endpoint_agents(endpoint_id,hostname,platform,agent_version)
                        VALUES (%s,'lab-pc','Windows 11','3.1.0')""", (ENDPOINT,))
    for label, fingerprint, classification in (("ghidra", "fp-shadow", "shadow"), ("filesystem", "fp-ok", "registered")):
        await db.execute("""INSERT INTO endpoint_inventory(endpoint_id,config_path,server_label,transport,endpoint_ref,fingerprint,classification)
                            VALUES (%s,'config.toml',%s,'stdio','ref',%s,%s)""", (ENDPOINT, label, fingerprint, classification))
    for process, fingerprint, evidence in (("pyghidra-mcp.exe", "fp-confirmed", "confirmed"), ("codex.exe", "fp-suspected", "suspected")):
        await db.execute("""INSERT INTO endpoint_listeners(endpoint_id,source,address,port,process_name,mcp_evidence,fingerprint,classification)
                            VALUES (%s,'network','127.0.0.1',8765,%s,%s,%s,'shadow')""", (ENDPOINT, process, evidence, fingerprint))
    await ops_response.endpoint_alerts()
    first = await alerts()
    CHECKS.ok("설정의 미등록 서버와 확인된 수신기만 경보", sorted(a["origin"] for a in first) == ["endpoint-inventory", "endpoint-listener"],
              rows=[(a["origin"], a["evidence"].get("label")) for a in first])
    CHECKS.ok("엔드포인트·호스트·서버·위치가 근거에 있다",
              all(a["evidence"].get("endpoint_id") == ENDPOINT and a["evidence"].get("hostname") == "lab-pc" and a["evidence"].get("place")
                  for a in first), evidence=json.dumps([a["evidence"] for a in first], ensure_ascii=False))
    await ops_response.endpoint_alerts()
    CHECKS.ok("같은 발견은 경보를 다시 만들지 않는다", len(await alerts()) == len(first))
    await db.execute("""INSERT INTO endpoint_inventory(endpoint_id,config_path,server_label,transport,endpoint_ref,fingerprint,classification)
                        VALUES (%s,'config.toml','other','stdio','ref','fp-new','shadow')""", (ENDPOINT,))
    await ops_response.endpoint_alerts()
    CHECKS.ok("새 미등록 서버는 새 경보", len(await alerts()) == len(first) + 1)
    before = len(await alerts())
    for n, (server, path) in enumerate((("ghidra", "local"), ("ghidra", "local"), ("memory-gw", "gateway"), ("claude_ai_Drive", "connector"))):
        await db.execute("""INSERT INTO endpoint_tool_events(endpoint_id,event_id,called_at,harness,server,tool,path)
                            VALUES (%s,%s,now(),'codex',%s,'decompile_function',%s)""", (ENDPOINT, f"event-{n:06d}", server, path))
    await ops_response.endpoint_alerts()
    tool_alerts = [a for a in await alerts() if a["origin"] == "endpoint-tool"]
    CHECKS.ok("로컬 경로 도구 호출은 서버마다 한 번 경보, 게이트웨이·커넥터는 경보 없음",
              len(await alerts()) == before + 1 and [a["evidence"]["label"] for a in tool_alerts] == ["ghidra"])
    await ops_response.endpoint_alerts()
    CHECKS.ok("같은 서버의 다음 호출은 경보를 늘리지 않는다", len(await alerts()) == before + 1)
    device = {"endpoint_id": ENDPOINT, "owner_token": None}
    first_request = await endpoint_plane.self_request(device, "ghidra", "https://github.com/clearbluejar/pyghidra-mcp", "바이너리 분석에 필요합니다")
    again = await endpoint_plane.self_request(device, "ghidra", "", "다시 요청합니다 열 글자")
    listed = await endpoint_plane.endpoint_requests()
    CHECKS.ok("엔드포인트 요청은 같은 서버에 하나만 열린다", not first_request["duplicate"] and again["duplicate"]
              and [r["server_label"] for r in listed] == ["ghidra"] and listed[0]["hostname"] == "lab-pc")
    CHECKS.ok("관리자가 닫으면 열린 목록에서 빠진다", await endpoint_plane.close_endpoint_request(first_request["id"], "admin-lab")
              and not await endpoint_plane.endpoint_requests() and not await endpoint_plane.close_endpoint_request(first_request["id"], "admin-lab"))
    return CHECKS.finish()


if __name__ == "__main__":
    run(main)
