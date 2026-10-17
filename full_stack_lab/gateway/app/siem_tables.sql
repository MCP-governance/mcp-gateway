SELECT pg_advisory_xact_lock(721018128);

CREATE TABLE IF NOT EXISTS siem_outbox (
  id bigserial PRIMARY KEY,
  source text NOT NULL CHECK (source IN ('decisions','approval_events','ops_alerts')),
  source_id bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  attempts integer NOT NULL DEFAULT 0,
  next_attempt_at timestamptz NOT NULL DEFAULT now(),
  delivered_at timestamptz,
  last_error text,
  UNIQUE(source,source_id)
);
CREATE INDEX IF NOT EXISTS siem_outbox_pending ON siem_outbox(next_attempt_at,id) WHERE delivered_at IS NULL;

-- The source insert and its delivery reference commit together, including direct SQL writers.
CREATE OR REPLACE FUNCTION siem_enqueue() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_TABLE_NAME='ops_alerts' THEN
    IF NEW.synthetic THEN RETURN NEW; END IF;
  END IF;
  INSERT INTO siem_outbox(source,source_id) VALUES (TG_TABLE_NAME,NEW.id) ON CONFLICT DO NOTHING;
  RETURN NEW;
END;
$$;
CREATE OR REPLACE TRIGGER decisions_siem AFTER INSERT ON decisions FOR EACH ROW EXECUTE FUNCTION siem_enqueue();
CREATE OR REPLACE TRIGGER approvals_siem AFTER INSERT ON approval_events FOR EACH ROW EXECUTE FUNCTION siem_enqueue();
CREATE OR REPLACE TRIGGER alerts_siem AFTER INSERT ON ops_alerts FOR EACH ROW EXECUTE FUNCTION siem_enqueue();
