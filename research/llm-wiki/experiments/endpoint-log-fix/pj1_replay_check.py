"""Controlled journal replay through the existing periodic service; no manual POST."""
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import urllib.request

root=Path('/home/pj1/mcpgw-telemetry-fix-20261014/logs/ea472c80fae8')
sample=json.loads((root/'delivered.json').read_text())['os_event']
config=json.loads(Path('/var/lib/mcpgw-managed/managed-pj1/config.json').read_text())
spec=importlib.util.spec_from_file_location('managed','/usr/local/lib/mcpgw-managed/managed-linux.py')
managed=importlib.util.module_from_spec(spec);spec.loader.exec_module(managed)
managed.verify_transport(config)
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):raise ValueError('Credential redirect refused')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
def call(path,body=None,token=None):
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    request=urllib.request.Request(config['gateway_url']+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
    with opener.open(request,timeout=15) as response:return json.load(response)
token=call('/auth/mock-login',{'email':'root','password':'root'})['access_token']
event_cursor=sample['event_id'].split(':',1)[1]
journal=subprocess.run(['journalctl','-k','-o','json','--no-pager','--cursor',event_cursor,'--reverse','-n','2'],
                       check=True,capture_output=True,text=True,timeout=15)
entries=[json.loads(line) for line in journal.stdout.splitlines()]
assert len(entries)==2 and entries[0]['__CURSOR']==event_cursor
earlier=entries[1]['__CURSOR']
cursor=Path('/var/lib/mcpgw-managed/managed-pj1/observer.journal-cursor')
assert not cursor.is_symlink() and managed.protected(cursor)
saved=cursor.read_bytes()
started=time.time()
def emit(**record):
    row={'at':time.time(),**record}
    with (root/'replay.jsonl').open('a') as out:out.write(json.dumps(row)+'\n')
    print(json.dumps(row),flush=True)
managed.private_write(cursor,earlier);cursor.chmod(0o600)
try:
    deadline=time.monotonic()+150
    while time.monotonic()<deadline:
        data=call('/api/endpoint/inventory',token=token)
        device=next(r for r in data['agents'] if r['endpoint_id']==config['endpoint_id'])
        status=device['detail']['observation']['os']
        from datetime import datetime
        if (status['state']=='success' and status['accepted_count']>=1
                and datetime.fromisoformat(status['reported_at']).timestamp()>started):
            rows=[r for r in data['os_events'] if r['event_id']==sample['event_id']]
            assert len(rows)==1 and rows[0]['id']==sample['id'] and rows[0]['received_at']==sample['received_at']
            assert cursor.read_text()!=earlier
            record={'ok':True,'manual_telemetry_post':False,'periodic_replay_confirmed':True,
                    'event_id':sample['event_id'],'existing_row_id':sample['id'],'rows_after':1,
                    'received_at_unchanged':True,'os_status':status}
            (root/'replay-result.json').write_text(json.dumps(record,indent=2)+'\n')
            emit(stage='replay-dedup-pass',**record)
            break
        emit(stage='waiting-for-periodic-replay',state=status['state'],reported_at=status['reported_at'])
        time.sleep(8)
    else:raise AssertionError('Periodic replay timed out')
finally:
    if cursor.read_text()==earlier:
        managed.private_write(cursor,saved.decode());cursor.chmod(0o600)
    for name in ['replay.jsonl','replay-result.json']:
        p=root/name
        if p.exists():p.chmod(0o644)
