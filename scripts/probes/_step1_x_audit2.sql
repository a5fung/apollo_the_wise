\pset format unaligned
\pset fieldsep '\t'
\pset footer off
SELECT created_at, event_type, regexp_replace(summary, E'[\\n\\r\\t]+', ' ', 'g') AS summary, regexp_replace(coalesce(detail,''), E'[\\n\\r\\t]+', ' // ', 'g') AS detail FROM mi_audit_log WHERE event_type IN ('theme_pass1_protect_strip','theme_merge_dissolved_post_validation','theme_cap_drop','theme_sector_cap_dropped','theme_breadth_fade') ORDER BY created_at;
