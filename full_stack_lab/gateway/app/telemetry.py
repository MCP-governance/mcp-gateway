"""Small, privacy-safe OpenTelemetry bootstrap shared by HTTP services.

Only routing and outcome metadata belongs in traces.  Tokens, MCP arguments,
tool results and request bodies are evidence and stay in the append-only audit
store; they must not be duplicated into a tracing backend.
"""
from __future__ import annotations

import os
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure(scope: str, default_service: str) -> Any:
    """Configure OTLP/HTTP export once per process and return a tracer."""
    if os.getenv("OTEL_SDK_DISABLED", "").strip().lower() in {"1", "true", "yes"}:
        return trace.get_tracer(scope)

    provider = TracerProvider(resource=Resource.create({
        "service.name": os.getenv("OTEL_SERVICE_NAME", default_service),
        "deployment.environment.name": os.getenv("OTEL_ENVIRONMENT", "local-lab"),
    }))
    endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318"
    ).rstrip("/") + "/v1/traces"
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    try:
        trace.set_tracer_provider(provider)
    except Exception:
        # A test runner may already have installed a provider.  In production each
        # service is a separate process, so this is only a test/embedding concern.
        pass
    return trace.get_tracer(scope)
