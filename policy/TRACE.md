# 정책 추적표

생성 파일 — `python policy/tools/trace.py`. 손으로 고치지 않는다.
원본 시트: `MCP_보안_관리_정책_20261101-0445.xlsm` (SHA-256 `1604359f5f395401…`).

분류: 이미 구현 18 · 구현 가능(PaC) 48 · 솔루션 기능으로 커버 18 · 구현 불가·제외 6. Rego 판정이 있는 정책 66개, 정책 번호가 붙은 시험 361건, 독립 반례 시험 144건.

- 「판정 위치」는 그 정책의 결과를 내는 줄(findings·violations)이다. 정책 하나가 여러 줄·여러 패키지에 걸칠 수 있다.
- 「시험」은 통과/차단 시험 수, 「반례」는 규칙 작성자의 시험을 보지 않고 시트만으로 쓴 시험 수다.
- 이 표는 코드·시험의 연결이다. 게이트웨이 판정 경로 연결과 실기기 집행은 따로 확인한다(README 「게이트웨이 연결」).

| 정책 | 단계 | 우선순위 | 통제 대상 | 분류 | 판정 | 판정 위치 | 시험 | 반례 | 상태 | 사유(솔루션·제외) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| POL-I-01 | 도입 검토 | P2 | MCP Server | 구현 가능(PaC) | Rego | intake.rego:55 | 2/8 | 4 | Rego 규칙·시험 |  |
| POL-I-02 | 도입 검토 | P2 | Tool / Resource | 구현 가능(PaC) | Rego + 센서 | intake.rego:72 | 1/5 | 2 | Rego 규칙·시험 |  |
| POL-I-03 | 도입 검토 | P1 | Tool / Resource | 구현 가능(PaC) | Rego | call.rego:78 | 2/4 | 2 | Rego 규칙·시험 |  |
| POL-I-04 | 도입 검토 | P2 | Tool / Resource | 구현 가능(PaC) | Rego + 센서 | intake.rego:97, intake.rego:102, intake.rego:110, intake.rego:116, intake.rego:122 | 1/6 | 2 | Rego 규칙·시험 |  |
| POL-I-05 | 도입 검토 | P2 | Tool / Resource | 구현 가능(PaC) | Rego + 센서 | intake.rego:135, intake.rego:172, intake.rego:184, intake.rego:191, intake.rego:197 | 1/6 | 2 | Rego 규칙·시험 |  |
| POL-I-06 | 도입 검토 | P3 | Tool / Resource | 구현 가능(PaC) | Rego + 센서 | intake.rego:210, intake.rego:215 | 1/3 | 2 | Rego 규칙·시험 |  |
| POL-I-07 | 도입 검토 | P2 | Agent | 구현 불가·제외 | Rego | resource.rego:56, resource.rego:61 | 1/3 | 2 | Rego 규칙·시험 | 제외(현재 범위): 게이트웨이가 Prompt를 중개하지 않아 전부 거부된다. 승인본 허용이 필요하면 Prompt 중개를 별도 결정해야 한다 |
| POL-I-08 | 도입 검토 | P2 | MCP Server | 구현 가능(PaC) | Rego + 센서 | connect.rego:260, connect.rego:266 | 1/3 | 2 | Rego 규칙·시험 |  |
| POL-I-09 | 도입 검토 | P2 | MCP Server | 구현 가능(PaC) | Rego + 센서 | intake.rego:228, intake.rego:235, intake.rego:241 | 2/4 | 3 | Rego 규칙·시험 |  |
| POL-I-10 | 도입 검토 | P1 | 사용자 | 구현 가능(PaC) | Rego | call.rego:609, call.rego:615, intake.rego:262 | 2/5 | 2 | Rego 규칙·시험 |  |
| POL-I-11 | 도입 검토 | P2 | Tool / Resource | 구현 가능(PaC) | Rego | intake.rego:282, intake.rego:287 | 1/4 | 2 | Rego 규칙·시험 |  |
| POL-R-01 | 등록 및 연결 | P2 | MCP Host 및 MCP Client | 이미 구현 | Rego | connect.rego:48 | 1/6 | 2 | Rego 규칙·시험 |  |
| POL-R-02 | 등록 및 연결 | P2 | MCP Host 및 MCP Client | 구현 가능(PaC) | Rego | call.rego:165, call.rego:171, connect.rego:67, connect.rego:73 | 3/5 | 2 | Rego 규칙·시험 |  |
| POL-R-03 | 등록 및 연결 | P2 | MCP Host 및 MCP Client | 구현 가능(PaC) | Rego | connect.rego:85, connect.rego:91, connect.rego:96, connect.rego:102, connect.rego:107 | 2/7 | 2 | Rego 규칙·시험 |  |
| POL-R-04 | 등록 및 연결 | P3 | Agent | 이미 구현 | Rego | call.rego:183 | 1/2 | 2 | Rego 규칙·시험 |  |
| POL-R-05 | 등록 및 연결 | P3 | MCP Server | 이미 구현 | Rego | call.rego:199 | 2/4 | 2 | Rego 규칙·시험 |  |
| POL-R-06 | 등록 및 연결 | P3 | MCP Server | 솔루션 기능으로 커버 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 게이트웨이는 직원 토큰을 상위 서버로 넘기지 않지만, MCP 서버가 받은 토큰을 자신의 하위 서비스에 재사용하는 것은 서버 쪽 동작이라 게이트웨이 판정으로 막을 수 없다 |
| POL-R-07 | 등록 및 연결 | P3 | MCP Host 및 MCP Client | 솔루션 기능으로 커버 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 연결 응답의 발신 대상·인증 서버 발급자 확인은 전송 계층(TLS 서버 이름)과 로그인 라이브러리·IdP 처리 과정의 기능이다. 현재는 조직 SSO의 ID 토큰 발급자·대상만 검사하며(oidc.py:94) 모든 MCP 연결 응답의 발신 대상 혼동 방지가 확인된 것은 아니다 |
| POL-R-08 | 등록 및 연결 | P2 | MCP Host 및 MCP Client | 구현 가능(PaC) | Rego | connect.rego:125 | 1/4 | 3 | Rego 규칙·시험 |  |
| POL-R-09 | 등록 및 연결 | P3 | MCP Host 및 MCP Client | 솔루션 기능으로 커버 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 인증 결과 수신처(redirect 주소)의 승인값 일치는 해당 OAuth 클라이언트의 IdP 등록 설정과 실제 적용 상태에 달려 있다. 설정·시험 확인 전에는 집행 완료로 보지 않는다 |
| POL-R-10 | 등록 및 연결 | P3 | MCP Host 및 MCP Client | 솔루션 기능으로 커버 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 연결 결과와 현재 사용자·세션 요청의 일치(state·PKCE 1회 사용)는 로그인 라이브러리가 세션 상태로 검증한다. 모든 연결 경로에서 재사용 거부가 성립하는지는 별도 확인이 필요하다 |
| POL-R-11 | 등록 및 연결 | P2 | MCP Host 및 MCP Client | 구현 가능(PaC) | Rego | connect.rego:143 | 1/3 | 2 | Rego 규칙·시험 |  |
| POL-R-12 | 등록 및 연결 | P3 | MCP Host 및 MCP Client | 구현 가능(PaC) | Rego + 센서 | connect.rego:157 | 1/7 | 2 | Rego 규칙·시험 |  |
| POL-R-13 | 등록 및 연결 | P2 | MCP Host 및 MCP Client | 구현 가능(PaC) | Rego + 센서 | ops.rego:58, ops.rego:64, ops.rego:73, ops.rego:79 | 1/4 | 2 | Rego 규칙·시험 |  |
| POL-R-14 | 등록 및 연결 | P3 | MCP Host 및 MCP Client | 이미 구현 | Rego | call.rego:224, connect.rego:340 | 4/4 | 2 | Rego 규칙·시험 |  |
| POL-R-15 | 등록 및 연결 | P2 | Agent | 구현 가능(PaC) | Rego | connect.rego:174, connect.rego:180, connect.rego:185, connect.rego:191 | 2/6 | 2 | Rego 규칙·시험 |  |
| POL-R-16 | 등록 및 연결 | P3 | MCP Host 및 MCP Client | 이미 구현 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 |  |
| POL-R-17 | 등록 및 연결 | P3 | MCP Host 및 MCP Client | 이미 구현 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 |  |
| POL-R-18 | 등록 및 연결 | P2 | MCP Host 및 MCP Client | 이미 구현 | Rego + 센서 | connect.rego:203, connect.rego:209, connect.rego:223 | 1/4 | 2 | Rego 규칙·시험 |  |
| POL-R-19 | 등록 및 연결 | P3 | MCP Server | 이미 구현 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 |  |
| POL-R-20 | 등록 및 연결 | P2 | MCP Host 및 MCP Client | 구현 가능(PaC) | Rego + 센서 | connect.rego:235, connect.rego:241 | 1/4 | 2 | Rego 규칙·시험 |  |
| POL-R-21 | 등록 및 연결 | P3 | 사용자 | 구현 가능(PaC) | Rego | connect.rego:287 | 1/5 | 2 | Rego 규칙·시험 |  |
| POL-R-22 | 등록 및 연결 | P2 | 사용자 | 이미 구현 | Rego | connect.rego:307 | 1/3 | 2 | Rego 규칙·시험 |  |
| POL-E-01 | 실행 | P1 | Agent | 구현 가능(PaC) | Rego | call.rego:100 | 1/2 | 2 | Rego 규칙·시험 |  |
| POL-E-02 | 실행 | P3 | MCP Host 및 MCP Client | 이미 구현 | Rego | call.rego:122 | 1/2 | 2 | Rego 규칙·시험 |  |
| POL-E-03 | 실행 | P2 | Agent | 구현 가능(PaC) | Rego | call.rego:139 | 1/2 | 2 | Rego 규칙·시험 |  |
| POL-E-04 | 실행 | P1 | Agent | 구현 가능(PaC) | Rego + 센서 | call.rego:247, call.rego:253 | 2/3 | 2 | Rego 규칙·시험 |  |
| POL-E-05 | 실행 | P1 | MCP Host 및 MCP Client | 구현 가능(PaC) | Rego + 센서 | call.rego:265, call.rego:270, call.rego:281, call.rego:286 | 2/5 | 2 | Rego 규칙·시험 |  |
| POL-E-06 | 실행 | P3 | MCP Host 및 MCP Client | 솔루션 기능으로 커버 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 게이트웨이 우회 차단은 직원 PC의 방화벽·실행 제한(엔드포인트 키트)이 해야 한다. 격리 모드만 집행하고 간편 모드·미관리 경로는 관측만 한다 |
| POL-E-07 | 실행 | P2 | Tool / Resource | 구현 가능(PaC) | Rego + 센서 | call.rego:342 | 2/4 | 2 | Rego 규칙·시험 |  |
| POL-E-08 | 실행 | P1 | Tool / Resource | 구현 가능(PaC) | Rego + 센서 | call.rego:361 | 1/2 | 2 | Rego 규칙·시험 |  |
| POL-E-09 | 실행 | P2 | Tool / Resource | 구현 가능(PaC) | Rego + 센서 | call.rego:381 | 1/5 | 2 | Rego 규칙·시험 |  |
| POL-E-10 | 실행 | P2 | MCP Server | 구현 불가·제외 | Rego + 센서 | resource.rego:92 | 1/3 | 2 | Rego 규칙·시험 | 제외(현재 범위): 게이트웨이가 Resource를 중개하지 않아 전부 거부된다 |
| POL-E-11 | 실행 | P2 | MCP Host 및 MCP Client | 구현 가능(PaC) | Rego + 센서 | call.rego:412, call.rego:417, call.rego:425 | 1/4 | 2 | Rego 규칙·시험 |  |
| POL-E-12 | 실행 | P3 | Agent | 구현 불가·제외 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 현재 게이트웨이는 하네스 내부 대화 컨텍스트를 관측하지 못해 이 조건을 집행할 수 없다. 관리형 하네스 연동을 별도로 설계할 여지는 있다 |
| POL-E-13 | 실행 | P2 | Tool / Resource | 이미 구현 | Rego | call.rego:298, call.rego:304 | 1/3 | 2 | Rego 규칙·시험 |  |
| POL-E-14 | 실행 | P2 | Tool / Resource | 구현 가능(PaC) | Rego + 센서 | call.rego:445 | 1/3 | 3 | Rego 규칙·시험 |  |
| POL-E-15 | 실행 | P2 | Tool / Resource | 이미 구현 | Rego | call.rego:321 | 1/2 | 2 | Rego 규칙·시험 |  |
| POL-E-16 | 실행 | P2 | Tool / Resource | 구현 가능(PaC) | Rego + 센서 | call.rego:468, call.rego:475, call.rego:480 | 1/5 | 3 | Rego 규칙·시험 |  |
| POL-E-17 | 실행 | P2 | Tool / Resource | 구현 가능(PaC) | Rego + 센서 | call.rego:512 | 1/3 | 2 | Rego 규칙·시험 |  |
| POL-E-18 | 실행 | P2 | MCP Server | 구현 가능(PaC) | Rego + 센서 | call.rego:561 | 1/4 | 2 | Rego 규칙·시험 |  |
| POL-E-19 | 실행 | P1 | MCP Server | 구현 가능(PaC) | Rego + 센서 | call.rego:580 | 1/3 | 2 | Rego 규칙·시험 |  |
| POL-E-20 | 실행 | P2 | 사용자 | 구현 가능(PaC) | Rego | call.rego:628, call.rego:634 | 1/4 | 2 | Rego 규칙·시험 |  |
| POL-E-21 | 실행 | P3 | 사용자 | 구현 가능(PaC) | Rego + 센서 | call.rego:658 | 1/4 | 3 | Rego 규칙·시험 |  |
| POL-E-22 | 실행 | P3 | Tool / Resource | 솔루션 기능으로 커버 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 재시도 중복 방지는 실행기의 요청 식별값·작업값 결속, 원자적 예약, 기존 결과 보관과 불명 상태 처리로 구현해야 한다. 현재는 같은 인자 쓰기의 24시간 중복 차단만 있다 |
| POL-E-23 | 실행 | P2 | MCP Host 및 MCP Client | 구현 가능(PaC) | Rego + 센서 | call.rego:533 | 1/5 | 3 | Rego 규칙·시험 |  |
| POL-E-24 | 실행 | P2 | MCP Host 및 MCP Client | 솔루션 기능으로 커버 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 게이트웨이 대기 시간 제한은 있으나 원격 서버에서 이미 시작된 작업의 종료는 실행기·상위 서버 연동으로만 보장할 수 있다 |
| POL-E-25 | 실행 | P1 | MCP Host 및 MCP Client | 구현 가능(PaC) | Rego + 센서 | call.rego:684, call.rego:690 | 2/3 | 2 | Rego 규칙·시험 |  |
| POL-E-26 | 실행 | P2 | MCP Host 및 MCP Client | 이미 구현 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 |  |
| POL-E-27 | 실행 | P2 | MCP Host 및 MCP Client | 솔루션 기능으로 커버 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 감사 저장 실패 시 새 호출 차단, 진행 중 호출의 안전한 중단, 장애 알림과 복구 후 누락 조사까지 저장소·실행기·운영 기능이 필요하다 |
| POL-E-28 | 실행 | P2 | MCP Host 및 MCP Client | 솔루션 기능으로 커버 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 기록 전 가림과 금지 정보 탐지가 필요하고, 제거할 수 없으면 저장 자체를 막아야 한다. 현재 감사 입력은 300자 초과만 축약한다 |
| POL-E-29 | 실행 | P3 | MCP Host 및 MCP Client | 솔루션 기능으로 커버 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 오류를 만드는 경로마다 민감 진단 원문을 막고 표준 오류로 바꿔야 한다. 상위 Tool의 오류 본문은 가림 뒤 그대로 반환된다 |
| POL-O-01 | 관리 | P2 | Tool / Resource | 이미 구현 | Rego + 센서 | call.rego:701, ops.rego:93, ops.rego:100 | 2/6 | 3 | Rego 규칙·시험 |  |
| POL-O-02 | 관리 | P3 | MCP Host 및 MCP Client | 이미 구현 | Rego + 센서 | call.rego:718 | 1/2 | 2 | Rego 규칙·시험 |  |
| POL-O-03 | 관리 | P1 | Tool / Resource | 구현 불가·제외 | Rego + 센서 | resource.rego:109 | 1/3 | 2 | Rego 규칙·시험 | 제외(현재 범위): Resource 미중개로 목록·읽기가 전부 거부된다 |
| POL-O-04 | 관리 | P3 | Tool / Resource | 구현 불가·제외 | Rego + 센서 | resource.rego:128 | 1/2 | 2 | Rego 규칙·시험 | 제외(현재 범위): Resource 미중개로 사용이 전부 거부된다 |
| POL-O-05 | 관리 | P2 | Agent | 구현 불가·제외 | Rego + 센서 | resource.rego:51 | 1/3 | 2 | Rego 규칙·시험 | 제외(현재 범위): Prompt 미중개로 사용이 전부 거부된다 |
| POL-O-06 | 관리 | P2 | MCP Server | 구현 가능(PaC) | Rego + 센서 | intake.rego:296, intake.rego:300, intake.rego:302, ops.rego:122, ops.rego:136 | 3/7 | 3 | Rego 규칙·시험 |  |
| POL-O-07 | 관리 | P2 | MCP Server | 구현 가능(PaC) | Rego + 센서 | ops.rego:156, ops.rego:162, ops.rego:168 | 1/5 | 2 | Rego 규칙·시험 |  |
| POL-O-08 | 관리 | P2 | MCP Server | 구현 가능(PaC) | Rego + 센서 | ops.rego:201 | 8/10 | 5 | Rego 규칙·시험 |  |
| POL-O-09 | 관리 | P3 | MCP Server | 구현 가능(PaC) | Rego + 센서 | ops.rego:247, ops.rego:254 | 1/5 | 3 | Rego 규칙·시험 |  |
| POL-O-10 | 관리 | P2 | MCP Server | 구현 가능(PaC) | Rego + 센서 | ops.rego:276 | 1/4 | 2 | Rego 규칙·시험 |  |
| POL-O-11 | 관리 | P2 | MCP Host 및 MCP Client | 이미 구현 | Rego | connect.rego:328 | 2/2 | 2 | Rego 규칙·시험 |  |
| POL-O-12 | 관리 | P2 | MCP Server | 구현 가능(PaC) | Rego + 센서 | ops.rego:312, ops.rego:319 | 1/2 | 2 | Rego 규칙·시험 |  |
| POL-O-13 | 관리 | P2 | MCP Server | 구현 가능(PaC) | Rego + 센서 | ops.rego:331, ops.rego:338 | 1/2 | 2 | Rego 규칙·시험 |  |
| POL-O-14 | 관리 | P2 | MCP Server | 구현 가능(PaC) | Rego + 센서 | ops.rego:351, ops.rego:357 | 1/2 | 2 | Rego 규칙·시험 |  |
| POL-O-15 | 관리 | P2 | MCP Host 및 MCP Client | 구현 가능(PaC) | Rego + 센서 | ops.rego:371, ops.rego:379 | 1/3 | 2 | Rego 규칙·시험 |  |
| POL-O-16 | 관리 | P2 | MCP Host 및 MCP Client | 솔루션 기능으로 커버 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 로그 수집 설정을 바꾼 뒤 허용·거부·실패 시험을 하고 필수 기록이 빠지면 배포를 멈추는 게이트는 배포 절차(CI)로 만들어야 한다 |
| POL-O-17 | 관리 | P2 | 관리자 | 솔루션 기능으로 커버 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 경보 규칙 적용·정기 시험에서 필수 경보가 나오지 않으면 규칙 적용을 멈추는 것은 운영 절차·경보 시스템 기능이다 |
| POL-O-18 | 관리 | P2 | 관리자 | 솔루션 기능으로 커버 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 담당자 전달 성공 확인, 실패 재시도, 미복구 시 상위 연락 경로 전환은 알림 시스템 기능이다. 경보 저장만으로 전달 완료가 아니다 |
| POL-O-19 | 관리 | P2 | 관리자 | 구현 가능(PaC) | Rego + 센서 | call.rego:741, ops.rego:395 | 3/3 | 2 | Rego 규칙·시험 |  |
| POL-D-01 | 연결 해제 및 폐기 | P3 | 관리자 | 이미 구현 | Rego | call.rego:756, connect.rego:358 | 2/2 | 2 | Rego 규칙·시험 |  |
| POL-D-02 | 연결 해제 및 폐기 | P3 | MCP Host 및 MCP Client | 솔루션 기능으로 커버 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 폐기 서버의 Agent 접속 설정 제거·재등록 차단·재연결 실패 확인은 엔드포인트 키트와 관리형 하네스 설정이 해야 한다 — 관리형 경로 밖 Agent는 입증하지 못함 |
| POL-D-03 | 연결 해제 및 폐기 | P3 | MCP Host 및 MCP Client | 솔루션 기능으로 커버 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 폐기 자격의 요청 차단과 제공자 측 무효화 확인이 필요하다. Gitea 자격 회수 경로(decommission.py:620)는 있으나 모든 제공자로 일반화되지 않았다 |
| POL-D-04 | 연결 해제 및 폐기 | P3 | MCP Server | 솔루션 기능으로 커버 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 관리형 로컬 실행만 중지·확인됨 — 관리 범위 밖 로컬 프로세스 종료·자동 시작 해제는 엔드포인트 조치가 필요하다 |
| POL-D-05 | 연결 해제 및 폐기 | P2 | MCP Server | 솔루션 기능으로 커버 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 문서 저장소의 전용 계정·공유 권한 회수와 결과 확인, 회수 전 접근 차단은 저장소 API 연동 조치다 |
| POL-D-06 | 연결 해제 및 폐기 | P3 | 관리자 | 솔루션 기능으로 커버 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 | 폐기 서버의 전용 허용 경로 제거와 결과 확인은 네트워크 설정 조치다. 다른 서비스와 공유하는 경로는 영향과 대체 경로를 따로 다뤄야 한다 |
| POL-D-07 | 연결 해제 및 폐기 | P3 | 관리자 | 구현 가능(PaC) | Rego + 센서 | ops.rego:415, ops.rego:422 | 1/3 | 2 | Rego 규칙·시험 |  |
| POL-D-08 | 연결 해제 및 폐기 | P2 | 관리자 | 이미 구현 | 솔루션 | — | 0/0 | 0 | Rego 대상 아님 |  |
| POL-D-09 | 연결 해제 및 폐기 | P3 | MCP Host 및 MCP Client | 구현 가능(PaC) | Rego + 센서 | connect.rego:370, connect.rego:375 | 1/9 | 0 | Rego 규칙·시험 |  |
