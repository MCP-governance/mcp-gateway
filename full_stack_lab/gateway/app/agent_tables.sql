-- gateway와 agent-service가 기동할 때마다 같은 파일을 동시에 적용한다. 서로 다른
-- 순서로 ALTER의 AccessExclusiveLock을 잡으면 교착이 나고 한쪽 서비스가 기동에
-- 실패한다. 마이그레이션은 한 번에 하나만 돌게 잠금을 먼저 잡는다.
SELECT pg_advisory_xact_lock(hashtext('mcp_governance_schema_migration'));

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

-- §11.17 정책 판단 및 집행 증적. 판정만 남기면 "어느 정책의 어느 버전이, 어떤
-- 의무와 예외를 달고, 어떤 경쟁 정책을 제치고 최종 판단이 됐는지"를 나중에
-- 재구성할 수 없다. 기존 행은 chain_version으로 구분되므로 해시 체인은 그대로다.
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS policy_version text;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS obligations jsonb NOT NULL DEFAULT '[]';
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS exception_id text;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS conflicts jsonb NOT NULL DEFAULT '[]';
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS environment text;
-- NULL은 구버전 기록이다. 기존 해시는 고치지 않고 체인 v4부터 시도 여부를 보호한다.
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS upstream_attempted boolean;

-- §11.4.1 승인 유효기간 만료 확인. 승인은 영구가 아니므로 Registry가 기한을
-- 들고 있어야 정책이 그것을 판단할 수 있다.
ALTER TABLE mcp_tools ADD COLUMN IF NOT EXISTS approval_valid_until timestamptz;
UPDATE mcp_tools SET approval_valid_until = timestamptz '2027-06-30 23:59:59+00'
  WHERE approval_valid_until IS NULL;

-- EXC-001(감사 대응 한시 열람) 예외의 유일한 적용 대상. 기존 볼륨에도 들어가야
-- 예외 시연이 secret-001의 차단 시나리오를 덮어쓰지 않는다.
INSERT INTO documents(id, title, data_class, classification_source, classification_version, owner_department)
VALUES ('audit-001', '외부 감사 대응 계약 사본', 'important', 'manual-registry', 'demo-v1', '거버넌스팀')
ON CONFLICT (id) DO NOTHING;

-- 협력업체 직원(partner)으로 역할 이름을 바꾼다. 내부망 테스트베드에 "고객"이
-- 있는 것이 이상하고, 이 역할이 실제로 대리하는 것은 신뢰경계 밖에서 들어오는
-- 외부 인력이다. 기존 볼륨에도 적용해야 로그인 신원과 DB 역할이 갈라지지 않는다.
ALTER TABLE principals DROP CONSTRAINT IF EXISTS principals_role_check;
UPDATE principals SET role='partner' WHERE role='customer';
UPDATE principals SET token='partner-demo', display_name='협력업체 김민수', department='협력사 A'
  WHERE token='cust-demo';
ALTER TABLE principals ADD CONSTRAINT principals_role_check
  CHECK (role IN ('partner', 'employee', 'admin'));

-- 도입 요청의 실제 검증 결과. 상태만 바꾸고 증적이 없으면 "검증했다"가 아니라
-- "검증했다고 적었다"이다. 격리 워커가 만든 commit·source_ref·요약을 함께 둔다.
ALTER TABLE mcp_intake_requests ADD COLUMN IF NOT EXISTS commit_sha text;
ALTER TABLE mcp_intake_requests ADD COLUMN IF NOT EXISTS source_ref text;
ALTER TABLE mcp_intake_requests ADD COLUMN IF NOT EXISTS evidence jsonb NOT NULL DEFAULT '{}';
ALTER TABLE mcp_intake_requests ADD COLUMN IF NOT EXISTS validated_at timestamptz;
ALTER TABLE mcp_intake_requests DROP CONSTRAINT IF EXISTS mcp_intake_requests_status_check;
ALTER TABLE mcp_intake_requests ADD CONSTRAINT mcp_intake_requests_status_check
  CHECK (status IN ('HOLD', 'VALIDATION_QUEUED', 'VALIDATING', 'VALIDATED', 'APPROVED', 'FAILED', 'REJECTED'));
