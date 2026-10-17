# 정책50 구현 공백 보강 레퍼런스 지도 (2026-10-17)

정책50(MCP_보안정책50.xlsm, POL-01~50)의 기술 통제 구현에서 부분 구현으로 남은 공백을 메울 근거 문헌 36건(`LIB-K01`~`LIB-K36`)을 원문 확인 후 등록했다. 아래는 공백별로 어떤 자료가 어느 POL 번호에 쓰이는지 보인다. 자료를 등록했다는 사실이 해당 POL의 구현·검수 완료를 뜻하지 않으며, 정책 번호 체계(POL50, 독스용 PAC50, 원본 PAC24, 런타임 PAC-01~15)를 번호로 대응시키지 않는다. 확인 근거와 해시는 [검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json)에 있다.

## 공백별 근거 자료

### 목적지 DNS·서버 outbound

| 정책 | 근거 자료 |
| --- | --- |
| POL-10 | [LIB-K09](LIB-K09.md), [LIB-K10](LIB-K10.md), [LIB-K27](LIB-K27.md) |
| POL-24 | [LIB-K09](LIB-K09.md) |
| POL-26 | [LIB-K09](LIB-K09.md), [LIB-K10](LIB-K10.md) |
| POL-40 | [LIB-K09](LIB-K09.md), [LIB-K10](LIB-K10.md) |

### 전송 TLS

| 정책 | 근거 자료 |
| --- | --- |
| POL-16 | [LIB-K04](LIB-K04.md), [LIB-K11](LIB-K11.md), [LIB-K12](LIB-K12.md) |

### 에이전트 신원·위임

| 정책 | 근거 자료 |
| --- | --- |
| POL-15 | [LIB-K14](LIB-K14.md) |
| POL-19 | [LIB-K08](LIB-K08.md), [LIB-K13](LIB-K13.md), [LIB-K14](LIB-K14.md), [LIB-K15](LIB-K15.md) |
| POL-20 | [LIB-K08](LIB-K08.md), [LIB-K13](LIB-K13.md), [LIB-K14](LIB-K14.md), [LIB-K15](LIB-K15.md), [LIB-K29](LIB-K29.md) |
| POL-21 | [LIB-K14](LIB-K14.md) |
| POL-22 | [LIB-K08](LIB-K08.md) |

### 데이터 등급

| 정책 | 근거 자료 |
| --- | --- |
| POL-25 | [LIB-K07](LIB-K07.md), [LIB-K08](LIB-K08.md), [LIB-K27](LIB-K27.md) |

### 대량 조회·호출량

| 정책 | 근거 자료 |
| --- | --- |
| POL-28 | [LIB-K04](LIB-K04.md), [LIB-K27](LIB-K27.md) |
| POL-35 | [LIB-K04](LIB-K04.md), [LIB-K27](LIB-K27.md) |

### 중복 실행

| 정책 | 근거 자료 |
| --- | --- |
| POL-36 | [LIB-K26](LIB-K26.md) |

### 공급자 측 자격 회수

| 정책 | 근거 자료 |
| --- | --- |
| POL-14 | [LIB-K25](LIB-K25.md) |
| POL-22 | [LIB-K29](LIB-K29.md) |
| POL-41 | [LIB-K25](LIB-K25.md), [LIB-K28](LIB-K28.md) |
| POL-44 | [LIB-K28](LIB-K28.md), [LIB-K29](LIB-K29.md), [LIB-K30](LIB-K30.md), [LIB-K35](LIB-K35.md) |
| POL-45 | [LIB-K25](LIB-K25.md), [LIB-K28](LIB-K28.md), [LIB-K29](LIB-K29.md), [LIB-K35](LIB-K35.md) |
| POL-47 | [LIB-K25](LIB-K25.md) |
| POL-49 | [LIB-K25](LIB-K25.md) |

### 경보 검증·자동 대응

