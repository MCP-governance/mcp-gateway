"""Builds and runs approved source MCP servers from fixed recipes (DEV-38, D-114).

This is the one process that holds the container engine. It takes jobs an administrator queued for an
approved repository intake and, for each, ties approval → verified commit → recipe → image → container →
endpoint together with evidence, re-checking the approval before it builds, before it starts and before
it reports the runtime active. Contract approval stays where it is: the gateway compares the advertised
tools at registration and before every call.

Every container gets its own internal network shared only with the gateway (and this worker, to check
it answers). Its outbound traffic has no route except an allowlist proxy whose hosts are the reviewed
destinations of the registered tools; before registration the list is empty and nothing gets out.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import tomllib
import urllib.error
import urllib.request
from base64 import b64encode
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

import provenance

DATABASE_URL = os.getenv("DATABASE_URL", "")
WORKER_ID = os.getenv("RUNTIME_WORKER_ID", "runtime-worker-1")
POLL_SECONDS = float(os.getenv("RUNTIME_POLL_SECONDS", "5"))
RECIPES = Path(os.getenv("RUNTIME_RECIPES", "/app/recipes"))
WORK_DIR = Path(os.getenv("RUNTIME_WORK_DIR", "/work"))
REGISTRY_RUNTIME = Path(os.getenv("REGISTRY_RUNTIME_DIR", "/registry-runtime")) / "servers.json"
EGRESS_IMAGE = os.getenv("RUNTIME_EGRESS_IMAGE", "mcpgw/model-proxy:1.0")
GITEA_URL = os.getenv("GITEA_ADMIN_URL", "http://corp-git:3000").rstrip("/")
GITEA_ORG = os.getenv("GITEA_ORG", "mcp")
LEASE_SECONDS = 1800
MAX_ATTEMPTS = 3
BUILD_TIMEOUT = 1800
LIVE = ("QUEUED", "BUILDING", "STARTING", "VERIFYING", "ACTIVE", "STOPPING")
HOST = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")
# The model proxy's tinyproxy, with this runtime's allowlist instead of the model domains.
EGRESS_SCRIPT = ('printf "%s\\n" "$ALLOW" > /tmp/allow && '
                 'sed "s#/etc/tinyproxy/model-domains.txt#/tmp/allow#" /etc/tinyproxy/tinyproxy.conf > /tmp/tinyproxy.conf && '
                 'exec tinyproxy -d -c /tmp/tinyproxy.conf')


class Fenced(Exception):
    """Another worker took the job over, or an administrator stopped it: stop touching it."""


class Refused(Exception):
    """The job must not go on (approval changed, evidence does not match). The reason is shown."""


def log(message: str) -> None:
    print(f"[runtime-worker] {message}", flush=True)


# ── recipes ──────────────────────────────────────────────────────────────────────────────────────

def load_recipes(folder: Path = RECIPES) -> dict[str, dict]:
    """Recipes ship inside this image; a job can only name one of them, never bring its own."""
    found = {}
    for path in sorted(folder.glob("*.toml")):
        recipe = dict(tomllib.loads(path.read_text(encoding="utf-8"))["recipe"])
        dockerfile = path.with_name(recipe["dockerfile"])
        text = dockerfile.read_text(encoding="utf-8")
        base = re.search(r"^FROM\s+(\S+)", text, re.M)
        if not base or "@sha256:" not in base.group(1):
            raise ValueError(f"{path.name}: the base image must be pinned by digest")
        if not isinstance(recipe.get("port"), int) or not str(recipe.get("path", "")).startswith("/"):
            raise ValueError(f"{path.name}: port and path are required")
        if not all(isinstance(a, str) for a in recipe.get("args", [])):
            raise ValueError(f"{path.name}: args must be strings")
        recipe.update(sha256=hashlib.sha256(path.read_bytes() + b"\0" + dockerfile.read_bytes()).hexdigest(),
                      dockerfile_path=str(dockerfile), base_image=base.group(1))
        found[recipe["repository"]] = recipe
    return found


# ── names and docker arguments (pure, checked in tests/runtime_worker_check.py) ────────────────────

def names(runtime: dict) -> dict:
    short, intake = str(runtime["id"])[:8], str(runtime["intake_id"])[:8]
    # The alias follows the approval, not the run: a rebuilt runtime keeps the address the gateway
    # registered, and the gateway's per-call contract check decides whether it still matches.
    return {"container": f"mcpgw-rt-{short}", "egress": f"mcpgw-rt-{short}-egress",
            "network": f"mcpgw-rt-{short}", "alias": f"mcpgw-mcp-{intake}"}


def endpoint(recipe: dict, runtime: dict) -> str:
    return f"http://{names(runtime)['alias']}:{recipe['port']}{recipe['path']}"


def labels(runtime: dict, role: str) -> list[str]:
    return ["--label", f"mcpgw.runtime={runtime['id']}", "--label", f"mcpgw.intake={runtime['intake_id']}",
            "--label", f"mcpgw.generation={runtime['generation']}", "--label", f"mcpgw.role={role}"]


def egress_filter(hosts) -> str:
    """tinyproxy ERE filter: exact reviewed hosts only. No host means a pattern no host matches."""
    clean = sorted({h for h in hosts if isinstance(h, str) and HOST.fullmatch(h)})
    return "\n".join("^" + h.replace(".", "\\.") + "$" for h in clean) or "^$"


def mcp_run_args(recipe: dict, runtime: dict, image_id: str) -> list[str]:
    n = names(runtime)
    proxy = f"http://{n['egress']}:3128"
    return ["docker", "run", "-d", "--name", n["container"], *labels(runtime, "mcp"),
            "--network", n["network"], "--network-alias", n["alias"], "--restart", "unless-stopped",
            "--read-only", "--tmpfs", "/tmp:rw,nosuid,size=128m", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", recipe.get("user", "65534:65534"),
            "--memory", recipe.get("memory", "1g"), "--pids-limit", str(recipe.get("pids", 256)),
            "--cpus", str(recipe.get("cpus", "1.0")),
            "-e", f"HTTPS_PROXY={proxy}", "-e", f"HTTP_PROXY={proxy}", "-e", f"https_proxy={proxy}",
            "-e", f"http_proxy={proxy}", "-e", "NO_PROXY=", "-e", "no_proxy=",
            image_id, *recipe.get("args", [])]


def egress_run_args(runtime: dict, allow: str) -> list[str]:
    n = names(runtime)
    return ["docker", "run", "-d", "--name", n["egress"], *labels(runtime, "egress"),
            "--label", f"mcpgw.allow={hashlib.sha256(allow.encode()).hexdigest()}",
            "--network", n["network"], "--restart", "unless-stopped", "--read-only", "--tmpfs", "/tmp:size=1m",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "-e", f"ALLOW={allow}",
            EGRESS_IMAGE, "sh", "-c", EGRESS_SCRIPT]


# ── docker ───────────────────────────────────────────────────────────────────────────────────────

def docker(*args: str, timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(["docker", *args] if args[0] != "docker" else list(args),
                            capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"docker {args[0] if args[0] != 'docker' else args[1]}: {result.stderr.strip()[-400:]}")
    return result


def inspect(kind: str, name: str) -> dict | None:
    result = docker(kind, "inspect", name, check=False)
    return json.loads(result.stdout)[0] if result.returncode == 0 else None


def compose_context() -> dict:
    """This worker's compose project tells which containers are the gateway and which network is edge."""
    me = inspect("container", os.environ["HOSTNAME"]) or {}
    project = (me.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project")
    if not project:
        raise RuntimeError("the worker must run as a compose service")
    gateways = docker("ps", "-q", "--filter", f"label=com.docker.compose.project={project}",
                      "--filter", "label=com.docker.compose.service=gateway").stdout.split()
    gateways += docker("ps", "-q", "--filter", f"label=com.docker.compose.project={project}",
                       "--filter", "label=com.docker.compose.service=gateway-sse").stdout.split()
    return {"project": project, "edge": f"{project}_edge", "self": me["Id"], "gateways": gateways}


def attach(network: str, container: str) -> None:
    info = inspect("container", container)
    if info and network not in (info.get("NetworkSettings", {}).get("Networks") or {}):
        docker("network", "connect", network, container)


def remove_runtime_resources(runtime: dict, context: dict | None) -> int:
    """Containers and the network go; the image stays as evidence. Returns what is left behind."""
    n = names(runtime)
    # By name, and by label: a helper run from the built image (pip freeze) inherits the image's labels.
    labelled = docker("ps", "-aq", "--filter", f"label=mcpgw.runtime={runtime['id']}", check=False).stdout.split()
    for name in (n["container"], n["egress"], *labelled):
        docker("rm", "-f", name, check=False)
    if inspect("network", n["network"]):
        for container in ([*context["gateways"], context["self"]] if context else []):
            docker("network", "disconnect", "-f", n["network"], container, check=False)
        docker("network", "rm", n["network"], check=False)
    left = docker("ps", "-aq", "--filter", f"label=mcpgw.runtime={runtime['id']}").stdout.split()
    return len(left) + (1 if inspect("network", n["network"]) else 0)


# ── database ─────────────────────────────────────────────────────────────────────────────────────

def event(connection, runtime: dict, kind: str, outcome: str = "recorded", reason: str | None = None,
          scope: dict | None = None) -> None:
    connection.execute(
        """INSERT INTO approval_events(kind,outcome,target_kind,target_id,actor,reason,scope)
           VALUES (%s,%s,'intake',%s,%s,%s,%s)""",
        (kind, outcome, str(runtime["intake_id"]), WORKER_ID, reason,
         Jsonb({"runtime": str(runtime["id"]), "generation": runtime["generation"], **(scope or {})})))


def advance(connection, runtime: dict, expected: str, status: str, **fields) -> dict:
    """Moves a claimed job on, only while this worker still holds the same attempt in the same state."""
    columns = "".join(f", {key}=%s" for key in fields)
    values = [Jsonb(v) if isinstance(v, dict) else v for v in fields.values()]
    row = connection.execute(
        f"""UPDATE mcp_runtimes SET status=%s, updated_at=now(),
                   lease_expires_at=now() + make_interval(secs => %s){columns}
            WHERE id=%s AND lease_owner=%s AND attempts=%s AND status=%s RETURNING *""",
        (status, LEASE_SECONDS, *values, runtime["id"], WORKER_ID, runtime["attempts"], expected)).fetchone()
    connection.commit()
    if not row:
        raise Fenced(str(runtime["id"]))
    return row


def claim(connection) -> dict | None:
    row = connection.execute(
        """UPDATE mcp_runtimes SET status='BUILDING', attempts=attempts+1, lease_owner=%s, updated_at=now(),
                  lease_expires_at=now() + make_interval(secs => %s), error=NULL
           WHERE id = (SELECT id FROM mcp_runtimes WHERE status='QUEUED' ORDER BY created_at
                       LIMIT 1 FOR UPDATE SKIP LOCKED)
           RETURNING *""", (WORKER_ID, LEASE_SECONDS)).fetchone()
    connection.commit()
    return row


def reclaim(connection) -> None:
    """A worker that died mid-job leaves a lease that runs out; the job goes back to the queue (the next
    attempt finds and replaces anything the dead one created) or fails after the attempt limit."""
    connection.execute(
        """UPDATE mcp_runtimes SET status=CASE WHEN attempts >= %s THEN 'FAILED' ELSE 'QUEUED' END,
                  error=CASE WHEN attempts >= %s THEN '작업 시간이 지나 실패로 처리했습니다.' ELSE error END,
                  lease_owner=NULL, lease_expires_at=NULL, updated_at=now()
           WHERE status IN ('BUILDING','STARTING','VERIFYING') AND lease_expires_at < now()""",
        (MAX_ATTEMPTS, MAX_ATTEMPTS))
    connection.commit()


def recover_own(connection, context: dict) -> None:
    """At start nothing of this worker is running, so a job it still holds was cut off mid-way: its
    containers go and it returns to the queue now rather than when the lease runs out."""
    rows = connection.execute(
        """SELECT * FROM mcp_runtimes WHERE lease_owner=%s AND status IN ('BUILDING','STARTING','VERIFYING')""",
        (WORKER_ID,)).fetchall()
    for runtime in rows:
        left = remove_runtime_resources(runtime, context)
        connection.execute(
            """UPDATE mcp_runtimes SET status=CASE WHEN attempts >= %s THEN 'FAILED' ELSE 'QUEUED' END,
                      error='작업 도중 실행기가 다시 시작되었습니다.', lease_owner=NULL, lease_expires_at=NULL, updated_at=now()
               WHERE id=%s AND lease_owner=%s AND attempts=%s""",
            (MAX_ATTEMPTS, runtime["id"], WORKER_ID, runtime["attempts"]))
        connection.commit()
        log(f"recovered {runtime['id']} left={left}")


def heartbeat(connection) -> None:
    connection.execute(
        """INSERT INTO worker_heartbeats(worker, role, seen_at, detail) VALUES (%s, 'runtime', now(), %s)
           ON CONFLICT (worker) DO UPDATE SET seen_at=now(), detail=EXCLUDED.detail""",
        (WORKER_ID, Jsonb({"poll_seconds": POLL_SECONDS})))
    connection.commit()


def approval_problem(connection, runtime: dict, recipes: dict, *, recipe_fixed: bool = True) -> str | None:
    """Why this approval may no longer run, re-read from the database every time it matters."""
    row = connection.execute(
        """SELECT r.status, r.intake_kind, r.commit_sha, r.repository_url, s.lifecycle, s.status AS server_status
           FROM mcp_intake_requests r LEFT JOIN mcp_servers s ON s.id = r.registered_server_id
           WHERE r.id=%s""", (runtime["intake_id"],)).fetchone()
    if not row or row["status"] != "APPROVED" or row["intake_kind"] != "repository":
        return "도입 승인이 유효하지 않습니다."
    if row["commit_sha"] != runtime["source_commit"]:
        return "승인한 커밋이 바뀌었습니다."
    recipe = recipes.get(row["repository_url"])
    if recipe_fixed and (not recipe or recipe["sha256"] != runtime["recipe_sha256"] or recipe["id"] != runtime["recipe_id"]):
        # A running image was built from the recipe it recorded; only a build in progress must match.
        return "실행 레시피가 예약 이후 바뀌었습니다."
    if row["lifecycle"] in ("TERMINATING", "RETIRED"):
        return "종료 절차가 시작된 이용 관계입니다."
    if row["server_status"] == "DISABLED":
        return "게이트웨이 등록이 해제된 신청입니다."
    return None


def destinations(intake_id) -> list[str]:
    """Reviewed external hosts of the registered tools of this approval (empty before registration)."""
    try:
        servers = json.loads(REGISTRY_RUNTIME.read_text(encoding="utf-8")).get("servers", {})
    except (OSError, ValueError):
        return []
    hosts = set()
    for spec in servers.values():
        if spec.get("intake_id") == str(intake_id):
            for review in (spec.get("tool_reviews") or {}).values():
                hosts.update(review.get("destinations") or [])
    return sorted(hosts)


# ── one job ──────────────────────────────────────────────────────────────────────────────────────

def fetch_source(connection, runtime: dict, folder: Path) -> dict:
    row = connection.execute("SELECT internal_repo_url, provenance FROM mcp_intake_requests WHERE id=%s",
                             (runtime["intake_id"],)).fetchone()
    name = (row["internal_repo_url"] or "").rstrip("/").rsplit("/", 1)[-1]
    if not name:
        raise Refused("내부 저장소 사본이 없습니다.")
    token = b64encode(f"{os.getenv('GITEA_ADMIN_USER', 'corpadmin')}:{os.getenv('GITEA_ADMIN_PASSWORD', '')}".encode()).decode()
    request = urllib.request.Request(f"{GITEA_URL}/api/v1/repos/{GITEA_ORG}/{name}/archive/{runtime['source_commit']}.tar.gz",
                                     headers={"Authorization": "Basic " + token})
    archive = folder / "source.tar.gz"
    with urllib.request.urlopen(request, timeout=300) as response, archive.open("wb") as out:
        shutil.copyfileobj(response, out)
    with archive.open("rb") as handle:
        digest = provenance.archive_digest(handle)
    recorded = ((row["provenance"] or {}).get("artifact") or {}).get("sha256")
    if digest["sha256"] != recorded:
        raise Refused(f"내부 사본이 검증한 소스와 다릅니다 ({str(recorded)[:12]} / {digest['sha256'][:12]}).")
    context = folder / "context"
    with tarfile.open(archive) as tar:
        top = tar.getmembers()[0].name.split("/")[0]
        for member in tar.getmembers():
            parts = member.name.split("/")[1:]
            if not parts or parts == [""]:
                continue
            member.name = "/".join(parts)
            tar.extract(member, context, filter="data")
    return {"source_archive_sha256": digest["sha256"], "files": digest["files"], "top": top}


def build(recipe: dict, runtime: dict, context: Path, folder: Path) -> dict:
    iid = folder / "image-id"
    started = time.time()
    result = docker("build", "-f", recipe["dockerfile_path"], "--iidfile", str(iid), *labels(runtime, "mcp"),
                    "--label", f"mcpgw.commit={runtime['source_commit']}", "--label", f"mcpgw.recipe={recipe['sha256']}",
                    str(context), timeout=BUILD_TIMEOUT, check=False)
    log_text = result.stdout + result.stderr
    if result.returncode:
        raise Refused("빌드 실패: " + log_text.strip()[-300:])
    image_id = iid.read_text().strip()
    image = inspect("image", image_id) or {}
    if (image.get("Config", {}).get("Labels") or {}).get("mcpgw.commit") != runtime["source_commit"]:
        raise Refused("빌드한 이미지의 커밋 표식이 승인한 커밋과 다릅니다.")
    frozen = docker("run", "--rm", "--network", "none", "--entrypoint", "python", image_id, "-m", "pip", "freeze",
                    timeout=120, check=False).stdout
    return {"image_id": image_id, "build_seconds": round(time.time() - started, 1),
            "build_log_sha256": hashlib.sha256(log_text.encode()).hexdigest(),
            "packages_sha256": hashlib.sha256(frozen.encode()).hexdigest(),
            "packages": frozen.split()[:200], "base_image": recipe["base_image"]}


def start(recipe: dict, runtime: dict, image_id: str, context: dict) -> None:
    n = names(runtime)
    if not inspect("network", n["network"]):
        docker("network", "create", "--internal", *labels(runtime, "network"), n["network"])
    for container in [*context["gateways"], context["self"]]:
        attach(n["network"], container)
    current = inspect("container", n["container"])
    if current and (current["Image"] != image_id or not current["State"]["Running"]):
        docker("rm", "-f", n["container"])
        current = None
    sync_egress(runtime, context)
    if not current:
        docker(*mcp_run_args(recipe, runtime, image_id))


def sync_egress(runtime: dict, context: dict) -> None:
    n = names(runtime)
    allow = egress_filter(destinations(runtime["intake_id"]))
    want = hashlib.sha256(allow.encode()).hexdigest()
    current = inspect("container", n["egress"])
    if current and ((current["Config"].get("Labels") or {}).get("mcpgw.allow") != want or not current["State"]["Running"]):
        docker("rm", "-f", n["egress"])
        current = None
    if not current:
        docker(*egress_run_args(runtime, allow))
        docker("network", "connect", context["edge"], n["egress"])


def answers(url: str, deadline: float) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                                  "clientInfo": {"name": "mcpgw-runtime-worker", "version": "1"}}}).encode()
    last = ""
    while time.time() < deadline:
        try:
            request = urllib.request.Request(url, data=body, method="POST", headers={
                "content-type": "application/json", "accept": "application/json, text/event-stream"})
            with urllib.request.urlopen(request, timeout=10) as response:
                text = response.read(65536).decode("utf-8", "replace")
            payload = json.loads(text[text.index("{"):] if not text.lstrip().startswith("{") else text)
            result = payload.get("result") or {}
            if result.get("protocolVersion"):
                return {"protocol_version": result["protocolVersion"],
                        "server": (result.get("serverInfo") or {}).get("name", "")}
            last = "응답에 프로토콜 판이 없음"
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last = type(exc).__name__
        time.sleep(2)
    raise Refused(f"MCP 서버가 응답하지 않습니다 ({last}).")


