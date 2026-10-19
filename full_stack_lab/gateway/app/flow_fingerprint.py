"""P-FLOW-001 content match (D-142): does a call's text repeat what this principal read elsewhere.

A read of important data keeps salted hashes of its normalised text, never the text. A later call
to another server is a flow from that read only when its arguments share enough of those hashes.
What cannot be compared (no fingerprint stored, the stored one cannot be read, a failure here) stays
a flow source: the principal-wide mark of D-133 is the floor, so every failure here over-blocks.
No I/O in this module; the ledger queries are in core.py.
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata

SHINGLE = 16      # normalised characters per shingle
MIN_SHARED = 3    # shingles two texts must share to count as the same content (a copied run of 18)
MAX_HASHES = 40000  # a read with more shingles is not fingerprinted and keeps the coarse mark

MATCHED = "열람 후 다른 서버 호출(내용 일치)"
MISMATCH = "열람 후 다른 서버 호출(내용 불일치)"
UNCHECKED = "열람 후 다른 서버 호출(내용 확인 불가)"

_PEPPER = os.getenv("FLOW_FINGERPRINT_PEPPER", "").encode()
# Stored with every row: hashes made under another pepper cannot be compared, and a mismatch they
# would show is no evidence, so such a row counts as unchecked.
KEY_ID = hashlib.blake2b(_PEPPER, digest_size=4).hexdigest()
# Values shorter than a shingle that still identify a person or an account: an address, or nine to 32
# digits with single spaces or hyphens between them (not before ':', so not a time). Every repeat is
# bounded: the arguments are up to 64 KB and an open-ended pattern backtracks quadratically on them.
_IDENTIFIER = re.compile(r"[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){1,8}|\d(?:[ -]?\d){8,31}(?![\d:])")


def leaf_text(value: object, keys: bool = False) -> str:
    """Every string and number in a JSON value, one per line. Unlike the Presidio walk there is no depth
    or list-length cut-off: whatever is left out of the text is left out of the comparison, and an
    argument nested deeper than that cut-off would carry data past it."""
    parts, pending = [], [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            pending.extend(reversed([*item.keys(), *item.values()] if keys else list(item.values())))
        elif isinstance(item, list):
            pending.extend(reversed(item))
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            parts.append(str(item))
    return "\n".join(parts)


def squash(text: str) -> str:
    """Letters and digits only, compatibility-folded and case-folded: spacing, punctuation, case, width
    and zero-width characters no longer change the text."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", text).casefold() if ch.isalnum())


def _hasher(salt: bytes):
    key = hashlib.blake2b(salt + _PEPPER, digest_size=32).digest()
    return lambda item: int.from_bytes(
        hashlib.blake2b(item.encode(), digest_size=8, key=key).digest(), "big", signed=True)


def fingerprint(text: str, salt: bytes, limit: int | None = None) -> tuple[list[int], list[int]]:
    """(shingle hashes, identifier hashes), each distinct and sorted. `limit` bounds how many of each
    there may be (ValueError over it); the shingles are checked before anything is hashed."""
    flat = squash(text)
    if limit is not None and len(flat) - SHINGLE + 1 > limit:
        raise ValueError("fingerprint limit exceeded")
    digest = _hasher(salt)
    shingles = {flat[i:i + SHINGLE] for i in range(len(flat) - SHINGLE + 1)}
    identifiers = {squash(m.group()) for m in _IDENTIFIER.finditer(unicodedata.normalize("NFKC", text))}
    if limit is not None and len(identifiers) > limit:
        raise ValueError("fingerprint limit exceeded")
    return sorted(map(digest, shingles)), sorted(map(digest, identifiers - {""}))


def same_content(read: dict, outbound: tuple[list[int], list[int]]) -> bool:
    """A shared identifier, or MIN_SHARED shared shingles."""
    return (bool(set(read["identifiers"]) & set(outbound[1]))
            or len(set(read["shingles"]) & set(outbound[0])) >= MIN_SHARED)


def narrow(rows: list[dict], outbound_text: str) -> tuple[list[str], dict[str, str]]:
    """(servers still a flow source, what was observed per server).

    A row is {"server_id", "key_id", "salt", "shingles", "identifiers"}; the last four are None for a
    read without a stored fingerprint. A server is dropped only when every one of its reads in the window
    was compared and none matched. Any error answers with every server (the coarse mark).
    """
    servers = sorted({row["server_id"] for row in rows})
    try:
        outbound: dict[bytes, tuple[list[int], list[int]]] = {}
        seen: dict[str, str] = {}
        for row in rows:
            if (row.get("salt") is None or row.get("shingles") is None or row.get("identifiers") is None
                    or row.get("key_id") != KEY_ID):
                state = UNCHECKED
            else:
                salt = bytes(row["salt"])
                if salt not in outbound:
                    outbound[salt] = fingerprint(outbound_text, salt)
                state = MATCHED if same_content(row, outbound[salt]) else MISMATCH
            order = (MATCHED, UNCHECKED, MISMATCH)
            if row["server_id"] not in seen or order.index(state) < order.index(seen[row["server_id"]]):
                seen[row["server_id"]] = state
        return [s for s in servers if seen[s] != MISMATCH], seen
    except Exception:
        return servers, dict.fromkeys(servers, UNCHECKED)
