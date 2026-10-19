"""Contract impact is bounded by reviewed tool names; unknown evidence blocks the server."""


def restricted_tools(findings):
    restricted = set()
    if not isinstance(findings, list):
        return None
    for item in findings:
        if not isinstance(item, dict):
            return None
        kind = item.get("type")
        if kind == "contract-drift":
            fields = item.get("fields")
            if (not isinstance(item.get("tool"), str) or not isinstance(fields, list)
                    or not fields or any(f not in {"description", "schema", "output_schema", "version"} for f in fields)
                    or not isinstance(item.get("enabled"), bool)):
                return None
            if item["enabled"] and any(f != "version" for f in fields):
                restricted.add(item["tool"])
        elif kind in {"enabled-tool-missing", "unsafe-description"}:
            tools = item.get("tools")
            if not isinstance(tools, (list, dict)) or not tools or any(not isinstance(t, str) or not t for t in tools):
                return None
            restricted.update(tools)
        elif kind not in {"tool-set-drift", "version-carried"}:
            return None
    return sorted(restricted)


def available(snapshot, tool):
    if not snapshot:
        return False
    scope = snapshot.get("restricted_tools")
    return bool(snapshot.get("exact_match") or (isinstance(scope, list) and tool not in scope))
