# OPS-TLS-RECOVERY-R2 검증 근거

기준 `73dfad7884ce3458baeb43ec2fff83ffabd62394`, 작업 시작 clean, 기존 `10/22-runtime-recovery` 유지. 사용자 범위 제한에 따라 branch 변경·원격 HEAD 조회·SSH·배포·서비스 조작·자격 변경은 하지 않는다.

| 원자 요구사항 | 구현 / 근거 | 검증과 한계 |
| --- | --- | --- |
| TLS-R2-01 두 인증서 사건 분리 | [복구 절차](../../integrations/lab/openbao/tls-recovery.md) | backend CA·interop frontend·제품 HTTPS 구분, 원격 실측 미실행 |
| TLS-R2-02 만료를 정상으로 보고하지 않음 | [검사](../../integrations/lab/openbao/check_expiry.py) | 서버·CA 정상/경계/만료/미래/누락/파싱/도구 실패. 파일 기간만 판정 |
| TLS-R2-03 기존 수명·자격 경계 유지 | [prepare.py](../../integrations/lab/openbao/prepare.py), [listener](../../integrations/lab/openbao/server.hcl) | CA·키 교체 없는 운영자 절차. secret/SDK/네트워크 접근 없음 |
| TLS-R2-04 검토 전 적용 금지 | [작업 보고](../../status/reports/2026-10-22-ops-tls-recovery-r2.md) | Gemini 독립 검토·Claude 판단 대기, 고정판 reload 안전성 미확인 |

[회귀](../../../../full_stack_lab/tests/openbao_expiry_test.py)는 날짜 대역과 실제 OpenSSL의 폐기 가능한 합성 인증서만 사용한다. 저장소 안 임시 디렉터리는 finally/context manager로 정리한다. OpenSSL 부재는 실패이며 생략 통과하지 않는다. 시험 결과는 `checks.txt`, 정적 결과는 `static-checks.txt`·`diff-check.txt`에 남긴다. 새로운 단위 시험은 파일 기간 검사 경계만 다루며 실제 MCP·운영 복구 증거가 아니다.
