"""Verify an optional DSSE/in-toto attestation against configured Ed25519 trust roots."""
from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

VERIFIED = "검증됨"
MISSING = "확인 안 됨"
UNAVAILABLE = "검증 불가"
MISMATCH = "불일치"
PAYLOAD_TYPE = "application/vnd.in-toto+json"
STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
SLSA_PREDICATE = "https://slsa.dev/provenance/v1"
POLICY_ID = "MCP-SUPPLY-001"
REFERRER_TIMEOUT_SECONDS = 3
REFERRER_TOTAL_SECONDS = 8
REFERRER_MAX_DESCRIPTORS = 16
REFERRER_MAX_BLOBS = 8
REFERRER_MAX_BYTES = 2 << 20
REFERRER_ACCEPT = ", ".join((
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/json",
))


class _SameOriginRedirect(HTTPRedirectHandler):
    def __init__(self, origin: str):
        self.origin = origin

    def redirect_request(self, request, fp, code, msg, headers, new_url):
        if urlsplit(new_url).scheme != "https" or urlsplit(new_url).netloc.lower() != self.origin:
            raise URLError("registry redirect left the configured origin")
        return super().redirect_request(request, fp, code, msg, headers, new_url)


def _registry_get(origin: str, path: str, *, accept: str = REFERRER_ACCEPT, deadline: float | None = None) -> bytes:
    timeout = REFERRER_TIMEOUT_SECONDS if deadline is None else min(REFERRER_TIMEOUT_SECONDS, deadline - time.monotonic())
    if timeout <= 0:
        raise TimeoutError("OCI referrer lookup exceeded time limit")
    request = Request(origin + path, headers={"Accept": accept})
    opener = build_opener(_SameOriginRedirect(urlsplit(origin).netloc.lower()))
    with opener.open(request, timeout=timeout) as response:
        data = response.read(REFERRER_MAX_BYTES + 1)
    if len(data) > REFERRER_MAX_BYTES:
        raise ValueError("OCI referrer response exceeds limit")
    return data


def _attestation_from_index(origin: str, repository: str, index: dict, deadline: float) -> dict | None:
    descriptors = index.get("manifests")
    if not isinstance(descriptors, list):
        descriptors = [index] if isinstance(index, dict) and index.get("layers") else []
    for descriptor in descriptors[:REFERRER_MAX_DESCRIPTORS]:
        if not isinstance(descriptor, dict) or not isinstance(descriptor.get("digest"), str):
            continue
        manifest_bytes = _registry_get(origin, f"/v2/{repository}/manifests/{quote(descriptor['digest'], safe=':')}",
                                       deadline=deadline)
        manifest = json.loads(manifest_bytes)
        layers = manifest.get("layers") or manifest.get("blobs") or []
        config = manifest.get("config")
        candidates = ([config] if isinstance(config, dict) else []) + (layers if isinstance(layers, list) else [])
        for blob in candidates[:REFERRER_MAX_BLOBS]:
            if not isinstance(blob, dict):
                continue
            media_type = str(blob.get("mediaType", "")).lower()
            if "dsse" not in media_type and "in-toto" not in media_type:
                continue
            if isinstance(blob.get("data"), str):
                raw = base64.b64decode(blob["data"], validate=True)
            elif isinstance(blob.get("digest"), str):
                raw = _registry_get(origin, f"/v2/{repository}/blobs/{quote(blob['digest'], safe=':')}", deadline=deadline)
            else:
                continue
            if len(raw) > REFERRER_MAX_BYTES:
                raise ValueError("OCI attestation exceeds limit")
            envelope = json.loads(raw)
            if (isinstance(envelope, dict) and envelope.get("payloadType") == PAYLOAD_TYPE
                    and isinstance(envelope.get("payload"), str) and isinstance(envelope.get("signatures"), list)
                    and envelope["signatures"] and all(isinstance(sig, dict) and isinstance(sig.get("sig"), str)
                                                        for sig in envelope["signatures"])):
                payload = base64.b64decode(envelope["payload"], validate=True)
                json.loads(payload)
                return envelope
    return None


def collect_oci_referrer(registry_origins: list[str], repository: str, digest: str) -> dict | None:
    """Find a DSSE in-toto envelope for an allowed OCI repository; all discovery failures are optional."""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest) or not re.fullmatch(r"[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*", repository):
        return None
    deadline = time.monotonic() + REFERRER_TOTAL_SECONDS
    for origin in registry_origins[:4]:
        parsed = urlsplit(origin)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            continue
        clean_origin = f"https://{parsed.netloc.lower()}"
        referrers = f"/v2/{repository}/referrers/{quote(digest, safe=':')}"
        try:
            try:
                index = json.loads(_registry_get(clean_origin, referrers, deadline=deadline))
            except HTTPError as exc:
                if exc.code not in (404, 405):
                    continue
                fallback_tag = "sha256-" + digest.split(":", 1)[1]
                index = json.loads(_registry_get(clean_origin,
                                                 f"/v2/{repository}/manifests/{fallback_tag}", deadline=deadline))
            if envelope := _attestation_from_index(clean_origin, repository, index, deadline):
                return envelope
        except (OSError, URLError, HTTPError, AttributeError, ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError):
            continue
    return None


def allowed_registry_origins(value: str | None = None) -> list[str]:
    """Read exact HTTPS registry origins from administrator configuration, never from intake input."""
    return [item.strip().rstrip("/") for item in (value if value is not None else
            os.getenv("MCP_PROVENANCE_REGISTRY_ALLOWLIST", "")).split(",") if item.strip()]


