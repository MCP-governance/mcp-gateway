"""DEV-73 transaction/race checks on an explicitly disposable PostgreSQL database.

No MCP server or engine is created. Synthetic device acknowledgements establish DB semantics
only; a real engine stop receipt still needs the separately authorized device experiment.
"""
import asyncio
from contextlib import contextmanager
import hashlib
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'gateway'))
from app import db, endpoint_plane, local_jobs, registry
from termination_lab_support import APP, Checks, add_principal, add_server, apply_schema, isolated_disposal, run

DEVICE='dev73-rework-device'
OWNER='dev73-rework-owner'
SERVER='dev73-rework-server'
NOW=lambda:datetime.now(timezone.utc)
CHECKS=Checks('DEV-73 PostgreSQL transition, replay, claim race, stop barrier and evidence')
ok=CHECKS.ok
GENERATION=[1]


async def fixture():
    await add_principal(OWNER)
    await add_server(SERVER)
    intake=str(uuid.uuid4())
    await db.execute("""INSERT INTO endpoint_agents(endpoint_id,hostname,platform,agent_version,owner_token,status,
        managed_state,local_username,local_uid,device_epoch,policy_hash,heartbeat_at)
        VALUES(%s,'synthetic','linux','synthetic',%s,'active','active','synthetic',2001,'epoch',%s,now())""",
        (DEVICE,OWNER,endpoint_plane.installed_hash('policy',{})))
    await db.execute("""INSERT INTO mcp_intake_requests(id,submitted_by,display_name,repository_url,requested_transport,
        purpose,status,reviewed_by,local_observer_device) VALUES(%s,%s,'synthetic','https://example.test/repository',
        'stdio','synthetic','APPROVED','synthetic-reviewer',%s)""",(intake,OWNER,DEVICE))
    await db.execute("INSERT INTO policy_versions(id,source_path,source_sha256,status) VALUES('dev73-rework','synthetic','version-1','ACTIVE')")
    body={'server_id':SERVER,'image':'mirror.test/mcp/fs@sha256:'+'a'*64,'mounts':[],'command':['serve'],'env':{},
          'reason':{'kind':'local_file','text':'로컬 데이터 시험을 위한 합성 승인'},
          'approval':{'generation':1,'expires_at':(NOW()+timedelta(minutes=10)).isoformat()}}
    local={'manifest':body,'manifest_sha256':hashlib.sha256(local_jobs.canonical(body)).hexdigest(),
           'signature':'synthetic-not-an-MCP-run','observer_device':DEVICE}
    with patch.dict(os.environ,{'LOCAL_IMAGE_MIRRORS':'mirror.test/mcp'}):
        await local_jobs.approve_manifest(local,intake,observed=True)
    return intake,local


async def queued(local,*,deadline=20,jti=None):
    identity=str(uuid.uuid4())
    dispatch_id=str(uuid.uuid4())
    await db.execute("""INSERT INTO dispatch_intents(request_id,user_token,server_id,tool_name,action,fingerprint)
        VALUES(%s,%s,%s,'synthetic-tool','r','synthetic-fingerprint')""",(dispatch_id,OWNER,SERVER))
    await db.execute("""INSERT INTO local_jobs(id,device_id,user_token,server_id,manifest_sha256,manifest,signature,method,
        params,deadline,policy_generation,device_epoch,device_policy,policy_version,request_id,control_sha256,token_jti)
        SELECT %s,%s,%s,%s,%s,%s,%s,'tools/call','{}',clock_timestamp()+make_interval(secs=>%s),
        policy_generation,'epoch','policy','version-1',%s,'control-1',%s FROM local_approvals WHERE server_id=%s""",
        (identity,DEVICE,OWNER,SERVER,local['manifest_sha256'],local_jobs.Jsonb(local['manifest']),local['signature'],deadline,dispatch_id,jti,SERVER))
    return identity


