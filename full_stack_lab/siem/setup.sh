#!/usr/bin/env bash
# SIEM(OpenSearch + Dashboards + Vector) 기동. 이 폴더에서 실행하고, 제품 스택은 건드리지 않는다.
#   SIEM_BIND=<Tailscale IPv4> ./setup.sh [제품 siem-secrets 디렉터리]
# 첫 실행: 난수 토큰·관리자 비밀번호·사설 CA와 서버 인증서를 만든다(값은 출력하지 않는다).
# 제품 쪽에는 ca.pem과 token만 넘긴다. 이미 있는 비밀은 덮어쓰지 않는다.
set -euo pipefail
cd "$(dirname "$0")"
: "${SIEM_BIND:?Tailscale IPv4를 지정하세요}"
PRODUCT_SECRETS="${1:-}"
umask 077
mkdir -p secrets/pki secrets/vector
# Vector의 SECRET[] 치환은 파일 내용을 그대로 넣는다. 끝 개행이 있으면 설정 줄이 깨지므로 개행 없이 쓴다.
[[ -s secrets/vector/siem_token ]] || printf '%s' "$(openssl rand -hex 32)" > secrets/vector/siem_token
if [[ ! -s secrets/vector/opensearch_password ]]; then
  # OpenSearch 초기 관리자 비밀번호 규칙: 대소문자·숫자·기호 포함 8자 이상.
  printf 'Ms-%s-9aZ!' "$(openssl rand -hex 16)" > secrets/vector/opensearch_password
fi
for f in secrets/vector/siem_token secrets/vector/opensearch_password; do printf '%s' "$(cat "$f")" > "$f"; done
password="$(cat secrets/vector/opensearch_password)"
printf 'OPENSEARCH_INITIAL_ADMIN_PASSWORD=%s\n' "$password" > secrets/opensearch.env
cat > secrets/opensearch_dashboards.yml <<YML
server.host: 0.0.0.0
opensearch.hosts: ["https://opensearch:9200"]
opensearch.ssl.verificationMode: none
opensearch.username: admin
opensearch.password: "$password"
YML
if [[ ! -s secrets/pki/ca.pem ]]; then
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 825 -subj "/CN=MINT SIEM CA" \
    -keyout secrets/pki/ca.key -out secrets/pki/ca.pem
  openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -subj "/CN=siem-ingest" \
    -keyout secrets/pki/ingest.key -out secrets/pki/ingest.csr
  printf 'subjectAltName=IP:%s,DNS:ingest,DNS:siem-ingest\nextendedKeyUsage=serverAuth\n' "$SIEM_BIND" > secrets/pki/san.ext
  openssl x509 -req -in secrets/pki/ingest.csr -CA secrets/pki/ca.pem -CAkey secrets/pki/ca.key -CAcreateserial \
    -days 397 -extfile secrets/pki/san.ext -out secrets/pki/ingest.crt
fi
# Vector는 root로 읽고, Dashboards(uid 1000)는 이 사용자가 소유한 설정 파일을 읽는다.
chmod 644 secrets/pki/ca.pem
export SIEM_BIND
for image in opensearch:opensearchproject/opensearch:3.8.0 dashboards:opensearchproject/opensearch-dashboards:3.8.0 vector:timberio/vector:0.59.0-alpine; do
  var="$(echo "${image%%:*}" | tr a-z A-Z)_DIGEST"
  ref="${image#*:}"
  digest="$(docker image inspect "$ref" --format '{{index .RepoDigests 0}}' 2>/dev/null | sed 's/.*@//')"
  [[ -n "$digest" ]] || { docker pull -q "$ref" >/dev/null; digest="$(docker image inspect "$ref" --format '{{index .RepoDigests 0}}' | sed 's/.*@//')"; }
  export "$var=$digest"
done
docker compose up -d
echo "OpenSearch 기동 대기"
for _ in $(seq 1 60); do
  [[ "$(docker inspect -f '{{.State.Health.Status}}' mint-siem-opensearch-1 2>/dev/null)" == healthy ]] && break
  sleep 5
done
# time은 OCSF 밀리초 epoch다. 없으면 날짜 필드가 아니라 숫자로 색인돼 검색 화면이 시간 축을 못 쓴다.
docker exec mint-siem-opensearch-1 curl -sk -u "admin:$password" -X PUT https://localhost:9200/_index_template/mint-ocsf -H 'content-type: application/json' -d '{
  "index_patterns": ["mint-ocsf-*"],
  "template": {"settings": {"number_of_replicas": 0}, "mappings": {"properties": {
    "time": {"type": "date", "format": "epoch_millis"},
    "metadata": {"properties": {"uid": {"type": "keyword"}}},
    "unmapped": {"properties": {
      "source": {"type": "keyword"}, "decision": {"type": "keyword"}, "policy_id": {"type": "keyword"},
      "kind": {"type": "keyword"}, "outcome": {"type": "keyword"}, "target_kind": {"type": "keyword"}}}}}}}' >/dev/null
# Dashboards 검색 화면용 인덱스 패턴(시간 필드 time). 이미 있으면 409라 무시한다.
for _ in $(seq 1 30); do
  curl -s -m 5 -o /dev/null -u "admin:$password" "http://${SIEM_BIND}:5601/api/status" && break
  sleep 3
done
curl -s -m 20 -o /dev/null -u "admin:$password" -X POST "http://${SIEM_BIND}:5601/api/saved_objects/index-pattern/mint-ocsf"   -H 'osd-xsrf: true' -H 'content-type: application/json' -d '{"attributes":{"title":"mint-ocsf-*","timeFieldName":"time"}}' || true
if [[ -n "$PRODUCT_SECRETS" ]]; then
  install -m 644 secrets/pki/ca.pem "$PRODUCT_SECRETS/ca.pem"
  [[ -s "$PRODUCT_SECRETS/token" ]] || install -m 600 secrets/vector/siem_token "$PRODUCT_SECRETS/token"
  echo "제품 siem-secrets에 ca.pem·token 배치 완료"
fi
echo "수신 주소: https://${SIEM_BIND}:8688/ingest   화면: http://${SIEM_BIND}:5601"
