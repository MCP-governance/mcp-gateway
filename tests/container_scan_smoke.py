"""Verify real A.I.G task ingress without paid model calls and optional Trivy evidence."""
import argparse
import asyncio
import os
from pathlib import Path
import httpx

async def main(trivy):
    cfg={}
    for line in (Path(__file__).resolve().parents[1]/".env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k,v=line.split("=",1);cfg[k]=v
    issuer="http://127.0.0.1:"+cfg.get("KEYCLOAK_PORT","18081")+"/realms/mcp"
    scan="http://127.0.0.1:"+cfg.get("SCAN_API_PORT","18084")
    async with httpx.AsyncClient(timeout=30,trust_env=False) as client:
        assert (await client.post(scan+"/scans",json={"target":"demo"})).status_code==401
        async def login(name):
            r=await client.post(issuer+"/protocol/openid-connect/token",data={"grant_type":"password","client_id":"mcp-gateway","username":name,"password":cfg[name.upper()+"_PASSWORD"]});r.raise_for_status()
            return {"Authorization":"Bearer "+r.json()["access_token"]}
        admin=await login("admin");user=await login("user")
        assert (await client.post(scan+"/scans",headers=user,json={"target":"demo"})).status_code==403
        assert (await client.post(scan+"/scans",headers=admin,json={"target":"unknown"})).status_code==400
        # Fresh product task DB has no model. This verifies actual API wiring,
        # and intentionally never configures/charges an external model.
        if not os.getenv("AIG_SCAN_MODEL") and not cfg.get("AIG_SCAN_MODEL"):
            r=await client.post(scan+"/scans",headers=admin,json={"target":"demo"})
            assert r.status_code==503,(r.status_code,r.text)
            assert "credentials" in r.json()["detail"]
            print("PASS: real A.I.G rejects missing model credentials; admin and target boundaries enforced")
        if trivy:
            r=await client.post(scan+"/scans/trivy-result",headers={"X-Service-Token":cfg["SERVICE_TOKEN"]});r.raise_for_status()
            data=r.json();assert data["scanner"]=="Trivy" and isinstance(data["finding_count"],int)
            assert data["approval"]=="unchanged"
            print("PASS: actual Trivy report normalized, approval unchanged; findings="+str(data["finding_count"]))

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--trivy",action="store_true")
    asyncio.run(main(parser.parse_args().trivy))
