# COT family — crowded-positioning fades (Jason Shapiro's CMR method)

**Owner of:** the COT family's definition, its setups, their buy and stop, findings and change log.
**Phase:** alerts only (2026-11-15: two read-only jobs send research alerts; no strategy row, no orders). Futures; Alpaca cannot trade futures yet.
**Operator's framing (2026-11-15):** *"This is part of Apollo, we can't trade futures with it yet, but this is just
another setup for Apollo. The long term plan is that Apollo trades many strategies with ultimate goal it being about
to trade several uncorrelated strategies successfully."* — and *"Let's make this the cot setup family."*

Research workspace: `~/cmr_lab` (private; the newsletter text stays out of every git repo — its licence forbids
building a database from it). This file holds only the method and the measured results.

## FAMILY vs SETUPS (CLAUDE.md definition)

The FAMILY is the **condition**: a futures market whose three trader groups are at opposite crowded extremes on the
COT index. It is not tradeable alone — Shapiro "will never enter a trade based on a market becoming max crowded".
The SETUPS inside it each have a buy point and a stop:

| Setup | Trigger (on a set-up market) | Buy | Stop |
|---|---|---|---|
| **COT news failure** | scheduled news that should move the market WITH the crowd; first reaction goes that way; the day closes AGAINST the crowd | that session's close (or the next open when posted after the close / over a weekend) | a CLOSE beyond that day's high (shorts) / low (longs); never trailed |
| **COT correlation failure** | the market closes against the crowd while a closely tied peer closes strongly the crowd's way (e.g. Soybean Oil red, Crude green) | same | same |
| **COT Friday confirmation** | the failure happened earlier in the week; Friday's new COT data completes the set up | next open (Sunday night) | a close beyond the failure day's high / low |

**Exit (all three):** a close beyond the stop, or when the relevant group's index returns to ~50 (Commercials for
equity indices; any group otherwise). No targets. **Size:** 0.7% of the account at risk; half size when the signal is
weaker or a correlated position is already on.

## The COT index (rebuilt exactly, 2026-11-15)

- Data: CFTC legacy Futures-Only report; nets of Commercials, Non-commercial (Large Specs), Non-reportable (Small Specs).
- Index per group = 100 × (net − min) / (max − min) over a market-specific lookback of N weekly reports back,
  inclusive of the current week; rounded half up. 0 = max crowded short, 100 = max crowded long.
- Set up: Commercials ≤ 5 and both speculator groups ≥ 95 (short), or the mirror (long); equity indices on
  Commercials alone.
- Close to a set up (his footnote: "markets of interest based on Jason's review and Commercials reaching max or very
  close to max crowded levels and waiting for both speculators to reach max levels"; operator: a speculator group at
  the opposite extreme is not a set up): not a set up, Commercials ≥ 95, Large Specs ≤ 15, Small Specs ≤ 80 (long),
  or the mirror (short: ≤ 5, ≥ 85, ≥ 20). Equity indices: Commercials 90–94 / 6–10. His review drops a few each week;
  the rule cannot see that.
- Lookbacks (weeks): equities 26–27; Pound / Yen / CAD / Swiss 30; AUD / NZD ~80; Euro / Dollar Index 90; bonds ~97;
  Crude / Heating Oil / Gasoline 40; Natural Gas 68; Gold 24, Silver 23, Platinum 16, Copper 86; Coffee / OJ 8,
  Cocoa 10, Cotton 40, Sugar 131; Wheat 10, Meal 30, Bean Oil 34, Corn 86, Soybeans 127; Hogs / Cattle 13;
  Bitcoin / Ether 89. Full table: `~/cmr_lab/data/lookback_final.csv`.
- Verified: our formula reproduces his unadjusted index on 126 of 129 cells for 2026-11-08 (misses = Oats, no longer
  reported by the CFTC). His published index adds a small adjustment for Tuesday→Friday price / open-interest moves
  (usually 0–3 points). The set-up rule on his official index reproduces his newsletter set-up list at 92% precision /
  98% recall.
- Open: lookbacks drift over 2021–2026 (some re-tuned in 2025).

## Findings (research, 2023-08 → 2026-11; his 69 eligible trades)

