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
