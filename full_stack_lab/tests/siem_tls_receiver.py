"""Disposable HTTPS receiver shared by offline TLS and real-PostgreSQL SIEM checks."""
from collections import deque
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sqlite3
import ssl
import threading


def certificates(folder):
    # Reuse the gateway's cryptography dependency; no openssl executable or system trust edits.
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SIEM disposable lab CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, hashes.SHA256()))
    server = (x509.CertificateBuilder()
              .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
              .issuer_name(ca_name).public_key(server_key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
              .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
              .add_extension(x509.KeyUsage(True, False, True, False, False, False, False, False, False), critical=True)
              .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
              .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
              .add_extension(x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()), critical=False)
              .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
              .sign(ca_key, hashes.SHA256()))
    ca_path, cert_path, key_path = (folder / name for name in ("ca.pem", "server.pem", "server.key"))
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    cert_path.write_bytes(server.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(server_key.private_bytes(serialization.Encoding.PEM,
                         serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    key_path.chmod(0o600)
    return ca_path, cert_path, key_path


@contextmanager
def receiver(folder):
    ca, cert, key = certificates(folder)
    store = folder / "received.sqlite"
    with closing(sqlite3.connect(store)) as connection, connection:
        connection.execute("CREATE TABLE events(uid TEXT PRIMARY KEY, payload TEXT NOT NULL)")
    received, failures, replies = [], [], deque([503])

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                uid = payload["metadata"]["uid"]
                if self.path != "/ingest" or self.headers.get("Idempotency-Key") != uid:
                    raise ValueError("delivery contract mismatch")
                code = replies.popleft() if replies else 200
                body = json.dumps(payload, sort_keys=True)
                if code == 200:
                    # Commit before ACK, as required of the receiver; each UID has one stored event.
                    with closing(sqlite3.connect(store)) as connection, connection:
                        connection.execute("INSERT OR IGNORE INTO events(uid,payload) VALUES (?,?)", (uid, body))
                        if connection.execute("SELECT payload FROM events WHERE uid=?", (uid,)).fetchone()[0] != body:
                            raise ValueError("same UID with different payload")
                received.append((uid, code, body))
            except Exception as exc:
                failures.append(type(exc).__name__)
                code = 500
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {"url": f"https://localhost:{server.server_port}/ingest", "token_file": "", "ca_file": str(ca)}, received, failures, store
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


