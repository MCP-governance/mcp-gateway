"""Actual PJ1 periodic collection; synthetic processes, real Linux denial, scoped fault.

Run via the administrator's verified root runner. No manual inventory/listener/OS
POST, policy change, registry approval, model turn or product database reset.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid

assert os.geteuid() == 0 and socket.gethostname().lower() == 'pj1'
programs=Path('/usr/local/lib/mcpgw-managed')
config_path=Path('/var/lib/mcpgw-managed/managed-pj1/config.json')
config=json.loads(config_path.read_text())
assert config['uid'] == 1001 and config['username'] == 'managed-pj1'
run_id=uuid.uuid4().hex[:12]
public=Path('/home/pj1/mcpgw-telemetry-fix-20261014/logs')/run_id
public.mkdir(mode=0o755,parents=True)
owner=pwd.getpwnam('pj1')
os.chown(public,owner.pw_uid,owner.pw_gid)
transcript=public/'automatic-check.jsonl'
def emit(stage,**data):
    row={'stage':stage,'at':time.time(),'run_id':run_id,**data}
    with transcript.open('a') as out:out.write(json.dumps(row)+'\n')
    transcript.chmod(0o644)
    print(json.dumps(row),flush=True)

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
managed=module('managed',programs/'managed-linux.py')
parser=module('os_observer',programs/'os-observer.py')
managed.verify_transport(config)
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*unused):raise ValueError('Credential redirect refused')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
def call(path,body=None,token=None):
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    request=urllib.request.Request(config['gateway_url']+path,
        data=None if body is None else json.dumps(body).encode(),headers=headers)
    with opener.open(request,timeout=15) as response:return json.load(response)
auth=call('/auth/mock-login',{'email':'root','password':'root'})['access_token']
def snapshot():return call('/api/endpoint/inventory',token=auth)
def agent(data):return next(r for r in data['agents'] if r['endpoint_id']==config['endpoint_id'])
def state(data,channel):return agent(data).get('detail',{}).get('observation',{}).get(channel,{})
def scoped_rows(data):return [r for r in data['listeners'] if r['endpoint_id']==config['endpoint_id']]
def safe_agent(data):
    a=agent(data)
    return {'endpoint_id':a['endpoint_id'],'managed_state':a['managed_state'],'agent_version':a['agent_version'],
            'observation':a.get('detail',{}).get('observation',{})}
def wait_for(name,predicate,seconds=165):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        data=snapshot()
        if predicate(data):return data
        emit('waiting',condition=name,observation=safe_agent(data)['observation'])
        time.sleep(8)
    raise AssertionError('Automatic observation timed out: '+name)

def broker_works():
    code="import json,socket;s=socket.socket(socket.AF_UNIX);s.connect("+repr(config['socket'])+");r=json.loads(s.recv(131072));print(json.dumps({'usable':r.get('Authorization','').startswith('Bearer ')}))"
    r=subprocess.run(['sudo','-u','managed-pj1','--','/usr/bin/python3','-I','-S','-c',code],
                     capture_output=True,text=True,timeout=15,check=True)
    return json.loads(r.stdout)['usable']
def fixture(uid,marker):
    account=pwd.getpwuid(uid)
    def identity():
        os.setgroups([]);os.setgid(account.pw_gid);os.setuid(uid)
    process=subprocess.Popen(['/bin/bash','-c','exec -a "$1" /usr/bin/sleep 600','fixture',marker],
                            preexec_fn=identity,start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for _ in range(50):
        path=Path('/proc')/str(process.pid)
        cmd=(path/'cmdline').read_bytes()
        if cmd.split(b'\0')[0]==marker.encode():
            assert path.stat().st_uid==uid
            return process,hashlib.sha256(' '.join(cmd.decode().strip('\0').split('\0')).encode()).hexdigest()
        time.sleep(.05)
    raise AssertionError('Fixture not started')
def stop(process):
    if process.poll() is None:
        assert os.getpgid(process.pid)==process.pid
        os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=10)

processes=[]
cursor=config_path.with_name('observer.json').with_suffix('.journal-cursor')
cursor_saved=None
fault=b'telemetry-invalid-cursor-'+run_id.encode()
markers=['ghidramcp-telemetry-managed-'+run_id,'ghidramcp-telemetry-other-'+run_id]
result={'scope':'Linux managed UID1001; synthetic marker processes, actual AppArmor denial; no MCP/model call',
        'manual_telemetry_post':False,'registry_approval':False,'product_database_reset':False}
try:
    first=wait_for('initial healthy collectors',lambda d:state(d,'process').get('state')=='success'
                   and state(d,'os').get('state')=='success' and agent(d)['managed_state']=='active')
    observed=json.loads(config_path.with_name('observer.json').read_text())
    assert observed['ENDPOINT_PROCESS_SCAN']=='1' and observed['ENDPOINT_PROCESS_UID']=='1001' and observed['ENDPOINT_NETSCAN']=='0'
    assert broker_works()
    emit('baseline',agent=safe_agent(first),logs=str(public))
    # A wrong endpoint is rejected through the deployed device HTTP boundary.
    try:
        managed.request(config,'/api/endpoint/observation-status',{'endpoint_id':'other-telemetry-fixture',
                        'channel':'process','state':'success','accepted_count':0})
        raise AssertionError('Wrong endpoint accepted')
    except urllib.error.HTTPError as error:
        assert error.code==403
    p,digest=fixture(1001,markers[0]);processes.append(p)
    negative,_=fixture(1000,markers[1]);processes.append(negative)
    started=time.time()
    denial=subprocess.run(['sudo','-u','managed-pj1','--','/usr/local/lib/mcpgw-enforcement/mcpgw-managed-pj1/login-shell',
                           '-c','/usr/bin/python3 -c pass'],capture_output=True,text=True,timeout=15)
    assert denial.returncode!=0
    events=[]
    for _ in range(15):
        journal=subprocess.run(['journalctl','-k','-o','json','--no-pager','--since','@'+str(int(started)-1)],
                               capture_output=True,text=True,check=True,timeout=15)
        events=[found for line in journal.stdout.splitlines()
                if (found:=parser.event(json.loads(line),1001,'mcpgw-managed-pj1')) and found['kind']=='execution-denied'
                and found['details'].get('executable')=='python3.12']
        if not events:
            events=[found for line in journal.stdout.splitlines()
                    if (found:=parser.event(json.loads(line),1001,'mcpgw-managed-pj1')) and found['kind']=='execution-denied'
                    and found['details'].get('executable','').startswith('python3')]
        if events:break
        time.sleep(.2)
    assert events,'Independent journal has no matching UID/profile denial'
    expected=events[-1]
    emit('fixtures-active',managed_pid=p.pid,other_uid_pid=negative.pid,markers=markers,
         expected_command_sha256='sha256:'+digest,denial_exit=denial.returncode,expected_event=expected)
    positive=wait_for('automatic process and OS delivery',lambda d:
        any(r.get('process_name')==markers[0] for r in scoped_rows(d))
        and any(r.get('event_id')==expected['event_id'] for r in d['os_events']))
    rows=scoped_rows(positive)
    match=next(r for r in rows if r.get('process_name')==markers[0])
    assert not any(r.get('process_name')==markers[1] for r in rows)
    assert match['mcp_evidence']=='suspected' and match['source']=='stdio-process'
    assert match['classification']=='shadow' and match['freshness']=='fresh'
    assert match['command_line']=='sha256:'+digest
    assert state(positive,'network')['state']=='disabled'
    stored=next(r for r in positive['os_events'] if r['event_id']==expected['event_id'])
    assert stored['endpoint_id']==config['endpoint_id'] and stored['details']==expected['details']
    assert broker_works()
    emit('automatic-delivery-pass',listener=match,os_event=stored,agent=safe_agent(positive),
         other_uid_absent=True,broker_usable=True)
    (public/'delivered.json').write_text(json.dumps({'listener':match,'os_event':stored,'agent':safe_agent(positive)},indent=2)+'\n')
    for _ in range(3):
        emit('ui-inspection-window',seconds_remaining=60-_ *20)
        time.sleep(20)
    for p in processes:stop(p)
    removed=wait_for('automatic process reconciliation',lambda d:
        not any(r.get('process_name') in markers for r in scoped_rows(d)) and state(d,'process').get('state')=='success')
    emit('automatic-cleanup-pass',agent=safe_agent(removed))
    prior=state(removed,'os')['last_success_at']
    assert cursor.is_file() and not cursor.is_symlink() and managed.protected(cursor)
    cursor_saved=(cursor.read_bytes(),cursor.stat().st_mode & 0o777)
    managed.private_write(cursor,fault.decode());cursor.chmod(0o600)
    emit('fault-injected',fault='invalid journal cursor',last_success_at=prior)
    failed=wait_for('OS collector failure visibility',lambda d:state(d,'os').get('state')=='failed')
    assert state(failed,'os')['last_success_at']==prior
    assert state(failed,'process')['state']=='success' and state(failed,'inventory')['state']=='success'
    assert broker_works()
    assert cursor.read_bytes()==fault,'Failed OS scan advanced cursor'
    emit('failure-isolation-pass',agent=safe_agent(failed),broker_usable=True,cursor_unchanged=True)
    managed.private_write(cursor,cursor_saved[0].decode());cursor.chmod(cursor_saved[1]);cursor_saved=None
    recovered=wait_for('OS collector recovery',lambda d:state(d,'os').get('state')=='success'
                       and state(d,'os').get('last_success_at')!=prior)
    assert broker_works()
    events_now=[r for r in recovered['os_events'] if r['event_id']==expected['event_id']]
    assert len(events_now)==1,'OS retry duplicated journal event'
    result.update(ok=True,automatic_process=True,other_uid_excluded=True,actual_os_event_received=True,
                  scoped_empty_reconciliation=True,collector_fault_visible=True,last_success_preserved=True,
                  cursor_no_advance_on_failure=True,broker_survived_observer_failure=True,recovery=True,
                  duplicate_event_rows=len(events_now),endpoint_id=config['endpoint_id'],run_id=run_id,logs=str(public))
    emit('recovery-pass',agent=safe_agent(recovered),broker_usable=True,duplicate_event_rows=len(events_now))
finally:
    for p in processes:stop(p)
    if cursor_saved is not None:
        assert cursor.read_bytes()==fault,'Cursor changed; preserve for inspection'
        managed.private_write(cursor,cursor_saved[0].decode());cursor.chmod(cursor_saved[1])
    (public/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    for path in public.iterdir():path.chmod(0o644)
    emit('final',**result)
