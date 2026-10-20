"""Sign an approved local MCP manifest (DEV-73, D-175).

Run by the approver on a machine that is not the gateway. The private key never goes to the
appliance: a compromised gateway must not be able to make device runners start new images.

  python sign-local-manifest.py keygen KEYDIR          # once; KEYDIR/manifest.key stays offline
  python sign-local-manifest.py sign KEYDIR manifest.json
"""
import base64
import hashlib
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def canonical(manifest: dict) -> bytes:
    # Must equal gateway/app/local_jobs.canonical and the runner's.
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "keygen":
        folder = Path(sys.argv[2])
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        key = Ed25519PrivateKey.generate()
        private = folder / "manifest.key"
        private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
        private.chmod(0o600)
        (folder / "manifest.pub").write_bytes(key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        print(folder / "manifest.pub")
    elif len(sys.argv) == 4 and sys.argv[1] == "sign":
        key = serialization.load_pem_private_key((Path(sys.argv[2]) / "manifest.key").read_bytes(), None)
        manifest = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
        body = canonical(manifest)
        print(json.dumps({"signature": base64.b64encode(key.sign(body)).decode(),
                          "manifest_sha256": hashlib.sha256(body).hexdigest()}))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
