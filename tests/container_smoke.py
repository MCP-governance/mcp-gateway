"""Real Keycloak -> Agent -> MCP -> OPA/Presidio -> Collector -> PostgreSQL test."""
import asyncio
import os
import time
import httpx

async def main():
    issuer="http://127.0.0.1:"+os.getenv("KEYCLOAK_PORT","18081")+"/realms/mcp"
    agent="http://127.0.0.1:"+os.getenv("AGENT_PORT","18082")
    dashboard="http://127.0.0.1:"+os.getenv("DASHBOARD_PORT","18083")
    async with httpx.AsyncClient(timeout=15,trust_env=False) as client:
        deadline=time.monotonic()+180
        while True:
            try:
                r=await client.post(issuer+"/protocol/openid-connect/token",data={"grant_type":"password","client_id":"mcp-gateway","username":"user","password":os.getenv("USER_PASSWORD","local-user-change-me")})
                if r.status_code==200: break
            except httpx.HTTPError: pass
            if time.monotonic()>deadline: raise RuntimeError("Keycloak user login not ready")
            await asyncio.sleep(2)
        token=r.json()["access_token"]
        r=await client.post(issuer+"/protocol/openid-connect/token",data={"grant_type":"password","client_id":"mcp-gateway","username":"admin","password":os.getenv("ADMIN_PASSWORD","local-admin-user-change-me")});r.raise_for_status()
        admin=r.json()["access_token"]
        adminheaders={"Authorization":"Bearer "+admin}
        headers={"Authorization":"Bearer "+token,"Accept":"application/json, text/event-stream","Content-Type":"application/json"}
        assert (await client.post(agent+"/mcp/demo",json={},headers={"Accept":headers["Accept"]})).status_code==401
        async def rpc(method,params=None):
            payload={"jsonrpc":"2.0","id":1,"method":method}
            if params is not None:payload["params"]=params
            return await client.post(agent+"/mcp/demo",json=payload,headers=headers)
        for attempt in range(30):
            r=await rpc("initialize",{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"architecture-smoke","version":"1"}})
            if r.status_code==200: break
            await asyncio.sleep(1)
        r.raise_for_status()
        if r.headers.get("mcp-session-id"):headers["Mcp-Session-Id"]=r.headers["mcp-session-id"]
        headers["MCP-Protocol-Version"]=r.json()["result"]["protocolVersion"]
        r=await client.post(agent+"/mcp/demo",json={"jsonrpc":"2.0","method":"notifications/initialized"},headers=headers);assert r.status_code in (200,202)
        r=await rpc("tools/list");r.raise_for_status();names={t["name"] for t in r.json()["result"]["tools"]};assert names=={"echo","fetch_internal","fetch_external"}
        r=await client.put(dashboard+"/api/tools/demo/echo",headers=adminheaders,json={"approved":False});r.raise_for_status()
        r=await rpc("tools/call",{"name":"echo","arguments":{"text":"hello public world"}});assert r.status_code==403
        assert (await client.put(dashboard+"/api/tools/demo/echo",headers={"Authorization":"Bearer "+token},json={"approved":True})).status_code==403
        for tool in sorted(names):
            r=await client.put(dashboard+"/api/tools/demo/"+tool,headers=adminheaders,json={"approved":True});r.raise_for_status()
        r=await rpc("tools/call",{"name":"echo","arguments":{"text":"hello public world"}});r.raise_for_status();assert r.json()["result"]["content"][0]["text"]=="hello public world"
        for tool in ["fetch_internal","fetch_external"]:
            r=await rpc("tools/call",{"name":tool,"arguments":{}});r.raise_for_status();assert not r.json()["result"].get("isError",False)
        r=await rpc("tools/call",{"name":"echo","arguments":{"text":"private email someone@example.com"}});assert r.status_code==403
        deadline=time.monotonic()+45
        while True:
            r=await client.get(dashboard+"/api/events",headers=adminheaders);r.raise_for_status();events=r.json()["events"]
            sources={e["service"] for e in events}
            if {"agent-service","mcp-gateway","mcp-server"}.issubset(sources) and any(e["risk"]=="high" for e in events):break
            if time.monotonic()>deadline:raise RuntimeError("Collector/evidence pipeline missing sources or Presidio risk")
            await asyncio.sleep(1)
        serialized=str(events)
        assert token not in serialized and "someone@example.com" not in serialized
        print("PASS: real Keycloak authentication, admin approval, OPA, Presidio, MCP internal/external APIs, three OTel sources, normalized PostgreSQL evidence")

if __name__=="__main__":asyncio.run(main())
