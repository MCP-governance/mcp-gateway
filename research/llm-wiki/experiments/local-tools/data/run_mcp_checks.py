from __future__ import annotations
import json, os, queue, shutil, stat, subprocess, threading, time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[5]
TASK = ROOT / ".task-local-20261014" / "data"
APP = TASK / "app"
LOG = TASK / "log"
FIX = APP / "fixtures"
EVIDENCE = LOG / "protocol-evidence.json"
NODE = shutil.which("node")
GIT = shutil.which("git")
if not NODE or not GIT:
    raise SystemExit("Node.js and Git must be available")

class MCP:
    def __init__(self, name: str, command: list[str], env: dict[str, str], cwd: Path, log_path: Path):
        self.name = name
        self.command = command
        self.responses: queue.Queue[str] = queue.Queue()
        self.err = open(log_path, "w", encoding="utf-8")
        self.process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=self.err, text=True, encoding="utf-8", bufsize=1)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.next_id = 1

    def _read(self):
        for line in self.process.stdout:
            self.responses.put(line)

    def request(self, method: str, params: dict | None = None, timeout: int = 30):
        req_id = self.next_id
        self.next_id += 1
        payload = {"jsonrpc":"2.0", "id":req_id, "method":method}
        if params is not None:
            payload["params"] = params
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{self.name} response timeout for {method}; process={self.process.poll()}")
            line = self.responses.get(timeout=remaining)
            response = json.loads(line)
            if response.get("id") == req_id:
                return response

    def notify(self, method: str, params: dict | None = None):
        payload = {"jsonrpc":"2.0", "method":method}
        if params is not None:
            payload["params"] = params
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def close(self):
        try:
            self.process.stdin.close()
            self.process.wait(timeout=4)
        except Exception:
            self.process.kill()
            self.process.wait(timeout=4)
        self.err.close()


def mk_env():
    # Preserve Windows runtime variables, but remove ambient credentials before starting a server.
    blocked = ("TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "API_KEY", "APIKEY", "PRIVATE_KEY",
               "GITHUB", "GH_TOKEN", "GIT_ASKPASS", "SSH_AUTH", "AWS_", "AZURE_", "GOOGLE_",
               "OPENAI_", "ANTHROPIC_", "HF_TOKEN")
    env = {k:v for k,v in os.environ.items() if not any(part in k.upper() for part in blocked)}
    env["HOME"] = str(TASK / "venv" / "home")
    env["USERPROFILE"] = str(TASK / "venv" / "home")
    env["APPDATA"] = str(TASK / "venv" / "appdata")
    env["LOCALAPPDATA"] = str(TASK / "venv" / "localappdata")
    env["GIT_CONFIG_GLOBAL"] = str(TASK / "venv" / "empty.gitconfig")
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["MCP_TRANSPORT_TYPE"] = "stdio"
    env["MCP_LOG_LEVEL"] = "error"
    for d in (TASK / "venv" / "home", TASK / "venv" / "appdata", TASK / "venv" / "localappdata"):
        d.mkdir(parents=True, exist_ok=True)
    (TASK / "venv" / "empty.gitconfig").touch(exist_ok=True)
    return env


def assert_fixture_path(path: Path, root: Path = FIX):
    """Reject paths outside this task's fixture tree, including symlink escapes."""
    root = root.resolve(strict=True)
    candidate = path.absolute()
    current = candidate
    while current != root and root in current.parents:
        if current.is_symlink():
            raise RuntimeError(f"Refusing fixture symlink: {current}")
        current = current.parent
    resolved = candidate.resolve(strict=False)
    try:
        common = Path(os.path.commonpath([str(root), str(resolved)]))
    except ValueError as exc:
        raise RuntimeError(f"Refusing path outside fixture root: {path}") from exc
    if common != root or resolved == root:
        raise RuntimeError(f"Refusing path outside fixture root: {path}")
    return resolved


def assert_synthetic_git_repo(path: Path):
    assert_fixture_path(path)
    if not (path / ".git").exists() or (path / ".git").is_symlink():
        raise RuntimeError(f"Refusing destructive action on unrecognized Git repo: {path}")
    name = subprocess.check_output([GIT, "-C", str(path), "config", "user.name"], text=True).strip()
    email = subprocess.check_output([GIT, "-C", str(path), "config", "user.email"], text=True).strip()
    if (name, email) != ("Synthetic MCP Test", "synthetic-mcp@example.invalid"):
        raise RuntimeError(f"Refusing destructive action on non-synthetic Git repo: {path}")


