# COT news watch — line the news up before it lands, then judge it (design, 2026-11-25)

**Scoring ruling (review round, 11-25):** the judged row is scored on the LINED-UP forecast (the frozen pre-release figure), not the figure listed after the release; with none stored it falls back to the release-day read and the card says so. Rules: `docs/setups/cot_family.md` §News watch scoring.

**Status:** built 2026-11-25 on branch `cot-news-watch`, not deployed (see §7). **Owner of the rules:** `docs/setups/cot_family.md` (this file is a finding /
build spec, never the owner). **Money:** none — display and labels only; `detect()`, the alert rule and the Telegram
messages are NOT changed by this build.

**His ask (2026-11-25):** *"What Shapiro does is watch for news failure, so ideally we'll have news lined up already,
so setup or close setup should expand for news to watch for and what's expectation, once news is here, we assess vs
expectation, bullish v bearish, and market action after it."*

## 0. What was found (code + two source reads; prod NOT read)

| Question | Answer | Evidence |
|---|---|---|
| Which events map to which markets | `cot_family.EVENT_MARKETS` + `EARNINGS_MARKETS` (table in §1.1) | code |
| Which way a surprise pushes a market | `cot_family.news_sign()` (the research's mapping) and the component signs in `SURPRISE_COMPONENTS` | code |
| Is a forecast known BEFORE the release | **Yes for most US data, late for EIA.** The same FXEmpire rows the job already reads carry `forecast` and `previous` ahead of the release | read 2026-11-25 14:50 ET: NFP Fri 12-04 already shows 82.0K / unemployment 4.2%, nine days ahead. EIA stocks for 12-02 / 12-03 show blank. In the 11-17 file the 11-18 EIA rows were still blank the day before; by release day they carry one (11-25: crude 1.5M) |
| How the forecast is fetched today | `fetch_fxempire` -> `refresh_this_week` (every weekday 17:15 ET, this Mon-Sun week only) and `refresh_calendar` (Mondays, 3 more US weeks + 6 other countries 6 weeks out). **The forecast is read and thrown away**: `calendar_rows_from_fx` keeps date / type / time only | code |
| Stored per event now | `mi_cot_calendar`: `event_date` (the session), `event_type`, `release_et`, `source`, `refreshed_at`. No forecast, no actual | `db.py` |
| Stored per alert now | `mi_cot_alerts.detail.news[]`: `{event, class, z, first_minute{status, move, big}}` + the row's `z` (close move) | code |
| The gap | The news read and the first minute are computed **only when an alert fired** (`_label` runs on alerting markets). A news day where the market followed the news leaves no trace, so "no failure" cannot be shown today | code |
| Non-US events | The Australian page carries forecasts too (CPI 11-24: 0.4% forecast, 0.5% actual) but there is no measured mapping or typical-surprise number for them | read 2026-11-25 |

Not verified (the prod read was refused in this session; the query is saved unrun at
`scripts/probes/_cot_newswatch_design_1125/nw_q1_schema_rows.sql`): the live table shapes, the stored calendar rows,
and whether the 11-22 news sources and the 11-25 alert-tile export are on the server yet. The local snapshot of
11-24 18:30 ET has no `z` / `news` keys on alerts, so the server had not pulled the 11-25 export by then. The raw
source read is at `scripts/probes/_cot_newswatch_design_1125/nw_fx_1123_1206.json`.

## 1. What an expanded set-up / near-set-up card shows

One block per scheduled event for that market, oldest first, covering the last 7 days and the next 7. A card with no
event in the window does not expand (it stays as it is now).

### 1.1 Three kinds of event (decides what the "expectation" line can say)

| Kind | Events | Forecast figure | Crowd read |
|---|---|---|---|
| **A. Forecast + crowd read** | CPI, PPI, PCE, NFP, Retail sales, GDP, Fed decision, EIA oil stocks (crude / gasoline / distillate by market), EIA gas stocks, company earnings (stock indices) | yes (EIA: often only on the day; earnings: the EPS estimate if the source lists it, else "no forecast") | yes |
| **B. Forecast shown, no crowd read** | Australian CPI / jobs / wages, RBA / ECB / BoE / BoJ / BoC / SNB decisions; and any kind-A event on a market where `news_sign` returns 0 (e.g. growth data on stock indices, anything on platinum / palladium) | shown raw when the source lists one | "no crowd read for this market" |
| **C. No forecast** | WASDE, OPEC+ meeting, USDA weekly export sales, Fed minutes, RBA minutes | "no forecast" | none |

Kind B is NOT upgraded to a crowd read here: `cot_family.md` allows a consensus read only where the research holds a
frozen typical-surprise number and a mapping. That is a separate, evidence-gated addition.

Event -> markets (from `EVENT_MARKETS`): the seven US macro types and Fed minutes -> every equities / rates /
currency / metals / crypto market; EIA oil -> crude, heating oil, gasoline; EIA gas -> natural gas; WASDE -> grains,
livestock, cotton, sugar; OPEC+ -> the three oil markets; export sales -> soybean oil, soybeans, meal, corn, wheat;
each central bank and the Australian data -> its own currency; the ten large-company earnings -> NASDAQ, S&P, Dow.

### 1.2 BEFORE the release

```
NFP (jobs report) · Fri 12-04 08:30 ET
Forecast: payrolls 82.0K (prior 165K) · unemployment 4.2% (prior 4.1%)   [as read Thu 12-03 17:15 ET]
Crowd is SHORT silver. News that favours the crowd: jobs STRONGER than forecast
  (payrolls above 82.0K, unemployment below 4.2%) = bearish silver.
Failure to watch for: that news, a first move down, then a close UP.
```

- Kind B: the forecast line, then "No crowd read for this event on this market."
- Kind C: "No forecast for this event. Watch the reaction: a close UP after it is against the crowd."
- Forecast blank at the last read: "No forecast listed yet."
- The crowd sentence is written by the job in Python (§2.3), never by the page or the SQL.

### 1.3 AFTER the release (same block, three steps, then the verdict)

```
NFP (jobs report) · Fri 12-04 08:30 ET
1 News:         payrolls 120K vs 82.0K · unemployment 4.1% vs 4.2% -> stronger than forecast
                = bearish silver = WITH the crowd
2 First minute: moved the crowd's way by 0.31 of a day's range (big)
3 Close:        UP 0.42 of a day's range = AGAINST the crowd
=> NEWS FAILURE, all three steps      · alert sent
```

Verdict table (step 3 decides failure or not; steps 1 and 2 say how clean it is). The live alert rule is the looser
one — any scheduled event plus a close against the crowd — so the card names both readings and never hides an alert:

| Close | News read | First minute | Code | Words on the card |
|---|---|---|---|---|
| against the crowd | with the crowd | crowd's way | `failure_full` | NEWS FAILURE, all three steps |
| against the crowd | with the crowd | flat / against / not read | `failure` | News failure: news favoured the crowd, closed against them (first move: ...) |
| against the crowd | against the crowd | any | `followed_news` | No failure: the market followed the news (the news itself was against the crowd). Alert sent under the live rule |
| against the crowd | in line / no crowd read / no forecast | any | `against_unread` | Closed against the crowd on a news day; the news had no clear read. A failure by the live rule only |
| crowd's way | with the crowd | any | `followed_news` | No failure: the market followed the news |
| crowd's way | against the crowd | any | `shrugged` | No failure: bad news for the crowd, and the market closed their way anyway |
| crowd's way | anything else | any | `no_failure` | No failure: closed the crowd's way |
| no final daily bar | — | — | `pending` | Pending close |

"First minute the crowd's way" = a read first minute with `move` above 0.01 of a day's range (the page's flat band);
the raw move is stored, so the stricter-rule test can re-cut that line later. When no forecast was seen before the
release, step 1 shows the figure the source lists afterwards, labelled "forecast read after the release" — the news
read is always scored from the same 17:15 read the alert label uses, so the card and the alert never disagree.

