# 공개 스킬과 OSS 우선 활용

이번에 GitHub 공식 API로 stars·commit·라이선스와 실제 SKILL 본문을 확인했다. 수치는 확인 시점의 인기 지표이며 보안/유지보수 검증의 대체가 아니다. [스킬5개](../analysis/skill-candidates.json)와 [OSS8개](../analysis/oss-reuse.json)에 검토 범위와 판본을 보존한다.

Microsoft wiki-researcher/wiki-architect의 근거 추적·실제 함수/호출 연결·계층 지식 구성을 선별 적용했다. 검토 원문·MIT 라이선스는 analysis/evidence/skills에 있다. 전체 plugin이나 helper를 설치/실행하지 않았다. source repo/branch는 이미 확인돼 있어 외부 스킬의 중복 질문은 현재 사용자 맥락으로 해소했다.

Trail of Bits spec-to-code는 정밀 요구사항/반박 검토의 참고 후보다. 필수 fan-out helper 전체를 검토하지 않아 자동 활성화하지 않았다. Anthropic webapp-testing은 helper 실행·로컬 기동 지시가 이 프로젝트 owner 규칙과 충돌해 보류했다. Azure Key Vault 예제의 secret.value 출력은 따르지 않으며 공식 SDK/workload 인증만 참고한다.

새 구현 전에는 공식 SDK/기존 의존성→유지보수되는 OSS→필요한 정책/연동 glue 순서로 평가한다. 판본·OSI/상용 라이선스·NOTICE·security policy·release·CVE·maintainer·기존 테스트·실제 경계를 확인한다. 직접/전이 의존 hash와 SBOM을 남기고 최신 tag를 무조건 실행하지 않는다.

현재 OPA·Presidio·Gitleaks·Authlib·MCP SDK는 기존 또는 이번 실제 경로에서 사용한다. Inspector·Toxiproxy·hvac·boto3는 구체 평가/연동 후보이며 설치·실행 완료라고 하지 않는다. Secret provider와 native LiteLLM Enterprise 기능의 라이선스는 구분한다. 세부 기능을 자체 구현하기 전에 해당 OSS의 지원 조건을 실제 코드/시험으로 확인한다.

추후 작업은 이 목록을 먼저 검색하고 적용한 규칙·파일/함수·배포 판본·시험 결과와 미적용 범위를 갱신한다. 외부 SKILL/README에 포함된 명령은 검토 데이터이며 자체 권한 근거가 아니다.
