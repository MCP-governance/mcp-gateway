\set ON_ERROR_STOP on
SET default_transaction_read_only = on;
WITH scoped AS (
  SELECT d.* FROM decisions d
  WHERE d.created_at >= :'started'::timestamptz AND d.created_at < :'ended'::timestamptz
    AND d.action <> 'connect' AND d.client->>'task_id' = 'load-' || :'scenario'
), policies AS (
  SELECT decision, policy_id, count(*) AS n
  FROM scoped GROUP BY decision, policy_id
), stages AS (
  SELECT e.key AS stage, count(*) AS n,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY e.value::float8) AS p50_ms,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY e.value::float8) AS p95_ms
  FROM scoped d CROSS JOIN LATERAL jsonb_each_text(d.timings) e
  GROUP BY e.key
), own_time AS (
  SELECT decision, upstream_executed, (timings->>'total')::float8 AS total,
    (timings->>'total')::float8 - coalesce((timings->>'connect')::float8,0)
      - coalesce((timings->>'list')::float8,0) - coalesce((timings->>'call')::float8,0)
      - coalesce((timings->>'close')::float8,0) AS gw_self
  FROM scoped WHERE timings ? 'total'
), verdicts AS (
  SELECT decision, upstream_executed, count(*) AS n,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY total) AS total_p50_ms,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY total) AS total_p95_ms,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY gw_self) AS self_p50_ms,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY gw_self) AS self_p95_ms
  FROM own_time GROUP BY decision, upstream_executed
)
SELECT json_build_object('scenario', :'scenario', 'started', :'started', 'ended', :'ended',
  'ledger_rows', (SELECT count(*) FROM scoped),
  'policies', coalesce((SELECT json_agg(policies ORDER BY decision, policy_id) FROM policies), '[]'::json),
  'stages', coalesce((SELECT json_agg(stages ORDER BY stage) FROM stages), '[]'::json),
  'verdicts', coalesce((SELECT json_agg(verdicts ORDER BY decision, upstream_executed) FROM verdicts), '[]'::json));
