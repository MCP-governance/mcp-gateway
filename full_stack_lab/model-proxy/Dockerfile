# 관리형 엔드포인트 계정이 모델 API에 닿는 유일한 경로. 엔드포인트의 바깥 통신은 게이트웨이 호스트로만
# 열려 있으므로, 하네스는 이 프록시에 CONNECT로 모델 도메인만 요청할 수 있다(model-domains.txt).
FROM alpine:3.22
RUN apk add --no-cache squid
COPY squid.conf /etc/squid/squid.conf
COPY model-domains.txt /etc/squid/model-domains.txt
USER squid
EXPOSE 3128
CMD ["squid", "-N", "-d", "1", "-f", "/etc/squid/squid.conf"]
