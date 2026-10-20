#!/usr/bin/env bash
# 솔루션 기기에서 실행: 제품 siem_outbox 와 SIEM(OpenSearch) 문서를 (source:source_id) 쌍으로 대조한다.
#   ./verify.sh            → 대기·전달·SIEM 문서 수, 양방향 차집합, _id==metadata.uid 중복 없음 확인
# 읽기 전용이다. 제품 DB는 SELECT만, OpenSearch는 검색만 한다.
set -euo pipefail
cd "$(dirname "$0")"
DB="${PRODUCT_DB_CONTAINER:-$(docker ps --format '{{.Names}}' | grep -E -- '-db-1$' | grep -v mint | head -1)}"
OS=mint-siem-opensearch-1
password="$(cat secrets/vector/opensearch_password)"
q() { docker exec "$DB" psql -U mcp -d mcp_governance -At -c "$1" </dev/null; }
os() { docker exec "$OS" curl -sk -u "admin:$password" "$@"; }
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
q "SELECT source||':'||source_id FROM siem_outbox" | sort > "$tmp/db_all"
q "SELECT source||':'||source_id FROM siem_outbox WHERE delivered_at IS NOT NULL" | sort > "$tmp/db_delivered"
os "https://localhost:9200/mint-ocsf-*/_search?size=10000&_source=unmapped.source,unmapped.source_id,metadata.uid" > "$tmp/os.json"
python3 - "$tmp" <<'PY'
import json, sys
d = json.load(open(sys.argv[1] + "/os.json"))
hits = d["hits"]["hits"]
open(sys.argv[1] + "/os_pairs", "w").write("".join(f"{h['_source']['unmapped']['source']}:{h['_source']['unmapped']['source_id']}\n" for h in hits))
print("os_docs", d["hits"]["total"]["value"], "distinct_id", len({h["_id"] for h in hits}),
      "id==metadata.uid", all(h["_id"] == h["_source"]["metadata"]["uid"] for h in hits))
PY
sort "$tmp/os_pairs" > "$tmp/os_sorted"
echo "outbox_rows=$(wc -l < "$tmp/db_all") delivered=$(wc -l < "$tmp/db_delivered") os_pairs=$(wc -l < "$tmp/os_sorted") distinct_pairs=$(sort -u "$tmp/os_sorted" | wc -l)"
echo "delivered_not_in_os=$(comm -23 "$tmp/db_delivered" "$tmp/os_sorted" | wc -l) in_os_not_in_outbox=$(comm -13 "$tmp/db_all" "$tmp/os_sorted" | wc -l)"
q "SELECT source, count(*) total, count(delivered_at) delivered, count(*)-count(delivered_at) pending, max(attempts) max_attempts FROM siem_outbox GROUP BY source ORDER BY source"
