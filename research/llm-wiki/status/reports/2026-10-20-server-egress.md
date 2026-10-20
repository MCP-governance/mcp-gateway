# 2026-10-20 서버 외부 통신 사건과 호출 상관

- 작업자: Codex sol
- 코드 기준: `10/20-server-egress`, 시작 `89aad130cefc290c2705aff4954086d58d270381`, 시작 작업 트리 clean. 변경은 미커밋 상태로 남긴다.
- 시작 근거: DEV-20, D-114·D-111·D-116·D-132·D-145, [Lunar 분석](../../solutions/lunar-mcpx.md), [팀 시험 계획](2026-10-13-mcp-validation-plan.md).
- 해결할 문제와 완료 조건: 기존 서버 egress 집행과 실제 사건을 호출 원장에 연결한다. 목적지·허용/차단을 기록하되 자격·재시도·독립 효과가 관측되지 않는 범위는 남긴다. DEV-20 전체 완료 판정은 보류한다.
- 변경 파일: `full_stack_lab/runtime/{worker.py,Dockerfile}`, `full_stack_lab/gateway/app/{server_egress.py,endpoint_plane.py,agent_static/console.js}`, 새 `full_stack_lab/tests/server_egress_check.py`, D-155, [분석 정본](../../analysis/server-egress/README.md), 이 보고서, 백로그 DEV-20 상태 칸. `status/current.md`는 사용자 지시에 따라 유지한다.
- 원격 기본 HEAD 재확인: `git ls-remote --symref origin HEAD`는 GitHub 연결 실패. 이미 제공된 작업 브랜치를 유지했다.

## 결과

실행기가 엔진 소유 tinyproxy의 연결·필터 거부·접속 실패 로그에서 목적지와 관측 시각을 추출하고 기존 append-only 감사 사건에 저장한다.
서버별 행 잠금·사건 ID 중복 검사·겹친 로그 수집·원자적 커서 기록으로 재수집을 처리한다.
목적지 승인 목록 변경과 수집 장애가 겹치면 옛 프록시를 제거하고, 다른 서버의 철회 처리는 계속한다.
서버 전용 망·허용 목록·권한과 실제 MCP 판정은 기존 경계를 유지한다.

기존 관리자 호출 상관 조회와 「연관 이벤트」에 같은 서버·전송 실행 구간의 사건을 보조 근거로 붙였다.
원장 판정·신원은 고치지 않으며 임의 프록시 로그를 직원의 실행 증거로 승격하지 않는다.
콘솔은 한국어 라벨과 상태만 추가했다. 신규 라우트·DB 구조·의존성·정책 ID·자체 MCP 서버는 없다.
자격 사용은 미관측, API 재시도 횟수는 미확인, 독립 외부 업무 효과는 미확인이다.

## 검증

2026-10-20 로컬 Windows / Python 3.10에서 실행. 아래 결과는 기기 배포 증거가 아니다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 새 순수 함수·DB/엔진 대역 | `python -B -X utf8 -m unittest discover -s full_stack_lab/tests -p server_egress_check.py -v` | 15건 통과 | [로컬 실행 기록](../../analysis/server-egress/local-checks.txt) |
| 기존 상관 회귀 | 같은 discover, `-p event_correlation_check.py` | 5건 통과 | 같은 기록 |
| 기존 콘솔 상태 | `node --test full_stack_lab/tests/console-state.test.mjs` | 15건 통과 | 같은 기록 |
| 구문·공백·인증 | 변경 Python 4파일 `python -m py_compile`, `node --check full_stack_lab/gateway/app/agent_static/console.js`, `git diff --check`, `python -B -X utf8 full_stack_lab/tests/open_endpoints.py` | 통과 | 같은 기록 |
| 기존 실행기 회귀 | `python -B -X utf8 -m unittest discover -s full_stack_lab/tests -p runtime_worker_check.py -v` | 실행 실패: Python 3.10에 `tomllib` 없음 | 같은 기록, 기대값 변경 없음 |
| pyflakes | 변경 Python 4파일 `python -m pyflakes` | 실행 불가: 미설치 | 같은 기록 |
| 실제 PostgreSQL·프록시·기기 이미지 | 아래 기기 명령 | 미실행 | 없음 |
| 실제 모델·하네스 / upstream 독립 효과 / 배포·정책 해시 | 아래 PJ1·기기 절차 | 미실행 / 미확인 / 미확인 | 없음 |

신규 시험 작성 중 event INSERT 시험이 SELECT 전용 대역을 재사용해 실패한 1건은 별도 연결 대역으로 고쳤다.
제품의 event INSERT와 기존 시험은 바꾸지 않았다. 실제 DB commit/롤백/경합 보장은 대역 결과만으로 확정하지 않는다.