| Feed | Alerts / month | His trades caught (strict / ±1 day) | Notes |
|---|---|---|---|
| A: event day closes against the crowd, or peer divergence | 11.7 | 43% / 51% | pre-registered; PARTIAL vs a 60% bar |
| A + Friday confirmation | 13.0 | 48% / 55% | Friday alert exploratory |
| First tick read on HOURLY bars | 1.8 | 13% | too coarse: the hourly bar matches the first 5 minutes 2 times in 3 |

- Precision counting trades he took OR said he missed: ~15% of alerts.
- His 5 timed labelled news failures: the first hour moved the way he described in all 5.
- Open: a true first-tick (1-minute) test; the news's own bullish/bearish read vs expectations (consensus) before
  watching for the failure — the operator's point, 2026-11-15.

## Live alerts (2026-11-15) — alerts only, no orders

**Phase: alerts.** Two read-only jobs send research alerts to the paper chat so the weekly newsletter can score them
forward. No strategy row, no order, no sizing, no broker import. Code: `agents/market_intelligence/cot_family.py`
(rules copied from the research and frozen; nothing tuned live).

| Job | When (ET) | What it does |
|---|---|---|
| `cot_weekly` | Fri 17:40, retry 18:40 | Reads the CFTC report (released Fri 15:30), computes the index for 40 markets (Oats left out: no longer reported), stores the week, sends ONE message: this week's set ups (main rule, and the close list: Commercials at max, waiting on the speculators), markets that LEFT a set up or reached neutral ~50 (the exit signal for anyone holding), and the Friday-confirmation alerts. One message per report week; the retry is a no-op once it has gone. |
| `cot_daily` | Mon–Fri 17:15 | For each market set up (main or close list) in the week **known before today**: today's daily bar, today's scheduled events, feed A. ONE message when there is an alert; silence otherwise; one audit row every run. Mon–Thu, after the day's calendar read and before the alerts, it picks up a holiday-delayed CFTC release (and then sends that week's message, entry "the next open"). |

Why after 17:00: the futures daily bar ends at 17:00 ET, and the Friday check needs Friday's bar. The daily job
refuses to run on a bar that is not final.

