-- #693 validator-thinking-ON live check. Run after the 17:00 ET nightly pull's validation pass (~17:15 ET):
--   ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F \$'\\t' -v d=2026-10-12" < tonight_check.sql
-- POSITIVE thinking-on signature (live precedent 09-30 / 10-01 / 10-02, adaptive thinking): 27-29% of calls >25 output tokens, mean 59-78, p90 228-324.
-- BROKEN (thinking not engaged) signature (10-05..10-09): <=4 calls >25 tokens, mean 9.6-14, p90 9-16.
\echo == theme_validation calls on :d
SELECT count(*) n, count(*) FILTER (WHERE stop_reason='end_turn') end_turn, count(*) FILTER (WHERE stop_reason='max_tokens') max_tok,
  count(*) FILTER (WHERE output_tokens>25) gt25, count(*) FILTER (WHERE output_tokens>50) gt50, count(*) FILTER (WHERE output_tokens>100) gt100,
  percentile_disc(0.9) WITHIN GROUP (ORDER BY output_tokens) p90, round(avg(output_tokens),1) mean, max(output_tokens) mx, round(sum(cost_usd)::numeric,3) cost
FROM api_usage WHERE caller='theme_validation' AND (created_at AT TIME ZONE 'America/New_York')::date = :'d'::date;
\echo == FULL-PASS GATE (a broken validator keeps every ticker; only a full call count + zero errors discriminate)
SELECT count(*) AS calls,
       CASE WHEN count(*) >= 130 THEN 'FULL_PASS' WHEN count(*) BETWEEN 1 AND 40 THEN 'SMALL_RESCORE_DOES_NOT_COUNT'
            ELSE 'PARTIAL_PASS_INVESTIGATE' END AS pass_kind,
       (SELECT count(*) FROM mi_audit_log WHERE (created_at AT TIME ZONE 'America/New_York')::date = :'d'::date
          AND event_type IN ('validation_error','validation_api_failure','validation_rate_limited','anthropic_rate_limited')) AS error_rows
FROM api_usage WHERE caller='theme_validation' AND (created_at AT TIME ZONE 'America/New_York')::date = :'d'::date;
\echo == removals that ET day (full pass Mon/Wed/Fri: baseline off 26/19/19, on-precedent 13; replay 5; bar <15)
SELECT count(*) removals FROM mi_audit_log WHERE event_type='ticker_revalidated_out' AND (created_at AT TIME ZONE 'America/New_York')::date = :'d'::date;
\echo == alarms that ET day (truncation / near-ceiling / validation errors)
SELECT event_type, count(*) FROM mi_audit_log WHERE (created_at AT TIME ZONE 'America/New_York')::date = :'d'::date
  AND (event_type IN ('llm_truncation_live','llm_refusal','validation_error','validation_api_failure','validation_rate_limited','anthropic_rate_limited')
       OR event_type ILIKE '%near_ceiling%' OR event_type ILIKE '%validation%error%' OR (event_type ILIKE '%validation%' AND summary ILIKE '%parse%'))
GROUP BY 1 ORDER BY 1;
-- ⚠ (Opus verifier 2026-10-13) a validator that ERRORS keeps every ticker, so a broken run ALSO shows <15 removals and no
-- truncation. A PASS needs, together: the call count of a FULL pass (10-07 142, 10-09 141, 10-12 154; Tue's small
-- rescore was 15), ZERO rows of the four error/rate-limit events above, 0 max_tokens, >=20% of calls >25 tokens,
-- mean >=40, removals <15. Removals 15-19 = neither pass nor fail (>=20): do not close; re-read Friday.