## 솔루션 기기에서 실행할 검사

메인이 변경을 검토·반영한 뒤 `user@100.83.175.111`의 이 저장소 `full_stack_lab`에서 실행한다.
로컬 노트북에는 스택을 띄우지 않는다. 기기에서도 새 스택 대신 승인된 `./console.sh field up`을 쓴다.
아래 `GATEWAY_CONTAINER`에는 해당 프로젝트의 실제 게이트웨이 컨테이너 ID만 넣는다.

```bash
cd full_stack_lab
./console.sh field up
GATEWAY_CONTAINER=<해당-프로젝트-게이트웨이-ID>
GATEWAY_IMAGE=$(docker inspect --format '{{.Config.Image}}' "$GATEWAY_CONTAINER")
docker run --rm --network none -v "$PWD:/workspace:ro" -w /workspace --entrypoint python "$GATEWAY_IMAGE" -B -m unittest discover -s tests -p server_egress_check.py -v
docker run --rm --network none -v "$PWD:/workspace:ro" -w /workspace --entrypoint python "$GATEWAY_IMAGE" -B -m unittest discover -s tests -p event_correlation_check.py -v
docker run --rm --network none -v "$PWD:/workspace:ro" -w /workspace -e PYTHONPATH=/workspace/supply_chain --entrypoint python "$GATEWAY_IMAGE" -B -m unittest discover -s tests -p runtime_worker_check.py -v
```

`field up` 뒤 runtime-worker 이미지에 `server_egress.py`가 포함됐는지 확인한다.
실제 프록시의 `tinyproxy -v`, Docker 이미지 ID와 `mcpgw.runtime`·`mcpgw.role` 표식을 기록한다.
기존 Alpine 이미지 태그는 패키지 판본을 고정하지 않아 새 파서와 실제 로그 형식 일치 확인이 필요하다.

## 실기기 허용/차단·독립 효과 확인 절차

1. 기존 승인 OSS MarkItDown 실행기 하나와 합성 자료만 사용한다. runtime·generation·MCP/프록시 컨테이너·이미지 ID,
   해당 도구의 승인 destinations·목적·등급·자격 유형만 기록한다. 자격 원문·직원 토큰은 인자/환경/로그로 옮기지 않는다.
   기존 승인 호스트에서 운영자가 수신 기록을 확인할 수 있는 합성 자료 URL과 미승인 호스트의 격리 수신 대상을 사용한다.
   새 업무 권한·새 목적지 승인·새 자체 MCP 서버는 만들지 않는다. 독립 수신 기록 접근이 없으면 효과 시험은 미실행이다.
2. 실행기 MCP 컨테이너 내부에서 다음 stdlib 프로브를 승인 URL과 미승인 URL 각각에 한 번씩 실행한다.
   이는 egress 망 프로브이며 MCP 호출 성공 증거가 아니다. 승인 대상은 정상 HTTP 상태/독립 수신 기록, 미승인 대상은 403/독립 수신 0을 요구한다.

```bash
MCP_CONTAINER=<해당-runtime의-MCP-컨테이너-ID>
PROBE_URL=https://<기존-허용-호스트>/<합성-자료-경로>
docker exec -i "$MCP_CONTAINER" python - "$PROBE_URL" <<'PY'
import sys
import urllib.error
import urllib.request
try:
    with urllib.request.urlopen(sys.argv[1], timeout=15) as response:
        print('http_status', response.status)
except urllib.error.HTTPError as exc:
    print('http_status', exc.code)
except Exception as exc:
    print('connection_error', type(exc).__name__)
    raise
PY
```

   URL에는 자격·개인정보를 넣지 않는다. 미승인 대상으로 `PROBE_URL`을 바꾸고 같은 명령을 반복한다.
   추가로 기존 D-114와 같은 프록시 우회 직접 연결·메타데이터 접근 음성 프로브를 승인된 격리 범위에서 재확인한다.
   이번 수집기는 프록시 우회 실패를 기록하지 않으므로 그런 사건이 없는 것을 프로브 성공으로 세지 않는다.
3. 수집 주기 뒤 DB에서 `approval_events.kind=runtime-egress`의 `scope`와 runtime의 `egress_log_cursor`를 조회한다.
   각각 connected/blocked, 목적지, Docker 시각, 컨테이너·이미지·세대와 사건 ID를 대조한다. 사건이 없으면 수집 미확인으로 실패 처리한다.
   worker 로그 수집/DB 장애·10,000행 상한은 오류이며 새 성공 커서가 없어야 한다. 원래 로그에는 URL이 있을 수 있어 원문을 공개 보고에 복사하지 않는다.
