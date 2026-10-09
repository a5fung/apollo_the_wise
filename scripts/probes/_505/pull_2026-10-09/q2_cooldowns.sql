SELECT json_agg(json_build_object('a',theme_a,'b',theme_b,'verdict',verdict,'reason',reason,'at',(adjudicated_at AT TIME ZONE 'America/New_York')::text,'until',(cooldown_until AT TIME ZONE 'America/New_York')::text,'live',cooldown_until>NOW()) ORDER BY adjudicated_at)
FROM mi_theme_merge_cooldowns;
