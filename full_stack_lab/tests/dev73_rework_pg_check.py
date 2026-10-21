"""DEV-73 transaction/race checks on an explicitly disposable PostgreSQL database.

No MCP server or engine is created. Synthetic device acknowledgements establish DB semantics
only; a real engine stop receipt still needs the separately authorized device experiment.
"""
import asyncio
import hashlib
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'gateway'))
from app import db, endpoint_plane, local_jobs, registry
from termination_lab_support import APP, add_principal, add_server, apply_schema, isolated_disposal, run

DEVICE='dev73-rework-device'
OWNER='dev73-rework-owner'
SERVER='dev73-rework-server'
NOW=lambda:datetime.now(timezone.utc)


async def fixture():
    await add_principal(OWNER)
    await add_server(SERVER)
    intake=str(uuid.uuid4())
    await db.execute("""INSERT INTO endpoint_agents(endpoint_id,hostname,platform,agent_version,owner_token,status,
        managed_state,local_username,local_uid,device_epoch,policy_hash,heartbeat_at)
        VALUES(%s,'synthetic','linux','synthetic',%s,'active','active','synthetic',2001,'epoch','policy',now())""",(DEVICE,OWNER))
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


async def queued(local,*,deadline=20):
    identity=str(uuid.uuid4())
    dispatch_id=str(uuid.uuid4())
    await db.execute("""INSERT INTO dispatch_intents(request_id,user_token,server_id,tool_name,action,fingerprint)
        VALUES(%s,%s,%s,'synthetic-tool','r','synthetic-fingerprint')""",(dispatch_id,OWNER,SERVER))
    await db.execute("""INSERT INTO local_jobs(id,device_id,user_token,server_id,manifest_sha256,manifest,signature,method,
        params,deadline,policy_generation,device_epoch,device_policy,policy_version,request_id,control_sha256)
        SELECT %s,%s,%s,%s,%s,%s,%s,'tools/call','{}',clock_timestamp()+make_interval(secs=>%s),
        policy_generation,'epoch','policy','version-1',%s,'control-1' FROM local_approvals WHERE server_id=%s""",
        (identity,DEVICE,OWNER,SERVER,local['manifest_sha256'],local_jobs.Jsonb(local['manifest']),local['signature'],deadline,dispatch_id,SERVER))
    return identity


async def main():
    if os.getenv('TERMINATION_DISPOSABLE_LAB')!='1':
        raise RuntimeError('일회성 DB 확인이 필요합니다: TERMINATION_DISPOSABLE_LAB=1')
    await apply_schema()
    await db.execute((APP/'local_run_tables.sql').read_text(encoding='utf-8'))
    intake,local=await fixture()
    device=await db.fetch_one('SELECT * FROM endpoint_agents WHERE endpoint_id=%s',(DEVICE,))
    policy={'policy_hash':'policy'}
    with isolated_disposal(),patch.object(endpoint_plane,'managed_policy',AsyncMock(return_value=policy)),patch.object(registry,'server',return_value={'local':local}),patch.object(local_jobs,'control_generation',return_value='control-1'):
        # F2: the same transition cancels old queued jobs and persists the withdrawn generation.
        identity=await queued(local)
        await db.execute("UPDATE mcp_servers SET lifecycle='TERMINATING' WHERE id=%s",(SERVER,))
        assert await local_jobs.claim(device,0) is None
        row=await db.fetch_one('SELECT * FROM local_jobs WHERE id=%s',(identity,))
        assert row['state']=='expired' and row['claimed_at'] is None
        with patch.dict(os.environ,{'LOCAL_IMAGE_MIRRORS':'mirror.test/mcp'}):
            try:await local_jobs.approve_manifest(local,intake,observed=True)
            except ValueError:pass
            else:raise AssertionError('withdrawn signature generation was replayed')
        # New approval generation is deliberate, never an automatic retry of the old job.
        await db.execute("UPDATE mcp_servers SET lifecycle='OPERATING' WHERE id=%s",(SERVER,))
        local['manifest']['approval']['generation']=2
        local['manifest_sha256']=hashlib.sha256(local_jobs.canonical(local['manifest'])).hexdigest()
        with patch.dict(os.environ,{'LOCAL_IMAGE_MIRRORS':'mirror.test/mcp'}):await local_jobs.approve_manifest(local,intake,observed=True)
        # F7: admission is bounded before another row is inserted, not after a job is sent.
        for _ in range(local_jobs.QUEUE_LIMIT):await queued(local)
        count=await db.fetch_one('SELECT count(*) AS n FROM local_jobs')
        try:await local_jobs.exchange(DEVICE,local,'tools/list',{},1)
        except local_jobs.NotStarted as exc:assert exc.local_policy=='P-RATE-003'
        else:raise AssertionError('queue saturation accepted another job')
        assert (await db.fetch_one('SELECT count(*) AS n FROM local_jobs'))['n']==count['n']
        await db.execute("UPDATE local_jobs SET state='expired',finished_at=now() WHERE state='queued'")
        # F2/F7: simultaneous claims have one winner; expired leases never return to queued.
        await queued(local)
        claims=await asyncio.gather(*[local_jobs.claim(device,0) for _ in range(4)])
        assert sum(c is not None for c in claims)==1
        job=next(c for c in claims if c)
        await local_jobs.validate_job(device,job['id'],start=True)
        try:await local_jobs.validate_job(device,job['id'],start=True)
        except local_jobs.NotStarted:pass
        else:raise AssertionError('a claimed job was executed twice')
        # A final transition is refused until a real/synthetic device stop receipt exists.
        try:await db.execute("UPDATE mcp_servers SET lifecycle='TERMINATING' WHERE id=%s",(SERVER,))
        except Exception as exc:
            assert getattr(exc,'sqlstate',None)=='55000'
        else:raise AssertionError('termination completed with an unconfirmed container')
        barrier=asyncio.create_task(local_jobs.quiesce(server_id=SERVER))
        for _ in range(100):
            row=await db.fetch_one('SELECT stop_requested FROM local_jobs WHERE id=%s',(job['id'],))
            if row['stop_requested']:break
            await asyncio.sleep(.01)
        assert row['stop_requested'] and not barrier.done()
        assert await local_jobs.complete(device,job['id'],None,'synthetic stop receipt',stopped=True)
        await barrier
        await db.execute("UPDATE mcp_servers SET lifecycle='TERMINATING' WHERE id=%s",(SERVER,))
        assert await local_jobs.claim(device,0) is None
        evidence=await db.fetch_one('SELECT * FROM local_job_events WHERE job_id=%s ORDER BY id DESC LIMIT 1',(job['id'],))
        assert evidence['evidence']['stopped_at'] and evidence['evidence']['result_sha256']
        assert await db.fetch_one('SELECT 1 FROM dispatch_intents WHERE request_id=%s',(evidence['request_id'],))
        # F7: stale, never-started rows are cleaned separately from permanent job evidence.
        await db.execute("UPDATE local_jobs SET state='expired',finished_at=now()-interval '2 hours' WHERE started_at IS NULL")
        async with db.transaction() as connection:await local_jobs.cleanup(connection)
        assert await db.fetch_one('SELECT 1 FROM local_job_events WHERE job_id=%s',(job['id'],))
    print('PASS DEV-73 PostgreSQL transition, replay, claim race, stop barrier and evidence checks')
    return 0


if __name__=='__main__':run(main)
