\pset format unaligned
\pset fieldsep '\t'
\pset footer off
SELECT created_at, event_type, regexp_replace(summary, E'[\\n\\r\\t]+', ' ', 'g') AS summary, regexp_replace(coalesce(detail,''), E'[\\n\\r\\t]+', ' // ', 'g') AS detail FROM mi_audit_log WHERE event_type IN ('theme_engine_funnel','theme_discovery_llm_call','theme_assignment','theme_carryforward_filter_stripped','theme_member_pruned_while_rising','seeded_pool_admission') ORDER BY created_at;