def collect_intake_referrer(registry_origins: list[str], repository_url: str, digest: str) -> dict | None:
    """Map an approved GitHub source path to the same path in each configured OCI registry."""
    parsed = urlsplit(repository_url)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.query or parsed.fragment:
        return None
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2:
        return None
    # shortcut: source digest exists before build; use an approved OCI image coordinate when intake supplies one.
    repository = "/".join(part.removesuffix(".git").lower() for part in parts)
    return collect_oci_referrer(registry_origins, repository, digest)


def trust_keys(path: str | Path = "") -> dict:
    """Load the administrator-managed keyid-to-trust-policy map; evidence cannot add keys."""
    if not path:
        return {}
    keys = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(keys, dict) or any(not isinstance(k, str) or not isinstance(v, (str, dict))
                                         for k, v in keys.items()):
        raise ValueError("신뢰 키 설정 형식 오류")
    return keys


def _pae(payload_type: bytes, payload: bytes) -> bytes:
    return b"DSSEv1 " + str(len(payload_type)).encode() + b" " + payload_type + b" " + str(len(payload)).encode() + b" " + payload


def verify_source_attestation(record: dict | None, expected_sha256: str,
                              keys: dict[str, str]) -> dict:
    """Return a separate status for absent, invalid and unverifiable source provenance."""
    verification = (record or {}).get("verification") or {}
    if verification.get("error"):
        return {"status": UNAVAILABLE, "reason": "서명 증명 확인 경로가 실패했습니다."}
    envelope = verification.get("attestation")
    if envelope is None:
        return {"status": MISSING, "reason": "출처 증명이 제공되지 않았습니다."}
    try:
        if not isinstance(envelope, dict) or envelope.get("payloadType") != PAYLOAD_TYPE:
            raise ValueError("지원하지 않는 증명 형식")
        payload_type = envelope["payloadType"].encode("utf-8")
        payload = base64.b64decode(envelope["payload"], validate=True)
        signatures = envelope["signatures"]
        if not isinstance(signatures, list) or not signatures:
            return {"status": MISMATCH, "reason": "제공된 증명에 서명이 없습니다."}
        statement = json.loads(payload)
        if not isinstance(statement, dict) or not isinstance(signatures, list) or any(
            not isinstance(signature, dict) for signature in signatures
        ):
            raise ValueError("증명 구조 오류")
        if statement.get("_type") != STATEMENT_TYPE or statement.get("predicateType") != SLSA_PREDICATE:
            return {"status": MISMATCH, "reason": "SLSA 출처 증명 형식이 아닙니다."}
        subjects = statement.get("subject")
        if not isinstance(subjects, list) or not any(isinstance(subject, dict) and
            isinstance(subject.get("digest"), dict) and subject["digest"].get("sha256") == expected_sha256
            for subject in subjects):
            return {"status": MISMATCH, "reason": "증명 대상 digest가 도입 기록과 다릅니다."}
        if not ((statement.get("predicate") or {}).get("buildDefinition") or {}).get("buildType"):
            return {"status": MISMATCH, "reason": "SLSA 빌드 정의가 없습니다."}
        signed = _pae(payload_type, payload)
        builder_id = (((statement.get("predicate") or {}).get("runDetails") or {}).get("builder") or {}).get("id")
        key_errors = usable_key = False
        for signature in signatures:
            keyid = signature.get("keyid")
            candidates = ({keyid: keys[keyid]} if isinstance(keyid, str) and keyid in keys
                          else keys if not keyid else {})
            for trusted_id, trust in candidates.items():
                try:
                    pem = trust["public_key"] if isinstance(trust, dict) else trust
                    builders = trust.get("builders", []) if isinstance(trust, dict) else []
                    if not builder_id or builder_id not in builders:
                        continue
                    key = serialization.load_pem_public_key(pem.encode("utf-8"))
                    if not isinstance(key, Ed25519PublicKey):
                        key_errors = True
                        continue
                    usable_key = True
                    key.verify(base64.b64decode(signature["sig"], validate=True), signed)
                    return {"status": VERIFIED, "reason": "서명과 도입 digest가 일치합니다.",
                            "keyid": trusted_id, "sha256": expected_sha256}
                except InvalidSignature:
                    continue
                except (ValueError, TypeError, KeyError, AttributeError):
                    key_errors = True
        if key_errors and not usable_key:
            return {"status": UNAVAILABLE, "reason": "설정 신뢰 키를 사용할 수 없습니다."}
        if not keys or not any(not (isinstance(sig, dict) and sig.get("keyid")) or sig.get("keyid") in keys
                               for sig in signatures):
            return {"status": UNAVAILABLE, "reason": "설정된 신뢰 키로 증명을 확인할 수 없습니다."}
        return {"status": MISMATCH, "reason": "신뢰 키의 서명이 유효하지 않습니다."}
    except (OSError, UnicodeError, json.JSONDecodeError, AttributeError, KeyError, TypeError, ValueError) as exc:
        return {"status": UNAVAILABLE, "reason": f"증명 형식을 확인할 수 없습니다 ({type(exc).__name__})."}


def blocking_reason(result: dict) -> str | None:
    if result["status"] in (MISMATCH, UNAVAILABLE):
        return f"{POLICY_ID}: 출처 증명 {result['status']} — {result['reason']}"
    return None
