-- #655 scope (2026-10-10), READ-ONLY, run ONCE by capture.sh. Each section is a COPY to stdout
-- prefixed by a marker line so split.py can cut the stream.
BEGIN TRANSACTION READ ONLY;
\echo @@AUDIT_CORRECTNESS
COPY (SELECT json_build_object('id',id,'et',to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS'),
      'summary',summary,'detail',detail) FROM mi_audit_log WHERE event_type='theme_correctness_check' ORDER BY id) TO STDOUT;
\echo @@AUDIT_THEME_EVENTS
COPY (SELECT json_build_object('id',id,'et',to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS'),
      'event_type',event_type,'summary',summary,'detail',detail) FROM mi_audit_log
      WHERE created_at >= '2026-09-14' AND event_type IN (
       'theme_retired','theme_discovered','theme_pass1_5_absorption','theme_pass1_5_skip',
       'theme_sector_cap_not_absorbed','theme_sector_cap_absorbed','theme_sector_cap_dropped','theme_sector_cap_kept_distinct',
       'theme_retired_small_fading','theme_auto_retired','theme_pass1_protect_strip','theme_cap_drop','theme_cap_strip',
       'theme_birth_gate','theme_birth_validated','theme_renamed_for_continuity','theme_renamed_on_mass_flag',
       'theme_thesis_merged','theme_member_rehomed','theme_split','theme_dissolved_flagged_pair','theme_empty_tickers',
       'theme_engine_funnel','theme_operator_promoted','theme_merge_parent_child','theme_composition_churn',
       'theme_ecosystem_assigned','theme_merge_distinct')
      ORDER BY id) TO STDOUT;
\echo @@THEMES
COPY (SELECT json_build_object('id',id,'d',theme_date,'name',name,'stage',stage,'score',score,'rs_avg',rs_avg,
      'tickers',tickers,'parent',parent_theme,'source',source,'days_active',days_active,
      'desc', CASE WHEN theme_date >= '2026-09-21' THEN description END)
      FROM mi_themes WHERE theme_date >= '2026-06-15' ORDER BY theme_date, id) TO STDOUT;
\echo @@ECOSYSTEMS
COPY (SELECT json_build_object('theme',theme_name,'e',e_code,'method',method) FROM mi_theme_ecosystems) TO STDOUT;
\echo @@INDUSTRY
COPY (SELECT json_build_object('t',ticker,'sector',sector,'industry',industry) FROM mi_ticker_overrides) TO STDOUT;
\echo @@SCORES
COPY (SELECT score_date, ticker, rs_composite, sector FROM mi_stock_scores WHERE score_date >= '2026-09-25' AND score_date <= '2026-10-09') TO STDOUT WITH (FORMAT csv);
\echo @@CLOSES
COPY (SELECT ticker, trade_date, close FROM mi_daily_closes
      WHERE trade_date >= '2026-05-15' AND trade_date < '2026-10-10' AND close IS NOT NULL AND close > 0
        AND (ticker = 'SPY'
             OR ticker IN (SELECT ticker FROM mi_stock_scores WHERE score_date >= '2026-09-25' AND score_date <= '2026-10-09')
             OR ticker IN (SELECT unnest(tickers) FROM mi_themes WHERE theme_date >= '2026-09-14'))) TO STDOUT WITH (FORMAT csv);
\echo @@END
COMMIT;
