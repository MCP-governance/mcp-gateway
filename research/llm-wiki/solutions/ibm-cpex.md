# IBM CPEX — 원자 호출량 처리와 플러그인 경계

확인일: 2026-10-13 · 확인 수준: 고정 커밋 Rust 코드 검토 · 라이선스: Apache-2.0.

[검토 커밋](https://github.com/IBM/cpex-plugins/tree/ae26938128cb438a268e7f3217603bc39b9dd18f): `ae26938128cb438a268e7f3217603bc39b9dd18f`.

## 코드로 확인한 사실

호출량 플러그인의 [redis_backend.rs:28–110](https://github.com/IBM/cpex-plugins/blob/ae26938128cb438a268e7f3217603bc39b9dd18f/plugins/rust/python-package/rate_limiter/src/redis_backend.rs#L28-L110)은 fixed window, sliding window, token bucket 연산을 Redis Lua 배치로 정의한다. 단순히 카운터를 읽고 나중에 증가시키는 분리 연산과 비교하는 데 사용할 수 있다. 이 스크립트의 존재가 실제 배포의 Redis 사용이나 클러스터 구성의 성공을 증명하지는 않는다.

[framework_bridge/src/lib.rs:7–23](https://github.com/IBM/cpex-plugins/blob/ae26938128cb438a268e7f3217603bc39b9dd18f/crates/framework_bridge/src/lib.rs#L7-L23)은 `cpex.framework`를 Python 모듈로 import한다. 공개 탐지기·카운터 로직과 외부 실행 프레임워크의 배선·예외 처리를 구분해야 한다. 공개 Rust 소스를 못 찾았다는 과거 결론으로 CPEX 전체를 비공개라고 부르지 않는다.

## 채택 판단

우리 PostgreSQL 예약 방식은 `core.py`의 실행 예약, 중복, 동시성, 불확실한 결과를 함께 다룬다. Redis 카운터를 그대로 이식하기보다 같은 주체가 동시에 보낸 두 호출에서 상한과 부수효과를 확인하는 비교 실험에 쓴다. 적용 저장소·TTL·장애 시 기본 결정이 다른데 동일한 보장이라고 표현하지 않는다.

후보는 단일 연산 안에 계수·기한을 처리하는 패턴과 다차원 상한이다. 별도 Rust 실행 엔진을 개발 솔루션에 추가하는 것은 현재 범위가 아니다. 탐지 규칙이나 코드 이식 시 Apache-2.0 저작권·라이선스·관련 NOTICE와 변경 표시를 유지한다.

## 확보 증거와 한계

[Redis 배치 발췌](evidence/ibm-cpex/plugins__rust__python-package__rate_limiter__src__redis_backend.rs.excerpt.txt), [framework bridge 발췌](evidence/ibm-cpex/crates__framework_bridge__src__lib.rs.excerpt.txt), [라이선스](evidence/ibm-cpex/LICENSE.txt), [해시 목록](evidence/manifest.json). 검토 커밋 루트에 NOTICE 파일은 없다.

실행 엔진 패키지의 소스·통합 오류 처리, 실제 다중 프로세스 부하, Redis 장애·클러스터 hash slot은 시험하지 않았다. 원자성에 관한 결론은 확인한 Lua 연산 범위에 한정한다.
