SET default_transaction_read_only = on;
SELECT event_type, count(*) FROM mi_audit_log WHERE created_at > TIMESTAMPTZ '2026-10-26 20:00+00' AND (event_type ILIKE '%held%' OR event_type ILIKE '%under_floor%' OR event_type ILIKE 'promote_%') GROUP BY 1 ORDER BY 2 DESC;
SELECT count(*) skips, count(DISTINCT (detail::jsonb->>'theme')) themes, count(DISTINCT (detail::jsonb->>'ticker')||'|'||(detail::jsonb->>'theme')) pairs FROM mi_audit_log WHERE event_type='promote_member_skipped' AND created_at > TIMESTAMPTZ '2026-10-26 20:00+00';
SELECT detail::jsonb->>'theme' theme, count(*) nights_skipped FROM mi_audit_log WHERE event_type='promote_member_skipped' AND created_at > TIMESTAMPTZ '2026-10-26 20:00+00' GROUP BY 1 ORDER BY 2 DESC LIMIT 8;
