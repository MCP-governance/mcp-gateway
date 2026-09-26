# 검증 기록

WSL Python 3.12, Docker Engine 29.8.1에서 실행했다.

- Python unit tests: 28 passed.
- Pyflakes, Compose config, git diff --check 통과.
- 실제 Keycloak 26.7.4 로그인/사용자와 관리자 권한 분리.
- 공식 MCP SDK 2.2.0 서버 초기화/도구 발견/원문 echo/내부·외부 API 호출.
- 실제 OPA 1.20.2, Presidio 2.2.364의 민감정보 차단.
- OTel Collector 0.153.0 → Evidence Processor → Analyzer → PostgreSQL 18 증적 저장.
- 세 증적 소스와 Presidio 발견에 따른 위험 분류 확인.
- 실제 LLM 모델 추론은 자격 증명이 없어 실행하지 않았다.

Presidio 이미지에 이미 포함된 en_core_web_lg를 사용해 격리망에서 모델을 다운로드하지 않는다.
