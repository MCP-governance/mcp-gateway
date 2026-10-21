SELECT pg_advisory_xact_lock(721017120);

-- NULL in historical snapshots means the impact was not bounded.
ALTER TABLE catalog_snapshots ADD COLUMN IF NOT EXISTS restricted_tools text[];

CREATE TABLE IF NOT EXISTS runtime_image_scans (
  id bigserial PRIMARY KEY,
  runtime_id uuid NOT NULL REFERENCES mcp_runtimes(id),
  image_id text NOT NULL,
  checked_at timestamptz NOT NULL DEFAULT now(),
  result jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS runtime_image_scans_image ON runtime_image_scans(image_id, id DESC);

CREATE TABLE IF NOT EXISTS ops_suspensions (
  id bigserial PRIMARY KEY,
  server_id text NOT NULL REFERENCES mcp_servers(id),
  source text NOT NULL,
  reason text NOT NULL,
  evidence jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  resumed_at timestamptz,
  resumed_by text,
  resume_note text
);
CREATE UNIQUE INDEX IF NOT EXISTS ops_suspensions_active ON ops_suspensions(server_id) WHERE resumed_at IS NULL;

-- An administrator stops one employee's use of one MCP server; the console account stays. The row is
-- state (resuming fills the resume columns); who did it and when is the approval_events record
-- written in the same transaction.
CREATE TABLE IF NOT EXISTS user_server_suspensions (
  id bigserial PRIMARY KEY,
  user_token text NOT NULL,
  server_id text NOT NULL REFERENCES mcp_servers(id),
  reason text NOT NULL,
  suspended_by text NOT NULL,
  suspended_at timestamptz NOT NULL DEFAULT now(),
  resumed_at timestamptz,
  resumed_by text,
  resume_note text
);
CREATE UNIQUE INDEX IF NOT EXISTS user_server_suspensions_active
  ON user_server_suspensions(user_token, server_id) WHERE resumed_at IS NULL;
ALTER TABLE user_server_suspensions ADD COLUMN IF NOT EXISTS expires_at timestamptz;

CREATE TABLE IF NOT EXISTS alert_self_tests (
  id bigserial PRIMARY KEY,
  policy_hash text NOT NULL,
  synthetic boolean NOT NULL DEFAULT true CHECK (synthetic),
  passed boolean NOT NULL,
  results jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops_alerts (
  id bigserial PRIMARY KEY,
  kind text NOT NULL,
  origin text NOT NULL,
  origin_id text NOT NULL,
  synthetic boolean NOT NULL,
  evidence jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (kind,origin,origin_id,synthetic)
);

CREATE TABLE IF NOT EXISTS disposal_blocks (
  kind text NOT NULL,
  subject text NOT NULL,
  server_id text NOT NULL DEFAULT '',
  detail jsonb NOT NULL,
  PRIMARY KEY (kind, subject, server_id)
);
