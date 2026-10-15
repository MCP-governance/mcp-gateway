# 엔드포인트 로그 수정 검증과 확인할 파일

[최종 보고](../../status/reports/2026-10-14-endpoint-telemetry-fix.md) · [수정 전 진단](../../status/reports/2026-10-14-endpoint-log-wbs.md) · [WBS](../development-wbs/README.md).

PJ1 사용자 계정의 `/home/pj1/mcpgw-telemetry-fix-20261014/logs/ea472c80fae8/`에서 같은 안전한 검사 로그를 읽을 수 있다. 제품은 통제 범위 → 미등록·잔존에서 확인한다.

| 파일 | 확인할 내용 |
| --- | --- |
| [automatic-check.jsonl](pj1-live/automatic-check.jsonl) | 실제 주기 수집·독립 journal 예상 이벤트·수신·프로세스 제거·오류·복구 시각 |
| [delivered.json](pj1-live/delivered.json) | 합성 marker의 hashed 명령, 실제 OS 보관 표본1388, 채널별 상태 |
| [result.json](pj1-live/result.json) | 관리UID 자동 수집·다른UID 제외·복구 조건, 합성/실제 범위 |
| [replay-result.json](pj1-live/replay-result.json) | 주기 수집기의 실제 동일 이벤트 재전송 후 id/최초수신/행1개 보존 |
| [checks.json](checks.json) | 단위/정적 검사별 환경·실제 결과와 보존된 실행 오류 |
| [pg-snapshot-deployed.jsonl](pg-snapshot-deployed.jsonl) | 전용 schema8조건 PASS/rollback/초기화·삭제, 배포 image 실행 |
| [deployment.json](deployment.json) | 실제 source SHA·DB/registry 보존·readiness 및 kit mount 최종 갱신 |
| [pj1-update.json](pj1-update.json) | PJ1 설치3파일 SHA·기존 집행 점검·수집 scope |
| [source-reviewed.json](source-reviewed.json) | 로컬 source SHA와 원격 호환 prepared source를 구분 |

원문 명령·device key·JWT·raw journal은 이 정본에 없다. 루트관리자에 대한 원격 attestation, 실제 MCP 모델 turn, Windows 실기기 및 전 이벤트 무손실을 의미하지 않는다.
