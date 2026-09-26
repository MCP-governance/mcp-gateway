# 구조도 브랜치 작업 규칙
사용자가 제공한 draw.io의 제1안/제2안이 기준이다. 초안과 기존 main의 직원 PC 실습은 포함하지 않는다.
research/는 멘토 소유이며 변경하거나 삭제하지 않는다. 서비스 경계, 실제 외부 제품과 테스트 대역을 문서에서 구분한다.
사용자 토큰을 MCP upstream에 보내지 않는다. 인증/정책 실패는 실행 전에 차단한다.
pytest, Compose config, HTTP/MCP 통합 시험과 git diff --check를 실행한다.