`strict` = true only on `failure_full`. That is the doc's rule (news favours the crowd, first reaction their way,
close against); `alerted` = a news alert row exists for that market and day (the live rule). Both are stored on every
row, so the forward record for the stricter-vs-looser comparison builds itself, including the days no alert fired.

**"Pending close" is a rare state, not a live view.** The job judges at 17:15 ET and the page is refreshed once, at
18:30 ET. A normal release is therefore seen as "before" one evening and "judged" the next. Pending shows only for a
release after the 17:00 close that belongs to the next session (company earnings) or when the day's bar could not be
read. Between a release and that evening's refresh the page writes "Released; the result arrives after 18:30 ET"
from the release time against the clock (ET) — it does not pretend to know the outcome.

## 2. Data: where it comes from, the smallest change

### 2.1 One new table, nothing else changed

`mi_cot_news_watch`, one row per (session day, event, market). Chosen over adding forecast columns to
`mi_cot_calendar` because `replace_calendar` deletes and re-inserts future calendar rows on every refresh (a stored
forecast would be wiped), and because the "after" half is per market anyway.

| Column | Type | Meaning |
|---|---|---|
| `event_date`, `event_type`, `market` | DATE, TEXT, TEXT — primary key | same keys as `mi_cot_calendar` |
| `release_et` | TIMESTAMPTZ null | copied from the calendar row (null for OPEC+) |
| `direction`, `level`, `report_date` | TEXT, TEXT, DATE | the set up the row was built on: short / long, main / close, the COT week |
| `read` | TEXT | `mapped` / `ambiguous` / `none` (kinds A / B / B-C above, from `news_sign`) |
| `crowd_outcome` | TEXT | the plain sentence of §1.2; empty unless `read = mapped` |
| `series` | JSONB | `[{name, forecast, previous, actual, forecast_after}]` as printed by the source (text, e.g. "82.0K"). `forecast` = the last figure read BEFORE the release; `forecast_after` = the figure in the judging read (what the news read was scored on) |
| `forecast_seen_at` | TIMESTAMPTZ null | when the stored forecast was read; null = none was seen before the release |
| `news_class`, `surprise_z` | TEXT, DOUBLE null | from the existing `news_class()` |
| `first_minute` | JSONB null | `{status, move, big}` from the existing `first_minute()` |
| `close_z`, `close_against` | DOUBLE, BOOL null | the day's close move in day-ranges (raw sign) and whether it was against the crowd |
| `verdict`, `strict`, `alerted` | TEXT, BOOL, BOOL null | §1.3 |
| `judged_at`, `updated_at` | TIMESTAMPTZ | |

