# 엔드포인트 평면 에이전트.
#
# 의존성이 없다. 표준 라이브러리만 쓰는 것이 의도이고, 그래서 slim 이미지에
# 파일 하나만 넣는다. 사용자 PC에서 도는 프로세스의 공급망은 조직이 가장
# 통제하기 어려운 축에 속하므로, 여기에 패키지를 더하는 것은 그 자체로 비용이다.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN useradd --uid 10003 --create-home observer
COPY --chown=observer:observer endpoint_agent.py /app/endpoint_agent.py
USER observer
WORKDIR /app
CMD ["python", "endpoint_agent.py"]
