# COT snapshot (`apollo_cot_snapshot.json`)

Read-only nightly export for portfolio-app2's **COT** page: this week's COT index per market, the 12 weeks before it, and the last 60 alerts. Display only — no trade, grade, alert or sizing reads it. Family definition: `docs/setups/cot_family.md`.

| | |
|---|---|
| SQL | `scripts/export_cot_snapshot.sql` (one SELECT over `mi_cot_index_weekly`, `mi_cot_alerts`, `mi_cot_weeks`) |
| Run | `scripts/auto_export_snapshots.sh`, guarded like the breadth / RS Leaders exports (ON_ERROR_STOP, 300 s timeout, 200-byte floor; a failure keeps the last published file and never blocks the others) |
| Test | `tests/test_cot_export_sql.py` (static SQL checks, the VALUES list vs `cot_family.MARKETS`, the peer list vs `cot_family.PEERS`, the shell guard). NOT yet run against a real Postgres (none available when written): the first prod run is the SQL's first execution; check the file after the first 18:30 ET export |

## Rules
- Weeks = distinct `report_date` in `mi_cot_index_weekly`, newest = rank 1 (a holiday-shifted week is still one week). `report_date` = the newest week; `known_from` = the day Apollo first held it (`mi_cot_weeks`).
- Per market: the newest week's `comm` / `lspec` / `sspec` (0-100 index, 0 most short, 100 most long), `setup` / `close_setup` (`short`/`long` = the direction to fade into, else null), `prev` = the week before (null if none), `history` = the 12 weeks before the newest, oldest first. A market with no row in the newest week is not exported.
- `name` and `sector` come from the VALUES list in the SQL (not stored in the DB); a test keeps it equal to `cot_family.MARKETS`.
- Alerts: the newest 60 `mi_cot_alerts` rows, newest first. Labels only; nothing places an order.
- Alert readings (added 2026-11-25, for the page's expandable tile; all additive, the old keys are unchanged): `z` = the market's own day move, (close - previous close) / its 20-day average range, RAW signed (up = positive; a failure is against the crowd, so short set up = negative, long = positive); `peer_z` = the peers' median move in each peer's own range, signed so POSITIVE = the CROWD's way (crowd = long for a short set up, short for a long one; `cot_family.peer_reading`); `comm` / `lspec` / `sspec` = the 0-100 index at alert; `entry_note` + `entry_price` (the failure day's close; null on a Friday row, which enters at the next open); `stop_rule` = plain text; `failure_day` (set on Friday rows); `atr` and `news`[] ({`event`, `class` WITH / AGAINST / INLINE / AMBIG / UNKNOWN, `z` = the surprise vs forecast, `first_minute` {`status`, `move` in day-ranges, + = the crowd's way, `big`}}) come from `detail`, which some rows store double-encoded (a JSON string holding the JSON): the SQL unwraps both, and a string that is not an object reads as no detail.
- `peers`[] ({`market`, `name`, `inverse`}) = the markets the correlation reading was taken over, for the alert's market. Derived in SQL from a `peerdef` VALUES list a test keeps equal to `cot_family.PEERS` (chosen over a static map in the page: the page repo then carries no second copy to drift, and the names ride in the file itself). `inverse` = the peer moves the opposite way (Dollar Index vs currencies), already flipped in `peer_z`.
- Old snapshots lack all of these; the page renders them as a plain tile.
- The page derives "near set ups" (`close_setup` set, `setup` null) and the exit watch (in a set up in `prev`, not now) from these fields.

## JSON contract
`version`, `generated_at`, `report_date`, `known_from`, `markets`[], `alerts`[], `definitions`.
Market: `market`, `name`, `sector`, `comm`, `lspec`, `sspec`, `setup`, `close_setup`, `prev` {`report_date`, `comm`, `lspec`, `sspec`, `setup`, `close_setup`}, `history`[] (same fields as `prev`).
Alert: `alert_date`, `market`, `direction`, `kind` (news / correlation / friday), `level`, `report_date`, `events`, `entry_price`, `stop_price`, `first_minute`, `first_minute_big`, `news_class`, `z`, `peer_z`, `comm`, `lspec`, `sspec`, `entry_note`, `stop_rule`, `failure_day`, `atr`, `news`, `peers`.

## Go-live
Server `git pull` (the cron reads the SQL from the checkout); the next nightly export publishes the file. Page: portfolio-app2 `pages/COT.py`.