Created in `db.py`'s `_COT_FAMILY_DDL` beside the other `mi_cot_*` tables (`CREATE TABLE IF NOT EXISTS`); that block
is run by `initialize_schema()` at market-agent startup (`agent.py`), so the table exists as soon as the deploy boots.

### 2.2 Who writes it (both existing jobs; no new job, no new schedule)

1. **Upcoming rows** (`event_date` after today, up to 7 days ahead) — written at the end of every `cot_daily` run and
   at the end of `cot_weekly` when it stored a new week. Direction and level come from the **newest stored COT week**
   (what the cards show). Upsert each (event, market) pair; then delete future rows no longer in the built set.
   `cot_weekly` makes NO calendar read for this: a market that joins the list on Friday copies `series` and
   `forecast_seen_at` from a stored row of the same event on another market (EIA oil stocks are per market, so those
   are not copied); with none to copy it reads "no forecast listed yet" until Monday's 17:15 run.
2. **Today's rows** — judged inside `cot_daily` after `detect()`. Direction and level come from the daily job's own
   `setups` (the **week known before today**, the same one the alert used). Every set-up or near-set-up market with an
   event today gets a row, alert or not. Rows for a market not in `setups` today are deleted.
3. **The forecast is frozen at the release.** Every read made BEFORE `release_et` that carries a forecast figure
   refreshes `series[].forecast` and `forecast_seen_at` (so the card holds the latest pre-release figure); a blank
   read never erases a stored one; no read at or after `release_et` touches either. `actual` and `forecast_after`
   are filled by the judging read.
