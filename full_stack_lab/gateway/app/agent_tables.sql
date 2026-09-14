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

-- A repository URL is an intake record, never an instruction to fetch or run
-- somebody else's code. It stays outside the active MCP registry until a
-- reviewer attaches evidence from an isolated checkout.
CREATE TABLE IF NOT EXISTS mcp_intake_requests (
  id uuid PRIMARY KEY,
  submitted_by text NOT NULL,
  display_name text NOT NULL,
  repository_url text NOT NULL,
  requested_transport text NOT NULL CHECK (requested_transport IN ('streamable-http', 'stdio', 'sse')),
  purpose text NOT NULL,
  status text NOT NULL DEFAULT 'HOLD' CHECK (status IN ('HOLD', 'VALIDATION_QUEUED', 'REJECTED')),
  risk_level text NOT NULL DEFAULT 'UNASSESSED' CHECK (risk_level IN ('UNASSESSED', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
  review_note text,
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mcp_intake_requests_created_idx ON mcp_intake_requests(created_at DESC);
CREATE INDEX IF NOT EXISTS mcp_intake_requests_submitter_idx ON mcp_intake_requests(submitted_by, created_at DESC);

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

-- The application role owns this PoC schema, so REVOKE alone cannot take away the
-- owner's implicit UPDATE/DELETE privilege. A trigger makes ordinary application
-- writes fail closed; a production deployment should additionally use a separate
-- migration owner and an append-only writer role.
CREATE OR REPLACE FUNCTION reject_decision_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'decisions is append-only';
END;
$$;
DROP TRIGGER IF EXISTS decisions_append_only ON decisions;
CREATE TRIGGER decisions_append_only
  BEFORE UPDATE OR DELETE ON decisions
  FOR EACH ROW EXECUTE FUNCTION reject_decision_mutation();

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

-- Which workspace path a scanner covers for this server. Scan output imported under
-- a server's own source_ref is what _contract() counts, so without this the Trivy
-- numbers on the dashboard and the MCP-SUPPLY-001 gate were two unrelated things.
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS scan_path text;
UPDATE mcp_servers SET scan_path = 'full_stack_lab/mock_server' WHERE id = 'mock-http' AND scan_path IS NULL;
-- mcp-server-time is pinned and installed in the gateway image, so the gateway's own
-- dependency set is the closest local proxy for that server's supply chain.
UPDATE mcp_servers SET scan_path = 'full_stack_lab/gateway' WHERE id = 'mock-stdio' AND scan_path IS NULL;

-- A reviewer who can only approve has one button and no way to say why not.
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS review_note text;

-- The organisational axis. 3 roles x 3 classes is the whole policy vocabulary today,
-- but a real tenant decides by department, project and customer as well. Widening the
-- policy *input* now costs nothing and is what keeps the rule set from having to be
-- rewritten later; the rule that uses it ships disabled (see opa/data.json).
ALTER TABLE principals ADD COLUMN IF NOT EXISTS department text;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS owner_department text;
-- Classification is an operator-owned registry value, not an LLM guess. Existing
-- demo rows receive the same explicit source during the idempotent migration.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS classification_source text;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS classification_version text;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS classified_at timestamptz;
UPDATE documents SET classification_source='manual-registry' WHERE classification_source IS NULL;
UPDATE documents SET classification_version='demo-v1' WHERE classification_version IS NULL;
UPDATE documents SET classified_at=now() WHERE classified_at IS NULL;
ALTER TABLE documents ALTER COLUMN classification_source SET DEFAULT 'manual-registry';
ALTER TABLE documents ALTER COLUMN classification_version SET DEFAULT 'demo-v1';
ALTER TABLE documents ALTER COLUMN classified_at SET DEFAULT now();
ALTER TABLE documents ALTER COLUMN classification_source SET NOT NULL;
ALTER TABLE documents ALTER COLUMN classification_version SET NOT NULL;
ALTER TABLE documents ALTER COLUMN classified_at SET NOT NULL;
UPDATE principals SET department='고객' WHERE token='cust-demo' AND department IS NULL;
UPDATE principals SET department='보안기술팀' WHERE token='emp-demo' AND department IS NULL;
UPDATE principals SET department='거버넌스팀' WHERE token='admin-demo' AND department IS NULL;
UPDATE documents SET owner_department='보안기술팀' WHERE id='work-001' AND owner_department IS NULL;
UPDATE documents SET owner_department='거버넌스팀' WHERE id='secret-001' AND owner_department IS NULL;

-- Applied on every boot so existing volumes get them too. Audit lookups are by
-- request id or by user over a time window; without these both are seq scans.
CREATE INDEX IF NOT EXISTS decisions_request_idx ON decisions(request_id);
CREATE INDEX IF NOT EXISTS decisions_user_time_idx ON decisions(user_token, created_at DESC);
CREATE INDEX IF NOT EXISTS catalog_snapshots_server_idx ON catalog_snapshots(server_id, id DESC);
CREATE INDEX IF NOT EXISTS supply_chain_source_idx ON supply_chain_reports(source_ref, scanner, id DESC);
