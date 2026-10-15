"""Observe actual Ghidra processes; one explicitly scoped listener report, no approval."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import urllib.request

root=Path('/var/lib/mcpgw-managed/managed-pj1')
config=json.loads((root/'config.json').read_text())
observer=root/'observer.json'
sys.argv=['agent.py','--config',str(observer)]
spec=importlib.util.spec_from_file_location('installed_observer','/usr/local/lib/mcpgw-managed/agent.py')
agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
agent.validate_gateway()
base=config['gateway_url']
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*unused): raise ValueError('No credential forwarding')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
def console(path,body=None,token=None):
    request=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
    with opener.open(request,timeout=20) as response: return json.loads(response.read(3000000))
reviewer=console('/auth/mock-login',dict(email='root',password='root'))['access_token']
before=console('/api/endpoint/inventory',token=reviewer)
prior=[row for row in before['listeners'] if row['endpoint_id']==config['endpoint_id']]
assert not prior,'Existing listener snapshot present; do not overwrite another observation'
processes=[]; raw_by_digest={}
for p in Path('/proc').iterdir():
    if not p.name.isdigit(): continue
    try:
        raw=(p/'cmdline').read_bytes().replace(b'\x00',b' ').decode(errors='replace').strip()
        if 'mcpgw-ghidra-20261014' in raw and p.stat().st_uid==1000 and agent.PROCESS_MARKERS.search(raw):
            digest=agent.command_digest(raw)
            processes.append(dict(pid=int(p.name),uid=p.stat().st_uid,profile=(p/'attr/current').read_text().strip(),command_digest=digest))
            raw_by_digest[digest]=True
    except OSError: pass
assert processes,'GhidraMCP process no longer running; no observation sent'
findings=[row for row in agent.stdio_processes() if row['command_line'] in raw_by_digest]
assert findings,'Installed process scanner did not detect the live GhidraMCP process'
automatic=agent.report_listeners()
assert automatic is None and agent.SCAN_ENABLED is False
automatic_snapshot=console('/api/endpoint/inventory',token=reviewer)
assert not [row for row in automatic_snapshot['listeners'] if row['endpoint_id']==config['endpoint_id']]
report=agent.call('POST','/api/endpoint/listeners',dict(endpoint_id=config['endpoint_id'],findings=findings))
assert report['accepted']==len(findings) and report['counts']['shadow']==len(findings)
received=console('/api/endpoint/inventory',token=reviewer)
rows=[row for row in received['listeners'] if row['endpoint_id']==config['endpoint_id']]
assert {row['command_line'] for row in rows}=={row['command_line'] for row in findings}
assert all(row['classification']=='shadow' and row['mcp_evidence']=='suspected' for row in rows)
data=dict(at=time.time(),endpoint_id=config['endpoint_id'],processes=processes,collector_sha256=hashlib.sha256(Path(agent.__file__).read_bytes()).hexdigest(),
    automatic_scan_enabled=agent.SCAN_ENABLED,automatic_report=automatic,automatic_listener_rows=0,
    manual_collection=True,listener_findings=findings,receiver_result=report,console_listener_rows=rows,
    prior_listener_rows=0,registry_approval_performed=False,raw_command_or_credentials_logged=False)
out=root/'evidence/ghidra-20261014';out.mkdir(mode=0o700,parents=True,exist_ok=True)
(out/'live-observation.json').write_text(json.dumps(data,indent=2,default=str)+'\n')
print(json.dumps(dict(process_count=len(processes),findings=len(findings),automatic_forwarding=False,
    manual_receiver_accepted=report['accepted'],console_shadow=len(rows),evidence=str(out/'live-observation.json'))),flush=True)