4. **A failure here never blocks or changes an alert.** The whole write sits in its own try; the error goes in the
   audit row under `news_watch`. It does not page; instead the export carries the newest `updated_at` and the page
   prints "news watch last updated <date>" when it is more than one weekday old (so silence is visible).

### 2.3 Fetches: reuse first, three small additions

| Need | Today | Change |
|---|---|---|
| US forecast + actual, this week | `refresh_this_week` already returns the raw rows | keep the `forecast` / `previous` / `actual` text of the component series (new pure helper `expectations_from_fx(events, country)` -> `{(session day, type): [series...]}`) |
| US forecast, next 7 days across a week boundary | next week is read on Mondays only, so a Friday-evening card would show Monday's figure | every `cot_daily` also reads NEXT US week (one more request, 1.5 s pause). Its calendar rows replace the stored ones only when the answer holds a trigger row (the existing empty-answer guard); an empty or failed read is recorded, not paged — Monday's full refresh still pages |
| Other countries' forecast | read on Mondays (6 weeks out) and dropped | `refresh_calendar` hands back the raw rows it already read; the watch keeps their forecast. On a day one of these events is in today's rows, read that country's page for today once to get the actual (shown raw, kind B) |
| Earnings estimate | `fetch_earnings` already returns `estimate` | use it when the source lists it for the upcoming date; otherwise "no forecast" (not checked whether it is listed ahead) |
| First minute for every event market | minute bars fetched only for alerting markets | fetch once per set-up market that has a timed event today and share it with `_label` (one fetch per market per run) |
| Crowd sentence | — | new pure helper: favouring surprise sign = `crowd_sign(direction) * news_sign(type, market)`; words per type below; figures from `series` with each component's sign |

Words for a surprise ABOVE forecast (below = the opposite): CPI / PPI / PCE "inflation hotter than forecast"; NFP
"jobs stronger than forecast (payrolls above X, unemployment below Y)"; Retail "retail sales stronger"; GDP "growth
stronger"; Fed decision "a rate above forecast (a hawkish surprise)"; EIA "a bigger stock build, or a smaller draw,
than forecast"; earnings "an EPS beat". Then "= bullish / bearish <market> = favours the crowd". A surprise smaller
than a quarter of the series' typical miss reads "in line" (existing `SURPRISE_DEAD_ZONE`).

