# 개편 요청 8개와 완료 증거 관리표

기준: 2026-10-01, PAC15 코드 `15db1cb` 배포 후 실기기 검증 시점.
이 표는 [초기 개편 기록](REMASTER_2026-10-01.md)의 이후 상태를 보완한다.
진행 중인 코드가 실기기에 자동 반영되었다고 가정하지 않는다.
최신 배포·실험 결과가 생기면 이 파일의 상태와 증거를 같이 갱신한다.

| 사용자 요청 | 현재 상태와 근거 | 완료까지 필요한 증거 |
| --- | --- | --- |
| 1. MS·IBM·LiteLLM UI 분석·리마스터 | **소스 분석·초기 UI 구현/배포, 추가 기능 진행.** [고정 커밋 분석](BENCHMARK_UI_ONBOARDING_2026-10-01.md)에 소스 경로·채택 근거가 있다. 상단 검색·접는 메뉴·로그 종류/실행 필터와 실제 실행 수는 `fa70b959` 범위. 새 PAC capability 화면·원격 인자 범위·OS 차단 탭도 배포함. OS collector의 실제 장치 연동은 별도 남음 | 최신 세 서비스 이미지 배포 SHA, 실제 dashboard 로그인/새 로그/상세 화면, 작은 화면·키보드 확인. 세 참조 제품을 직접 기동한 UI 비교는 아직 없음 |
| 2. 엔드포인트 설치 및 실제 로컬 MCP 3종 이상 | **Linux 비관리자 집행 코드·부분 PJ1 시험, 3종 연동 미완료.** `endpoint-agent/enforce-linux.py`는 root 소유 native Codex/Claude·AppArmor 로그인 프로필·UID nftables를 설치. IDA MCP 실제 초기화, Ghidra/Obsidian 공급자 앱 준비는 개별 작업이며 3종 통합 통과로 세지 않음 | 세 실제 공급자 MCP의 정상 tools/list·읽기 호출, 설정/리스너 발견, 미등록/direct 차단, 정식 신청→승인→Gateway 사용. 공급자 소스 수정 없이 남긴 요청·응답 및 실제 앱 효과 |
| 3. 일반 사용자 조직 등록 간편화 | **초대 API/UI 구현 및 인수 확인.** 최대 50명·48시간·1회용·비밀 해시 저장, 서버가 아이디/부서/employee 역할을 고정. MS 팀/Entra, IBM 팀/초대, LiteLLM org/key 흐름에서 경계와 UX를 차용 | 실제 일반 사용자 초대→본인 가입→장치 등록→MCP 사용 전 과정. 외부 Entra/OIDC SSO·자동 프로비저닝은 아직 미구현 |
| 4. npm·pip·git clone·apt 차단 | **OS 집행 구현·부분 실기기 확인, 완료 아님.** 일반 계정의 허용 실행 경로 외 실행을 AppArmor가 막고, Gateway 지정 IP/port 외 모든 UID IP egress를 nftables가 거부. Gateway 제품들의 MCP 등록 화면을 OS 패키지 통제 기능으로 인용하지 않음 | 비관리자 계정에서 네 명령 실제 실패 + 설치/복제 효과 부재, 이름 변경/다운로드 바이너리·일반 Python/Node·BUN 환경·오프라인 설치·TCP/UDP·IPv4/IPv6·loopback·source port 우회 실패, 서비스 재시작/재부팅 지속성, kernel→장치 로그→Console 증거 |
| 5. 섀도 AI·MCP 통제 | **관리 설정·관측·미등록 감사 구현, 강제 경로 통합 진행.** approved endpoint는 registry 기반으로 판정. 미등록 `/mcp/<id>/`는 별도 `mcp-connection` 감사. OS 차단 collector/API는 별도 장치 scope와 원장 | 새 일반 사용자에 실제 관리 설정 적용, 직접 원격/로컬/stdio/앱커넥터/비관리 LLM 경로 차단, 승인 경로 정상 실행. 관측 이벤트만으로 차단했다고 보고하지 않음 |
| 6. 리팩터링·푸시 | **이전 단계 push/배포, 새 PAC·단말 변경은 작업 트리.** 신원·계약·실행 전 경계를 공통 경로에서 재확인하며 다른 랩/사용자 작업은 보존. 별도 `mcpgw-remaster-20261001` 네트워크·빈 볼륨 테스트보드를 사용 | 현재 전체 `console.sh test` exit 0, 필요한 실기기 재현, 검토 문서·README·D-결정 갱신, commit/push 원격 SHA/CI, 솔루션의 gateway/gateway-sse/agent-service 및 OPA/Caddy 실제 반영 |
| 7. 333 폐기 및 팀원+Claude 검토 PAC 사용 | **완료: 런타임 통합·전체 검증·실기기 배포·PJ1 정상/차단 확인.** 수정 PAC pack을 제품에 넣고 3개 인터페이스 차이만 조정. `capabilities.json`·원격 주체/인자 제약으로 인가. 333 권한 데이터/조회/화면을 제거하고 과거 ID는 중지된 감사 식별자로 보존 | [PAC 런타임 문서](PAC_RUNTIME_2026-10-01.md)의 사실·한계를 유지, 승인 nonce/다이제스트·기간·철회·미확인 mutation·범위 밖 인자 회귀, 실제 배포 정책·capability hash, 정상 사용·차단의 upstream 증거 |
| 8. 결과를 위한 꼼수 금지 | **모든 완료 판단에 적용.** 임시 `pj1-log-*` 시험은 예전 제한된 실험으로 표기. 공급자 코드·승인 기록·원장은 결과를 맞추려고 바꾸지 않음 | mock·정책 사실 입력·native 초기화·tools/call·실제 효과·OS 관측을 서로 나눠 보고. 정책에 맞춘 시험 수정은 변경 이유/예전 실패를 보존하고, 허용 범위를 넓혀 실패를 숨기지 않음 |