| 정책 | 근거 자료 |
| --- | --- |
| POL-38 | [LIB-K03](LIB-K03.md), [LIB-K30](LIB-K30.md) |
| POL-42 | [LIB-K03](LIB-K03.md), [LIB-K31](LIB-K31.md) |
| POL-43 | [LIB-K20](LIB-K20.md), [LIB-K31](LIB-K31.md), [LIB-K35](LIB-K35.md), [LIB-K36](LIB-K36.md) |

### 복원 후 재활성화

| 정책 | 근거 자료 |
| --- | --- |
| POL-46 | [LIB-K32](LIB-K32.md), [LIB-K35](LIB-K35.md) |
| POL-50 | [LIB-K31](LIB-K31.md), [LIB-K32](LIB-K32.md), [LIB-K35](LIB-K35.md) |

### 정책 번호 체계 표류

| 정책 | 근거 자료 |
| --- | --- |
| POL-01~POL-50 | [LIB-K01](LIB-K01.md), [LIB-K02](LIB-K02.md), [LIB-K03](LIB-K03.md), [LIB-K05](LIB-K05.md) |

### 정책 변경 시험·동치 분석

| 정책 | 근거 자료 |
| --- | --- |
| POL-22 | [LIB-K02](LIB-K02.md), [LIB-K04](LIB-K04.md), [LIB-K06](LIB-K06.md) |
| POL-23 | [LIB-K06](LIB-K06.md) |
| POL-37 | [LIB-K02](LIB-K02.md), [LIB-K05](LIB-K05.md), [LIB-K06](LIB-K06.md), [LIB-K07](LIB-K07.md) |
| POL-44 | [LIB-K02](LIB-K02.md) |

### 공급망 출처·취약점 대응

| 정책 | 근거 자료 |
| --- | --- |
| POL-01 | [LIB-K16](LIB-K16.md), [LIB-K17](LIB-K17.md) |
| POL-03 | [LIB-K17](LIB-K17.md), [LIB-K18](LIB-K18.md), [LIB-K22](LIB-K22.md) |
| POL-39 | [LIB-K16](LIB-K16.md), [LIB-K17](LIB-K17.md), [LIB-K18](LIB-K18.md), [LIB-K19](LIB-K19.md), [LIB-K20](LIB-K20.md), [LIB-K21](LIB-K21.md), [LIB-K22](LIB-K22.md), [LIB-K23](LIB-K23.md), [LIB-K24](LIB-K24.md) |

### 법령·표준 근거 확인

| 정책 | 근거 자료 |
| --- | --- |
| POL-02 | [LIB-K34](LIB-K34.md), [LIB-K36](LIB-K36.md) |
| POL-03 | [LIB-K34](LIB-K34.md) |
| POL-05 | [LIB-K34](LIB-K34.md) |
| POL-07 | [LIB-K34](LIB-K34.md), [LIB-K36](LIB-K36.md) |
| POL-08 | [LIB-K33](LIB-K33.md) |
| POL-09 | [LIB-K36](LIB-K36.md) |
| POL-10 | [LIB-K35](LIB-K35.md) |
| POL-16 | [LIB-K35](LIB-K35.md) |
| POL-26 | [LIB-K33](LIB-K33.md), [LIB-K36](LIB-K36.md) |
| POL-30 | [LIB-K36](LIB-K36.md) |
| POL-31 | [LIB-K36](LIB-K36.md) |
| POL-32 | [LIB-K34](LIB-K34.md) |
| POL-37 | [LIB-K34](LIB-K34.md) |
| POL-38 | [LIB-K34](LIB-K34.md), [LIB-K35](LIB-K35.md), [LIB-K36](LIB-K36.md) |
| POL-39 | [LIB-K34](LIB-K34.md) |
| POL-48 | [LIB-K36](LIB-K36.md) |
| POL-49 | [LIB-K36](LIB-K36.md) |

## 자료 목록

