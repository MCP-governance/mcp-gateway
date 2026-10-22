# OPS-TLS-RECOVERY-R2 검증 근거

기준 `73dfad7884ce3458baeb43ec2fff83ffabd62394`, 작업 시작 clean, 기존 `10/22-runtime-recovery` 유지. 사용자 범위 제한에 따라 branch 변경·원격 HEAD 조회·SSH·배포·서비스 조작·자격 변경은 하지 않는다.

| 원자 요구사항 | 구현 / 근거 | 검증과 한계 |
| --- | --- | --- |
| TLS-R2-01 두 인증서 사건 분리 | [복구 절차](../../integrations/lab/openbao/tls-recovery.md) | backend CA·interop frontend·제품 HTTPS 구분, 원격 실측 미실행 |
| TLS-R2-02 만료를 정상으로 보고하지 않음 | [검사](../../integrations/lab/openbao/check_expiry.py) | 서버·CA 정상/경계/만료/미래/누락/파싱/도구 실패. 파일 기간만 판정 |
| TLS-R2-03 기존 수명·자격 경계 유지 | [prepare.py](../../integrations/lab/openbao/prepare.py), [listener](../../integrations/lab/openbao/server.hcl) | CA·키 교체 없는 운영자 절차. secret/SDK/네트워크 접근 없음 |
| TLS-R2-04 검토 전 적용 금지 | [작업 보고](../../status/reports/2026-10-22-ops-tls-recovery-r2.md) | Gemini 독립 검토·Claude 판단 대기, 고정판 reload 안전성 미확인 |

[회귀](../../../../full_stack_lab/tests/openbao_expiry_test.py)는 날짜 대역과 실제 OpenSSL의 폐기 가능한 합성 인증서만 사용한다. 저장소 안 임시 디렉터리는 finally/context manager로 정리한다. OpenSSL 부재는 실패이며 생략 통과하지 않는다. 시험 결과는 `checks.txt`, 정적 결과는 `static-checks.txt`·`diff-check.txt`에 남긴다. 새로운 단위 시험은 파일 기간 검사 경계만 다루며 실제 MCP·운영 복구 증거가 아니다.

## OPS-TLS-RELOAD-SOURCE 후속 (2026-10-22)

기준 `ca368bff78b12608b132bdc98851b035bce542b6`, 시작 clean, 같은 branch, 문서 3개만 미커밋 변경한다. 원본 구현·회귀 결과는 위 기준의 이력이며 이번에 재실행한 것으로 세지 않는다.

| 원자 요구사항 | 실제 근거 / 결과 | 미확인 범위 |
| --- | --- | --- |
| TLS-SRC-01 공식 release 고정 | [공식 v2.7.1](https://github.com/openbao/openbao/releases/tag/v2.7.1)의 `a5db72c` 표시, [provenance](../../integrations/lab/openbao/provenance.json)의 전체 commit·MPL-2.0 | 고정 source 본문으로 전체 commit 독립 재확인 못함 |
| TLS-SRC-02 reload 기호·행·실패 동작 | [후속 정본](../../integrations/lab/openbao/tls-recovery.md#ops-tls-reload-source-후속--고정-구현-확보-차단)의 공식 URL별 연결 실패·Cache miss·404 기록 | 2.7.1 reload 등록/dispatch·pair 파싱·캐시 교체·오류 처리·audit 경로 미확보. 재시도 중단 |
| TLS-SRC-03 기본 entrypoint와 로컬 설정 분리 | 보존 Dockerfile L48-54와 LICENSE L1-3 확인, SHA-256 두 건 모두 provenance 일치. Compose L3-7·L20-31, listener L11-19 대조 | 스크립트 본문·실기기 image/override/init/PID1 미검증 |
| TLS-SRC-04 안전 전제와 미보증 실패 구분 | 현재 공식 TCP 문서의 시작 경로·동일 passphrase 전제와 별도 자동 reload 옵션 확인. 같은 정본의 조건표에 지원/미확인 구분 | 만료/파싱/키 불일치/권한 실패 시 기존 인증서 보존이나 프로세스 생존 보증 없음. 구판 issue를 2.7.1 증거로 사용 안 함 |

후속 검사: 보존 공식 파일 SHA-256 2건 일치, 허용 Markdown 3개 링크·변경 범위·`git diff --check` 통과. 전체 위키 생성/기록기·회귀 재실행·실기기 시험은 하지 않았다. 이 후속의 실제 검사와 공백은 [동일 작업 보고의 후속 절](../../status/reports/2026-10-22-ops-tls-recovery-r2.md#ops-tls-reload-source-후속-구현-기록)에 기록한다.

다음 운영자 확인은 후속 정본의 실제 PID1 실행 경로·server 인자 읽기 전용 대조 하나다. `WORK_STATUS: BLOCKED` — 고정 release reload 본문을 확보하지 못해 구현·실패 동작 조사 완료를 주장하지 않는다.
