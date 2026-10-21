-- v2 schema additions. Idempotent; runs at every Gateway start after agent_tables.sql
-- and lifecycle_tables.sql. See docs/ai/DATA_MODEL.md.

CREATE TABLE IF NOT EXISTS console_sessions (
  jti uuid PRIMARY KEY,
  user_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_activity_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS console_sessions_expiry_idx ON console_sessions(expires_at);

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
ALTER TABLE oauth_issued_tokens ADD COLUMN IF NOT EXISTS device_id text;
ALTER TABLE oauth_issued_tokens ADD COLUMN IF NOT EXISTS device_epoch text;
ALTER TABLE oauth_issued_tokens ADD COLUMN IF NOT EXISTS device_policy text;
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
  'endpoint-inventory', 'credential-check', 'resource-rejection', 'session-termination', 'operator-statement'));

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

-- Endpoint evidence: where a stored observation came from and whether the stored form
-- is the form the agent said it sent. NULL origin/provenance = written before this.
ALTER TABLE endpoint_inventory ADD COLUMN IF NOT EXISTS origin text CHECK (origin IN ('automatic','manual','os_event'));
ALTER TABLE endpoint_inventory ADD COLUMN IF NOT EXISTS provenance jsonb;
ALTER TABLE endpoint_listeners ADD COLUMN IF NOT EXISTS origin text CHECK (origin IN ('automatic','manual','os_event'));
ALTER TABLE endpoint_listeners ADD COLUMN IF NOT EXISTS provenance jsonb;
ALTER TABLE endpoint_os_events ADD COLUMN IF NOT EXISTS origin text NOT NULL DEFAULT 'os_event' CHECK (origin IN ('automatic','manual','os_event'));
ALTER TABLE endpoint_os_events ADD COLUMN IF NOT EXISTS provenance jsonb;
ALTER TABLE endpoint_os_events ADD COLUMN IF NOT EXISTS raw_sha256 text;
ALTER TABLE endpoint_os_events ADD COLUMN IF NOT EXISTS denial_class text CHECK (denial_class IN ('harness_startup','blocked_attempt','unknown'));
CREATE INDEX IF NOT EXISTS endpoint_os_events_raw_idx ON endpoint_os_events(endpoint_id, raw_sha256) WHERE raw_sha256 IS NOT NULL;
CREATE INDEX IF NOT EXISTS endpoint_os_events_observed_idx ON endpoint_os_events(endpoint_id, observed_at DESC);

-- A bounded local observer buffer reports any intentional discard after reconnection.
-- Unique event IDs make retries append-only without retaining source log content.
CREATE TABLE IF NOT EXISTS endpoint_buffer_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  endpoint_id text NOT NULL REFERENCES endpoint_agents(endpoint_id),
  event_uid text NOT NULL,
  dropped_count integer NOT NULL CHECK (dropped_count > 0),
  reason text NOT NULL CHECK (reason IN ('capacity','retention','mixed')),
  reported_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(endpoint_id,event_uid)
);

-- One row per heartbeat cycle of the managed endpoint service, measured against the
-- Gateway address that device already uses. Rows older than seven days are removed by
-- the ingest that adds new ones.
CREATE TABLE IF NOT EXISTS endpoint_network_samples (
  endpoint_id text NOT NULL REFERENCES endpoint_agents(endpoint_id) ON DELETE CASCADE,
  measured_at timestamptz NOT NULL,
  rtt_p50_ms double precision CHECK (rtt_p50_ms IS NULL OR (rtt_p50_ms >= 0 AND rtt_p50_ms <= 60000)),
  rtt_p95_ms double precision CHECK (rtt_p95_ms IS NULL OR (rtt_p95_ms >= 0 AND rtt_p95_ms <= 60000)),
  jitter_ms double precision CHECK (jitter_ms IS NULL OR (jitter_ms >= 0 AND jitter_ms <= 60000)),
  failure_pct double precision NOT NULL CHECK (failure_pct >= 0 AND failure_pct <= 100),
  probes integer NOT NULL CHECK (probes BETWEEN 1 AND 32),
  received_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (endpoint_id, measured_at)
);
CREATE INDEX IF NOT EXISTS endpoint_network_samples_time_idx ON endpoint_network_samples(measured_at DESC);

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