def assert_probe_clone(path: Path, source: Path, expected_head: str):
    assert_fixture_path(path)
    if not (path / ".git").is_dir() or {p.name for p in path.iterdir()} != {".git", "README.md"}:
        raise RuntimeError(f"Refusing cleanup of unexpected clone contents: {path}")
    for item in path.rglob("*"):
        if item.is_symlink() or item.stat().st_file_attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise RuntimeError(f"Refusing recursive cleanup containing a link/reparse point: {item}")
    origin = subprocess.check_output([GIT, "-C", str(path), "config", "--get", "remote.origin.url"], text=True).strip()
    head = subprocess.check_output([GIT, "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    readme = (path / "README.md").read_text(encoding="utf-8")
    if Path(origin).resolve() != source.resolve() or head != expected_head or readme != "Synthetic repository for local MCP protocol testing.\n":
        raise RuntimeError(f"Refusing cleanup of clone not matching the synthetic source: {path}")


def remove_probe_clone(path: Path, source: Path, expected_head: str):
    assert_probe_clone(path, source, expected_head)
    def clear_readonly(func, name, exc):
        if isinstance(exc, PermissionError):
            os.chmod(name, stat.S_IWRITE)
            func(name)
            return
        raise exc
    shutil.rmtree(path, onexc=clear_readonly)


def init_client(client: MCP):
    init = client.request("initialize", {"protocolVersion":"2025-11-25", "capabilities":{},
        "clientInfo":{"name":"local-tools-evidence-probe","version":"1.0"}})
    client.notify("notifications/initialized")
    listing = client.request("tools/list", {})
    return init, listing


def call(client: MCP, name: str, arguments: dict):
    return client.request("tools/call", {"name":name,"arguments":arguments})


def git_fixture():
    scope = FIX / "git"
    repo = scope / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    assert_fixture_path(repo)
    if not (repo / ".git").exists():
        subprocess.run([GIT,"init","-b","main",str(repo)],check=True,capture_output=True,text=True)
        subprocess.run([GIT,"-C",str(repo),"config","user.name","Synthetic MCP Test"],check=True)
        subprocess.run([GIT,"-C",str(repo),"config","user.email","synthetic-mcp@example.invalid"],check=True)
        (repo / "README.md").write_text("Synthetic repository for local MCP protocol testing.\n",encoding="utf-8")
        subprocess.run([GIT,"-C",str(repo),"add","README.md"],check=True)
        subprocess.run([GIT,"-C",str(repo),"commit","-m","test: seed synthetic repository"],check=True,capture_output=True,text=True)
    else:
        assert_synthetic_git_repo(repo)
        if (repo / "README.md").read_text(encoding="utf-8") != "Synthetic repository for local MCP protocol testing.\n":
            raise RuntimeError(f"Refusing to use unexpected existing Git fixture: {repo}")
    assert_synthetic_git_repo(repo)
    before = subprocess.check_output([GIT,"-C",str(repo),"rev-parse","HEAD"],text=True).strip()
    env = mk_env()
    env.update({"GIT_BASE_DIR":str(scope),"GIT_USERNAME":"Synthetic MCP Test",
        "GIT_EMAIL":"synthetic-mcp@example.invalid","GIT_SIGN_COMMITS":"false"})
    return scope, repo, before, env


def sqlite_fixture():
    import sqlite3
    folder = FIX / "sqlite"
    folder.mkdir(parents=True, exist_ok=True)
    db = folder / "synthetic.sqlite"
    assert_fixture_path(db, folder)
    if db.exists():
        if db.is_symlink():
            raise RuntimeError(f"Refusing SQLite symlink: {db}")
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            people = con.execute("SELECT id,name FROM people ORDER BY id").fetchall() if "people" in tables else None
            events = con.execute("SELECT id,note FROM synthetic_events ORDER BY id").fetchall() if "synthetic_events" in tables else None
        finally:
            con.close()
        if tables != {"people", "synthetic_events"} or people != [(1, "Ada"), (2, "Grace")] or events not in ([], [(99, "written via MCP")]):
            raise RuntimeError(f"Refusing to replace unexpected SQLite fixture content: {db}")
        if events:
            con = sqlite3.connect(db)
            try:
                con.execute("DELETE FROM synthetic_events WHERE id = 99 AND note = 'written via MCP'")
                con.commit()
                if con.execute("SELECT id,note FROM synthetic_events").fetchall():
                    raise RuntimeError(f"Could not restore known synthetic event residue: {db}")
            finally:
                con.close()
    else:
        with sqlite3.connect(db) as con:
            con.executescript("CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT NOT NULL); INSERT INTO people VALUES (1, 'Ada'); INSERT INTO people VALUES (2, 'Grace'); CREATE TABLE synthetic_events (id INTEGER PRIMARY KEY, note TEXT NOT NULL);")
    uri = "sqlite:///" + str(db).replace("\\","/")
    return folder, db, uri


def public_result(response):
    return response.get("result", response)


def main():
    import sqlite3
    import hashlib
    timestamp = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    FIX.mkdir(parents=True, exist_ok=True)
    LOG.mkdir(parents=True, exist_ok=True)
    git_scope, repo, git_head_before, git_env = git_fixture()
    db_folder, db_path, db_uri = sqlite_fixture()
    git_entry = APP / "git" / "node_modules" / "@cyanheads" / "git-mcp-server" / "dist" / "index.js"
    db_entry = APP / "dbhub" / "node_modules" / "@bytebase" / "dbhub" / "dist" / "index.js"
    result = {"timestamp_kst":timestamp,"environment":{"node":subprocess.check_output([NODE,"--version"],text=True).strip(),
        "git":subprocess.check_output([GIT,"--version"],text=True).strip()},"servers":{}}

    clone_dest = FIX / "mcp-clone-boundary-probe"
    source_head = subprocess.check_output([GIT,"-C",str(repo),"rev-parse","HEAD"],text=True).strip()
    if clone_dest.exists():
        # Recover only a verified synthetic clone left by an interrupted prior run.
        remove_probe_clone(clone_dest, repo, source_head)

    g = MCP("git-mcp-server",[NODE,str(git_entry)],git_env,repo,LOG / "git-mcp-server.stderr.log")
    try:
        init, listing = init_client(g)
        result["servers"]["git"] = {"command":[NODE,str(git_entry)],"scope":str(git_scope),
            "initialize":init,"tools_list":listing}
        set_dir = call(g,"git_set_working_dir",{"path":str(repo)})
        status = call(g,"git_status",{})
        result["servers"]["git"]["read_calls"] = {"set_working_dir":set_dir,"git_status":status}
        sibling = git_scope / "other-repo"
        sibling.mkdir(parents=True, exist_ok=True)
        if not (sibling / ".git").exists():
            subprocess.run([GIT,"init","-b","main",str(sibling)],check=True,capture_output=True,text=True)
            subprocess.run([GIT,"-C",str(sibling),"config","user.name","Synthetic MCP Test"],check=True)
            subprocess.run([GIT,"-C",str(sibling),"config","user.email","synthetic-mcp@example.invalid"],check=True)
            (sibling / "sibling-only.txt").write_text("Second synthetic repository under configured base.\n",encoding="utf-8")
            subprocess.run([GIT,"-C",str(sibling),"add","sibling-only.txt"],check=True)
            subprocess.run([GIT,"-C",str(sibling),"commit","-m","test: seed second synthetic repository"],check=True,capture_output=True,text=True)
        sibling_access = call(g,"git_set_working_dir",{"path":str(sibling)})
        sibling_status = call(g,"git_status",{})
        outside = FIX / "outside-git-base"
        outside.mkdir(parents=True, exist_ok=True)
        assert_fixture_path(outside)
        if not (outside / ".git").exists():
            subprocess.run([GIT,"init","-b","main",str(outside)],check=True,capture_output=True,text=True)
            (outside / "outside-only.txt").write_text("Synthetic path outside configured GIT_BASE_DIR.\n",encoding="utf-8")
        else:
            assert_fixture_path(outside)
            if not (outside / ".git").is_dir():
                raise RuntimeError(f"Refusing unexpected outside Git fixture: {outside}")
            if (outside / "outside-only.txt").read_text(encoding="utf-8") != "Synthetic path outside configured GIT_BASE_DIR.\n":
                raise RuntimeError(f"Refusing unexpected existing outside fixture content: {outside}")
        outside_access = call(g,"git_set_working_dir",{"path":str(outside)})
        outside_status_implicit = call(g,"git_status",{})
        outside_status_explicit = call(g,"git_status",{"path":str(outside)})
        assert_fixture_path(clone_dest)
        clone_result = None
        cloned_head = None
        clone_result = call(g,"git_clone",{"url":str(repo),"path":str(clone_dest)})
        if clone_dest.exists():
            assert_probe_clone(clone_dest, repo, source_head)
            cloned_head = subprocess.check_output([GIT,"-C",str(clone_dest),"rev-parse","HEAD"],text=True).strip()
        result["servers"]["git"]["path_scope_check"] = {"configured_base":str(git_scope),
            "initial_repo":str(repo),"sibling_repo":str(sibling),"sibling_set_working_dir":sibling_access,
            "sibling_git_status":sibling_status,"outside_repo":str(outside),"outside_set_working_dir":outside_access,
            "outside_git_status_implicit":outside_status_implicit,"outside_git_status_explicit":outside_status_explicit,
            "outside_clone_destination":str(clone_dest),"outside_git_clone":clone_result,
            "outside_clone_verified_head":cloned_head,"source_head":source_head,
            "clone_head_matches_source":cloned_head == source_head}
        set_dir = call(g,"git_set_working_dir",{"path":str(repo)})
        result["servers"]["git"]["path_scope_check"]["restore_initial_repo"] = set_dir
    finally:
        g.close()

    clone_cleanup = {"server_process_exited":g.process.poll() is not None}
    try:
        if clone_dest.exists():
            remove_probe_clone(clone_dest, repo, source_head)
        clone_cleanup["removed_after_server_exit"] = not clone_dest.exists()
    except Exception as exc:
        clone_cleanup["cleanup_error"] = str(exc)
        clone_cleanup["removed_after_server_exit"] = not clone_dest.exists()
        # The Git MCP subprocess has exited; one guarded retry distinguishes transient locks from residue.
        try:
            if clone_dest.exists():
                remove_probe_clone(clone_dest, repo, source_head)
            clone_cleanup["retry_removed"] = not clone_dest.exists()
        except Exception as retry_exc:
            clone_cleanup["retry_error"] = str(retry_exc)
            clone_cleanup["retry_removed"] = not clone_dest.exists()
    result["servers"]["git"]["path_scope_check"]["clone_cleanup"] = clone_cleanup
    result["servers"]["git"]["path_scope_check"]["clone_destination_removed"] = not clone_dest.exists()

    g_write = MCP("git-mcp-server-write",[NODE,str(git_entry)],git_env,repo,LOG / "git-mcp-server-write.stderr.log")
    try:
        write_init, _ = init_client(g_write)
        write_result = {"initialize":write_init,"head_before":git_head_before}
        probe = repo / "mcp-write-probe.txt"
        assert_synthetic_git_repo(repo)
        if probe.exists():
            if probe.is_symlink() or probe.read_text(encoding="utf-8") != "Created only for the disposable MCP write check.\n":
                raise RuntimeError(f"Refusing to overwrite unexpected probe file: {probe}")
            if subprocess.check_output([GIT,"-C",str(repo),"status","--porcelain=v1"],text=True).strip() != "?? mcp-write-probe.txt":
                raise RuntimeError(f"Refusing stale probe recovery with unexpected repo changes: {repo}")
            assert_fixture_path(probe, repo)
            probe.unlink()
        assert_fixture_path(probe, repo)
        probe.write_text("Created only for the disposable MCP write check.\n",encoding="utf-8")
        try:
            stage = call(g_write,"git_add",{"path":str(repo),"paths":["mcp-write-probe.txt"]})
            commit = call(g_write,"git_commit",{"path":str(repo),"message":"test: synthetic MCP write"})
            post_head = subprocess.check_output([GIT,"-C",str(repo),"rev-parse","HEAD"],text=True).strip()
            post_status = subprocess.check_output([GIT,"-C",str(repo),"status","--porcelain=v1"],text=True)
            write_result.update({"stage":stage,"commit":commit,"head_after":post_head,"status_after":post_status})
        finally:
            assert_synthetic_git_repo(repo)
            cleanup = subprocess.run([GIT,"-C",str(repo),"reset","--hard",git_head_before],capture_output=True,text=True)
            write_result["restore"] = {"exit_code":cleanup.returncode,"stdout":cleanup.stdout,"stderr":cleanup.stderr,
                "head_after_restore":subprocess.check_output([GIT,"-C",str(repo),"rev-parse","HEAD"],text=True).strip(),
                "status_after_restore":subprocess.check_output([GIT,"-C",str(repo),"status","--porcelain=v1"],text=True),
                "probe_file_exists_after_restore":(repo/"mcp-write-probe.txt").exists()}
        result["servers"]["git"]["write_check"] = write_result
    finally:
        g_write.close()

    d = MCP("dbhub",[NODE,str(db_entry),"--transport=stdio",f"--dsn={db_uri}"],mk_env(),db_folder,LOG / "dbhub.stderr.log")
    try:
        init, listing = init_client(d)
        result["servers"]["sqlite"] = {"command":[NODE,str(db_entry),"--transport=stdio",f"--dsn={db_uri}"],
            "database_path":str(db_path),"initialize":init,"tools_list":listing}
        read = call(d,"execute_sql",{"sql":"SELECT id, name FROM people ORDER BY id"})
        result["servers"]["sqlite"]["read_call"] = read
        write_result = {}
        try:
            write = call(d,"execute_sql",{"sql":"INSERT INTO synthetic_events (id, note) VALUES (99, 'written via MCP')"})
            with sqlite3.connect(db_path) as con:
                independent_after_write = con.execute("SELECT id,note FROM synthetic_events ORDER BY id").fetchall()
            write_result.update({"write":write,"independent_after_write":independent_after_write})
        finally:
            assert_fixture_path(db_path, db_folder)
            with sqlite3.connect(db_path) as con:
                rows = con.execute("SELECT id,note FROM synthetic_events ORDER BY id").fetchall()
            if rows in ([], [(99, "written via MCP")]):
                try:
                    restore = call(d,"execute_sql",{"sql":"DELETE FROM synthetic_events WHERE id = 99"})
                    write_result["restore"] = restore
                except Exception as exc:
                    write_result["mcp_restore_error"] = str(exc)
                    with sqlite3.connect(db_path) as con:
                        con.execute("DELETE FROM synthetic_events WHERE id = 99 AND note = 'written via MCP'")
                        con.commit()
                    write_result["local_synthetic_fixture_fallback_restore"] = True
                with sqlite3.connect(db_path) as con:
                    independent_after_restore = con.execute("SELECT id,note FROM synthetic_events ORDER BY id").fetchall()
                write_result["independent_after_restore"] = independent_after_restore
            else:
                raise RuntimeError(f"Refusing SQLite cleanup with unexpected rows: {rows!r}")
        result["servers"]["sqlite"]["write_check"] = write_result
    finally:
        d.close()

    attach_path = db_folder / "attach-attempt.sqlite"
    extension_path = db_folder / "nonexistent-extension.dll"
    readonly_config = db_folder / "dbhub-readonly.toml"
    dsn_toml = db_uri.replace('"','\\"')
    readonly_config.write_text(f'[[sources]]\nid = "default"\ndsn = "{dsn_toml}"\n\n[[tools]]\nname = "execute_sql"\nsource = "default"\nreadonly = true\nmax_rows = 100\n',encoding="utf-8")
    ro_command = [NODE,str(db_entry),"--transport=stdio",f"--config={readonly_config}"]
    ro = MCP("dbhub-readonly",ro_command,mk_env(),db_folder,LOG / "dbhub-readonly.stderr.log")
    try:
        ro_init, ro_listing = init_client(ro)
        write_attempt = call(ro,"execute_sql",{"sql":"INSERT INTO synthetic_events (id, note) VALUES (7, 'must be denied')"})
        attach_sql = f"ATTACH DATABASE '{str(attach_path).replace(chr(92),'/')}' AS attached_probe"
        attach_attempt = call(ro,"execute_sql",{"sql":attach_sql})
        extension_sql = f"SELECT load_extension('{str(extension_path).replace(chr(92),'/')}')"
        extension_attempt = call(ro,"execute_sql",{"sql":extension_sql})
        with sqlite3.connect(db_path) as con:
            remaining_rows = con.execute("SELECT id,note FROM synthetic_events ORDER BY id").fetchall()
        result["servers"]["sqlite"]["readonly_scope_check"] = {"command":ro_command,
            "config_path":str(readonly_config),"config_sha256":hashlib.sha256(readonly_config.read_bytes()).hexdigest(),
            "initialize":ro_init,"tools_list":ro_listing,"insert_attempt":write_attempt,
            "attach_sql":attach_sql,"attach_attempt":attach_attempt,"attach_file_exists":attach_path.exists(),
            "load_extension_sql":extension_sql,"load_extension_attempt":extension_attempt,
            "synthetic_extension_file_exists":extension_path.exists(),"remaining_rows_after_restore":remaining_rows}
    finally:
        ro.close()

    EVIDENCE.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"evidence":str(EVIDENCE),"timestamp_kst":timestamp,
        "git_tools":len(result["servers"]["git"]["tools_list"].get("result",{}).get("tools",[])),
        "sqlite_tools":len(result["servers"]["sqlite"]["tools_list"].get("result",{}).get("tools",[])),
        "git_write_effect":result["servers"]["git"]["write_check"]["head_before"] != result["servers"]["git"]["write_check"]["head_after"],
        "sqlite_write_effect":bool(result["servers"]["sqlite"]["write_check"]["independent_after_write"]),
        "sqlite_restored":not result["servers"]["sqlite"]["write_check"]["independent_after_restore"]},ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
