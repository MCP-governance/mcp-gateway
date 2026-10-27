# 수동 시험 매뉴얼 — Linux 직원 PC

직원 PC(Ubuntu 22.04/24.04 등, systemd)에 키트를 설치하고 승인된 MCP를 실제 하네스로 써 보며 게이트웨이 판정을 확인하는 절차다.
한 번 끝까지 하는 데 약 40분. 결과는 맨 아래 기록 표에 적는다. Windows는 [MANUAL_TEST_WINDOWS.md](MANUAL_TEST_WINDOWS.md).

## 0. 준비

| 항목 | 내용 |
| --- | --- |
| 게이트웨이 | `https://<게이트웨이 주소>/` 에 콘솔이 열리고 로그인할 수 있어야 한다. 주소는 운영 담당에게 받는다 |
| 계정 | 직원 계정 1개(시험 대상), 관리자 계정 1개(동의·승인 확인용, 시험 직원과 다른 사람) |
| PC | 일반 사용자 계정 + `sudo` 가능(설치 때 관리자 암호 1회). `unzip`·`python3` 있음 |
| 하네스 | Claude Code(`claude --version`) 또는 Codex CLI(`codex --version`) 중 하나 이상이 직원 계정에 설치·로그인돼 있음 |
| 로컬 MCP(선택) | 파일·기억·단계별 사고 MCP를 시험하려면 Docker 또는 Podman(설치기가 시도함) |
| 문서 폴더 | 시험용 파일을 둘 `~/mcp-docs` (없으면 만든다) |

시험 중 콘솔에서 볼 곳: **도구 호출 로그**(판정·정책 ID·처리 시간), **이용 동의**, **MCP 서버**(서버 상세 → 범위), **사용자·엔드포인트 → 엔드포인트**, **내 연결**.
판정은 「허용(Allow)/차단(Block)/경보(Alert)」과 **정책 ID까지** 확인한다(같은 차단이라도 이유가 다르면 실패다).

## 1. 설치

1. 브라우저로 콘솔에 직원 계정으로 로그인 → 왼쪽 아래 **PC 연결 설정** → **Linux** → **설치 파일 받기**(`mcp-managed-kit-linux.zip`).
   - 「고급: 격리 계정」은 체크하지 않는다(기본 간편 모드). 격리 계정 시험은 7절.
2. 터미널에서 실행:

   ```bash
   unzip ~/Downloads/mcp-managed-kit-linux.zip -d ~/mcp-managed-kit && ~/mcp-managed-kit/install.sh
   ```

   관리자 암호를 한 번 묻는다. 터미널이면 풀화면으로 단계·소요 시간이 보인다.
3. 설치 끝 화면의 **세 칸**을 확인한다.

   | 칸 | 통과 기준 |
   | --- | --- |
   | 모델 응답 | 하네스가 실제로 답함 |
   | 도구 | 승인 서버마다 도구 수가 0보다 큼 |
   | 서버 연결 | 승인 서버 1건 연결 성공 |

4. 활성화: 콘솔 **사용자·엔드포인트 → 엔드포인트**에서 이 PC가 「활성」인지 본다. 「새 PC 활성화」가 「자동」이면 설치 직후 활성,
   「관리자 확인」이면 관리자가 활성화한다.
5. **새 터미널**을 연다(사설 인증서 환경은 새 로그인부터 읽힌다).

기록: 설치 시작~세 칸 표시까지 걸린 시간, 활성화까지 걸린 시간.

## 2. 상태 확인

```bash
mcpgw-status            # 터미널이면 2초마다 갱신(q 닫기, c 연결 확인)
mcpgw-status --check    # 도구·서버 연결 두 칸을 다시 잰다
```

통과: 장치 상태 「활성」, 게이트웨이 「연결됨」, 마지막 보고 60초 이내, 승인 서버 수가 콘솔 **MCP 서버**의 사용 가능 서버 수와 같음,
(로컬 MCP가 있으면) 「로컬 MCP 준비: n/n」.

## 3. 정상 기능 시험

각 항목은 직원 터미널에서 `claude -p "<프롬프트>"`(Codex는 `codex exec "<프롬프트>"`)로 실행한다. 서버 이름은 콘솔 **MCP 서버**의 표시 이름을 쓴다.
대화형으로 해도 된다(`claude` 실행 후 같은 문장 입력).

### 3.1 첫 사용 동의 → 재호출 (원격 문서 MCP)

1. `Microsoft Learn MCP로 "Azure Functions Python v2 HTTP trigger" 문서를 검색해 핵심 3줄로 요약해. 차단되면 차단 코드와 사유를 그대로 적어.`
2. 기대: 처음이면 「`P-CONSENT-001` 이 도구의 데이터 이용에 사용자 동의가 필요합니다」. 콘솔(직원) **이용 동의 → 확인 필요**에서 그 서버를 허용.
3. 같은 문장을 다시 실행 → **도구 호출 로그**에 `Allow`·`P-AUTHZ-ALLOW-001`. 처리 시간(ms)을 적는다.
4. 다른 원격 서버(DeepWiki·Cloudflare Docs·AWS Knowledge·Hugging Face·Grep 등)도 같은 방식으로 한 번씩.

