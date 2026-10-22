"""Read only the lab's two public certificate files; no TLS connection or secrets."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import ssl
import subprocess


def check_certificate(path, min_valid_seconds, openssl, now):
    try:
        result = subprocess.run(
            [openssl, "x509", "-in", str(path), "-noout", "-dates"],
            check=True, capture_output=True, text=True, timeout=10,
        )
        dates = dict(line.split("=", 1) for line in result.stdout.splitlines())
        start = ssl.cert_time_to_seconds(dates["notBefore"])
        end = ssl.cert_time_to_seconds(dates["notAfter"])
        if start >= end:
            raise ValueError("Invalid validity interval")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, OverflowError):
        # OpenSSL error text can contain file contents; never forward it.
        return {"status": "error"}
    if start > now:
        status = "not_yet_valid"
    elif end <= now:
        status = "expired"
    elif end <= now + min_valid_seconds:
        status = "expires_soon"
    else:
        status = "ok"
    return {
        "status": status,
        "not_before": datetime.fromtimestamp(start, timezone.utc).isoformat(),
        "not_after": datetime.fromtimestamp(end, timezone.utc).isoformat(),
    }


def check_expiry(tls_dir, min_valid_seconds=172800, openssl="openssl", now=None):
    if min_valid_seconds < 0:
        raise ValueError("Validity threshold must be nonnegative")
    checked_at = datetime.now(timezone.utc).timestamp() if now is None else now
    certificates = {
        name: check_certificate(Path(tls_dir) / filename, min_valid_seconds, openssl, checked_at)
        for name, filename in (("server", "server.pem"), ("ca", "ca.pem"))
    }
    ok = all(item["status"] == "ok" for item in certificates.values())
    return {
        "check": "openbao_local_certificate_expiry",
        "scope": "local_files_only",
        "checked_at": datetime.fromtimestamp(checked_at, timezone.utc).isoformat(),
        "min_valid_seconds": min_valid_seconds,
        "ok": ok,
        "certificates": certificates,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tls-dir", required=True)
    parser.add_argument("--min-valid-seconds", type=int, default=172800)
    parser.add_argument("--openssl", default="openssl")
    args = parser.parse_args(argv)
    if args.min_valid_seconds < 0:
        parser.error("--min-valid-seconds must be nonnegative")
    result = check_expiry(args.tls_dir, args.min_valid_seconds, args.openssl)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
