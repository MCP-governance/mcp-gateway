"""Verify an optional DSSE/in-toto attestation against configured Ed25519 trust roots."""
from __future__ import annotations

import base64
import json
from pathlib import Path

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