## PJ1 로그의 증거 기준

사용자가 지금 확인하려는 것은 **PJ1에서 생긴 실제 요청이 솔루션 기기 원장과 화면에 쌓이는가**이다.
각 실험은 송신 전·후의 실제 decision id 범위를 기록하고 해당 행만 집계한다.

| 이벤트/결과 | 보고해야 하는 사실 |
| --- | --- |
| 미등록 연결 | `event_kind=mcp-connection`, 실제 서버 이름, 초기화/HTTP 방법, 정책, attempted/executed=false. 도구 호출 건수에 합치지 않음 |
| 실제 tools/call | 실제 native Codex/Claude 경로, 공급자 도구 이름·인자, decision/policy, request/trace id |
| 승인 대기·실행 전 차단 | upstream_attempted=false와 별도 서비스/DB 효과 부재 |
| 실제 호출 | attempted=true와 응답 또는 독립 upstream 효과. 공급자 읽기 도구 하나가 다른 업무/쓰기까지 증명하지 않음 |
| 응답 유실/미확인 mutation | attempted=true, executed=false의 불확실성을 유지. 실패=효과 없음으로 단정하지 않음 |
| OS 차단 | 실제 AppArmor/nft kernel 이벤트→bound device report. MCP 실행 로그에 합치지 않음 |

이전 PJ1 200건은 원장 **21~220**, Codex/Claude 각각 100건,
Allow 9·Alert 10·Approval 32·Block 149, 실제 attempted/executed 19건이다.
14개 대표 읽기 뒤 186건을 송신 6/s로 보낸 **이전 임시 등록 경로의 제한된 실험**이다.
이를 정식 도입 승인 완료 또는 공급자별 전체 기능 검증으로 제시하지 않는다.
새 로그 확인은 아래 별도 범위로 기록하며 이전 200건과 합산해 새 실험 수로 제시하지 않는다.

### 최신 실기기 적재 확인

본 작업의 live 조회에서 송신 전 마지막 id **332**가 송신 후 **379**로 증가했다.
신규 범위는 **333~379, 총 47행**이다. PJ1 native Codex 20건·Claude Code 20건의 GitHub 도구
요청 **40건**과 미등록 연결 **7건**을 구분했다. 송신은 **6/s**, 모델 추론은 **0회**다.
실제 upstream 실행은 **4건**이며 공급자 정상 응답 **3건**, 실행 후 출력 통제에 걸린 응답
**1건**이다. 출력 차단 1건을 실행 전 차단으로 세지 않는다.

이 결과는 솔루션 기기의 **`b3c5efb6912eb78f458742610313565dffadb673`**에서 확인했다.
최초 기록의 `fa70b959`는 작업 트리 기준을 운영 revision으로 잘못 옮긴 값이었다.
운영 Gateway `build_info()`와 환경 변수, 소스 HEAD를 다시 대조해 정정했다.
Gateway 시작 시각은 `2026-10-01T04:54:11Z`로 이번 14:46 KST 로그 시험보다 앞선다.
실제 OPA에 로드된 기존 `policy.rego` SHA-256은
`c577f4ce37443e992e1f78ed4d1741d584e55334009b3ad888021ffc48182708`이며,
기존 Claude D-54 하드닝을 포함한다. 팀원 PAC15 통합 모듈은 아직 로드되지 않았다.
새 PAC·OS 이벤트 변경은 미커밋/미배포 상태이므로 이 47행을 새 PAC 개편의 실기기 검증으로
사용하지 않는다. 나머지 판정의 정책별 분포·실행 여부는 해당 id 범위의 live 원장을 근거로 확인한다.