| ID | 자료 | 확인 수준 | 라이선스 |
| --- | --- | --- | --- |
| [LIB-K01](LIB-K01.md) | OSCAL v1.2.3 통제 매핑 모델 | `page_text_read` | CC0 1.0 |
| [LIB-K02](LIB-K02.md) | OPA Policy Testing | `page_text_read` | Apache-2.0(저장소) |
| [LIB-K03](LIB-K03.md) | OPA Decision Logs | `page_text_read` | Apache-2.0(저장소) |
| [LIB-K04](LIB-K04.md) | OPA Agent Tool Calling | `page_text_read` | Apache-2.0(저장소) |
| [LIB-K05](LIB-K05.md) | Regal v0.43.0 | `page_text_read` | Apache-2.0 |
| [LIB-K06](LIB-K06.md) | Cedar (OOPSLA 2024) | `bibliographic_and_abstract_checked` | CC BY 4.0 |
| [LIB-K07](LIB-K07.md) | Zelkova (FMCAD 2018) | `bibliographic_and_abstract_checked` | 미확인 |
| [LIB-K08](LIB-K08.md) | NIST SP 800-162 (ABAC) | `full_text_selected_sections_read` | 미국 비저작권(NIST) |
| [LIB-K09](LIB-K09.md) | OWASP SSRF Prevention Cheat Sheet | `full_text_selected_sections_read` | CC BY-SA 4.0 |
| [LIB-K10](LIB-K10.md) | Stripe Smokescreen v0.1.0 | `page_text_read` | MIT |
| [LIB-K11](LIB-K11.md) | RFC 9325 / BCP 195 (TLS 권고) | `full_text_selected_sections_read` | IETF Trust |
| [LIB-K12](LIB-K12.md) | NIST SP 800-52 Rev. 2 (TLS) | `full_text_selected_sections_read` | 미국 비저작권(NIST) |
| [LIB-K13](LIB-K13.md) | RFC 9334 (RATS 아키텍처) | `full_text_selected_sections_read` | IETF Trust |
| [LIB-K14](LIB-K14.md) | SPIFFE ID·X509-SVID·JWT-SVID | `full_text_selected_sections_read` | Apache-2.0 |
| [LIB-K15](LIB-K15.md) | SPIRE v1.15.4 | `page_text_read` | Apache-2.0 |
| [LIB-K16](LIB-K16.md) | Sigstore (CCS 2022) | `bibliographic_and_abstract_checked` | CC BY 4.0 |
| [LIB-K17](LIB-K17.md) | OpenSSF Scorecard v5.6.0 점검 항목 | `full_text_selected_sections_read` | Apache-2.0 |
| [LIB-K18](LIB-K18.md) | OSV 스키마 1.9.2 | `page_text_read` | Apache-2.0(저장소) |
| [LIB-K19](LIB-K19.md) | CISA KEV 카탈로그 | `page_text_read` | CC0 1.0 |
| [LIB-K20](LIB-K20.md) | CISA BOD 26-04 (BOD 22-01 대체) | `full_text_selected_sections_read` | 미확인 |
| [LIB-K21](LIB-K21.md) | FIRST EPSS 모델 v5 | `page_text_read` | 무료·출처 표시 요청 |
| [LIB-K22](LIB-K22.md) | CSAF 2.0 (OASIS Standard) | `full_text_selected_sections_read` | OASIS 고지 |
| [LIB-K23](LIB-K23.md) | OpenVEX v0.2.0 | `full_text_selected_sections_read` | CC0-1.0 |
| [LIB-K24](LIB-K24.md) | CISA VEX 최소 요건 | `page_metadata_checked` | 미확인 |
| [LIB-K25](LIB-K25.md) | OWASP Secrets Management Cheat Sheet | `full_text_selected_sections_read` | CC BY-SA 4.0 |
| [LIB-K26](LIB-K26.md) | Idempotency-Key 초안 -07 (만료) | `full_text_selected_sections_read` | IETF Trust |
| [LIB-K27](LIB-K27.md) | OWASP API Security Top 10 2023 | `full_text_selected_sections_read` | CC BY-SA 4.0 |
| [LIB-K28](LIB-K28.md) | OpenID Shared Signals Framework 1.0 | `full_text_selected_sections_read` | OIDF 고지 |
| [LIB-K29](LIB-K29.md) | OpenID CAEP 1.0 | `full_text_selected_sections_read` | OIDF 고지 |
| [LIB-K30](LIB-K30.md) | RFC 8417 (SET) | `full_text_selected_sections_read` | IETF Trust |
| [LIB-K31](LIB-K31.md) | NIST SP 800-61 Rev. 3 | `full_text_selected_sections_read` | 미국 비저작권(NIST) |
| [LIB-K32](LIB-K32.md) | NIST SP 800-34 Rev. 1 | `full_text_selected_sections_read` | 미국 비저작권(NIST) |
| [LIB-K33](LIB-K33.md) | ISO/IEC TS 27560:2023 (동의 기록) | `page_metadata_checked` | ISO(유료, 본문 미복제) |
| [LIB-K34](LIB-K34.md) | ISO/IEC 42001:2023 | `page_metadata_checked` | ISO(유료, 본문 미복제) |
| [LIB-K35](LIB-K35.md) | ISMS-P 인증기준 안내서 2023.11. | `full_text_selected_sections_read` | 출처 표시 의무 |
| [LIB-K36](LIB-K36.md) | 개인정보 보호법 (시행 2026.9.11.) | `full_text_selected_sections_read` | 법령(본문 미복제) |

