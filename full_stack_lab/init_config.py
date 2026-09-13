"""Initialize a local random signing key without replacing existing configuration."""
import os
from pathlib import Path
import secrets

path = Path(__file__).resolve().parent / ".env"
content = path.read_text() if path.exists() else "# Local demo settings; do not commit.\n"
lines = content.splitlines()
key_lines = [line for line in lines if line.startswith("AGENT_JWT_SECRET=")]
if not key_lines or not key_lines[-1].split("=", 1)[1].strip():
    lines = [line for line in lines if not line.startswith("AGENT_JWT_SECRET=")]
    lines.append("AGENT_JWT_SECRET=" + secrets.token_urlsafe(48))
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write("\n".join(lines) + "\n")
    print("합성 인증용 로컬 서명 키를 .env에 준비했습니다.")
path.chmod(0o600)
