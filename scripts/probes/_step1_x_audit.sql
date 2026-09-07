\pset format unaligned
\pset fieldsep '\t'
\pset footer off

SELECT created_at, event_type, regexp_replace(summary, E'[\\n\\r\\t]+', ' ', 'g') AS summary, regexp_replace(coalesce(detail,''), E'[\\n\\r\\t]+', ' // ', 'g') AS detail FROM mi_audit_log WHERE event_type IN ('theme_auto_retired','theme_pass1_5_absorption','theme_thesis_merged','theme_merge_parent_child','theme_split','theme_retired','theme_dissolved_flagged_pair','theme_renamed_for_continuity','theme_renamed_on_mass_flag','theme_retired_while_healthy','theme_subtheme_routed','theme_operator_promoted','theme_birth_gate','theme_birth_validated','theme_discovered','theme_new') ORDER BY created_at;
