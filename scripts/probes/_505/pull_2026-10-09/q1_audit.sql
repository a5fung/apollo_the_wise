SELECT json_agg(json_build_object('id',id,'ts',(created_at AT TIME ZONE 'America/New_York')::text,'event',event_type,'summary',summary,'detail',detail) ORDER BY id)
FROM mi_audit_log WHERE event_type LIKE 'theme_parent_pass%' AND created_at > NOW() - INTERVAL '45 days';
