-- 전주기의 마지막 구간: 종료·폐기와 그 판정.
--
-- 이 저장소의 기존 스키마는 "들어오는 것"에 대해서는 촘촘하다. 도입 요청, 격리
-- 검증, 승인, catalog 고정, 공급망 증적이 모두 있다. 그런데 나가는 것에 대해서는
-- mcp_servers.status='DISABLED' 한 칸뿐이었다. 그 한 칸은 "호출을 막았다"만
-- 말하고 "회수했다"는 말하지 못한다. 둘은 다른 사실이다.
--
-- 여기의 표는 CISC-W'26 투고 논문(「원격 MCP 서비스 종료 시 권한 회수의 구조적
-- 한계 및 종료 판정 기준 제안」)의 C1~C4 기준과 T1~T3 등급을 그대로 데이터
-- 모델로 옮긴 것이다. 판정을 사람의 서술이 아니라 조회 가능한 행으로 만드는 것이
-- 목적이다. "종료했습니다"는 주장이고, "C3을 충족하지 못해 T2입니다"는 판정이다.
SELECT pg_advisory_xact_lock(hashtext('mcp_governance_schema_migration'));

-- ── 1. 서버 생애주기 ────────────────────────────────────────────────────────
-- status(READY/DISABLED/BLOCKED_SUPPLY_CHAIN)와 분리한다. status는 "지금 쓸 수
-- 있는가"이고 lifecycle은 "이 이용 관계가 어느 단계에 있는가"다. 공급망 문제로
-- 잠깐 막힌 서버와 폐기 절차에 들어간 서버를 같은 칸에 넣으면, 폐기를 되돌리는
-- 것과 차단을 푸는 것이 같은 조작이 된다.
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS lifecycle text NOT NULL DEFAULT 'OPERATING';
ALTER TABLE mcp_servers DROP CONSTRAINT IF EXISTS mcp_servers_lifecycle_check;
ALTER TABLE mcp_servers ADD CONSTRAINT mcp_servers_lifecycle_check
  CHECK (lifecycle IN ('OPERATING', 'TERMINATING', 'RETIRED'));
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS lifecycle_changed_at timestamptz;
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS lifecycle_changed_by text;
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS termination_case_id uuid;

-- ── 2. 종료 케이스 ──────────────────────────────────────────────────────────
-- 논문은 분석 단위를 "조직·목적·제공자·허용 자원으로 식별되는 접근 허용의 집합"
-- 곧 이용 관계로 정의한다. 이 테스트베드에서는 Registry 서버 하나가 그 대리키가
-- 되지만, 케이스를 열 때 목적·제공자·자원을 스냅샷으로 함께 굳힌다. 폐기가 끝난
-- 뒤 Registry 행이 바뀌어도 "무엇을 종료한 케이스였는가"가 남아야 한다.
CREATE TABLE IF NOT EXISTS termination_cases (
  id uuid PRIMARY KEY,
  server_id text NOT NULL REFERENCES mcp_servers(id),
  engagement_label text NOT NULL,
  provider text NOT NULL,
  allowed_resources jsonb NOT NULL DEFAULT '[]',
  reason text NOT NULL,
  status text NOT NULL DEFAULT 'OPEN'
    CHECK (status IN ('OPEN', 'REVOKING', 'ASSESSED', 'CLOSED', 'REOPENED')),
  grade text CHECK (grade IN ('T1', 'T2', 'T3')),
  criteria jsonb NOT NULL DEFAULT '{}',
  -- 호출 차단이 시작된 시각. C3(연속성)의 기준점이며, 이 시각 이후의 성공한
  -- upstream 호출이 한 건이라도 있으면 연속성은 깨진 것이다.
  cutover_at timestamptz,
  opened_by text NOT NULL,
  opened_at timestamptz NOT NULL DEFAULT now(),
  assessed_by text,
  assessed_at timestamptz,
  closed_by text,
  closed_at timestamptz,
  close_note text,
  -- T3(판단 불가)를 종결하려면 위험 수용의 주체가 기록에 남아야 한다. 논문 5.1은
  -- T3를 "위험 수용을 판단하기에 증거가 부족한 상태"로 분류하고 별도 승인을
  -- 요구한다. 이 칸이 비어 있으면 T3 케이스는 닫히지 않는다.
  risk_accepted_by text,
  risk_accepted_at timestamptz,
  risk_acceptance_note text
);
CREATE INDEX IF NOT EXISTS termination_cases_server_idx ON termination_cases(server_id, opened_at DESC);
CREATE INDEX IF NOT EXISTS termination_cases_status_idx ON termination_cases(status, opened_at DESC);
-- 한 서버에 살아 있는 케이스는 하나뿐이다. 둘이 열리면 어느 판정이 그 서버의
-- 상태인지 저장소가 답하지 못한다.
CREATE UNIQUE INDEX IF NOT EXISTS termination_cases_one_live_per_server
  ON termination_cases(server_id) WHERE status IN ('OPEN', 'REVOKING', 'ASSESSED', 'REOPENED');

