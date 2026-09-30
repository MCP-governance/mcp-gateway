"""What a tool call touches: resources, destinations, data class and effective action.

The policy never looks at tool names to decide what data is involved. This module
turns the arguments of a call into facts the policy can judge:

  * resources   - paths, tables, repositories, keys ... each with a data class
  * destinations- URLs and e-mail recipients, each with a category
                  (intranet / external / infrastructure, internal / external mail)
  * action      - the registry's r/w/x for the tool, raised when the arguments make
                  the call worse (SQL DDL, mail to an outside domain, egress)
  * dlp         - labels of personal/secret data found in outbound content

Anything that cannot be classified is treated as important and, for destinations,
as infrastructure. Unknown is the dangerous case, so it gets the strictest answer.

Run `python -m app.classify` for the self-check.
"""
from __future__ import annotations

import ipaddress
import json
import posixpath
import re
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pglast import parser as pgparser

from . import registry

CLASS_ORDER = {"public": 0, "nonimportant": 1, "important": 2}
ACTION_ORDER = {"r": 0, "w": 1, "x": 2}


@dataclass
class Resource:
    kind: str
    id: str
    data_class: str
    owner_department: str | None = None

    def view(self) -> dict:
        return {"kind": self.kind, "id": self.id, "data_class": self.data_class,
                "owner_department": self.owner_department}


@dataclass
class Destination:
    kind: str       # url | email
    value: str
    host: str
    category: str   # intranet | external | infrastructure | internal-mail | external-mail

    @property
    def external(self) -> bool:
        return self.category in {"external", "external-mail"}

    def view(self) -> dict:
        return {"kind": self.kind, "value": self.value[:300], "host": self.host,
                "category": self.category, "external": self.external}


@dataclass
class Classification:
    server: str
    tool: str
    base_action: str
    action: str
    resources: list[Resource] = field(default_factory=list)
    destinations: list[Destination] = field(default_factory=list)
    dlp: list[str] = field(default_factory=list)
    restrictable: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def data_class(self) -> str:
        if not self.resources:
            return "important"
        return max((r.data_class for r in self.resources), key=CLASS_ORDER.__getitem__)

    @property
    def primary(self) -> Resource:
        if not self.resources:
            return Resource("unknown", f"{self.server}:{self.tool}", "important")
        return max(self.resources, key=lambda r: CLASS_ORDER[r.data_class])

    def escalate(self, action: str, note: str) -> None:
        if ACTION_ORDER[action] > ACTION_ORDER[self.action]:
            self.action = action
            self.notes.append(note)

    def summary(self) -> str:
        target = self.primary.id
        if self.destinations:
            target += " → " + ", ".join(d.value for d in self.destinations[:3])
        return f"{self.server}.{self.tool} {target}"[:400]


