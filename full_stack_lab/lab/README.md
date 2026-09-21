# 기업 내부망 공급망 실습

`compose.corporate-lab.yaml`은 Tencent Zhuque Lab의 원본 A.I.G Web·Agent·API Checker를 Gateway 컨테이너 하나에서 실행합니다. 별도 A.I.G 전용 컨테이너는 없습니다.

```text
브라우저(127.0.0.1) → Gateway API :8080 / A.I.G UI :8088
                                  │
              Gateway + A.I.G Web·Agent·API Checker (같은 컨테이너)
                                  │
                  scanner / aig-targets (internal) ─── MCP target
격리 공급망 워커 ───────┘  (A.I.G mcp-scan CLI·SCA·SAST)
```

원본 Agent의 Chromium 점검 때문에 통합 Gateway에는 `SYS_ADMIN`과 `seccomp:unconfined`가 적용됩니다. Gateway API는 비특권 사용자이지만 A.I.G와 컨테이너·스캔 네트워크를 공유합니다. 이는 기존 컨테이너 격리를 포기한 로컬 실습 구성이지 운영용 보안 경계가 아닙니다. A.I.G UI에는 인증 기능이 없으므로 host loopback에만 공개합니다. 기존 A.I.G 데이터 볼륨은 재사용하며, `./console.sh lab-down`은 실습 볼륨까지 제거합니다.

## 내부망 자산 탐색 범위

`aig-network-probe`는 전용 one-shot Docker 컨테이너입니다. `console.sh`가 Compose 라벨에서 수집한 현재 컨테이너 IP만 전달하고, `5432, 8000, 8080, 8088, 8181, 9000, 4010, 4317, 4318, 16686/tcp`에 TCP connect만 수행합니다. 따라서 Docker `/16` 대역을 무차별 훑거나 host·외부망을 스캔하지 않습니다. 결과는 `reports/aig-network-inventory.json`에 남으며, `9000/tcp` MCP 엔드포인트의 발견은 A.I.G 동적 검사의 사전 조건입니다.

## 실제 취약 버전 후보

| 후보 | 근거 | 이 실습의 사용 방식 |
| --- | --- | --- |
| `@modelcontextprotocol/server-filesystem@0.6.2` | [GHSA-q66q-fx2p-7w4m](https://github.com/advisories/GHSA-q66q-fx2p-7w4m), CVE-2025-53109 — `0.6.3` / `2025.7.01` 이전 경로 검증 우회 | `package-lock.json` 메타데이터만 Trivy로 검사; 패키지를 설치·실행하지 않음 |
| `mcp-server-git==2025.11.25` | [GHSA-9xwc-hfwc-8w59](https://github.com/advisories/GHSA-9xwc-hfwc-8w59) — `2025.12.18` 이전 인자 주입 | `requirements.txt` 메타데이터만 SCA 대상으로 사용 |

기존 공용 `llm-stub`은 A.I.G의 큐·CLI·native JSON/SARIF 결과 경로를 검증하는 test double입니다. 별도 A.I.G 엔진이 아니며 결과에 `evidence_mode: test-double`이 남고 Gateway 차단 근거에는 들어가지 않습니다. A.I.G가 실제로 독립 발견한 결과를 차단에 쓰려면 A.I.G UI에서 조직의 검증된 모델 endpoint를 등록하고 `MCP_SCAN_EVIDENCE_MODE=live`로 실행해야 합니다.

실제 API 키를 쓰는 경로는 `../start-live-lab.cmd`(Windows 더블클릭) 또는 `./console.sh live-lab`(WSL/Linux)입니다. 이 명령은 `compose.live-lab.yaml`을 마지막 오버레이로 적용해 test double 설정을 실제 모델 설정으로 바꾸고, A.I.G Web에 `mcp-gateway-live` 모델을 등록합니다. 첫 실행에서만 키를 숨겨 입력받으며 이후에는 같은 명령으로 재기동합니다. 이 경로는 기존 DB와 A.I.G 이력을 지우지 않습니다. 연결 확인은 실제 API 응답과 워커 생존까지 확인하고, 실제 보안 판단은 이후 실행한 검사 결과에서 확인합니다.

## 실행

WSL/Linux의 `full_stack_lab`에서 다음을 실행합니다.

```bash
./console.sh corporate-lab
```

명령은 초기화된 DB에서 다음을 수행합니다.

1. 실제 GitHub MCP 도입 요청을 제출하고 격리 검증 대기열에 넣습니다.
2. 명시적 `LAB EXCEPTION`으로 취약 후보를 제한된 mock MCP 경로에만 도입합니다.
3. 전용 probe가 현재 Compose 내부망의 컨테이너 IP·허용 포트를 자산화하고 MCP endpoint를 확인합니다.
4. Trivy SCA와 A.I.G mcp-scan test-double 결과를 각각 저장합니다.
5. 공급망 차단 후 upstream 효과가 증가하지 않는지 확인합니다.
6. 해당 서버의 회수 대상·증거·도달 확인을 남기고 MCP 컨테이너를 제거해 `RETIRED`로 종결합니다.

검사 과정에서 실제 외부 저장소 코드는 격리 워커가 shallow clone하여 읽기만 합니다. 취약 패키지 버전은 실행하지 않습니다.
