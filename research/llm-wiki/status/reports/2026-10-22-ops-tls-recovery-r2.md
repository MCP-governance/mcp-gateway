# 2026-10-22 OPS-TLS-RECOVERY-R2

- 작업자: Codex, implement, job `wf-OPS-TLS-RECOVERY-R2-implement-0`.
- 기준: `73dfad7884ce3458baeb43ec2fff83ffabd62394`, 시작 clean, 기존 `10/22-runtime-recovery` 유지. 사용자 지시로 branch 변경·원격 HEAD 조회·SSH·push·merge·배포는 하지 않았다.
- 시작 근거: 사용자가 제공한 2026-10-22 12:51 KST OpenBao 만료 관측. 원격 원본은 재확인하지 않았다.
- 완료 범위: 기존 구현의 수명 검토, 읽기 전용 파일 만료 검사, 격리 회귀, 운영자 복구 제안. 운영 복구 완료를 의미하지 않는다.

## 결과

[복구 절차](../../integrations/lab/openbao/tls-recovery.md)는 prepare의 CA 30일·leaf 7일·기존 runtime 거부를 근거로 기존 CA/서버 키 유지 재발급, staging·검증·reload 전제와 실패 중단을 기록한다. interop backend, Caddy frontend, 제품 HTTPS와 Windows Schannel 오류를 구분한다. 기존 provisioning·Compose·listener·SDK·정책·자격은 수정하지 않았다.

[검사](../../integrations/lab/openbao/check_expiry.py)는 `server.pem`·`ca.pem`만 읽어 기본 48시간 경계까지 실패로 반환한다. 현재 만료·미래 notBefore·CA 만료·누락·파싱/실행/timeout 오류도 종료 1이다. 네트워크·인증서 발급·secret 값 접근·서비스 조작은 없다. 출력은 기간·역할별 상태이며 인증서 본문·키·원문 오류를 출력하지 않는다.

[회귀](../../../../full_stack_lab/tests/openbao_expiry_test.py)는 날짜 대역과 실제 OpenSSL을 사용한다. 합성 키·인증서는 저장소 안 임시 디렉터리에서만 생성·정리하며 실기기 자격과 무관하다. 실제 MCP·OpenBao 가동 시험은 아니다. [요구사항 연결과 증거](../../analysis/ops-tls-recovery-r2/README.md)에 검사 범위를 연결했다.

## 검증

| 검사 | 환경·명령 | 실제 결과·증거 |
| --- | --- | --- |
| 격리 회귀 | Windows Python 3.10.5, OpenSSL 3.5.7; `python -B -X utf8 -m unittest discover -s full_stack_lab/tests -p openbao_expiry_test.py -v` (`OPENBAO_TEST_OPENSSL`로 Git OpenSSL 경로 지정) | 10건 통과, 생략 없음; [원본](../../analysis/ops-tls-recovery-r2/checks.txt), 2026-10-22 05:14 UTC |
| Python 정적 검사 | 두 변경 Python 파일 `ast.parse` | 통과; [원본](../../analysis/ops-tls-recovery-r2/static-checks.txt) |
| 범위별 문서·공백 검사 | 새 Markdown 3개 로컬 링크 15개, `git diff --check` 및 새 파일 trailing whitespace 확인 | 통과; 위 정적 원본과 [diff 결과](../../analysis/ops-tls-recovery-r2/diff-check.txt) |
| 실기기·실통신·PJ1·Schannel | 사용자 금지 범위 | 미실행. 만료 해소·health 복귀·제품 HTTPS 정상화 주장 없음 |

## 실패·미완료·한계