4. PJ1(`pj1@100.110.81.60`)의 실제 관리 하네스에서 같은 MarkItDown 도구를 승인 URL로 호출한다.
   실제 `decision`·`policy_id`·request_id·trace_id·intent와 업무 결과를 대조하고, 관리자 인증으로
   `/api/endpoint/correlation?decision_id=<판정-ID>`를 조회한다. 사건 시각이 intent~원장 기록 안일 때만 보조 근거로 표시돼야 한다.
   호출 전에 수행한 단독 프로브는 이 호출과 연결되면 실패다. 도구가 기존 TLS 터널을 재사용하면 새 연결 사건이 없을 수 있으며 관측 없음으로 기록한다.
5. 실행 시간이 겹치는 두 호출은 동일 사건이 각각 후보로 보일 수 있다. 어느 것도 정확 연결로 나오면 안 된다.
   다른 서버/전송 전/후 사건은 제외해야 한다. 게이트웨이가 인자 단계에서 미승인 URL을 막은 호출은 intent·서버 사건이 없는 정상 음성이다.
   외부 403을 게이트웨이 `MCP-EGRESS` 정책 차단이라고 재분류하지 않는다.
6. 동일 합성 URL 요청을 두 번 실행하고 두 연결 사건을 확인하되 이를 API 재시도 1회로 세지 않는다.
   API 재시도·자격 사용을 확정하려면 기존 외부 API/공식 SDK 관측의 요청 ID·상태·자격 식별자(원문 제외)가 추가로 필요하다.
   독립 수신/업무 로그의 합성 표식·관측 시각·해시와 게이트웨이 후보 요청·사건 ID를 검증 보고 표에 함께 기록한다.
   연결 확인만 있고 외부 업무 로그가 없으면 효과는 미확인이다. 이번 API의 `external_effect`는 계속 unverified다.
7. 수집기 재시작 후 같은 사건 ID가 중복되지 않는지, 승인 destinations 변경 시 옛 프록시가 없어지는지 확인한다.
   다른 사람이 실행 중인 종료 케이스·스택은 중단하지 않는다. 합성 자료는 소유한 자원만 `finally`로 정리한다.

## 기존 시험 변경 필요

없음. 기존 파일의 기대값·fixture는 변경하지 않았다. 로컬 실행기 회귀의 import 실패는 지원 Python/이미지에서 재실행한다.

## 실패·미완료·한계

15개 신규 시험은 생산 함수 본문의 AST와 AsyncMock/DB·Docker 대역이며 MCP 실행 증거가 아니다.
실제 DB 잠금/롤백·동시 worker·로그 형식/회전·브라우저 렌더링·배포·PJ1은 미실행이다.
프록시 공유, DNS/IP 재결속, 연결 풀과 TLS 내부의 자격·재시도, 제3자 GitHub/Context7의 outbound는 입증하지 못한다.
종료/재생성 직전 최종 로그와 빌드 중 수집 지연으로 기록이 빠질 수 있다. 200건 조회는 상한 여부만 반환한다.
관측 채널은 호출 허가 조건이 아니며, 필터가 그대로이면 수집 장애 중 기존 통신은 계속 가능하다.
DEV-20은 구현된 목적지/결과 사건과 미확인 자격/재시도/독립 효과를 분리한 부분 구현이다.

## 다음 작업

메인이 기기 이미지 검사→실제 DB 경합/복구→기존 프로브 5종 재실행→PJ1 호출과 독립 수신 로그를 대조한다.
DEV-20 완료 여부는 그 결과와 API 자격/재시도/효과 관측 범위로 판단한다. DEV-41의 서버 DNS/IP 통제·프록시 공유 제한은 별도 공백이다.

## 사용자에게 필요한 입력

없음. 현재 승인·격리 자원으로 진행할 수 있는 절차를 남겼으며, 독립 수신 로그 접근이 없는 항목은 미실행으로 유지한다.

## 기기 실행 (Claude, 2026-10-20)

- 브랜치 355888a를 솔루션 기기에 배포하고 PJ1 관리 Claude Code로 markitdown 변환을 호출했다(성공).
- `approval_events`에 `runtime-egress` 사건이 기록됐고(markitdown, 01:52:57Z), D-145 상관 조회에서 판정 85에 `server-egress` 1건(learn.microsoft.com, 상태 connected, 자격 사용 unobserved, 재시도 null, 외부 효과 unverified, 후보 요청 ID)이 붙었다.

