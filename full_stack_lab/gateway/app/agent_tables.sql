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

-- Applied on every boot so existing volumes get them too. Audit lookups are by
-- request id or by user over a time window; without these both are seq scans.
CREATE INDEX IF NOT EXISTS decisions_request_idx ON decisions(request_id);
CREATE INDEX IF NOT EXISTS decisions_user_time_idx ON decisions(user_token, created_at DESC);
CREATE INDEX IF NOT EXISTS catalog_snapshots_server_idx ON catalog_snapshots(server_id, id DESC);
CREATE INDEX IF NOT EXISTS supply_chain_source_idx ON supply_chain_reports(source_ref, scanner, id DESC);
