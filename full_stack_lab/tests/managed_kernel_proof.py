"""Run as root on an enrolled Linux board, with Console identities on stdin.

Uses the actual installed collector, kernel rules and protected configuration.
No supplier, enforcement check, heartbeat timestamp or JWT is fabricated.
Temporarily stops only this device service; restores it in finally.
"""
import argparse
import base64
import io
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    assert os.geteuid() == 0, "root kernel access is required"
    import importlib.util
    spec = importlib.util.spec_from_file_location("managed", "/usr/local/lib/mcpgw-managed/managed-linux.py")
    managed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(managed)
    config = json.loads(args.config.read_text())
    managed.verify_transport(config)
    credentials = json.load(sys.stdin)
    base, service = config["gateway_url"], "mcpgw-managed-" + config["username"] + ".service"
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *unused):
            raise ValueError("Do not forward identities to a different endpoint")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    def call(path, body=None, token=None, raw=False, method=None):
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), headers=headers, method=method)
        try:
            with opener.open(req, timeout=20) as response:
                data = response.read()
                return response.status, data if raw else json.loads(data)
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())
    def login(identity):
        status, result = call("/auth/mock-login", identity)
        assert status == 200
        return result["access_token"]
    employee, reviewer = login(credentials["employee"]), login(credentials["reviewer"])
    def heartbeat(device=config):
        policy = managed.request(device, "/api/endpoint/managed-policy")
        hashes, health = managed.checks(device, policy)
        report = managed.request(device, "/api/endpoint/heartbeat", {"policy_hash": policy["policy_hash"],
                                   "configuration_hashes": hashes, "checks": health})
        return policy, hashes, health, report
    def activate(device, policy):
        status, result = call("/api/endpoint/devices/" + device["endpoint_id"] + "/activate",
                             {"policy_hash": policy["policy_hash"], "note": "Root inspected actual PJ1 kernel AppArmor, UID nft table and protected file hashes; independent organization review for this boundary test."}, reviewer)
        assert status == 200, result
    def mint(device=config):
        return managed.request(device, "/oauth/device-token", {})["access_token"]
    def admission(token, expected, reason=None):
        status, result = call("/mcp/github/", {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                              "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                                         "clientInfo": {"name": "managed-kernel-boundary-proof", "version": "1"}}}, token)
        assert status == expected, (status, result)
        if reason:
            assert result.get("policy_id") == "ENDPOINT-MANAGED-001" and reason in result["detail"], result
        print(json.dumps({"check": reason or "active", "http_status": status,
                          "policy_id": result.get("policy_id")}), flush=True)
    original = {p: p.read_bytes() for p in managed.FILES.values()}
    disposable = None
    try:
        policy, hashes, health, report = heartbeat()
        assert health and all(health.values()) and hashes == policy["configuration_hashes"] and report["state"] == "active"
        admission(employee, 403, "관리형")
        token = mint()
        admission(token, 200)
        subprocess.run(["systemctl", "stop", service], check=True)
        deadline = time.monotonic() + policy["max_heartbeat_age"] + 5
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            print(json.dumps({"check": "waiting-real-heartbeat-expiry", "remaining_seconds": round(remaining)}), flush=True)
            time.sleep(min(30, remaining))
        claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
        assert claims["exp"] > time.time(), "The JWT must still be unexpired for this check"
        admission(token, 403, "heartbeat")
        try:
            mint()
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
        else:
            raise AssertionError("Stale device minted a token")
        policy, _, _, report = heartbeat()
        assert report["state"] == "active"
        admission(mint(), 200)
        target = managed.FILES["managed_config.toml"]
        target.write_bytes(original[target] + b"\n# deliberate root-authorized drift test\n")
        policy, _, _, report = heartbeat()
        assert report == {"state": "quarantined", "compliant": False, "policy_hash": policy["policy_hash"]}
        admission(token, 403, "격리")
        target.write_bytes(original[target])
        policy, hashes, health, report = heartbeat()
        assert all(health.values()) and hashes == policy["configuration_hashes"] and report["state"] == "quarantined"
        admission(token, 403, "격리")
        activate(config, policy)
        admission(mint(), 200)
        # A second credential uses the SAME actual enrolled UID/kernel. It has no
        # fake compliant state and is always revoked after this revocation check.
        status, bundle = call("/api/pc-kit", {}, employee, raw=True)
        assert status == 200
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            grant = json.loads(archive.read("enrollment.json"))
        key = secrets.token_urlsafe(32)
        enrolled = managed.request(grant, "/oauth/device-enroll", {"enrollment_token": grant["enrollment_token"],
                         "device_key": key, "hostname": socket.gethostname(),
                         "local_username": config["username"], "local_uid": config["uid"]}, credential=False)
        disposable = {**config, "device_key": key, "endpoint_id": enrolled["endpoint_id"]}
        policy, hashes, health, report = heartbeat(disposable)
        assert all(health.values()) and hashes == policy["configuration_hashes"] and report["state"] == "pending"
        activate(disposable, policy)
        temporary_token = mint(disposable)
        admission(temporary_token, 200)
        status, result = call("/api/endpoint/devices/" + disposable["endpoint_id"], {}, reviewer, method="DELETE")
        assert status == 200, result
        admission(temporary_token, 403, "폐기")
        try:
            mint(disposable)
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("Revoked device minted a token")
        print("PASS actual kernel: stale JWT, configuration quarantine, independent recovery, revoked unexpired JWT/key", flush=True)
    finally:
        for target, content in original.items():
            target.write_bytes(content)
        if disposable:
            call("/api/endpoint/devices/" + disposable["endpoint_id"], {}, reviewer, method="DELETE")
        try:
            policy, hashes, health, report = heartbeat()
            if report["state"] == "quarantined" and all(health.values()) and hashes == policy["configuration_hashes"]:
                activate(config, policy)
        finally:
            subprocess.run(["systemctl", "start", service], check=True)


if __name__ == "__main__":
    main()
