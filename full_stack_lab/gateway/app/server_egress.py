"""Runtime proxy observations, without inferring an MCP call or an API effect."""
from __future__ import annotations

import hashlib
import ipaddress
import re
from datetime import datetime, timezone


LOG = re.compile(r'^(\S+) (?:CONNECT|NOTICE|ERROR|WARNING)\s+\w{3} +\d+ [\d:.]+ \[\d+\]: (.*)$')
CONNECTED = re.compile(r'^Established connection to host "([^"\s]+)" using file descriptor \d+\.$')
BLOCKED = re.compile(r'^Proxying refused on filtered domain "([^"\s]+)"$')
FAILED = re.compile(r'^opensock: Could not establish a connection to ([^\s]+):(\d+)$')
HOST = re.compile(r'(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?')


def timestamp(value: str) -> datetime:
    # Docker supplies nanoseconds; datetime on all supported Python versions keeps microseconds.
    value = re.sub(r'(\.\d{6})\d+', r'\1', value)
    at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if at.tzinfo is None:
        raise ValueError('timezone required')
    return at.astimezone(timezone.utc)


def parse_log(line: str, container_id: str) -> dict | None:
    """Accept only terminal host messages; never retain request URLs, headers or error bodies."""
    match = LOG.fullmatch(line)
    if not match:
        return None
    raw_at, message = match.groups()
    result = CONNECTED.fullmatch(message)
    outcome, port = 'connected', None
    if not result:
        result, outcome = BLOCKED.fullmatch(message), 'blocked'
    if not result:
        result, outcome = FAILED.fullmatch(message), 'connect_failed'
        if result:
            port = int(result[2])
            if not 1 <= port <= 65535:
                return None
    if not result:
        return None
    host = result[1].lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not HOST.fullmatch(host) or any(not label or len(label) > 63 or
                label.startswith('-') or label.endswith('-') for label in host.split('.')):
            return None
    try:
        timestamp(raw_at)
    except ValueError:
        return None
    return {'event_id': hashlib.sha256((container_id + '\0' + line).encode()).hexdigest(),
            'observed_at': raw_at, 'destination': host, 'port': port, 'outcome': outcome,
            'credential_use': 'unobserved', 'retry_count': None, 'external_effect': 'unverified'}


def correlate(call: dict, intent: dict | None, events: list[dict]) -> list[dict]:
    # shortcut: no MCP request ID in proxy logs; require request-aware telemetry for causation.
    if not intent or not call.get('request_id'):
        return []
    low, high = intent['attempted_at'], call['created_at']
    records = []
    for row in events:
        scope = row['scope']
        try:
            at = timestamp(scope['observed_at'])
        except (KeyError, TypeError, ValueError):
            continue
        if scope.get('server_id') != call.get('server_id') or not low <= at <= high:
            continue
        records.append({'kind': 'server-egress', 'id': row['id'], 'at': at.isoformat(),
                        'title': scope['destination'], 'source': 'runtime-proxy',
                        'correlation_id': scope['event_id'], 'runtime_id': scope['runtime'],
                        'generation': scope['generation'], 'proxy_container_id': scope['proxy_container_id'],
                        'proxy_image_id': scope['proxy_image_id'], 'state': scope['outcome'],
                        'port': scope.get('port'), 'credential_use': 'unobserved',
                        'retry_count': None, 'external_effect': 'unverified',
                        'candidate_request_id': str(call['request_id']), 'candidate_trace_id': call.get('trace_id'),
                        'link_basis': ['same_server', 'dispatch_interval'], 'link_strength': 'corroborating'})
    return records


async def for_decision(call: dict, intent: dict | None) -> dict:
    from . import db

    if not intent or not call.get('request_id'):
        return {'records': [], 'observation_status': 'no_dispatch', 'truncated': False}
    # The event's Docker time, not ingestion time, must fall inside the actual dispatch interval.
    rows = await db.fetch_all(
        """SELECT id, scope FROM approval_events WHERE kind='runtime-egress' AND target_kind='intake'
             AND scope->>'server_id'=%s AND (scope->>'observed_at')::timestamptz BETWEEN %s AND %s
           ORDER BY id DESC LIMIT 201""",
        (call['server_id'], intent['attempted_at'], call['created_at']))
    records = correlate(call, intent, rows[:200])
    return {'records': records, 'observation_status': 'observed' if records else 'unobserved',
            'truncated': len(rows) > 200}
