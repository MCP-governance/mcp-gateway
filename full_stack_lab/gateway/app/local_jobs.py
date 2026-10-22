"""Approved local MCP servers run on the caller's own device (DEV-73, D-175).

The gateway keeps one decision path: execute_call judges the call exactly as for a remote
server, and only the transport differs. Each MCP message becomes a row here that the
device's root runner takes over its own outbound long-poll, so the device opens no port and
the managed account never touches the container engine.
"""
from __future__ import annotations

import asyncio
import base64
import contextvars
import hashlib
import json
import os
import posixpath
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from mcp import types
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from . import db

PREFIX = "local:"
UTC = timezone.utc
# shortcut: bounded queues poll their rows; use LISTEN/NOTIFY if measured latency warrants it.
POLL_SECONDS = 0.05
MAX_RESULT_BODY = 262144
MAX_PARAMS_BYTES = int(os.getenv("LOCAL_PARAMS_MAX_BYTES", "65536"))
# Stored-state ceilings. Defaults are the reviewed values; an environment value lets a lab check the real boundary.
ACTIVE_TOTAL_LIMIT = int(os.getenv("LOCAL_JOBS_PENDING_MAX", "64"))
ROW_LIMIT = int(os.getenv("LOCAL_JOBS_ROWS_MAX", "10000"))
RESULT_STORE_BYTES = int(os.getenv("LOCAL_RESULTS_STORE_MAX_BYTES", str(64 * 1024 * 1024)))
CLAIM_SECONDS = 5
RUN_SECONDS = 20
PREPARE_SECONDS = 180
QUEUE_LIMIT = 8
ACTIVE_LIMIT = 1
RATE_LIMIT = 30
RETENTION_SECONDS = 300
evidence_context = contextvars.ContextVar("local_job_evidence", default=None)
transport_context = contextvars.ContextVar("local_job_transport", default={})


IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/:-]{0,200}@sha256:[0-9a-f]{64}$")
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
# Loader and interpreter hooks would let a manifest run code the image does not contain.
ENV_DENIED = re.compile(r"^(LD_|DYLD_|PYTHON|NODE_OPTIONS$|BASH_ENV$|ENV$|PATH$|HOME$)")
REASONS = {"local_file": "로컬 파일", "local_tool": "로컬 도구", "device": "장치"}
# A manifest under review during registration, before the server exists in the registry.
registering: contextvars.ContextVar[dict | None] = contextvars.ContextVar("registering", default=None)


class NotStarted(ConnectionError):
    """The device never took the message: nothing ran."""
    def __init__(self, message, policy_id='MCP-CATALOG-001'):
        super().__init__(message)
        self.local_policy=policy_id


class LocalExecutionError(RuntimeError):
    """Only a persisted, inspected device diagnostic may cross the public error boundary."""


async def failure_message(error, diagnostics=None):
    from . import poisoning, secret_scan
    if diagnostics is None:
        return error
    messages={'permission':'이미지 실행 파일의 권한 때문에 관리 계정으로 실행할 수 없습니다',
              'exited':'로컬 MCP 컨테이너가 종료되었습니다',
              'timeout':'로컬 MCP 준비 또는 실행 기한이 지났습니다',
              'failed':'로컬 MCP 실행을 완료하지 못했습니다'}
    message=messages.get(diagnostics.get('kind'),messages['failed'])
    code=diagnostics.get('exit_code')
    if type(code) is int and 0<=code<=255:
        message+=f' · 종료 코드 {code}'
    tail=diagnostics.get('stderr_tail')
    if isinstance(tail,str) and tail:
        tail=''.join(c for c in tail if c in '\n\t' or ord(c)>=32 and ord(c)!=127)
        # Diagnostics also reach MCP callers; keep the existing output inspection boundary.
        try:
            tail='[오류 본문 숨김]' if poisoning.result_findings(tail) else await secret_scan.redact_error(tail)
        except Exception:
            tail='[오류 본문 숨김]'
        if tail==secret_scan.ERROR_REDACTED:
            tail='[비밀 숨김]'
        message+=' · 표준 오류: '+tail
    return message[:500]


def manifest_errors(manifest: dict, server_id: str) -> list[str]:
    """The same rules the device runner applies again before it starts anything (C10 §8)."""
    errors = []
    if set(manifest) - {"approval"} != {"server_id", "image", "command", "mounts", "env", "reason"}:
        return ["매니페스트 항목은 server_id·image·command·mounts·env·reason만 허용합니다."]
    if manifest["server_id"] != server_id:
        errors.append("매니페스트의 서버 id가 등록 id와 다릅니다.")
    if not isinstance(manifest["image"], str) or not IMAGE.fullmatch(manifest["image"]):
        errors.append("이미지는 sha256 digest로 고정해야 합니다.")
    command = manifest["command"]
    if not isinstance(command, list) or len(command) > 32 or not all(
            isinstance(a, str) and 0 < len(a) <= 512 and chr(0) not in a for a in command):
        errors.append("명령은 문자열 목록(32개 이하)이어야 합니다.")
    mounts = manifest["mounts"]
    if not isinstance(mounts, list) or len(mounts) > 8:
        errors.append("마운트는 8개 이하 목록이어야 합니다.")
    else:
        for item in mounts:
            path = item.get("path") if isinstance(item, dict) else None
            parts = path.split("/") if isinstance(path, str) else []
            if (not isinstance(item, dict) or set(item) != {"path", "mode"} or item["mode"] not in {"ro", "rw"} or not path
                    or path.startswith("/") or posixpath.normpath(path) != path
                    or any(p in {"", ".", ".."} or p.startswith(".") for p in parts)):
                errors.append(f"마운트 경로는 홈 아래 점으로 시작하지 않는 상대 경로만 허용합니다: {path!r}")
    env = manifest["env"]
    if not isinstance(env, dict) or len(env) > 32 or not all(
            ENV_NAME.fullmatch(k) and not ENV_DENIED.match(k) and isinstance(v, str) and len(v) <= 256
            for k, v in env.items()):
        errors.append("환경 변수 이름·값이 허용 범위를 벗어났습니다.")
    reason = manifest["reason"]
    if (not isinstance(reason, dict) or reason.get("kind") not in REASONS
            or not isinstance(reason.get("text"), str) or not 10 <= len(reason["text"].strip()) <= 500):
        errors.append("로컬 실행이 필요한 이유(로컬 파일·로컬 도구·장치)와 설명이 필요합니다.")
    return errors


