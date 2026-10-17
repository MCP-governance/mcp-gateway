# 개발 작업별 레퍼런스 읽기 지도

2026-10-17 현재의 [연구 목록](README.md)은 203건이다(2026-10-15 기준 167건 + 정책50 구현 공백 보강 36건). 자료 수·초록 대조·코드 존재를 제품 검증으로 세지 않는다. 아래는 기존 자료를 다음 개발 작업에 연결한 탐색 지도이며 원문 전문을 새로 정독했다는 뜻은 아니다. 새로 확인한 공식 문서의 판본·읽은 절은 [참고 자료 목록](../analysis/review-2026-10-15/references.json)에 기록한다.

| 개발 질문 | 기존 자료 | 함께 확인할 공식 자료/코드 | 결과로 남길 것 |
| --- | --- | --- | --- |
| 승인한 것과 실행한 것이 같은가 | [T15](T15.md), [LIB-J01](LIB-J01.md), J 공급망·감사 묶음 | SLSA v1.2, BuildKit provenance, [ToolHive](../solutions/toolhive-runtime.md) | source→build→image→endpoint 검증, DEV-38 |
| 요청의 신원·자격은 누구의 것인가 | [T01](T01.md), [T10](T10.md), [T11](T11.md), [T12](T12.md), E 인증 묶음 | transport 토큰·upstream 별도 자격·DB 상태 경계 | audience/scope/철회·중지 경쟁, DEV-43 |
| 스키마·프로토콜 변경을 어떻게 다룰까 | [T02](T02.md), A 명세·SDK 묶음 | 2025-11-25와 2026-07-28 차이, JSON Schema 참조 | outputSchema·배열·`$defs`·pagination, DEV-44 |
| 호스트 이름 검사로 충분한가 | [T21](T21.md), [E05](../experiments/E05-ssrf-normalization.md) | OWASP SSRF, MCP OAuth SSRF 절, 실제 서버 outbound | 빈 목적지·redirect·DNS·IPv6, DEV-41 |
| 하네스 설정만으로 우회를 막는가 | [E13](../experiments/E13-local-bypass.md), [권한 근거](../catalogs/endpoint-permission-references.json) | Claude managed hooks·AppArmor 전환·UID 방화벽 | 정상 실행과 훅/셸·비관리 계정 반례, DEV-42·35 |
| 탐지 규칙 점수가 방어 효과인가 | [P38](P38.md), [P39](P39.md), [P43](P43.md), [P60](P60.md), B/C/F 묶음 | [실제 코퍼스 평가](../status/reports/2026-10-15-inspection-corpus.md) | 출처별 분리·독립 한국어·정상 성공·공격 효과, DEV-46 |
| PII 저지연화가 탐지를 보존하는가 | H 개인정보 묶음, [한국어 평가](../status/reports/2026-10-15-inspection-corpus.md) | 실제 Presidio/Gitleaks 판본·지원 entity별 정상/음성군 | 사람명·주소 등 포함 지원범위와 탐지/마스킹 손실 |
| 종료를 완료했다고 말할 수 있는가 | [T19](T19.md), [T20](T20.md), [T22](T22.md) | [종료 모델](../../../docs/ai/TERMINATION_MODEL.md), provider 자원 거부 | 차단·세션/프로세스 정지·자격 회수·백업 복원 반례 |
| 어떤 호출이 실제 효과를 냈는가 | J 관측·감사 묶음 | OpenTelemetry MCP, [증거 계약](../methodology/evidence-contract.md) | run/request/decision/intent/endpoint/외부 효과, DEV-39·45 |
| 외부 LLM Gateway·비밀 저장소와 연결되는가 | [기업 연동](../integrations/README.md), [연동 조건](../analysis/integration-cases.json) | 제품 edition·공식 SDK·LLM 경로와 MCP 경로 분리 | 회전·철회·스트림·장애를 포함한 실제 연동 |
| 서버·MCP outbound와 DNS를 어떻게 막는가 | [LIB-K09](LIB-K09.md), [LIB-K10](LIB-K10.md), [T21](T21.md) | OWASP SSRF Case 1·2, Smokescreen ACL·IP 검사, [E05](../experiments/E05-ssrf-normalization.md) | 해석된 IP·리다이렉트·승인 목적지 변경 재승인, POL-10·26·40 |
| 전송 TLS와 상대 검증은 무엇을 시험하나 | [LIB-K11](LIB-K11.md), [LIB-K12](LIB-K12.md) | RFC 9325 §3.1.1·3.2·7.1, SP 800-52r2 §4.2.2 | TLS 1.0/1.1 거부·호스트 이름 검증·폐지 확인 음성군, POL-16 |
| 에이전트·워크로드 신원은 어떻게 증명하나 | [LIB-K13](LIB-K13.md), [LIB-K14](LIB-K14.md), [LIB-K15](LIB-K15.md), [LIB-K08](LIB-K08.md) | RATS 역할·신선도, SPIFFE SVID, ABAC 속성 | 자기 신고 신원 거부·위임 유효기간·속성 캐시 철회 경쟁, POL-19·20·25 |
| 대량 조회와 중복 쓰기를 어떻게 막나 | [LIB-K27](LIB-K27.md), [LIB-K04](LIB-K04.md), [LIB-K26](LIB-K26.md) | API4:2023, OPA 도구 호출 상한 예, Idempotency-Key 초안(만료) | 반환 건수·크기 상한, 같은 키 동시·재시도·다른 인자 재사용의 업스트림 쓰기 횟수, POL-35·36·28 |
| 공급자 측 회수·철회 전파를 확인했나 | [LIB-K25](LIB-K25.md), [LIB-K28](LIB-K28.md), [LIB-K29](LIB-K29.md), [LIB-K30](LIB-K30.md) | Secrets 수명주기·SSF·CAEP·SET | 회수 뒤 이전 값의 제공자 거부, 재사용 시도 감사, POL-41·44·45·47 |
| 경보·대응·복원 검증은 어디까지 하나 | [LIB-K31](LIB-K31.md), [LIB-K32](LIB-K32.md), [LIB-K03](LIB-K03.md) | SP 800-61r3 DE.AE·RS.MI·RC.RP, SP 800-34r1 복원 단계, OPA 결정 로그 | 설정 변경 뒤 경보 발화, 복원 뒤 폐기 연결 재활성화 거부(문서에 없어 추가 항목), POL-42·43·50 |
| 정책 번호와 정책 변경은 어떻게 추적·시험하나 | [LIB-K01](LIB-K01.md), [LIB-K02](LIB-K02.md), [LIB-K05](LIB-K05.md), [LIB-K06](LIB-K06.md) | OSCAL 매핑 관계값, `opa test`, Regal, Cedar 동치 분석 | POL↔PAC 매핑 레코드, 케이스 이름의 POL 번호, 변경 전후 결정 회귀, POL-37 |
| 취약점·공급망 증거는 무엇으로 남기나 | [LIB-K16](LIB-K16.md), [LIB-K17](LIB-K17.md), [LIB-K18](LIB-K18.md), [LIB-K19](LIB-K19.md), [LIB-K20](LIB-K20.md), [LIB-K21](LIB-K21.md), [LIB-K22](LIB-K22.md), [LIB-K23](LIB-K23.md) | Sigstore, Scorecard, OSV, KEV, BOD 26-04, EPSS, CSAF·VEX | 서명자 신원·취약점 판정·조치 기한·영향 없음 근거, POL-01·03·39 |
| 엑셀 근거 열의 법령·표준 인용이 맞는가 | [LIB-K35](LIB-K35.md), [LIB-K36](LIB-K36.md), [LIB-K34](LIB-K34.md), [LIB-K33](LIB-K33.md) | ISMS-P 안내서 항목·쪽, 개인정보 보호법 현행 조문, ISO 판본 | 확인된 인용과 검증 불가 인용(ISO 42001 조항 8건) 구분, 법적 적합성 판단 아님 |

법령·인증이 적힌 자료는 I 묶음과 원문 적용 조건을 따로 검토한다. 국내 모델 여부나 GS·CSAP 같은 표기만으로 실제 처리 위치·MCP 실행 경로·해당 배포의 보안 승인을 추정하지 않는다. 이번 기술 위키 보강에서는 법적 적합성 판단을 하지 않았다.
