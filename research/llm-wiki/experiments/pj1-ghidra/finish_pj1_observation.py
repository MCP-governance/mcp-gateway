import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

root=Path('/var/lib/mcpgw-managed/managed-pj1')
evidence=root/'evidence/ghidra-20261014'
live=json.loads((evidence/'live-observation.json').read_text())
for row in live['processes']:
    assert not Path('/proc/'+str(row['pid'])).exists(),'Test Ghidra process still running'
config=json.loads((root/'config.json').read_text())
sys.argv=['agent.py','--config',str(root/'observer.json')]
spec=importlib.util.spec_from_file_location('installed_observer','/usr/local/lib/mcpgw-managed/agent.py')
agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent);agent.validate_gateway()
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*unused): raise ValueError('No credential forwarding')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
def call(path,body=None,token=None):
    req=urllib.request.Request(config['gateway_url']+path,data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
    with opener.open(req,timeout=20) as res:return json.loads(res.read(3000000))
admin=call('/auth/mock-login',dict(email='root',password='root'))['access_token']
current=call('/api/endpoint/inventory',token=admin)
rows=[r for r in current['listeners'] if r['endpoint_id']==config['endpoint_id']]
assert {r['command_line'] for r in rows}=={r['command_line'] for r in live['console_listener_rows']},'Another listener writer changed the snapshot; do not remove it'
remaining=[r for r in agent.stdio_processes() if r['command_line'] in {v['command_digest'] for v in live['processes']}]
assert not remaining
clean=agent.call('POST','/api/endpoint/listeners',dict(endpoint_id=config['endpoint_id'],findings=[]))
assert clean['removed']==len(rows) and clean['accepted']==0
shell='/usr/local/lib/mcpgw-enforcement/mcpgw-managed-pj1/login-shell'
started=time.time()
command='/usr/bin/python3 -m ghidra_mcp --headless --binary /home/pj1/mcpgw-ghidra-20261014/artifacts/run/synthetic_return_42.elf'
denied=subprocess.run(['sudo','-u','managed-pj1','--',shell,'-c',command],capture_output=True,text=True,timeout=10)
assert denied.returncode==126 and 'Permission denied' in denied.stderr
journal=subprocess.run(['journalctl','-k','-o','json','--no-pager','--since','@'+str(int(started))],check=True,capture_output=True,text=True,timeout=15)
spec=importlib.util.spec_from_file_location('os_observer','/usr/local/lib/mcpgw-managed/os-observer.py')
observer=importlib.util.module_from_spec(spec);spec.loader.exec_module(observer)
events=[]
for line in journal.stdout.splitlines():
    item=observer.event(json.loads(line),1001,'mcpgw-managed-pj1')
    if item and item['kind']=='execution-denied' and item['details']['executable'] in ('python3','python3.12'):
        events.append(item)
assert events,'No independent kernel denial for the attempted interpreter launch'
sent=agent.call('POST','/api/endpoint/os-events',dict(endpoint_id=config['endpoint_id'],events=events))
after=call('/api/endpoint/inventory',token=admin)
received=[r for r in after['os_events'] if r['event_id'] in {e['event_id'] for e in events}]
assert {r['event_id'] for r in received}=={e['event_id'] for e in events}
assert subprocess.run(['systemctl','is-active','--quiet','mcpgw-managed-managed-pj1.service']).returncode==0
result=dict(at=time.time(),ghidra_process_exited=True,listener_snapshot_cleanup=clean,
    managed_launch=dict(uid=1001,command=command,exit=denied.returncode,stderr=denied.stderr.strip(),
        boundary='AppArmor denied general Python interpreter before loading GhidraMCP; not a Ghidra-specific signature'),
    kernel_events=events,receiver_os_event_result=sent,console_os_events=received,managed_service_active=True,
    registry_approval_performed=False,scan_setting_unchanged=False if agent.SCAN_ENABLED else True)
(evidence/'finish-and-managed-denial.json').write_text(json.dumps(result,indent=2,default=str)+'\n')
print(json.dumps(dict(process_exited=True,task_listener_rows_removed=clean['removed'],managed_python_exit=denied.returncode,
    independent_kernel_denials=len(events),console_os_events=len(received),service_active=True)),flush=True)
# Export only credential-free observed evidence so the human PJ1 operator can read it.
public=Path('/home/pj1/mcpgw-ghidra-20261014/logs')
for name in ('live-observation.json','finish-and-managed-denial.json'):
    src=evidence/name;dst=public/name;dst.write_bytes(src.read_bytes());dst.chmod(0o644)
    import os
    os.chown(dst,1000,1000)