-- Per-stage wall time of a tools/call in ms (core._Laps). Operational data outside the
-- audit fingerprint: it says how long the gateway took, not what it decided.
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS timings jsonb;

-- Intake provenance and supply-chain freshness (D-90). The intake worker records where the
-- code came from and what it hashed to; the vulnerability database timestamp makes a stale
-- scan visible instead of silently green.
ALTER TABLE mcp_intake_requests ADD COLUMN IF NOT EXISTS provenance jsonb NOT NULL DEFAULT '{}';
ALTER TABLE supply_chain_reports ADD COLUMN IF NOT EXISTS vuln_db_updated_at timestamptz;

-- A critical finding blocks until an operator accepts it for a limited time (D-90). The row is
-- the record; an acceptance past expires_at no longer counts and the request returns to hold.
CREATE TABLE IF NOT EXISTS accepted_risks (
  id bigserial PRIMARY KEY,
  intake_id uuid NOT NULL,
  commit_sha text NOT NULL,
  critical_count integer NOT NULL,
  finding_ids jsonb NOT NULL DEFAULT '[]',
  reason text NOT NULL,
  accepted_by text NOT NULL,
  accepted_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  revoked_by text
);
CREATE INDEX IF NOT EXISTS accepted_risks_intake_idx ON accepted_risks(intake_id, expires_at DESC);

-- Human-approved scope of every tool a Console registration serves (D-91): purpose, asset,
-- action and external destinations. A tool without one is not enabled.
ALTER TABLE mcp_tools ADD COLUMN IF NOT EXISTS scope_review jsonb;

