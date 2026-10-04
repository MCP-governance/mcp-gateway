# 관리형 엔드포인트 계정이 모델 API에 닿는 유일한 경로. 엔드포인트의 바깥 통신은 게이트웨이 호스트로만
# 열려 있으므로, 하네스는 이 프록시를 거쳐 model-domains.txt의 도메인에만 닿는다.
# Squid 6.12는 연결 도중 끊긴 터널에서 단언 실패로 죽어(D-67) 단순한 tinyproxy를 쓴다.
FROM alpine:3.22
RUN apk add --no-cache tinyproxy
COPY tinyproxy.conf /etc/tinyproxy/tinyproxy.conf
COPY model-domains.txt /etc/tinyproxy/model-domains.txt
USER nobody
EXPOSE 3128
CMD ["tinyproxy", "-d", "-c", "/etc/tinyproxy/tinyproxy.conf"]
