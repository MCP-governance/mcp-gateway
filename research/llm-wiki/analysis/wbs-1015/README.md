# 2026-10-15 WBS 재산정 근거

[작업 보고](../../status/reports/2026-10-15-wbs-implementation.md)의 점수를 받치는 원자료다. 재산정은 `python -X utf8 research/development-status-site/rescore_1015.py`가 이 파일들을 단정(assert)하며 만든다. 값이 맞지 않으면 산정이 실패한다.

| 파일 | 내용 |
| --- | --- |
| [lab-results.jsonl](lab-results.jsonl) | 최종 병합 소스(3차 배포 판본)에서 돌린 회귀. `kind`: `lab`(공용 격리 실행기 — 실제 PostgreSQL·OPA·Presidio·Gitea MCP), `unit`(게이트웨이 이미지, 저장소 배치), `local`(이 PC·WSL). 한 시험이 두 번 있으면 뒤의 줄이 최종이다 |
| [lab-results-batch1.jsonl](lab-results-batch1.jsonl) | D 병합 전 1차 실행. 실험 환경 차이로 실패한 9건과 그 원인을 그대로 보존 |
| [deploy.json](deploy.json) · [deploy-stage2.json](deploy-stage2.json) | 솔루션 기기 배포 기록: commit, `field up` 결과, 기기 작업본 백업 위치, 네이티브 엔진 동등성, 분석기 이미지 빌드 시각, 포함된 병합 commit |
| [appliance-evidence.json](appliance-evidence.json) | 기기 DB 조회: PJ1 실제 SDK 호출의 판정·구간 시간, 전송 의도, PJ1 망 품질 표본, 수집 기록의 출처·해시 일치, OS 거부 분류, 루프백 차단 포트, 도구 범위 기록, 무효 주석 |

토큰·비밀번호·장치 키는 담지 않는다(주체 값 `root`·`user`는 원장의 식별자다).