## 등록하지 않았거나 확인하지 못한 것

| 항목 | 상태 | 이유·대체 |
| --- | --- | --- |
| CISA BOD 22-01 | 등록 안 함 | 2026-06-10 폐지되고 BOD 26-04로 대체됨을 원문에서 확인. 대신 BOD 26-04를 등록(LIB-K20) |
| CSAF 2.1 | 표준으로 등록 안 함 | 2026-09-11 기준 Committee Specification Draft 03. 2.0 OASIS Standard만 등록(LIB-K22) |
| NIST SP 800-52 Rev. 3 | 확인 못 함 | 추측한 초안 주소가 404였고 Rev. 2 페이지는 "검토 중"만 표시. Rev. 2만 등록(LIB-K12) |
| ISO/IEC TS 27560·ISO/IEC 42001 본문 | 본문 미열람 | 유료 표준. 랜딩 페이지의 판본·초록만 등록(LIB-K33·K34). 엑셀의 ISO 42001 조항 번호 8건은 미검증 인용 |
| KISA ISMS-P 자료실 원본 페이지 | 열지 못함 | isms.kisa.or.kr 이름 해석 실패. 개인정보위·개인정보 포털 게시물과 같은 PDF로 대체 확인(LIB-K35). 더 새로운 개정판 유무는 미확인 |
| ACM 디지털 라이브러리(Sigstore 본문, Cedar ACM 판) | 열지 못함 | HTTP 403 봇 차단. Crossref·OpenAlex·Semantic Scholar·arXiv로 서지·초록만 대조(LIB-K16·K06) |
| OPA `ids` 필드 도입 판본 | 일부 확인 | `rule_labels`는 저장소 OPA 1.20.2에서 동작(일회성 시험). `id` 주석은 1.20.2에서 `ids`로 남지 않음. 도입 판본과 1.21.x는 미시험(LIB-K03) |
| SSF/CAEP·SPIFFE·SPIRE·Smokescreen·OSCAL 스키마의 코드·상세 | 미열람 | 명세 구조·README·메타데이터 수준만 읽음. 상류 제공자의 SSF/CAEP 지원 여부는 미확인 |
| NIST 토큰 보안 신규 지침(2026-09) | 단서만 | OIDF 페이지의 한 줄 언급. 열지 않았고 등록하지 않음 |

