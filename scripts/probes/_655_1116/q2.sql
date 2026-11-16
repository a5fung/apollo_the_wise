SET default_transaction_read_only = on;
\echo == A pass1_5 event-type counts since 10-17 (do skip rows exist; is the exempt event ever written)
SELECT event_type, count(*), min((created_at AT TIME ZONE 'America/New_York')::date), max((created_at AT TIME ZONE 'America/New_York')::date) FROM mi_audit_log WHERE event_type LIKE 'theme_pass1_5%' AND created_at >= '2026-10-17' GROUP BY 1 ORDER BY 1;
\echo == B every theme audit row naming a promoted theme in the 12 days from its promotion
WITH p(frag, since) AS (VALUES
 ('Software & Data Platforms Re-Rating for the AI Era','2026-10-22'::date),
 ('Natural Gas Producers & Midstream Pipelines','2026-10-29'),
 ('Home Pest Control & Lawn/Garden Residential Services','2026-11-02'),
 ('Self-Storage REIT Re-Rating','2026-11-05'),
 ('Packaged Food, Agri-Inputs & Consumer Staples Rotation','2026-11-06'),
 ('Housing-Cycle Rate-Relief Rebound','2026-11-09'),
 ('Digital Asset & Bitcoin Infrastructure Re-Rating','2026-11-12'))
SELECT a.id, a.event_type, (a.created_at AT TIME ZONE 'America/New_York')::timestamp(0) AS et, left(a.summary,230) AS summary, left(a.detail,260) AS detail
FROM mi_audit_log a JOIN p ON (a.summary LIKE '%'||p.frag||'%' OR a.detail LIKE '%'||p.frag||'%')
WHERE a.created_at >= p.since AND a.created_at < p.since + 12 AND a.event_type LIKE 'theme_%'
ORDER BY p.since, a.created_at;
\echo == C board presence + member count of each promoted theme by night (check column names with \d mi_themes first)
WITH p(nm, since) AS (VALUES
 ('Software & Data Platforms Re-Rating for the AI Era','2026-10-22'::date),
 ('Natural Gas Producers & Midstream Pipelines','2026-10-29'),
 ('Home Pest Control & Lawn/Garden Residential Services','2026-11-02'),
 ('Self-Storage REIT Re-Rating','2026-11-05'),
 ('Packaged Food, Agri-Inputs & Consumer Staples Rotation','2026-11-06'),
 ('Housing-Cycle Rate-Relief Rebound (Builders, Lenders & Home Services)','2026-11-09'),
 ('Digital Asset & Bitcoin Infrastructure Re-Rating','2026-11-12'))
SELECT p.nm, t.theme_date, t.source, cardinality(t.tickers) AS members, t.tickers
FROM p JOIN mi_themes t ON t.name = p.nm AND t.theme_date >= p.since AND t.theme_date <= p.since + 9
ORDER BY p.since, t.theme_date, t.source;