**No look-ahead.** A week is stored with `known_from` = the ET day we first held it; a day's alerts use the latest
week with `known_from` BEFORE that day (the research's timing: the issue in hand before the session). A week older
than 17 days (the research's 12-day carry past the issue Sunday) is not used. On the FIRST run only, a report more
than a week old is stamped known from its scheduled Friday (it was public long before the job existed). After that,
a report first seen today is known from today however old its date — a backlog release after a CFTC outage is not
used on the day it lands — and the weeks between it and the last stored one are stored too (no message for those).
A report more than 10 days old gets no Friday-confirmation check — that moment has passed.

**What a daily alert is (feed A, as scored in the research — 11.7 alerts / month there):**
- News failure (N1): the market has a scheduled event today and closed AGAINST the crowd (down for a short set up).
- Correlation failure (C1): it closed against the crowd while its peers' median close was at least 0.5 of their own
  20-day daily range the crowd's way.
- The move is measured as (close − previous close) / the average true range of the 20 sessions before.

**What an alert contains:** market, direction (fade the crowd), kind (news / correlation / Friday), the event,
entry = today's close (or the next open), stop = a daily CLOSE beyond today's high (short) / low (long), the three
index values and whether the set up is main or close-list, and two LABELS on news alerts:
- *First minute:* the close of the 1-minute bar that starts at the release minute, minus the last bar before it, in
  units of the market's 20-day daily range, signed the crowd's way; "big" at 0.25 or more. Measured on the future's
  own 1-minute bars (the research measured it on ETF minute bars in ETF-range units — not the same number).
- *News vs consensus:* with the crowd / against the crowd / in line / unknown, from actual vs forecast
  (surprise ÷ the series' 2023–2026 typical surprise, in line under 0.25; the research's mapping of which way a
  surprise pushes each market). Central-bank decisions other than the Fed, and WASDE, have no consensus: unknown.

**Friday confirmation:** a market that is a main set up this week and was not last week, with a failure day (N1 or
C1) between the Wednesday after the report date and the release day, whose stop has not since been closed through.
Entry "Sunday open" (or "the next open" in a delayed week), stop = a close beyond the failure day's high / low.
The row stores NO entry price (the open is not known yet; the failure day's close is in `detail`), and is dated the
day the week was first held, so a message retried on a later day updates that row. The check reads this week's
calendar itself (the daily catch-up runs it after the day's calendar read); a failed read is named in the message.
**New install (2026-11-15):** the calendar table holds nothing before its first day, so when the check's window
starts before the earliest stored event date it reads those days from the sources itself — the past US weeks (whole
weeks, same empty-week rule as below), the six central banks, the WASDE dates and the earnings dates — and uses
them for this check only (nothing is stored). A source that cannot be read back is named in the weekly message with
the days ("The Friday check could not read WASDE for 11-11 to 11-16 …"); a refusal earlier in the run sends no
further FXEmpire request. The audit row carries `calendar_backfill` (from, to, stored_from, rows, failed).

**Exit signal in the weekly message:** "left" = was a main set up last week and is not now; "neutral ~50" = the first
week since its last main set up (within 26 weeks) that Commercials (stock indices) or any group (others) is back at 50.

**Sources (all free, read-only):** CFTC public reporting API (legacy futures-only; the yearly history zip as the
fallback); Yahoo continuous futures via yfinance for daily and 1-minute bars; FXEmpire's economic calendar for US
macro, EIA and central-bank decisions (this week re-read every day, three more weeks every Monday); USDA's WASDE
release dates; yfinance earnings dates for NVDA MSFT AAPL AMZN GOOGL META TSLA MU INTC AVGO.

**Tables:** `mi_cot_nets_weekly` (CFTC nets cache), `mi_cot_weeks` (report week, known_from, message sent),
`mi_cot_index_weekly` (report_date, market, comm, lspec, sspec, setup, close_setup), `mi_cot_calendar` (scheduled
events), `mi_cot_alerts` (one row per alert day / market / direction / kind, with entry, stop and the two labels).

**Failure handling:** one market's error never stops the rest: the readable markets alert and send first. Then any
of these raises AFTER the audit row, which pages: ANY set-up market with no bar today or a failed read (nothing
re-reads it; on a weekday the stock market is shut a market with no bar is a quiet no-bar, a failed read still pages), a CFTC fetch that failed,
a calendar source that failed or refused (news alerts may be blind), an undelivered message, or STALE COT data —
no report stored, or the newest stored report more than 17 days old (the CFTC source can keep answering with old
rows; paged on Mondays while it lasts, and the first stale run is always a Monday). A missing peer only drops out
of the correlation median (`peers_unread` in the audit row). An exception anywhere else still leaves the run's one
audit row (FAILED). An undelivered message is retried on the next run; a re-run never sends the same alert twice.

**An empty calendar answer is a failed read (2026-11-15).** An HTTP-200 answer from FXEmpire is taken as real only
when the body is JSON with a `calendar` list and a `last` flag (both are present even for an empty range). A US
WEEK with no trigger row at all — this week's daily read, or NEXT week's in the Monday refresh — is a failed read:
every real week lists the EIA releases (the weeks of 11-09, 11-16 and 11-23 read whole on 2026-11-15 held 2-3
trigger rows each). The stored rows are kept, the reason is in the audit row, and the run pages through its normal
problems path. The Monday refresh replaces each of the three forward US weeks on its own, and only a week whose
answer holds a trigger row; a far week the source does not list yet (it lists ~2 weeks out) replaces nothing.

**A set-up market with no usable price series (2026-11-15, OJ=F).** Yahoo answers ORANGE JUICE with one bar. A
set-up market whose 3-month daily read holds SOME bars but fewer than 21 sessions (the 20 a reading needs, plus
the day) can never alert, so it does not page: the weekly message names it once ("No usable price data for: …"), the weekly and
daily audit rows list it (`no_price_data`), and the daily job skips it. It stays in the index and the set-up list.
An EMPTY answer is never excused (that is also how a rate-limited read looks): it stays a no-bar and pages. The
rule is judged only when some other series in the same run IS usable — if nothing is, the source is down and the
run pages as before. A usable series that only lacks today's bar still pages. Cost, stated: a day on which Yahoo
serves a market 1-20 bars instead of its ~65 is skipped for that market without a page (it is in the audit row).

**Known limits (state them when reading the alerts):**
- The research alert rates were measured on the newsletter's official index (with its small price adjustment). Live
  uses our rebuilt index without it, so a market within a few points of 5 / 95 can be in or out differently.
- **Close basis (OPEN, measured 2026-11-15 in review).** Yahoo restates PAST daily closes to a settlement-like
  value, but the newest bar's close is the last trade near 17:00 (ES 11-12: 7615.25 restated vs 7621.75 last trade;
  ZW 584.25 vs 582.50; GC 3885.3 vs 3881.7). So at 17:15 the job compares today's last trade with yesterday's
  settlement, where the research compared settlement with settlement: a market that settled one side of the prior
  close and traded to the other by 17:00 reads the wrong side. Detection is unchanged (a different close source is
  a rule change). The daily audit row now carries `closes` = each set-up market's close and previous close; one
  day's `close` against the next day's `prev_close` is the size of the gap, and how often the sign of the move flips.
- Yahoo bars can be broken (a close or open outside the day's own high-low; seen on Bitcoin and Coffee). The
  research data has the same rows, so they are judged as they come; the alert says "price bar looks broken" and the
  audit row lists `suspect_bars`.
- The calendar comes from FXEmpire, not the official schedules the research used. Measured in the research
  (2023-08 → 2026-11): it carried CPI 39 of 39, PPI 38 of 39, jobs 39 of 39, retail sales 39 of 42, GDP 37 of 40,
  Fed 26 of 26, EIA petroleum 170 of 172, EIA natural gas 169 of 172. It lists a release only a week or two ahead
  (so this week is re-read every day), and on 2026-11-15 it showed no Bank of Canada / RBA / SNB decision rows
  (those three event names are unverified until one appears).
- A missed day re-run by the job-recovery sweep holds its Telegram (the sweep's summary names it); it does not run
  the weekly catch-up and leaves the alert rows unmarked.
- A federal-holiday week moves the CFTC release; the daily job picks it up the day it lands.

## Change log

### 2026-11-16 — close-to-a-set-up rule rebuilt from his own definition (operator "ok")

**Trigger**: he asked why Natural Gas was not a close set up (Shapiro on Discord 11-16: "close set up"); the alert
listed 0 of his 9 close set ups for the 11-10 report. He then shared the heat-map footnote and ruled "specs shouldn't
be opposite of max".

**Evidence**: `~/cmr_lab/docs/close_rule_study.md` (pre-registered time split, frozen before scoring: fit 2024-03 →
2025-12, 73 issues; holdout 2026, 42 issues; 135 candidates; blind re-computation matched). On the prod (pre-algo)
index, 2026 holdout: old rule catches 20% of his close list (84% of flags on his lists, 2.0 a week); new rule 78% /
92% / 6.8 a week. Large Specs cutoff is a plateau from 15 to 40. Counting 4 off-schedule issues that can never be
scored lowers recall a few points for every rule. The 11-10 week on prod: main list identical to his (5 of 5); close
7 of his 9 (misses Euro, Commercials 94; Heating Oil, Large Specs 19), 1 extra (Platinum).

**Anticipated effect**: the weekly message's close list grows from ~2 to ~7 markets a week and matches his; the daily
job watches those markets too, so news / correlation-failure alerts on close-list markets rise in proportion. No
orders, no sizing. Unintended: more daily bar reads (a dead ticker on a newly listed market pages).

**Reversion-flag**: NEW (replaces the research-approximate "both speculators ≤ 15 / ≥ 85" close rule).

**Status**: built; deploy scope market-agent.

### 2026-11-15 — review fixes: empty calendar answers, the first-run Friday check, a dead price ticker

**Trigger**: verified review findings 2026-11-15 (before the first live Monday run).

**Evidence**: BUG FIXES, not criteria changes — the index window, rounding, lookbacks, contract codes and the feed A
thresholds are untouched. (1) A 200 answer with an empty or renamed body was read as "no events" and deleted the
stored future US rows. (2) On the first run the Friday check could not see last week's news days (the 11-10 report
lands Mon 11-16: its window is Wed 11-11 → Mon 11-16 and the table starts 11-16). (3) OJ=F serves one bar, so a set
up in ORANGE JUICE would have paged every day. Each has a test that fails on the old code
(`tests/test_cot_family.py`, "review fixes 2026-11-15").

**Anticipated effect**: no change on a normal day. A broken calendar answer now pages instead of silently blinding
the news alerts; Monday 11-16's weekly message either carries last week's news failure days or says which days it
could not read; ORANGE JUICE is named in the weekly message and never pages.

**Reversion-flag**: NEW.

**Status**: deployed 2026-11-15 `3af0b701` (market-agent then execution); live since the 11-16 catch-up run.

### 2026-11-15 — live alerts added, no orders (operator "Go")

**Trigger**: his ruling 2026-11-15 — live alerts for the family so the weekly newsletter can score them forward; no orders.

**Evidence**: the live index code reproduces all 120 cells (40 markets x 3 groups) of the 2026-11-03 report from CFTC
data fetched live; feed A, the Friday rule and the two label rules are the research's, unchanged (see Findings). Not a
criteria change — nothing trades. A dry run on real data for 2026-11-09..13 gave 2 alerts (Nasdaq and Wheat on
the 11-10 CPI / WASDE day).

**Review fixes, same day (before any deploy)**: stale COT data pages; any unread set-up market pages after the
others alert; a backlog report is known from the day it lands (back-dating only on the first run); the Friday check
reads the calendar itself and says when it could not; a Friday row stores no entry price and keeps one row across
a retry; broken bars are flagged; the audit row carries the closes that measure the last-trade-vs-settlement gap
(left open, see Known limits).

**Anticipated effect**: one message every Friday evening; about 12 daily alert rows a month if live matches the
research rate (it was measured on the official index, so expect a difference); nothing in the main chat.

**Reversion-flag**: NEW.

**Status**: deployed 2026-11-15 `3af0b701`; first live run 11-16 (`cot_daily` catch-up, 40 markets stored). To revert: remove the two `add_job` blocks in `scheduler.py`; the tables are inert.

### 2026-11-15 — family created (operator)
- Trigger: his words above. Evidence: the research in `~/cmr_lab/docs/` (method.md, index_rebuild.md, step5*.md).
- Nothing runs; no detector, no alerts, no orders.

## Data — 1-minute archive
- What: once a week, one gzip CSV of free 1-minute futures bars (extended hours included; columns market,ticker,ts_et,o,h,l,c,v; timestamps in ET) for every COT market. The ticker list is DERIVED from the family's own market table (`cot_family.MARKETS`), and the pull and the ET conversion are `cot_family`'s (`fetch_minute_frame`, `et_index`) — no second copy. Since 2026-11-15 that means: the dollar index is IN (DX-Y.NYB does serve 1-minute bars — 8,003 rows over 8 days that day; the earlier "no 1-minute history" note was wrong), and OATS (ZO=F) is OUT (the CFTC no longer reports it, so it has no index and no alert to test; 1-minute history not saved cannot be recovered later — say so if oats is wanted back). OPEN: the alerts' first-minute label still skips the dollar index (`NO_MINUTE_BARS`), on the same wrong note; left as is until ruled.
- Where: `/app/logs/cot_minutes/<run_date_ET>.csv.gz` (bind-mounted host dir, survives deploys). Code: `agents/market_intelligence/cot_minutes_archive.py`. Each run fetches the last 8 days, so files overlap; dedupe on (market, ts_et) at read time.
- Schedule: Saturdays 10:00 ET, intelligence-owned, one audit row per run (`cot_minutes_archive`); a run where every ticker fails pages.
- Why: yfinance keeps only ~30 days of 1-minute history; the first-tick news-failure rule needs a true 1-minute test later. Read-only data; no detector, no alerts, no orders.
- Stock / ETF bars (e.g. 1-minute ETF proxies) for this research: `fetch_bars` in `agents/market_intelligence/research_data.py`, run from the market container — it reads Alpaca through apollo-execution's read-only `POST /data/bars` (`docs/architecture/dual_account.md` §Research market data).

### 2026-11-15 — 1-minute archive job added (operator "Go")
- Weekly save of 1-minute futures bars so the first-tick test can run later. Nothing trades off it.
