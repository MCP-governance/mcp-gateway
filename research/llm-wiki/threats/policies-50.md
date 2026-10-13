# (본)정책 최종본 — 50개 정책

원본 셀에서 추출한 정책입니다. 이 표의 PAC 번호와 런타임 PAC-01~15는 다른 식별자 체계입니다.
정책 수와 표준·법령 버전은 원본 기재값이며 현재성이나 구현 완료를 뜻하지 않습니다.

## POL-01 배포물 출처와 무결성 확인

출처: `(본)정책 최종본!A5` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-01

**영역**

도입 검토

**정책명**

배포물 출처와 무결성 확인

**정책 내용**

도입 담당자는 MCP 서버와 의존성의 배포처, 배포자, 버전과 무결성 검증 결과를 기록하여야
한다. 배포자의 서명이나 해시 등 승인된 방법으로 검증하고, 출처 미확인, 검증 실패 또는 결과
부재 시 도입을 보류하여야 한다.

**CIA 영향**

무결성

**OWASP MCP Top 10 2025 Beta**

MCP04: Software Supply Chain Attacks and Dependency Tampering

**OWASP MCP Security Cheat Sheet**

9. Supply Chain Security

## POL-02 도입 범위와 필요 권한 검토

출처: `(본)정책 최종본!A6` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-02

**정책명**

도입 범위와 필요 권한 검토

**정책 내용**

도입 담당자는 기능, 목적, 데이터, 권한과 외부 전송을 검토하고 승인 범위만 등록하여야 한다.
개인정보 수집과 이용의 적법한 근거 및 목적을 확인하여야 한다. AI 제품이나 서비스 제공
사업자는 고영향 AI 해당 여부를 사전 검토하여야 한다.

**CIA 영향**

기밀성

**MCP Specification 2026-07-28**

Authorization: 6
Scope Selection Strategy

**MCP Security Best Practices 2026-07-28**

Scope Minimization/ Mitigation

**OWASP MCP Top 10 2025 Beta**

MCP02: Privilege Escalation via Scope Creep

**OWASP MCP Security Cheat Sheet**

1. Principle of Least Privilege

**ISO 42001:2023**

A.6.2.2 AI system requirements and specification

**ISMS-P 인증기준 2023.11 안내서**

2.8.1 보안 요구사항 정의

**NIST AI RMF 1.0**

MAP 3.3

**개인정보 보호법 2026-09-11 시행**

제15조제1항

**인공지능기본법 2026-07-21 시행**

제33조제1항

## POL-03 보안 업데이트 지원 여부 확인

출처: `(본)정책 최종본!A7` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-03

**정책명**

보안 업데이트 지원 여부 확인

**정책 내용**

도입 담당자는 MCP 서버 제공자의 유지보수, 보안 공지 및 취약점 수정 지원을 확인하여야
한다. 지원이 종료되었거나 수정 경로가 불명확한 서버의 신규 도입은 보류하여야 한다.

**CIA 영향**

무결성

**OWASP MCP Top 10 2025 Beta**

MCP04: Software Supply Chain Attacks and Dependency Tampering

**ISO 42001:2023**

B.10.3 Suppliers (p.44)

**ISMS-P 인증기준 2023.11 안내서**

2.10.8 패치관리 (pp.166-167)

**NIST AI RMF 1.0**

MAP 4.1

## POL-04 Tool의 악성 지시 검토

출처: `(본)정책 최종본!A8` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-04

**정책명**

Tool의 악성 지시 검토

**정책 내용**

에이전트는 Tool 설명을 기능 이해 목적으로만 사용하여야 한다. 사용자의 요청과 승인된 업무
범위를 벗어나는 Tool의 추가 지시를 따라서는 안 된다.

**CIA 영향**

무결성

**MCP Specification 2026-07-28**

Specification: 3.1.3
Key Principles/Tool Safety

**OWASP MCP Top 10 2025 Beta**

MCP03: Tool Poisoning

**OWASP MCP Security Cheat Sheet**

2. Tool Description & Schema Integrity

## POL-05 Tool 설명과 실제 동작의 일치 시험

출처: `(본)정책 최종본!A9` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-05

**정책명**

Tool 설명과 실제 동작의 일치 시험

**정책 내용**

보안 담당자는 제한된 시험 환경에서 Tool 설명과 실제 조회, 변경 및 전송 동작의 일치를
시험하여야 한다. 실제 동작이 설명이나 승인 신청과 다르면 운영 연결을 승인해서는 안 된다.

**CIA 영향**

무결성

**OWASP MCP Top 10 2025 Beta**

MCP03: Tool Poisoning

**ISO 42001:2023**

B.6.2.4 AI system verification and validation (pp.32-33)

**ISMS-P 인증기준 2023.11 안내서**

2.8.2 보안 요구사항 검토 및 시험 (p.124)

**NIST AI RMF 1.0**

