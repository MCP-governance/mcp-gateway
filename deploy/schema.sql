CREATE TABLE IF NOT EXISTS evidence_events (
  id BIGSERIAL PRIMARY KEY,
  trace_id TEXT NOT NULL,
  span_id TEXT NOT NULL,
  service TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload JSONB NOT NULL,
  risk TEXT CHECK (risk IN ('low','medium','high')),
  flags JSONB NOT NULL DEFAULT '[]',
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  analyzed_at TIMESTAMPTZ,
  UNIQUE(trace_id,span_id)
);
CREATE TABLE IF NOT EXISTS tool_contracts (
  server TEXT NOT NULL,
  tool TEXT NOT NULL,
  hash TEXT NOT NULL,
  definition JSONB NOT NULL,
  approved BOOLEAN NOT NULL DEFAULT false,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(server,tool)
);
CREATE TABLE IF NOT EXISTS audit_events (
  id BIGSERIAL PRIMARY KEY,
  kind TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE OR REPLACE FUNCTION prevent_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_events is append-only';
END;
$$;
DROP TRIGGER IF EXISTS audit_append_only ON audit_events;
CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();
