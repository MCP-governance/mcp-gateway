"""Actual kernel denial followed only by read-only Console polling."""
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import urllib.request

root=Path('/var/lib/mcpgw-managed/managed-pj1');config=json.loads((root/'config.json').read_text())
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*unused):
        raise ValueError('No credential forwarding')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
def request(path,body=None,token=None):
    req=urllib.request.Request(config['gateway_url']+path,data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
    with opener.open(req,timeout=15) as response:return json.loads(response.read(3000000))
token=request('/auth/mock-login',dict(email='root',password='root'))['access_token']
spec=importlib.util.spec_from_file_location('parser','/usr/local/lib/mcpgw-managed/os-observer.py')
parser=importlib.util.module_from_spec(spec);spec.loader.exec_module(parser)
started=time.time()
attempt=subprocess.run(['sudo','-u','managed-pj1','--','/usr/local/lib/mcpgw-enforcement/mcpgw-managed-pj1/login-shell',
    '-c','/usr/bin/python3 -m ghidra_mcp --help'],capture_output=True,text=True,timeout=10)
assert attempt.returncode==126
journal=subprocess.run(['journalctl','-k','--no-pager','-o','json','--since','@'+str(int(started))],check=True,capture_output=True,text=True)
events=[parser.event(json.loads(line),1001,'mcpgw-managed-pj1') for line in journal.stdout.splitlines()]
events=[e for e in events if e and e['details'].get('executable') in ('python3','python3.12')]
assert events
ids={e['event_id'] for e in events}
deadline=time.monotonic()+100
rows=[]
while time.monotonic()<deadline:
    inventory=request('/api/endpoint/inventory',token=token)
    rows=[r for r in inventory['os_events'] if r['event_id'] in ids]
    if {r['event_id'] for r in rows}==ids:break
    print(json.dumps(dict(progress='waiting-existing-periodic-os-observer',remaining=round(deadline-time.monotonic()))),flush=True)
    time.sleep(8)
result=dict(ok=bool(rows) and {r['event_id'] for r in rows}==ids,started_at=started,finished_at=time.time(),
    managed_python_exit=attempt.returncode,kernel_events=events,console_os_events=rows,
    manual_report_sent=False,periodic_service_not_restarted=True,registry_approval_performed=False)
out=root/'evidence/ghidra-20261014/automatic-os-event.json';out.write_text(json.dumps(result,indent=2,default=str)+'\n')
public=Path('/home/pj1/mcpgw-ghidra-20261014/logs/automatic-os-event.json');public.write_bytes(out.read_bytes());public.chmod(0o644)
import os
os.chown(public,1000,1000)
print(json.dumps(dict(ok=result['ok'],manual_report_sent=False,console_os_event_ids=[r['id'] for r in rows],
    elapsed_seconds=round(result['finished_at']-started,2))),flush=True)
