SELECT name, theme_date, stage, array_length(tickers,1) AS n, source
FROM mi_themes
WHERE theme_date >= CURRENT_DATE - 20
  AND name IN ('Oncology Targeted Therapy Biotechs',
               'Rare & Orphan Disease Biotech',
               'Clinical-Stage Oncology Drug Development',
               'Autoimmune & Inflammatory Disease Biopharmaceuticals',
               'Targeted Protein Degradation Oncology',
               'Liquid Biopsy & Multi-Cancer Early Detection')
ORDER BY name, theme_date;
