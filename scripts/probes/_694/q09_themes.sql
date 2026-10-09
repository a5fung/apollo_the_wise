-- #694 theme snapshots to rebuild the in-active-theme flag for days before the scan log recorded it (2026-08-29)
SELECT name, theme_date, stage, array_to_string(tickers, ',') tickers
  FROM mi_themes WHERE theme_date BETWEEN '2026-04-20' AND '2026-10-08' ORDER BY theme_date, name;