def approval_window(manifest: dict) -> tuple[int, datetime]:
    try:
        approval = manifest["approval"]
        generation = approval["generation"]
        expires = datetime.fromisoformat(approval["expires_at"])
        if type(generation) is not int or generation < 1 or expires.tzinfo is None or expires <= datetime.now(UTC):
            raise ValueError
        return generation, expires
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("만료되지 않은 승인 서명 세대가 필요합니다.") from exc


def mirror_image(image: str, mirrors: list[str]) -> bool:
    return bool(IMAGE.fullmatch(image) and any(image.startswith(m.rstrip('/') + '/') for m in mirrors if m))


def canonical(manifest: dict) -> bytes:
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def validate_params(params: dict) -> None:
    try:
        size = len(canonical(params))
    except (TypeError, ValueError) as exc:
        raise NotStarted("로컬 실행 요청 인자를 직렬화할 수 없습니다.", "P-RATE-003") from exc
    if size > MAX_PARAMS_BYTES:
        raise NotStarted("로컬 실행 요청 인자가 크기 상한을 넘었습니다.", "P-RATE-003")


def verify(manifest: dict, signature: str) -> bool:
    """The gateway checks the approver's signature too, but the device trusts only its pinned key."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    # A PEM in an env file arrives on one line with literal \n separators.
    pem = os.getenv("LOCAL_MANIFEST_PUBKEY", "").replace("\\n", "\n").strip()
    if not pem:
        raise ValueError("로컬 실행 매니페스트 서명 검증 키가 구성되지 않았습니다.")
    try:
        load_pem_public_key(pem.encode()).verify(base64.b64decode(signature, validate=True), canonical(manifest))
    except (InvalidSignature, ValueError):
        return False
    return True


async def applicant_device(token: str, intake_id: str) -> str:
    """The contract is observed where the applicant will run it: their active managed PC."""
    bound = await db.fetch_one("SELECT local_observer_device FROM mcp_intake_requests WHERE id=%s", (intake_id,))
    if bound and bound.get("local_observer_device"):
        try:
            device = await _device(bound["local_observer_device"])
        except NotStarted:
            device = None  # 키트 재설치로 장치가 바뀌었다. 신청자의 현재 장치로 다시 묶는다(새 서명 세대로 관찰).
        if device:
            if device["owner_token"] != token:
                raise ValueError("관찰 엔드포인트의 소유자가 신청자와 다릅니다.")
            return device["endpoint_id"]
    row = await db.fetch_one(
        """SELECT endpoint_id FROM endpoint_agents WHERE owner_token=%s AND status='active' AND managed_state='active'
           AND local_uid IS NOT NULL ORDER BY heartbeat_at DESC NULLS LAST LIMIT 1""", (token,))
    if not row:
        raise ValueError("신청자의 활성 관리형 PC가 없어 로컬 실행 계약을 확인할 수 없습니다.")
    bound = await db.fetch_one(
        """UPDATE mcp_intake_requests SET local_observer_device=%s WHERE id=%s RETURNING local_observer_device""",
        (row["endpoint_id"], intake_id))
    return bound["local_observer_device"]


def local_block(manifest: dict, signature: str, observer_device: str, server_id: str) -> dict:
    errors = manifest_errors(manifest, server_id)
    if errors:
        raise ValueError(" / ".join(errors))
    if not verify(manifest, signature):
        raise ValueError("매니페스트 서명이 승인 키와 맞지 않습니다.")
    return {"manifest": manifest, "signature": signature, "observer_device": observer_device,
            "manifest_sha256": hashlib.sha256(canonical(manifest)).hexdigest(), "image_signature": "확인 안 됨"}


async def approve_manifest(local: dict, intake_id: str, *, observed: bool = False) -> dict:
    """The review pins the observer and signed generation; a withdrawn generation cannot be revived."""
    generation, expires = approval_window(local["manifest"])
    mirrors = [m.strip() for m in os.getenv("LOCAL_IMAGE_MIRRORS", "").split(',') if m.strip()]
    if not mirror_image(local["manifest"]["image"], mirrors):
        raise ValueError("사전 반입한 내부 미러 digest 이미지만 허용합니다.")
    async with db.transaction() as connection:
        await connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ('local-approval:' + local['manifest']['server_id'],))
        old = await (await connection.execute("SELECT * FROM local_approvals WHERE server_id=%s FOR UPDATE",
                                             (local['manifest']['server_id'],))).fetchone()
        if old and (generation < old['signature_generation'] or
                    (generation == old['signature_generation'] and
                     (old['revoked'] or old['manifest_sha256'] != local['manifest_sha256'] or
                      old['observer_device'] != local['observer_device'] or str(old['intake_id']) != str(intake_id)))):
            raise ValueError("철회되었거나 이전 세대의 매니페스트입니다.")
        await connection.execute(
            """INSERT INTO local_approvals(server_id,intake_id,observer_device,manifest_sha256,signature_generation,expires_at,observed)
               VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(server_id) DO UPDATE SET
                 intake_id=EXCLUDED.intake_id,observer_device=EXCLUDED.observer_device,
                 manifest_sha256=EXCLUDED.manifest_sha256,signature_generation=EXCLUDED.signature_generation,
                 expires_at=EXCLUDED.expires_at,observed=EXCLUDED.observed,revoked=false,
                 policy_generation=local_approvals.policy_generation+1""",
            (local['manifest']['server_id'],intake_id,local['observer_device'],local['manifest_sha256'],generation,expires,observed))
        if old and generation>old['signature_generation']:
            await connection.execute("DELETE FROM local_run_stops WHERE server_id=%s AND user_token='' AND device_id=''",
                                     (local['manifest']['server_id'],))
    return local


def server_of(endpoint: str | None) -> str | None:
    value = (endpoint or "").strip()
    return value[len(PREFIX):] if value.startswith(PREFIX) and value[len(PREFIX):] else None


def control_generation():
    from . import pac, registry
    return hashlib.sha256(canonical({'catalog':registry.catalog_version(),'capabilities':pac.capabilities()})).hexdigest()


async def _device(device_id: str | None) -> dict:
    device = await db.fetch_one("SELECT * FROM endpoint_agents WHERE endpoint_id=%s", (device_id,)) if device_id else None
    if not device or device["status"] != "active" or device["managed_state"] != "active" or not device.get("local_uid"):
        raise NotStarted("로컬 실행을 맡을 활성 관리형 엔드포인트가 없습니다.")
    if not device.get('heartbeat_at') or (datetime.now(UTC)-device['heartbeat_at']).total_seconds() >= 180:
        raise NotStarted("엔드포인트 점검 보고가 만료됐습니다.")
    return device


async def exchange(device_id: str, local: dict, method: str, params: dict, timeout: float) -> dict:
    validate_params(params)
    device = await _device(device_id)
    principal=transport_context.get().get('_principal')
    if (principal is not None and principal!=device['owner_token']) or (method=='tools/call' and principal is None):
        raise NotStarted('전송 신원과 실행 엔드포인트 소유자가 다릅니다.')
    approval_window(local['manifest'])
    job = str(uuid.uuid4())
    run_timeout = min(timeout, RUN_SECONDS)
    # Registration's HTTP proxy already reserves 240 seconds for the first image. Ordinary
    # calls/checks keep their caller's total timeout (and therefore their reservation bound).
    prepare_timeout=0
    if method=='initialize':
        prepare_timeout=PREPARE_SECONDS if registering.get() else min(PREPARE_SECONDS,max(0,timeout-run_timeout))
    timeout = run_timeout + prepare_timeout
    server = local['manifest']['server_id']
    event = evidence_context.get()
    async with db.transaction() as connection:
        # One small admission transaction bounds all three dimensions, including two devices of one owner.
        await admission_locks(connection,device,server)
        await lock_execution(connection,{'user_token':device['owner_token'],'device_id':device_id,
                                        'server_id':server,'token_jti':transport_context.get().get('jti')})
        await cleanup(connection)
        if not await authorized(connection, device, server, local['manifest_sha256'], method):
            raise NotStarted("로컬 실행 승인 또는 정책이 변경됐습니다.")
        for column, value in [('user_token', device['owner_token']), ('device_id',device_id), ('server_id', server)]:
            counts = await (await connection.execute(
                f"""SELECT count(*) FILTER(WHERE state='queued') AS queued,
                     count(*) FILTER(WHERE state='claimed' OR (started_at IS NOT NULL AND stopped_at IS NULL)) AS active,
                     count(*) FILTER(WHERE created_at>clock_timestamp()-interval '60 seconds') AS rate
                     FROM local_jobs WHERE {column}=%s""", (value,))).fetchone()
            if counts['queued'] >= QUEUE_LIMIT or counts['active'] >= ACTIVE_LIMIT or counts['rate'] >= RATE_LIMIT:
                raise NotStarted("로컬 실행 대기열 또는 생성률 상한입니다.", 'P-RATE-003')
        if (await (await connection.execute('SELECT count(*) AS n FROM local_jobs')).fetchone())['n'] >= ROW_LIMIT:
            raise NotStarted("로컬 실행 저장 상한입니다.", 'P-RATE-003')
        if (await (await connection.execute("SELECT count(*) AS n FROM local_jobs WHERE state IN ('queued','claimed')")).fetchone())['n']>=ACTIVE_TOTAL_LIMIT:
            raise NotStarted('로컬 실행 전체 대기열 상한입니다.','P-RATE-003')
        await connection.execute(
            """INSERT INTO local_jobs(id,device_id,user_token,server_id,manifest_sha256,manifest,signature,method,params,deadline,
                                     policy_generation,device_epoch,device_policy,request_id,token_jti,control_sha256,policy_version,run_seconds)
               SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,a.policy_generation,%s,%s,%s,%s,%s,
                 (SELECT source_sha256 FROM policy_versions WHERE status='ACTIVE' ORDER BY activated_at DESC LIMIT 1),%s
                 FROM local_approvals a WHERE a.server_id=%s""",
            (job,device_id,device['owner_token'],server,local['manifest_sha256'],Jsonb(local['manifest']),local['signature'],
             method,Jsonb(params),datetime.now(UTC)+timedelta(seconds=timeout),device['device_epoch'],device['policy_hash'],
             (event or {}).get('request_id'),transport_context.get().get('jti'),control_generation(),run_timeout,server))
    if event is not None and method=='tools/call':
        # An unreadable job is uncertain until a durable row proves it was never claimed.
        event['upstream_attempted']=True
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        row = await db.fetch_one("SELECT * FROM local_jobs WHERE id=%s", (job,))
        if row["state"] == "done":
            await record_evidence(row, event)
            if row["error"]:
                diagnostic=await db.fetch_one("""SELECT evidence->>'failure' AS failure FROM local_job_events
                    WHERE job_id=%s AND evidence ? 'failure' ORDER BY id DESC LIMIT 1""",(job,))
                if diagnostic:
                    raise LocalExecutionError(diagnostic['failure'])
                raise RuntimeError(row["error"])
            return row["result"]
        if row['state'] == 'expired':
            await record_evidence(row,event)
            if row['claimed_at'] is None:
                raise NotStarted("로컬 실행 전에 요청이 취소됐습니다.")
            raise TimeoutError("수령 뒤 로컬 실행 결과를 확인하지 못했습니다.")
        await asyncio.sleep(POLL_SECONDS)
    expired = await db.fetch_one(
        """UPDATE local_jobs SET state='expired',stop_requested=true,finished_at=clock_timestamp()
           WHERE id=%s AND state IN ('queued','claimed') RETURNING *""", (job,))
    row = expired or await db.fetch_one('SELECT * FROM local_jobs WHERE id=%s',(job,))
    await record_evidence(row,event)
    if row['claimed_at'] is None:
        raise NotStarted("엔드포인트가 로컬 실행 요청을 받지 않았습니다.")
    # Taken but unanswered: it may have run. The caller records the outcome as unknown.
    raise TimeoutError("로컬 실행 결과가 기한 안에 오지 않았습니다.")


def remember(row: dict, event: dict | None):
    if event is None:
        return
    view = {key: str(row[key]) if row.get(key) is not None else None for key in
            ('id','request_id','device_id','server_id','method','manifest_sha256','claimed_at','started_at','finished_at','stopped_at','state','result_sha256')}
    event.setdefault('client', {}).setdefault('local_jobs', []).append(view)
    if row['method'] == 'tools/call':
        event['upstream_attempted'] = row['claimed_at'] is not None


async def record_evidence(row, event=None, connection=None):
    remember(row,event)
    snapshot={key:str(row[key]) if row.get(key) is not None else None for key in
              ('state','claimed_at','started_at','finished_at','stopped_at','result_sha256','manifest_sha256','method')}
    execute=connection.execute if connection else db.execute
    await execute('INSERT INTO local_job_events(job_id,request_id,device_id,server_id,evidence) VALUES(%s,%s,%s,%s,%s)',
                  (row['id'],row.get('request_id'),row['device_id'],row['server_id'],Jsonb(snapshot)))


async def cleanup(connection):
    await connection.execute("""UPDATE local_jobs SET state='expired',stop_requested=true,finished_at=clock_timestamp()
        WHERE state IN ('queued','claimed') AND
        (deadline<=clock_timestamp() OR (state='claimed' AND lease_until<=clock_timestamp()))""")
    await connection.execute("""UPDATE local_jobs SET finished_at=clock_timestamp()
        WHERE state='expired' AND finished_at IS NULL""")
    await connection.execute("""INSERT INTO local_job_events(job_id,request_id,device_id,server_id,evidence)
        SELECT j.id,j.request_id,j.device_id,j.server_id,jsonb_build_object('state',j.state,'claimed_at',j.claimed_at,
        'started_at',j.started_at,'finished_at',j.finished_at,'stopped_at',j.stopped_at,'result_sha256',j.result_sha256)
        FROM local_jobs j WHERE j.state IN ('done','expired') AND (j.started_at IS NULL OR j.stopped_at IS NOT NULL)
        AND j.finished_at<clock_timestamp()-make_interval(secs=>%s)
        AND NOT EXISTS(SELECT 1 FROM local_job_events e WHERE e.job_id=j.id)""",(RETENTION_SECONDS,))
    # Operational payloads expire; append-only dispatch/decision evidence is never deleted here.
    await connection.execute("""DELETE FROM local_jobs j WHERE state IN ('done','expired')
        AND (started_at IS NULL OR stopped_at IS NOT NULL)
        AND finished_at<clock_timestamp()-make_interval(secs=>%s)
        AND EXISTS(SELECT 1 FROM local_job_events e WHERE e.job_id=j.id)""", (RETENTION_SECONDS,))


async def authorized(connection, device, server, digest, method, *, generation=None):
    row = await (await connection.execute("""SELECT a.*,s.lifecycle,s.status AS server_status,p.status AS account_status,
        e.managed_state,e.status AS device_status,e.policy_hash,e.device_epoch,e.owner_token,e.local_uid,
        EXISTS(SELECT 1 FROM user_server_suspensions x WHERE x.user_token=e.owner_token
               AND x.server_id=a.server_id AND x.resumed_at IS NULL) AS suspended,
        EXISTS(SELECT 1 FROM local_run_stops x WHERE (x.server_id='' OR x.server_id=a.server_id)
               AND (x.user_token='' OR x.user_token=e.owner_token) AND (x.device_id='' OR x.device_id=e.endpoint_id)) AS stopped,
        EXISTS(SELECT 1 FROM disposal_blocks x WHERE x.server_id=a.server_id AND x.kind IN ('server','credential')) AS disposed,
        EXISTS(SELECT 1 FROM local_manifest_revocations r WHERE r.server_id=a.server_id
               AND r.signature_generation>=a.signature_generation) AS withdrawn
        FROM local_approvals a JOIN endpoint_agents e ON e.endpoint_id=%s JOIN principals p ON p.token=e.owner_token
        JOIN mcp_intake_requests i ON i.id=a.intake_id AND i.local_observer_device=a.observer_device
             -- 원클릭 승인은 승인 전에 신청자 PC에서 계약을 관찰한다(D-192). 운영 실행은 아래 observed·OPERATING 조건이 막는다.
             AND (i.status='APPROVED' OR (NOT a.observed AND i.status IN ('HOLD','VALIDATED')))
        LEFT JOIN mcp_servers s ON s.id=a.server_id WHERE a.server_id=%s
        AND EXISTS(SELECT 1 FROM policy_versions WHERE status='ACTIVE')""", (device['endpoint_id'],server))).fetchone()
    if not row or row['revoked'] or row['withdrawn'] or row['expires_at']<=datetime.now(UTC) or row['manifest_sha256']!=digest:
        return None
    if (row['account_status']!='active' or row['device_status']!='active' or row['managed_state']!='active'
            or row['suspended'] or row['stopped'] or row['disposed'] or row['policy_hash']!=device['policy_hash']
            or row['device_epoch']!=device['device_epoch'] or row['owner_token']!=device['owner_token']
            or row['local_uid']!=device['local_uid'] or (generation is not None and row['policy_generation']!=generation)):
        return None
    if row['observed']:
        return row if row['lifecycle']=='OPERATING' and row['server_status'] in ('READY','DRIFT') else None
    if row['lifecycle'] is not None and (row['lifecycle']!='OPERATING' or row['server_status'] not in ('PENDING','READY','DRIFT')):
        return None
    return row if method in ('initialize','tools/list') and row['observer_device']==device['endpoint_id'] else None


class LocalClient:
    """The subset of the SDK client _call_upstream and discovery use."""

    def __init__(self, device_id: str, local: dict, timeout: float, *, discovery: bool = True):
        self.device_id, self.local, self.timeout = device_id, local, timeout
        self.discovery = discovery
        self.protocol_version = None
        self.server_info = None
        self.reused = False

    def bind_evidence(self, event, claims=None):
        self.event = event
        self.claims=claims or {}
        event.setdefault('client',{})['local_execution']=True

    async def _send(self, method: str, params: dict) -> dict:
        token = evidence_context.set(getattr(self, 'event', None))
        transport = transport_context.set({**getattr(self,'claims',{}),'_principal':getattr(self,'principal',None)})
        try:
            return await exchange(self.device_id, self.local, method, params, self.timeout)
        finally:
            evidence_context.reset(token)
            transport_context.reset(transport)

    # A call's own container initializes and checks the approved contract (description, input and output
    # schema hashes, protocol) on the device before it calls (local-runner execute_job). Answering a call's
    # initialize and tools/list from that approval here saves two container starts per call, which used to
    # spend the call's time budget before the call itself ran (10-23 PJ1). Observation still asks the server.
    async def start(self) -> None:
        if not self.discovery:
            from . import registry
            self.protocol_version = registry.pinned_protocol(self.local["manifest"]["server_id"])
            self.server_info = types.Implementation(name="", version="")
            return
        hello = await self._send("initialize", {})
        self.protocol_version = hello.get("protocolVersion")
        self.server_info = types.Implementation.model_validate(hello.get("serverInfo") or {"name": "", "version": ""})

    async def list_tools(self, cursor=None, **_):
        if not self.discovery:
            rows = await db.fetch_all("SELECT name, description, input_schema, output_schema FROM mcp_tools"
                                      " WHERE server_id=%s AND enabled ORDER BY name", (self.local["manifest"]["server_id"],))
            return types.ListToolsResult.model_validate({"tools": [
                {"name": r["name"], "description": r["description"], "inputSchema": r["input_schema"],
                 **({"outputSchema": r["output_schema"]} if r["output_schema"] is not None else {})} for r in rows]})
        return types.ListToolsResult.model_validate(await self._send("tools/list", {"cursor": cursor} if cursor else {}))

    async def call_tool(self, name: str, arguments: dict):
        from .output_contract import WireRejected
        if getattr(self,'event',None) is not None:
            self.event['upstream_attempted']=False
        result = await self._send("tools/call", {"name": name, "arguments": arguments})
        try:
            return types.CallToolResult.model_validate(result)
        except ValidationError as exc:
            raise WireRejected("도구 응답이 협상된 출력 형식과 일치하지 않습니다.") from exc


@asynccontextmanager
async def session(endpoint: str, timeout: float, device_id: str | None, *, discovery: bool, principal=None):
    from . import registry
    server_id = server_of(endpoint)
    pending = registering.get()
    local = (pending if discovery and pending and pending["manifest"]["server_id"] == server_id
             else (registry.server(server_id) or {}).get("local") or {})
    if not local.get("manifest_sha256"):
        raise NotStarted("승인된 로컬 실행 매니페스트가 없습니다.")
    # Discovery has no caller; the contract is observed on the device the applicant named. A call
    # runs only on the caller's own device and never falls back to another one.
    target = local.get("observer_device") if discovery else device_id
    if not target:
        raise NotStarted("로컬 실행은 관리형 엔드포인트에서 호출해야 합니다.")
    client = LocalClient(target, local, timeout, discovery=discovery)
    client.principal=principal
    await client.start()
    yield client


# ── device side ──────────────────────────────────────────────────────────────

async def claim(device: dict, wait: float) -> dict | None:
    loop = asyncio.get_running_loop()
    end = loop.time() + wait
    while True:
        device = await _device(device['endpoint_id'])
        async with db.transaction() as connection:
            await connection.execute("SELECT pg_advisory_xact_lock(hashtext('local:admission'))")
            await connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ('local:claim:'+device['endpoint_id'],))
            await cleanup(connection)
            row = await (await connection.execute(
                """SELECT * FROM local_jobs WHERE device_id=%s AND state='queued' AND deadline>clock_timestamp()
                   AND NOT EXISTS(SELECT 1 FROM local_jobs a WHERE a.device_id=%s AND
                       (a.state='claimed' OR (a.started_at IS NOT NULL AND a.stopped_at IS NULL)))
                   ORDER BY created_at LIMIT 1""", (device['endpoint_id'],device['endpoint_id']))).fetchone()
            if row:
                # Lock order (D-175): execution locks first, the job row last. The candidate was chosen without a
                # lock, so it is read again under the locks; if it was cancelled or changed meanwhile, nothing is claimed.
                # The per-device claim lock above already serializes claimers, so SKIP LOCKED is not needed.
                await admission_locks(connection,device,row['server_id'])
                await lock_execution(connection,row)
                row = await (await connection.execute(
                    """SELECT * FROM local_jobs WHERE id=%s AND state='queued' AND deadline>clock_timestamp()
                       AND NOT stop_requested AND started_at IS NULL FOR UPDATE""", (row['id'],))).fetchone()
            if row:
                allowed = await authorized(connection,device,row['server_id'],row['manifest_sha256'],row['method'],
                                           generation=row['policy_generation'])
                active = await (await connection.execute("""SELECT count(*) AS n FROM local_jobs WHERE
                   (device_id=%s OR user_token=%s OR server_id=%s) AND
                   (state='claimed' OR (started_at IS NOT NULL AND stopped_at IS NULL))""",
                   (device['endpoint_id'],device['owner_token'],row['server_id']))).fetchone()
                if active['n']>=ACTIVE_LIMIT:
                    row=None
                elif not allowed or not await current_job(connection,row,device):
                    await connection.execute("UPDATE local_jobs SET state='expired',stop_requested=true,finished_at=clock_timestamp() WHERE id=%s",(row['id'],))
                    row=None
                else:
                    row = await (await connection.execute("""UPDATE local_jobs SET state='claimed',claimed_at=clock_timestamp(),
                        lease_until=LEAST(deadline,clock_timestamp()+make_interval(secs=>%s)) WHERE id=%s RETURNING *""",
                        (CLAIM_SECONDS,row['id']))).fetchone()
        if row or loop.time() >= end:
            return row and {**row, "id": str(row["id"]), "deadline": row["deadline"].isoformat(),
                            'lease_until':row['lease_until'].isoformat(), 'device_epoch':device['device_epoch'],
                            'account_uid':device['local_uid']}
        await asyncio.sleep(0.1)


async def lock_execution(connection, row):
    # These locks conflict with every state mutation covered by the database transition guard.
    await connection.execute("SELECT pg_advisory_xact_lock(hashtext('local:policy'))")
    if row.get('token_jti'):
        await connection.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('local:token:'+str(row['token_jti']),))
    await connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",(row['user_token'],))
    for query,value in [("SELECT id FROM mcp_servers WHERE id=%s FOR SHARE",row['server_id']),
                        ("SELECT token FROM principals WHERE token=%s FOR SHARE",row['user_token']),
                        ("SELECT endpoint_id FROM endpoint_agents WHERE endpoint_id=%s FOR SHARE",row['device_id']),
                        ("SELECT server_id FROM local_approvals WHERE server_id=%s FOR SHARE",row['server_id'])]:
        await connection.execute(query,(value,))


async def admission_locks(connection,device,server):
    await connection.execute("SELECT pg_advisory_xact_lock(hashtext('local:admission'))")
    for scope in sorted(['local:account:'+device['owner_token'],
                         'local:device:'+device['endpoint_id'],'local:server:'+server]):
        await connection.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(scope,))


async def current_job(connection,row,device):
    from . import disposal
    if disposal.blocked(jti=row.get('token_jti'),server_id=row['server_id'],raise_errors=True):
        return False
    policy=await (await connection.execute("SELECT source_sha256 FROM policy_versions WHERE status='ACTIVE' ORDER BY activated_at DESC LIMIT 1")).fetchone()
    revoked=await (await connection.execute('SELECT jti FROM agent_revoked_tokens WHERE jti=%s',(row['token_jti'],))).fetchone() if row['token_jti'] else None
    return (bool(policy) and row['policy_version']==policy['source_sha256'] and not revoked
            and row['control_sha256']==control_generation()
            and row['device_epoch']==device['device_epoch'] and row['device_policy']==device['policy_hash'])


async def validate_job(device: dict, job_id: str, *, start=False) -> dict:
    from . import endpoint_plane, registry
    device = await _device(device['endpoint_id'])
    stop = await db.fetch_one('SELECT stop_requested FROM local_jobs WHERE id=%s AND device_id=%s',
                              (job_id, device['endpoint_id']))
    if stop and stop['stop_requested']:
        raise NotStarted("중지 요청이 기록된 로컬 작업입니다.")
    async with db.transaction() as connection:
        row = await (await connection.execute('SELECT * FROM local_jobs WHERE id=%s AND device_id=%s',
                                              (job_id,device['endpoint_id']))).fetchone()
        if not row:
            raise NotStarted("이 엔드포인트의 요청이 아닙니다.")
        await lock_execution(connection,row)
        allowed = await authorized(connection,device,row['server_id'],row['manifest_sha256'],row['method'],
                                   generation=row['policy_generation'])
        policy = await endpoint_plane.managed_policy(device)
        if (not allowed or row['stop_requested'] or row['state']!='claimed' or row['deadline']<=datetime.now(UTC)
                or row['lease_until']<=datetime.now(UTC) or row['device_policy']!=policy['policy_hash']
                or not await current_job(connection,row,device) or device['policy_hash']!=policy['policy_hash']):
            raise NotStarted("정책·서명 세대·철회 상태가 바뀌었거나 실행 기한이 지났습니다.")
        if start:
            run_seconds=min(RUN_SECONDS,row['run_seconds'])
            started = await (await connection.execute("""UPDATE local_jobs SET started_at=clock_timestamp(),
                deadline=LEAST(deadline,clock_timestamp()+make_interval(secs=>%s)),
                lease_until=LEAST(deadline,clock_timestamp()+make_interval(secs=>%s))
                WHERE id=%s AND started_at IS NULL AND state='claimed' AND NOT stop_requested
                AND lease_until>clock_timestamp() AND deadline>clock_timestamp() RETURNING *""",
                (run_seconds,run_seconds,job_id))).fetchone()
            if not started:
                raise NotStarted("이미 실행을 시작한 요청입니다. 다시 실행하지 않습니다.")
            row=started
        elif row['started_at'] is None:
            # A renewal is valid only after every authorization/epoch/expiry check above passed.
            renewed=await connection.execute("""UPDATE local_jobs SET lease_until=LEAST(deadline,
                clock_timestamp()+make_interval(secs=>%s)) WHERE id=%s AND state='claimed'
                AND started_at IS NULL AND NOT stop_requested AND lease_until>clock_timestamp()
                AND deadline>clock_timestamp()""",(CLAIM_SECONDS,job_id))
            if renewed.rowcount!=1:
                raise NotStarted('로컬 실행 수령 임대를 갱신하지 못했습니다.')
        spec = registry.server(row['server_id']) or {}
        if allowed['observed'] and (spec.get('local') or {}).get('manifest_sha256')!=row['manifest_sha256']:
            raise NotStarted("현재 승인 매니페스트와 다릅니다.")
        return {'policy_generation':allowed['policy_generation'],'manifest_sha256':allowed['manifest_sha256'],
                'signature_generation':allowed['signature_generation'],'revoked':False,'lifecycle':allowed['lifecycle'] or 'OBSERVING',
                'device_epoch':device['device_epoch'],'device_policy':policy['policy_hash'],
                'account_uid':device['local_uid'],
                'policy_version':row['policy_version'],
                'control_sha256':row['control_sha256'],
                'protocol_version':registry.pinned_protocol(row['server_id']) if allowed['observed'] else None,
                'expires_at':allowed['expires_at'].isoformat(),'deadline':row['deadline'].isoformat(),
                'contracts':{t['name']:{'description_sha256':t['approved_description_hash'],'schema_sha256':t['approved_schema_hash'],'output_schema_sha256':t['approved_output_schema_hash']} for t in await db.fetch_all('SELECT * FROM mcp_tools WHERE server_id=%s AND enabled',(row['server_id'],))} if allowed['observed'] else {}}


async def complete(device: dict, job_id: str, result: dict | None, error: str | None, *, stopped: bool = False, isolation=None, diagnostics=None) -> bool:
    if (result is None) == (error is None):
        raise ValueError("결과와 오류 중 하나만 보냅니다.")
    if result is not None and len(json.dumps(result)) > MAX_RESULT_BODY:
        result, error = None, "로컬 실행 결과가 상한을 넘었습니다."
    if not stopped:
        raise ValueError("컨테이너 정지 확인이 필요합니다.")
    if error is not None and diagnostics is not None:
        error=await failure_message(error,diagnostics)
    if isolation is not None and len(canonical(isolation))>4096:
        raise ValueError('사용자 매핑 증거 상한입니다.')
    async with db.transaction() as connection:
        await connection.execute("SELECT pg_advisory_xact_lock(hashtext('local:results'))")
        stored=await (await connection.execute('SELECT COALESCE(sum(pg_column_size(result)),0) AS bytes FROM local_jobs')).fetchone()
        if result is not None and stored['bytes']+len(canonical(result))>RESULT_STORE_BYTES:
            result,error=None,'로컬 실행 결과 저장 상한입니다.'
        digest = hashlib.sha256(canonical(result if result is not None else {'error':error})).hexdigest()
        row = await (await connection.execute(
        """UPDATE local_jobs SET state=CASE WHEN state='claimed' AND deadline>clock_timestamp() AND NOT stop_requested
                      THEN 'done' ELSE 'expired' END,result=%s,error=%s,result_sha256=%s,
                      finished_at=clock_timestamp(),stopped_at=clock_timestamp()
           WHERE id=%s AND device_id=%s AND claimed_at IS NOT NULL AND stopped_at IS NULL RETURNING *""",
            (Jsonb(result) if result is not None else None, error and error[:500],digest,job_id,device['endpoint_id']))).fetchone()
        if row:
            await record_evidence(row,connection=connection)
            if diagnostics is not None and error is not None:
                await connection.execute("""INSERT INTO local_job_events(job_id,request_id,device_id,server_id,evidence)
                    VALUES(%s,%s,%s,%s,%s)""",(job_id,row['request_id'],row['device_id'],row['server_id'],Jsonb({'failure':error})))
            if isolation:
                await connection.execute("""INSERT INTO local_job_events(job_id,request_id,device_id,server_id,evidence)
                     VALUES(%s,%s,%s,%s,%s)""",(job_id,row['request_id'],row['device_id'],row['server_id'],Jsonb({'isolation':isolation})))
    return row is not None


def is_local(server_id: str) -> bool:
    from . import registry
    return bool((registry.server(server_id) or {}).get('local'))


async def quiesce(*, server_id='', user_token='', device_id=''):
    """Close admission first, then require a device stop receipt before the final state transition."""
    if not any((server_id,user_token,device_id)):
        raise ValueError('중지 범위가 필요합니다.')
    if server_id and not is_local(server_id):
        return  # a remote server has nothing running on a device: no stop row, no wait
    async with db.transaction() as connection:
        await connection.execute("""INSERT INTO local_run_stops(server_id,user_token,device_id) VALUES(%s,%s,%s)
            ON CONFLICT DO NOTHING""",(server_id,user_token,device_id))
        await connection.execute("""UPDATE local_jobs SET stop_requested=true,
            state=CASE WHEN started_at IS NULL THEN 'expired' ELSE state END,
            finished_at=CASE WHEN started_at IS NULL THEN clock_timestamp() ELSE finished_at END
            WHERE (%s='' OR server_id=%s) AND (%s='' OR user_token=%s) AND (%s='' OR device_id=%s)
              AND state IN ('queued','claimed')""",(server_id,server_id,user_token,user_token,device_id,device_id))
    until = asyncio.get_running_loop().time()+RUN_SECONDS+5
    while await db.fetch_one("""SELECT id FROM local_jobs WHERE started_at IS NOT NULL AND stopped_at IS NULL
        AND (%s='' OR server_id=%s) AND (%s='' OR user_token=%s) AND (%s='' OR device_id=%s) LIMIT 1""",
        (server_id,server_id,user_token,user_token,device_id,device_id)):
        if asyncio.get_running_loop().time()>=until:
            raise RuntimeError('로컬 실행 정지가 확인되지 않아 상태 전환을 보류했습니다.')
        await asyncio.sleep(.1)


async def resume(*, server_id='', user_token='', device_id=''):
    if server_id and not is_local(server_id):
        return
    await db.execute('DELETE FROM local_run_stops WHERE server_id=%s AND user_token=%s AND device_id=%s',
                     (server_id,user_token,device_id))


async def resume_user_stop(connection, server_id: str, user_token: str) -> None:
    """Reopen exactly one pair in the same transaction that resumes its suspension row."""
    if not server_id or not user_token:
        raise ValueError('로컬 재개 범위가 올바르지 않습니다.')
    # The catalog may have changed since suspension. An exact-pair delete is
    # idempotent and never clears a server-wide, user-wide or device stop.
    await connection.execute(
        "DELETE FROM local_run_stops WHERE server_id=%s AND user_token=%s AND device_id=''",
        (server_id,user_token))


async def prepare_token_revocation(connection, tokens):
    """Hold the same token locks as start until the signed revocation and its DB row commit."""
    identities=sorted({str(t['jti']) for t in tokens})
    for identity in identities:
        await connection.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('local:token:'+identity,))
    if not identities:
        return
    await db.execute("""UPDATE local_jobs SET stop_requested=true,
        state=CASE WHEN started_at IS NULL THEN 'expired' ELSE state END,
        finished_at=CASE WHEN started_at IS NULL THEN clock_timestamp() ELSE finished_at END
        WHERE token_jti=ANY(%s::uuid[]) AND state IN ('queued','claimed')""",(identities,))
    until=asyncio.get_running_loop().time()+RUN_SECONDS+5
    while await db.fetch_one('SELECT id FROM local_jobs WHERE token_jti=ANY(%s::uuid[]) AND started_at IS NOT NULL AND stopped_at IS NULL LIMIT 1',(identities,)):
        if asyncio.get_running_loop().time()>=until:
            raise RuntimeError('로컬 실행 정지가 확인되지 않아 토큰 철회를 보류했습니다.')
        await asyncio.sleep(.1)


async def recoverable(device):
    return await db.fetch_all("""SELECT id FROM local_jobs WHERE device_id=%s AND claimed_at IS NOT NULL
        AND stopped_at IS NULL AND (started_at IS NOT NULL OR lease_until<=clock_timestamp()) ORDER BY created_at LIMIT 16""",
        (device['endpoint_id'],))
