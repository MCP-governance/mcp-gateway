# DEV-76 SBOM 영향 조회·서버 대응

## 요구사항과 현재 선택

방향 갱신 원문 [direction-1020/README.md](../direction-1020/README.md) §3 DEV-76의 완료 조건을 적용한다. 입력은 CycloneDX 구성요소 이름과 SemVer 판본 범위다. 결과는 등록 서버·실행 세대별로 `영향 있음`, `영향 없음`, `판단 불가`, `자료 없음`을 구분하고, 확인한 경우 구성요소 이름·판본·purl·SBOM 행 ID를 반환한다. 서버 차단은 기존 서버 중지 경로를 서버마다 호출하며 새 판정이나 정책 ID를 만들지 않는다.

| 요구 | 구현·확인 |
| --- | --- |
| 저장된 SBOM 범위만 사용 | 서버별 가장 최근 등록 intake 신청의 Syft 시도가 `DONE`이고 Syft 보고서가 `IMPORTED`이며 `registered_server_id`·`intake_id`·실행 세대 source commit이 이어지는 행만 판정한다. |
| 취약 판본과 영향 없는 서버 구분 | 세 자리 SemVer와 AND 판본 조건을 비교한다. 정확히 이름이 같은 구성요소만 대조한다. |
| 비교·자료 공백 표시 | SemVer 파싱 실패 또는 잘린 200개 요약에서 취약 버전이 확인되지 않으면(동일 이름 구성요소가 전부 범위 밖으로 보여도) `판단 불가`; Syft 요약·시도·연결이 없으면 `자료 없음`이다. |
| 전사 중지 및 감사 | `ops_response.suspend`를 서버마다 반복한다. `ops_suspensions`·서버 `DISABLED`·실행기 `STOPPING` 경로를 재사용하고 append-only `automatic-suspension` 행의 `scope.batch`에 동일 UUID를 넣는다. |
| 부분 실패 | 성공·건너뜀·실패 배열과 각 숫자를 반환한다. 중지 함수 예외는 서버 ID와 예외 종류만 남긴다. |
| 관리자 경계 | Console API 두 라우트 모두 `Depends(admin_caller)`다. |

## 기존 공급망 자료와 저장 위치

2026-10-21 로컬 checkout `859f4d63db9cab5714f25e5d3cc4607077959e13`에서 `full_stack_lab/supply_chain/` 전체를 확인했다. 신규 소스·SBOM·라이선스 자료를 수집하거나 만들지 않았다.

| 파일 | 기존 역할·판본 근거 |
| --- | --- |
| `intake_worker.py` | 저장소를 checkout하되 제출 코드는 실행하지 않고 Syft·Trivy·Semgrep·Gitleaks를 실행한다. Syft는 CycloneDX JSON 원본을 `intake-<UUID>-sbom.cdx.json`으로 만든다. summary에는 전체 구성요소 수와 앞 200개(`name`, `version`, `type`, `purl`, `licenses`) 및 `truncated`가 저장된다. 별도로 Trivy license-file 결과에서 저장소 license 요약을 추출해 provenance에 둔다. |
| `intake-worker.Dockerfile` | Syft 1.51.1, Trivy 0.74.0, Semgrep 1.172.0, Gitleaks 8.30.1을 고정한다. Python 3.12-slim, psycopg 3.3.5, Semgrep pip 1.172.0; 새 의존성은 추가하지 않았다. |
| `provenance.py` | Syft와 별도로 스캔 source tree의 manifest SHA-256과 파일 수/총 바이트를 계산한다. 소스 트리 digest는 SBOM 파일 digest나 실행 이미지 digest가 아니다. |
| `trivy_scan.py` | Trivy 요약·취약점 DB 시각 해석. SBOM 영향 검색의 판본 비교에는 사용하지 않는다. |
| `exit_terms.py` | 신청 저장소의 종료 조건 조사·결론. 취약점 패키지 목록이 아니다. |
| `semgrep-mcp.yml` | MCP 소스 정적 규칙. SBOM 구성요소 인벤토리가 아니다. |
| `gitleaks.toml` | 운영자가 소유한 기본 비밀 탐지 설정. 신청 저장소 설정은 불러오지 않는다. |

도입 검증 원본 CycloneDX는 Compose의 `intake_reports` named volume(`/reports` 워커, `/intake-reports` 읽기 전용 Console API)에 저장되며 기존 관리자 신청 보고서 API로 파일을 받을 수 있다. DB의 `supply_chain_reports.summary.inventory`는 200개로 제한된 조회용 사본이다. `truncated=true`이면 취약 버전을 발견하지 못한 모든 경우(구성요소를 못 찾았거나, 앞 200개에 보인 같은 이름 판본이 전부 범위 밖이어도) `판단 불가`로 남긴다. Syft가 실패했거나 현재 시도에서 `DONE`이 아니면 이전 보고서가 남아 있어도 조회에 쓰지 않는다. 과거 `/reports/sbom.cdx.json` 수동 import는 `workspace` source_ref와 구성요소 수만 저장하고 inventory·신청·등록 서버·세대 연결을 저장하지 않아 전사 조회에 사용할 수 없다.