def run_job(connection, runtime: dict, recipes: dict, context: dict) -> None:
    recipe = next((r for r in recipes.values() if r["id"] == runtime["recipe_id"]), None)
    folder = WORK_DIR / str(runtime["id"])
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    try:
        if problem := approval_problem(connection, runtime, recipes):
            raise Refused(problem)
        source = fetch_source(connection, runtime, folder)
        built = build(recipe, runtime, folder / "context", folder)
        evidence = {**source, **built}
        runtime = advance(connection, runtime, "BUILDING", "STARTING", source_archive_sha256=source["source_archive_sha256"],
                          image_id=built["image_id"], evidence=evidence)
        event(connection, runtime, "runtime-built", scope={k: evidence[k] for k in (
            "source_archive_sha256", "image_id", "packages_sha256", "base_image", "build_seconds")})
        connection.commit()
        if problem := approval_problem(connection, runtime, recipes):
            raise Refused(problem)
        start(recipe, runtime, built["image_id"], context)
        runtime = advance(connection, runtime, "STARTING", "VERIFYING")
        found = answers(endpoint(recipe, runtime), time.time() + 90)
        if problem := approval_problem(connection, runtime, recipes):
            raise Refused(problem)
        runtime = advance(connection, runtime, "VERIFYING", "ACTIVE", endpoint=endpoint(recipe, runtime),
                          evidence={**evidence, "answered": found, "container": names(runtime)["container"]})
        event(connection, runtime, "runtime-active", scope={"endpoint": runtime["endpoint"], "image_id": runtime["image_id"], **found})
        connection.commit()
        log(f"active {runtime['id']} {runtime['endpoint']}")
    except (Refused, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        # Refused is final. A docker or network error gets another attempt, after this one's containers
        # and network are gone, so the retry never finds a half-made runtime to duplicate.
        connection.rollback()
        retry = not isinstance(exc, Refused) and runtime["attempts"] < MAX_ATTEMPTS
        reason = (str(exc) if isinstance(exc, Refused) else f"{type(exc).__name__}: {exc}")[:500]
        left = remove_runtime_resources(runtime, context)
        try:
            advance(connection, runtime, runtime["status"], "QUEUED" if retry else "FAILED", error=reason,
                    lease_owner=None)
            if not retry:
                event(connection, runtime, "runtime-failed", "held", reason=reason, scope={"left": left})
                connection.commit()
        except Fenced:
            pass
        log(f"{'retry' if retry else 'failed'} {runtime['id']}: {reason}")
    finally:
        shutil.rmtree(folder, ignore_errors=True)


# ── reconcile live runtimes ──────────────────────────────────────────────────────────────────────

def reconcile(connection, recipes: dict, context: dict) -> None:
    rows = connection.execute("SELECT * FROM mcp_runtimes WHERE status IN ('ACTIVE','STOPPING')").fetchall()
    for runtime in rows:
        if runtime["status"] == "ACTIVE":
            reason = approval_problem(connection, runtime, recipes, recipe_fixed=False)
            n = names(runtime)
            current = inspect("container", n["container"])
            if not reason and (not current or current["Image"] != runtime["image_id"]):
                reason = "실행 중인 컨테이너가 승인한 이미지와 다르거나 없습니다."
            if not reason:
                for container in context["gateways"]:
                    attach(n["network"], container)
                sync_egress(runtime, context)
                continue
            connection.execute("UPDATE mcp_runtimes SET status='STOPPING', error=%s, updated_at=now() WHERE id=%s AND status='ACTIVE'",
                               (reason, runtime["id"]))
            connection.commit()
            runtime = {**runtime, "status": "STOPPING", "error": reason}
        left = remove_runtime_resources(runtime, context)
        done = connection.execute(
            """UPDATE mcp_runtimes SET status='STOPPED', updated_at=now(), lease_owner=NULL, lease_expires_at=NULL,
                      evidence = evidence || %s WHERE id=%s AND status='STOPPING' RETURNING id""",
            (Jsonb({"stopped_left_behind": left}), runtime["id"])).fetchone()
        if done:
            event(connection, runtime, "runtime-stopped", reason=runtime.get("error"), scope={"left": left})
        connection.commit()
        log(f"stopped {runtime['id']} left={left}")


def main() -> int:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    recipes = load_recipes()
    log(f"recipes {sorted(r['id'] for r in recipes.values())} · worker={WORKER_ID}")
    while True:
        try:
            with psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=False) as connection:
                recover_own(connection, compose_context())
                while True:
                    heartbeat(connection)
                    reclaim(connection)
                    context = compose_context()
                    reconcile(connection, recipes, context)
                    job = claim(connection)
                    if job:
                        try:
                            run_job(connection, job, recipes, context)
                        except Fenced:
                            connection.rollback()
                            log(f"fenced {job['id']}")
                    else:
                        time.sleep(POLL_SECONDS)
        except (psycopg.Error, RuntimeError, OSError) as exc:
            log(f"loop error: {type(exc).__name__}: {str(exc)[:300]}")
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
