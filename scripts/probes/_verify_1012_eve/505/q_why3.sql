\echo == ecosystem assignment time for the 3 replay-only children and their parents
SELECT theme_name, e_code, method, assigned_at::text FROM mi_theme_ecosystems
WHERE theme_name IN ('AI-Driven Memory & Storage Supply Shortage','AI-Driven Semiconductor Manufacturing Ecosystem (Capex & Foundry)','Enterprise Information Management & Infrastructure Engineering Software','Enterprise HR & Workforce Management SaaS','Gold Miners Not Yet Classified: Mid-Tier Gold Producers (AGI, NG, HYMC, MUX)','Primary Silver Miners') ORDER BY theme_name;
\echo == tonight ecosystem assignments (all)
SELECT id,(created_at AT TIME ZONE 'America/New_York')::text ts, left(summary,200) s FROM mi_audit_log WHERE event_type='theme_ecosystem_assigned' AND created_at > '2026-10-12 17:00:00-04' ORDER BY id;
\echo == Arm B proposed pairs tonight
SELECT id,(created_at AT TIME ZONE 'America/New_York')::text ts, left(summary,300) s, left(detail,1500) d FROM mi_audit_log WHERE event_type='theme_merge_pairs_proposed' AND created_at > '2026-10-12 17:00:00-04';
\echo == the 3 themes birth/first-seen
SELECT name, min(theme_date) first_seen, max(theme_date) last_seen, max(source) src FROM mi_themes WHERE name IN ('AI-Driven Memory & Storage Supply Shortage','Enterprise Information Management & Infrastructure Engineering Software','Gold Miners Not Yet Classified: Mid-Tier Gold Producers (AGI, NG, HYMC, MUX)','AI-Driven Semiconductor Manufacturing Ecosystem (Capex & Foundry)') GROUP BY 1;