### 3.2 GitHub — 「내 연결」 없음과 연결 뒤

1. `GitHub MCP의 get_me로 내 계정 정보를 알려줘.`
2. 기대(연결 전): `MCP-CREDENTIAL-001` 「GitHub 계정 연결이 없거나 만료되어 호출하지 않았습니다」. 로그에 상위 호출 없음.
3. 콘솔 **내 연결**에서 GitHub 개인 액세스 토큰을 연결(본인 토큰, 읽기 권한) → 같은 문장 → `Allow`. 끝나면 **내 연결**에서 해제할 수 있다.

### 3.3 로컬 MCP 3종 (PC 격리 실행)

1. 시험 문서 하나를 `~/mcp-docs`에 둔다(아무 Markdown, 수십 KB).
2. 프롬프트:
   `filesystem MCP로 허용 폴더의 파일 목록을 보고 가장 큰 Markdown 문서를 읽어 5줄로 요약해. 그다음 memory MCP에 문서 제목과 요약 3개를 엔티티로 저장하고 read_graph로 다시 읽어 보여줘. 마지막으로 sequentialthinking MCP로 이 문서를 팀에 적용하는 4단계 계획을 세워. 차단되면 코드와 사유를 그대로 적어.`
3. 기대: 모든 호출 `Allow`, `read_graph`가 방금 저장한 엔티티를 보여 줌. 로컬 호출은 1회 3~5초(컨테이너 기동).
4. 같은 문장을 한 번 더 실행해 두 번 다 통과하는지 본다.
5. 정리: `memory MCP의 delete_entities로 방금 만든 엔티티를 지워.`

### 3.4 출력 통제(오탐이 없어야 하는 경우)

`~/mcp-docs`에 아래 세 파일을 만든다.

```bash
python3 - <<'EOF'
import json, os, random
d = os.path.expanduser("~/mcp-docs")
open(f"{d}/long-handbook.md", "w").write("\n".join(f"## {i}절\n\n본문 {i} 내용입니다." for i in range(1500)))
open(f"{d}/deploy-example.md", "w").write("# 예시\n\n```bash\nexport AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\nexport GITHUB_TOKEN=ghp_" + "a1B2" * 9 + "\n```\n")
rows = [{"order_id": int("1" + "".join(random.choice("0123456789") for _ in range(15))), "qty": 1} for _ in range(300)]
open(f"{d}/orders.json", "w").write(json.dumps({"orders": rows}, indent=1))
EOF
```

| 프롬프트 | 기대 |
| --- | --- |
| `filesystem MCP로 long-handbook.md를 read_file로 읽고 절 개수를 세어 줘.` | `Allow`(긴 문서도 줄 수로 막지 않음) |
| `filesystem MCP로 deploy-example.md를 읽고 절차를 2줄로 요약해. 키 값은 옮기지 마.` | `Allow`, 결과의 키가 `[REDACTED]`로 가려짐(로그 결과 요약에 가림 종류 표시) |
| `filesystem MCP로 orders.json을 읽고 주문 건수를 알려줘.` | `Allow`(1로 시작하는 주문번호는 카드번호로 보지 않음) |

참고: 4·5로 시작하는 16자리 숫자가 카드번호 검증(Luhn)을 통과하면 결과 전체가 보류된다(정책). 그때 사유가
「결과의 키나 숫자 값에 개인정보 형태가 있어 JSON 구조를 바꾸지 않고는 가릴 수 없습니다: CARD_NUMBER」인지 확인한다.

### 3.5 주소 인자가 있는 도구(허용 주소)

1. 관리자: **MCP 서버 → AWS Knowledge → 범위**에서 `aws___read_documentation`의 **허용 주소**에 `docs.aws.amazon.com` 기록.
2. 직원: `AWS Knowledge MCP의 aws___read_documentation으로 https://docs.aws.amazon.com/AmazonS3/latest/userguide/example-bucket-policies-vpc-endpoint.html 을 읽고 4줄로 정리해.`
3. 기대: `Allow`. 허용 주소에 없는 주소(예 `https://example.com/`)로 바꾸면 `PAC-01` 「값이 승인된 주소·형식 밖」.

### 3.6 동시 사용(같은 직원, 터미널 두 개)

터미널 두 개를 열고 거의 동시에 실행한다.

```bash
claude -p "DeepWiki MCP로 microsoft/playwright 위키 목차를 보고 5줄로 요약해"      # 터미널 1
claude -p "Microsoft Learn MCP로 Entra ID 조건부 액세스 문서를 검색해 4줄로 요약해"   # 터미널 2
```

기대: 두 하네스 모두 요청한 서버의 도구를 찾고 `Allow`. 「도구가 보이지 않는다」는 답이 나오면 실패로 기록한다(시각 포함).

### 3.7 정책 변경 중 사용