기존 source-tree digest·artifact SHA·license report의 의미를 확장하지 않는다. `mcp_intake_requests.provenance.artifact.sha256`는 source-tree manifest, runtime의 `source_archive_sha256`는 별도 압축본, `image_id`는 실행 이미지 식별자이며 서로 대체하지 않는다. Syft summary의 `licenses`는 component별 SBOM license 표현이고 provenance의 `license`는 Trivy가 찾은 저장소 license-file 요약이다. SBOM JSON 자체의 SHA-256은 `supply_chain_reports` 열에 저장되지 않는다. `intake_reports` named volume 존재만으로 백업·보존 기한·복원 검증을 입증할 수 없다.

조사 기준 소스(`859f4d6`)의 SHA-256:

| 파일 | SHA-256 |
| --- | --- |
| `exit_terms.py` | `a5f682a1327b34737fc04b6e4d474eca32efdf4b8139c20225c11e93c74eb789` |
| `gitleaks.toml` | `bd83e2894cf79be4c6b3c35d3a63f423be09aec9d546e1d726ab027a7820a900` |
| `intake-worker.Dockerfile` | `9a4bb37d7399485e2f19a26864fce2d8049aa64a208bb810f6fd85624ed7d512` |
| `intake_worker.py` | `0ee5401c1c61bb9feb73882ecc7ac0dc4b7d0b436d01b88526e5a9d51e6ef04c` |
| `provenance.py` | `f8c7e0f78859e00a05372c938b00836421632f5dd508963c1eadf0408d11f83c` |
| `semgrep-mcp.yml` | `b03bfbb114dc07d1ad9fa4c1ef034e064b5691f44d0cdf155084c1c93f4ab94c` |
| `trivy_scan.py` | `348282349e8d16da174e1b9b13767e6835c7752c96827eedecaa17a9112815de` |

## 판본 비교와 정확도 경계

비교기는 추가 패키지 없이 SemVer 2.0 형식(major.minor.patch, 선택적 prerelease/build metadata)을 해석한다. 범위는 쉼표나 공백으로 나눈 최대 네 개의 `<`, `<=`, `=`, `>=`, `>` 조건을 모두 만족하는 AND 조건이다. prerelease의 SemVer 우선순위를 따르고 build metadata는 비교에서 제외한다. caret/tilde/wildcard/OR, 생략 판, 날짜 판본, `latest`, 배포자별 사용자 판본은 지원하지 않는다. 해당 package version이나 입력 범위를 파싱하지 못하면 `판단 불가` 또는 요청 오류다. 패키지 이름은 공백 제거 후 대소문자를 접어 SBOM `name`과 비교하며 namespace 별도 해석은 하지 않는다.

이 영향 목록은 **저장된 source-tree SBOM 요약에 대한 조회**다. Syft 대상은 빌드 결과 이미지가 아니므로 실제 실행 이미지 레이어·다운로드 구성요소와 다를 수 있다. 최대 200개 summary의 누락·실패한 현재 검사·잘못 연결된 세대는 비영향으로 단정하지 않는다. 데이터가 없는 서버도 영향 목록 바깥에서 조용히 빠지지 않고 `자료 없음` 행으로 반환한다. 사용자와 엔드포인트는 이 저장 데이터에 SBOM 연결이 없어 DEV-76 구현 범위의 결과로 내세우지 않는다.

## 중지와 원장

영향이 확인된 세대가 하나라도 있는 서버를 한 번씩 중지한다. `ops_response.suspend(server_id, "supply-chain", ...)`가 기존 트랜잭션에서 `ops_suspensions`를 만들고 `mcp_servers.status='DISABLED'`, 관련 `mcp_runtimes.status='STOPPING'`을 적용한다. 새 중지일 때만 기존 형식의 `approval_events(kind='automatic-suspension', target_kind='server')`가 추가되며, 해당 행의 `scope.batch`는 한 HTTP 일괄 요청의 UUID이고 `scope.requested_by`에 관리자 주체가 보존된다. 이미 다른 이유로 중지된 서버는 새 원장 행을 만들지 않고 건너뜀으로 보고한다. 실패 서버는 계속 다음 서버로 진행한다. 서버 중지 후 재개·자격 회전·외부 upstream 자격 회수는 포함하지 않는다.

Console은 입력과 네 수치, 중지 결과 세 수치만 표시한다. 서버·세대·SBOM 구성요소 근거 전체는 관리자 조회 API 응답에 있으나 화면은 목록을 보여 주지 않는다.

## 시험 연결

`full_stack_lab/tests/sbom_impact_check.py`는 합성 SBOM 행으로 SemVer 경계, 영향/비영향/판단 불가/자료 없음, 서버별 세대 중복 제거, 일부 중지 실패, `scope.batch` 원장 쓰기를 고정한다. 기존 공급망·D-179~181 회귀 파일의 기대값이나 AST는 바꾸지 않았다. 실제 PostgreSQL, 원본 volume 파일, 런타임 컨테이너, MCP 호출, 기기/PJ1 효과는 미검증이다.

## 출처

- [방향 갱신 원문](../direction-1020/README.md) §3 DEV-76
- `full_stack_lab/supply_chain/{intake_worker.py,intake-worker.Dockerfile,provenance.py,trivy_scan.py,exit_terms.py,semgrep-mcp.yml,gitleaks.toml}`
- `full_stack_lab/compose.yaml` (`intake_reports` volume)
- `docs/ai/DATA_MODEL.md` §6, `full_stack_lab/gateway/app/ops_response.py`, `full_stack_lab/gateway/app/user_suspend.py`