- `rg`, PATH의 Python/OpenSSL은 없어 PowerShell 파일명 조회와 설치된 절대 실행 파일을 사용했다. 첫 PowerShell stderr 병합 출력은 NativeCommandError 형식으로 표시됐지만 시험 exit 0이었다. 증거 파일은 동일 회귀의 재실행 결과를 UTF-8로 기록했다.
- OpenBao [공식 2.7.x listener 문서](https://openbao.org/docs/configuration/listener/tcp/)는 SIGHUP 재독해를 설명한다. [2.7.1 release](https://github.com/openbao/openbao/releases/tag/v2.7.1)의 commit prefix는 기존 provenance와 일치하지만, 고정판 reload source URL 조회는 실패했다. 구판 SIGHUP crash 보고의 적용 여부도 미확인이다. 실행 판본·PID1·reload 안전성 확인 전 signal 적용은 보류한다.
- 로컬 파일 기간 검사 통과는 서명·체인·SAN·실제 제공 leaf·서버 상태의 증거가 아니다. 운영자가 런북의 단계별 검증을 별도 수행해야 한다. Windows `0x80096004`의 원인은 미확정이며 제품 인증서 만료로 추정하지 않았다.
- 사용자 한정 범위에 따라 전체 위키 capture/build/check·협업 기록기 변경 대신 관련 문서 링크만 검사했다. 이 보고는 전체 위키 검사를 통과했다고 주장하지 않는다.
- **Gemini 독립 검토 PASS와 사용자 역할 규칙의 Sol 대행 원문 검토 PASS를 확인했다.** 다른 에이전트 호출·worker ask/add·CLI 중첩은 수행하지 않았다.

## 다음 작업

운영자가 실제 PID1 실행 경로·server 인자를 읽기 전용으로 확인해 저장소 Compose와 대조한다. 아래 후속의 고정 구현 공백과 signal 보류는 유지한다.

## 사용자에게 필요한 입력

현재 로컬 제안 완료에는 없음. 운영 적용 권한·기기 증거·자격 값은 요청하거나 취득하지 않았다.


## 조정자의 후속 검증·소스 통합 (18:53 KST)

고정 manifest의 source fingerprint가 현재 미커밋 변경과 같음을 다시 확인했다. Gemini PASS 뒤 Opus 구독 대기 중의 Sol 대행이 원문·diff·기존 provisioning/listener/Compose/Caddy를 읽기 전용으로 대조해 PASS했다. 첫 Sol 판정은 이전 Claude용 셸 금지와 도구 구성 차이로 BLOCK이었고 원본을 보존했다. 같은 Sol·같은 읽기 전용 권한에서 파일 조회 명령만 허용한 후속 판정은 `loop/agent-hub/runtime/results/TLS-R2-SOL-READ-0239e35b.md`다. 안전 거절·실행 정책을 우회하지 않았다.

조정자가 Windows의 Git OpenSSL 경로를 해당 검사 프로세스 PATH에만 추가하고 `python -X utf8 full_stack_lab/tests/openbao_expiry_test.py`를 실행해10건 통과했다. 기본 PATH의 첫 실행은 OpenSSL 미발견으로9통과/1실패였으며 실패 기록은 그대로 둔다. 위의 최초 구현 기록과 달리 현재는 소스 통합·커밋 대상이다. 인증서 갱신·신뢰 저장소 변경·원격 배포·재시작·PJ1 검증은 하지 않았다.

## OPS-TLS-RELOAD-SOURCE 후속 구현 기록

- 담당: sol, implement, job `wf-OPS-TLS-RELOAD-SOURCE-implement-0`.
- 기준 commit: `ca368bff78b12608b132bdc98851b035bce542b6`, branch `10/22-runtime-recovery`, 시작 clean. 이전 검토 보고는 증거로만 취급했다.
- 변경: 기존 [복구 정본](../../integrations/lab/openbao/tls-recovery.md)·[분석 README](../../analysis/ops-tls-recovery-r2/README.md)·이 보고만 수정, 미커밋. 새 branch·보고·의존성·서비스 없음.

### 실제 결과

[공식 v2.7.1 릴리스](https://github.com/openbao/openbao/releases/tag/v2.7.1)의 tag·`a5db72c` 표시를 확인했다. 기존 provenance의 전체 commit은 `a5db72cef75c24b920ade02065b18dd8eb666bac`, 라이선스는 MPL-2.0이다. 기존 보존 Dockerfile의 `USER` L48-49·`COPY`/`ENTRYPOINT` L51-54, LICENSE L1-3을 읽고 SHA-256 두 건이 provenance와 일치함을 확인했다. 정확한 공식 URL·전체 hash·실패 URL/접근별 결과는 복구 정본의 후속 절에 남겼다.

로컬 Compose L3-7은 고정 image·UID/GID·직접 `/usr/bin/bao server` 설정·`unless-stopped`이며, 기본 이미지 Dockerfile의 스크립트 entrypoint와 구분된다. 실제 실행 중인 PID1·override/init·image는 확인하지 않았다. listener L11-19의 고정 cert/key 경로·TLS 1.3·ACME 비활성·자동 reload 미설정을 확인했다.

현재 [공식 TCP 문서](https://openbao.org/docs/configuration/listener/tcp/)는 SIGHUP에서 시작 시 cert/key 경로를 사용하고 암호화 키 passphrase를 유지하도록 설명한다. 이 문서는 변경 가능하므로 고정 release 구현으로 세지 않았다. 누락·잘못된 PEM·키 불일치·권한·만료 시 기존 인증서 유지/오류 반환/프로세스 생존은 단정하지 않았다. 구판 [issue #3138](https://github.com/openbao/openbao/issues/3138)의 Closed/`cannot reproduce` 표시는 2.7.1 수정 또는 재현 증거가 아니다.

### 실제 검사·공백

| 검사 | 결과 |
| --- | --- |
| 보존 공식 Dockerfile·LICENSE SHA-256 대조 | 2건 모두 기존 provenance와 일치 |
| 고정 commit listenerutil raw / blob 조회 | PowerShell 연결 실패, 공개 웹 raw/blob Cache miss. 본문 미확보 |
| tag command/server.go raw / 공식 tag tree | 각각 조회 도구 404 / Cache miss. 실제 파일 경로·구현 부재를 뜻하지 않음 |
| 허용 문서 로컬 링크·변경 파일 범위·공백 검사 | 통과, `git diff --check` 종료 0. 이 후속에서 새 검사 산출물 파일은 만들지 않음 |
| reload 등록·dispatch·pair 파싱·캐시 교체·audit 실패 경로의 2.7.1 기호/행 | 미확보. 현재 main·구판 trace로 대체하지 않고 재시도 중단 |
| 실기기 PID1·제공 leaf·reload·복구 효과 | 미실행. SSH·컨테이너/서비스 호출·signal·인증서/비밀 읽기·자격 변경·배포 없음 |

허용 파일 제한에 따라 status/current·backlog·전체 위키 capture/build/check·협업 기록기는 변경/실행하지 않았다. 기존 회귀 10건은 앞선 작업의 결과이며 이 문서 후속에서 재실행하지 않았다. signal 보류는 유지한다.

다음 행동은 운영자의 **실제 PID1 실행 경로·server 인자 읽기 전용 대조** 하나다. 고정 release 소스 공백은 별도로 미해결이며 이 확인이 signal 적용을 승인하지 않는다.

`WORK_STATUS: BLOCKED` — 고정 OpenBao 2.7.1 reload 본문을 확보하지 못해 정확한 구현과 실패 동작을 입증할 수 없음.
