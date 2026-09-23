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