CREATE INDEX IF NOT EXISTS mcp_intake_requests_status_idx ON mcp_intake_requests(status, created_at);

-- AI-Infra-Guard mcp-scan은 LLM endpoint를 요구하는 코드 감사라 도입 검증과 같은
-- 트랜잭션에 넣을 수 없다. 운영자가 필요할 때 돌리는 별도 작업으로 큐에 넣고,
-- 어떤 모델·endpoint로 돌렸는지까지 결과와 함께 남긴다. 어떤 모델이 판단했는지
-- 모르는 보안 결과는 증적이 아니다.
CREATE TABLE IF NOT EXISTS scan_jobs (
  id uuid PRIMARY KEY,
  kind text NOT NULL CHECK (kind IN ('mcp-scan')),
  target_kind text NOT NULL CHECK (target_kind IN ('intake')),
  target_id uuid NOT NULL,
  target_label text NOT NULL DEFAULT '',
  status text NOT NULL DEFAULT 'QUEUED' CHECK (status IN ('QUEUED', 'RUNNING', 'DONE', 'FAILED')),
  requested_by text NOT NULL,
  model text,
  base_url text,
  report_path text,
  summary jsonb NOT NULL DEFAULT '{}',
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS scan_jobs_status_idx ON scan_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS scan_jobs_target_idx ON scan_jobs(target_id, created_at DESC);

-- ── AI 코드 감사 실행 구조 (v1.5) ──────────────────────────────────────────
-- 이전 판의 mcp-scan은 "관리자가 버튼을 누르면 QUEUED 한 줄을 넣는다"가 전부였다.
-- 그래서 세 가지가 동시에 깨져 있었다.
--
--  1) 워커가 RUNNING 중에 죽으면 그 행은 영원히 RUNNING으로 남고, 재실행 API는
--     QUEUED·RUNNING이면 409로 막으므로 그 대상은 다시는 감사할 수 없었다.
--  2) 워커가 아예 떠 있지 않아도 Console은 "설정됨"만 보여줬다. 큐에 쌓이는 것과
--     실행되는 것을 화면에서 구분할 수 없었다.
--  3) 대상이 도입 요청뿐이라, 이미 Registry에 올라가 실제로 호출되는 서버는
--     감사 대상이 될 수 없었다. 심사받은 코드와 운영 중인 코드가 갈라진다.
--
-- lease는 "이 작업을 이 시각까지 들고 있겠다"는 선언이다. 만료되면 다른 워커가
-- 회수한다. 작업이 실패해도 대기열에 조용히 남지 않는 것이 이 설계의 목적이다.
-- uuid -> text. 이미 text면 건드리지 않는다. 조건 없이 쓰면 매 기동마다 테이블을
-- 다시 쓴다.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='scan_jobs' AND column_name='target_id' AND data_type='uuid') THEN
    ALTER TABLE scan_jobs ALTER COLUMN target_id TYPE text USING target_id::text;
  END IF;
END $$;
ALTER TABLE scan_jobs DROP CONSTRAINT IF EXISTS scan_jobs_target_kind_check;
ALTER TABLE scan_jobs ADD CONSTRAINT scan_jobs_target_kind_check
  CHECK (target_kind IN ('intake', 'server'));
ALTER TABLE scan_jobs DROP CONSTRAINT IF EXISTS scan_jobs_status_check;
ALTER TABLE scan_jobs ADD CONSTRAINT scan_jobs_status_check
  CHECK (status IN ('QUEUED', 'RUNNING', 'DONE', 'FAILED', 'CANCELLED'));

-- 어떤 시점이 이 작업을 만들었는지 남긴다. "관리자가 기억나서 눌렀다"와
-- "검증 통과가 자동으로 걸었다"는 증적으로서 값이 다르다.
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS trigger text NOT NULL DEFAULT 'manual';
ALTER TABLE scan_jobs DROP CONSTRAINT IF EXISTS scan_jobs_trigger_check;
ALTER TABLE scan_jobs ADD CONSTRAINT scan_jobs_trigger_check
  CHECK (trigger IN ('manual', 'validated', 'rescan', 'drift'));
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS commit_sha text;
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS repository_url text;
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS source_ref text;
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS attempts integer NOT NULL DEFAULT 0;
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz;
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS cancel_requested boolean NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS scan_jobs_lease_idx ON scan_jobs(status, lease_expires_at);

