"""Print a fresh Ed25519 key pair as .env lines.

Run inside the gateway image so the host needs no crypto library:

    docker compose run --rm --no-deps -T --entrypoint python gateway -m app.keygen

Only Agent Service receives the private key. Every verifier receives the public key
and therefore cannot mint a token - that is the whole point of the split.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> None:
    private = Ed25519PrivateKey.generate()
    raw_private = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    raw_public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    print("AGENT_JWT_PRIVATE_KEY=" + base64.urlsafe_b64encode(raw_private).decode())
    print("AGENT_JWT_PUBLIC_KEY=" + base64.urlsafe_b64encode(raw_public).decode())


if __name__ == "__main__":
    main()
