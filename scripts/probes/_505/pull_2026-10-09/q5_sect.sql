SELECT json_agg(json_build_object('t',ticker,'s',sector)) FROM mi_stock_scores WHERE score_date=(SELECT MAX(score_date) FROM mi_stock_scores) AND sector IS NOT NULL AND sector <> 'Unknown';
