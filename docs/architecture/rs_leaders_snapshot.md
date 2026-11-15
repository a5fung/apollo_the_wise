# RS Leaders snapshot (`apollo_rs_leaders_snapshot.json`)

Read-only nightly export for portfolio-app2's **RS Leaders** page: the 50 strongest stocks by price return over 1 week / 1 month / 3 months / 6 months. Display only — no trade, grade, alert or sizing reads it.

| | |
|---|---|
| SQL | `scripts/export_rs_leaders_snapshot.sql` (one SELECT) |
| Run | `scripts/auto_export_snapshots.sh`, guarded like the breadth export (ON_ERROR_STOP, 300 s timeout, 200-byte floor; a failure keeps the last published file and never blocks the others) |
| Test | `tests/test_rs_leaders_export_sql.py` (static SQL checks + the shell guard); the SQL was also run on embedded Postgres against a 3,010-stock synthetic fixture and every ranking recomputed independently in Python (2026-11-15) |

## Rules
- Sessions, `as_of`, universe: the breadth export's (see `market_breadth_snapshot.md`): 3,000-row CS/ADRC session from the data, close >= 1.00, NaN never counts.
- **Liquidity floor: 20-session median dollar volume (close x volume) >= $5,000,000, on >= 15 of 20 sessions.** Median so one huge day cannot lift a dead stock; the floor keeps untradeable thin names off the board.
- Return = newest close / close 5 / 21 / 63 / 126 sessions earlier - 1. No bar on the base session = not ranked for that period. Ranked high to low, ties by ticker; top 50 each.
- `pct_from_high` = close vs the highest daily high of the last 252 sessions (<= 0). `adr20` = 100 x (mean high/low over 20 sessions - 1). `dollar_volume` = the 20-session median.
- `sector`: newest full RS run's sector, else `mi_ticker_overrides.sector`, else null. `name`: `mi_security_types.name`, else `mi_ticker_overrides.company_name`. `themes`: active-theme names holding the stock (newest row per theme within 7 days of as_of, not Retired).

## JSON contract
`version`, `generated_at`, `as_of`, `universe` {`n`, `n_liquid`, `min_dollar_volume`}, `periods` {`1w`,`1m`,`3m`,`6m`} each {`sessions`, `n_ranked`, `rows`[]}, `definitions`.
Row: `rank`, `ticker`, `name`, `close`, `ret`, `pct_from_high`, `adr20`, `dollar_volume`, `sector`, `themes`[].

## Go-live
Server `git pull` (the cron script reads the SQL from the repo checkout); first night publishes the file. Page: portfolio-app2 `pages/RS_Leaders.py`.
