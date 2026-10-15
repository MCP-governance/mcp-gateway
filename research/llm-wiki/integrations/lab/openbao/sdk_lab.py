"""Official hvac SDK glue for a dedicated OpenBao lab; no secret values in output."""
import argparse
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import time
from urllib.parse import urlsplit
import uuid

import hvac
import requests

HERE = Path(__file__).resolve().parent
MOUNT = "lab-kv"
AUTH = "lab-approle"
ROLE = "litellm-lab"


def private_read(path):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("Credential files must be owned regular files with mode0600")
    return json.loads(path.read_text(encoding="utf-8"))


def private_secret_value(path):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("Seed secret must be an owned regular mode0600 file")
    return path.read_text(encoding="utf-8").strip()


def private_write(path, data, replace=False):
    path = Path(path)
    if path.parent.stat().st_uid != os.geteuid() or stat.S_IMODE(path.parent.stat().st_mode) != 0o700:
        raise ValueError("The private directory must be owned and mode0700")
    temporary = path.with_name(path.name + ".new-" + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(data, stream)
        stream.flush()
        os.fsync(stream.fileno())
    if replace:
        private_read(path)
        os.replace(temporary, path)
    else:
        # An atomic link fails rather than overwriting another run's credentials.
        os.link(temporary, path)
        temporary.unlink()


def client(args, token=None, ca=None):
    parsed = urlsplit(args.address)
    if parsed.scheme != "https" or parsed.hostname not in {"127.0.0.1", "localhost", "openbao"} or parsed.username or parsed.password:
        raise ValueError("Only this lab's fixed TLS endpoint is permitted")
    session = requests.Session()
    session.trust_env = False
    return hvac.Client(url=args.address, token=token, verify=str(ca or args.ca),
                       session=session, timeout=5, allow_redirects=False)


def app_login(operator, args, role=ROLE):
    role_id = operator.auth.approle.read_role_id(role_name=role, mount_point=AUTH)["data"]["role_id"]
    secret_id = operator.auth.approle.generate_secret_id(role_name=role, mount_point=AUTH)["data"]["secret_id"]
    app = client(args)
    auth = app.auth.approle.login(role_id=role_id, secret_id=secret_id, mount_point=AUTH)["auth"]
    return app, auth, role_id, secret_id


def forbidden(operation):
    try:
        operation()
    except hvac.exceptions.Forbidden:
        return True
    raise AssertionError("Expected authorization denial403")


def bootstrap(args):
    private = Path(args.private_dir)
    init_file = private / "init-operator.json"
    root = client(args)
    if not root.sys.is_initialized():
        if init_file.exists():
            raise RuntimeError("Existing initialization evidence must not be overwritten")
        initialized = root.sys.initialize(secret_shares=1, secret_threshold=1)
        private_write(init_file, initialized)
    record = private_read(init_file)
    if root.sys.is_sealed():
        root.sys.submit_unseal_key(record["keys_base64"][0])
    if not record.get("root_token"):
        return {"bootstrapped": True, "already_bootstrapped": True, "root_token_retained": False}
    root.token = record["root_token"]
    if not root.is_authenticated():
        raise RuntimeError("Initialization root is unavailable; preserve files and recover manually")
    mounts = root.sys.list_mounted_secrets_engines()["data"]
    if MOUNT + "/" not in mounts:
        root.sys.enable_secrets_engine(backend_type="kv", path=MOUNT, options={"version": "2"})
    root.secrets.kv.v2.configure(max_versions=10, cas_required=True, mount_point=MOUNT)
    root.sys.create_or_update_policy(name="bao-lab-app-read", policy=(HERE / "app-read.hcl").read_text())
    root.sys.create_or_update_policy(name="bao-lab-operator", policy=(HERE / "operator.hcl").read_text())
    if AUTH + "/" not in root.sys.list_auth_methods()["data"]:
        root.sys.enable_auth_method(method_type="approle", path=AUTH)
    root.auth.approle.create_or_update_approle(
        role_name=ROLE, mount_point=AUTH, token_policies=["bao-lab-app-read"],
        token_no_default_policy=True, token_type="service", token_ttl="5m", token_max_ttl="10m",
        token_explicit_max_ttl="10m", secret_id_ttl="10m", secret_id_num_uses=1,
        secret_id_bound_cidrs=args.bound_cidr, token_bound_cidrs=args.bound_cidr, bind_secret_id=True,
    )
    if "lab-file/" not in root.sys.list_enabled_audit_devices()["data"]:
        root.sys.enable_audit_device(device_type="file", path="lab-file",
                                     options={"file_path": "/openbao/logs/audit.jsonl", "log_raw": "false"})
    for key in ("litellm", "smoke", "denied"):
        value = secrets.token_urlsafe(32)
        if key == "litellm" and args.seed_secret_file:
            value = private_secret_value(args.seed_secret_file)
            if not value:
                raise ValueError("Empty seed secret is forbidden")
        try:
            root.secrets.kv.v2.create_or_update_secret(path="integration/" + key,
                                                       secret={"api_key": value}, cas=0, mount_point=MOUNT)
        except hvac.exceptions.InvalidRequest:
            # CAS0 protects existing data; verify it exists instead of overwriting.
            root.secrets.kv.v2.read_secret_version(path="integration/" + key, mount_point=MOUNT,
                                                 raise_on_deleted_version=True)
    operator_file = private / "operator.json"
    if operator_file.exists():
        raise RuntimeError("An operator credential already exists; preserve and recover manually")
    operator_auth = root.auth.token.create(policies=["bao-lab-operator"], ttl="2h",
                                          explicit_max_ttl="4h", no_parent=True,
                                          no_default_policy=True)["auth"]
    operator = client(args, operator_auth["client_token"])
    if not operator.is_authenticated():
        raise RuntimeError("Limited operator authentication failed")
    try:
        private_write(operator_file, {"token": operator_auth["client_token"], "accessor": operator_auth["accessor"],
                                      "role": ROLE, "bound_cidrs": args.bound_cidr})
    except Exception:
        root.auth.token.revoke_accessor(operator_auth["accessor"])
        raise
    root.auth.token.revoke_self()
    if not operator.is_authenticated():
        raise RuntimeError("Limited orphan operator did not survive bootstrap-root revocation")
    record["root_token"] = None
    record["bootstrap_root_revoked"] = True
    private_write(init_file, record, replace=True)
    return {"bootstrapped": True, "root_token_retained": False, "root_token_revoked": True,
            "operator_policy": "bao-lab-operator", "kv_version": 2, "secret_id_num_uses": 1,
            "app_token_max_ttl_seconds": 600, "seed_is_synthetic": not bool(args.seed_secret_file)}


def check_authenticated_app(operator, app, args, role_id, secret_id):
    secret = app.secrets.kv.v2.read_secret_version(path="integration/smoke", mount_point=MOUNT,
                                                raise_on_deleted_version=True)
    original = secret["data"]["data"]
    version = secret["data"]["metadata"]["version"]
    result = {"TLS_verified": True, "AppRole_authenticated": True, "KVv2_read": bool(original.get("api_key")),
              "SDK": "hvac2.4.0", "OpenBao_target": "2.7.1", "secret_values_printed": False}
    result["other_path_denied403"] = forbidden(lambda: app.secrets.kv.v2.read_secret_version(
        path="integration/denied", mount_point=MOUNT, raise_on_deleted_version=True))
    result["workload_write_denied403"] = forbidden(lambda: app.secrets.kv.v2.create_or_update_secret(
        path="integration/smoke", secret={"api_key": "must-not-be-stored"}, cas=version, mount_point=MOUNT))
    try:
        client(args).auth.approle.login(role_id=role_id, secret_id=secret_id, mount_point=AUTH)
        raise AssertionError("A one-use SecretID unexpectedly authenticated twice")
    except (hvac.exceptions.Forbidden, hvac.exceptions.InvalidRequest):
        result["one_use_secret_id_reuse_denied"] = True
    try:
        client(args, ca=Path(args.ca).with_name("wrong-ca.pem")).sys.is_initialized()
        raise AssertionError("An unrelated CA unexpectedly authenticated the TLS endpoint")
    except requests.exceptions.SSLError:
        result["wrong_CA_rejected"] = True
    mutated = False
    try:
        rotated = {"api_key": secrets.token_urlsafe(32)}
        response = operator.secrets.kv.v2.create_or_update_secret(
            path="integration/smoke", secret=rotated, cas=version, mount_point=MOUNT)
        mutated = True
        next_version = response["data"]["version"]
        fresh = app.secrets.kv.v2.read_secret_version(path="integration/smoke", mount_point=MOUNT,
                                                   raise_on_deleted_version=True)
        result["rotation_latest_version"] = fresh["data"]["data"] == rotated and next_version == version + 1
        try:
            operator.secrets.kv.v2.create_or_update_secret(
                path="integration/smoke", secret={"api_key": "stale-must-not-store"}, cas=version, mount_point=MOUNT)
            raise AssertionError("Stale CAS unexpectedly overwrote a secret")
        except hvac.exceptions.InvalidRequest:
            result["stale_CAS_rejected"] = True
    finally:
        if mutated:
            latest = operator.secrets.kv.v2.read_secret_version(path="integration/smoke", mount_point=MOUNT,
                                                              raise_on_deleted_version=True)
            # Restore only the isolated smoke secret through CAS, preserving audit/history.
            operator.secrets.kv.v2.create_or_update_secret(
                path="integration/smoke", secret=original, cas=latest["data"]["metadata"]["version"], mount_point=MOUNT)
            result["isolated_smoke_value_restored"] = True
    return result


def sdk_check(args):
    record = private_read(Path(args.private_dir) / "operator.json")
    operator = client(args, record["token"])
    if not operator.is_authenticated():
        raise RuntimeError("Limited operator expired or unavailable")
    app, auth, role_id, secret_id = app_login(operator, args)
    try:
        result = check_authenticated_app(operator, app, args, role_id, secret_id)
    finally:
        # Early TLS/authorization failures must also retire the issued workload token.
        operator.auth.token.revoke_accessor(auth["accessor"])
    result["revoked_token_read_denied403"] = forbidden(lambda: app.secrets.kv.v2.read_secret_version(
        path="integration/smoke", mount_point=MOUNT, raise_on_deleted_version=True))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["bootstrap", "check"])
    parser.add_argument("--address", default="https://127.0.0.1:18200")
    parser.add_argument("--ca", required=True)
    parser.add_argument("--private-dir", required=True)
    parser.add_argument("--bound-cidr", action="append", default=[])
    parser.add_argument("--seed-secret-file")
    args = parser.parse_args()
    if sys.platform != "linux":
        raise RuntimeError("Execute only on the designated solution appliance lab")
    if args.mode == "bootstrap" and not args.bound_cidr:
        raise ValueError("Bind AppRole to the verified dedicated lab subnet")
    result = bootstrap(args) if args.mode == "bootstrap" else sdk_check(args)
    required = [key for key, value in result.items() if isinstance(value, bool) and key != "secret_values_printed"]
    if args.mode == "check" and not all(result[key] is True for key in required):
        raise AssertionError("A required denial or restoration failed")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__,
                          "detail": "preserve lab state; inspect redacted diagnostics without printing credentials"}), file=sys.stderr)
        sys.exit(1)