1. 직원: 오래 걸리는 작업을 시작한다.
   `sequentialthinking MCP로 "사내 MCP 도입 위험 점검"을 8단계로 생각하고, 생각 사이마다 filesystem MCP로 ~/mcp-docs 목록을 확인해. 호출별 성공/차단 표를 만들어.`
2. 그 작업이 도는 동안 관리자가 **다른** 시험 서버를 원클릭 승인하거나 철회한다(4절).
3. 기대: 직원 작업의 모든 호출이 `Allow`(끊김·`ENDPOINT-MANAGED-001`·「rejected the credential」 없음). 새 서버는 1분 안에
   `mcpgw-status`의 승인 서버 수에 반영되고, 열려 있던 하네스에 안 보이면 하네스를 다시 시작한다.

## 4. 도입 수명주기(관리자·직원)

1. 직원: 콘솔 **도입 신청 → 새 신청**에서 원격 MCP 주소로 신청(예 `https://gitmcp.io/docs`, 목적 10자 이상).
2. 관리자: **도입 신청 → 검토** → 위험 등급·도구·허용 주소 확인 → 사용 대상 「전체 직원」 → **승인**(미리보기 뒤 15분 안에).
3. 직원: 1분 뒤 `mcpgw-status`에 서버가 늘었는지 → 하네스를 새로 열고 그 서버로 호출 → 동의 → `Allow`.
4. 관리자: **MCP 서버 → 그 서버 → 철회**. 직원: 1분 안에 하네스에서 사라짐(호출하면 「사용할 수 없는 서버」).
5. 같은 신청을 다시 해 도구 분류를 「읽기」로 낮춰 승인하면 같은 인자로 두 번 불러도 막히지 않는다. 끝나면 철회.

## 5. 재설치·제거

| 시험 | 방법 | 기대 |
| --- | --- | --- |
| 재설치(업데이트) | 1절 2단계를 다시 실행 | 같은 PC·같은 직원이면 활성 상태를 이어받음(관리자 재활성화 불필요) |
| 상태 | `mcpgw-status` | 「키트 판본」이 새 값 |
| 제거 | `sudo ~/mcp-managed-kit/install.sh --remove` | `/etc/claude-code/managed-*.json` 등 키트 파일이 사라지고 하네스가 원래대로 동작 |

## 6. 결과 기록

| 번호 | 시험 | 시각 | 판정·정책 ID | 처리 시간 | 통과/실패 | 메모 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 설치·세 칸 | | | | | |
| 3.1 | 동의 → 재호출 | | | | | |
| 3.2 | GitHub 내 연결 | | | | | |
| 3.3 | 로컬 3종(2회) | | | | | |
| 3.4 | 출력 통제 3건 | | | | | |
| 3.5 | 허용 주소 | | | | | |
| 3.6 | 동시 사용 | | | | | |
| 3.7 | 정책 변경 중 | | | | | |
| 4 | 수명주기 | | | | | |
| 5 | 재설치·제거 | | | | | |

실패하면 그 시각, 프롬프트, 하네스의 답 원문, 콘솔 **도구 호출 로그**의 해당 행(판정·정책 ID·사유)을 함께 남긴다.

## 7. 고급: 격리 계정

콘솔에서 「고급: 격리 계정」을 체크해 받거나 `install.sh --isolated`로 설치한다. 별도 관리 계정 `managed-<직원>`이 생기고
AppArmor·UID 방화벽이 걸린다. 활성화는 관리자가 한다. 하네스는 같은 명령으로 실행하지만 관리 계정으로 돈다. 3절을 같은 방식으로 반복하고,
추가로 직원 계정에서 `curl https://example.com`이 관리 계정에서는 막히는지 본다.

## 8. 문제 해결

| 증상 | 확인 | 조치 |
| --- | --- | --- |
| 하네스가 「도구가 없다」고 함 | `mcpgw-status`의 서버 이름에 있는지 | 새로 승인된 서버면 하네스 재시작. 계속되면 시각과 함께 보고 |
| 401 「활성화를 기다리는 중」 | 콘솔 엔드포인트 상태 | 관리자 활성화 |
| 인증서 오류(사설 CA) | 설치 전 연 터미널인지 | 새 터미널(또는 다시 로그인) |
| `P-CONSENT-001` 반복 | **이용 동의**에 대기 항목 | 직원이 허용 |
| 로컬 MCP 오류 | `docker ps`가 되는지, `mcpgw-status`의 로컬 준비 | 엔진 설치·사용자 권한 확인 |
| 승인 서버 수가 콘솔과 다름 | 마지막 보고 시각 | 1분 기다린 뒤 `mcpgw-status --check` |
| 호출은 되는데 `MCP-SHADOW-002` 경보가 붙음 | 프롬프트에 `FastMCP`·`modelcontextprotocol` 같은 MCP 패키지 이름이 있는지 | 알려진 오탐: 관찰기가 하네스 명령줄을 미등록 MCP로 본다. 그 단어를 빼고 다시 해 보고 결과를 기록 |