-- Who approved what, for whom and why (D-92). Append-only like decisions: a correction is a new
-- event, never an edit.
CREATE TABLE IF NOT EXISTS approval_events (
  id bigserial PRIMARY KEY,
  kind text NOT NULL,
  outcome text NOT NULL CHECK (outcome IN ('recorded', 'approved', 'rejected', 'refused', 'held')),
  target_kind text NOT NULL,
  target_id text NOT NULL,
  actor text NOT NULL,
  applicant text,
  reason text,
  scope jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS approval_events_target_idx ON approval_events(target_kind, target_id, id);

-- A decision row that is known to be invalid stays in the ledger (its hash chain must not
-- change); an annotation says so next to it. first_id..last_id are decisions.id.
CREATE TABLE IF NOT EXISTS audit_annotations (
  id bigserial PRIMARY KEY,
  target_kind text NOT NULL CHECK (target_kind IN ('decision')),
  first_id bigint NOT NULL,
  last_id bigint NOT NULL,
  reason text NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (first_id <= last_id),
  UNIQUE (target_kind, first_id, last_id)
);
CREATE INDEX IF NOT EXISTS audit_annotations_range_idx ON audit_annotations(target_kind, first_id, last_id);

CREATE OR REPLACE FUNCTION reject_record_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$;
DROP TRIGGER IF EXISTS approval_events_append_only ON approval_events;
CREATE TRIGGER approval_events_append_only
  BEFORE UPDATE OR DELETE ON approval_events
  FOR EACH ROW EXECUTE FUNCTION reject_record_mutation();
DROP TRIGGER IF EXISTS audit_annotations_append_only ON audit_annotations;
CREATE TRIGGER audit_annotations_append_only
  BEFORE UPDATE OR DELETE ON audit_annotations
  FOR EACH ROW EXECUTE FUNCTION reject_record_mutation();

-- A tools/call is written here immediately before it is sent. The audit ledger only
-- learns of a call once its decision is recorded, so a process that dies after the send
-- left no trace and the same call could be sent again once its reservation expired.
-- pending = sent, no answer recorded yet; resolved = answered and ledgered;
-- uncertain = sent, no definite answer (timeout, lost response); confirmed_* = an
-- administrator checked the downstream system. Only uncertain (and a pending row whose
-- reservation is gone) blocks an identical write. Separate from decisions, which stay append-only.
CREATE TABLE IF NOT EXISTS dispatch_intents (
  request_id   uuid PRIMARY KEY,
  user_token   text NOT NULL,
  server_id    text NOT NULL,
  tool_name    text NOT NULL,
  action       text NOT NULL CHECK (action IN ('r','w','x')),
  fingerprint  text NOT NULL,
  attempted_at timestamptz NOT NULL DEFAULT now(),
  state        text NOT NULL DEFAULT 'pending'
               CHECK (state IN ('pending','resolved','uncertain','confirmed_executed','confirmed_not_executed')),
  decision_id  bigint,
  resolved_at  timestamptz,
  resolved_by  text,
  note         text
);
CREATE INDEX IF NOT EXISTS dispatch_intents_unsettled_idx
  ON dispatch_intents(user_token, fingerprint) WHERE state IN ('pending','uncertain');
CREATE INDEX IF NOT EXISTS dispatch_intents_server_idx ON dispatch_intents(server_id, attempted_at DESC);
CREATE INDEX IF NOT EXISTS dispatch_intents_replay_idx ON dispatch_intents(user_token, fingerprint);

-- Connection-pool closures. A cutover or a revoked principal is decided in one process
-- while every process holds warm upstream connections; the others read these rows.
CREATE TABLE IF NOT EXISTS upstream_pool_events (
  id         bigserial PRIMARY KEY,
  endpoint   text,
  principal  text,
  reason     text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Approved source MCP servers the solution builds and runs itself (DEV-38, D-114). Approval stays on the
-- intake; a runtime is one build-and-run of its verified commit with a fixed recipe. Only the runtime
-- worker (the one process with the container engine) moves these rows; attempts is its fencing token.
CREATE TABLE IF NOT EXISTS mcp_runtimes (
  id uuid PRIMARY KEY,
  intake_id uuid NOT NULL REFERENCES mcp_intake_requests(id),
  generation integer NOT NULL,
  recipe_id text NOT NULL,
  recipe_sha256 text NOT NULL,
  source_commit text NOT NULL,
  status text NOT NULL CHECK (status IN ('QUEUED','BUILDING','STARTING','VERIFYING','ACTIVE','STOPPING','STOPPED','FAILED')),
  requested_by text NOT NULL,
  attempts integer NOT NULL DEFAULT 0,
  lease_owner text,
  lease_expires_at timestamptz,
  source_archive_sha256 text,
  image_id text,
  endpoint text,
  error text,
  evidence jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (intake_id, generation)
);
ALTER TABLE mcp_runtimes ADD COLUMN IF NOT EXISTS rollback_target_generation integer;
ALTER TABLE mcp_runtimes ADD COLUMN IF NOT EXISTS rollback_contract jsonb;
-- One live runtime per approval: a second click or a second worker cannot start another.
CREATE UNIQUE INDEX IF NOT EXISTS mcp_runtimes_one_live ON mcp_runtimes(intake_id)
  WHERE status NOT IN ('STOPPED', 'FAILED');

-- POL-08: an employee's consent to one tool at one data grade, bound to the reviewed terms of that tool.
CREATE TABLE IF NOT EXISTS user_consents (
  id bigserial PRIMARY KEY,
  user_token text NOT NULL,
  server_id text NOT NULL,
  tool_name text NOT NULL,
  grade text NOT NULL CHECK (grade IN ('public', 'nonimportant', 'important')),
  terms_hash text NOT NULL,
  purpose text NOT NULL DEFAULT '',
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'GRANTED', 'DENIED', 'REVOKED')),
  requested_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz,
  expires_at timestamptz,
  UNIQUE (user_token, server_id, tool_name, grade, terms_hash)
);
-- What the employee is shown and agrees to: the reviewed terms the hash stands for.
ALTER TABLE user_consents ADD COLUMN IF NOT EXISTS terms jsonb NOT NULL DEFAULT '{}'::jsonb;

-- New ledger snapshots only; older rows remain untouched and are projected at read time.
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS outcome jsonb;

CREATE TABLE IF NOT EXISTS incident_cases (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text NOT NULL,
  started_at timestamptz NOT NULL,
  detected_at timestamptz NOT NULL,
  assessed_at timestamptz,
  scope_since timestamptz NOT NULL,
  scope_until timestamptz NOT NULL,
  scope jsonb NOT NULL,
  jurisdictions text[] NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (started_at <= detected_at),
  CHECK (assessed_at IS NULL OR assessed_at >= detected_at),
  CHECK (scope_since <= scope_until)
);
ALTER TABLE incident_cases ADD COLUMN IF NOT EXISTS assessed_at timestamptz;
CREATE TABLE IF NOT EXISTS incident_timer_heartbeat (
  id integer PRIMARY KEY CHECK (id=1),
  checked_at timestamptz NOT NULL
);
-- Per-call explanation and later human reversal; the original execution status remains evidence.
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS explanation jsonb;
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS revoked_at timestamptz;
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS revoked_by text;

