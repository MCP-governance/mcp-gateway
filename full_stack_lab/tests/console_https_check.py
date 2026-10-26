"""Offline console TLS checks; --docker also validates Caddy and renders Compose, never starts a stack."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "full_stack_lab"
FIELD = LAB / "field"
BASH = shutil.which("bash")
DOCKER = "--docker" in sys.argv
if DOCKER:
    sys.argv.remove("--docker")
    if not shutil.which("docker"):
        sys.exit("FAIL: --docker requires Docker CLI; Caddy/Compose checks were not run.")


class ConsoleTLS(unittest.TestCase):
    def configure(self, values=None, env_text="", setup=""):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, ".env").write_text(env_text, encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if not k.startswith("FIELD_CONSOLE_")}
            env.update(values or {})
            script = '''set -euo pipefail
source "$1"
env_value() { sed -n "s/^$1=//p" .env | tail -1; }
CONSOLE_URL=http://existing:8000
''' + setup + '''
console_tls_configure
printf '%s\\n' "$FIELD_CONSOLE_TLS" "$CONSOLE_URL" "${CONSOLE_TLS_COMPOSE[*]}"
'''
            return subprocess.run([BASH, "-c", script, "check", (FIELD / "console-tls.sh").as_posix()],
                                  cwd=folder, env=env, capture_output=True, text=True, encoding="utf-8", timeout=10)

    def test_none_preserves_default_and_needs_no_socket_or_files(self):
        result = self.configure()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["none", "http://existing:8000", ""])

    def test_env_file_is_read_and_environment_takes_precedence(self):
        result = self.configure(env_text="FIELD_CONSOLE_TLS=invalid\n")
        self.assertNotEqual(result.returncode, 0)
        result = self.configure({"FIELD_CONSOLE_TLS": "none"}, "FIELD_CONSOLE_TLS=invalid\n")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_mode_or_host_rejected_before_mount_selection(self):
        for mode, name in [("other", "console.example"), ("file", ""), ("file", "https://console.example"),
                           ("file", "console.example:443"), ("file", "*.example"), ("file", "a..example"),
                           ("file", "-a.example"), ("file", "127.0.0.1"), ("file", "a\n.example"),
                           ("tailscale", "console.example"), ("file", "a" * 64 + ".example")]:
            with self.subTest(mode=mode, name=name):
                result = self.configure({"FIELD_CONSOLE_TLS": mode, "FIELD_CONSOLE_NAME": name})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(result.stdout)

    def test_missing_certificate_and_relative_paths_rejected(self):
        for cert, key in [("/missing/cert.pem", "/missing/key.pem"), ("cert.pem", "key.pem"), ("", "")]:
            result = self.configure({"FIELD_CONSOLE_TLS": "file", "FIELD_CONSOLE_NAME": "console.example",
                                     "FIELD_CONSOLE_CERT_FILE": cert, "FIELD_CONSOLE_KEY_FILE": key})
            self.assertNotEqual(result.returncode, 0)

    def test_file_selection_and_private_key_permission_boundary(self):
        for mode in ("600", "400", "640", "644"):
            # Windows ACLs differ from Linux mode bits: simulate only stat's mode result there.
            setup = '''printf certificate > cert.pem; printf key > key.pem
FIELD_CONSOLE_CERT_FILE="$(pwd)/cert.pem"; FIELD_CONSOLE_KEY_FILE="$(pwd)/key.pem"
chmod ''' + mode + ''' key.pem
'''
            if os.name == "nt":
                setup += "stat() { printf '%s\\n' " + mode + "; }\n"
            result = self.configure({"FIELD_CONSOLE_TLS": "file", "FIELD_CONSOLE_NAME": "Console.Example"}, setup=setup)
            with self.subTest(mode=mode):
                if mode in ("600", "400"):
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.splitlines()[:2], ["file", "https://console.example"])
                    self.assertIn("compose.console-file.yaml", result.stdout)
                else:
                    self.assertNotEqual(result.returncode, 0)

    def test_field_dispatch_selects_overlay_and_excludes_duplicate_internal_name(self):
        text = (LAB / "console.sh").read_text(encoding="utf-8")
        dispatch = text[text.index("field_dispatch() {"):text.index('\ncase "${1:-up}"')]
        for mode in ("none", "file"):
            script = '''set -euo pipefail
source "$1"
env_value() { return 0; }
tailscale() { printf '100.64.0.1\\n'; }
stat() { printf '600\\n'; }
printf certificate > cert.pem; printf key > key.pem
export FIELD_CONSOLE_TLS="$2" FIELD_CONSOLE_NAME=console.example FIELD_PUBLIC_NAME=CONSOLE.EXAMPLE
export FIELD_CONSOLE_CERT_FILE="$(pwd)/cert.pem" FIELD_CONSOLE_KEY_FILE="$(pwd)/key.pem"
field_up() { printf '%s\\n' "$FIELD_TLS_ADDRESSES" "$CONSOLE_URL" "${FIELD_COMPOSE[*]}"; }
''' + dispatch + '\nfield_dispatch up\n'
            env = {k: v for k, v in os.environ.items() if k != "APPLIANCE_BIND"}
            with tempfile.TemporaryDirectory() as folder, self.subTest(mode=mode):
                result = subprocess.run([BASH, "-c", script, "check", (FIELD / "console-tls.sh").as_posix(), mode],
                                        cwd=folder, env=env, capture_output=True, text=True, encoding="utf-8", timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                if mode == "file":
                    self.assertEqual(result.stdout.splitlines()[:2], ["https://100.64.0.1:8080", "https://console.example"])
                    self.assertIn("compose.field.yaml -f", result.stdout)
                    self.assertIn("compose.console-file.yaml", result.stdout)
                else:
                    self.assertEqual(result.stdout.splitlines()[:2],
                                     ["https://100.64.0.1:8080, https://CONSOLE.EXAMPLE:8080", "http://100.64.0.1:8000"])
                    self.assertEqual(result.stdout.splitlines()[2], "-f compose.yaml -f compose.field.yaml")

    def test_public_urls_and_kit_issuer_remain_ip_based(self):
        field = (LAB / "compose.field.yaml").read_text(encoding="utf-8")
        deploy = (ROOT / "deploy/compose.yaml").read_text(encoding="utf-8")
        for text, bind in ((field, "APPLIANCE_BIND"), (deploy, "MINT_BIND")):
            self.assertIn("IDP_ISSUER: https://${" + bind + ":?}:443" if bind == "MINT_BIND"
                          else "IDP_ISSUER: https://${APPLIANCE_BIND}:443", text)
            self.assertIn("GATEWAY_PUBLIC_MCP_URL: https://${" + bind + "}:443/mcp/", text)
            self.assertNotIn("tailscaled.sock", text)
        caddy = (FIELD / "Caddyfile").read_text(encoding="utf-8")
        self.assertIn("default_sni {$APPLIANCE_BIND}", caddy)
        self.assertIn("tls internal", caddy)
        self.assertIn("http://:8081", caddy)
        self.assertIn("@harness path /mcp/* /oauth/* /api/endpoint/* /api/addon/* /.well-known/*", caddy)
        for mode in ("tailscale", "file"):
            self.assertIn("import browser-console", (FIELD / "console" / (mode + ".caddy")).read_text())
            overlay = (FIELD / ("compose.console-" + mode + ".yaml")).read_text()
            self.assertNotIn("ports:", overlay)
            self.assertIn("read_only: true", overlay)
            self.assertIn("create_host_path: false", overlay)
        self.assertNotIn("tailscaled.sock", (FIELD / "compose.console-file.yaml").read_text())


@unittest.skipUnless(DOCKER, "requires explicit --docker (one-off validation only)")
class ContainerConfig(unittest.TestCase):
    def test_three_caddy_modes_and_six_compose_renders(self):
        image = re.search(r"image: (caddy:\S+)", (LAB / "compose.field.yaml").read_text()).group(1)
        openssl = shutil.which("openssl") or "C:/Program Files/Git/mingw64/bin/openssl.exe"
        with tempfile.TemporaryDirectory() as folder:
            temporary = Path(folder)
            cert, key = temporary / "cert.pem", temporary / "key.pem"
            subprocess.run([openssl, "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
                            "-nodes", "-days", "1", "-subj", "/CN=console.example", "-addext", "subjectAltName=DNS:console.example",
                            "-keyout", str(key), "-out", str(cert)], check=True, capture_output=True, timeout=30)
            empty = temporary / "empty.env"
            empty.touch()
            env = {**os.environ, "APPLIANCE_BIND": "100.64.0.1", "MINT_BIND": "100.64.0.1", "MINT_VERSION": "0.9.0",
                   "FIELD_TLS_ADDRESSES": "https://100.64.0.1:8080", "MINT_TLS_ADDRESSES": "https://100.64.0.1:8080",
                   "FIELD_CONSOLE_NAME": "console.example", "FIELD_CONSOLE_CERT_FILE": str(cert), "FIELD_CONSOLE_KEY_FILE": str(key)}
            for path in (LAB / "compose.yaml", ROOT / "deploy/compose.yaml"):
                for required in re.findall(r"\$\{(\w+):\?[^}]*\}", path.read_text(encoding="utf-8")):
                    env.setdefault(required, "offline-check")
            for mode in ("none", "tailscale", "file"):
                with self.subTest(mode=mode):
                    env["FIELD_CONSOLE_TLS"] = mode
                    env["FIELD_CONSOLE_NAME"] = "console.example.ts.net" if mode == "tailscale" else "console.example"
                    command = ["docker", "run", "--rm", "--network", "none", "-v", f"{FIELD}:/etc/caddy:ro",
                               "-v", f"{temporary}:/run/console-tls:ro"]
                    for name in ("APPLIANCE_BIND", "FIELD_TLS_ADDRESSES", "FIELD_CONSOLE_TLS", "FIELD_CONSOLE_NAME"):
                        command += ["-e", name + "=" + env[name]]
                    command += [image, "caddy", "validate", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
                    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    for deploy in (False, True):
                        directory = ROOT / "deploy" if deploy else LAB
                        command = ["docker", "compose", "--env-file", str(empty), "-f", str(directory / "compose.yaml")]
                        if not deploy:
                            command += ["-f", str(LAB / "compose.field.yaml")]
                        if mode != "none":
                            command += ["-f", str(FIELD / ("compose.console-" + mode + ".yaml"))]
                        result = subprocess.run(command + ["config", "--format", "json"], cwd=directory,
                                                env=env, capture_output=True, text=True, timeout=30, check=True)
                        services = json.loads(result.stdout)["services"]
                        mounts = services["caddy"]["volumes"]
                        socket_mounts = [m for svc in services.values() for m in svc.get("volumes", [])
                                         if m.get("target") == "/var/run/tailscale/tailscaled.sock"]
                        self.assertEqual(len(socket_mounts), int(mode == "tailscale"))
                        if socket_mounts:
                            self.assertTrue(socket_mounts[0]["read_only"])
                            self.assertIn(socket_mounts[0], mounts)
                        self.assertEqual(sum(m["target"].startswith("/run/console-tls/") for m in mounts), 2 if mode == "file" else 0)
                        for name, service in services.items():
                            for port in service.get("ports", []):
                                if port["host_ip"] != "127.0.0.1":
                                    self.assertIn(name, ("caddy", "model-proxy"))
                                    self.assertEqual(port["host_ip"], env["APPLIANCE_BIND"])
                        self.assertEqual(services["agent-service"]["environment"]["IDP_ISSUER"], "https://100.64.0.1:443")


if __name__ == "__main__":
    if not BASH:
        sys.exit("FAIL: bash is required; configuration checks were not run.")
    unittest.main(verbosity=2)
