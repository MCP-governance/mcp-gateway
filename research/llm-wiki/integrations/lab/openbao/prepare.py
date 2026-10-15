"""Create only a new Linux lab directory and TLS files; never start a service."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--owner-uid", type=int, required=True)
    parser.add_argument("--owner-gid", type=int, required=True)
    args = parser.parse_args()
    if sys.platform != "linux" or os.geteuid() != 0:
        raise RuntimeError("Run preparation with privilege on the solution appliance only")
    if not shutil.which("openssl"):
        raise RuntimeError("OpenSSL must be installed by the operator")
    root = Path(args.runtime_dir).expanduser().resolve()
    if not root.is_absolute() or root == Path("/") or len(root.parts) < 4:
        raise ValueError("A dedicated absolute runtime path is required")
    # A rerun must never replace keys or adopt another project's existing data.
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    for name in ("private", "tls", "data", "logs"):
        (root / name).mkdir(mode=0o700)
    private, tls = root / "private", root / "tls"

    def openssl(*argv):
        subprocess.run(["openssl", *map(str, argv)], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, env={"PATH": os.environ["PATH"]})

    openssl("req", "-x509", "-newkey", "rsa:3072", "-sha256", "-nodes", "-days", "30",
            "-subj", "/CN=MCP-Interop-Lab-CA", "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign",
            "-keyout", private / "ca.key", "-out", tls / "ca.pem")
    openssl("req", "-new", "-newkey", "rsa:3072", "-nodes", "-subj", "/CN=openbao",
            "-keyout", tls / "server.key", "-out", private / "server.csr")
    extensions = private / "server.ext"
    extensions.write_text("subjectAltName=DNS:openbao,DNS:localhost,IP:127.0.0.1\n"
                          "extendedKeyUsage=serverAuth\nbasicConstraints=CA:FALSE\n", encoding="utf-8")
    openssl("x509", "-req", "-in", private / "server.csr", "-CA", tls / "ca.pem",
            "-CAkey", private / "ca.key", "-CAcreateserial", "-out", tls / "server.pem",
            "-days", "7", "-sha256", "-extfile", extensions)
    openssl("req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes", "-days", "7",
            "-subj", "/CN=MCP-Interop-Wrong-CA", "-keyout", private / "wrong-ca.key",
            "-out", tls / "wrong-ca.pem")
    for directory in (root, private):
        os.chown(directory, args.owner_uid, args.owner_gid)
        os.chmod(directory, 0o700)
    for path in private.iterdir():
        os.chown(path, args.owner_uid, args.owner_gid)
        os.chmod(path, 0o600)
    # Numeric server identity avoids inheriting host employee privileges.
    for directory in (tls, root / "data", root / "logs"):
        os.chown(directory, 10000, 10000)
        os.chmod(directory, 0o755 if directory == tls else 0o700)
    for path in tls.iterdir():
        os.chown(path, 10000, 10000)
        os.chmod(path, 0o600 if path.suffix == ".key" else 0o644)
    print(json.dumps({"prepared": True, "runtime_dir": str(root), "service_started": False,
                      "tls_private_key_printed": False, "existing_directory_modified": False}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Exception strings from subprocesses and TLS helpers can expose paths/data.
        print(json.dumps({"prepared": False, "error_type": type(exc).__name__}), file=sys.stderr)
        sys.exit(1)
