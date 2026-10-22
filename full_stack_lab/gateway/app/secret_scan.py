"""The upstream Gitleaks rule catalog, with no secret values in returned evidence.

Detection runs in this process through libmcpgw_gitleaks.so, the Gitleaks Go
library built as a C-ABI shared object (gateway/native/gitleaks). Starting the
gitleaks binary per inspection cost a process spawn, a temp directory and a full
rule compile on every call. The library keeps the compiled catalog and scans in a
worker thread; ctypes releases the GIL while the scan runs, so the event loop keeps
serving other calls. Same catalog, flags and regexp engine as `gitleaks stdin`
(tests/secret_engine_parity_check.py).
"""
from __future__ import annotations

import asyncio
import ctypes
import json
import os
import re
from urllib.parse import parse_qsl, unquote, urlsplit

from .privacy import InspectionUnavailable
from .classify import SECRET_PATTERNS

LIBRARY = os.getenv("GITLEAKS_LIBRARY", "/usr/local/lib/libmcpgw_gitleaks.so")
# 문서 여러 개를 한 번에 읽는 결과(수십 KB)와 동시 호출에서 5초가 모자라 정상 문서가 보류됐다(10-23 실사용).
TIMEOUT_SECONDS = 20

_slots = asyncio.Semaphore(4)
_library: ctypes.CDLL | None = None


def _engine() -> ctypes.CDLL:
    global _library
    if _library is None:
        library = ctypes.CDLL(LIBRARY)
        library.mcpgw_gitleaks_scan.argtypes = [ctypes.c_char_p, ctypes.c_longlong]
        library.mcpgw_gitleaks_scan.restype = ctypes.c_void_p
        library.mcpgw_gitleaks_free.argtypes = [ctypes.c_void_p]
        library.mcpgw_gitleaks_free.restype = None
        _library = library
    return _library


def rule_ids(data: bytes) -> list[str]:
    """Blocking scan; raises ValueError when the engine reports anything but a result."""
    engine = _engine()
    pointer = engine.mcpgw_gitleaks_scan(data, len(data))
    if not pointer:
        raise ValueError("scanner returned no result")
    try:
        found = json.loads(ctypes.string_at(pointer).decode())
    finally:
        engine.mcpgw_gitleaks_free(pointer)
    if not isinstance(found, dict) or found.get("error"):
        raise ValueError("scanner failed")
    rules = found.get("rules")
    if not isinstance(rules, list) or any(not isinstance(r, str) or not r for r in rules):
        raise ValueError("invalid scanner output")
    return rules


def scan_text(text: str) -> str:
    # Gitleaks token boundaries do not include URL query delimiters.
    # Inspect decoded query values as separate lines as well as the raw input.
    query_values = [value for url in re.findall(r"https?://[^\s<>\"']+", text)
                    for _, value in parse_qsl(urlsplit(url).query, keep_blank_values=True)]
    return "\n".join([text, *query_values])


def _finished(scan: asyncio.Future) -> None:
    _slots.release()
    if not scan.cancelled():
        scan.exception()  # read here, so a scan that outlived its caller is not reported as unhandled


async def labels(text: str) -> list[str]:
    if len(text) < 6:
        return []
    try:
        data = scan_text(text).encode()
        await _slots.acquire()
        # A thread cannot be cancelled: a scan past its time limit keeps running, so its
        # slot is returned when the scan ends, not when the caller stops waiting.
        scan = asyncio.ensure_future(asyncio.to_thread(rule_ids, data))
        scan.add_done_callback(_finished)
        rules = await asyncio.wait_for(asyncio.shield(scan), timeout=TIMEOUT_SECONDS)
    except (OSError, ValueError, TypeError, AttributeError, asyncio.TimeoutError) as exc:
        raise InspectionUnavailable(f"Gitleaks Secret 검사를 완료하지 못했습니다: {type(exc).__name__}") from exc
    return sorted({"gitleaks:" + rule for rule in rules})


ERROR_REDACTED = "[REDACTED]"
_CREDENTIAL_CONTEXT = re.compile(
    r"(?i)(?:authorization|proxy-authorization|access[_-]?token|refresh[_-]?token|id[_-]?token|"
    r"api[_-]?key|client[_-]?secret|password|passwd|secret|credential|signature|sig|token)"
    r"[\"']?\s*[:=]\s*[\"']?[^\s\"'&,;}]+")


async def redact_error(value: str | None) -> str | None:
    if not value:
        return value
    # Gitleaks returns rule IDs, not spans. Withhold the whole diagnostic rather than guess spans.
    try:
        if (len(value) > 500 or _CREDENTIAL_CONTEXT.search(unquote(value))
                or any(re.search(pattern, value) for pattern in SECRET_PATTERNS.values())
                or await labels(value)):
            return ERROR_REDACTED
        return value
    except Exception:
        # A scanner outage must never turn an error into an uninspected output channel.
        return ERROR_REDACTED
