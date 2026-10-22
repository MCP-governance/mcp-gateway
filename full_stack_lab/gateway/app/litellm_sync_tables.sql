SELECT pg_advisory_xact_lock(hashtext('mcp_governance_schema_migration'));

-- Retry state is mutable; evidence is appended separately to approval_events.
CREATE TABLE IF NOT EXISTS litellm_sync_jobs (
  server_id text PRIMARY KEY,
  revision bigint NOT NULL DEFAULT 1,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','failed','verified')),
  fingerprint text,
  attempts integer NOT NULL DEFAULT 0,
  retry_at timestamptz NOT NULL DEFAULT now(),
  subjects jsonb NOT NULL DEFAULT '[]',
  session_users jsonb NOT NULL DEFAULT '[]',
  inventory_unknown boolean NOT NULL DEFAULT false,
  event_id bigint,
  updated_at timestamptz NOT NULL DEFAULT now()
);