MEASURE 2.3

## POL-06 서버 제공 Prompt 템플릿 검토

출처: `(본)정책 최종본!A10` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-06

**정책명**

서버 제공 Prompt 템플릿 검토

**정책 내용**

보안 담당자는 서버 제공 Prompt 템플릿의 본문과 변수 입력을 검토하여야 한다. 업무 지시를
왜곡하거나 불필요한 내부정보를 요구하는 템플릿의 사용을 승인해서는 안 된다.

**CIA 영향**

무결성

**MCP Specification 2026-07-28**

Prompts: 8
Security

**OWASP MCP Top 10 2025 Beta**

MCP06: Intent Flow Subversion

## POL-07 외부 제공자의 문서 처리 조건 확인

출처: `(본)정책 최종본!A11` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-07

**정책명**

외부 제공자의 문서 처리 조건 확인

**정책 내용**

도입 담당자는 외부 MCP 제공자의 문서와 결과 저장, 재사용 및 제3자 제공을 확인하여야
한다. 보관, 삭제, 처리 위치가 불명확하거나 조직 기준에 맞지 않으면 도입을 보류하여야 한다.

**CIA 영향**

기밀성

**ISO 42001:2023**

B.10.3 Suppliers (p.44)

**ISMS-P 인증기준 2023.11 안내서**

2.3.2 외부자 계약 시 보안 (pp.69~70)

**NIST AI RMF 1.0**

MAP 4.1

**개인정보 보호법 2026-09-11 시행**

제26조제1항

## POL-08 연결 승인과 사용자 동의 확인

출처: `(본)정책 최종본!A12` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-08

**영역**

등록 및 연결

**정책명**

연결 승인과 사용자 동의 확인

**정책 내용**

호스트와 게이트웨이는 등록된 서버 식별자, 주소, 승인 조건과 유효기간을 확인하여야 한다.
관리자 승인과 데이터 접근 및 기능 사용의 사용자 동의를 각각 확인한 경우에만 연결을
허용하여야 한다. 주소 등록만으로 승인을 갈음해서는 안 된다.

**CIA 영향**

기밀성

**MCP Specification 2026-07-28**

Specification: 3.1.1
Key Principles/User Consent and Control

**OWASP MCP Top 10 2025 Beta**

MCP09: Shadow MCP Servers

**OWASP MCP Security Cheat Sheet**

11. Consent & Installation Security

## POL-09 실행 환경과 시험 데이터 관리

출처: `(본)정책 최종본!A13` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-09

**정책명**

실행 환경과 시험 데이터 관리

**정책 내용**

운영 담당자는 개발, 시험, 운영 접근을 분리하고 승인된 자원만 허용하여야 한다. 시험은 생성
또는 가공 데이터로 수행하되 운영 데이터와 인증정보는 불가피한 경우 책임자 승인, 보호 및
감시 하에 사용하여야 한다. 법정 보존 대상 외 시험 데이터는 사용 후 즉시 삭제하여야 한다.

**CIA 영향**

기밀성

**MCP Security Best Practices 2026-07-28**

Local MCP Server Compromise/ Mitigation

**OWASP MCP Top 10 2025 Beta**

MCP05: Command Injection and Execution

**OWASP MCP Security Cheat Sheet**

3. Sandbox and Isolate MCP Servers

**ISMS-P 인증기준 2023.11 안내서**

2.8.4 시험 데이터 보안

**개인정보 보호법 2026-09-11 시행**

제21조제1항

## POL-10 실제 연결 주소 확인

출처: `(본)정책 최종본!A14` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-10

**정책명**

실제 연결 주소 확인

**정책 내용**

클라이언트와 게이트웨이는 DNS, 리디렉션 및 OAuth 조회를 포함한 실제 연결 주소를
검증하여야 한다. 대상이 불명확하거나 승인 범위 밖이면 차단하고, 도구를 통한 외부 데이터
전송에는 PAC26을 적용하여야 한다.

**CIA 영향**

무결성

**MCP Security Best Practices 2026-07-28**

Server-Side Request Forgery (SSRF)/ Mitigation

**OWASP MCP Security Cheat Sheet**

5. Input and Output Validation

**ISMS-P 인증기준 2023.11 안내서**

2.6.1 네트워크 접근

## POL-11 서버별 사용 기능 등록

출처: `(본)정책 최종본!A15` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-11

**정책명**

서버별 사용 기능 등록

**정책 내용**

게이트웨이는 서버 식별자, 기능 유형과 식별자의 허용목록에 따라 기능을 허용하여야 한다. 새
기능은 검토 후 등록하고 서버 식별자와 표시 이름을 구분하여야 한다. 연결 승인으로 새
기능을 허용하거나 다른 서버의 동명 기능에 승인을 재사용해서는 안 된다.

**CIA 영향**

무결성

**MCP Specification 2026-07-28**

