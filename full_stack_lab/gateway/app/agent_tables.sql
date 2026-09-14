CREATE TABLE IF NOT EXISTS agent_sessions (
  id uuid PRIMARY KEY, user_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS agent_runs (
  id uuid PRIMARY KEY, session_id uuid NOT NULL REFERENCES agent_sessions(id), user_id text NOT NULL,
  fingerprint text NOT NULL, status text NOT NULL DEFAULT 'RUNNING', message text NOT NULL,
  response jsonb, created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS agent_runs_session_idx ON agent_runs(session_id, created_at);
CREATE TABLE IF NOT EXISTS agent_gateway_receipts (
  id uuid PRIMARY KEY, user_id text NOT NULL, fingerprint text NOT NULL,
  response jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS agent_revoked_tokens (
  jti uuid PRIMARY KEY, expires_at timestamptz NOT NULL
);

-- Tamper-evident audit. Each decision carries the hash of the previous one, so an
-- edited or deleted row breaks the chain at a point anyone can find. The single
-- chain row is what serialises appends.
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS prev_sha256 text;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS entry_sha256 text;
CREATE TABLE IF NOT EXISTS audit_chain (
  id integer PRIMARY KEY CHECK (id = 1),
  head_sha256 text NOT NULL,
  entries bigint NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO audit_chain(id, head_sha256) VALUES (1, repeat('0', 64)) ON CONFLICT (id) DO NOTHING;

-- Defence in depth, not a boundary: the owner can re-grant. It stops the ordinary
-- "just fix that row" edit and states the intent in the schema itself.
DO $$ BEGIN
  EXECUTE 'REVOKE UPDATE, DELETE ON decisions FROM ' || quote_ident(current_user);
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'decisions append-only grant not applied: %', SQLERRM;
END $$;

-- Observation mode. A decision records what was enforced and, when the gateway is
-- only observing, what enforcement would have done instead.
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS enforcement text NOT NULL DEFAULT 'enforce';
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS would_decision text;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS would_policy_id text;
-- Rows hashed before a column existed were hashed over a smaller column set, so the
-- chain records which set it used instead of retroactively invalidating itself.
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS chain_version integer NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS gateway_settings (
  key text PRIMARY KEY,
  value text NOT NULL,
  updated_by text,
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Applied on every boot so existing volumes get them too. Audit lookups are by
-- request id or by user over a time window; without these both are seq scans.
CREATE INDEX IF NOT EXISTS decisions_request_idx ON decisions(request_id);
CREATE INDEX IF NOT EXISTS decisions_user_time_idx ON decisions(user_token, created_at DESC);
CREATE INDEX IF NOT EXISTS catalog_snapshots_server_idx ON catalog_snapshots(server_id, id DESC);
CREATE INDEX IF NOT EXISTS supply_chain_source_idx ON supply_chain_reports(source_ref, scanner, id DESC);
