"""Render local Keycloak users/redirects from .env before Compose starts."""
import json
from pathlib import Path
b=Path(__file__).parent
values={}
for line in (b/".env").read_text().splitlines():
    if line and not line.startswith("#") and "=" in line:
        k,v=line.split("=",1); values[k]=v
realm=json.loads((b/"deploy/realm.json").read_text())
for u in realm["users"]:
    u["credentials"][0]["value"]=values[u["username"].upper()+"_PASSWORD"]
origin="http://127.0.0.1:"+values.get("DASHBOARD_PORT","18083")
realm["clients"][0]["redirectUris"]=[origin+"/*"]
realm["clients"][0]["webOrigins"]=[origin]
(b/"deploy/realm.json").write_text(json.dumps(realm,indent=2)+"\n")
issuer="http://127.0.0.1:"+values.get("KEYCLOAK_PORT","18081")+"/realms/mcp"
(b/"dashboard/config.js").write_text("export const issuer="+json.dumps(issuer)+";\n")