-- ── 3. 회수 대상 모집단 (C1) ────────────────────────────────────────────────
-- 논문 C1은 "회수 대상을 빠짐없이 열거하고 조치 대상과 대조하였는가"를 묻는다.
-- 열거되지 않은 것은 조치되지도 않으므로, 이 표가 비면 나머지 세 기준은 검토할
-- 대상조차 없다. holder가 provider인 행은 조직이 스스로 회수할 수 없는 자격,
-- 곧 논문 3.2절의 하위 위임 자격이다.
CREATE TABLE IF NOT EXISTS revocation_targets (
  id uuid PRIMARY KEY,
  case_id uuid NOT NULL REFERENCES termination_cases(id) ON DELETE CASCADE,
  kind text NOT NULL CHECK (kind IN (
    'client-token', 'refresh-token', 'dynamic-registration', 'session',
    'server-held-credential', 'endpoint-config', 'api-key', 'webhook', 'cached-artifact')),
  label text NOT NULL,
  -- 누가 이것을 회수할 수 있는가. C2(수행 권한)가 이 값을 본다.
  holder text NOT NULL CHECK (holder IN ('org', 'provider', 'endpoint')),
  -- 어떻게 알게 되었는가. 제공자가 고지하지 않은 provider 보유 자격은 모집단을
  -- 열거했다고 말할 수 없다. 출처를 남기지 않으면 그 구분이 사라진다.
  discovered_by text NOT NULL CHECK (discovered_by IN (
    'gateway-ledger', 'endpoint-agent', 'provider-disclosure', 'operator-manual', 'liveness-probe')),
  status text NOT NULL DEFAULT 'OUTSTANDING'
    CHECK (status IN ('OUTSTANDING', 'REVOKED', 'EXPIRED', 'UNVERIFIABLE')),
  revoked_at timestamptz,
  revoked_by text,
  note text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS revocation_targets_case_idx ON revocation_targets(case_id, created_at);

-- ── 4. 증거 (C4) ────────────────────────────────────────────────────────────
-- C4는 "증거가 대상·시점을 특정하며 열람 가능한가"를 묻는다. 그래서 subject와
-- observed_at이 NOT NULL이다. "폐기 요청을 보냈다"는 기록은 대상의 상태를
-- 특정하지 않으므로 그것만으로는 C4를 충족하지 못한다(논문 3.1).
CREATE TABLE IF NOT EXISTS termination_evidence (
  id uuid PRIMARY KEY,
  case_id uuid NOT NULL REFERENCES termination_cases(id) ON DELETE CASCADE,
  target_id uuid REFERENCES revocation_targets(id) ON DELETE CASCADE,
  kind text NOT NULL CHECK (kind IN (
    'revocation-response', 'introspection', 'provider-attestation',
    'gateway-denial', 'liveness-probe', 'endpoint-inventory', 'operator-statement')),
  subject text NOT NULL,
  observed_at timestamptz NOT NULL,
  source text NOT NULL,
  detail jsonb NOT NULL DEFAULT '{}',
  sha256 text NOT NULL,
  recorded_by text NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS termination_evidence_case_idx ON termination_evidence(case_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS termination_evidence_target_idx ON termination_evidence(target_id);

-- ── 5. 엔드포인트 인벤토리 (망 경계 밖의 모집단) ────────────────────────────
-- Gateway는 자기를 통과한 호출만 안다. 사용자 PC의 MCP 클라이언트 설정 파일에
-- 남아 있는 서버 항목은 Gateway 기록에 존재하지 않으므로, C1의 모집단을 게이트웨이
-- 혼자서는 열거할 수 없다. 그 부분은 엔드포인트 평면이 보고한다.
--
-- 이 표가 종료 판정과 이어지는 지점이 핵심이다. 폐기한 서버가 어느 노트북의
-- 설정에 그대로 남아 있으면 그것은 회수되지 않은 접근 경로다.
CREATE TABLE IF NOT EXISTS endpoint_agents (
  endpoint_id text PRIMARY KEY,
  hostname text NOT NULL,
  platform text NOT NULL,
  agent_version text NOT NULL,
  owner_token text,
  enrolled_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  detail jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS endpoint_inventory (
  id bigserial PRIMARY KEY,
  endpoint_id text NOT NULL REFERENCES endpoint_agents(endpoint_id) ON DELETE CASCADE,
  reported_at timestamptz NOT NULL DEFAULT now(),
  config_path text NOT NULL,
  server_label text NOT NULL,
  transport text NOT NULL,
  endpoint_ref text NOT NULL,
  fingerprint text NOT NULL,
  registry_match text REFERENCES mcp_servers(id),
  -- registered      : Registry의 운영 중인 서버와 대조됨
  -- shadow          : 어느 등록 서버와도 대조되지 않음 (AI-Infra-Guard MCP09)
  -- retired-residue : 폐기했거나 폐기 중인 서버가 설정에 남아 있음
  classification text NOT NULL CHECK (classification IN ('registered', 'shadow', 'retired-residue')),
  raw jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS endpoint_inventory_class_idx ON endpoint_inventory(classification, reported_at DESC);
CREATE INDEX IF NOT EXISTS endpoint_inventory_match_idx ON endpoint_inventory(registry_match);
-- 같은 엔드포인트의 같은 설정 항목은 한 행이다. 보고가 반복될 때마다 행이 쌓이면
-- "지금 남아 있는 잔존 설정 수"를 셀 수 없고, 그 수가 곧 C1 판정의 입력이다.
CREATE UNIQUE INDEX IF NOT EXISTS endpoint_inventory_unique_entry
  ON endpoint_inventory(endpoint_id, fingerprint);

-- ── 6. AI-Infra-Guard 위험 범주 대장 ────────────────────────────────────────
-- 스캐너가 "MCP03 도구 중독 1건"이라고 말했을 때, 그것이 이 조직의 어느 통제로
-- 이어지는지 저장소가 답할 수 있어야 한다. 답하지 못하면 발견 목록은 읽을거리다.
-- gate='blocking'인 범주는 치명 등급이 실제 호출 차단으로 이어지고,
-- 'evidence-only'는 증적으로만 남는다. 어느 쪽인지 화면이 먼저 말한다.
CREATE TABLE IF NOT EXISTS aig_risk_catalog (
  id text PRIMARY KEY,
  title_ko text NOT NULL,
  title_en text NOT NULL,
  description text NOT NULL,
  mapped_policy_ids jsonb NOT NULL DEFAULT '[]',
  mapped_control_ids jsonb NOT NULL DEFAULT '[]',
  gate text NOT NULL CHECK (gate IN ('blocking', 'evidence-only')),
  ordinal integer NOT NULL
);

INSERT INTO aig_risk_catalog(id, title_ko, title_en, description, mapped_policy_ids, mapped_control_ids, gate, ordinal) VALUES
  ('MCP01', '토큰·비밀 노출', 'Token & Secret Exposure',
   '저장소나 도구 응답에 자격증명이 드러난다. 폐기 단계에서는 회수 대상 모집단(C1)에 추가해야 하는 항목이 된다.',
   '["MCP-SUPPLY-001", "MCP-DECOMM-001"]', '["CTL-002", "CTL-018"]', 'blocking', 1),
  ('MCP02', '권한 상승·범위 확장', 'Privilege Escalation & Scope Creep',
   '승인된 범위보다 넓은 권한을 요구하거나 획득한다. 333 권한표와 Registry 계약이 판단 근거다.',
   '["MCP-CATALOG-001", "P-333-DENY-001"]', '["CTL-003", "CTL-004"]', 'blocking', 2),
  ('MCP03', '도구 중독', 'Tool Poisoning Attack',
   '도구 설명이나 스키마에 정책 우회 지시를 심는다. 설명·스키마 해시 고정이 직접 대응한다.',
   '["MCP-CATALOG-001"]', '["CTL-003"]', 'blocking', 3),
  ('MCP04', '공급망 공격', 'Supply Chain Attack',
   '의존성이나 빌드 경로를 통해 악성 코드가 들어온다. 격리 검증의 SBOM·SCA 증적이 대응한다.',
   '["MCP-SUPPLY-001"]', '["CTL-002"]', 'blocking', 4),
  ('MCP05', '명령 주입·실행', 'Command Injection & Execution',
   '도구 인자가 셸이나 인터프리터로 흘러 임의 실행이 된다. 입력 스키마 검증과 SAST 규칙이 대응한다.',
   '["P-INPUT-SCHEMA-001", "MCP-SUPPLY-001"]', '["CTL-002", "CTL-009"]', 'blocking', 5),
  ('MCP06', '프롬프트 인젝션', 'Prompt Injection Attack',
   '도구 결과나 설명이 모델의 지시를 바꾼다. Gateway는 결과를 검사하고 prompts/resources를 중개하지 않는다.',
   '["MCP-OUTPUT-001", "MCP-METHOD-001"]', '["CTL-010", "CTL-011"]', 'blocking', 6),
  ('MCP07', '인증·인가 미흡', 'Insufficient Auth & Authorization',
   '서버가 신원을 확인하지 않거나 범위를 강제하지 않는다. 단일 강제 경로와 서명 신원이 대응한다.',
   '["MCP-REGISTRY-002", "P-333-DENY-001"]', '["CTL-001", "CTL-004"]', 'evidence-only', 7),
  ('MCP08', '감사·원격측정 부재', 'Missing Audit & Telemetry',
   '호출 기록이 남지 않아 사후 재구성이 불가능하다. 종료 판정의 C4가 정확히 이 문제를 본다.',
   '["MCP-DECOMM-001"]', '["CTL-012", "CTL-018"]', 'evidence-only', 8),
  ('MCP09', '섀도 MCP 서버', 'Shadow MCP Server',
   '등록되지 않은 MCP 서버가 엔드포인트에서 직접 쓰인다. 게이트웨이를 통과하지 않으므로 네트워크 평면 혼자서는 보이지 않는다.',
   '["MCP-REGISTRY-001"]', '["CTL-001", "CTL-019"]', 'evidence-only', 9),
  ('MCP10', '컨텍스트 주입·과다 공유', 'Context Injection & Over-sharing',
   '필요 이상의 맥락이 외부로 나간다. 데이터 등급과 외부 전송 제한이 대응한다.',
   '["P-X-RESTRICT-001", "P-X-APPROVAL-001"]', '["CTL-005", "CTL-006"]', 'evidence-only', 10),
  ('NAME-CONFUSION', '이름 혼동', 'Name Confusion Attack',
   '정상 서버와 비슷한 이름으로 오인을 유도한다. 카탈로그 검색과 등록 대조가 대응한다.',
   '["MCP-REGISTRY-001"]', '["CTL-001"]', 'evidence-only', 11),
  ('RUG-PULL', '러그풀', 'Rug Pull Attack',
   '승인 이후 서버가 조용히 동작을 바꾼다. 매 호출 전 catalog 재대조와 재감사 주기가 대응한다.',
   '["MCP-CATALOG-001", "P-APPROVAL-EXPIRY-001"]', '["CTL-003", "CTL-007"]', 'blocking', 12),
  ('TOOL-SHADOWING', '도구 가리기', 'Tool Shadowing Attack',
   '다른 서버의 도구를 가려 호출을 가로챈다. 도구 집합 고정(known_tools_only)이 대응한다.',
   '["MCP-CATALOG-001"]', '["CTL-003"]', 'blocking', 13)
ON CONFLICT (id) DO UPDATE SET
  title_ko = EXCLUDED.title_ko, title_en = EXCLUDED.title_en, description = EXCLUDED.description,
  mapped_policy_ids = EXCLUDED.mapped_policy_ids, mapped_control_ids = EXCLUDED.mapped_control_ids,
  gate = EXCLUDED.gate, ordinal = EXCLUDED.ordinal;

-- ── 7. 감사 작업의 확장 (AI-Infra-Guard 전체 활용) ──────────────────────────
-- v1.5까지 scan_jobs는 정적 코드 감사 한 종류였다. AI-Infra-Guard는 그 밖에
-- 실행 중인 서버를 대상으로 하는 동적 점검과 AI 인프라 지문·취약점 점검을 함께
-- 제공한다. 셋을 한 표에 두되 mode와 kind로 구분한다. 무엇을 돌렸는지 모르는
-- 결과는 증적이 아니다.
-- kind는 'mcp-scan' 하나로 둔다. 원본 A.I.G UI의 인프라 지문·CVE 점검은
-- Gateway 컨테이너에서 수동 실행할 수 있으나 이 자동 작업 표에 연결되지 않는다.
-- 구현하지 않은 종류를 예약해 두면 실제로 검사한 것처럼 오인될 수 있다.
ALTER TABLE scan_jobs DROP CONSTRAINT IF EXISTS scan_jobs_kind_check;
ALTER TABLE scan_jobs ADD CONSTRAINT scan_jobs_kind_check
  CHECK (kind IN ('mcp-scan'));
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS mode text NOT NULL DEFAULT 'static';
ALTER TABLE scan_jobs DROP CONSTRAINT IF EXISTS scan_jobs_mode_check;
ALTER TABLE scan_jobs ADD CONSTRAINT scan_jobs_mode_check CHECK (mode IN ('static', 'dynamic'));
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS server_url text;
-- 어떤 위험 범주를 검사 범위로 삼았는지. 범위를 남기지 않으면 "발견 0건"이
-- "안전하다"인지 "그 범주를 보지 않았다"인지 구분되지 않는다.
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS risk_scope jsonb NOT NULL DEFAULT '[]';
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS risk_breakdown jsonb NOT NULL DEFAULT '{}';
ALTER TABLE scan_jobs DROP CONSTRAINT IF EXISTS scan_jobs_target_kind_check;
ALTER TABLE scan_jobs ADD CONSTRAINT scan_jobs_target_kind_check
  CHECK (target_kind IN ('intake', 'server', 'endpoint'));
ALTER TABLE scan_jobs DROP CONSTRAINT IF EXISTS scan_jobs_trigger_check;
ALTER TABLE scan_jobs ADD CONSTRAINT scan_jobs_trigger_check
  CHECK (trigger IN ('manual', 'validated', 'rescan', 'drift', 'termination'));

-- 같은 대상이라도 정적 감사와 동적 점검은 서로 다른 작업이다. v1.5의 유일 인덱스는
-- 대상 하나에 살아 있는 작업 하나만 허용했으므로, 폐기 확인용 동적 점검이 정적
-- 재감사 때문에 큐에 들어가지 못하는 일이 생긴다.
DROP INDEX IF EXISTS scan_jobs_one_live_per_target;
UPDATE scan_jobs old SET status='CANCELLED', finished_at=now(),
       error=COALESCE(old.error,'') || ' · 같은 대상·방식의 최신 작업만 남깁니다.'
 WHERE old.status IN ('QUEUED','RUNNING')
   AND EXISTS (SELECT 1 FROM scan_jobs newer
               WHERE newer.target_kind=old.target_kind AND newer.target_id=old.target_id
                 AND newer.kind=old.kind AND newer.mode=old.mode
                 AND newer.status IN ('QUEUED','RUNNING') AND newer.created_at > old.created_at);
CREATE UNIQUE INDEX IF NOT EXISTS scan_jobs_one_live_per_target_mode
  ON scan_jobs(target_kind, target_id, kind, mode) WHERE status IN ('QUEUED', 'RUNNING');

-- catalog 드리프트가 관측된 시각. T4(드리프트 재감사) 트리거가 "마지막 감사보다
-- 뒤에 드리프트가 있었는가"를 이 값으로 판단한다. v1.5는 이 칸이 없어서 트리거
-- 값만 예약된 채 구현되지 못했다.
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS drift_observed_at timestamptz;

-- ── 8. 종료 준비를 도입 시점에 확보한다 (조달 체크리스트) ──────────────────
-- 논문 5.2는 이들 증거가 "개시 시점의 기록 체계와 계약 설계에 의존하므로 소급
-- 확보가 어렵다"고 적는다. 그러면 T3의 구조적 원인을 줄이는 자리는 종료 단계가
-- 아니라 도입 단계다. 끝낼 수 없는 것을 시작하지 않는 것이 유일한 완화다.
--
-- 여기 기록하는 것은 **계약 조항의 존재**이지 제공자가 실제로 고지했다는 사실이
-- 아니다. 둘을 같은 칸에 넣으면 조항만 체크해 두고 C1이 충족된 것처럼 보인다.
-- 조항은 "요청할 권리가 있다"까지이고, 고지는 별도 증거로 들어온다.
ALTER TABLE mcp_intake_requests ADD COLUMN IF NOT EXISTS exit_terms jsonb NOT NULL DEFAULT '{}';

-- 종료 준비도를 서버에도 옮겨 둔다. 도입 요청은 승인 뒤 참조가 끊기지만 종료는
-- 몇 달 뒤에 일어나고, 그때 필요한 것은 "이 서버를 들일 때 무엇을 약속받았는가"다.
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS exit_terms jsonb NOT NULL DEFAULT '{}';

-- 기존 등록 서버는 도입 심사 이전에 들어온 것들이라 약속받은 것이 없다. 빈 값이
-- 곧 "확인되지 않음"이고, 드릴이 그 사실을 최선 등급 T3로 보여준다.