Tools: 5.1.1
Data Types/Tool/Tool Names

**OWASP MCP Top 10 2025 Beta**

MCP07: Insufficient Authentication and Authorization

**ISMS-P 인증기준 2023.11 안내서**

2.6.3 응용프로그램 접근

## POL-12 게이트웨이 우회 연결 차단

출처: `(본)정책 최종본!A16` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-12

**정책명**

게이트웨이 우회 연결 차단

**정책 내용**

운영 담당자는 MCP 게이트웨이 환경의 관리 대상 MCP 접근을 게이트웨이 경유로 제한하여야
한다. 에이전트의 직접 연결과 로컬 서버 실행을 제한하고 우회를 탐지하여 기록하여야 한다.

**CIA 영향**

무결성

**OWASP MCP Top 10 2025 Beta**

MCP09: Shadow MCP Servers

**ISMS-P 인증기준 2023.11 안내서**

2.6.1 네트워크 접근

## POL-13 인증 응답과 요청 상태의 일치 확인

출처: `(본)정책 최종본!A17` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-13

**정책명**

인증 응답과 요청 상태의 일치 확인

**정책 내용**

HTTP OAuth 클라이언트는 인증 응답의 반환 주소, 발급자와 요청 상태를 현재 인증 요청과
대조하여야 한다. 불일치하거나 재사용된 응답은 토큰 교환 전에 거부하여야 한다.

**CIA 영향**

무결성

**MCP Specification 2026-07-28**

Authorization: 7.1
Authorization Response Validation

**MCP Security Best Practices 2026-07-28**

Mix-Up Attacks/ Mitigation

**OWASP MCP Top 10 2025 Beta**

MCP07: Insufficient Authentication and Authorization

## POL-14 연결 설정의 인증정보 평문 노출 방지

출처: `(본)정책 최종본!A18` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-14

**정책명**

연결 설정의 인증정보 평문 노출 방지

**정책 내용**

운영 담당자는 토큰과 API 키를 승인된 비밀정보 보관 수단으로 관리하여야 한다. 설정 파일,
실행 인자와 오류 메시지의 원문 노출을 방지하고 노출된 인증정보는 교체하여야 한다.

**CIA 영향**

기밀성

**MCP Specification 2026-07-28**

Authorization Security Considerations: 2
Token Theft

**OWASP MCP Top 10 2025 Beta**

MCP01: Token Mismanagement and Secret Exposure

**OWASP MCP Security Cheat Sheet**

6. Authentication, Authorization & Transport Security

**ISMS-P 인증기준 2023.11 안내서**

2.7.1 암호정책 적용

## POL-15 MCP Server별 인증정보 분리

출처: `(본)정책 최종본!A19` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-15

**정책명**

MCP Server별 인증정보 분리

**정책 내용**

운영 담당자는 인증정보의 사용 대상과 접근 범위를 MCP 서버별로 구분하여야 한다. 특정
서버의 토큰이나 API 키를 다른 서버의 연결 설정에 재사용해서는 안 된다.

**CIA 영향**

기밀성

**MCP Specification 2026-07-28**

Authorization: 9.2
Token Handling

**OWASP MCP Top 10 2025 Beta**

MCP07: Insufficient Authentication and Authorization

**OWASP MCP Security Cheat Sheet**

1. Principle of Least Privilege

## POL-16 원격 MCP 전송 구간 보호

출처: `(본)정책 최종본!A20` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-16

**정책명**

원격 MCP 전송 구간 보호

**정책 내용**

운영 담당자는 원격 MCP 연결에 승인된 암호화 전송을 적용하고 연결 상대를 검증하여야
한다. 평문 전송이나 검증되지 않은 중간 경로를 거치는 구성은 운영에서 제외하여야 한다.

**CIA 영향**

기밀성

**MCP Specification 2026-07-28**

Authorization Security Considerations: 3
Communication Security

**OWASP MCP Top 10 2025 Beta**

MCP07: Insufficient Authentication and Authorization

**OWASP MCP Security Cheat Sheet**

6. Authentication, Authorization & Transport Security

**ISMS-P 인증기준 2023.11 안내서**

2.7.1 암호정책 적용

## POL-17 로컬 서버 실행 명령 검증

출처: `(본)정책 최종본!A21` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-17

**정책명**

로컬 서버 실행 명령 검증

**정책 내용**

호스트는 로컬 MCP 서버 시작 전에 실행 경로, 인자와 환경변수를 승인 설정과 대조하여야
한다. 명령이나 실행 파일이 바뀌었거나 미승인 인자가 있으면 서버를 시작해서는 안 된다.

**CIA 영향**

무결성

**MCP Security Best Practices 2026-07-28**

Local MCP Server Compromise/ Mitigation/ Pre-Configuration Consent

**OWASP MCP Top 10 2025 Beta**

MCP05: Command Injection and Execution