Claude native control API가 isError 응답의 `_meta`를 버릴 수 있으므로,
metadata가 없다는 이유만으로 Gateway 미도달이라고 집계하지 않는다. 실제 DB와 transport 결과를 대조한다.
하네스 control API를 통한 도구 호출에는 모델 추론이 필요하지 않으며, 모델 토큰 사용량과 MCP 요청 수를 구분한다.

## 클린 테스트보드의 현재 확인과 남은 실패

읽은 보고서: `/home/kali/mcpgw-remaster-20261001/full_stack_lab/reports/remaster-phase12-pac.txt`.
그 시점의 결과는 Rego 99/99·acceptance 22/22·capability 경계 검사 PASS·독립 SQL 효과 경쟁
2/2 통과다. 6개 동시 요청의 실제 DB 효과는 4회, 중복 2개 요청의 효과는 1회다.
native 하네스 4종 × 워크스테이션 4개는 각각 관리형 MCP 10/10 연결을 확인했다.
그러나 전체 시험은 아래 업무 기대값 불일치 때문에 아직 통과하지 않았다.

| 사례 | 실제 결과 | 검토할 조치 |
| --- | --- | --- |
| ws-ysg run-tests | `cd /workspace/payment-service && python -m pytest -q`가 승인된 세 명령 밖이므로 PAC-01 Block. 예전 기대는 Approval | 업무상 필요하면 별도 정확한 capability 심사. 필요 없으면 기대값을 Block/PAC-01/미전송으로 갱신 |
| ws-nkk audit-copy | 폐기한 EXC-001 대상이 PAC-01 Block. 예전 기대는 Alert | 폐기 이유를 남기고 새 기대값을 검증. 예외를 되살려 통과시키지 않음 |
| ws-nkk exfil-upload | fetch가 협력사 tools/list에서 빠져 inspector가 tool_not_found로 호출하지 않음. decision 없음 | 목록 비노출 검증과 악성 직접 tools/call의 Gateway 차단 검증을 분리. 존재하지 않는 결정 행을 만들지 않음 |

실패 보고서는 보존한다. 이전 `phase4` 전체 통과는 이전 코드의 증거이며,
그 뒤 PAC·단말 변경의 전체 통과를 대신하지 않는다.

## 남은 완료 순서

1. 즉시 요청의 PJ1 로그 47행은 위 실기기 범위로 확인했다. 이후 실험도 원장 범위와 화면의 종류/실행 수를 대조한다.
2. 새 PAC 업무 기대값과 악성 직접 호출을 정책 근거에 맞춰 검증하고 전체 시험을 끝낸다.
3. 원격 7종은 미승인 경로를 닫은 뒤 각각 정식 신청·독립 승인·인자 범위로 등록한다.
   OAuth 실패는 endpoint/TCP/TLS/token 만료/resource/도구 권한을 구분해 보고하고 반복 창으로 대체하지 않는다.
4. 등록 일반 계정·장치의 OS 집행과 세 실제 로컬 MCP를 연결해 우회/정상 사용을 확인한다.
5. 전체 변경을 push·배포한 뒤 실제 UI 및 revision·정책/capability hash와 시험 증거를 남긴다.

전체 MCP Top 10 대응 또는 IBM/MS/LiteLLM보다 우수하다는 판단은 아직 하지 않는다.
동일 시나리오·동일 효과 검증으로 비교한 결과가 있어야 차이를 주장할 수 있다.

## 이번 PAC15 즉시 반영 결과

전체 클린 시험 exit 0과 배포 파일/OPA hash 일치, 333 grants 부재를 확인했습니다.
GitHub는 사용자 새 신청·관리자 명시적 스키마 검토·독립 승인으로 재등록했습니다.
PJ1 Codex/Claude는 실제 커밋 반환 각각 1건, 범위 밖 인자 PAC-01 미전송 각각 1건(384~387).
정책/로그 UI와 원장 근거는 [런타임 통합 문서](PAC_RUNTIME_2026-10-01.md)를 따릅니다.

로컬 IDA(6도구)·Ghidra(27도구)·Obsidian(17도구)의 공급자 원본 읽기 실행 증거는
`/home/kali/mcpgw-local-vendors-20261001/`에 별도 보존했습니다. 세 종류의 Gateway 등록·승인·
단말 우회 차단 증거는 아직 완료하지 않았습니다. 위 관리표의 나머지 1~6 전사 검증 과제는 계속 남습니다.
