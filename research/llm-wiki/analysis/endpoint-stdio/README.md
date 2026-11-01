# 승인 stdio 소스의 엔드포인트 프로세스 실행

- 기준: `91524ab5e0d53f08439e8233aa44b979ca0cfd63`, 브랜치 `10/28-endpoint-stdio`.
- 결정: [D-299](../../../../docs/ai/decisions/D-251-300.md#d-299-승인-소스형-stdio-mcp는-기존-로컬-작업으로-엔드포인트-프로세스에서-실행한다-2026-10-28).
- 정본: [원자 요구사항](requirements.json), [실제 로컬 시험 결과](test-results.json), [작업 보고](../../status/reports/2026-10-28-endpoint-stdio.md).
- 증거: 소스·계약·인가의 대역 단위 시험 및 일반 자식 프로세스의 Windows 수명 시험이다. 자체 MCP 서버는 만들지 않았다. 실제 OSS MCP, Gitea/DB, 모델 하네스, 배포·PJ1·pj3 검증으로 세지 않는다.
- 미완료: Git index.lock 권한, Linux 실행, Windows 서비스 토큰 축소·공유 Python의 독립 네트워크 격리, 잠금이 없는 승인 커밋의 패키징 검토. 동시 준비·실제 패키지 네트워크 설치·실기기 장애 복구는 코드/설계와 시험된 효과를 분리해 후속 확인한다.

## 2차 현재 상태

기준 `0c0bb151`에서 1차의 SYSTEM 실행·수동 잠금·솔루션 native HTTP 실행 유지를 대체했다. [2차 검증](test-results-round2.json)은 별도 보존하며 1차 검증 JSON을 덮어쓰지 않는다. 현재 원자 요구사항은 2차 코드 해시에 결속한다. Windows 직원 토큰 생성·실제 OSS/스캐너·배포는 미실행이며, 보류한 wheel 미러와 플랫폼 제한은 작업 보고의 2차 한계를 따른다.