**OWASP MCP Security Cheat Sheet**

11. Consent & Installation Security

## POL-18 HTTP 요청 출처 검증

출처: `(본)정책 최종본!A22` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-18

**정책명**

HTTP 요청 출처 검증

**정책 내용**

MCP 서버는 연결 요청에 승인된 출처 기준을 적용하여야 하며, 허용 범위를 벗어난 요청은 차단하여야 한다.

**CIA 영향**

기밀성

**MCP Specification 2026-07-28**

Streamable HTTP: 1
Security & Endpoint

**OWASP MCP Top 10 2025 Beta**

MCP07: Insufficient Authentication and Authorization

**OWASP MCP Security Cheat Sheet**

6. Authentication, Authorization & Transport Security

## POL-19 사용자와 에이전트 신원 확인

출처: `(본)정책 최종본!A23` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-19

**영역**

실행 및 통제

**정책명**

사용자와 에이전트 신원 확인

**정책 내용**

인증 시스템은 신뢰할 수 있는 경로로 사용자와 에이전트의 신원 및 승인을 검증하여야 한다.
요청의 이름이나 외부 설명만으로 신원을 인정해서는 안 되며, 업무 세션 사용 시 요청 주체와
일치하는지 확인하여야 한다.

**CIA 영향**

무결성

**MCP Security Best Practices 2026-07-28**

State Handle Hijacking/ Mitigation

**OWASP MCP Top 10 2025 Beta**

MCP07: Insufficient Authentication and Authorization

**ISMS-P 인증기준 2023.11 안내서**

2.5.3 사용자 인증

## POL-20 위임 범위와 유효기간 확인

출처: `(본)정책 최종본!A24` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-20

**정책명**

위임 범위와 유효기간 확인

**정책 내용**

게이트웨이는 호출마다 위임의 발급 경로, 주체, 목적, 범위 및 유효기간을 검증하여야 한다.
사용자 권한과 위임 범위 내의 승인된 서버와 기능만 허용하고, 위임정보가 없거나 검증 실패
시 요청을 거부하여야 한다.

**CIA 영향**

무결성

**OWASP MCP Top 10 2025 Beta**

MCP02: Privilege Escalation via Scope Creep

**ISMS-P 인증기준 2023.11 안내서**

2.5.1 사용자 계정 관리

## POL-21 OAuth 토큰 검증

출처: `(본)정책 최종본!A25` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-21

**정책명**

OAuth 토큰 검증

**정책 내용**

HTTP OAuth 서버는 토큰 형식에 맞게 발급자, 대상, 유효기간과 Scope를 검증하여야 한다.
대상 불일치, 만료, 검증 실패 또는 권한 부족 시 요청을 거부하여야 한다.

**CIA 영향**

무결성

**MCP Specification 2026-07-28**

Authorization: 9.2
Token Handling

**MCP Security Best Practices 2026-07-28**

Token Passthrough/ Mitigation

**OWASP MCP Top 10 2025 Beta**

MCP07: Insufficient Authentication and Authorization

**OWASP MCP Security Cheat Sheet**

6. Authentication, Authorization & Transport Security

## POL-22 요청마다 실행 권한 확인

출처: `(본)정책 최종본!A26` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-22

**정책명**

요청마다 실행 권한 확인

**정책 내용**

게이트웨이는 실행마다 기능, 작업, 입력, 데이터와 목적지를 최신 승인 및 위임 상태에 따라
검사하여야 한다. 판단 정보가 없으면 차단하고 범위가 바뀐 요청에 이전 허용 결과를
재사용해서는 안 된다.

**CIA 영향**

무결성

**MCP Specification 2026-07-28**

Tools: 8
Security Considerations

**OWASP MCP Top 10 2025 Beta**

MCP07: Insufficient Authentication and Authorization

**OWASP MCP Security Cheat Sheet**

6. Authentication, Authorization & Transport Security

## POL-23 작업별 권한 구분

출처: `(본)정책 최종본!A27` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-23

**정책명**

작업별 권한 구분

**정책 내용**

게이트웨이는 기능별 조회, 생성, 수정, 삭제, 실행 및 전송의 권한을 구분하여 검사하여야
한다. 조회 권한이나 연결 승인만으로 수정, 삭제 또는 전송을 허용해서는 안 된다.

**CIA 영향**

무결성

**OWASP MCP Top 10 2025 Beta**

MCP02: Privilege Escalation via Scope Creep

**ISMS-P 인증기준 2023.11 안내서**

2.6.3 응용프로그램 접근

## POL-24 입력값과 실행 대상 검사

출처: `(본)정책 최종본!A28` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-24

**정책명**

입력값과 실행 대상 검사

**정책 내용**

서버와 게이트웨이는 정규화한 실제 입력과 실행 대상을 규격 및 승인 범위와 대조하여야
한다. 불명확하거나 범위를 벗어난 요청은 거부하고, Resource URI와 파일 경로는 제공
서버가 검증하여야 한다.

