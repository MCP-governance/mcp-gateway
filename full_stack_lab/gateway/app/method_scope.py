"""Refuse the MCP methods this gateway does not mediate, instead of leaving them undefined.

A control point that answers `resources/read` or `prompts/get` with an empty result
"because nothing is registered" has no policy on those methods - it merely happens to
be empty today, and gains one the day someone registers a resource. Prompt and
resource content is the main injection path into an agent, so the gateway states
plainly that it does not carry them.
"""
from __future__ import annotations

import logging
from typing import Any

from mcp_types import METHOD_NOT_FOUND
from opentelemetry import trace

from mcp.server.context import CallNext, HandlerResult, ServerMiddleware, ServerRequestContext
from mcp.shared.exceptions import MCPError

logger = logging.getLogger(__name__)

# Connect-time negotiation and liveness. `server/discover` is the modern-era probe the
# SDK sends before `initialize`; refusing it breaks the connection outright, so any
# SDK upgrade has to revisit this set. That fragility is the price of deny-by-default,
# and the SDK version is pinned precisely so the upgrade is a deliberate event.
PROTOCOL_METHODS = frozenset({"initialize", "server/discover", "ping"})
# The only two methods that actually run through the policy path.
MEDIATED_METHODS = frozenset({"tools/list", "tools/call"})
# Everything else - resources/*, prompts/*, completion/*, logging/*, roots/*,
# sampling/*, elicitation/*, subscriptions/* - is refused.
ALLOWED_METHODS = PROTOCOL_METHODS | MEDIATED_METHODS


class MethodScope(ServerMiddleware[Any]):
    """Deny-by-default on the ingress method surface."""

    async def __call__(self, ctx: ServerRequestContext[Any, Any], call_next: CallNext) -> HandlerResult:
        # Notifications (request_id is None) carry the handshake and cancellation and
        # never reach a handler that could act on data, so they pass through.
        if ctx.request_id is not None and ctx.method not in ALLOWED_METHODS:
            span = trace.get_current_span()
            span.set_attribute("mcp.refused_method", ctx.method)
            span.set_attribute("mcp.policy_id", "MCP-METHOD-001")
            logger.warning("MCP-METHOD-001 중개하지 않는 메서드를 거부했습니다: %s", ctx.method)
            raise MCPError(
                METHOD_NOT_FOUND,
                f"MCP-METHOD-001: {ctx.method}은(는) 이 Gateway가 중개하지 않는 메서드입니다.",
            )
        return await call_next(ctx)
