-- #327 hypothesis tests (2026-09-27) — the ONE read-only capture this probe makes: mi_alert_rank_shadow (latest
-- computed_at per campaign) + mi_ep_alerts catalyst_type / judge_* for the SAME 277 campaigns as gate.sql. H5 only.
WITH a AS (
  SELECT DISTINCT ON (ticker, alert_date) id, ticker, alert_date, catalyst_type, judge_tier, judge_grade, created_at
  FROM mi_ep_alerts
  WHERE alert_date BETWEEN DATE '2026-05-01' AND DATE '2026-09-11' AND COALESCE(source,'live')='live'
  ORDER BY ticker, alert_date, created_at
), r AS (
  SELECT DISTINCT ON (ticker, alert_date) * FROM mi_alert_rank_shadow ORDER BY ticker, alert_date, computed_at DESC
)
SELECT a.ticker, a.alert_date, a.catalyst_type, a.judge_tier, a.judge_grade, r.score_tier AS rs_score_tier,
       r.ext_xadr_eod, r.ext_xadr_pregap, r.tightness_pct_eod, r.composite_rank_eod, r.pool_size_eod,
       r.expct_scheduled, r.expct_looking, r.expct_beat, r.expct_combined_class, r.open_range_position,
       r.orb_range_over_adr20, r.adr20_frac, r.gap_pct_eod, r.day_open, r.day_high, r.day_low, r.day_close,
       r.base_days_adr6, r.base_depth_adr6, r.base_net_disp_xadr, r.computed_at
FROM a LEFT JOIN r ON r.ticker = a.ticker AND r.alert_date = a.alert_date
ORDER BY a.ticker, a.alert_date;
