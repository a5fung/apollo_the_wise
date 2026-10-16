-- READ-ONLY. Shape check for tripwire flag_mna_screen_first_fire_598: flag-detector blocks since a date.
SELECT 'since 2026-10-04' AS w, count(*) FROM mi_audit_log WHERE event_type='mna_filter_fired' AND created_at >= DATE '2026-10-04'
   AND (summary LIKE '%(flag)%' OR detail LIKE '%''detector'': ''flag''%')
UNION ALL
SELECT 'ever', count(*) FROM mi_audit_log WHERE event_type='mna_filter_fired'
   AND (summary LIKE '%(flag)%' OR detail LIKE '%''detector'': ''flag''%')
UNION ALL
SELECT 'last flag block', NULL FROM (SELECT 1) x
UNION ALL
SELECT to_char(max(created_at) AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI'), count(*) FROM mi_audit_log WHERE event_type='mna_filter_fired'
   AND (summary LIKE '%(flag)%' OR detail LIKE '%''detector'': ''flag''%');
