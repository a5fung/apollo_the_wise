# COT snapshot (`apollo_cot_snapshot.json`)

Read-only nightly export for portfolio-app2's **COT** page: this week's COT index per market, the 12 weeks before it, and the last 60 alerts. Display only — no trade, grade, alert or sizing reads it. Family definition: `docs/setups/cot_family.md`.

| | |
|---|---|
| SQL | `scripts/export_cot_snapshot.sql` (one SELECT over `mi_cot_index_weekly`, `mi_cot_alerts`, `mi_cot_weeks`) |
| Run | `scripts/auto_export_snapshots.sh`, guarded like the breadth / RS Leaders exports (ON_ERROR_STOP, 300 s timeout, 200-byte floor; a failure keeps the last published file and never blocks the others) |
| Test | `tests/test_cot_export_sql.py` (static SQL checks, the VALUES list vs `cot_family.MARKETS`, the shell guard). NOT yet run against a real Postgres (none available when written): the first prod run is the SQL's first execution; check the file after the first 18:30 ET export |

## Rules
- Weeks = distinct `report_date` in `mi_cot_index_weekly`, newest = rank 1 (a holiday-shifted week is still one week). `report_date` = the newest week; `known_from` = the day Apollo first held it (`mi_cot_weeks`).
- Per market: the newest week's `comm` / `lspec` / `sspec` (0-100 index, 0 most short, 100 most long), `setup` / `close_setup` (`short`/`long` = the direction to fade into, else null), `prev` = the week before (null if none), `history` = the 12 weeks before the newest, oldest first. A market with no row in the newest week is not exported.
- `name` and `sector` come from the VALUES list in the SQL (not stored in the DB); a test keeps it equal to `cot_family.MARKETS`.
- Alerts: the newest 60 `mi_cot_alerts` rows, newest first. Labels only; nothing places an order.
- The page derives "near set ups" (`close_setup` set, `setup` null) and the exit watch (in a set up in `prev`, not now) from these fields.

## JSON contract
`version`, `generated_at`, `report_date`, `known_from`, `markets`[], `alerts`[], `definitions`.
Market: `market`, `name`, `sector`, `comm`, `lspec`, `sspec`, `setup`, `close_setup`, `prev` {`report_date`, `comm`, `lspec`, `sspec`, `setup`, `close_setup`}, `history`[] (same fields as `prev`).
Alert: `alert_date`, `market`, `direction`, `kind` (news / correlation / friday), `level`, `report_date`, `events`, `entry_price`, `stop_price`, `first_minute`, `first_minute_big`, `news_class`.

## Go-live
Server `git pull` (the cron reads the SQL from the checkout); the next nightly export publishes the file. Page: portfolio-app2 `pages/COT.py`.
