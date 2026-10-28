"""Device downloads share local-job authorization; Gitea credentials stay on the appliance."""
from __future__ import annotations

import asyncio
import os
import re
import tempfile
from urllib.parse import quote, urlsplit

import httpx
from fastapi import HTTPException
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from . import db, local_jobs, pac, provenance, registry, review

DOWNLOAD_SLOTS = asyncio.Semaphore(4)


def source_errors(source):
    if not isinstance(source, dict) or set(source) != {'commit', 'sha256', 'runtime', 'entrypoint', 'lock', 'lock_sha256'}:
        return ['승인 소스 항목이 올바르지 않습니다.']
    if (not re.fullmatch(r'[0-9a-f]{40}', str(source['commit']))
            or any(not re.fullmatch(r'[0-9a-f]{64}', str(source[k])) for k in ('sha256', 'lock_sha256'))
            or source['runtime'] not in ('python', 'node')):
        return ['승인 소스 식별자가 올바르지 않습니다.']
    for key in ('entrypoint', 'lock'):
        value = source[key]
        if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./-]{0,255}', value)
                or any(part in ('', '.', '..') for part in value.split('/'))):
            return ['소스 경로는 안전한 상대 경로여야 합니다.']
    if source['runtime'] == 'node' and source['lock'] != 'package-lock.json':
        return ['Node 잠금 파일은 package-lock.json이어야 합니다.']
    return []


def source_for(row):
    source = ((row.get('evidence') or {}).get('local_run') or {}).get('source')
    if (row.get('intake_kind') != 'repository' or not row.get('validated_at') or source_errors(source)
            or source['commit'] != row.get('commit_sha')
            or source['sha256'] != ((row.get('provenance') or {}).get('artifact') or {}).get('sha256')):
        raise ValueError('검증한 소스와 실행 잠금 정보가 필요합니다.')
    return source


async def authorized_source(device, server_id, digest):
    if not review.SERVER.fullmatch(server_id) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise HTTPException(409, '승인 매니페스트 식별자가 올바르지 않습니다.')
    try:
        device = await local_jobs._device(device['endpoint_id'])
    except local_jobs.NotStarted as exc:
        raise HTTPException(403, str(exc)) from exc
    async with db.transaction() as connection:
        approval = await local_jobs.authorized(connection, device, server_id, digest, 'initialize')
        if not approval:
            raise HTTPException(403, '현재 승인된 MCP 소스만 받을 수 있습니다.')
        if approval['observed']:
            owner = await (await connection.execute('SELECT * FROM principals WHERE token=%s', (device['owner_token'],))).fetchone()
            if not owner or server_id not in pac.servers_for(owner):
                raise HTTPException(403, '이 직원에게 승인된 MCP가 아닙니다.')
        row = await (await connection.execute('SELECT * FROM mcp_intake_requests WHERE id=%s', (approval['intake_id'],))).fetchone()
        if not row:
            raise HTTPException(409, '소스 신청을 확인할 수 없습니다.')
        local = (registry.server(server_id) or {}).get('local') or {}
        spec = local.get('manifest') if approval['observed'] else (row.get('evidence') or {}).get('local_run')
        source = (spec or {}).get('source')
        try:
            if not source or source != source_for(row) or (approval['observed'] and local.get('manifest_sha256') != digest):
                raise ValueError('현재 승인된 소스·잠금와 다릅니다.')
        except (ValueError, OSError, KeyError) as exc:
            raise HTTPException(409, '현재 승인된 소스·잠금를 확인할 수 없습니다.') from exc
        # Select a path only, never a URL from the database: credentials go to the configured Gitea alone.
        parts = urlsplit(row.get('internal_repo_url') or '').path.rstrip('/').split('/')
        org = os.getenv('GITEA_ORG', 'mcp')
        if len(parts) < 3 or parts[-2] != org or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', parts[-1]):
            raise HTTPException(409, '승인 소스 저장소가 없습니다.')
        path = f'/api/v1/repos/{quote(org, safe="")}/{quote(parts[-1], safe="")}/archive/{source["commit"]}.tar.gz'
        return {'source': source, 'path': path, 'intake_id': str(approval['intake_id']),
                'policy_generation': approval['policy_generation'], 'device_epoch': device['device_epoch'],
                'policy_hash': device['policy_hash'], 'owner': device['owner_token']}


async def receive(spool, path):
    async with httpx.AsyncClient(base_url=os.getenv('GITEA_ADMIN_URL', 'http://corp-git:3000').rstrip('/'),
                                auth=(os.getenv('GITEA_ADMIN_USER', ''), os.getenv('GITEA_ADMIN_PASSWORD', '')),
                                timeout=30, trust_env=False, follow_redirects=False) as client:
        async with client.stream('GET', path, headers={'Accept-Encoding': 'identity'}) as response:
            if response.status_code != 200 or response.headers.get('content-encoding', 'identity').lower() != 'identity':
                raise HTTPException(502, '승인 소스를 받지 못했습니다.')
            length = response.headers.get('content-length')
            if length is not None and (not length.isdecimal() or int(length) > provenance.MAX_ARCHIVE_BYTES):
                raise HTTPException(413, '소스 크기 상한을 넘었습니다.')
            total = 0
            async for block in response.aiter_raw(chunk_size=64 << 10):
                total += len(block)
                if total > provenance.MAX_ARCHIVE_BYTES:
                    raise HTTPException(413, '소스 크기 상한을 넘었습니다.')
                await asyncio.to_thread(spool.write, block)
            if not total or (length is not None and int(length) != total):
                raise HTTPException(502, '소스 전송이 완료되지 않았습니다.')
    spool.seek(0)
    return total


async def download(device, server_id, digest):
    before = await authorized_source(device, server_id, digest)
    spool = tempfile.SpooledTemporaryFile(max_size=4 << 20)
    try:
        async with DOWNLOAD_SLOTS:
            size = await asyncio.wait_for(receive(spool, before['path']), timeout=120)
        if before != await authorized_source(device, server_id, digest):
            raise HTTPException(409, '소스를 받는 동안 승인이 변경되었습니다.')
        await review.record_event('local-source-download', 'recorded', 'server', server_id, device['endpoint_id'],
                                  scope={'manifest_sha256': digest, 'commit': before['source']['commit'],
                                         'sha256': before['source']['sha256'], 'bytes': size, 'intake_id': before['intake_id']})
    except (httpx.HTTPError, asyncio.TimeoutError) as exc:
        spool.close()
        raise HTTPException(502, '승인 소스에 연결하지 못했습니다.') from exc
    except BaseException:
        spool.close()
        raise

    async def chunks():
        try:
            while block := await asyncio.to_thread(spool.read, 64 << 10):
                yield block
        finally:
            spool.close()

    return StreamingResponse(chunks(), media_type='application/gzip', background=BackgroundTask(spool.close),
                             headers={'Content-Length': str(size), 'X-Content-SHA256': before['source']['sha256'],
                                      'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