**CIA 영향**

무결성

**MCP Specification 2026-07-28**

Tools: 8
Security Considerations

**OWASP MCP Top 10 2025 Beta**

MCP05: Command Injection and Execution

**OWASP MCP Security Cheat Sheet**

5. Input and Output Validation

## POL-25 데이터별 접근권한 확인

출처: `(본)정책 최종본!A29` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-25

**정책명**

데이터별 접근권한 확인

**정책 내용**

게이트웨이는 자산과 보안등급을 확인하고 사용자, 위임 및 기능의 접근 범위를 모두
검사하여야 한다. 자산이나 등급이 불명확하거나 권한을 벗어나면 차단하고, 입력과 응답은
업무에 필요한 범위로 제한하여야 한다.

**CIA 영향**

기밀성

**MCP Specification 2026-07-28**

Resources: 8
Security Considerations

**OWASP MCP Top 10 2025 Beta**

MCP07: Insufficient Authentication and Authorization

**ISMS-P 인증기준 2023.11 안내서**

2.6.3 응용프로그램 접근

## POL-26 외부 전송 대상과 데이터 확인

출처: `(본)정책 최종본!A30` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-26

**정책명**

외부 전송 대상과 데이터 확인

**정책 내용**

내부 자료의 외부 전송은 수신처, 목적, 데이터 범위와 등급이 승인 및 필요한 동의와 일치할 때만 허용하고, 변경 시 재검증하여야 한다.

**CIA 영향**

기밀성

**MCP Specification 2026-07-28**

Specification: 3.1.2
Key Principles/Data Privacy

**OWASP MCP Top 10 2025 Beta**

MCP10: Context Injection and Over-Sharing

**개인정보 보호법 2026-09-11 시행**

제17조제1항

## POL-27 민감한 작업의 개별 승인

출처: `(본)정책 최종본!A31` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-27

**정책명**

민감한 작업의 개별 승인

**정책 내용**

호스트는 고위험 요청의 대상과 내용을 제시하고 게이트웨이는 개별 승인 시에만 실행을
허용하여야 한다. 변경 시 재승인을 받고 미승인 요청은 보류하여야 한다. 고영향 AI 제품이나
서비스 제공 사업자는 법에 따른 사람의 관리와 감독 의무를 이행하여야 한다.

**CIA 영향**

무결성

**MCP Specification 2026-07-28**

Tools: 8
Security Considerations

**OWASP MCP Top 10 2025 Beta**

MCP02: Privilege Escalation via Scope Creep

**OWASP MCP Security Cheat Sheet**

4. Human-in-the-Loop for Sensitive Actions

**NIST AI RMF 1.0**

MAP 3.5

**인공지능기본법 2026-07-21 시행**

제34조제1항제4호

## POL-28 호출량과 실행 시간 제한

출처: `(본)정책 최종본!A32` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-28

**정책명**

호출량과 실행 시간 제한

**정책 내용**

서버와 게이트웨이는 용량에 따른 호출 및 동시 실행 한도를 적용하고 초과하거나 사용량이
불명확하면 제한하여야 한다. 클라이언트는 승인된 시간 한도를 적용하고 초과 시 실행이나
응답 대기를 종료하여야 한다. 대기 종료를 서버 작업의 중단으로 간주해서는 안 된다.

**CIA 영향**

가용성

**MCP Specification 2026-07-28**

Tools: 8
Security Considerations

**OWASP MCP Security Cheat Sheet**

6. Authentication, Authorization & Transport Security

**ISMS-P 인증기준 2023.11 안내서**

2.9.2 성능 및 장애관리

## POL-29 외부 콘텐츠를 이용한 권한 변경 차단

출처: `(본)정책 최종본!A33` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-29

**정책명**

외부 콘텐츠를 이용한 권한 변경 차단

**정책 내용**

호스트와 게이트웨이는 외부 문서, 도구 응답과 기능 설명을 승인이나 위임의 근거로
인정해서는 안 된다. 새 호출도 승인 등록부와 유효한 위임에 따라 권한을 검사하여야 한다.

**CIA 영향**

무결성

**MCP Specification 2026-07-28**

Specification: 3.1.3
Key Principles/Tool Safety

**OWASP MCP Top 10 2025 Beta**

MCP06: Intent Flow Subversion

**OWASP MCP Security Cheat Sheet**

12. Prompt Injection via Tool Return Values

## POL-30 응답의 민감정보 노출 제한

출처: `(본)정책 최종본!A34` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-30

**정책명**

응답의 민감정보 노출 제한

**정책 내용**

서버는 출력을 정제하고 클라이언트는 전달 전 목적과 접근권한을 별도로 검사하여야 한다.
불필요한 민감정보는 제거하거나 마스킹하고 금지 정보의 제거가 불명확하면 전달을
차단하여야 한다. 응답 내 개인정보의 제공과 국외 이전에는 PAC26을 적용하여야 한다.