# ── DLP ─────────────────────────────────────────────────────────────────────
# Credentials by the prefix their issuer puts on them. Only formats a vendor documents
# are here, because a hit on an outbound call is a refusal (P-DLP-001): the generic
# "32+ hex" and "24+ base64" rules of the IBM CPEX secrets plugin (Apache-2.0,
# plugins/rust/python-package/secrets_detection/src/patterns.rs), from which the
# GitHub, Slack, Google, Stripe, JWT and AWS-secret forms below are taken, also match
# every git commit and SHA-256 digest a developer mails, so they are not.
# The same strings feed the Presidio recognizer that masks them in tool results.
SECRET_PATTERNS = {
    "aws-access-key": r"\bAKIA[0-9A-Z]{16}\b",
    "aws-secret-key": r"(?i)aws.{0,20}(?:secret|access).{0,20}[:=]\s*[\"']?[A-Za-z0-9/+=]{40}\b",
    "github-token": r"\b(?:gh[opusr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,})\b",
    "gitlab-token": r"\bglpat-[0-9A-Za-z_\-]{20,}\b",
    "slack-token": r"\bxox[abpqr]-[0-9A-Za-z\-]{10,80}\b",
    "google-api-key": r"\bAIza[0-9A-Za-z\-_]{35}\b",
    "stripe-key": r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b",
    # OpenAI keys and the LiteLLM virtual keys this lab issues share the `sk-` form.
    "sk-api-key": r"\bsk-(?!ant-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}\b",
    "anthropic-key": r"\bsk-ant-(?:api|admin)\d{2}-[A-Za-z0-9_\-]{40,}\b",
    "jwt": r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b",
    "private-key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "api-key-assignment": r"(?i)\b(?:(?:x[-_])?api[-_]?key|apikey|api[_-]?token|access[_-]?token|auth[_-]?token"
                          r"|bearer[_-]?token|client[_-]?secret)\b\s*[:=]\s*[\"']?[A-Za-z0-9_\-./+]{20,}",
}
DLP_PATTERNS = {
    "kr-rrn": re.compile(r"\b\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])-?[1-4]\d{6}\b"),
    "card-number": re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b"),
    "kr-mobile": re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b"),
    **{label: re.compile(pattern) for label, pattern in SECRET_PATTERNS.items()},
    "password-assignment": re.compile(r"(?i)\b(password|passwd|pwd|secret)\s*[=:]\s*\S{6,}"),
    "confidential-marker": re.compile(r"대외비|\bCONFIDENTIAL\b|기밀|급여|salary", re.IGNORECASE),
}


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        n = int(ch)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
        alt = not alt
    return total % 10 == 0


def dlp_scan(*values: Any) -> list[str]:
    """Labels only - the matched values never leave this function."""
    found: set[str] = set()
    for value in values:
        for text in _strings(value):
            for label, pattern in DLP_PATTERNS.items():
                for match in pattern.finditer(text):
                    if label == "card-number" and not _luhn(re.sub(r"\D", "", match.group())):
                        continue
                    found.add(label)
                    break
    return sorted(found)


def _strings(value: Any, depth: int = 0):
    if depth > 6:
        return
    if isinstance(value, str):
        yield value[:20000]
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value[:200]:
            yield from _strings(item, depth + 1)


# ── rule lookups ─────────────────────────────────────────────────────────────
def _rules(section: str) -> dict[str, str]:
    return registry.catalog().get("classification", {}).get(section, {})


def _org() -> dict:
    return registry.catalog().get("organization", {})


def _longest_prefix(value: str, rules: dict[str, str], sep: str = "/") -> str | None:
    best = None
    for prefix in rules:
        if value == prefix or value.startswith(prefix.rstrip(sep) + sep) or (sep == "" and value.startswith(prefix)):
            if best is None or len(prefix) > len(best):
                best = prefix
    return best


# Percent-encoded dots and slashes, and the `....//` form that survives one round of
# "strip ../". Nothing under these roots is named this way, and a path written like an
# attempt to get past a prefix check is not one to grade as public: the grade would be
# read off the prefix while the bytes say something else.
EVASIVE_PATH = re.compile(r"%2e|%2f|%5c|\.\.\.\.", re.IGNORECASE)


def path_resource(raw: Any, root: str, listing: bool = False) -> Resource:
    """A filesystem path under the server's root, classified by the longest prefix.

    For listing tools the answer also covers what lives *under* the path: listing
    /shared shows the names of confidential files, so it is as important as they are.
    """
    text = str(raw or "")
    if EVASIVE_PATH.search(text):
        return Resource("path", text[:300], "important")
    normalised = posixpath.normpath(text) if text.startswith("/") else posixpath.normpath(posixpath.join(root, text))
    rules = _rules("paths")
    owners = _rules("owners")
    if not (normalised == root or normalised.startswith(root.rstrip("/") + "/")):
        return Resource("path", normalised, "important")
    prefix = _longest_prefix(normalised, rules)
    data_class = rules[prefix] if prefix else "important"
    if listing:
        below = [rules[p] for p in rules if p.startswith(normalised.rstrip("/") + "/")]
        if below:
            data_class = max([data_class, *below], key=CLASS_ORDER.__getitem__)
    owner_prefix = _longest_prefix(normalised, owners)
    return Resource("path", normalised, data_class, owners[owner_prefix] if owner_prefix else None)


def _as_ip(text: str) -> ipaddress._BaseAddress | None:
    """One host label sequence as an address, in every form a resolver accepts.

    `ipaddress` only parses the dotted-quad form, but a connect() reaches 127.0.0.1
    through `127.1`, `0177.0.0.1`, `0x7f.0.0.1` and `2130706433` as well, so a check
    built on `ipaddress` alone reads those as ordinary names. inet_aton is the same
    parser the C library uses and touches no resolver, so an unknown name still raises.
    """
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        pass
    try:
        return ipaddress.IPv4Address(socket.inet_aton(text))
    except (OSError, ipaddress.AddressValueError):
        return None


def _internal_address(address: ipaddress._BaseAddress) -> bool:
    mapped = getattr(address, "ipv4_mapped", None)
    address = mapped or address
    return (address.is_private or address.is_loopback or address.is_link_local
            or address.is_reserved or address.is_multicast or address.is_unspecified)


def _embedded_addresses(host: str):
    """Addresses spelled inside a name: `169.254.169.254.nip.io`, `10-0-0-1.sslip.io`.

    A wildcard-DNS name resolves to the address written in it, so the destination is
    that address no matter which domain answers for it.
    """
    labels = host.split(".")
    for size in (4, 1):
        for start in range(len(labels) - size + 1):
            window = ".".join(labels[start:start + size])
            for candidate in (window, window.replace("-", ".")):
                address = _as_ip(candidate)
                if address is not None:
                    yield address


def host_category(raw_host: str) -> str:
    """intranet | infrastructure | external for a URL host, before any connection.

    Trailing dots, uppercase and the numeric address forms above are normalised first:
    `INTRANET.BOB.LOCAL.` and `intranet.bob.local` are one host, and a name that
    carries an internal address is infrastructure whoever resolves it.
    """
    org = _org()
    host = raw_host.strip().lower().rstrip(".")
    if not host:
        return "infrastructure"
    literal = _as_ip(host)
    if literal is not None:
        return "infrastructure" if _internal_address(literal) else "external"
    if host in {name.lower().rstrip(".") for name in org.get("intranet_hosts", [])}:
        return "intranet"
    if any(_internal_address(address) for address in _embedded_addresses(host)):
        return "infrastructure"
    infrastructure = {name.lower().rstrip(".") for name in org.get("infrastructure_hosts", [])}
    # A container service answers to both `corp-db` and `corp-db.bob.local`.
    if host in infrastructure or host.split(".")[0] in infrastructure:
        return "infrastructure"
    if any(host.startswith(prefix) for prefix in org.get("infrastructure_prefixes", [])):
        return "infrastructure"
    if "." not in host:  # a bare service name only resolves inside the lab
        return "infrastructure"
    # An internal domain that is not the approved intranet host is company infrastructure.
    if any(host == domain or host.endswith("." + domain)
           for domain in (name.lower().strip(".") for name in org.get("internal_domains", []))):
        return "infrastructure"
    return "external"


def url_destination(raw: Any) -> Destination:
    value = str(raw or "").strip()
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower().rstrip(".")
        parts.port  # validates malformed/out-of-range ports without resolving a host
    except ValueError:  # a malformed authority (bad IPv6 literal, bad port)
        return Destination("url", value, "", "infrastructure")
    if parts.scheme not in {"http", "https"} or not host:
        return Destination("url", value, host, "infrastructure")
    return Destination("url", value, host, host_category(host))


def email_destination(raw: Any) -> Destination:
    value = str(raw or "").strip()
    address = value.split("<")[-1].rstrip(">").strip().lower()
    domain = address.rsplit("@", 1)[-1] if "@" in address else ""
    internal = domain in _org().get("internal_email_domains", [])
    return Destination("email", address or value, domain, "internal-mail" if internal else "external-mail")


def _web_resource(dest: Destination) -> Resource:
    rules = _rules("web")
    if dest.category == "intranet":
        return Resource("web", dest.value, rules.get(dest.host, "nonimportant"))
    return Resource("web", dest.value, "public" if dest.category == "external" else "important")


# PostgreSQL's own grammar decides what a statement does (pglast wraps libpg_query,
# the parser the server itself uses). The regex version this replaces read the text
# instead: `SELECT ... INTO other.table` looked like a read, a table name inside a
# dollar-quoted string looked like DDL, and `pg_terminate_backend(...)` looked like an
# ordinary select. Anything the server would not accept is not classified at all -
# it is returned as "x", the strictest answer, because an unparsed statement is the
# case we know least about.
SQL_READ_STATEMENTS = {"SelectStmt", "TransactionStmt", "VariableShowStmt", "ExplainStmt"}
SQL_WRITE_STATEMENTS = {"InsertStmt", "UpdateStmt", "DeleteStmt", "MergeStmt"}
# Functions that reach outside the queried rows: the file system, another server,
# the session's own configuration, other backends, or the clock. They keep their
# meaning under any statement, so they are judged on the parsed call and not the text.
SQL_X_FUNCTIONS = {
    "pg_read_file", "pg_read_binary_file", "pg_stat_file", "pg_ls_dir", "pg_ls_logdir",
    "pg_ls_waldir", "pg_ls_tmpdir", "pg_ls_archivestatusdir", "pg_logdir_ls",
    "lo_import", "lo_export", "lo_unlink", "lo_put", "lo_from_bytea",
    "dblink", "dblink_exec", "dblink_connect", "dblink_send_query", "dblink_open",
    "set_config", "pg_terminate_backend", "pg_cancel_backend", "pg_reload_conf",
    "pg_rotate_logfile", "pg_switch_wal", "pg_create_restore_point", "pg_promote",
    "pg_sleep", "pg_sleep_for", "pg_sleep_until", "pg_advisory_lock",
    "pg_advisory_lock_shared", "pg_advisory_xact_lock", "query_to_xml", "copy_from_program",
}
# Sequence state survives the statement, so these are writes even inside a SELECT.
SQL_W_FUNCTIONS = {"nextval", "setval"}
# A SELECT can call a user-defined function with any side effect, so a function the
# server does not ship is judged as "x". Which functions it ships, and whether each can
# change anything, is the server's own catalog and not a list written here: an earlier
# hand-written allowlist of 40 names classified 25 of 40 ordinary analytics queries
# (`extract`, `row_number() over`, `split_part`, `percentile_cont` ...) as execution.
# pg_proc marks every built-in immutable, stable or volatile; PostgreSQL does not let an
# immutable or stable function modify the database, so those read. Volatile built-ins
# are mostly administration (locks, replication slots, files, backends, statistics
# resets) and are "x" unless they are listed here as reading only.
#   Regenerate for a new major version (output → pg_builtin_functions.json):
PG_FUNCTIONS_QUERY = """select proname, case when bool_or(provolatile = 'v') then 'v'
  when bool_or(provolatile = 's') then 's' else 'i' end
  from pg_proc where pronamespace = 'pg_catalog'::regnamespace group by proname"""
PG_FUNCTIONS: dict[str, str] = json.loads(
    (Path(__file__).parent / "pg_builtin_functions.json").read_text(encoding="utf-8"))["functions"]
SQL_READ_VOLATILE = {
    "random", "random_normal", "setseed", "array_sample", "array_shuffle", "clock_timestamp",
    "timeofday", "gen_random_uuid", "uuidv4", "uuidv7", "currval", "lastval",
    "pg_database_size", "pg_relation_size", "pg_table_size", "pg_total_relation_size",
    "pg_indexes_size", "pg_tablespace_size", "pg_partition_tree", "pg_partition_ancestors",
    "pg_is_in_recovery", "pg_blocking_pids", "pg_lock_status", "pg_xact_status", "txid_status",
    "pg_sequence_last_value",
}


def _function_action(name: str) -> str:
    """r/w/x for one called function, as the parse tree spells it (schema.name or name)."""
    schema, _, bare = name.rpartition(".")
    if schema and schema != "pg_catalog":
        return "x"  # a function in a user schema, whatever it is called
    if bare in SQL_X_FUNCTIONS:
        return "x"
    if bare in SQL_W_FUNCTIONS:
        return "w"
    volatility = PG_FUNCTIONS.get(bare)
    if volatility is None:
        return "x"  # not shipped with the server: user-defined or an extension
    if volatility == "v" and bare not in SQL_READ_VOLATILE:
        return "x"
    return "r"


def _sql_nodes(node: Any, key: str):
    """Every value stored under `key` anywhere in the parse tree."""
    if isinstance(node, dict):
        for name, value in node.items():
            if name == key:
                yield value
            yield from _sql_nodes(value, key)
    elif isinstance(node, list):
        for item in node:
            yield from _sql_nodes(item, key)


def _sql_relations(node: Any, skip: set[str]) -> set[str]:
    """schema-qualified names of every relation the statement names.

    A RangeVar is tagged in generic fields but bare in typed ones (`InsertStmt.relation`,
    `IntoClause.rel`), so the shape is what identifies it, not the tag.
    """
    found: set[str] = set()
    stack = [node]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            name = item.get("relname")
            if isinstance(name, str) and name:
                schema = item.get("schemaname")
                if schema or name.lower() not in skip:
                    found.add(f"{(schema or 'public').lower()}.{name.lower()}")
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return found


def _copy_action(copy: dict) -> str:
    """COPY moves rows between a table and somewhere else.

    Through the client (STDIN/STDOUT) it is an ordinary read or write. With a program
    or a server-side path it runs a command or touches the server's disk.
    """
    if copy.get("is_program") or copy.get("filename"):
        return "x"
    return "w" if copy.get("is_from") else "r"


def _statement_action(statement: dict) -> str:
    kind = next(iter(statement), "")
    body = statement.get(kind) or {}
    if kind == "SelectStmt":
        # SELECT ... INTO creates a table and fills it: the rows leave the source.
        return "x" if body.get("intoClause") else "r"
    if kind == "CopyStmt":
        return _copy_action(body)
    if kind == "ExplainStmt":
        # EXPLAIN plans; EXPLAIN ANALYZE runs the statement it is given.
        options = {option.get("DefElem", {}).get("defname") for option in body.get("options") or []}
        return _statement_action(body.get("query") or {}) if "analyze" in options else "r"
    if kind in SQL_WRITE_STATEMENTS:
        return "w"
    if kind in SQL_READ_STATEMENTS:
        return "r"
    return "x"  # DDL, GRANT/REVOKE, DO, CALL, SET, VACUUM, LOCK ... and anything new


def sql_facts(sql: str) -> tuple[str, list[str]]:
    """(effective action, schema-qualified tables) for a SQL text."""
    try:
        tree = json.loads(pgparser.parse_sql_json(sql or ""))
    except Exception:
        return "x", []
    action = "r"
    # Every statement the text submits, plus the ones nested in WITH: a data-modifying
    # CTE runs under a SELECT, so the outer statement's kind alone would read as a read.
    statements = [wrapper.get("stmt") or {} for wrapper in tree.get("stmts") or []]
    statements += [nested for nested in _sql_nodes(tree, "ctequery") if isinstance(nested, dict)]
    for statement in statements:
        action = max(action, _statement_action(statement), key=ACTION_ORDER.__getitem__)
    functions = {".".join(part["String"]["sval"] for part in call.get("funcname") or [] if "String" in part).lower()
                 for call in _sql_nodes(tree, "FuncCall")}
    for name in functions:
        action = max(action, _function_action(name), key=ACTION_ORDER.__getitem__)
    # A CTE name is a label for rows inside this statement, not a company table.
    ctes = {name.lower() for name in _sql_nodes(tree, "ctename") if isinstance(name, str)}
    return action, sorted(_sql_relations(tree, ctes))


# ── usage relationship scope (D-39) ─────────────────────────────────────────
# A relationship's allowed_resources name company data of four kinds. Other kinds (a
# mail message, a shell command, a URL) are not something a relationship grants, so
# they neither widen nor break its scope; destinations are judged by the egress rules.
SCOPED_KINDS = {"path", "repository", "table", "mailbox"}
CATALOG_SCHEMAS = ("information_schema.", "pg_catalog.")


def _scope_covers(entry: str, resource: Resource) -> bool:
    entry = str(entry).strip()
    if resource.kind == "path":
        base = posixpath.normpath(entry) if entry.startswith("/") else None
        return bool(base) and (base == "/" or resource.id == base or resource.id.startswith(base + "/"))
    value, entry = resource.id.lower(), entry.lower()
    # "sales.*" and "bob/*" name a whole schema or organisation.
    if entry.endswith(("/*", ".*")):
        return value.startswith(entry[:-1])
    return value == entry


def outside_scope(resources: list[Resource], allowed: list[str]) -> list[str]:
    """Ids of this call's scoped resources that no allowed resource covers."""
    outside = []
    for resource in resources:
        if resource.kind not in SCOPED_KINDS or resource.id.startswith("("):
            continue
        # Catalog views are database metadata, not company data (catalog.toml).
        if resource.kind == "table" and resource.id.startswith(CATALOG_SCHEMAS):
            continue
        if not any(_scope_covers(entry, resource) for entry in allowed):
            outside.append(resource.id)
    return outside


def table_resource(name: str) -> Resource:
    rules = _rules("tables")
    schema = name.split(".", 1)[0]
    data_class = rules.get(name) or rules.get(schema) or "important"
    return Resource("table", name, data_class)


def redis_resource(key: Any, pattern: bool = False) -> Resource:
    text = str(key or "")
    rules = _rules("redis")
    if pattern:
        literal = text.split("*", 1)[0].split("?", 1)[0].split("[", 1)[0]
        matches = [cls for prefix, cls in rules.items() if prefix.startswith(literal) or literal.startswith(prefix)]
        if not literal or not matches:
            return Resource("redis-pattern", text or "*", "important")
        return Resource("redis-pattern", text, max(matches, key=CLASS_ORDER.__getitem__))
    prefix = _longest_prefix(text, rules, sep="")
    return Resource("redis-key", text, rules[prefix] if prefix else "important")


def repo_resource(owner: Any, repo: Any) -> Resource:
    name = f"{owner}/{repo}".lower().strip("/")
    return Resource("repository", name, _rules("repos").get(name, "important"))


# ── per-server extraction ────────────────────────────────────────────────────
LISTING_TOOLS = {"list_directory", "list_directory_with_sizes", "directory_tree", "search_files",
                 "start_search", "list_allowed_directories"}
PATH_ARGS = ("path", "source", "destination", "file_path", "outputPath")


def _paths(args: dict, root: str, tool: str, cls: Classification) -> None:
    listing = tool in LISTING_TOOLS
    for key in PATH_ARGS:
        if args.get(key):
            cls.resources.append(path_resource(args[key], root, listing))
    for item in args.get("paths") or []:
        cls.resources.append(path_resource(item, root, listing))
    if not cls.resources:
        cls.resources.append(path_resource(root, root, listing=True))


def _filesystem(tool: str, args: dict, cls: Classification) -> None:
    _paths(args, "/shared", tool, cls)


def _desktop(tool: str, args: dict, cls: Classification) -> None:
    if tool == "read_file" and args.get("isUrl"):
        dest = url_destination(args.get("path"))
        cls.destinations.append(dest)
        cls.resources.append(_web_resource(dest))
        if dest.category != "intranet":
            cls.escalate("x", "URL 읽기는 외부 전송 경로")
        return
    if tool in {"start_process", "interact_with_process"}:
        command = str(args.get("command") or args.get("input") or "")
        cls.resources.append(Resource("command", command[:300], "nonimportant"))
        for token in re.findall(r"(/[\w./-]+)", command):
            if not token.startswith("/workspace") and not token.startswith(("/usr/", "/bin/")):
                cls.resources.append(path_resource(token, "/workspace"))
        for url in re.findall(r"https?://[^\s'\"]+", command):
            cls.destinations.append(url_destination(url))
        cls.dlp = dlp_scan(command)
        return
    _paths(args, "/workspace", tool, cls)


def _git(tool: str, args: dict, cls: Classification) -> None:
    repo = args.get("repo_path") or "/repos"
    cls.resources.append(path_resource(repo, "/repos", listing=True))


def _fetch(tool: str, args: dict, cls: Classification) -> None:
    dest = url_destination(args.get("url"))
    cls.destinations.append(dest)
    cls.resources.append(_web_resource(dest))
    cls.restrictable = ["max_chars"]
    if dest.category == "external":
        cls.escalate("x", "외부 인터넷으로 나가는 요청(egress)")
    cls.dlp = dlp_scan(args.get("url"))


def _memory(tool: str, args: dict, cls: Classification) -> None:
    spec = registry.server("memory") or {}
    cls.resources.append(Resource("knowledge-graph", "memory:graph", spec.get("data_class", "nonimportant")))


def _postgres(tool: str, args: dict, cls: Classification) -> None:
    if tool in {"execute_sql", "explain_query"}:
        action, tables = sql_facts(str(args.get("sql") or ""))
        if tool == "explain_query" and not args.get("analyze"):
            action = "r"  # EXPLAIN without ANALYZE plans but does not execute
        cls.escalate(action, "SQL 문장 유형에 따른 행위")
        cls.resources.extend(table_resource(t) for t in tables)
        if not tables:
            cls.resources.append(Resource("table", "(no table)", "public"))
    elif tool == "get_object_details":
        schema = args.get("schema_name") or "public"
        cls.resources.append(table_resource(f"{schema}.{args.get('object_name', '')}".lower()))
    elif tool == "analyze_query_indexes":
        for sql in args.get("queries") or []:
            cls.resources.extend(table_resource(t) for t in sql_facts(str(sql))[1])
        cls.resources.append(Resource("database", "corp", "public"))
    elif tool == "get_top_queries":
        # Query texts from pg_stat_statements can carry literals from any table.
        cls.resources.append(Resource("database", "corp:query-history", "important"))
    else:
        cls.resources.append(Resource("database", "corp:catalog", "public"))


def _redis(tool: str, args: dict, cls: Classification) -> None:
    if tool in {"scan_keys", "scan_all_keys"}:
        cls.resources.append(redis_resource(args.get("pattern") or "*", pattern=True))
        return
    for key in ("key", "name", "old_key", "new_key"):
        if args.get(key):
            cls.resources.append(redis_resource(args[key]))
    if not cls.resources:
        cls.resources.append(Resource("redis", "corp-redis:server", "public"))


def _email(tool: str, args: dict, cls: Classification) -> None:
    mailbox = Resource("mailbox", "ai-assistant@bob.local", "nonimportant")
    if tool not in {"send_email", "forward_email", "save_to_mailbox"}:
        cls.resources.append(mailbox)
        return
    for key in ("recipients", "cc", "bcc"):
        values = args.get(key) or []
        for value in values if isinstance(values, list) else [values]:
            cls.destinations.append(email_destination(value))
    cls.dlp = dlp_scan(args.get("subject"), args.get("body"))
    content_class = "important" if cls.dlp else "nonimportant"
    cls.resources.append(Resource("message", str(args.get("subject") or "(forward)")[:120], content_class))
    if args.get("attachments"):
        cls.resources.append(Resource("attachment", ",".join(map(str, args["attachments"]))[:200], "important"))
    if tool != "save_to_mailbox":
        cls.restrictable = ["max_chars", "journal_bcc"] if tool == "send_email" else ["journal_bcc"]
    if any(d.external for d in cls.destinations):
        cls.escalate("x", "사외 수신자에게 발송")


def _gitea(tool: str, args: dict, cls: Classification) -> None:
    if args.get("owner") and args.get("repo"):
        cls.resources.append(repo_resource(args["owner"], args["repo"]))
    elif args.get("org") or tool in {"list_org_repos", "search_repos", "list_my_repos"}:
        # Listings reveal names of every repository, including the important one.
        cls.resources.append(Resource("repository-list", f"{args.get('org') or 'bob'}/*", "nonimportant"))
    else:
        cls.resources.append(Resource("gitea", "corp-git:metadata", "public"))
    if tool in {"create_or_update_file", "issue_write", "wiki_write", "pull_request_write"}:
        cls.dlp = dlp_scan(args.get("content"), args.get("body"), args.get("title"))


# Pages the playwright browser currently shows, per principal. The Gateway cannot
# see the browser, so it remembers where each person navigated; an interaction on
# an unknown page is treated as happening on an external one.
_browser_page: dict[str, Destination] = {}


def _playwright(tool: str, args: dict, cls: Classification, principal: str) -> None:
    if tool in {"browser_navigate"} or (tool == "browser_tabs" and args.get("url")):
        dest = url_destination(args.get("url"))
        cls.destinations.append(dest)
        cls.resources.append(_web_resource(dest))
        if dest.category == "external":
            cls.escalate("x", "외부 사이트로 이동(egress)")
        cls.dlp = dlp_scan(args.get("url"))
        return
    page = _browser_page.get(principal)
    if page is None:
        page = Destination("url", "(unknown page)", "", "external")
    cls.destinations.append(page)
    cls.resources.append(_web_resource(page))
    if tool in {"browser_type", "browser_fill_form", "browser_select_option", "browser_press_key"}:
        cls.dlp = dlp_scan(args.get("text"), args.get("fields"), args.get("values"))
        if page.category != "intranet":
            cls.escalate("x", "외부 페이지에 입력")


def remember_navigation(principal: str, cls: Classification, executed: bool) -> None:
    if executed and cls.server == "playwright" and cls.tool in {"browser_navigate", "browser_tabs"} and cls.destinations:
        _browser_page[principal] = cls.destinations[0]


EXTRACTORS = {
    "filesystem": _filesystem, "desktop": _desktop, "git": _git, "fetch": _fetch,
    "memory": _memory, "postgres": _postgres, "redis": _redis, "email": _email, "gitea": _gitea,
}


def classify(server: str, tool: str, arguments: dict | None, principal: str = "") -> Classification:
    base = registry.approved_tools(server).get(tool, "x")
    cls = Classification(server=server, tool=tool, base_action=base, action=base)
    args = arguments if isinstance(arguments, dict) else {}
    try:
        if server == "playwright":
            _playwright(tool, args, cls, principal)
        elif server in EXTRACTORS:
            EXTRACTORS[server](tool, args, cls)
        elif (spec := registry.server(server) or {}).get("data_class") in CLASS_ORDER:
            # A server registered from the Console has no argument extractor; its whole data is
            # the grade the admin gave it at registration (D-49). Unknown stays important.
            cls.resources.append(Resource("service", f"{server}:{tool}", spec["data_class"]))
            cls.dlp = dlp_scan(args)
    except Exception as exc:  # classification must never make a call look safer
        cls.resources = [Resource("unclassified", f"{server}:{tool}", "important")]
        cls.escalate("x", f"분류 실패: {type(exc).__name__}")
    if any(d.category == "infrastructure" for d in cls.destinations):
        cls.notes.append("내부 인프라 주소를 목적지로 지정(SSRF)")
    if cls.dlp and cls.action == "x":
        cls.notes.append("외부로 나가는 내용에 민감정보 패턴")
    return cls


def apply_restrictions(cls: Classification, arguments: dict, restrictions: dict) -> tuple[dict, list[str]]:
    """Rewrite arguments to honour a Restrict decision. Unknown keys never get here:
    the Gateway rejects a policy result whose restrictions this tool cannot enforce."""
    args = dict(arguments)
    applied = []
    if "max_chars" in restrictions:
        limit = int(restrictions["max_chars"])
        if cls.server == "fetch":
            args["max_length"] = min(int(args.get("max_length") or limit), limit)
            applied.append(f"max_length={args['max_length']}")
        elif cls.server == "email" and isinstance(args.get("body"), str):
            args["body"] = args["body"][:limit]
            applied.append(f"body≤{limit}자")
    if "journal_bcc" in restrictions and cls.server == "email":
        bcc = list(args.get("bcc") or [])
        if restrictions["journal_bcc"] not in bcc:
            bcc.append(restrictions["journal_bcc"])
        args["bcc"] = bcc
        applied.append(f"bcc+{restrictions['journal_bcc']}")
    return args, applied


if __name__ == "__main__":
    assert classify("filesystem", "read_text_file", {"path": "/shared/confidential/hr/salary-2026.csv"}).data_class == "important"
    assert classify("filesystem", "read_text_file", {"path": "/shared/public/company-intro.md"}).data_class == "public"
    assert classify("filesystem", "read_text_file", {"path": "/shared/public/../confidential/x"}).data_class == "important"
    # A path written to get past a prefix check is graded on that fact, not on its prefix.
    for evasive in ("/shared/public/%2e%2e/confidential/hr/salary-2026.csv",
                    "/shared/public/....//....//confidential/hr/x",
                    "/shared/public/..%2fconfidential/hr/x"):
        assert classify("filesystem", "read_text_file", {"path": evasive}).data_class == "important", evasive
    assert classify("filesystem", "read_text_file", {"path": "/shared/public/q3...final.md"}).data_class == "public"
    assert classify("filesystem", "list_directory", {"path": "/shared"}).data_class == "important"
    assert classify("filesystem", "list_directory", {"path": "/shared/partners"}).data_class == "public"
    assert classify("filesystem", "write_file", {"path": "/etc/passwd", "content": "x"}).data_class == "important"
    assert classify("postgres", "execute_sql", {"sql": "select * from sales.orders"}).action == "r"
    assert classify("postgres", "execute_sql", {"sql": "SELECT * FROM hr.salaries"}).data_class == "important"
    assert classify("postgres", "execute_sql", {"sql": "update hr.employees set title='x'"}).action == "w"
    assert classify("postgres", "execute_sql", {"sql": "drop table public.products"}).action == "x"
    assert classify("postgres", "execute_sql", {"sql": "select 1; drop table x"}).action == "x"
    assert classify("postgres", "execute_sql", {"sql": "select '; drop table x' as s"}).action == "r"
    assert classify("postgres", "execute_sql", {"sql": "with d as (delete from sales.orders returning *) select * from d"}).action == "w"
    # The parser answers on the statement's meaning, not on words in the text.
    assert sql_facts("select $$; drop table x;$$") == ("r", [])
    assert sql_facts("select 1 /* drop table x */") == ("r", [])
    assert sql_facts("select public.count(*) from public.products")[0] == "x"
    assert sql_facts("select custom_side_effect()")[0] == "x"
    assert sql_facts("select pg_catalog.count(*) from public.products")[0] == "r"
    # What the server ships and marks side-effect free reads; the rest does not. Syntax the
    # parser rewrites into catalog calls (EXTRACT, AT TIME ZONE, POSITION, TRIM) reads too.
    for analytics in (
            "select extract(year from created_at) as y, count(*) from sales.orders group by 1",
            "select id, row_number() over (order by amount desc) from sales.orders",
            "select id, lag(amount) over (order by created_at) from sales.orders",
            "select percentile_cont(0.5) within group (order by amount) from sales.orders",
            "select created_at at time zone 'Asia/Seoul' from sales.orders",
            "select split_part(email, '@', 2), position('@' in email) from sales.customers",
            "select trim(both ' ' from name), regexp_replace(name, '[0-9]', '', 'g') from public.products",
            "select stddev(amount), bool_and(true) from sales.orders",
            "select * from generate_series(1, 10)", "select random(), gen_random_uuid()",
            "select jsonb_extract_path_text('{}'::jsonb, 'k'), md5('x'), format('%s', 1)",
            "select pg_total_relation_size('sales.orders')"):
        assert sql_facts(analytics)[0] == "r", analytics
    for side_effect in ("select pg_notify('c', 'x')", "select pg_stat_reset()",
                        "select pg_create_logical_replication_slot('s', 'pgoutput')",
                        "select pg_try_advisory_lock(1)", "select lo_creat(-1)",
                        "select ts_stat('select vector from docs')", "select pg_hba_file_rules()",
                        "select myschema.harmless_looking()", "select not_a_builtin(1)"):
        assert sql_facts(side_effect)[0] == "x", side_effect
    for malformed in ("http://[invalid/", "https://example.com:99999/", "http://example.com:bad/"):
        assert url_destination(malformed).category == "infrastructure"
    assert sql_facts("with d as (delete from sales.orders returning *) select * from d") == ("w", ["sales.orders"])
    assert sql_facts("select * into public.stolen from hr.salaries") == ("x", ["hr.salaries", "public.stolen"])
    assert sql_facts("create table t as select * from hr.salaries")[0] == "x"
    assert sql_facts("insert into public.audit select * from hr.salaries") == ("w", ["hr.salaries", "public.audit"])
    assert sql_facts("explain select * from hr.salaries") == ("r", ["hr.salaries"])
    assert sql_facts("explain analyze delete from sales.orders") == ("w", ["sales.orders"])
    assert sql_facts("copy hr.salaries to stdout")[0] == "r"
    assert sql_facts("copy hr.salaries to program 'curl http://x'")[0] == "x"
    assert sql_facts("copy hr.salaries to '/tmp/x.csv'")[0] == "x"
    for reaching_out in ("select pg_terminate_backend(123)", "select set_config('role','postgres',false)",
                         "select pg_read_file('/etc/passwd')", "select lo_import('/etc/passwd')",
                         "select dblink_exec('host=x','drop table y')", "select pg_sleep(600)",
                         "select * from pg_ls_dir('/')", "select pg_reload_conf()"):
        assert sql_facts(reaching_out)[0] == "x", reaching_out
    assert sql_facts("select nextval('sales.orders_id_seq')")[0] == "w"
    assert sql_facts("select this is not sql") == ("x", [])  # unparsed stays the strictest answer
    assert sql_facts("select * from information_schema.tables") == ("r", ["information_schema.tables"])
    mail = classify("email", "send_email", {"recipients": ["a@gmail.com"], "subject": "hi", "body": "900101-1234567"})
    assert mail.action == "x" and "kr-rrn" in mail.dlp and mail.data_class == "important"
    assert classify("email", "send_email", {"recipients": ["ysg@bob.local"], "subject": "배포", "body": "완료"}).action == "w"
    assert classify("fetch", "fetch", {"url": "http://intranet.bob.local/wiki/onboarding.html"}).action == "r"
    assert classify("fetch", "fetch", {"url": "https://share.external.example/?q=1"}).action == "x"
    assert classify("fetch", "fetch", {"url": "http://corp-git:3000/api/v1/admin/users"}).destinations[0].category == "infrastructure"
    assert classify("fetch", "fetch", {"url": "http://169.254.169.254/latest"}).destinations[0].category == "infrastructure"
    assert classify("fetch", "fetch", {"url": "file:///etc/passwd"}).destinations[0].category == "infrastructure"
    # Every spelling a resolver accepts for an internal address is the same destination.
    for internal in ("http://127.1/", "http://0x7f.0.0.1/", "http://0177.0.0.1/", "http://2130706433/",
                     "http://[::ffff:127.0.0.1]/", "http://LOCALHOST./", "http://0/",
                     "http://127.0.0.1.nip.io/", "http://169.254.169.254.nip.io/", "http://10-0-0-1.sslip.io/",
                     "http://corp-db.bob.local/", "http://corp-git.bob.local:3000/api/v1/admin/users",
                     "https://example.com@127.0.0.1/", "http://[::1]/", "http://192.168.0.5/"):
        assert url_destination(internal).category == "infrastructure", internal
    assert url_destination("http://intranet.bob.local./wiki").category == "intranet"
    assert url_destination("http://INTRANET.BOB.LOCAL/wiki").category == "intranet"
    for outside in ("https://share.external.example/", "https://8.8.8.8/", "http://example.com/"):
        assert url_destination(outside).category == "external", outside
    assert classify("redis", "get", {"key": "session:3f9a1c"}).data_class == "important"
    assert classify("redis", "scan_keys", {"pattern": "cache:*"}).data_class == "public"
    assert classify("redis", "scan_keys", {"pattern": "*"}).data_class == "important"
    assert classify("gitea", "get_file_contents", {"owner": "bob", "repo": "infra-secrets", "path": "prod/db.env"}).data_class == "important"
    assert classify("git", "git_log", {"repo_path": "/repos/handbook"}).data_class == "public"
    assert classify("desktop", "start_process", {"command": "cat /etc/shadow"}).data_class == "important"
    assert classify("playwright", "browser_type", {"text": "x"}, "p1").action == "x"  # unknown page counts as external
    nav = classify("playwright", "browser_navigate", {"url": "http://intranet.bob.local/"}, "p1")
    remember_navigation("p1", nav, True)
    assert classify("playwright", "browser_type", {"text": "x"}, "p1").action == "w"
    assert classify("unknown-server", "anything", {}).data_class == "important"
    assert dlp_scan("card 4111 1111 1111 1111") == ["card-number"] and dlp_scan("1234 5678 9012 3456") == []
    # Issuer-prefixed credentials. Synthetic values assembled here so no real key sits in the source.
    fake = "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0"
    for label, text in (("github-token", "GITHUB_TOKEN=ghp_" + fake[:36]),
                        ("github-token", "github_pat_11" + fake + "_x"),
                        ("gitlab-token", "glpat-" + fake[:20]),
                        ("slack-token", "xoxb-123456789012-" + fake[:24]),
                        ("google-api-key", "AIza" + fake[:35]),
                        ("stripe-key", "sk_live_" + fake[:24]),
                        ("sk-api-key", "OPENAI_API_KEY=sk-proj-" + fake),
                        ("anthropic-key", "sk-ant-api03-" + fake + fake[:10]),
                        ("jwt", "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0." + fake),
                        ("aws-secret-key", "aws_secret_access_key = " + fake),
                        ("api-key-assignment", "client_secret: " + fake)):
        assert label in dlp_scan(text), (label, dlp_scan(text))
    # What a developer mails every day must not read as a credential.
    for ordinary in ("commit 9f1c2ab34de56f7890a1b2c3d4e5f60718293a4b merged",
                     "sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                     "request 123e4567-e89b-12d3-a456-426614174000 failed",
                     "pip install scikit-learn==1.5.0", "see https://github.com/pglast/pglast",
                     "the access token expires in 10 minutes"):
        assert dlp_scan(ordinary) == [], (ordinary, dlp_scan(ordinary))
    leak = classify("email", "send_email", {"recipients": ["x@gmail.com"], "subject": "config",
                                            "body": "GITHUB_TOKEN=ghp_" + fake[:36]})
    assert leak.action == "x" and "github-token" in leak.dlp, (leak.action, leak.dlp)
    args, applied = apply_restrictions(mail, {"recipients": ["a@gmail.com"], "body": "x" * 50}, {"max_chars": 10, "journal_bcc": "c@bob.local"})
    assert len(args["body"]) == 10 and args["bcc"] == ["c@bob.local"] and len(applied) == 2
    # Usage relationship scope: path prefixes by segment, exact or wildcard names, unscoped kinds ignored.
    scoped = classify("filesystem", "write_file", {"path": "/shared/team/data/x.md", "content": "x"})
    assert outside_scope(scoped.resources, ["/shared"]) == []
    assert outside_scope(classify("filesystem", "read_text_file", {"path": "/sharedx/a"}).resources, ["/shared"]) == ["/sharedx/a"]
    orders = classify("postgres", "execute_sql", {"sql": "SELECT * FROM sales.orders o JOIN public.products p ON p.id = o.product_id"})
    assert outside_scope(orders.resources, ["public.products", "sales.orders"]) == []
    assert outside_scope(classify("postgres", "execute_sql", {"sql": "select * from sales.customers"}).resources,
                         ["public.products", "sales.orders"]) == ["sales.customers"]
    assert outside_scope(classify("postgres", "execute_sql", {"sql": "select * from sales.customers"}).resources, ["sales.*"]) == []
    assert outside_scope(classify("postgres", "execute_sql", {"sql": "select * from information_schema.tables"}).resources, []) == []
    assert outside_scope(classify("gitea", "get_file_contents", {"owner": "bob", "repo": "infra-secrets", "path": "a"}).resources,
                         ["bob/handbook", "bob/payment-service"]) == ["bob/infra-secrets"]
    assert outside_scope(classify("email", "send_email", {"recipients": ["ysg@bob.local"], "subject": "s", "body": "b"}).resources, []) == []
    print("classify self-check: OK")
