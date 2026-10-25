<div align="center">

<img src="docs/assets/mint-logo.svg" width="84" alt="MINT">

# MINT

**MCP Governance Gateway**

[한국어](README.md) · **English**

[![Verify](https://github.com/MCP-governance/mcp-gateway/actions/workflows/verify.yml/badge.svg?branch=main)](https://github.com/MCP-governance/mcp-gateway/actions/workflows/verify.yml)
[![CodeQL](https://github.com/MCP-governance/mcp-gateway/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/MCP-governance/mcp-gateway/actions/workflows/codeql.yml)
![Version](https://img.shields.io/badge/version-0.9.0-1f4287)
![MCP](https://img.shields.io/badge/MCP-2025--11--25-1f4287)
![Docker](https://img.shields.io/badge/deploy-Docker%20Compose-2496ED?logo=docker&logoColor=white)

</div>

MINT limits the MCP servers that AI coding agents on employee PCs (Claude Code, Codex CLI) can use to the ones the company approved, and judges every
tool call at a single gateway **before it runs**. An employee requests an MCP server, it goes through supply-chain checks, and a different administrator approves it.
Each call is checked for identity, tool classification, input inspection, policy and consent; personal and secret data are masked in the response, and every
decision is appended to an append-only audit ledger. The endpoint kit deploys managed harness settings so that only the approved path is used, and when a
relationship ends MINT blocks it immediately and judges, from evidence, whether access was actually revoked.

<p align="center">
  <img src="docs/ai/architecture/mint-architecture-en.png" alt="MINT architecture" width="100%">
</p>

<p align="center"><sub>Annotated version: <a href="docs/ai/architecture/mint-architecture-roles-en.png">architecture (roles)</a> · editable source: <a href="docs/ai/architecture/mint-architecture-en.drawio">draw.io</a></sub></p>

## Support

| Harness | Status |
| --- | --- |
| Claude Code | Supported |
| Codex CLI | Supported |
| Gemini CLI · OpenCode | Tested in the lab stack |

| Employee PC | Install | Status |
| --- | --- | --- |
| Linux (Ubuntu 20.04–26.04) | One command, one sudo | Supported |
| Windows 11 | One file, one UAC prompt | Supported |
| macOS | One command | Preview |

| Server | Requirements |
| --- | --- |
| Gateway server | Linux x86_64, Docker Engine 24+, Docker Compose v2 |

## Five-minute install

```bash
git clone --branch v0.9.0 https://github.com/MCP-governance/mcp-gateway.git
cd mcp-gateway/deploy
./install.sh --bind <internal IPv4>
```

Then sign in at `https://<internal IPv4>/` as the administrator `root`. The initial password is in `deploy/initial-admin-password`;
change it with `./mint.sh set-password root`. Requirements, components and options are in [deploy/README.md](deploy/README.md) (Korean).

## Connecting employee PCs

1. The employee signs in to the console and downloads the kit for their OS from **Connect my PC**.
2. They run it (one command on Linux and macOS, one file on Windows). The kit carries the gateway address, root certificate and fingerprint.
3. Once an administrator activates the endpoint under **Users & endpoints**, the approved MCP servers appear in the harness. The first use asks for per-server consent.

What the kit installs, how to remove it and troubleshooting are in the [endpoint kit](endpoint-agent/README.md) guide.

## Operations

| Task | Where |
| --- | --- |
| MCP requests and approval | Console **Onboarding requests**, **Pending approval** |
| Audience, suspension and revocation of approved servers | Console **MCP servers** |
| Endpoint activation and control status | Console **Users & endpoints**, **Control coverage** |
| Decisions, consent and audit | Console **Tool call log**, **Usage consent**, **Audit log** |
| Accounts and passwords | `./mint.sh add-account`, `./mint.sh set-password` |
| Backup, restore, upgrade, rollback | `./mint.sh backup`·`restore`·`upgrade` — [runbook](docs/ai/RUNBOOK.md) (Korean) |
| Changes per version | [CHANGELOG.md](CHANGELOG.md) (Korean) |

## Security boundaries

- **Identity comes only from the transport token.** Identities in arguments, headers or client reports are recorded, never used for decisions.
- **Employee tokens are never passed to upstream MCP servers.** The gateway holds per-server credentials, and credentials employees connect are encrypted with an organization key.
- **If it cannot decide, it blocks.** A failed policy engine, inspector or contract check, or an unknown classification, means deny.
- **The gateway controls only the calls on its path.** Unmanaged accounts, PCs without the kit and vendor built-in connectors belong to endpoint, network and vendor management; the console shows their control status.
- **Termination verdicts are judgments from public evidence,** not verification of the provider's actual revocation.

The detailed threat model and limits are in [security boundaries](docs/ai/SECURITY_BOUNDARIES.md) (Korean).

## Development and contributing

- Design: [ARCHITECTURE](docs/ai/ARCHITECTURE.md) · decisions: [DECISIONS](docs/ai/DECISIONS.md) · document map: [docs/ai](docs/ai/README.md)
- Lab and verification stack (synthetic company, four employee PCs, ten MCP servers): [full_stack_lab/](full_stack_lab/README.md)
- Development status, work reports and experiment evidence: [research/llm-wiki/](research/llm-wiki/README.md)
- Contribution rules and invariants: [AGENTS.md](AGENTS.md). Work on a branch per task and add user-visible changes under "미배포" (Unreleased) in `CHANGELOG.md`.
- Every commit must pass CI: static checks, secret scan, full lab verification and the production install check.

## License

No open-source license has been chosen for this repository yet. It may not be copied, distributed or modified without the copyright holder's permission.
Bundled third-party components (OPA, Presidio, Caddy, Gitea, PostgreSQL and others) are under their own licenses.
