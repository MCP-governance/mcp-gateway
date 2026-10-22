"""Presidio's unmodified analyzer and anonymizer services at the Gateway boundary.

Ported from origin/main cc086e5 (PDF integration) to v2's real tools. Two changes:

- **Entity allowlist.** v1 inspected small synthetic documents. v2 masks real tool
  output - git logs, SQL rows, web pages - where Presidio's default English
  recognizers (dates, person names, locations, URLs, IPs) would redact the work
  itself. Only regulated identifiers and credentials are inspected.
- **Ignore hook.** A mail recipient is a destination, not disclosed content, and an
  internal colleague's address is not personal data the organisation hides from
  itself. The caller decides; this module only applies the decision.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Callable

import httpx

from . import connections
from .classify import SECRET_PATTERNS, _luhn

ANALYZER = os.getenv("PRESIDIO_ANALYZER_URL", "http://presidio-analyzer:3000")
ANONYMIZER = os.getenv("PRESIDIO_ANONYMIZER_URL", "http://presidio-anonymizer:3000")
# The analyzer serves requests in turn. Six concurrent documentation results queued
# past an 8 s timeout on the appliance and a public result was withheld (fail-closed,
# D-59 pj1). Queue here, where the wait is not the request's timeout, and give the
# request itself room. Still fail-closed when Presidio is really down.
TIMEOUT = float(os.getenv("PRESIDIO_TIMEOUT_SECONDS", "20"))
_slots = asyncio.Semaphore(int(os.getenv("PRESIDIO_CONCURRENCY", "2")))

# Presidio ships English recognizers. These request-local patterns cover the Korean
# identifiers and credential assignments used by this lab without forking Presidio.
RECOGNIZERS = [
    {"name": "Email including reserved test domains", "supported_language": "en",
     "supported_entity": "EMAIL_ADDRESS", "patterns": [
         {"name": "email", "regex": r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z])", "score": 0.85}]},
    # The same shape the DLP labels use: birth date validated, hyphen optional, 1-4 citizens and 5-8 foreign
    # residents. Korean glues its particles to a number ("990101-3123456입니다"), and \b treats Hangul as a word
    # character, so a number followed or preceded by a particle was never a match: a quarter of the resident
    # numbers and 70% of the mobile numbers written that way reached the model unmasked (tests/korean_pii_eval.py).
    # Every pattern here says "not a Latin letter or digit" instead of \b.
    {"name": "Korean resident registration number", "supported_language": "en",
     "supported_entity": "KR_RRN", "patterns": [
         {"name": "rrn", "regex": r"(?<![0-9A-Za-z])\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[- ]?[1-8]\d{6}(?![0-9])", "score": 0.85}]},
    # Mobile numbers with any usual separator and the +82 form; landlines (Seoul 02, area codes, 070, 080) the same way.
    # A number inside a longer code ("SKU-010-1234-5678") is not a telephone number.
    {"name": "Korean telephone number", "supported_language": "en",
     "supported_entity": "KR_PHONE", "patterns": [
         {"name": "mobile", "regex": r"(?<![0-9A-Za-z])(?<![0-9A-Za-z]-)(?:\+?82[-. ]?(?:\(0\)|0)?[-. ]?|\(?0)1[016789]\)?[-. ]?\d{3,4}[-. ]?\d{4}(?![0-9])",
          "score": 0.8},
         {"name": "landline", "regex": r"(?<![0-9A-Za-z])(?<![0-9A-Za-z]-)(?:\+?82[-. ]?(?:\(0\)|0)?[-. ]?|\(?0)(?:2|3[1-3]|4[1-4]|5[1-5]|6[1-4]|70|80)\)?[-. ]?\d{3,4}[-. ]?\d{4}(?![0-9])",
          "score": 0.65}]},
    # Numbers with no shape of their own are masked only behind their label, and the label stays in the text. A
    # date after a word such as "계좌 개설일" is not an account number.
    {"name": "Korean business registration number", "supported_language": "en",
     "supported_entity": "KR_BRN", "patterns": [
         {"name": "brn", "regex": r"(?<=(?:사업자\s*(?:등록\s*)?번호|biz[_ ]?(?:no|number)|business[_ ]registration[_ ](?:no\.?|number))[\"']?\s*(?:는|은|이|가)?\s*[:：=]?\s*[\"']?\s*)\d{3}-?\d{2}-?\d{5}(?![0-9])",
          "score": 0.85}]},
    {"name": "Korean bank account number", "supported_language": "en",
     "supported_entity": "KR_ACCOUNT", "patterns": [
         {"name": "labelled", "regex": r"(?<=(?:계좌\s*번호|계좌|입금\s*계좌|환불\s*계좌)[^\d\n]{0,14}|(?:account[_ ]?(?:no|number)|account(?=[\"']?\s*[:：=]))[\"']?\s*[:：=]?\s*[\"']?\s*)"
                                      r"(?!(?:19|20)\d{2}-\d{2}-\d{2}(?![0-9]))(?:\d{2,6}(?:-\d{2,8}){1,3}|\d{10,14})(?![0-9])",
          "score": 0.85},
         {"name": "bank", "regex": r"(?<=(?:국민|신한|우리|하나|농협|기업|카카오뱅크|토스뱅크|케이뱅크|우체국|SC제일|씨티|IBK|새마을금고|수협|신협)(?:은행)?[^\d\n]{0,10})"
                                   r"(?!(?:19|20)\d{2}-\d{2}-\d{2}(?![0-9]))\d{2,6}(?:-\d{2,8}){1,3}(?![0-9])",
          "score": 0.8}]},
    {"name": "Korean passport number", "supported_language": "en",
     "supported_entity": "KR_PASSPORT", "patterns": [
         {"name": "passport", "regex": r"(?<=(?:여권\s*번호|passport[_ ]?(?:no\.?|number)?)[\"']?\s*(?:는|은|이|가)?\s*[:：=]?\s*[\"']?\s*)[A-Z]\d{3}[A-Z0-9]\d{4}(?![0-9A-Za-z])",
          "score": 0.85}]},
    {"name": "Korean driver licence number", "supported_language": "en",
     "supported_entity": "KR_DRIVER_LICENSE", "patterns": [
         {"name": "licence", "regex": r"(?<![0-9])\d{2}-\d{2}-\d{6}-\d{2}(?![0-9])", "score": 0.8}]},
    # A card number runs through Presidio's own recognizer, which needs \b on both sides too; this one has the
    # Korean-safe boundaries and `analyze` drops what fails the Luhn check, as the built-in one does.
    {"name": "Card number", "supported_language": "en",
     "supported_entity": "CARD_NUMBER", "patterns": [
         {"name": "card", "regex": r"(?<![0-9A-Za-z])(?:\d{4}[- ]?){3}\d{4}(?![0-9])|(?<![0-9A-Za-z])3[47]\d{2}[- ]?\d{6}[- ]?\d{5}(?![0-9])", "score": 0.8}]},
    # An assignment to a name that says it is a secret, in Latin or Korean ("비밀번호는 ...", "DB_PASSWORD=..."). A Korean
    # value has to start with a Latin character, digit or sign: "비밀번호는 영문과숫자를조합해야 합니다" is a sentence. The
    # repeat in front of the label is bounded so a long snake_case identifier stays linear.
    {"name": "Assigned credential", "supported_language": "en",
     "supported_entity": "CREDENTIAL", "patterns": [
         {"name": "assignment", "regex": r"(?i)(?<![A-Za-z0-9])(?:[A-Za-z0-9]+[_-]){0,4}(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|pwd|client[_-]?secret"
                                         r"|aws[_-]?secret[_-]?access[_-]?key|secret[_-]?key|private[_-]?key)[\"']?\s*[:=]\s*[\"']?[^\s\"',;]{6,}",
          "score": 0.85},
         {"name": "korean-label", "regex": r"(?i)(?<![A-Za-z0-9])(?:비밀번호|패스워드|암호|비번|인증\s*키|api\s*키|시크릿(?:\s*키)?|토큰)(?:\s*[:：=]\s*|(?:는|은|이|가)\s*)"
                                            r"[\"']?[A-Za-z0-9!-/:-@\[-`{-~][^\s\"',;]{5,}",
          "score": 0.85}]},
    # Issuer-prefixed tokens (classify.SECRET_PATTERNS). A tool result that carries one is
    # masked before the model sees it; the model never needs the value to do the work.
    {"name": "Issuer-prefixed secret", "supported_language": "en",
     "supported_entity": "SECRET_TOKEN", "patterns": [
         {"name": label, "regex": pattern, "score": 0.9} for label, pattern in SECRET_PATTERNS.items()]},
]
ENTITIES = ["EMAIL_ADDRESS", "KR_RRN", "KR_PHONE", "KR_BRN", "KR_ACCOUNT", "KR_PASSPORT", "KR_DRIVER_LICENSE", "CREDENTIAL", "SECRET_TOKEN",
            "CARD_NUMBER", "CREDIT_CARD", "IBAN_CODE", "US_SSN"]
# Shorter strings cannot hold any of the entities above ("a@b.co" is 6).
MIN_CHARS = 6

Ignore = Callable[[str, str], bool]  # (entity_type, matched value) -> skip it


class InspectionUnavailable(RuntimeError):
    pass


def _client() -> httpx.AsyncClient:
    return connections.shared("presidio", lambda: httpx.AsyncClient(timeout=TIMEOUT, trust_env=False))


async def analyze(text: str, ignore: Ignore | None = None) -> list[dict]:
    if len(text or "") < MIN_CHARS:
        return []
    try:
        async with _slots:
            response = await _client().post(ANALYZER + "/analyze", json={
                "text": text, "language": "en", "score_threshold": 0.6,
                "entities": ENTITIES, "ad_hoc_recognizers": RECOGNIZERS,
            })
            response.raise_for_status()
            findings = response.json()
        if not isinstance(findings, list) or any(
            not isinstance(item, dict)
            or not isinstance(item.get("entity_type"), str)
            or not isinstance(item.get("start"), int)
            or not isinstance(item.get("end"), int)
            or isinstance(item["start"], bool)
            or isinstance(item["end"], bool)
            or not isinstance(item.get("score"), (int, float))
            or isinstance(item["score"], bool)
            or not 0 <= item["score"] <= 1
            or not 0 <= item["start"] < item["end"] <= len(text)
            for item in findings
        ):
            raise ValueError("invalid analyzer response")
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise InspectionUnavailable("PII analyzer unavailable or returned invalid data") from exc
    kept = [{key: item[key] for key in ("entity_type", "start", "end", "score")} for item in findings]
    # An ad-hoc pattern cannot validate; a sixteen-digit group that fails the Luhn check is an order number.
    kept = [item for item in kept if item["entity_type"] != "CARD_NUMBER"
            or _luhn(re.sub(r"\D", "", text[item["start"]:item["end"]]))]
    if ignore:
        kept = [item for item in kept if not ignore(item["entity_type"], text[item["start"]:item["end"]])]
    return kept


async def mask_text(text: str, ignore: Ignore | None = None) -> tuple[str, list[str]]:
    findings = await analyze(text, ignore)
    if not findings:
        return text, []
    try:
        async with _slots:
            response = await _client().post(ANONYMIZER + "/anonymize", json={
                "text": text, "analyzer_results": findings,
                "anonymizers": {"DEFAULT": {"type": "replace", "new_value": "[REDACTED]"}},
            })
            response.raise_for_status()
            masked = response.json()["text"]
        # Treat an incomplete anonymizer result as an output-control failure.
        if not isinstance(masked, str) or any(text[f["start"]:f["end"]] in masked for f in findings):
            raise ValueError("anonymizer left a detected value in its output")
        return masked, sorted({f["entity_type"] for f in findings})
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise InspectionUnavailable("PII anonymizer unavailable or returned invalid data") from exc


# 문서·예시에 흔한 자리표시 값. 실제 자격이 아니라 결과 전체를 보류할 근거가 아니다(10-23 실사용 오탐).
PLACEHOLDER = re.compile(r"(?i)^[\s\"']*(?:<[^<>]{1,60}>|\$\{[^{}]{1,60}\}|\{\{[^{}]{1,60}\}\}|\*{3,}|x{3,}|\.{3}|"
                         r"(?:your|my|example|sample|dummy|test|fake)[-_ ]?[a-z_-]{0,30}|changeme|replace[-_ ]?me|redacted)[\s\"']*$")


def _identifier_number(number: int | float) -> str | None:
    """숫자 값에는 하이픈 같은 서식이 없다. ID·타임스탬프·점수가 서식 패턴(사업자·계좌·전화)에 걸려
    결과 전체를 보류하던 오탐 대신, 숫자 자체로 검증되는 주민번호(생년월일·성별 자리)와 카드번호(Luhn)만 본다."""
    if not isinstance(number, int) or number < 0:
        return None
    digits = str(number)
    if len(digits) == 13:
        month, day, gender = int(digits[2:4]), int(digits[4:6]), digits[6]
        if 1 <= month <= 12 and 1 <= day <= 31 and gender in "12345678":
            return "KR_RRN"
    if 13 <= len(digits) <= 19 and _luhn(digits):
        return "CARD_NUMBER"
    return None


async def mask_payload(value: object, ignore: Ignore | None = None) -> tuple[object, list[str]]:
    """Mask text leaves and preserve the MCP result's JSON shape."""
    keys, numbers, assignments, pending = set(), [], [], [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            keys.update(item)
            pending.extend(item.values())
            assignments.extend((str(key), child) for key, child in item.items() if isinstance(child, str))
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            numbers.append(item)
    # Keys and numeric identifiers cannot be redacted without changing the schema.
    # Inspect them together once, including numbers which string-leaf masking skips.
    found = {kind for kind in map(_identifier_number, numbers) if kind}
    if keys or numbers:
        blob = json.dumps({"keys": sorted(keys), "numbers": numbers}, ensure_ascii=False, allow_nan=False)
        boundary = blob.rindex('"numbers"')
        for f in await analyze(blob, ignore):
            digits = re.sub(r"\D", "", blob[f["start"]:f["end"]])
            # 키 쪽 탐지는 그대로 받는다. 숫자 쪽은 숫자 자체로 검증되는 것만 받는다.
            if f["start"] < boundary or (digits and _identifier_number(int(digits))):
                found.add(f["entity_type"])
    if found:
        # 유형만 남긴다(값은 남기지 않는다). 다음 보류의 원인을 원장 오류로 바로 알 수 있게.
        raise InspectionUnavailable("PII in result keys or numbers cannot be masked while preserving the JSON schema: "
                                    + ", ".join(sorted(set(found))))
    # Low-entropy passwords can evade Gitleaks. Preserve assignment context for
    # Presidio's credential recognizer rather than inspect the value in isolation.
    # Only a match that crosses a synthetic "key=" prefix is a structured credential. One wholly inside a
    # text value (a document quoting client_secret=...) is masked with that string below, not withheld
    # with the whole result (10-23 PJ1: five SDK documents withheld).
    joined = "\n".join(f"{key}={child}" for key, child in assignments)
    prefixes, offset = [], 0
    for key, child in assignments:
        prefixes.append((offset, offset + len(key) + 1))
        offset += len(key) + len(child) + 2
    credentials = [f for f in (await analyze(joined, ignore) if assignments else [])
                   if f["entity_type"] in {"CREDENTIAL", "SECRET_TOKEN"}
                   and any(start <= f["start"] < end < f["end"] for start, end in prefixes)
                   and not PLACEHOLDER.match(joined[f["start"]:f["end"]].split("=", 1)[-1].split(":", 1)[-1])]
    if credentials:
        raise InspectionUnavailable("Credential in structured key/value context is withheld: "
                                    + ", ".join(sorted({f["entity_type"] for f in credentials})))

    async def convert(item: object) -> tuple[object, list[str]]:
        if isinstance(item, str):
            return await mask_text(item, ignore)
        if isinstance(item, list):
            converted = [await convert(child) for child in item]
            return [child for child, _ in converted], sorted({kind for _, kinds in converted for kind in kinds})
        if isinstance(item, dict):
            converted = {key: await convert(child) for key, child in item.items()}
            return ({key: child for key, (child, _) in converted.items()},
                    sorted({kind for _, kinds in converted.values() for kind in kinds}))
        return item, []

    return await convert(value)
