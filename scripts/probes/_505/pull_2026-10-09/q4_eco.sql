SELECT json_agg(json_build_object('name',theme_name,'e',e_code)) FROM mi_theme_ecosystems;
