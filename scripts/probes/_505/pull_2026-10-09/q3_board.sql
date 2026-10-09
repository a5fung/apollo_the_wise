SELECT json_build_object('theme_date',(SELECT MAX(theme_date) FROM mi_themes)::text,'rows',json_agg(json_build_object('name',name,'stage',stage,'parent_theme',parent_theme,'source',source,'tickers',tickers,'score',score,'description',description,'rs_avg',rs_avg)))
FROM mi_themes WHERE theme_date=(SELECT MAX(theme_date) FROM mi_themes);
