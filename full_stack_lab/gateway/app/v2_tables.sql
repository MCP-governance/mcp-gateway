-- v2 schema additions. Idempotent; runs at every Gateway start after agent_tables.sql
-- and lifecycle_tables.sql. See docs/ai/DATA_MODEL.md.

-- Registry rows now come from registry/catalog.toml (registry.sync()).
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS package text;
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS version text;
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS deployment text NOT NULL DEFAULT 'internal';
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS downstream text;
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS exit_terms jsonb NOT NULL DEFAULT '{}';
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS server_held_credentials jsonb NOT NULL DEFAULT '[]';

-- The approved schema itself (not only its hash), so arguments are validated before
-- the policy runs and tools/list can be served from the registry.
ALTER TABLE mcp_tools ADD COLUMN IF NOT EXISTS description text;
ALTER TABLE mcp_tools ADD COLUMN IF NOT EXISTS input_schema jsonb;
ALTER TABLE mcp_tools ADD COLUMN IF NOT EXISTS annotations jsonb;

-- Audit chain v5 columns.
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS server_id text;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS resource_id text;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS destinations jsonb;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS client jsonb;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS summary text;
CREATE INDEX IF NOT EXISTS decisions_server_time_idx ON decisions(server_id, created_at DESC);
CREATE INDEX IF NOT EXISTS decisions_time_idx ON decisions(created_at DESC);

-- Paper: the unit of analysis is the usage relationship (organisation, purpose,
-- provider, allowed resources), not the server. One server can carry several.
CREATE TABLE IF NOT EXISTS usage_relationships (
  id text PRIMARY KEY,
  server_id text NOT NULL REFERENCES mcp_servers(id),
  organization text NOT NULL,
  purpose text NOT NULL,
  provider text NOT NULL,
  owner_department text,
  allowed_resources jsonb NOT NULL DEFAULT '[]',
  status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'TERMINATING', 'TERMINATED')),
  created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE termination_cases ADD COLUMN IF NOT EXISTS relationship_id text REFERENCES usage_relationships(id);
ALTER TABLE revocation_targets ADD COLUMN IF NOT EXISTS subject_ref text;
ALTER TABLE revocation_targets ADD COLUMN IF NOT EXISTS expires_at timestamptz;
ALTER TABLE revocation_targets ADD COLUMN IF NOT EXISTS verification text;
ALTER TABLE revocation_targets ADD COLUMN IF NOT EXISTS criteria jsonb;
ALTER TABLE revocation_targets ADD COLUMN IF NOT EXISTS grade text;

-- OAuth 2.0 for workstation agents (IdP in agent-service). Access tokens are
-- self-contained JWTs; this table is the issuer's own record of what it issued, which
-- is what lets a termination case enumerate client tokens (C1) and prove their
-- state by introspection (C4).
CREATE TABLE IF NOT EXISTS oauth_issued_tokens (
  jti text PRIMARY KEY,
  user_id text NOT NULL,
  client_id text NOT NULL,
  family_id uuid NOT NULL,
  issued_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS oauth_issued_tokens_user_idx ON oauth_issued_tokens(user_id, issued_at DESC);
CREATE TABLE IF NOT EXISTS oauth_refresh_tokens (
  id uuid PRIMARY KEY,
  family_id uuid NOT NULL,
  user_id text NOT NULL,
  client_id text NOT NULL,
  token_sha256 text NOT NULL UNIQUE,
  issued_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  rotated_at timestamptz,
  revoked_at timestamptz
);
CREATE INDEX IF NOT EXISTS oauth_refresh_family_idx ON oauth_refresh_tokens(family_id);

-- v2 target and evidence kinds (the v1 constraints enumerated the old set).
ALTER TABLE revocation_targets DROP CONSTRAINT IF EXISTS revocation_targets_kind_check;
ALTER TABLE revocation_targets ADD CONSTRAINT revocation_targets_kind_check CHECK (kind IN (
  'gateway-route', 'gateway-access', 'client-token', 'refresh-token', 'dynamic-registration', 'session',
  'server-held-credential', 'endpoint-config', 'api-key', 'webhook', 'cached-artifact'));
ALTER TABLE termination_evidence DROP CONSTRAINT IF EXISTS termination_evidence_kind_check;
ALTER TABLE termination_evidence ADD CONSTRAINT termination_evidence_kind_check CHECK (kind IN (
  'revocation-response', 'introspection', 'provider-attestation', 'gateway-denial', 'liveness-probe',
  'endpoint-inventory', 'credential-check', 'session-termination', 'operator-statement'));

-- Calls that are in flight right now. The ceilings used to be counted from the audit
-- table, which only holds calls that already finished, so ten calls arriving together
-- each saw nine of them as not yet existing and all ten passed. A row is written here
-- before the policy sees the call, under a per-principal lock, so the number the policy
-- reads already includes this call and every other one still running.
CREATE TABLE IF NOT EXISTS call_reservations (
  request_id   uuid PRIMARY KEY,
  user_token   text NOT NULL,
  server_id    text,
  tool_name    text,
  fingerprint  text NOT NULL,
  data_class   text NOT NULL DEFAULT 'important',
  created_at   timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz NOT NULL,
  released_at  timestamptz
);
ALTER TABLE call_reservations ADD COLUMN IF NOT EXISTS data_class text NOT NULL DEFAULT 'important';
-- "what is this principal running now" is the only question asked of this table.
CREATE INDEX IF NOT EXISTS call_reservations_open_idx
  ON call_reservations(user_token, expires_at) WHERE released_at IS NULL;
CREATE INDEX IF NOT EXISTS call_reservations_arrivals_idx
  ON call_reservations(user_token, created_at);

-- OS refusals are device observations, not Gateway tools/call decisions. The
-- journal identity makes retries idempotent without rewriting received evidence.
CREATE TABLE IF NOT EXISTS endpoint_os_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  endpoint_id text NOT NULL REFERENCES endpoint_agents(endpoint_id),
  event_id text NOT NULL,
  observed_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  kind text NOT NULL CHECK (kind IN ('execution-denied','network-denied')),
  details jsonb NOT NULL,
  UNIQUE(endpoint_id,event_id)
);
CREATE INDEX IF NOT EXISTS endpoint_os_events_received_idx ON endpoint_os_events(received_at DESC);

-- An approved call that did not run is not a rejection (docs/architecture/proposals/
-- runtime-boundaries.md): NOT_EXECUTED = stopped before dispatch, UNCONFIRMED =
-- dispatched but the result is unknown. Databases created before this get the wider CHECK.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'approvals_status_check'
                  AND pg_get_constraintdef(oid) LIKE '%UNCONFIRMED%') THEN
    ALTER TABLE approvals DROP CONSTRAINT IF EXISTS approvals_status_check;
    ALTER TABLE approvals ADD CONSTRAINT approvals_status_check CHECK (status IN
      ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'EXECUTED', 'NOT_EXECUTED', 'UNCONFIRMED'));
  END IF;
END $$;