**CIA 영향**

기밀성

**MCP Specification 2026-07-28**

Tools: 8
Security Considerations

**OWASP MCP Top 10 2025 Beta**

MCP10: Context Injection and Over-Sharing

**OWASP MCP Security Cheat Sheet**

5. Input and Output Validation

**ISMS-P 인증기준 2023.11 안내서**

2.6.3 응용프로그램 접근 (pp.105-106)

**개인정보 보호법 2026-09-11 시행**

제3조제2항

## POL-31 Tool 사용 시  민감정보 제한

출처: `(본)정책 최종본!A35` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-31

**정책명**

Tool 사용 시  민감정보 제한

**정책 내용**

Tool 사용 시 사용 권한과 필요성을 확인하고 승인 업무의 최소 정보만 전달하여야 한다. 불필요한 민감정보는 제거하거나 마스킹하고 인증정보는 별도로 전달하여야
한다.

**CIA 영향**

기밀성

**OWASP MCP Top 10 2025 Beta**

MCP10: Context Injection and Over-Sharing

**개인정보 보호법 2026-09-11 시행**

제16조제1항

## POL-32 중요 Tool 응답의 출처와 내용 검증

출처: `(본)정책 최종본!A36` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-32

**정책명**

중요 Tool 응답의 출처와 내용 검증

**정책 내용**

중요 문서의 작성 또는 수정에 사용하는 Tool 응답은 출처의 확인이 가능하여야 한다. 원본 자료와 내용이 일치하지 않거나 출처를 확인할 수 없는 응답을 문서 작성에 사용해서는 안 된다.

**CIA 영향**

무결성

**MCP Specification 2026-07-28**

Tools: 8
Security Considerations

**OWASP MCP Top 10 2025 Beta**

MCP03: Tool Poisoning

**OWASP MCP Security Cheat Sheet**

5. Input and Output Validation

**ISO 42001:2023**

A.6.2.4 AI system verification and validation

## POL-33 서버 간 데이터 전달 경계 적용

출처: `(본)정책 최종본!A37` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-33

**정책명**

서버 간 데이터 전달 경계 적용

**정책 내용**

MCP 서버 간 문서 및 인증정보의 전달은 사전에 승인된 업무 목적, 수신 서버 및 데이터 범위에 한하여 허용하여야 한다. 승인 범위를 벗어나는 서버 간 전달을 허용해서는 안 된다.

**CIA 영향**

기밀성

**MCP Specification 2026-07-28**

Specification: 3.1.2
Key Principles/Data Privacy

**OWASP MCP Top 10 2025 Beta**

MCP10: Context Injection and Over-Sharing

**OWASP MCP Security Cheat Sheet**

8. Multi-Server Isolation and Cross-Origin Protection

## POL-34 업무별 Agent 컨텍스트 분리

출처: `(본)정책 최종본!A38` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-34

**정책명**

업무별 Agent 컨텍스트 분리

**정책 내용**

업무별 문서, 검색 결과 및 MCP 도구 실행 결과는 분리하여야 한다. 이전 업무의 정보가 다른 업무에 자동으로 사용되어서는 안 된다.

**CIA 영향**

기밀성

**MCP Specification 2026-07-28**

Specification: 3.1.2
Key Principles/Data Privacy

**OWASP MCP Top 10 2025 Beta**

MCP10: Context Injection and Over-Sharing

## POL-35 단일 조회의 문서 반환 범위 제한

출처: `(본)정책 최종본!A39` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-35

**정책명**

단일 조회의 문서 반환 범위 제한

**정책 내용**

문서 조회 MCP 도구는 한 번의 요청에서 해당 업무에 필요한 범위의 문서만 반환하여야 한다. 승인되지 않은 대량 조회와 전체 폴더 조회는 허용해서는 안 된다.

**CIA 영향**

기밀성

**MCP Specification 2026-07-28**

Tools: 8
Security Considerations

**OWASP MCP Top 10 2025 Beta**

MCP10: Context Injection and Over-Sharing

**OWASP MCP Security Cheat Sheet**

1. Principle of Least Privilege

## POL-36 변경 작업의 중복 실행 방지

출처: `(본)정책 최종본!A40` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-36

**정책명**

변경 작업의 중복 실행 방지

**정책 내용**

문서 수정 및 삭제 요청이 재전송되거나 재시도되더라도 동일한 작업이 중복 실행되어서는 안 된다.

**CIA 영향**

무결성

**OWASP MCP Security Cheat Sheet**

Key Risks: Message Tampering and Replay

## POL-37 구성 변경 검토와 재승인

출처: `(본)정책 최종본!A41` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-37

**영역**

운영 및 변경

**정책명**

구성 변경 검토와 재승인

**정책 내용**

