"""Kernel-label checks for the root-managed Linux header broker (D-183).

No /proc/PID fallback: the accepted socket's security context avoids PID reuse.
The warning stage preserves the legacy UID boundary; it is not process binding.
"""
import json
import socket
import struct
from pathlib import Path


def enforcing_profiles(username, harnesses=("codex", "claude"), mode="enforce"):
    """The profiles that must be loaded in enforce mode for the installed stage. The warning stage installs the
    legacy set (managed-linux.checks asks for the same names); only the strict stage installs the bound ones."""
    name = "mcpgw-" + username
    # A PC without one of the harnesses has no profiles for it; the others must still all enforce.
    strict = mode == "enforce"
    return {name + suffix for suffix in ("", "-bound-credential" if strict else "-credential") + tuple(
        suffix.format(h) for h in harnesses
        for suffix in (("-{}-entry", "-bound-{}", "-bound-{}-tool") if strict else ("-{}",)))}


def kernel_ready(username, harnesses=("codex", "claude"), mode="enforce"):
    try:
        if Path("/sys/module/apparmor/parameters/enabled").read_text().strip() != "Y":
            return "apparmor-unavailable"
        profiles = set(Path("/sys/kernel/security/apparmor/profiles").read_text().splitlines())
        if not {p + " (enforce)" for p in enforcing_profiles(username, harnesses, mode)} <= profiles:
            return "profiles-not-enforcing"
        if Path("/sys/kernel/security/apparmor/features/network/af_unix").read_text().strip() != "yes":
            return "unix-mediation-unavailable"
        if not {"trace", "read"} <= set(Path("/sys/kernel/security/apparmor/features/ptrace/mask").read_text().split()):
            return "ptrace-mediation-unavailable"
    except (OSError, ValueError):
        return "kernel-state-unreadable"
    return ""


def peer_label(connection):
    # SO_PEERSEC is Linux UAPI 31, even on Python builds without the constant.
    raw = connection.getsockopt(socket.SOL_SOCKET, getattr(socket, "SO_PEERSEC", 31), 4096)
    # No str.removesuffix: Ubuntu 20.04 ships Python 3.8.
    label = (raw[:-1] if raw.endswith(b"\0") else raw).decode("utf-8", errors="strict")
    # Stacked, complain and truncated labels must never match by prefix.
    return label[:-len(" (enforce)")] if label.endswith(" (enforce)") else label


def authorize_peer(connection, config):
    """Return permission and a fixed audit reason, never a credential or peer input."""
    mode = config.get("broker_binding", "warn")
    reason, pid, label = "", None, None
    try:
        pid, uid, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid != config["uid"]:
            reason = "uid-mismatch"
            allowed = False
        elif mode not in ("warn", "enforce"):
            reason = "invalid-binding-mode"
            allowed = False
        else:
            reason = kernel_ready(config["username"], config.get("harnesses", ("codex", "claude")), mode)
            label = peer_label(connection)
            if not reason:
                name = "mcpgw-" + config["username"] + "-bound-"
                if label not in {name + key for key in ("codex", "claude", "credential")}:
                    reason = "peer-label-mismatch"
            allowed = not reason or mode == "warn"
    except (OSError, ValueError, UnicodeError, AttributeError, struct.error):
        reason = reason or ("peer-label-unreadable" if pid is not None else "peer-credentials-unreadable")
        allowed = mode == "warn" and pid is not None
    # Only the kernel label and fixed reasons; no credential, response or exception text.
    print(json.dumps({"event": "header-broker-binding", "mode": mode,
                      "result": "warn" if allowed and reason else "allow" if allowed else "deny",
                      "reason": reason or "approved-peer", "pid": pid,
                      "peer_label": label[:256] if label is not None else None}), flush=True)
    return allowed
