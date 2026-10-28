"""Static release checks: version, changelog, deploy bundle pinning, and product-document hygiene.

Run from anywhere: python3 deploy/check.py. Exit 1 lists every failure.
"""
import re
import ipaddress
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?$")
SECRETS = ("POSTGRES_PASSWORD", "GITEA_ADMIN_PASSWORD", "MOCK_SSO_PASSWORD", "FLOW_FINGERPRINT_PEPPER",
           "USER_CREDENTIAL_KEY", "AGENT_JWT_PRIVATE_KEY", "AGENT_JWT_PUBLIC_KEY", "DISPOSAL_PRIVATE_KEY",
           "DISPOSAL_PUBLIC_KEY", "LOCAL_MANIFEST_PRIVATE_KEY", "LOCAL_MANIFEST_PUBKEY", "TYPESAFE_API_KEY")
# What a customer receives must not name our appliance, test PCs, accounts, local paths or the way it was built.
HYGIENE = re.compile(r"100\.(83\.175\.111|111\.15\.33|110\.81\.60|80\.43\.21)|192\.168\.85\.\d+|bobysg|[Cc]:[\\/]Users"
                     r"|\b[Pp][Jj][1-3]\b|\b1111\b|/home/kali|kali-linux|Codex가|레인|질책|\bDEV-\d+|\bW\d{1,2}-[A-Z]")
PRODUCT_DOCS = ["README.md", "README.en.md", "CHANGELOG.md", "AGENTS.md", "CLAUDE.md", "docs/ai/RUNBOOK.md",
                "docs/ai/TROUBLESHOOTING.md", "docs/ai/FIELD.md"]
PRIVATE = tuple(ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10"))
IP_LITERAL = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?(?![\w.])")


def private_addresses(line):
    found = []
    for match in IP_LITERAL.finditer(line):
        try:
            address = ipaddress.ip_interface(match[0])
        except ValueError:
            continue
        # Network ranges describe topology, not an appliance or a test PC.
        if "/" in match[0] and address.network.prefixlen < 32 and address.ip == address.network.network_address:
            continue
        if any(address.ip in network for network in PRIVATE):
            found.append(match[0])
    return found


def check() -> list[str]:
    fail = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not SEMVER.match(version):
        fail.append(f"VERSION이 유의적 버전이 아님: {version!r}")
    released = re.findall(r"^## \[(\d[^\]]*)\]", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
    if not released or released[0] != version:
        fail.append(f"CHANGELOG 첫 판본 {released[:1]}이 VERSION {version}과 다름")

    compose = (ROOT / "deploy/compose.yaml").read_text(encoding="utf-8")
    for image in re.findall(r"^\s+image:\s*(\S+)", compose, re.M):
        if not (re.fullmatch(r"mcpgw/[a-z-]+:\$\{MINT_VERSION(:\?)?\}", image)
                or re.fullmatch(r"[^@\s]+:[^:@]+@sha256:[0-9a-f]{64}", image)):
            fail.append(f"deploy 이미지가 판본·digest로 고정되지 않음: {image}")
    for port in re.findall(r'^\s+- "([^"]+)"$', compose, re.M):
        if ":" in port and not port.startswith("${MINT_BIND}:"):
            fail.append(f"deploy 게시 포트가 MINT_BIND 밖: {port}")
    for line in (ROOT / "deploy/.env.example").read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        if key in SECRETS and value:
            fail.append(f".env.example의 {key}에 값이 있음")

    local = {".env", "initial-admin-password", "backups", "ca", "siem", "litellm", "check.py", "__pycache__"}
    targets = PRODUCT_DOCS + [str(p.relative_to(ROOT)) for p in (ROOT / "deploy").rglob("*")
                              if p.is_file() and not local & set(p.relative_to(ROOT / "deploy").parts)]
    # The LiteLLM add-on ships to customers too (D-249); its lab-only secrets folder is local.
    for folder in ("addons/litellm", "full_stack_lab/llm/standalone", "full_stack_lab/integrations/litellm"):
        targets += [str(p.relative_to(ROOT)) for p in (ROOT / folder).rglob("*")
                    if p.is_file() and "secrets" not in p.parts and "__pycache__" not in p.parts]
    address_targets = {ROOT / name for name in targets}
    address_targets.update(p for p in (ROOT / "endpoint-agent").glob("*") if p.is_file())
    address_targets.update((ROOT / "docs/ai").glob("*VALIDATION*.md"))
    address_targets.update((ROOT / "docs/ai").glob("CONTROL_PLANES*.md"))
    address_targets.update((ROOT / "docs/ai").glob("PAC_RUNTIME*.md"))
    address_targets.update((ROOT / "docs/ai/evidence").glob("*.json"))
    address_targets.add(ROOT / "docs/design/NETWORK.md")
    for path in sorted(address_targets):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, 1):
            if private_addresses(line):
                fail.append(f"{path.relative_to(ROOT)}:{number}: 사설·Tailscale 실주소")
    for name in targets:
        path = ROOT / name
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if HYGIENE.search(line):
                fail.append(f"{name}:{number}: 내부 정보·작업 흔적: {line.strip()[:80]}")
    return fail


if __name__ == "__main__":
    failures = check()
    if failures:
        sys.exit("FAIL\n" + "\n".join(failures))
    print("PASS 판본·변경 기록·배포 묶음 고정·제품 문서 위생")
