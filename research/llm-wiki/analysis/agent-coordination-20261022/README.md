# LangGraph 기반 CLI 협업 운영

## 선택과 고정 판본

- 목적: 기존 `100.111.15.33:1000` 화면과 CLI 구독 인증을 유지하면서 구현·독립 검토·판단 단계를 중단 후 복구한다.
- 적용: `langgraph==1.2.16`, `langgraph-checkpoint-sqlite==3.1.2`, 두 패키지 메타데이터의 라이선스는 MIT. 설치 wheel URL·SHA-256은 [dependencies.json](dependencies.json), 전이 의존성은 [잠금 파일](../../../collaboration-console/requirements.lock.txt)에 고정했다.
- 공개 OSS 조사: [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph), 조회 시 HEAD `3cd57c038ad827d05f80c6488adea9994156c58c`. 이 HEAD를 적용 wheel의 소스 커밋으로 간주하지 않는다.
- 근거: [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api). 체크포인트·중단·재개와 명시적 단계 전환을 적용했다. LangChain 모델 래퍼나 별도 Agent Server는 사용하지 않는다.
- Windows: [OpenAI Docs의 Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox), [설정](https://learn.chatgpt.com/docs/config-file/config-basic). 설치된 CLI의 도움말·로컬 샌드박스 시험·실제 세션 메타데이터를 함께 확인했다. 레거시 `-s`만 적용한 초기 세션은 read-only였고, 명시적인 workspace 프로필을 전달한 세션은 workspace-write였다. 관리자·full-access·규칙 무시로 바꾸지 않았다.

## 적용 범위

- [coordination.py](../../../collaboration-console/coordination.py): 구현 → Gemini 검토 → 수정 한 번 → 재검토 → 필요한 Claude 판단. `SqliteSaver`, `interrupt`, `Command(resume=...)`, 그래프 단계 상한을 사용한다. 모델 실행 대신 기존 큐에 안정적인 작업 ID를 등록하므로 체크포인트 재실행으로 쓰기를 중복하지 않는다.
- [worker.py](../../../collaboration-console/worker.py): 제공자 한도·실제 CLI·세션·프로세스 신원·중복·호출/입출력 상한. 관리 중인 에이전트의 재위임은 거절한다. 준비 실패·정책 거절·불명 쓰기를 완료로 세지 않는다.
- [운영 규칙](../../../collaboration-console/COORDINATION.md): 같은 task_id, 짧은 인계와 근거 파일, 고정 판본 해시, 단일 구현자·독립 검토자. 정상 호출은 즉시 이어가며 같은 제공자만 최소 5초, 전체 시간당 60회·제공자별 30회가 최후 상한이다.
- 기존 `Local-Agent-Hub`와 `MINT-CollaborationConsole` 예약 작업만 갱신했다. 별도 웹 포트·DB 서버·컨테이너·LangSmith 서비스를 추가하지 않았다. 체크포인트는 로컬 SQLite이고 추적 업로드는 비활성화했다.

## 확인된 실제 경로와 한계

`OPS-INTAKE-PACKAGING-R3`에서 Codex가 Dockerfile의 `supplier_metadata.py` 복사 누락을 수정하고 회귀 시험을 추가했다. Gemini가 고정 diff·시험 로그·소스를 독립 검토해 PASS를 반환했다. 통합 담당자가 패키징 회귀를 다시 실행해 통과를 확인했다. 로컬 레인 commit은 `6a33afe`이며 제품 기기 배포는 수행하지 않았다.

그 뒤 콘솔 렌더링 효율과 인증서 유지보수 작업을 순서대로 등록했다. 보안 유지보수의 Claude 판단은 사용자 설명에 따른 주간 한도 해제 후 2026-10-22 19:05 KST부터 시도한다. 이번 시각에 실제 Claude 추론은 미실행이다.

로컬 기록만으로 사업자 전체 구독 잔량을 알 수 없다. CLI가 보고한 사용량·한도 오류를 관측하며 다른 앱의 소비는 합산하지 못한다. 짧은 메모리 표본과 재시작 복구 시험은 장시간 누수 부재를 증명하지 않는다. 그래프 PASS는 병합·배포·실기기 성공을 대신하지 않는다.

추가 단계·할당 정적 검토: Gemini 인라인 검토의 초기 지적을 [설치 API 대조](audit-adjudication.json)로 판정하고 실제 결과 본문 인계를 보강했다. 보강 후 PASS. 프로세스 I/O는 이 추가 검토 범위 밖이며 별도 회귀로 확인했다. 콘솔 최적화도 제품 레인 `73dfad7`에 로컬 커밋했으나 현재 1000번 UI에 반영한 것은 아니다.
