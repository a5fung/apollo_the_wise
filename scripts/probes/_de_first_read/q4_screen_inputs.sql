SELECT ticker, ep_date, session_idx, gap_pct, prev_close, ep_dollar_volume, extension_pct, catalyst_grade, screen_member, screen_version
FROM mi_delayed_entry_watch
WHERE ep_date >= DATE '2026-08-20' AND session_idx = 0
ORDER BY ep_date, ticker;