MIRROR={'LOCAL_IMAGE_MIRRORS':'mirror.test/mcp'}
STUCK="""SELECT pid,wait_event_type||':'||COALESCE(wait_event,'') AS waiting,pg_blocking_pids(pid) AS blocked_by,left(query,100) AS query
         FROM pg_stat_activity WHERE pid<>pg_backend_pid() AND datname=current_database() AND state<>'idle'"""


async def snapshot():
    return [{k:(str(v) if k=='blocked_by' else v) for k,v in r.items()} for r in await db.fetch_all(STUCK)]


async def reapprove(intake,local):
    """A deliberate new signed generation, as an approver would issue after a withdrawal."""
    GENERATION[0]+=1
    local['manifest']['approval']={'generation':GENERATION[0],'expires_at':(NOW()+timedelta(minutes=10)).isoformat()}
    local['manifest_sha256']=hashlib.sha256(local_jobs.canonical(local['manifest'])).hexdigest()
    with patch.dict(os.environ,MIRROR):await local_jobs.approve_manifest(local,intake,observed=True)


async def settle():
    """Close every job a race left open, the way a device stop receipt would."""
    await db.execute("UPDATE local_jobs SET state='expired',stop_requested=true,finished_at=COALESCE(finished_at,now()) WHERE state IN ('queued','claimed')")
    await db.execute("UPDATE local_jobs SET stopped_at=now() WHERE started_at IS NOT NULL AND stopped_at IS NULL")


async def operate(intake,local):
    await settle()
    await db.execute("UPDATE mcp_servers SET lifecycle='OPERATING' WHERE id=%s",(SERVER,))
    await reapprove(intake,local)


async def attempt(coroutine):
    """('ok', value) or the exception name, so a race reports every outcome instead of aborting."""
    try:return 'ok',await coroutine
    except local_jobs.NotStarted:return 'not_started',None
    except Exception as exc:return type(exc).__name__+':'+str(getattr(exc,'sqlstate','')),None


async def revoke(jti):
    """The same sequence idp.revoke_* runs: token locks, queue cancel, then the revocation row."""
    async with db.transaction() as connection:
        await local_jobs.prepare_token_revocation(connection,[{'jti':jti}])
        await connection.execute("INSERT INTO agent_revoked_tokens(jti,expires_at) VALUES(%s,now()+interval '1 hour') ON CONFLICT DO NOTHING",(jti,))


async def watch(tasks,limit=10):
    """Results of already-started contenders. A stuck pair (a lock cycle PostgreSQL cannot see)
    is captured while it is still stuck, then ended so the next round starts clean."""
    _,pending=await asyncio.wait(tasks,timeout=limit)
    if not pending:return [t.result() for t in tasks]
    seen=await snapshot()
    await db.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid<>pg_backend_pid() AND datname=current_database() AND state<>'idle'")
    for task in pending:task.cancel()
    await asyncio.gather(*tasks,return_exceptions=True)
    await asyncio.sleep(.5)
    return 'hang',seen


async def raced(*coroutines,limit=10):
    """Every contender with a random head start."""
    async def later(coroutine):
        await asyncio.sleep(random.choice((0,0,.003,.01,.03)))
        return await attempt(coroutine)
    return await watch([asyncio.ensure_future(later(c)) for c in coroutines],limit)


@contextmanager
def claim_holding_row(entered):
    """claim stopped exactly where it owns the job row and has not yet taken the execution locks:
    the window every other writer of that job (cancel, revoke, terminate) has to be safe in."""
    original=local_jobs.admission_locks
    async def paused(connection,device,server):
        await original(connection,device,server)
        entered.set()
        await asyncio.sleep(.5)
    with patch.object(local_jobs,'admission_locks',paused):yield


