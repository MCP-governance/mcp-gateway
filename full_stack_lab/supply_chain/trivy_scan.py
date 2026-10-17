"""Shared Trivy report parsing for intake and running images."""
import json
from datetime import datetime, timezone

SEVERITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW")


def database_time(document):
    try:
        value = datetime.fromisoformat(document["VulnerabilityDB"]["UpdatedAt"].replace("Z", "+00:00"))
        return value.astimezone(timezone.utc) if value.tzinfo else None
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def trivy_counts(report, root, limit=200):
    document = json.loads(report.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not document.get("SchemaVersion"):
        raise ValueError("Trivy 결과의 SchemaVersion이 없습니다.")
    counts = {level: 0 for level in SEVERITY_ORDER}
    findings = []
    prefix = str(root).rstrip("/") + "/"
    results = document.get("Results") or []
    if not isinstance(results, list):
        raise ValueError("Trivy Results 형식 오류")
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("Trivy 결과 항목 형식 오류")
        target = result.get("Target", "")
        if not isinstance(target, str):
            raise ValueError("Trivy 대상 형식 오류")
        for group in ("Vulnerabilities", "Misconfigurations", "Secrets"):
            items = result.get(group) or []
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise ValueError("Trivy 발견 항목 형식 오류")
            for item in items:
                severity = str(item.get("Severity", "UNKNOWN")).upper()
                if severity in counts:
                    counts[severity] += 1
                findings.append({
                    "severity": severity,
                    "id": item.get("VulnerabilityID") or item.get("ID") or item.get("RuleID") or group,
                    "title": item.get("Title") or item.get("Message") or group,
                    "target": target[len(prefix):] if target.startswith(prefix) else target,
                    "package": item.get("PkgName"), "installed_version": item.get("InstalledVersion"),
                    "fixed_version": item.get("FixedVersion"), "reference": item.get("PrimaryURL"),
                })
    return counts, findings[:limit] if limit is not None else findings