-- 같은 대상에 대해 살아 있는 작업은 하나뿐이다. 이전에는 애플리케이션 조회 한
-- 번으로만 막았으므로 동시에 두 번 누르면 두 개가 들어갔다.
-- 이전 판이 남긴 중복 대기 행이 있으면 인덱스 생성이 실패하고, 그러면 이 파일을
-- 실행하는 서비스가 뜨지 않는다. 마이그레이션이 기동을 막는 것이 가장 나쁘다.
-- 같은 대상의 오래된 대기 행을 먼저 정리하고 만든다.
UPDATE scan_jobs old SET status='CANCELLED', finished_at=now(),
       error=COALESCE(old.error,'') || ' · 같은 대상의 최신 작업만 남깁니다.'
 WHERE old.status IN ('QUEUED','RUNNING')
   AND EXISTS (SELECT 1 FROM scan_jobs newer
               WHERE newer.target_kind=old.target_kind AND newer.target_id=old.target_id
                 AND newer.status IN ('QUEUED','RUNNING') AND newer.created_at > old.created_at);
CREATE UNIQUE INDEX IF NOT EXISTS scan_jobs_one_live_per_target
  ON scan_jobs(target_kind, target_id) WHERE status IN ('QUEUED', 'RUNNING');

-- 워커 생존 신호. "설정이 있다"와 "실행할 사람이 있다"는 다른 질문이고,
-- 둘을 구분하지 못하면 큐에 쌓인 작업을 진행 중으로 읽게 된다.
CREATE TABLE IF NOT EXISTS worker_heartbeats (
  worker text PRIMARY KEY,
  role text NOT NULL,
  seen_at timestamptz NOT NULL DEFAULT now(),
  detail jsonb NOT NULL DEFAULT '{}'
);

-- ── 신원 관리대장 이관 (v1.5) ────────────────────────────────────────────────
-- 이미 만들어진 DB에도 같은 모양을 적용한다. db/init.sql은 최초 생성 때만 돌고,
-- 이 파일은 gateway와 agent-service가 뜰 때마다 돈다.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
ALTER TABLE principals ADD COLUMN IF NOT EXISTS user_id text;
ALTER TABLE principals ADD COLUMN IF NOT EXISTS email text;
ALTER TABLE principals ADD COLUMN IF NOT EXISTS employee_no text;
ALTER TABLE principals ADD COLUMN IF NOT EXISTS job_title text;
ALTER TABLE principals ADD COLUMN IF NOT EXISTS password_hash text;
ALTER TABLE principals ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active';
ALTER TABLE principals ADD COLUMN IF NOT EXISTS status_changed_by text;
ALTER TABLE principals ADD COLUMN IF NOT EXISTS status_changed_at timestamptz;
ALTER TABLE principals DROP CONSTRAINT IF EXISTS principals_status_check;
ALTER TABLE principals ADD CONSTRAINT principals_status_check
  CHECK (status IN ('active', 'disabled', 'locked'));
CREATE UNIQUE INDEX IF NOT EXISTS principals_user_id_key ON principals(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS principals_email_key ON principals(email);
CREATE INDEX IF NOT EXISTS principals_email_idx ON principals(lower(email));

UPDATE principals SET user_id='user-partner-001', email='partner@bob.local',
       employee_no=COALESCE(employee_no,'EXT-001'), job_title=COALESCE(job_title,'협력업체 담당')
 WHERE token='partner-demo' AND user_id IS NULL;
UPDATE principals SET user_id='user-test-001', email='miso@bob.local',
       employee_no=COALESCE(employee_no,'EMP-001'), job_title=COALESCE(job_title,'보안기술팀 사원')
 WHERE token='emp-demo' AND user_id IS NULL;
UPDATE principals SET user_id='user-admin-001', email='admin@bob.local',
       employee_no=COALESCE(employee_no,'EMP-002'), job_title=COALESCE(job_title,'거버넌스팀 관리자')
 WHERE token='admin-demo' AND user_id IS NULL;
