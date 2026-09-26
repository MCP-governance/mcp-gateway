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
import posixpath
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

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
DLP_PATTERNS = {
    "kr-rrn": re.compile(r"\b\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])-?[1-4]\d{6}\b"),
    "card-number": re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b"),
    "kr-mobile": re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b"),
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private-key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
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


def path_resource(raw: Any, root: str, listing: bool = False) -> Resource:
    """A filesystem path under the server's root, classified by the longest prefix.

    For listing tools the answer also covers what lives *under* the path: listing
    /shared shows the names of confidential files, so it is as important as they are.
    """
    text = str(raw or "")
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


def url_destination(raw: Any) -> Destination:
    value = str(raw or "").strip()
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    org = _org()
    if parts.scheme not in {"http", "https"} or not host:
        return Destination("url", value, host, "infrastructure")
    if host in org.get("intranet_hosts", []):
        return Destination("url", value, host, "intranet")
    if host in org.get("infrastructure_hosts", []) or any(host.startswith(p) for p in org.get("infrastructure_prefixes", [])):
        return Destination("url", value, host, "infrastructure")
    try:
        address = ipaddress.ip_address(host)
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            return Destination("url", value, host, "infrastructure")
    except ValueError:
        pass
    if "." not in host:  # a bare service name only resolves inside the lab
        return Destination("url", value, host, "infrastructure")
    return Destination("url", value, host, "external")


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


SQL_READ = {"select", "with", "show", "explain", "values", "table"}
SQL_WRITE = {"insert", "update", "delete", "merge", "copy", "upsert"}
TABLE_REF = re.compile(r"\b(?:from|join|into|update|table|truncate)\s+(?:only\s+)?"
                       r"((?:\"?[a-zA-Z_][\w$]*\"?\.)?\"?[a-zA-Z_][\w$]*\"?)", re.IGNORECASE)


def sql_facts(sql: str) -> tuple[str, list[str]]:
    """(action, tables) for a SQL text. Comments are stripped; string literals too."""
    text = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql or "", flags=re.S)
    text = re.sub(r"'(?:[^']|'')*'", "''", text)
    action = "r"
    for statement in (part.strip() for part in text.split(";")):
        if not statement:
            continue
        verb = statement.split(None, 1)[0].lower()
        if verb in SQL_READ:
            lowered = statement.lower()
            # CTE/SELECT that writes, and anything that runs programs or files.
            if re.search(r"\b(insert|update|delete|merge)\b", lowered):
                action = max(action, "w", key=ACTION_ORDER.__getitem__)
            if re.search(r"\b(pg_read_file|pg_ls_dir|lo_import|lo_export|dblink|copy\s)", lowered):
                action = "x"
            continue
        if verb in SQL_WRITE:
            if verb == "copy" and re.search(r"\bprogram\b|\bto\s+'/", statement, re.I):
                action = "x"
            else:
                action = max(action, "w", key=ACTION_ORDER.__getitem__)
            continue
        action = "x"  # DDL, GRANT/REVOKE, DO, CALL, SET ROLE, VACUUM ... or unknown
    tables = []
    for match in TABLE_REF.finditer(text):
        name = match.group(1).replace('"', "").lower()
        tables.append(name if "." in name else f"public.{name}")
    return action, sorted(set(tables))


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
    mail = classify("email", "send_email", {"recipients": ["a@gmail.com"], "subject": "hi", "body": "900101-1234567"})
    assert mail.action == "x" and "kr-rrn" in mail.dlp and mail.data_class == "important"
    assert classify("email", "send_email", {"recipients": ["ysg@bob.local"], "subject": "배포", "body": "완료"}).action == "w"
    assert classify("fetch", "fetch", {"url": "http://intranet.bob.local/wiki/onboarding.html"}).action == "r"
    assert classify("fetch", "fetch", {"url": "https://share.external.example/?q=1"}).action == "x"
    assert classify("fetch", "fetch", {"url": "http://corp-git:3000/api/v1/admin/users"}).destinations[0].category == "infrastructure"
    assert classify("fetch", "fetch", {"url": "http://169.254.169.254/latest"}).destinations[0].category == "infrastructure"
    assert classify("fetch", "fetch", {"url": "file:///etc/passwd"}).destinations[0].category == "infrastructure"
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
    args, applied = apply_restrictions(mail, {"recipients": ["a@gmail.com"], "body": "x" * 50}, {"max_chars": 10, "journal_bcc": "c@bob.local"})
    assert len(args["body"]) == 10 and args["bcc"] == ["c@bob.local"] and len(applied) == 2
    print("classify self-check: OK")
