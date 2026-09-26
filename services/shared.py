"""Keycloak validation and metadata-only OTel emission shared by service processes."""
import asyncio
import json
import os
from functools import lru_cache

import jwt
from fastapi import HTTPException, Request
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter


def internal_headers():
    token = os.environ.get("SERVICE_TOKEN", "")
    if not token:
        raise RuntimeError("SERVICE_TOKEN is required")
    return {"X-Service-Token": token}


@lru_cache
def jwks_client(url):
    return jwt.PyJWKClient(url, cache_jwk_set=True, lifespan=60, timeout=5)


async def authenticate(request: Request, admin=False):
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(401, "Keycloak login required")
    token = header[7:]
    try:
        issuer = os.environ["OIDC_ISSUER"]
        url = os.environ["OIDC_JWKS_URL"]
        key = await asyncio.to_thread(jwks_client(url).get_signing_key_from_jwt, token)
        claims = jwt.decode(token, key.key, algorithms=["RS256"], audience="mcp-gateway", issuer=issuer,
                            options={"require": ["exp", "iat", "sub", "iss", "aud"]})
    except (jwt.PyJWTError, KeyError, ValueError, OSError):
        raise HTTPException(401, "Invalid or expired Keycloak token") from None
    roles = claims.get("realm_access", {}).get("roles", [])
    if not isinstance(roles, list) or (admin and "admin" not in roles):
        raise HTTPException(403, "Administrator role required")
    claims["roles"] = roles
    return claims


@lru_cache
def tracer(service):
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    if endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint), schedule_delay_millis=250))
    return provider.get_tracer("mcp-gateway-architecture")


def emit(service, kind, attrs):
    # No request/response bodies or user credentials are collected. Presidio findings
    # are entity types/counts only; the processor normalizes this evidence centrally.
    safe_keys = {"server", "tool", "subject", "status", "approved", "hash", "finding_count", "entities", "session_id", "method", "transport"}
    safe = {k: v for k, v in attrs.items() if k in safe_keys}
    with tracer(service).start_as_current_span(kind) as span:
        span.set_attribute("evidence.kind", kind)
        span.set_attribute("evidence.data", json.dumps(safe, ensure_ascii=False))
