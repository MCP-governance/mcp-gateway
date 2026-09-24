"""Presidio's unmodified analyzer and anonymizer services at the Gateway boundary."""

from __future__ import annotations

import os

import httpx

ANALYZER = os.getenv("PRESIDIO_ANALYZER_URL", "http://presidio-analyzer:3000")
ANONYMIZER = os.getenv("PRESIDIO_ANONYMIZER_URL", "http://presidio-anonymizer:3000")

# Presidio ships English recognizers. These request-local patterns cover the Korean
# identifiers and credential assignments used by this lab without forking Presidio.
RECOGNIZERS = [
    {"name": "Email including reserved test domains", "supported_language": "en",
     "supported_entity": "EMAIL_ADDRESS", "patterns": [
         {"name": "email", "regex": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "score": 0.85}]},
    {"name": "Korean resident registration number", "supported_language": "en",
     "supported_entity": "KR_RRN", "patterns": [
         {"name": "rrn", "regex": r"\b\d{6}-[1-4]\d{6}\b", "score": 0.85}]},
    {"name": "Korean mobile number", "supported_language": "en",
     "supported_entity": "KR_PHONE", "patterns": [
         {"name": "mobile", "regex": r"\b01[016789]-?\d{3,4}-?\d{4}\b", "score": 0.8}]},
    {"name": "Assigned credential", "supported_language": "en",
     "supported_entity": "CREDENTIAL", "patterns": [
         {"name": "assignment", "regex": r"(?i)\b(?:api[_-]?key|access[_-]?token|password)\s*[:=]\s*[A-Za-z0-9._-]{8,}\b", "score": 0.85}]},
]


class InspectionUnavailable(RuntimeError):
    pass


async def analyze(text: str) -> list[dict]:
    if not text:
        return []
    try:
        async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
            response = await client.post(ANALYZER + "/analyze", json={
                "text": text, "language": "en", "score_threshold": 0.6,
                "ad_hoc_recognizers": RECOGNIZERS,
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
        return [{key: item[key] for key in ("entity_type", "start", "end", "score")}
                for item in findings]
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise InspectionUnavailable("PII analyzer unavailable or returned invalid data") from exc


async def mask_text(text: str) -> tuple[str, list[str]]:
    findings = await analyze(text)
    if not findings:
        return text, []
    try:
        async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
            response = await client.post(ANONYMIZER + "/anonymize", json={
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


async def mask_payload(value: object) -> tuple[object, list[str]]:
    """Mask text leaves and preserve the MCP result's JSON shape."""
    if isinstance(value, str):
        return await mask_text(value)
    if isinstance(value, list):
        converted = [await mask_payload(item) for item in value]
        return [item for item, _ in converted], sorted({kind for _, kinds in converted for kind in kinds})
    if isinstance(value, dict):
        converted = {key: await mask_payload(item) for key, item in value.items()}
        return ({key: item for key, (item, _) in converted.items()},
                sorted({kind for _, kinds in converted.values() for kind in kinds}))
    return value, []
