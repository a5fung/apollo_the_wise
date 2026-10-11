-- #210 review fix 2026-10-10, pull 3 — SELECT only. Captured ONCE to q3_lattice.out; never re-run to re-read.
-- Correction 5: which lattice rule produced the ACTING grade on the 10 shadow ticker-days
-- (raw routine -> acting strong on 7 of 10 per q2_anchor.out A1). The verifier named
-- routine_promoted_demotion_corrective on CIFR, MSTR, ITUB, NU, PBR, AAOI; this sources it.
\echo '### L1 lattice verdict per shadow ticker-day'
SELECT s.ticker, s.alert_date, s.catalyst_quality AS shadow_raw, a.catalyst_quality AS alert_acting,
       t.live_quality_first, t.live_quality_last, t.shadow_tier_first, t.shadow_tier_last,
       t.rule_first, t.rule_last, t.live_side, t.regrade_count,
       t.first_seen_et AT TIME ZONE 'America/New_York' AS first_seen_et
FROM mi_tv_news_shadow s
JOIN mi_ep_alerts a ON a.ticker = s.ticker AND a.alert_date = s.alert_date
LEFT JOIN mi_catalyst_tier_shadow t ON t.ticker = s.ticker AND t.scan_date = s.alert_date
ORDER BY s.alert_date, s.ticker;