-- DEV-71: what the applicant stated about data, transfer, permission and users. The risk tier is
-- computed from it each time (risk_tier.assess), never stored as a value that could drift from it.
ALTER TABLE mcp_intake_requests ADD COLUMN IF NOT EXISTS risk_input jsonb NOT NULL DEFAULT '{}';

-- Inbound MCP session bindings let lifecycle cutovers reject old protocol sessions.
CREATE TABLE IF NOT EXISTS mcp_client_sessions (
  session_hash text PRIMARY KEY,
  principal text NOT NULL,
  token_jti text NOT NULL,
  device_id text,
  server_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  terminated_at timestamptz,
  termination_reason text
);
CREATE INDEX IF NOT EXISTS mcp_client_sessions_owner_idx ON mcp_client_sessions(principal, token_jti);
CREATE INDEX IF NOT EXISTS mcp_client_sessions_server_idx ON mcp_client_sessions(server_id) WHERE terminated_at IS NULL;
CREATE TABLE IF NOT EXISTS mcp_session_events (
  id bigserial PRIMARY KEY,
  reason text NOT NULL,
  principal text,
  device_id text,
  server_id text,
  session_hash text,
  sessions_closed integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS mcp_session_events_append_only ON mcp_session_events;
CREATE TRIGGER mcp_session_events_append_only
  BEFORE UPDATE OR DELETE ON mcp_session_events
  FOR EACH ROW EXECUTE FUNCTION reject_record_mutation();

-- D-142 (P-FLOW-001): what an important read released, as salted hashes of its normalised text and
-- never the text, for the flow window. Not the ledger and not evidence: a row can only be added, and
-- is deleted once expired. A read without a row stays a flow source for the whole window.
CREATE TABLE IF NOT EXISTS flow_fingerprints (
  id bigserial PRIMARY KEY,
  user_token text NOT NULL,
  server_id text NOT NULL,
  decision_id bigint NOT NULL UNIQUE,
  salt bytea NOT NULL,
  key_id text NOT NULL DEFAULT '',
  shingles bigint[] NOT NULL,
  identifiers bigint[] NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL
);
ALTER TABLE flow_fingerprints ADD COLUMN IF NOT EXISTS key_id text NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS flow_fingerprints_owner_idx ON flow_fingerprints(user_token, expires_at);
DROP TRIGGER IF EXISTS flow_fingerprints_no_update ON flow_fingerprints;
CREATE TRIGGER flow_fingerprints_no_update
  BEFORE UPDATE ON flow_fingerprints
  FOR EACH ROW EXECUTE FUNCTION reject_record_mutation();

ALTER TABLE incident_cases ADD COLUMN IF NOT EXISTS pack_snapshot jsonb;
ALTER TABLE incident_cases ADD COLUMN IF NOT EXISTS incident_type text;
ALTER TABLE incident_cases ADD COLUMN IF NOT EXISTS fix_available_at timestamptz;
ALTER TABLE incident_cases ADD COLUMN IF NOT EXISTS handled_at timestamptz;
ALTER TABLE incident_timer_heartbeat ADD COLUMN IF NOT EXISTS last_failed_at timestamptz;

-- D-149: NULL approval means the legacy contract had no output schema, never TOFU.
ALTER TABLE mcp_tools ADD COLUMN IF NOT EXISTS output_schema jsonb;
ALTER TABLE mcp_tools ADD COLUMN IF NOT EXISTS observed_output_schema_hash text
  DEFAULT '74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b';
ALTER TABLE mcp_tools ADD COLUMN IF NOT EXISTS approved_output_schema_hash text;

ALTER TABLE mcp_intake_requests ADD COLUMN IF NOT EXISTS requested_tools jsonb NOT NULL DEFAULT '[]';
