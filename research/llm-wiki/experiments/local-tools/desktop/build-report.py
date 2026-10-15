"""Build the checked-in desktop MCP inventory from task-local protocol captures."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
TASK = REPO / ".task-local-20261014" / "desktop"
ANALYSIS = REPO / "research" / "llm-wiki" / "analysis" / "local-tools"
LOG = TASK / "log"


def load(name: str) -> dict:
    return json.loads((LOG / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def tool_rows(capture: dict, classes: dict[str, list[str]]) -> list[dict]:
    rows = []
    for raw in capture["tools"]:
        rows.append({**raw, "scope": classes[raw["name"]]})
    return rows


blender_capture = load("blender-protocol.json")
playwright_capture = load("playwright-protocol.json")

blender_classes = {
    "get_addon_status": ["read: addon/server status and telemetry setting"],
    "disable_telemetry": ["write: persistent addon telemetry preference"],
    "get_scene_info": ["read: live Blender scene objects and geometry facts"],
    "execute_blender_code": ["execute: arbitrary Python/bpy in Blender process", "read/write: all files, processes, network resources and user data reachable to that process token"],
    "record_trajectory_feedback": ["write: evaluation feedback; telemetry/data egress may occur depending on implementation/configuration"],
    "look": ["read: renders/screenshots of current Blender scene"],
    "generate_3d": ["network: provider/model-dependent generation", "write: imports generated model into scene", "execute: Blender import path"],
    "search_assets": ["network: searches configured external asset catalogs", "read: catalog metadata"],
    "import_asset": ["network: downloads selected asset", "write: imports file into Blender scene", "execute: Blender import path"],
}

playwright_classes = {
    "browser_close": ["write: closes current page"],
    "browser_resize": ["write: changes browser viewport"],
    "browser_console_messages": ["read: page console output"],
    "browser_handle_dialog": ["write: accepts/dismisses page dialog"],
    "browser_emulate_media": ["write: changes page emulation state"],
    "browser_evaluate": ["execute: arbitrary page JavaScript"],
    "browser_file_upload": ["read: arbitrary host file paths", "write: uploads files into page"],
    "browser_drop": ["read: arbitrary host file paths when paths are supplied", "write: injects files/data into page"],
    "browser_find": ["read: accessibility snapshot/text"],
    "browser_fill_form": ["write: changes form fields"],
    "browser_press_key": ["write: keyboard input to page"],
    "browser_type": ["write: text input to page"],
    "browser_navigate": ["network: navigates browser to requested URL", "write: changes page/browser state"],
    "browser_navigate_back": ["network: may request prior page", "write: changes page/browser state"],
    "browser_network_requests": ["read: recorded page network request metadata"],
    "browser_network_request": ["read: recorded request headers/body; may expose page data"],
    "browser_run_code_unsafe": ["execute: arbitrary JavaScript in Playwright server process; upstream describes this as RCE-equivalent"],
    "browser_take_screenshot": ["read: page screenshot"],
    "browser_snapshot": ["read: accessibility tree/page content"],
    "browser_click": ["write: activates page controls"],
    "browser_drag": ["write: drag interaction"],
    "browser_hover": ["write: hover interaction"],
    "browser_select_option": ["write: changes select field"],
    "browser_tabs": ["read/write: lists, creates, closes, or selects browser tabs; URL action may navigate"],
    "browser_wait_for": ["read: waits for page state/text; can change execution timing"],
}

now = datetime.now(timezone.utc).isoformat(timespec="seconds")
blender_repo = TASK / "sources" / "blender-mcp"
playwright_repo = TASK / "sources" / "playwright-mcp"
blender_addon = blender_repo / "src" / "blender_mcp" / "bundled" / "addon.py"
blender_server = blender_repo / "src" / "blender_mcp" / "server.py"
blender_wheel = TASK / "app" / "mcp_for_blender-2.1.9-py3-none-any.whl"
playwright_lock = TASK / "app" / "playwright" / "package-lock.json"
blender_manifest = TASK / "app" / "blender-5.2.2.sha256"
python_lock = HERE / "blender-requirements.lock"

report = {
    "category": "desktop-and-browser-local-mcp",
    "date": "2026-10-14",
    "generated_at_utc": now,
    "timezone": "Asia/Seoul",
    "results": [
        {
            "id": "blender",
            "app": {"name": "Blender", "version": "5.2.2 LTS", "distribution": "official portable ZIP", "license": "GPL-3.0-or-later", "path": ".task-local-20261014/desktop/app/blender/blender-5.2.2-windows-x64/blender.exe", "sha256": sha256(TASK / "app" / "blender-5.2.2-windows-x64.zip"), "official_hash_manifest": "https://download.blender.org/release/Blender5.2/blender-5.2.2.sha256"},
            "mcp": {"name": "mcp-for-blender", "version": "2.1.9", "server_reported_version": blender_capture.get("server_version"), "repository": "https://github.com/ahujasid/blender-mcp", "commit": "7a0373ec9199183cb460068c4f96aed9c579fb4f", "commit_date": "2026-10-06T20:37:57+05:30", "license": "MIT", "wheel_sha256": sha256(blender_wheel), "addon_source_sha256": sha256(blender_addon), "server_source_sha256": sha256(blender_server), "python_dependency_lock": {"path": "research/llm-wiki/experiments/local-tools/desktop/blender-requirements.lock", "sha256": sha256(python_lock)}, "tool_count": len(blender_capture["tools"]), "tools": tool_rows(blender_capture, blender_classes), "raw_protocol_capture": ".task-local-20261014/desktop/log/blender-protocol.json", "initialize_result": blender_capture.get("initialize_result"), "handshake": "Actual MCP initialize result captured from the SDK request; tools/list returned 9 tools.", "calls": {"get_addon_status": blender_capture["calls"]["get_addon_status"], "get_scene_info": blender_capture["calls"]["get_scene_info_before"], "execute_blender_code_synthetic_write": blender_capture["calls"]["execute_blender_code_synthetic_write"], "get_scene_info_after": blender_capture["calls"]["get_scene_info_after"]}, "telemetry": {"server_environment": blender_capture["telemetry_environment"], "addon_telemetry_consent_returned_by_get_addon_status": False, "boot_log": ".task-local-20261014/desktop/log/blender-boot.log", "startup_no_update_check": "BLENDERMCP_NO_UPDATE_CHECK=1", "source_evidence": "telemetry.py recognizes BLENDER_MCP_DISABLE_TELEMETRY and DISABLE_TELEMETRY; addon reads its persisted telemetry_consent setting. Actual get_addon_status returned telemetry_consent=false; boot log recorded telemetry_consent=False."}, "bridge": {"transport": "MCP stdio process to TCP socket bridge inside Blender", "observed_bind": "127.0.0.1:9876", "observed_process_id": 5388, "authentication": "none", "encryption": "none", "origin_check": "none for raw TCP bridge", "allowed_call_surface": "bridge supports execute_code; Python exec is not sandboxed on this socket", "mcp_server_safe_mode": "BLENDER_MCP_SAFE_MODE=1 enabled for tested MCP execution route only; does not constrain direct access to Blender socket", "observed_listener": "Get-NetTCPConnection reported 127.0.0.1:9876 only; listener stopped after validation"}, "external_requirements": {"basic_local_tools": "no model or external API key needed", "optional_integrations": "asset catalogs / generation providers disabled in observed status; those tools may require network, provider keys or paid Premium services"}, "validation": {"result": "success", "captured_at_utc": blender_capture["captured_at_utc"], "read": "factory-startup scene info read succeeded", "write": "synthetic sphere created through execute_blender_code; scene contained 1 mesh before and 2 meshes after and the follow-up query found it; unsaved factory-startup instance was stopped", "exact_commands": ["& .\\research\\llm-wiki\\experiments\\local-tools\\desktop\\start-blender.ps1", "node .\\research\\llm-wiki\\experiments\\local-tools\\desktop\\run-blender-mcp.mjs", "& .\\research\\llm-wiki\\experiments\\local-tools\\desktop\\stop-blender.ps1"]}},
        },
        {
            "id": "playwright-chromium",
            "app": {"name": "Playwright bundled Chromium", "version": "155.0.8059.12", "distribution": "task-local Playwright browser install", "path": ".task-local-20261014/desktop/app/browsers", "license": "Chromium open-source licenses; see bundled NOTICE files"},
            "mcp": {"name": "@playwright/mcp", "version": "0.0.83", "server_reported_version": playwright_capture.get("initialize_server_info"), "repository": "https://github.com/microsoft/playwright-mcp", "commit": "b8b4183e099f136cbec0388a6088d4aa2f6b9685", "commit_date": "2026-10-08T10:51:55-07:00", "license": "Apache-2.0", "sdk_version": "@modelcontextprotocol/sdk 1.25.2", "package_lock_sha256": sha256(playwright_lock), "package_json_sha256": sha256(playwright_repo / "package.json"), "readme_sha256": sha256(playwright_repo / "README.md"), "tool_count": len(playwright_capture["tools"]), "tools": tool_rows(playwright_capture, playwright_classes), "raw_protocol_capture": ".task-local-20261014/desktop/log/playwright-protocol.json", "initialize_result": playwright_capture.get("initialize_result"), "handshake": "Actual MCP initialize result captured from the SDK request; tools/list returned 25 tools.", "calls": {"browser_navigate": playwright_capture["calls"]["browser_navigate"], "browser_snapshot": playwright_capture["calls"]["browser_snapshot"]}, "validation": {"result": "success", "captured_at_utc": playwright_capture["captured_at_utc"], "fixture": "research/llm-wiki/experiments/local-tools/desktop/fixtures/local-read.html", "url": playwright_capture["local_fixture_url"], "profile": ".task-local-20261014/desktop/app/playwright-profile", "headless": True, "allowed_origin": "exact random-port loopback origin for the fixture", "read": "browser_navigate and browser_snapshot succeeded; synthetic Korean page content observed", "network": "loopback-only fixture server for this test; no existing browser profile/session was opened", "exact_command": "node .\\research\\llm-wiki\\experiments\\local-tools\\desktop\\run-playwright-mcp.mjs"}, "security": {"mcp_transport": "stdio; server exposes no MCP HTTP listener", "allowed_origins": "constrains browser requests only as documented; not a security boundary and redirects are not constrained", "arbitrary_code": "browser_evaluate executes page JS; browser_run_code_unsafe executes arbitrary JS in the MCP server process and is RCE-equivalent per upstream README", "filesystem": "browser_file_upload and browser_drop can read arbitrary user-provided local paths and transmit them to page; task test did not call them", "network": "browser_navigate and page execution can reach network targets beyond the fixture; use an isolated profile and narrow client policy"}},
        },
        {
            "id": "burp-community-official-mcp-candidate",
            "app": {"name": "Burp Suite Community Edition", "type": "commercial free edition", "version": "2026.9.2", "distribution": "official standalone Java JAR", "task_local_path": ".task-local-20261014/desktop/app/burp/burp-desktop-2026.9.2.jar", "sha256": "3571F8CADBFD65B0B090D2753735C40B76AD7FDDE0B927DF2B22EC46EA09693A", "bytes": 739336590, "acquisition": "complete; SHA-256 matches official PortSwigger release-page value", "installation": "portable JAR and JRE stored under task-local ignored directory; no global install or Burp application session started", "jre": "Temurin 21.0.12.1+1 task-local ZIP and extracted runtime", "cli_check": "`java -Djava.awt.headless=true -jar <jar> --help` succeeded and printed this build's supported CLI arguments", "artifact_acquired": True, "application_session_started": False},
            "mcp": {"name": "PortSwigger MCP Server BApp", "version": "1.3.0", "repository": "https://github.com/PortSwigger/mcp-server", "commit": "5f76126409780ecba2b766c7f7388f465c5b5f94", "license": "GPL-3.0", "app_compatibility": "official BApp metadata says ProOnly=false and SupportedProducts=Pro, Community", "artifact": {"download_url": "https://portswigger.net/bappstore/bapps/download/9952290f04ed4f628e624d0aa9dccebc/10", "task_local_path": ".task-local-20261014/desktop/permissions/originals/mcp-server-bapp-1.3.0.jar", "sha256": "4D675B10796FF51D440C5A40F3855A3D38A1666A91A0B28FB8853A26ABD5B2C5"}, "connection_test": "not run: the exact Burp user-config representation to load/enable this BApp was not source-verified. CLI supports --user-config-file/--project-file, but official docs recommend generating JSON through Burp; the BApp MCP tab's enable toggle and persisted extension settings were not activated. Native GUI control is unavailable here; no browser/certificate/proxy settings were changed.", "safe_manual_start_draft": {"shell": "PowerShell", "variables": {"jar": ".task-local-20261014/desktop/app/burp/burp-desktop-2026.9.2.jar", "java": ".task-local-20261014/desktop/app/burp/jre/jdk-21.0.12.1+1-jre/bin/java.exe", "data_dir": ".task-local-20261014/desktop/app/burp-data", "synthetic_project": ".task-local-20261014/desktop/app/burp-project.burp"}, "command": "& $java '-jar' $jar '--data-dir' $dataDir '--project-file' $projectFile", "not_run_reason": "Opens the application UI; extension/BApp configuration must be generated via Burp before a valid `--user-config-file` can be supplied."}, "intended_safe_test": "loopback synthetic project only; built-in encoding tool; do not invoke HTTP request, proxy history, Collaborator, scan, or user-data tools", "documented_transports": ["stdio packaged proxy", "SSE at http://127.0.0.1:9876"], "DAST_separate": "PortSwigger DAST MCP is a separate product and its licensed DAST/API-key prerequisite does not apply to this desktop BApp.", "security_defaults_from_pinned_source": {"host": "127.0.0.1", "port": 9876, "requireHttpRequestApproval": True, "requireDataAccessApproval": True, "configEditingTooling": False, "autoApproveTargets": "empty", "filterConfigCredentials": True, "authentication": "no MCP bearer authentication in extension source. Host/Origin/Referer checks reject disallowed browser origins and non-loopback hosts, but an Origin-less non-browser MCP client is not authenticated by those checks.", "default_enabled": True}},
        },
    ],
    "sources": [
        {"url": "https://github.com/ahujasid/blender-mcp/tree/7a0373ec9199183cb460068c4f96aed9c579fb4f", "kind": "pinned OSS source", "license": "MIT", "commit": "7a0373ec9199183cb460068c4f96aed9c579fb4f"},
        {"url": "https://pypi.org/project/mcp-for-blender/2.1.9/", "kind": "published wheel used because pinned Git tree omits gitignored config.py needed by telemetry import", "wheel_sha256": sha256(blender_wheel)},
        {"url": "https://github.com/microsoft/playwright-mcp/tree/b8b4183e099f136cbec0388a6088d4aa2f6b9685", "kind": "pinned OSS source", "license": "Apache-2.0", "commit": "b8b4183e099f136cbec0388a6088d4aa2f6b9685"},
        {"url": "https://portswigger.net/bappstore/9952290f04ed4f628e624d0aa9dccebc", "kind": "official BApp metadata: version 1.3.0, Community supported, ProOnly false, stdio/SSE transports"},
        {"url": "https://github.com/PortSwigger/mcp-server/tree/5f76126409780ecba2b766c7f7388f465c5b5f94", "kind": "pinned official PortSwigger MCP BApp source, GPL-3.0"},
        {"url": "https://portswigger.net/burp/documentation/desktop/troubleshooting/launch-from-command-line", "kind": "official CLI docs: --user-config-file and --config-file; headless flag, but no documented CLI argument to enable an installed BApp"},
        {"url": "https://portswigger.net/burp/documentation/desktop/settings/extensions", "kind": "official docs for extension loading/reloading behavior; startup configuration is UI/user settings"},
        {"url": "https://portswigger.net/burp/documentation/dast/user-guide/using-ai/mcp-server", "kind": "official DAST MCP docs; separate product and prerequisite, not desktop BApp compatibility"},
        {"url": "https://portswigger.net/burp/documentation/desktop/settings/suite/rest-api", "kind": "official desktop REST API docs; API is not MCP"},
        {"url": "https://portswigger.net/burp/communitydownload", "kind": "official Community edition download/feature scope"},
    ],
    "limitations": [
        "Only local, synthetic data was used. Both live app processes were stopped after validation.",
        "Blender raw TCP bridge is unauthenticated and allows arbitrary Python via execute_code. Loopback binding limits remote reachability, not other local processes or browser/agent processes.",
        "Blender server safe mode was enabled for its MCP execute route; it is not a substitute for socket isolation because the addon socket has an unrestricted execute_code command.",
        "Playwright allowed-origins does not constrain redirects or make browser tool calls safe; browser_run_code_unsafe is server-process arbitrary code execution and upload/drop tools can read selected local files.",
        "Optional Blender asset/generation functions are not proven local/offline; they were disabled and not invoked. Paid provider/Premium features were not installed or tested.",
        "MCP protocol version is not reported because the client transport did not expose it. Client initialize success and server-reported package versions are recorded separately.",
        "Official PortSwigger desktop BApp compatibility with Community is established from the official BApp metadata/source, but the Burp desktop JAR transfer stalled and the BApp was not loaded or called; no actual Burp connection is claimed. The 705 MiB app artifact remains a partial task-local file.",
    ],
}

ANALYSIS.mkdir(parents=True, exist_ok=True)
(ANALYSIS / "desktop.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

md = f'''# Local desktop and browser MCP candidates

Research date: 2026-10-14 (Asia/Seoul). Both successful test routes used task-local app state and synthetic/local content. The successful protocol captures retain the exact input/output JSON schemas returned by the servers in the canonical JSON `results[*].mcp.tools` entries; raw unmodified captures are under ignored task-local logs.

## Blender + mcp-for-blender

Installed official portable Blender 5.2.2 LTS and the MIT-licensed public project [`ahujasid/blender-mcp`](https://github.com/ahujasid/blender-mcp/tree/7a0373ec9199183cb460068c4f96aed9c579fb4f) at immutable commit `7a0373ec9199183cb460068c4f96aed9c579fb4f`. The MCP package was `mcp-for-blender 2.1.9` (official [PyPI release](https://pypi.org/project/mcp-for-blender/2.1.9/)); the package wheel SHA-256 is `{sha256(blender_wheel)}`. The upstream Git tree at that commit omits a gitignored `config.py` that the telemetry import requires, so the published wheel was used for the server and the addon itself was installed from the pinned repository source. The Blender ZIP SHA-256 `{sha256(TASK / 'app' / 'blender-5.2.2-windows-x64.zip')}` matches the [official release hash manifest](https://download.blender.org/release/Blender5.2/blender-5.2.2.sha256). Blender is under `.task-local-20261014/desktop/app/blender/`.

The MCP SDK client completed `initialize`; `tools/list` returned 9 real tools; `get_addon_status` and `get_scene_info` succeeded. A synthetic sphere was created through `execute_blender_code`, then found in a follow-up scene read. The factory-startup Blender instance was stopped without saving. Actual response bodies and exact server schemas are in [desktop.json](desktop.json) and `.task-local-20261014/desktop/log/blender-protocol.json`.

Telemetry is disabled at both ends: environment `BLENDERMCP_DISABLE_TELEMETRY=1` and `DISABLE_TELEMETRY=1` set in the server process; startup code sets `telemetry_consent=False`; the boot log records `telemetry_consent=False`; and the actual `get_addon_status` tool response returned `telemetry_consent: false`. `BLENDERMCP_NO_UPDATE_CHECK=1` disables the add-on's update check. The basic local scene tools need no model or API key. Asset search/import and 3D generation can make external requests; these integrations were off in the live status response and were not exercised. Provider or paid Premium requirements are separate from local scene control.

The real app bridge is a raw TCP listener observed on `127.0.0.1:9876`, with no authentication, encryption, or origin check. `execute_code` reaches Python `exec` in the Blender process. The MCP server's `BLENDER_MCP_SAFE_MODE=1` restricts calls made through that MCP server route; it does **not** restrict a process that directly connects to the add-on's raw socket. Loopback binding prevents direct remote network connections, but any local process can still attempt to connect. Consider this an arbitrary local code execution bridge, not a sandbox.

## Microsoft Playwright MCP + isolated Chromium

Installed [`microsoft/playwright-mcp`](https://github.com/microsoft/playwright-mcp/tree/b8b4183e099f136cbec0388a6088d4aa2f6b9685), commit `b8b4183e099f136cbec0388a6088d4aa2f6b9685`, Apache-2.0, package `@playwright/mcp 0.0.83`, plus task-local `@modelcontextprotocol/sdk 1.25.2`. `package-lock.json` SHA-256: `{sha256(playwright_lock)}`; package manifest: `{sha256(playwright_repo / 'package.json')}`; upstream README: `{sha256(playwright_repo / 'README.md')}`. Browser `Chromium 155.0.8059.12` was installed under `.task-local-20261014/desktop/app/browsers/`. No existing browser profile or login was used.

The captured `initialize` reply advertises protocol version `2025-11-25`, server `Playwright 1.64.0-alpha-1790635538000`; package version is `@playwright/mcp 0.0.83` and browser is Chromium `155.0.8059.12`. `tools/list` returned 25 tools. Actual `browser_navigate` and `browser_snapshot` calls read a synthetic Korean HTML page served on a random `127.0.0.1` port; Chromium ran headless with a task-local user-data-dir. The server used stdio, not a network MCP endpoint. The exact request/response records and schemas are in [desktop.json](desktop.json) and `.task-local-20261014/desktop/log/playwright-protocol.json`.

The tools include page reads, UI writes, arbitrary page JavaScript (`browser_evaluate`), and `browser_run_code_unsafe`. Upstream describes the latter as arbitrary JavaScript in the MCP server process and RCE-equivalent. `browser_file_upload`/`browser_drop` can read user-specified host paths and transmit contents into a page. `--allowed-origins` helps reject cross-origin browser requests but is not a security boundary and redirects are not constrained per the [upstream README](https://github.com/microsoft/playwright-mcp/tree/b8b4183e099f136cbec0388a6088d4aa2f6b9685). Use a task-isolated profile and constrain the client’s reachable URLs/files/tools.

## Commercial free edition: Burp Community + official PortSwigger MCP BApp

PortSwigger's official [MCP Server BApp page](https://portswigger.net/bappstore/9952290f04ed4f628e624d0aa9dccebc) lists both Professional and Community, says `ProOnly: False`, and describes a packaged stdio proxy and loopback SSE mode. The official [BApp source](https://github.com/PortSwigger/mcp-server/tree/5f76126409780ecba2b766c7f7388f465c5b5f94) is GPL-3.0 at immutable release commit `5f76126409780ecba2b766c7f7388f465c5b5f94`; its manifest names Community support. BApp binary 1.3.0 was downloaded to the ignored task-local originals folder (SHA-256 `4D675B10796FF51D440C5A40F3855A3D38A1666A91A0B28FB8853A26ABD5B2C5`). The official Community 2026.9.2 JAR is now fully downloaded task-locally (739,336,590 bytes; SHA-256 `3571F8CADBFD65B0B090D2753735C40B76AD7FDDE0B927DF2B22EC46EA09693A`) and its headless `--help` output was checked. This corrects the earlier mistaken assumption that only the separate DAST MCP could be official.

**Burp desktop and extension were not started or connected.** The official Community 2026.9.2 JAR and BApp artifacts are both present in task-local ignored storage. The JAR's `--help` output confirms this build supports `--data-dir`, `--project-file`, and `--user-config-file`; however, no exact user-config JSON encoding for loading/enabling this extension was source-verified. Official settings documentation recommends exporting the desired JSON from Burp, and BApp startup/server enablement is persisted extension state. No UI automation or browser/proxy/certificate/user profile configuration was changed. The recorded PowerShell launch draft is `& $java '-jar' $jar '--data-dir' $dataDir '--project-file' $projectFile`, with `$java`, `$jar`, `$dataDir`, and `$projectFile` resolving to the task-local paths recorded in desktop.json. This opens the UI; use the Burp Extensions UI to load only the official BApp JAR and its MCP tab to retain both approval requirements, leave auto-approve targets blank and config-editing disabled, and bind only `127.0.0.1`. Then call only the built-in URL/base64 encoding tool against a synthetic local string. Never send HTTP requests, inspect existing proxy history, scan, or use Collaborator for this validation.

This BApp is different from PortSwigger's [Burp Suite DAST MCP server](https://portswigger.net/burp/documentation/dast/user-guide/using-ai/mcp-server), whose DAST license/API-user/API-key requirement applies to the DAST product, not the desktop BApp. The desktop REST API is another separate interface.

## Reproduction

Task-local runtime, source checkouts, and captures are intentionally ignored by Git. Python version pins are tracked in `experiments/local-tools/desktop/blender-requirements.lock`; exact npm pins/integrity are in the task-local package-lock (SHA-256 is in desktop.json). From the repository root after preparing those pinned artifacts:

```powershell
& .\\research\\llm-wiki\\experiments\\local-tools\\desktop\\start-blender.ps1
node .\\research\\llm-wiki\\experiments\\local-tools\\desktop\\run-blender-mcp.mjs
& .\\research\\llm-wiki\\experiments\\local-tools\\desktop\\stop-blender.ps1
node .\\research\\llm-wiki\\experiments\\local-tools\\desktop\\run-playwright-mcp.mjs
python -X utf8 .\\research\\llm-wiki\\experiments\\local-tools\\desktop\\build-report.py
```

`start-blender.ps1` copies the tracked `blender_boot.py` into the task-local profile, refuses to reuse port 9876, sets telemetry/update-check environment flags, and launches the portable Blender hidden with `--factory-startup`. The Playwright runner creates its own random-port loopback fixture server, uses headless Chromium and a task-local profile, then closes both. The Playwright runner creates its own random-port loopback fixture server, uses headless Chromium and a task-local profile, then closes both.
'''
(ANALYSIS / "desktop.md").write_text(md, encoding="utf-8")
print(f"Wrote {ANALYSIS / 'desktop.json'} and {ANALYSIS / 'desktop.md'}")
