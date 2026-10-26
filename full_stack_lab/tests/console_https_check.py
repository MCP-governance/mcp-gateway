"""Offline console TLS checks; --docker also validates Caddy and renders Compose, never starts a stack."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
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

# Exercise Unix ownership rules consistently, including on Windows and under /tmp.
# Real container permissions and signals are checked separately with --docker.
FILE_SETUP = '''
id() { printf '10001\\n'; }
stat() {
  case "$2" in
    %u) printf '%s\\n' "${TEST_OWNER:-10001}" ;;
    %g) printf '0\\n' ;;
    %a) case "$3" in
      */key.pem) printf '%s\\n' "${TEST_MODE:-600}" ;;
      */unsafe) printf '%s\\n' "${TEST_PARENT_MODE:-755}" ;;
      *) printf '755\\n' ;;
    esac ;;
  esac
}
mkdir unsafe
printf certificate > unsafe/cert.pem; printf key > unsafe/key.pem
FIELD_CONSOLE_CERT_FILE="$(pwd)/unsafe/cert.pem"; FIELD_CONSOLE_KEY_FILE="$(pwd)/unsafe/key.pem"
'''


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
        for mode in ("600", "400", "640", "644", "660", "000"):
            result = self.configure({"FIELD_CONSOLE_TLS": "file", "FIELD_CONSOLE_NAME": "Console.Example",
                                     "TEST_MODE": mode}, setup=FILE_SETUP)
            with self.subTest(mode=mode):
                if mode in ("600", "400", "640"):
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.splitlines()[:2], ["file", "https://console.example"])
                    self.assertIn("compose.console-file.yaml", result.stdout)
                else:
                    self.assertNotEqual(result.returncode, 0)

    def test_untrusted_owner_and_writable_parent_rejected(self):
        values = {"FIELD_CONSOLE_TLS": "file", "FIELD_CONSOLE_NAME": "console.example"}
        for extra in ({"TEST_OWNER": "12345"}, {"TEST_PARENT_MODE": "775"},
                      {"TEST_PARENT_MODE": "777"}, {"TEST_OWNER": "0", "TEST_MODE": "600"}):
            with self.subTest(extra=extra):
                result = self.configure({**values, **extra}, setup=FILE_SETUP)
                self.assertNotEqual(result.returncode, 0, result.stdout)
        result = self.configure({**values, "TEST_OWNER": "0", "TEST_MODE": "640"}, setup=FILE_SETUP)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_local_tailscale_ip_and_deploy_binding(self):
        deploy = (ROOT / "deploy/mint.sh").read_text(encoding="utf-8")
        guard = deploy[deploy.index('  if [[ "$FIELD_CONSOLE_TLS" == tailscale'):
                       deploy.index('\n  MINT_TLS_ADDRESSES=')]
        for address, bind, accepted in [("100.64.0.1", "100.64.0.1", True),
                                        ("100.64.0.1", "192.168.1.10", False),
                                        ("100.64.0.1", "100.64.0.2", False),
                                        ("192.168.1.10", "192.168.1.10", False), ("100.64.999.1", "100.64.999.1", False),
                                        ("", "100.64.0.1", False)]:
            setup = 'tailscale() { printf "%s\\n" "$TEST_IP"; }; die() { exit 1; }\n'
            setup += 'FIELD_CONSOLE_TLS=tailscale\n' + guard + '\nFIELD_CONSOLE_TLS=none\n'
            result = self.configure({"TEST_IP": address, "MINT_BIND": bind}, setup=setup)
            self.assertEqual(result.returncode == 0, accepted, result.stderr)

    def test_field_dispatch_selects_overlay_and_excludes_duplicate_internal_name(self):
        text = (LAB / "console.sh").read_text(encoding="utf-8")
        dispatch = text[text.index("field_dispatch() {"):text.index('\ncase "${1:-up}"')]
        for mode in ("none", "file"):
            script = '''set -euo pipefail
source "$1"
env_value() { return 0; }
tailscale() { printf '100.64.0.1\\n'; }
''' + FILE_SETUP + '''
export FIELD_CONSOLE_TLS="$2" FIELD_CONSOLE_NAME=console.example FIELD_PUBLIC_NAME=CONSOLE.EXAMPLE
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
        self.assertNotIn("http://:8081", caddy)
        self.assertIn("http://:8081", (FIELD / "console/none.caddy").read_text())
        self.assertIn("@harness path /mcp/* /oauth/* /api/endpoint/* /api/addon/* /.well-known/*", caddy)
        self.assertEqual((FIELD / "console/tailscale.caddy").read_text().strip(), "import file.caddy")
        site = (FIELD / "console/file.caddy").read_text()
        self.assertIn('redir https://{$FIELD_CONSOLE_NAME}{uri} 301', site)
        self.assertNotIn("import browser-console", site[site.index("http://:8081"):])
        for mode in ("tailscale", "file"):
            overlay = (FIELD / ("compose.console-" + mode + ".yaml")).read_text()
            self.assertNotIn("ports:", overlay)
            self.assertIn("read_only: true", overlay)
            self.assertIn("create_host_path: false", overlay)
        self.assertNotIn("tailscaled.sock", (FIELD / "compose.console-file.yaml").read_text())

    def test_preparation_precedes_caddy_start_and_kit_download_uses_console_url(self):
        field = (LAB / "console.sh").read_text(encoding="utf-8")
        deploy = (ROOT / "deploy/mint.sh").read_text(encoding="utf-8")
        for text in (field, deploy):
            self.assertLess(text.index("  console_caddy_prepare "), text.index("up -d --force-recreate caddy"))
        self.assertIn('${CONSOLE_URL}/workspace', field)
        self.assertNotIn('https://${APPLIANCE_BIND}:443/workspace', field)


@unittest.skipUnless(DOCKER, "requires explicit --docker (one-off validation only)")
class ContainerConfig(unittest.TestCase):
    def docker(self, *args, check=True):
        return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=60, check=check)

    def test_certificate_publication_and_failure_keeps_previous_pair(self):
        volume = "mint-h50-cert-" + uuid.uuid4().hex
        image = "tailscale/tailscale:v1.102.4"
        self.docker("volume", "create", volume)
        command = ["run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL", "--tmpfs", "/tmp",
                   "-v", f"{volume}:/out", "-v", f"{FIELD}:/field:ro", "--entrypoint", "sh", image, "-c"]
        try:
            previous = None
            for value in ("first", "first", "second"):
                # CLI unit double, never a replacement MCP or a claim of real issuance.
                script = '''tailscale() {
  shift 2
  cert="$2"; key="$4"
  printf '%s' "$PAIR" > "$cert"; printf '%s' "$PAIR" > "$key"
}
sleep() { exit 0; }
export FIELD_CONSOLE_NAME=console.example.ts.net
. /field/console-cert.sh
'''
                self.docker(*command, "PAIR=" + value + "\n" + script)
                result = self.docker(*command, 'cat /out/current/cert.pem /out/current/key.pem; stat -c %a /out/current/key.pem')
                self.assertEqual(result.stdout, value * 2 + "640\n")
                current = self.docker(*command, "readlink /out/current").stdout
                if value == "first" and previous is not None:
                    self.assertEqual(current, previous, "unchanged certificates must not trigger reloads")
                previous = current
            result = self.docker(*command, 'tailscale() { return 1; }; export FIELD_CONSOLE_NAME=x.ts.net; . /field/console-cert.sh', check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.docker(*command, "readlink /out/current").stdout, previous)
        finally:
            self.docker("volume", "rm", volume, check=False)

    def test_nonroot_redirects_and_signal_reloads_served_certificate(self):
        import ssl
        volume = "mint-h50-tls-" + uuid.uuid4().hex
        name = "mint-h50-caddy-" + uuid.uuid4().hex
        image = re.search(r"image: (caddy:\S+)", (LAB / "compose.field.yaml").read_text()).group(1)
        openssl = shutil.which("openssl") or "C:/Program Files/Git/mingw64/bin/openssl.exe"
        self.docker("volume", "create", volume)
        try:
            with tempfile.TemporaryDirectory() as folder:
                temporary = Path(folder)
                for generation in ("first", "second"):
                    (temporary / generation).mkdir()
                    subprocess.run([openssl, "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
                                    "-nodes", "-days", "1", "-subj", "/CN=console.example",
                                    "-set_serial", "1" if generation == "first" else "2",
                                    "-keyout", str(temporary / generation / "key.pem"),
                                    "-out", str(temporary / generation / "cert.pem")],
                                   check=True, capture_output=True, timeout=30)
                watch = temporary / "watch.sh"
                watch.write_text((FIELD / "console-watch.sh").read_text().replace("sleep 60", "sleep 1"), encoding="utf-8")
                prepare = '''set -eu
cp -R /fixtures/first /fixtures/second /out/
chmod 755 /out; chmod 750 /out/first /out/second
chmod 640 /out/first/*.pem /out/second/*.pem
ln -s first /out/current
'''
                self.docker("run", "--rm", "--network", "none", "-v", f"{volume}:/out", "-v", f"{temporary}:/fixtures:ro",
                            "--entrypoint", "sh", image, "-c", prepare)
                self.docker("run", "-d", "--name", name, "--network", "none", "--user", "10001:0",
                            "--security-opt", "no-new-privileges:true", "--cap-drop", "ALL", "--cap-add", "NET_BIND_SERVICE",
                            "--tmpfs", "/data:uid=10001,gid=0", "--tmpfs", "/config:uid=10001,gid=0",
                            "-v", f"{FIELD}:/etc/caddy:ro", "-v", f"{watch}:/watch.sh:ro",
                            "-v", f"{volume}:/run/console-tls:ro", "-e", "APPLIANCE_BIND=127.0.0.1",
                            "-e", "FIELD_TLS_ADDRESSES=https://127.0.0.1:8080", "-e", "FIELD_CONSOLE_TLS=tailscale",
                            "-e", "FIELD_CONSOLE_NAME=console.example", image, "sh", "/watch.sh")

                def served_cert():
                    result = self.docker("exec", name, "curl", "-ksS", "--noproxy", "*", "--resolve",
                                         "console.example:8080:127.0.0.1", "-o", "/dev/null", "-w", "%{certs}",
                                         "https://console.example:8080/mcp/check", check=False)
                    match = re.search(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", result.stdout, re.S)
                    return ssl.PEM_cert_to_DER_cert(match.group()) if match else None

                for _ in range(40):
                    if served_cert():
                        break
                    time.sleep(0.25)
                first = ssl.PEM_cert_to_DER_cert((temporary / "first/cert.pem").read_text())
                self.assertEqual(served_cert(), first)
                for path in ("/login", "/workspace", "/static/kit/download?x=1", "/git/mcp/repo.git"):
                    result = self.docker("exec", name, "curl", "-sS", "--noproxy", "*", "-D", "-", "-o", "/dev/null",
                                         "http://127.0.0.1:8081" + path)
                    self.assertIn("301", result.stdout.splitlines()[0])
                    self.assertIn("location: https://console.example" + path, result.stdout.lower())
                self.docker("run", "--rm", "--network", "none", "-v", f"{volume}:/out", "--entrypoint", "sh", image,
                            "-c", "ln -s second /out/current.new && mv -Tf /out/current.new /out/current")
                second = ssl.PEM_cert_to_DER_cert((temporary / "second/cert.pem").read_text())
                for _ in range(40):
                    if served_cert() == second:
                        break
                    time.sleep(0.25)
                self.assertEqual(served_cert(), second, self.docker("logs", name).stderr)
                self.assertEqual(self.docker("inspect", "--format", "{{.RestartCount}}", name).stdout.strip(), "0")
        finally:
            self.docker("rm", "-f", name, check=False)
            self.docker("volume", "rm", volume, check=False)

    def test_three_caddy_modes_and_six_compose_renders(self):
        image = re.search(r"image: (caddy:\S+)", (LAB / "compose.field.yaml").read_text()).group(1)
        openssl = shutil.which("openssl") or "C:/Program Files/Git/mingw64/bin/openssl.exe"
        with tempfile.TemporaryDirectory() as folder:
            temporary = Path(folder)
            (temporary / "current").mkdir()
            cert, key = temporary / "current/cert.pem", temporary / "current/key.pem"
            subprocess.run([openssl, "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
                            "-nodes", "-days", "1", "-subj", "/CN=console.example", "-addext", "subjectAltName=DNS:console.example",
                            "-keyout", str(key), "-out", str(cert)], check=True, capture_output=True, timeout=30)
            empty = temporary / "empty.env"
            empty.touch()
            env = {**os.environ, "APPLIANCE_BIND": "100.64.0.1", "MINT_BIND": "100.64.0.1", "MINT_VERSION": "0.9.0",
                   "FIELD_TLS_ADDRESSES": "https://100.64.0.1:8080", "MINT_TLS_ADDRESSES": "https://100.64.0.1:8080",
                   "FIELD_CONSOLE_NAME": "console.example", "FIELD_CONSOLE_CERT_FILE": str(cert), "FIELD_CONSOLE_KEY_FILE": str(key),
                   "CONSOLE_TLS_DIR": str(FIELD)}
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
                        self.assertEqual(services["caddy"]["user"], "10001:0")
                        self.assertFalse(any("tailscaled.sock" in m.get("target", "") for m in mounts))
                        socket_mounts = [m for svc in services.values() for m in svc.get("volumes", [])
                                         if m.get("target") == "/var/run/tailscale/tailscaled.sock"]
                        self.assertEqual(len(socket_mounts), int(mode == "tailscale"))
                        if socket_mounts:
                            self.assertTrue(socket_mounts[0]["read_only"])
                            helper = services["console-cert"]
                            self.assertIn(socket_mounts[0], helper["volumes"])
                            self.assertEqual(helper["network_mode"], "none")
                            self.assertFalse(helper.get("ports"))
                            self.assertFalse(helper.get("networks"))
                            self.assertEqual(helper["image"], "tailscale/tailscale:v1.102.4")
                            self.assertTrue(helper["read_only"])
                            self.assertTrue(services["caddy"]["depends_on"]["console-cert"]["condition"] == "service_healthy")
                        cert_mounts = [m for m in mounts if m["target"].startswith("/run/console-tls")]
                        self.assertEqual(len(cert_mounts), {"none": 0, "tailscale": 1, "file": 2}[mode])
                        self.assertTrue(all(m["read_only"] for m in cert_mounts))
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
