-- 실습 스택 전용 합성 계정. 실습 compose(full_stack_lab/compose.yaml)만 init.sql 다음에 싣는다.
-- 운영 배포(deploy/compose.yaml)는 싣지 않는다(tests/seed_split_check.py).
-- 합성 계정. 비밀번호는 기동할 때 agent-service가 MOCK_SSO_PASSWORD로 채운다
-- (agent_tables.sql의 bootstrap). 해시를 SQL에 박아두면 .env로 바꿀 수 없다.
INSERT INTO principals(token, user_id, email, display_name, role, department, employee_no, job_title) VALUES
  ('admin-demo',   'user-admin-001',   'kkg@bob.local',  '김경곤', 'admin',    '거버넌스팀',   'EMP-001', '거버넌스팀 관리자'),
  ('admin-mks',    'user-admin-002',   'mks@bob.local',  '문광석', 'admin',    '보안운영팀',   'EMP-002', '보안운영팀 관리자'),
  ('emp-pse',      'user-emp-001',     'pse@bob.local',  '박소은', 'employee', '보안기술팀',   'EMP-101', '보안기술팀 사원'),
  ('emp-demo',     'user-test-001',    'miso@bob.local', '김미소', 'employee', '보안기술팀',   'EMP-102', '보안기술팀 사원'),
  ('emp-ysg',      'user-emp-003',     'ysg@bob.local',  '양승권', 'employee', '플랫폼개발팀', 'EMP-103', '플랫폼개발팀 사원'),
  ('emp-jwj',      'user-emp-004',     'jwj@bob.local',  '정원재', 'employee', '데이터분석팀', 'EMP-104', '데이터분석팀 사원'),
  ('partner-demo', 'user-partner-001', 'nkk@bob.local',  '권노경', 'partner',  '협력사 A',     'EXT-001', '협력사 직원')
ON CONFLICT (token) DO UPDATE SET
  user_id=EXCLUDED.user_id, email=EXCLUDED.email, display_name=EXCLUDED.display_name,
  role=EXCLUDED.role, department=EXCLUDED.department, employee_no=EXCLUDED.employee_no,
  job_title=EXCLUDED.job_title;