The added FXEmpire reads run AFTER the alert-critical reads (this week's calendar, the alerts, the message) and are
skipped when FXEmpire refused a request earlier in the run (`fx_ok`), so the extra volume can never blind an alert.

No model call anywhere. Network cost: +1 FXEmpire request per weekday, +1 on a non-US event day, and on a macro day
up to one 1-minute pull per set-up market (17 markets on the 11-17 report) instead of one per alerting market.

## 3. Export and page (additive; old files and old pages keep working)

**`scripts/export_cot_snapshot.sql`** — `version` stays 1.
- Each market object gains `news_watch`: `[]` or a list ordered by `event_date`, `release_et`, for rows with
  `event_date` between today − 7 and today + 7 (ET today), each
  `{event, event_date, release_et ("YYYY-MM-DD HH:MI ET" or null), direction, level, read, crowd_outcome, series,
  forecast_seen_at, news_class, surprise_z, first_minute, close_z, close_against, verdict, strict, alerted}`.
- Top level gains `news_watch_asof` (newest `updated_at`, ET text, or null) and a `definitions.news_watch` sentence.
- No existing key changes. `docs/architecture/cot_snapshot.md` documents the new keys in the same commit;
  `tests/test_cot_export_sql.py` gets the static checks.

**portfolio-app2** (`cot_view.py`, `pages/COT.py`)
- `card_html`: when the market has `news_watch` entries the card becomes `<details>` (the pattern of the alert tile,
  commit 5e10ce4). The closed card gains one line: the next event ("next: NFP Fri 08:30 ET") or the latest verdict
  ("Wed EIA: news failure"). Expanded: the blocks of §1.2 / §1.3 from a new pure `watch_lines(entry, market_name, now_et)`.
- Missing key, empty list or a malformed entry -> the card renders exactly as today (same try / fallback as the alert tile).
- `contract_problems` does NOT require the new keys.
- The alerts log is untouched.

## 4. Deploy scope and risks

| Step | Scope | Note |
|---|---|---|
| 1 | `bash scripts/deploy.sh market-agent` AND `execution` | `cot_family.py`, `db.py`; `db.py` is in `scripts/exec_loaded_modules.txt`, so the execution service loads it too. The same pull puts the new export SQL in the checkout the cron reads. No slash command, so no orchestrator; no broker code beyond that shared `db.py` |
| 2 | first `cot_daily` after it (17:15 ET) | writes the first rows; the 18:30 ET export then carries them |
| 3 | push portfolio-app2 | any time; the page tolerates the key being absent |

Order matters only one way: the export SQL names the new table, so it must not reach the server before the
market-agent has created it. One `deploy.sh market-agent` does both in the right order (pull, build, boot, then the
evening cron). If the export does run first it fails guarded and the last published file stays. Build from `main`
(the working tree's other branches are not the deploy source). Weekend deploy windows are open.

Risks:
- **More requests to free sources.** FXEmpire +1 a day; Yahoo 1-minute pulls up to one per set-up market on macro days. A refusal on the watch's own reads is recorded and the block reads "not read"; the alert path keeps its existing pages.
- **The forecast is the calendar's figure, not an official consensus.** It is the same field the live news read and the research's typical-surprise numbers were built on, so the card and the label agree; it can differ from a Bloomberg consensus.
- **EIA forecasts land late.** Until measured, the evening-before card will often say "no forecast yet". `forecast_seen_at` records when each one first appears; if most appear only on the morning, a short pre-release read is the follow-up (his call, see below).
- **Two COT weeks.** Upcoming rows use the newest week, today's verdict the week known before today. They differ only around a new report; today's rule (§2.2 point 2) wins for the judged row.
- **Holiday-moved releases** are whatever the source lists; a release the source moves after our last read keeps its old row until the next read (existing behaviour of the calendar).
- **Friday-confirmation alerts** are not shown in the watch (they have their own tile); the failure day's watch row already carries the verdict.

For him to rule (none blocks the build):

| Fork | Recommendation |
|---|---|
| The verdict wording of §1.3 | ship as written, adjust on first sight |
| A second, morning read so EIA forecasts are on the card before 10:30 | decide after two weeks of `forecast_seen_at` |
| A crowd read for Australian data and the other central banks | separate research task (needs measured numbers); not in this build |
| Refreshing the page more than once a day | not now; the nightly cadence gives "before" one evening, "judged" the next |

## 5. Verify plan (written before the build)

Target week: Mon 11-30 – Fri 12-04, assuming a weekend 11-28/29 build and deploy. Markets are whatever the cards
show that week (a new COT report lands first) — the checks name events, not markets.

**BASELINE (today):** the snapshot has no `news_watch` key; set-up cards do not expand; a news day with no alert
stores nothing; forecasts are never stored.

**EXPECT**

| # | When (ET) | What the page / table should show |
|---|---|---|
| 1 | Mon 11-30 after 18:30 | every set-up or near-set-up card for a rates / currency / metals / stock-index / crypto market expands and lists **NFP, Fri 12-04 08:30 ET** with a payrolls and an unemployment forecast (82.0K / 4.2% as of 11-25; may move) and, on mapped markets, the crowd sentence |
| 2 | Mon 11-30 after 18:30 | the oil cards show the **OPEC+ meeting** (session Mon 11-30) judged with "no forecast" and first minute "no release time" |
| 3 | Tue 12-01 and Wed 12-02 after 18:30 | oil cards: **EIA, Wed 12-02 10:30** — Tuesday either a forecast or "no forecast yet" (write down which: that is the measurement); Wednesday the three steps and a verdict. Same for natural gas, Thu 12-03 10:30 |
| 4 | Thu 12-03 after 18:30 | the NFP forecast on the card, with `forecast_seen_at` that evening |
| 5 | Fri 12-04 after 18:30 | every NFP row has actual figures, a news read, a first-minute reading, the close and a verdict; the forecast is still Thursday's figure |
| Unintended | all week | the `cot_daily` audit row is written as before and its alert count matches the Telegram message; no new page; old snapshot keys unchanged; the alerts log renders as before |

**DONE-WHEN:** rows 1, 4 and 5 hold for NFP 12-04 on at least one mapped market, with the verdict re-derived by hand
from that row's own numbers; row 2 or the Thu 12-03 export-sales row shows the "no forecast" path; at least one
"no failure" verdict was written on a day with no alert; and every news alert sent that week has a watch row with
`alerted = true`. Stop watching after Fri 12-04 (if that Friday's run fails, the next weekly EIA is the retest).

**WOULD-FAIL-IF** (each is a positive reading a broken build would give):
- Thu 12-03 evening the card has no NFP block, or its forecast is blank while the source lists one.
- `forecast_seen_at` on an NFP row is 08:30 Fri or later, or the stored forecast differs from Thursday evening's (it was overwritten after the release).
- A market that got a news alert shows `close_against = false` or a "closed the crowd's way" verdict (the watch and the alert disagree about the same bar).
- A set-up market with an event and a daily bar that day has no row, or a row with no verdict.
- The crowd sentence points the wrong way: check one long and one short set up by hand against `news_sign`.

## 6. Card for the build (one Sonnet card)

1. `db.py`: the table of §2.1.
2. `cot_family.py`: pure helpers `expectations_from_fx`, `crowd_outcome_words`, `watch_verdict`; `Io` methods to
   upsert / prune / read watch rows; the two write points of §2.2; the next-week read and the shared minute fetch of
   §2.3. `detect()`, `_alert_row`, the message formatters and every threshold stay byte-identical.
3. Tests (`tests/test_cot_family.py`): the verdict table row by row; the crowd sentence for one long and one short
   set up on CPI, NFP (two components, opposite signs), EIA and an ambiguous pair; the forecast freeze (a post-release
   read does not overwrite; a blank read does not erase); a watch failure leaves the alerts and the message unchanged;
   upcoming rows follow the newest week, today's rows follow `setups`.
4. `scripts/export_cot_snapshot.sql` + `tests/test_cot_export_sql.py` + `docs/architecture/cot_snapshot.md`.
5. `docs/setups/cot_family.md`: a "News watch" paragraph under Live alerts, the new table in the table list, a change-log
   entry (display only; no detection change, so no backtest), and a link to this file.
6. portfolio-app2: `cot_view.py` + `pages/COT.py` per §3; render the sheet against a hand-made snapshot holding one
   before, one judged and one "no forecast" entry.
7. No deploy from the card. No subagents.

## 7. Build notes (2026-11-25)

- Built per §6. Rules now live in `docs/setups/cot_family.md` §News watch; the export keys in `docs/architecture/cot_snapshot.md`.
- Where the doc and the build differ: the export formats minutes as `HH24:MI` (the doc's `HH:MI` is a 12-hour clock); the
  daily watch step sits at the very end of `_daily_body`, outside the "usable week" branch, so rows for the days ahead are
  also written when no week is usable today; the weekly rebuild is in `run_weekly`, not `ensure_week` (the daily catch-up
  also calls `ensure_week`); `refresh_calendar` takes an optional `raw_out` so Monday's full refresh hands its raw rows to the
  watch (no second next-week request that day); `_label` takes an optional per-run `cache` so the minute bars and earnings rows
  it fetched are reused.
- `forecast_seen_at` follows §2.2 point 3 (the LATEST pre-release read that carried a figure), not the §4 risk bullet's
  "first appears": to measure when an EIA forecast first lands, read the stamp on consecutive evenings' exports.
- Not run: the export SQL and the DDL have been parsed by the Postgres grammar (pglast) and checked column-by-column
  against the DDL, but never executed on a database (none available); a failure there leaves the whole COT file stale,
  not only the new key.