async def main():
    await apply_schema()
    await db.execute((APP/'local_run_tables.sql').read_text(encoding='utf-8'))
    intake,local=await fixture()
    device=await db.fetch_one('SELECT * FROM endpoint_agents WHERE endpoint_id=%s',(DEVICE,))
    # Jobs are bound to control_hash 'policy'; the device holds that control with no managed files (D-238).
    policy={'control_hash':'policy','servers':[],'configuration_hashes':{},'policy_hash':endpoint_plane.installed_hash('policy',{})}
    with isolated_disposal(),patch.object(endpoint_plane,'managed_policy',AsyncMock(return_value=policy)),patch.object(registry,'server',return_value={'local':local}),patch.object(local_jobs,'control_generation',return_value='control-1'):
        # F2: the same transition cancels old queued jobs and persists the withdrawn generation.
        identity=await queued(local)
        await db.execute("UPDATE mcp_servers SET lifecycle='TERMINATING' WHERE id=%s",(SERVER,))
        claimed=await local_jobs.claim(device,0)
        row=await db.fetch_one('SELECT * FROM local_jobs WHERE id=%s',(identity,))
        ok('F2 종료 전환이 대기 작업을 취소하고 claim을 막는다',claimed is None and row['state']=='expired' and row['claimed_at'] is None)
        with patch.dict(os.environ,MIRROR):
            try:await local_jobs.approve_manifest(local,intake,observed=True)
            except ValueError:replayed=False
            else:replayed=True
        ok('F2 철회한 서명 세대를 같은 서명으로 되살릴 수 없다',not replayed)
        # New approval generation is deliberate, never an automatic retry of the old job.
        await db.execute("UPDATE mcp_servers SET lifecycle='OPERATING' WHERE id=%s",(SERVER,))
        await reapprove(intake,local)
        old=await db.fetch_one('SELECT state FROM local_jobs WHERE id=%s',(identity,))
        ok('F2 새 승인 세대가 이전 작업을 되살리지 않는다',old['state']=='expired')

        # F7: arguments are bounded before any row exists; the limit itself is still admitted.
        await db.execute('DELETE FROM local_jobs')
        base=len(local_jobs.canonical({'cursor':''}))
        edge={'cursor':'x'*(local_jobs.MAX_PARAMS_BYTES-base)}
        over={'cursor':'x'*(local_jobs.MAX_PARAMS_BYTES-base+1)}
        unicode_over={'cursor':'가'*(local_jobs.MAX_PARAMS_BYTES//3+1)}
        refusals=[]
        for params in (over,unicode_over):
            try:await local_jobs.exchange(DEVICE,local,'tools/list',params,1)
            except local_jobs.NotStarted as exc:refusals.append((exc.local_policy,'크기 상한' in str(exc)))
            else:refusals.append(None)
        none_inserted=(await db.fetch_one('SELECT count(*) AS n FROM local_jobs'))['n']==0
        try:await local_jobs.exchange(DEVICE,local,'tools/list',edge,1)
        except local_jobs.NotStarted as exc:edge_admitted='크기 상한' not in str(exc)
        else:edge_admitted=True
        inserted=(await db.fetch_one('SELECT count(*) AS n FROM local_jobs'))['n']
        ok('F7 인자 크기 상한 초과는 행을 만들기 전에 P-RATE-003으로 거부한다(바이트 기준)',
           refusals==[('P-RATE-003',True)]*2 and none_inserted,limit=local_jobs.MAX_PARAMS_BYTES)
        ok('F7 상한과 같은 크기의 인자는 대기열에 들어간다',edge_admitted and inserted==1,rows=inserted)

        # F7: concurrent admission cannot exceed the per-account queue, whatever the interleaving.
        await db.execute('DELETE FROM local_jobs')
        outcomes=await asyncio.gather(*[attempt(local_jobs.exchange(DEVICE,local,'tools/list',{},1)) for _ in range(20)])
        rows=(await db.fetch_one('SELECT count(*) AS n FROM local_jobs'))['n']
        refused=sum(1 for kind,_ in outcomes if kind=='not_started')
        other=[kind for kind,_ in outcomes if kind not in ('ok','not_started')]
        ok('F7 동시 20건 입장에도 계정 대기열 상한(8)을 넘어 행이 생기지 않는다',rows==local_jobs.QUEUE_LIMIT and not other,rows=rows,refused=refused,other=other)
        untaken=await db.fetch_one("SELECT count(*) AS n FROM local_jobs WHERE state='expired' AND claimed_at IS NULL")
        ok('F7 입장한 행은 수령되지 않은 채 만료된다',untaken['n']==rows)
        await db.execute('DELETE FROM local_jobs')

        # F7: saturation is refused before another row is inserted, not after a job is sent.
        for _ in range(local_jobs.QUEUE_LIMIT):await queued(local)
        count=await db.fetch_one('SELECT count(*) AS n FROM local_jobs')
        try:await local_jobs.exchange(DEVICE,local,'tools/list',{},1)
        except local_jobs.NotStarted as exc:saturated=exc.local_policy=='P-RATE-003'
        else:saturated=False
        ok('F7 대기열이 가득 차면 새 행 없이 P-RATE-003으로 거부한다',
           saturated and (await db.fetch_one('SELECT count(*) AS n FROM local_jobs'))['n']==count['n'])
        await db.execute("UPDATE local_jobs SET state='expired',finished_at=now() WHERE state='queued'")

        # F2/F7: simultaneous claims have one winner; expired leases never return to queued.
        await queued(local)
        claims=await asyncio.gather(*[local_jobs.claim(device,0) for _ in range(4)])
        job=next((c for c in claims if c),None)
        ok('F2 동시 claim 4건 중 승자는 한 명이다',sum(c is not None for c in claims)==1)
        await local_jobs.validate_job(device,job['id'],start=True)
        try:await local_jobs.validate_job(device,job['id'],start=True)
        except local_jobs.NotStarted:twice=False
        else:twice=True
        ok('F2 수령한 작업을 두 번 실행하지 않는다',not twice)
        # A final transition is refused until a real/synthetic device stop receipt exists.
        try:await db.execute("UPDATE mcp_servers SET lifecycle='TERMINATING' WHERE id=%s",(SERVER,))
        except Exception as exc:refused_state=getattr(exc,'sqlstate',None)
        else:refused_state=None
        ok('F2 정지 미확인 컨테이너가 있으면 최종 전환을 DB가 거부한다(55000)',refused_state=='55000')
        barrier=asyncio.create_task(local_jobs.quiesce(server_id=SERVER))
        for _ in range(100):
            row=await db.fetch_one('SELECT stop_requested FROM local_jobs WHERE id=%s',(job['id'],))
            if row['stop_requested']:break
            await asyncio.sleep(.01)
        ok('F2 종료 요청이 정지 요청을 기록하고 정지 회신 전에는 끝나지 않는다',row['stop_requested'] and not barrier.done())
        received=await local_jobs.complete(device,job['id'],None,'synthetic stop receipt',stopped=True)
        await barrier
        await db.execute("UPDATE mcp_servers SET lifecycle='TERMINATING' WHERE id=%s",(SERVER,))
        ok('F2 정지 회신 뒤에만 최종 전환이 끝나고 이후 claim은 거부된다',received and await local_jobs.claim(device,0) is None)
        evidence=await db.fetch_one('SELECT * FROM local_job_events WHERE job_id=%s ORDER BY id DESC LIMIT 1',(job['id'],))
        ok('F9 증거에 정지 시각과 결과 해시가 남고 dispatch 의도와 request UUID로 이어진다',
           bool(evidence['evidence']['stopped_at'] and evidence['evidence']['result_sha256'])
           and bool(await db.fetch_one('SELECT 1 FROM dispatch_intents WHERE request_id=%s',(evidence['request_id'],))))
        # F7: stale, never-started rows are cleaned separately from permanent job evidence.
        await db.execute("UPDATE local_jobs SET state='expired',finished_at=now()-interval '2 hours' WHERE started_at IS NULL")
        async with db.transaction() as connection:await local_jobs.cleanup(connection)
        ok('F7 오래된 미시작 payload는 정리하되 작업 증거는 남는다',
           bool(await db.fetch_one('SELECT 1 FROM local_job_events WHERE job_id=%s',(job['id'],))))

        # F9: the stored hash is of the value actually stored (after the size cap), recomputable from the row.
        async def run_one(result=None,error=None):
            await operate(intake,local)
            await queued(local)
            taken=await local_jobs.claim(device,0)
            await local_jobs.validate_job(device,taken['id'],start=True)
            await local_jobs.complete(device,taken['id'],result,error,stopped=True)
            return await db.fetch_one('SELECT * FROM local_jobs WHERE id=%s',(taken['id'],))
        def recomputed(row):
            return hashlib.sha256(local_jobs.canonical(row['result'] if row['result'] is not None else {'error':row['error']})).hexdigest()
        good=await run_one({'content':[{'type':'text','text':'한글 결과'}],'isError':False})
        huge=await run_one({'content':[{'type':'text','text':'x'*(local_jobs.MAX_RESULT_BODY+10)}]})
        failed=await run_one(error='도구 실행 실패')
        ok('F9 저장된 결과의 해시를 행에서 다시 계산하면 일치한다',good['state']=='done' and good['result_sha256']==recomputed(good))
        ok('F9 크기 상한으로 바뀐 결과는 저장된 오류 값의 해시로 남는다(원본 해시가 아니다)',
           huge['result'] is None and '상한' in huge['error'] and huge['result_sha256']==recomputed(huge),stored_error=huge['error'])
        ok('F9 오류 결과도 저장된 값의 해시를 갖는다',failed['result_sha256']==recomputed(failed))
        events=await db.fetch_all('SELECT job_id,evidence FROM local_job_events WHERE job_id=ANY(%s::uuid[])',([good['id'],huge['id'],failed['id']],))
        ok('F9 작업 증거의 결과 해시가 작업 행과 같다',
           {str(e['job_id']):e['evidence'].get('result_sha256') for e in events}=={str(r['id']):r['result_sha256'] for r in (good,huge,failed)})

        # F7: the stored-state ceilings are settings; the lab sets small values and checks the real boundary.
        async def admitted():
            """True if exchange created a job row, False with its policy id if it was refused first."""
            before=(await db.fetch_one('SELECT count(*) AS n FROM local_jobs'))['n']
            try:await local_jobs.exchange(DEVICE,local,'tools/list',{},.3)
            except local_jobs.NotStarted as exc:
                grew=(await db.fetch_one('SELECT count(*) AS n FROM local_jobs'))['n']>before
                return grew,exc.local_policy,str(exc)
            return True,None,''
        await operate(intake,local)
        await db.execute('DELETE FROM local_jobs')
        with patch.object(local_jobs,'ACTIVE_TOTAL_LIMIT',3):
            for _ in range(2):await queued(local)
            below=await admitted()
            await db.execute("UPDATE local_jobs SET state='expired',finished_at=now() WHERE state='queued'")
            for _ in range(3):await queued(local)
            at_limit=await admitted()
        ok('F7 전체 대기·수령 작업 상한(설정값)의 경계: 미만은 입장, 상한이면 새 행 없이 P-RATE-003',
           below[0] and not at_limit[0] and at_limit[1]=='P-RATE-003' and '전체 대기열' in at_limit[2],limit=3)
        await db.execute('DELETE FROM local_jobs')
        with patch.object(local_jobs,'ROW_LIMIT',5):
            for _ in range(4):
                await queued(local)
            await db.execute("UPDATE local_jobs SET state='expired',finished_at=now()")
            below=await admitted()
            await db.execute("UPDATE local_jobs SET state='expired',finished_at=now() WHERE state='queued'")
            await queued(local)
            await db.execute("UPDATE local_jobs SET state='expired',finished_at=now()")
            at_limit=await admitted()
        ok('F7 보관 행 수 상한(설정값)의 경계: 미만은 입장, 상한이면 새 행 없이 P-RATE-003',
           below[0] and not at_limit[0] and at_limit[1]=='P-RATE-003' and '저장 상한' in at_limit[2],limit=5)
        await db.execute('DELETE FROM local_jobs')

        async def store(result):
            await operate(intake,local)
            await queued(local)
            taken=await local_jobs.claim(device,0)
            await local_jobs.validate_job(device,taken['id'],start=True)
            await local_jobs.complete(device,taken['id'],result,None,stopped=True)
            return await db.fetch_one('SELECT * FROM local_jobs WHERE id=%s',(taken['id'],))
        with patch.object(local_jobs,'RESULT_STORE_BYTES',400):
            first=await store({'text':'a'*100})
            second=await store({'text':'b'*100})
            third=await store({'text':'c'*400})
        ok('F7 결과 저장 총량 상한(설정값)의 경계: 안에 들면 저장, 넘기면 오류로 바꿔 저장하고 그 값의 해시를 남긴다',
           first['result'] is not None and second['result'] is not None and third['result'] is None
           and '저장 상한' in (third['error'] or '') and third['result_sha256']==recomputed(third) and third['state']=='done',limit=400)
        await db.execute('DELETE FROM local_jobs')

        # F2: a candidate chosen without a lock is read again under the locks; if it changed meanwhile nothing is claimed.
        async def changed_while_claiming(change):
            await operate(intake,local)
            identity=await queued(local)
            entered=asyncio.Event()
            with claim_holding_row(entered):
                holder=asyncio.ensure_future(attempt(local_jobs.claim(device,0)))
                await asyncio.wait_for(entered.wait(),10)
                await change(identity)
                outcome=await watch([holder])
            row=await db.fetch_one('SELECT state,claimed_at FROM local_jobs WHERE id=%s',(identity,))
            return outcome,row
        cancelled=await changed_while_claiming(lambda i:db.execute("UPDATE local_jobs SET state='expired',finished_at=now() WHERE id=%s",(i,)))
        stopping=await changed_while_claiming(lambda i:db.execute("UPDATE local_jobs SET stop_requested=true WHERE id=%s",(i,)))
        withdrawn=await changed_while_claiming(lambda i:db.execute("UPDATE mcp_servers SET lifecycle='TERMINATING' WHERE id=%s",(SERVER,)))
        ok('F2 claim이 후보를 고른 뒤 취소·정지 요청·종료 전환이 들어오면 수령하지 않는다',
           all(o[0]!='hang' and o[0][0]=='ok' and o[0][1] is None and r['claimed_at'] is None
               for o,r in (cancelled,stopping,withdrawn)),
           states=[r['state'] for _,r in (cancelled,stopping,withdrawn)])

        # F2: the window with claim holding the job row, forced instead of waited for.
        await operate(intake,local)
        jti=str(uuid.uuid4())
        await queued(local,jti=jti)
        entered=asyncio.Event()
        with claim_holding_row(entered):
            holder=asyncio.ensure_future(attempt(local_jobs.claim(device,0)))
            await asyncio.wait_for(entered.wait(),10)
            revoker=asyncio.ensure_future(attempt(revoke(jti)))
            outcome=await watch([holder,revoker])
        ok('F2 claim이 작업 행을 쥐고 있을 때 들어온 토큰 철회가 서로 기다리지 않고 끝난다',outcome[0]!='hang',
           outcome=outcome if outcome[0]=='hang' else [kind for kind,_ in outcome])
        await operate(intake,local)
        await queued(local)
        entered=asyncio.Event()
        with claim_holding_row(entered):
            holder=asyncio.ensure_future(attempt(local_jobs.claim(device,0)))
            await asyncio.wait_for(entered.wait(),10)
            terminator=asyncio.ensure_future(attempt(db.execute("UPDATE mcp_servers SET lifecycle='TERMINATING' WHERE id=%s",(SERVER,))))
            outcome=await watch([holder,terminator])
        ok('F2 claim이 작업 행을 쥐고 있을 때 들어온 종료 전환이 교착 없이 끝난다',
           outcome[0]!='hang' and all(kind in ('ok','not_started') for kind,_ in outcome),
           outcome=outcome if outcome[0]=='hang' else {'claim':outcome[0][0],'terminate':outcome[1][0]})

        # F2: token revocation and cancellation take the same locks as claim; they must neither
        # hang as a cross-connection cycle nor let a revoked job start.
        rounds=40;stuck=[];hangs=0;errors=set();started_revoked=0;winners={'claim':0,'revoke':0}
        for index in range(rounds):
            await operate(intake,local)
            jti=str(uuid.uuid4())
            identity=await queued(local,jti=jti)
            contenders=[local_jobs.claim(device,0),revoke(jti)]
            if index%2:contenders.append(local_jobs.quiesce(user_token=OWNER))
            outcome=await raced(*contenders)
            if outcome[0]=='hang':
                hangs+=1;stuck=stuck or outcome[1];continue
            errors.update(kind for kind,_ in outcome if kind not in ('ok','not_started'))
            await local_jobs.resume(user_token=OWNER)
            won=outcome[0][0]=='ok' and outcome[0][1] is not None
            winners['claim' if won else 'revoke']+=1
            if won:
                try:await local_jobs.validate_job(device,identity,start=True)
                except local_jobs.NotStarted:pass
                else:started_revoked+=1
        ok('F2 토큰 철회·취소·claim 경합에서 교착(서로 기다림) 없이 끝난다',hangs==0 and not errors,rounds=rounds,hangs=hangs,stuck=stuck,errors=sorted(errors),winners=winners)
        ok('F2 철회된 토큰의 작업은 어떤 순서로도 시작되지 않는다',started_revoked==0,started_after_revocation=started_revoked)

        # F2: lifecycle termination against start and claim: never TERMINATING with a started, unstopped job.
        rounds=24;stuck=[];hangs=0;errors=set();broken=0;seen={'start_first':0,'terminate_first':0}
        for index in range(rounds):
            await operate(intake,local)
            await queued(local)
            taken=await local_jobs.claim(device,0)
            outcome=await raced(local_jobs.validate_job(device,taken['id'],start=True),
                                db.execute("UPDATE mcp_servers SET lifecycle='TERMINATING' WHERE id=%s",(SERVER,)))
            if outcome[0]=='hang':
                hangs+=1;stuck=stuck or outcome[1];continue
            errors.update(kind for kind,_ in outcome if kind not in ('ok','not_started') and not kind.endswith(':55000'))
            state=await db.fetch_one("SELECT lifecycle FROM mcp_servers WHERE id=%s",(SERVER,))
            running=await db.fetch_one('SELECT id FROM local_jobs WHERE started_at IS NOT NULL AND stopped_at IS NULL')
            if state['lifecycle']=='TERMINATING' and running:broken+=1
            seen['start_first' if running else 'terminate_first']+=1
            if running:await local_jobs.complete(device,str(running['id']),None,'synthetic stop receipt',stopped=True)
        ok('F2 종료 전환과 시작 경합에서 정지 미확인 실행을 둔 채 종료되지 않는다',broken==0 and hangs==0 and not errors,
           rounds=rounds,broken=broken,hangs=hangs,stuck=stuck,errors=sorted(errors),outcomes=seen)

        rounds=40;stuck=[];hangs=0;errors=set();left=0;claimed_first=0
        for index in range(rounds):
            await operate(intake,local)
            await queued(local)
            outcome=await raced(local_jobs.claim(device,0),
                                db.execute("UPDATE mcp_servers SET lifecycle='TERMINATING' WHERE id=%s",(SERVER,)))
            if outcome[0]=='hang':
                hangs+=1;stuck=stuck or outcome[1];continue
            errors.update(f'{name}:{kind}' for name,(kind,_) in zip(('claim','terminate'),outcome) if kind not in ('ok','not_started'))
            claimed_first+=outcome[0][0]=='ok' and outcome[0][1] is not None
            state=await db.fetch_one("SELECT lifecycle FROM mcp_servers WHERE id=%s",(SERVER,))
            if state['lifecycle']=='TERMINATING' and await db.fetch_one("SELECT id FROM local_jobs WHERE state IN ('queued','claimed')"):left+=1
        ok('F2 종료 전환과 claim 경합에서 교착 없이 끝나고 종료 뒤 대기·수령 작업이 남지 않는다',
           hangs==0 and not errors and left==0,rounds=rounds,hangs=hangs,stuck=stuck,errors=sorted(errors),claimed_before_termination=claimed_first,left_open=left)
    return CHECKS.finish()


if __name__=='__main__':run(main)
