\pset format unaligned
\pset fieldsep '\t'
\pset footer off
SELECT ticker, coalesce(sector,'') AS sector, coalesce(industry,'') AS industry, (updated_at AT TIME ZONE 'America/New_York')::date AS updated_et FROM mi_ticker_overrides ORDER BY ticker;
