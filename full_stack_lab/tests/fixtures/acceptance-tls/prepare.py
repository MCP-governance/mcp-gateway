"""Build ephemeral CI TLS material; never alter the reviewed registry or its lock."""
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import ssl
import sys
import tomllib

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ENDPOINT = "https://mcp-fetch-tls:8443/mcp"


def prepare(registry: Path, output: Path, public_bundle: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise ValueError("TLS fixture output must be empty; do not rotate a running fixture")
    source = (registry / "catalog.toml").read_text()
    catalog = tomllib.loads(source)
    old = catalog["servers"]["fetch"]["endpoint"]
    if old != "http://mcp-fetch:8000/mcp" or source.count(f'endpoint = "{old}"') != 1:
        raise ValueError("Reviewed fetch endpoint changed; review the TLS fixture mapping")
    public = public_bundle.read_bytes()
    ssl.create_default_context(cadata=public.decode("ascii"))
    now = datetime.now(UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MINT acceptance temporary CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=2))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
          .sign(ca_key, hashes.SHA256()))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "mcp-fetch-tls")]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=2))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.KeyUsage(True, False, True, False, False, False, False, False, False), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("mcp-fetch-tls")]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    output.mkdir(parents=True, exist_ok=True)
    output.chmod(0o755)
    pem = serialization.Encoding.PEM
    for name, data in {"ca.pem": ca.public_bytes(pem), "server.pem": cert.public_bytes(pem),
                       "ca-bundle.pem": public.rstrip() + b"\n" + ca.public_bytes(pem)}.items():
        (output / name).write_bytes(data)
        (output / name).chmod(0o644)
    # The signing key is never persisted. Only Caddy receives the leaf private key.
    key_file = output / "server.key"
    key_file.touch(mode=0o600)
    key_file.write_bytes(key.private_bytes(pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    shutil.copytree(registry, output / "registry")
    (output / "registry" / "catalog.toml").write_text(source.replace(f'endpoint = "{old}"', f'endpoint = "{ENDPOINT}"'))
    (output / "manifest.json").write_text(json.dumps({
        "endpoint": ENDPOINT, "created_at": now.isoformat(), "expires_at": cert.not_valid_after_utc.isoformat(),
        "source_catalog_sha256": hashlib.sha256((registry / "catalog.toml").read_bytes()).hexdigest(),
        "source_lock_sha256": hashlib.sha256((registry / "contracts.lock.json").read_bytes()).hexdigest(),
        "ca_sha256": ca.fingerprint(hashes.SHA256()).hex(),
        "public_bundle_sha256": hashlib.sha256(public).hexdigest(),
    }, indent=2) + "\n")


if __name__ == "__main__":
    # The gateway image supplies the public roots used by its Linux truststore.
    bundle = ssl.get_default_verify_paths().cafile
    if not bundle:
        raise SystemExit("Gateway image has no default CA bundle")
    prepare(Path(sys.argv[1]), Path(sys.argv[2]), Path(bundle))
    print("Prepared temporary TLS CA and unchanged fetch tool contract for CI")
