# Claude/Codex 공통 작업 지시

```text
저장소 루트 AGENTS.md와 research/llm-wiki/AGENTS.md부터 읽어줘.
research/llm-wiki/status/current.md와 status/backlog.md를 보고 작업을 이어가줘.

이번 목표: <백로그 ID 또는 확인 가능한 문제 하나>
관련 근거: <논문 / 솔루션 코드 분석 / 원본 위협 ID>
완료 조건: <입력, 기대 판정, upstream 효과, 필요한 검증 층>
시작 참고: analysis/review-2026-10-15/claude-next-work.md와 작업별 레퍼런스 지도를 확인해줘.
새 실행은 run_id·소스 commit·이미지/정책 판본·독립 효과를 연결하고 과거 시험 결과와 구분해줘.

이미 확보한 sources, catalogs, solutions를 먼저 찾아서 재사용해줘.
확인한 커밋·파일·검증 명령과 원본 증거를 남겨줘.
미실행·검증 실패·배포 미확인 상태를 유지해줘.
끝나면 status/current.md와 backlog, 작업 보고서를 갱신하고
tools/capture_status.py, tools/build_wiki.py, tools/check_wiki.py를 실행해줘.
웹 위키는 생성하지 말고 실제 공개 메시지, 작업 시작·중단·완료,
수행한 검증 결과를 research/collaboration-console/console.py emit으로 남겨줘.
```

실험만 맡길 때는 대상 MCP, 테스트 계정의 권한, 정상·공격 입력, 허용된 기기, 독립 효과 확인·정리 절차를 추가합니다. 공급자 자격증명 값은 대화·Git에 붙이지 않습니다.
