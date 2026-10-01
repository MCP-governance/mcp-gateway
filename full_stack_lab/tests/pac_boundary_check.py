"""Run inside the Gateway image; exercise the deployed capability adapter, not a mock OPA."""
from pathlib import Path
from app import classify, pac, registry


def main():
    person = {"token": "reservation-check", "synthetic": True}
    sql = "UPDATE public.products SET price=price+1 WHERE id=1"
    for query in [sql, *[sql + f" /* slot-{i} */" for i in range(6)]]:
        cls = classify.classify("postgres", "execute_sql", {"sql": query})
        assert pac.scope(person, "postgres", "execute_sql", cls.action, cls.resources, {"sql": query})["allowed"]
    for query in ["UPDATE public.products SET price=0 WHERE id=1", "DELETE FROM public.products", sql + "; DROP TABLE public.products"]:
        cls = classify.classify("postgres", "execute_sql", {"sql": query})
        assert not pac.scope(person, "postgres", "execute_sql", cls.action, cls.resources, {"sql": query})["allowed"]
    cls = classify.classify("postgres", "execute_sql", {"sql": sql})
    assert not pac.scope({"token": "admin-demo", "synthetic": True}, "postgres", "execute_sql", cls.action, cls.resources, {"sql": sql})["allowed"]
    assert not pac.scope({"token": "acceptance-user-employee", "synthetic": False}, "postgres", "execute_sql", "r", [])["allowed"]
    assert not pac.under("/sharedx/file", ["/shared"])
    assert list(pac.leaves({"recipients": ["a@bob.local"], "options": {"command": "x"}})) == [
        (["recipients", 0], "a@bob.local"), (["options", "command"], "x")]
    original = registry.REGISTRY_DIR
    try:
        registry.REGISTRY_DIR = Path("/registry/field")
        field = pac.capabilities()
        assert field["capabilities"] == []
        assert field["execution_profile"]["limits"]["max_concurrency"] == 4
        assert not pac.scope({"token": "root"}, "git", "git_log", "r", [])["allowed"]
    finally:
        registry.REGISTRY_DIR = original
    print("PASS finite SQL capability, no admin/synthetic-name wildcard, path boundary and nested argument coverage")


if __name__ == "__main__":
    main()
