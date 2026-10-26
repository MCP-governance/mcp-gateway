-- 신원 관리대장. 이전 판은 이메일·역할 매핑이 Python 상수(IDENTITIES)에 있었고
-- 비밀번호는 모든 계정이 공유하는 환경변수 하나였다. 그래서 (1) 계정을 잠그거나
-- 끄는 방법이 없었고 (2) 한 계정의 비밀번호만 바꾸는 것이 불가능했다.
-- 사용자별 bcrypt 해시와 계정 상태를 이 관리대장에 둔다.
--
-- status가 애플리케이션 상수가 아니라 이 테이블에 있는 것이 핵심이다. 상수였다면
-- 계정을 끄는 일이 배포가 된다.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS principals (
  token text PRIMARY KEY,
  display_name text NOT NULL,
  role text NOT NULL CHECK (role IN ('partner', 'employee', 'admin')),
  department text,
  synthetic boolean NOT NULL DEFAULT true,
  user_id text UNIQUE,
  email text UNIQUE,
  employee_no text,
  job_title text,
  password_hash text,
  status text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'disabled', 'locked')),
  status_changed_by text,
  status_changed_at timestamptz
);
CREATE INDEX IF NOT EXISTS principals_email_idx ON principals(lower(email));

CREATE TABLE IF NOT EXISTS mcp_servers (
  id text PRIMARY KEY,
  display_name text NOT NULL,
  transport text NOT NULL,
  endpoint text,
  source_url text NOT NULL,
  source_ref text NOT NULL,
  supplier text NOT NULL,
  license text,
  status text NOT NULL,
  status_reason text NOT NULL,
  sbom_path text,
  scan_path text,
  last_seen_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mcp_tools (
  server_id text NOT NULL REFERENCES mcp_servers(id),
  name text NOT NULL,
  action text NOT NULL CHECK (action IN ('r', 'w', 'x')),
  approved_description_hash text,
  approved_schema_hash text,
  approved_server_version text,
  observed_description_hash text,
  observed_schema_hash text,
  observed_server_version text,
  observed_at timestamptz,
  enabled boolean NOT NULL DEFAULT true,
  PRIMARY KEY (server_id, name)
);

CREATE TABLE IF NOT EXISTS catalog_snapshots (
  id bigserial PRIMARY KEY,
  server_id text NOT NULL REFERENCES mcp_servers(id),
  server_version text,
  catalog_hash text NOT NULL,
  tool_count integer NOT NULL,
  exact_match boolean NOT NULL,
  findings jsonb NOT NULL DEFAULT '[]',
  observed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS policy_versions (
  id text PRIMARY KEY,
  source_path text NOT NULL,
  source_sha256 text NOT NULL,
  status text NOT NULL,
  activated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS decisions (
  id bigserial PRIMARY KEY,
  request_id uuid NOT NULL,
  trace_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  user_token text NOT NULL,
  role text NOT NULL,
  tool_name text NOT NULL,
  data_class text NOT NULL,
  action text NOT NULL,
  decision text NOT NULL CHECK (decision IN ('Allow', 'Alert', 'Approval', 'Restrict', 'Block')),
  policy_id text NOT NULL,
  reason text NOT NULL,
  upstream_executed boolean NOT NULL DEFAULT false,
  restrictions jsonb NOT NULL DEFAULT '{}',
  approval_id uuid,
  request_payload jsonb NOT NULL DEFAULT '{}',
  result_preview jsonb,
  error text
);

ALTER TABLE decisions ADD COLUMN IF NOT EXISTS server_id text;
CREATE INDEX IF NOT EXISTS decisions_tool_sunset_idx
  ON decisions(server_id, tool_name, created_at DESC) WHERE upstream_executed;

CREATE TABLE IF NOT EXISTS approvals (
  id uuid PRIMARY KEY,
  request_fingerprint text NOT NULL,
  request_payload jsonb NOT NULL,
  status text NOT NULL CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'EXECUTED',
                                         'NOT_EXECUTED', 'UNCONFIRMED')),
  requested_by text NOT NULL,
  reviewed_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  reviewed_at timestamptz,
  executed_decision_id bigint REFERENCES decisions(id)
);

CREATE TABLE IF NOT EXISTS supply_chain_reports (
  id bigserial PRIMARY KEY,
  scanner text NOT NULL,
  scanner_version text,
  source_ref text NOT NULL,
  report_path text NOT NULL,
  status text NOT NULL,
  critical_count integer NOT NULL DEFAULT 0,
  high_count integer NOT NULL DEFAULT 0,
  medium_count integer NOT NULL DEFAULT 0,
  summary jsonb NOT NULL DEFAULT '{}',
  imported_at timestamptz NOT NULL DEFAULT now()
);

-- mcp_servers / mcp_tools rows come from registry/catalog.toml and registry/contracts.lock.json,
-- synced by the Gateway at start (gateway/app/registry.py). Nothing about a server's
-- contract is hard-coded here any more.