운영 담당자는 승인이 완료된 도구를 보관하고 MCP 서버의 변경이 있다면 이를
대조하여 보안에 영향이 있을 시 사용을 차단한다.

**CIA 영향**

무결성

**OWASP MCP Top 10 2025 Beta**

MCP03: Tool Poisoning

**OWASP MCP Security Cheat Sheet**

2. Tool Description & Schema Integrity

**ISO 42001:2023**

B.6.2.6 AI system operation and monitoring (pp.33-34)

**ISMS-P 인증기준 2023.11 안내서**

2.9.1 변경관리 (p.134)

**NIST AI RMF 1.0**

MANAGE 4.1

## POL-38 호출과 권한 변경 이력 관리

출처: `(본)정책 최종본!A42` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-38

**정책명**

호출과 권한 변경 이력 관리

**정책 내용**

호출, 권한 변경, 폐기 및 인증정보 회수 이력을 기록하되 비밀정보는 제외하고 개인정보는
최소화 및 마스킹하여야 한다. 기록의 법정 보존, 접근통제와 변조 방지를 준수하고 권한과
이상징후를 정기 점검하여 보고하고 조치하여야 한다.

**CIA 영향**

무결성

**MCP Specification 2026-07-28**

Tools: 8
Security Considerations

**MCP Security Best Practices 2026-07-28**

Scope Minimization/ Mitigation/ Server guidance

**OWASP MCP Top 10 2025 Beta**

MCP08: Lack of Audit and Telemetry

**OWASP MCP Security Cheat Sheet**

10. Monitoring, Logging & Auditing

**ISO 42001:2023**

B.6.2.8 AI system recording of event logs (p.36)

**ISMS-P 인증기준 2023.11 안내서**

2.9.4 로그 및 접속기록 관리 (pp.140-142)

**개인정보 보호법 2026-09-11 시행**

제29조

## POL-39 알려진 취약점의 수정 및 격리

출처: `(본)정책 최종본!A43` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-39

**정책명**

알려진 취약점의 수정 및 격리

**정책 내용**

운영 중인 MCP 서버에서 알려진 취약점은 영향도를 평가하고 정해진 기한 내에 조치하여야 한다. 기한 내 조치가 불가능한 경우 해당 기능을 격리하거나 사용을 중지하여야 한다.

**CIA 영향**

무결성

**MCP Security Best Practices 2026-07-28**

Local MCP Server Compromise

**OWASP MCP Top 10 2025 Beta**

MCP04: Software Supply Chain Attacks

**OWASP MCP Security Cheat Sheet**

9. Supply Chain Security

**ISO 42001:2023**

A.6.2.6 AI system operation and monitoring

**ISMS-P 인증기준 2023.11 안내서**

2.9.1 변경관리

## POL-40 연결 목적지 변경의 재승인

출처: `(본)정책 최종본!A44` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-40

**정책명**

연결 목적지 변경의 재승인

**정책 내용**

MCP 서버의 승인된 연결 주소나 전송 대상이 변경되는 경우 재승인을 받아야 한다.

**CIA 영향**

기밀성

**OWASP MCP Top 10 2025 Beta**

MCP09: Shadow MCP Servers

**ISMS-P 인증기준 2023.11 안내서**

2.9.1 변경관리

## POL-41 인증정보 교체 후 이전 값 무효화

출처: `(본)정책 최종본!A45` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-41

**정책명**

인증정보 교체 후 이전 값 무효화

**정책 내용**

토큰 또는 API 키를 교체한 경우 이전 인증정보는 모든 사용처에서 제거하고, 이전 인증정보를 이용한 접근은 차단한다.

**CIA 영향**

기밀성

**MCP Security Best Practices 2026-07-28**

Token Passthrough: Mitigation

**OWASP MCP Top 10 2025 Beta**

MCP01: Token Mismanagement and Secret Exposure

## POL-42 이상 징후 경보의 동작 확인

출처: `(본)정책 최종본!A46` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-42

**정책명**

이상 징후 경보의 동작 확인

**정책 내용**

새로운 MCP 도구의 사용, 미승인 연결 시도 및 비정상적인 호출 증가에 대한 경보는 설정 변경 후에도 정상적으로 작동하여야 한다.

**CIA 영향**

무결성

**OWASP MCP Top 10 2025 Beta**

MCP08: Lack of Audit and Telemetry

**OWASP MCP Security Cheat Sheet**

10. Monitoring, Logging and Auditing

**NIST AI RMF 1.0**

MEASURE 1.2

## POL-43 탐지된 위험의 대응

출처: `(본)정책 최종본!A47` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-43

**정책명**

탐지된 위험의 대응

**정책 내용**

미승인 변경이나 비정상적인 호출이 탐지된 경우 관련 MCP 도구와 연결을 중지하고 영향 범위를 조사하여야 한다.

**CIA 영향**

