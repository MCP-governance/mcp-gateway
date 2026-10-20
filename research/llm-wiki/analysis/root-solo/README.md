# Root solo mode review evidence

## Decision

The source commit attempted to satisfy required approver counts by replacing the observed count with the tier's configured count whenever root solo mode was enabled. That bypassed a distinct second approver. The reviewed branch removes that count substitution. The mode is now recorded as context, not authorization.

## Approval truth table

| Tier | Actual approvers | Reason | Result |
| --- | ---: | --- | --- |
| High | 1 | absent | Pending second approver |
| High | 1 | written | Approved under existing D-143 alternative |
| Very high | 1 | written | Pending distinct second approver |
| Very high | 2 distinct people | written | Approved |

The handler calls `review.require_independent` before risk approval. That function compares principal and resolved user IDs, records a refusal event for self-approval, then raises `NotIndependent`. The root solo flag is not referenced by this guard.

## Mode, ledger, and display

`ROOT_SOLO_APPROVAL` is enabled only for the exact value `1`; field compose defaults it on and lab compose leaves it unset/off. Each completed approval stores `solo_mode` (the configuration state) and `solo_operator` (root admin used while enabled) in risk evidence and the `intake-approve` ledger scope. Cosign ledger rows carry the same fields. The registration projection exposes the mode, and the console displays `단독 운영`, `일반 운영`, or `—` for legacy evidence.

The environment transition itself is not recorded. Approval events show the setting when an approval/cosign event occurs; they cannot prove when an unused configuration value changed.

## Account creation secret path

`field_add_account` uses silent terminal input twice, sends the password only over stdin to `docker compose exec`, and stores `crypt(..., gen_salt('bf', 12))`. Password is absent from command arguments, printed output, environment, and config. Username-derived principal IDs are persisted as DB identity keys; the command does not create or print a bearer session token. No real DB or login was exercised.

## Sources read

- `research/llm-wiki/analysis/review-1020/d175-arbitration.md`: DEV-73 rejection maintained; D-175 unchanged.
- `docs/ai/SECURITY_BOUNDARIES.md` sections 4 and 5: trust boundaries and separate approval/control roles.
- `full_stack_lab/gateway/app/risk_tier.py`: high requires two approvers or written reason; very high requires two and a written reason.
- `full_stack_lab/gateway/app/review.py`: self-approval and same-person guard.
- `full_stack_lab/gateway/app/agent_service.py`: approval route, risk gate, append-only event scopes.

## Limits

Local source and regression evidence only. No live stack, device, managed harness, account creation, upstream effect, or GitHub latest-ref verification was performed. The shared checkout `.git` was read-only and GitHub fetch was network-blocked; branch work is in `worktrees/root-solo-main` based on local `origin/main` snapshot `d3238dccd6a6fb7266a7b9201f5b133e2a025aea`.
