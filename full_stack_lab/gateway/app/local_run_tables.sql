ALTER TABLE mcp_intake_requests ADD COLUMN IF NOT EXISTS local_observer_device text;
ALTER TABLE local_jobs ADD COLUMN IF NOT EXISTS user_token text;
ALTER TABLE local_jobs ADD COLUMN IF NOT EXISTS request_id uuid;
ALTER TABLE local_jobs ADD COLUMN IF NOT EXISTS policy_generation bigint;
ALTER TABLE local_jobs ADD COLUMN IF NOT EXISTS device_epoch text;
ALTER TABLE local_jobs ADD COLUMN IF NOT EXISTS device_policy text;
ALTER TABLE local_jobs ADD COLUMN IF NOT EXISTS lease_until timestamptz;
ALTER TABLE local_jobs ADD COLUMN IF NOT EXISTS started_at timestamptz;
ALTER TABLE local_jobs ADD COLUMN IF NOT EXISTS stopped_at timestamptz;
ALTER TABLE local_jobs ADD COLUMN IF NOT EXISTS stop_requested boolean NOT NULL DEFAULT false;
ALTER TABLE local_jobs ADD COLUMN IF NOT EXISTS result_sha256 text;
ALTER TABLE local_jobs ADD COLUMN IF NOT EXISTS token_jti uuid;
ALTER TABLE local_jobs ADD COLUMN IF NOT EXISTS policy_version text;
ALTER TABLE local_jobs ADD COLUMN IF NOT EXISTS control_sha256 text;
ALTER TABLE local_jobs ADD COLUMN IF NOT EXISTS run_seconds double precision NOT NULL DEFAULT 20 CHECK (run_seconds>0 AND run_seconds<=20);
CREATE INDEX IF NOT EXISTS local_jobs_owner ON local_jobs(user_token,created_at);
CREATE INDEX IF NOT EXISTS local_jobs_server ON local_jobs(server_id,created_at);
CREATE TABLE IF NOT EXISTS local_approvals (
  server_id text PRIMARY KEY,
  intake_id uuid NOT NULL,
  observer_device text NOT NULL,
  manifest_sha256 text NOT NULL,
  signature_generation bigint NOT NULL,
  policy_generation bigint NOT NULL DEFAULT 1,
  expires_at timestamptz NOT NULL,
  revoked boolean NOT NULL DEFAULT false,
  observed boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS local_manifest_revocations (
  server_id text NOT NULL,
  signature_generation bigint NOT NULL,
  revoked_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(server_id,signature_generation)
);
CREATE TABLE IF NOT EXISTS local_run_stops (
  server_id text NOT NULL DEFAULT '',
  user_token text NOT NULL DEFAULT '',
  device_id text NOT NULL DEFAULT '',
  PRIMARY KEY(server_id,user_token,device_id)
);
CREATE TABLE IF NOT EXISTS local_job_events (
  id bigserial PRIMARY KEY,
  job_id uuid NOT NULL,
  request_id uuid,
  device_id text NOT NULL,
  server_id text NOT NULL,
  evidence jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS local_job_events_dispatch ON local_job_events(request_id,job_id);

-- A state transition cannot claim success while any affected container lacks a stop receipt.
-- Admission/start share-lock the source rows before changing a job, closing the check/update race.
CREATE OR REPLACE FUNCTION local_execution_transition() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s text := ''; u text := ''; d text := ''; token uuid; person text; changed boolean := true;
BEGIN
  IF TG_TABLE_NAME='mcp_servers' THEN
    s := OLD.id;
    IF TG_OP='UPDATE' THEN changed := ROW(OLD.status,OLD.lifecycle,OLD.endpoint,OLD.deployment) IS DISTINCT FROM ROW(NEW.status,NEW.lifecycle,NEW.endpoint,NEW.deployment); END IF;
  ELSIF TG_TABLE_NAME='principals' THEN
    u := OLD.token;
    IF TG_OP='UPDATE' THEN changed := ROW(OLD.status,OLD.role,OLD.department) IS DISTINCT FROM ROW(NEW.status,NEW.role,NEW.department); END IF;
  ELSIF TG_TABLE_NAME='endpoint_agents' THEN
    d := OLD.endpoint_id;
    -- policy_hash is left out: it moves with every server approval. A control change is caught per job (D-238).
    IF TG_OP='UPDATE' THEN changed := ROW(OLD.status,OLD.managed_state,OLD.device_epoch,OLD.owner_token,OLD.local_uid)
       IS DISTINCT FROM ROW(NEW.status,NEW.managed_state,NEW.device_epoch,NEW.owner_token,NEW.local_uid); END IF;
  ELSIF TG_TABLE_NAME='mcp_tools' THEN
    s := OLD.server_id;
    IF TG_OP='UPDATE' THEN changed := ROW(OLD.enabled,OLD.action,OLD.scope_review,OLD.approval_valid_until,OLD.approved_description_hash,OLD.approved_schema_hash,OLD.approved_output_schema_hash)
       IS DISTINCT FROM ROW(NEW.enabled,NEW.action,NEW.scope_review,NEW.approval_valid_until,NEW.approved_description_hash,NEW.approved_schema_hash,NEW.approved_output_schema_hash); END IF;
  ELSIF TG_TABLE_NAME='local_approvals' THEN
    s := OLD.server_id;
  ELSIF TG_TABLE_NAME='user_server_suspensions' THEN
    s := NEW.server_id; u := NEW.user_token;
    changed := NEW.resumed_at IS NULL;
    PERFORM pg_advisory_xact_lock(hashtext(u));
  ELSIF TG_TABLE_NAME='local_manifest_revocations' THEN
    s := NEW.server_id;
    PERFORM 1 FROM local_approvals WHERE server_id=s FOR UPDATE;
  ELSIF TG_TABLE_NAME='policy_versions' THEN
    PERFORM pg_advisory_xact_lock(hashtext('local:policy'));
    IF TG_OP='UPDATE' THEN changed := ROW(OLD.status,OLD.source_sha256) IS DISTINCT FROM ROW(NEW.status,NEW.source_sha256); END IF;
    IF TG_OP='INSERT' THEN
      changed := NOT EXISTS(SELECT 1 FROM policy_versions p WHERE p.id=NEW.id AND p.status=NEW.status AND p.source_sha256=NEW.source_sha256);
    END IF;
  ELSIF TG_TABLE_NAME='agent_revoked_tokens' THEN
    token := NEW.jti;
    FOR person IN SELECT DISTINCT user_token FROM local_jobs WHERE token_jti=token ORDER BY user_token LOOP
      PERFORM pg_advisory_xact_lock(hashtext(person));
    END LOOP;
  ELSIF TG_TABLE_NAME='mcp_intake_requests' THEN
    SELECT server_id INTO s FROM local_approvals WHERE intake_id=OLD.id;
    IF s IS NULL THEN RETURN NEW; END IF;
    PERFORM 1 FROM local_approvals WHERE server_id=s FOR UPDATE;
    changed := ROW(OLD.status,OLD.local_observer_device) IS DISTINCT FROM ROW(NEW.status,NEW.local_observer_device);
  ELSIF TG_TABLE_NAME='disposal_blocks' THEN
    IF NEW.kind IN ('server','credential') THEN s := COALESCE(NULLIF(NEW.server_id,''),NEW.subject);
    ELSIF NEW.kind='principal' THEN u := NEW.subject;
    ELSIF NEW.kind='device' THEN d := NEW.subject;
    ELSE RETURN NEW; END IF;
    FOR person IN SELECT DISTINCT user_token FROM local_jobs WHERE (s='' OR server_id=s)
       AND (u='' OR user_token=u) AND (d='' OR device_id=d) ORDER BY user_token LOOP
      PERFORM pg_advisory_xact_lock(hashtext(person));
    END LOOP;
  END IF;
  IF changed THEN
    IF EXISTS(SELECT 1 FROM local_jobs j WHERE (s='' OR j.server_id=s) AND (u='' OR j.user_token=u)
       AND (d='' OR j.device_id=d) AND (token IS NULL OR j.token_jti=token)
       AND j.started_at IS NOT NULL AND j.stopped_at IS NULL) THEN
      RAISE EXCEPTION 'local container stop is unconfirmed; transition refused' USING ERRCODE='55000';
    END IF;
    UPDATE local_jobs j SET state='expired',stop_requested=true,finished_at=clock_timestamp()
      WHERE (s='' OR j.server_id=s) AND (u='' OR j.user_token=u) AND (d='' OR j.device_id=d)
        AND (token IS NULL OR j.token_jti=token)
        AND j.state IN ('queued','claimed');
    IF TG_TABLE_NAME='mcp_servers' THEN
      IF TG_OP='DELETE' THEN changed := true;
      ELSE changed := NEW.lifecycle<>'OPERATING' OR NEW.status='DISABLED'; END IF;
      IF changed THEN
        INSERT INTO local_manifest_revocations(server_id,signature_generation)
          SELECT server_id,signature_generation FROM local_approvals WHERE server_id=s ON CONFLICT DO NOTHING;
        UPDATE local_approvals SET revoked=true,policy_generation=policy_generation+1 WHERE server_id=s;
      END IF;
    END IF;
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $$;
DROP TRIGGER IF EXISTS local_transition ON mcp_servers;
CREATE TRIGGER local_transition BEFORE UPDATE OR DELETE ON mcp_servers FOR EACH ROW EXECUTE FUNCTION local_execution_transition();
DROP TRIGGER IF EXISTS local_transition ON principals;
CREATE TRIGGER local_transition BEFORE UPDATE OR DELETE ON principals FOR EACH ROW EXECUTE FUNCTION local_execution_transition();
DROP TRIGGER IF EXISTS local_transition ON endpoint_agents;
CREATE TRIGGER local_transition BEFORE UPDATE OR DELETE ON endpoint_agents FOR EACH ROW EXECUTE FUNCTION local_execution_transition();
DROP TRIGGER IF EXISTS local_transition ON mcp_tools;
CREATE TRIGGER local_transition BEFORE UPDATE OR DELETE ON mcp_tools FOR EACH ROW EXECUTE FUNCTION local_execution_transition();
DROP TRIGGER IF EXISTS local_transition ON local_approvals;
CREATE TRIGGER local_transition BEFORE UPDATE OR DELETE ON local_approvals FOR EACH ROW EXECUTE FUNCTION local_execution_transition();
DROP TRIGGER IF EXISTS local_transition ON user_server_suspensions;
CREATE TRIGGER local_transition BEFORE INSERT OR UPDATE ON user_server_suspensions FOR EACH ROW EXECUTE FUNCTION local_execution_transition();
DROP TRIGGER IF EXISTS local_transition ON local_manifest_revocations;
CREATE TRIGGER local_transition BEFORE INSERT ON local_manifest_revocations FOR EACH ROW EXECUTE FUNCTION local_execution_transition();
DROP TRIGGER IF EXISTS local_transition ON policy_versions;
CREATE TRIGGER local_transition BEFORE INSERT OR UPDATE OR DELETE ON policy_versions FOR EACH ROW EXECUTE FUNCTION local_execution_transition();
DROP TRIGGER IF EXISTS local_transition ON agent_revoked_tokens;
CREATE TRIGGER local_transition BEFORE INSERT ON agent_revoked_tokens FOR EACH ROW EXECUTE FUNCTION local_execution_transition();
DROP TRIGGER IF EXISTS local_transition ON mcp_intake_requests;
CREATE TRIGGER local_transition BEFORE UPDATE ON mcp_intake_requests FOR EACH ROW EXECUTE FUNCTION local_execution_transition();
DROP TRIGGER IF EXISTS local_transition ON disposal_blocks;
CREATE TRIGGER local_transition BEFORE INSERT ON disposal_blocks FOR EACH ROW EXECUTE FUNCTION local_execution_transition();