무결성

**ISMS-P 인증기준 2023.11 안내서**

2.11.1 사고 예방 및 대응체계 구축

**NIST AI RMF 1.0**

MANAGE 4.3

## POL-44 권한 철회와 연결 해제

출처: `(본)정책 최종본!A48` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-44

**영역**

연결 해제 및 폐기

**정책명**

권한 철회와 연결 해제

**정책 내용**

게이트웨이는 주체, 서버, 기능 및 승인의 중지나 철회를 즉시 반영하고 후속 호출을
거부하여야 한다. 폐기 시 등록, 설정과 연결 경로를 제거하고 PAC45에 따라 인증정보를
회수하여 재호출 차단을 확인하여야 한다.

**CIA 영향**

기밀성

**OWASP MCP Top 10 2025 Beta**

MCP07: Insufficient Authentication and Authorization

**OWASP MCP Security Cheat Sheet**

6. Authentication, Authorization & Transport Security

**ISMS-P 인증기준 2023.11 안내서**

2.5.1 사용자 계정 관리 (p.87)

**NIST AI RMF 1.0**

GOVERN 1.7

## POL-45 토큰과 API 키 회수

출처: `(본)정책 최종본!A49` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-45

**정책명**

토큰과 API 키 회수

**정책 내용**

운영 담당자는 폐기 시 토큰, API 키와 갱신 수단을 회수하거나 무효화한 후 제거하여야 한다.
공유 인증정보는 영향 확인 후 교체하고 즉시 회수가 어려우면 접근을 차단하여야 한다. 설정
삭제만으로 회수를 갈음해서는 안 되며 기존 인증정보의 재접근 차단을 시험하여야 한다.

**CIA 영향**

기밀성

**OWASP MCP Top 10 2025 Beta**

MCP07: Insufficient Authentication and Authorization

**ISMS-P 인증기준 2023.11 안내서**

2.5.1 사용자 계정 관리 (p.87)

**NIST AI RMF 1.0**

GOVERN 1.7

## POL-46 잔존 서버 프로세스 종료

출처: `(본)정책 최종본!A50` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-46

**정책명**

잔존 서버 프로세스 종료

**정책 내용**

연결이 해제된 로컬 MCP 서버의 실행 프로세스는 종료되어야 한다.

**CIA 영향**

무결성

**NIST AI RMF 1.0**

GOVERN 1.7

## POL-47 문서 저장소 권한 회수

출처: `(본)정책 최종본!A51` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-47

**정책명**

문서 저장소 권한 회수

**정책 내용**

MCP 연결을 폐기할 때 문서 저장소에 부여한 서비스 계정 권한과 공유 설정은 회수하여야 한다.

**CIA 영향**

기밀성

**OWASP MCP Top 10 2025 Beta**

MCP07: Insufficient Authentication and Authorization

**OWASP MCP Security Cheat Sheet**

1. Principle of Least Privilege

**NIST AI RMF 1.0**

GOVERN 1.7

## POL-48 임시 파일과 캐시 데이터 정리

출처: `(본)정책 최종본!A52` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-48

**정책명**

임시 파일과 캐시 데이터 정리

**정책 내용**

MCP 도구의 처리 과정에서 생성된 문서 사본, 임시 파일 및 캐시 데이터 중 보존 의무가 없는 자료는 연결 해제 시 삭제하여야 한다.

**CIA 영향**

기밀성

**개인정보 보호법 2026-09-11 시행**

제21조(개인정보의 파기) 제1항

## POL-49 외부 제공자의 보유 문서 정리

출처: `(본)정책 최종본!A53` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-49

**정책명**

외부 제공자의 보유 문서 정리

**정책 내용**

외부 MCP 서버와의 연결 종료 시 운영업체가 보유한 전달 문서와 처리 결과는 계약 및 보존 기준에 따라 반환하거나 삭제하여야 한다. 조직은 운영업체의 반환 또는 삭제 완료 여부를 확인하여야 한다.

**CIA 영향**

기밀성

**NIST AI RMF 1.0**

GOVERN 1.7

**개인정보 보호법 2026-09-11 시행**

제21조(개인정보의 파기) 제1항

## POL-50 복원 시 폐기된 연결의
재활성화 차단

출처: `(본)정책 최종본!A54` · [원본](originals/MCP_보안정책-추가25.xlsm)

**정책 ID**

POL-50

**정책명**

복원 시 폐기된 연결의
재활성화 차단

**정책 내용**

백업이나 스냅샷의 복원 후에도 폐기된 MCP 서버와 Tool의 연결 및 호출을 허용해서는 안 된다. 폐기된 인증정보의 재사용을 허용해서는 안 된다.

**CIA 영향**

기밀성

**OWASP MCP Top 10 2025 Beta**

MCP07: Insufficient Authentication and Authorization

**NIST AI RMF 1.0**

GOVERN 1.7
