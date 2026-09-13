CREATE TABLE IF NOT EXISTS principals (
  token text PRIMARY KEY,
  display_name text NOT NULL,
  role text NOT NULL CHECK (role IN ('customer', 'employee', 'admin')),
  synthetic boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS documents (
  id text PRIMARY KEY,
  title text NOT NULL,
  data_class text NOT NULL CHECK (data_class IN ('public', 'nonimportant', 'important'))
);

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

CREATE TABLE IF NOT EXISTS approvals (
  id uuid PRIMARY KEY,
  request_fingerprint text NOT NULL,
  request_payload jsonb NOT NULL,
  status text NOT NULL CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'EXECUTED')),
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

INSERT INTO principals(token, display_name, role) VALUES
  ('cust-demo', '고객 김민수', 'customer'),
  ('emp-demo', '직원 이서연', 'employee'),
  ('admin-demo', '관리자 박지훈', 'admin')
ON CONFLICT (token) DO NOTHING;

INSERT INTO documents(id, title, data_class) VALUES
  ('notice-001', '서비스 공개 공지', 'public'),
  ('work-001', '내부 업무 메모', 'nonimportant'),
  ('secret-001', '중요 계약 초안', 'important')
ON CONFLICT (id) DO NOTHING;

INSERT INTO mcp_servers(id, display_name, transport, endpoint, source_url, source_ref, supplier, license, status, status_reason) VALUES
  ('mock-http', '합성 문서 MCP', 'Streamable HTTP', 'http://mock-http-mcp:9000/mcp/', 'local://full_stack_lab/mock_server', 'demo-v1', 'MCP Governance Demo', 'MIT', 'READY', 'Git에 고정한 승인 계약과 비교'),
  ('mock-stdio', 'Time MCP', 'stdio', 'python -m mcp_server_time', 'https://github.com/modelcontextprotocol/servers', 'mcp-server-time', 'Model Context Protocol', 'MIT', 'READY', '허용 명령과 인자를 고정'),
  ('github', 'GitHub MCP Server', 'Streamable HTTP', 'https://api.githubcopilot.com/mcp/', 'https://github.com/github/github-mcp-server', 'v1.12.1', 'GitHub', 'MIT', 'DISABLED', '인증정보를 저장하지 않아 의도적으로 비활성')
ON CONFLICT (id) DO NOTHING;

INSERT INTO mcp_tools(
  server_id, name, action, enabled,
  approved_description_hash, approved_schema_hash, approved_server_version
) VALUES
  ('mock-http', 'read_document', 'r', true, 'd204053e86b958fc69afb655f7e375b202da57cac039d0a3c22c1a2b6a04d5bf', '6acf3889056551ca3e64167571d763aa08965a43e62d76cb3ebf65ac6ad2fad2', '1.0.0'),
  ('mock-http', 'write_document', 'w', true, '7ac99629874d91247a42fbc95776f375ad0c072bd3ad8cd5f030267fb8d3cfa0', '0343900e1ef1ea1e32e1f79dd11b230d3124a5df5480dbea5dab4b6bb95e2b32', '1.0.0'),
  ('mock-http', 'send_external', 'x', true, '9c668b07cecd4f93829842a503425b9794a311b93cc4bb1fb385b09020ba680c', '43b37769ed173223b4ff3e5ba229f97e1ec3e046e6715796c26fd7f3fb448e9d', '1.0.0'),
  ('mock-stdio', 'get_current_time', 'r', true, '0a34bcff2277db311ef58792a1ce0a5d4b0d678e88a0c6d77eeed328898cd9d5', '4c5f8341a69e313883df9a1bb60aeea0e8e5178e4591da372ff6d2571da53e69', '1.30.0'),
  ('mock-stdio', 'convert_time', 'r', false, '171c9160f314ac7ce564c0679d229f864814c2ed99728e2ca0e8bb34df580aa0', '116b20b454386f6d32475bdd7e7bf5cba5673c0644f23865bc19fafc9a9fafde', '1.30.0'),
  ('github', 'get_file_contents', 'r', false, NULL, NULL, 'v1.12.1'),
  ('github', 'issue_read', 'r', false, NULL, NULL, 'v1.12.1')
ON CONFLICT (server_id, name) DO NOTHING;
