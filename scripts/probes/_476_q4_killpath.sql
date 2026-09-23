SELECT (created_at AT TIME ZONE 'America/New_York')::date AS et_date,
       event_type, summary
FROM mi_audit_log
WHERE created_at >= NOW() - INTERVAL '30 days'
  AND event_type IN ('theme_pass1_protect_strip','theme_cap_drop','theme_auto_retired',
                     'theme_pass1_5_absorption','theme_save_dedup','theme_cap_strip',
                     'theme_subtheme_routed','theme_subtheme_route_merge','theme_subtheme_route_distinct')
  AND (summary ~* 'oncolog|autoimmun|inflammat|rare|orphan|biotech|clinical|therapeut|pharma|genom|gene |cell therapy|biopsy|neuro|metabol|cns|cardiometab|degradation|peptide|antibody|nucleic'
       OR detail ~* 'oncolog|autoimmun|rare|orphan|biotech')
ORDER BY created_at DESC
LIMIT 90;
