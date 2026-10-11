"""Generate q6_extra_bars.sql: bars + stored rows for the tickers the q1 replay says the new carry would ADD
(distinct extra tickers, nights >= 2026-08-04, where the 25-session lookback sits wholly inside the 06-27 rule).
Read-only SELECT; run once on prod, capture to q6_extra_bars.out."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
tickers = sorted({p[2] for p in (ln.rstrip("\n").split("\t") for ln in open(os.path.join(HERE, "q1_admit_replay.out")))
                  if p[0] == "extra" and p[1] >= "2026-08-04"})
lst = ",".join(f"'{t}'" for t in tickers)
print(f"-- {len(tickers)} tickers. bars (k=bar) and stored rows (k=row) for the #697 deeper replay. READ-ONLY.")
print(f"SELECT 'bar' k, ticker, trade_date::text d, open_price::text a, high_price::text b, low_price::text c, "
      f"close::text e, volume::text f FROM mi_daily_closes WHERE ticker IN ({lst}) AND trade_date >= '2025-08-01' "
      f"AND open_price IS NOT NULL ORDER BY ticker, trade_date;")
print(f"SELECT 'row' k, ticker, scan_date::text d, stage a, COALESCE(held_from_stage,'') b, COALESCE(reason,'') c, "
      f"COALESCE(pivot_high_date::text,'') e, COALESCE(pivot_high_price::text,'') f FROM mi_flag_candidates "
      f"WHERE ticker IN ({lst}) AND scan_date >= '2026-07-01' ORDER BY ticker, scan_date;")
