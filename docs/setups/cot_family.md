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
| `cot_weekly` | Fri 17:40, retry 18:40 | Reads the CFTC report (released Fri 15:30), computes the index for 40 markets (Oats left out: no longer reported), stores the week, sends ONE message: this week's set ups (main rule, and the close list by the research-approximate rule), markets that LEFT a set up or reached neutral ~50 (the exit signal for anyone holding), and the Friday-confirmation alerts. One message per report week; the retry is a no-op once it has gone. |
| `cot_daily` | Mon–Fri 17:15 | For each market set up (main or close list) in the week **known before today**: today's daily bar, today's scheduled events, feed A. ONE message when there is an alert; silence otherwise; one audit row every run. Mon–Thu it first picks up a holiday-delayed CFTC release (and then sends that week's message, entry "the next open"). |

Why after 17:00: the futures daily bar ends at 17:00 ET, and the Friday check needs Friday's bar. The daily job
refuses to run on a bar that is not final.

**No look-ahead.** A week is stored with `known_from` = the ET day we first held it; a day's alerts use the latest
week with `known_from` BEFORE that day (the research's timing: the issue in hand before the session). A week older
than 17 days (the research's 12-day carry past the issue Sunday) is not used.

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

**Exit signal in the weekly message:** "left" = was a main set up last week and is not now; "neutral ~50" = the first
week since its last main set up (within 26 weeks) that Commercials (stock indices) or any group (others) is back at 50.

**Sources (all free, read-only):** CFTC public reporting API (legacy futures-only; the yearly history zip as the
fallback); Yahoo continuous futures via yfinance for daily and 1-minute bars; FXEmpire's economic calendar for US
macro, EIA and central-bank decisions (this week re-read every day, three more weeks every Monday); USDA's WASDE
release dates; yfinance earnings dates for NVDA MSFT AAPL AMZN GOOGL META TSLA MU INTC AVGO.

**Tables:** `mi_cot_nets_weekly` (CFTC nets cache), `mi_cot_weeks` (report week, known_from, message sent),
`mi_cot_index_weekly` (report_date, market, comm, lspec, sspec, setup, close_setup), `mi_cot_calendar` (scheduled
events), `mi_cot_alerts` (one row per alert day / market / direction / kind, with entry, stop and the two labels).

**Failure handling:** one market's error never stops the rest. A day when no set-up market could be read, a CFTC
fetch that failed, a calendar source that failed or refused (news alerts may be blind), or an undelivered message
raises AFTER the audit row, which pages. An undelivered message is retried on the next run; a re-run never sends
the same alert twice.

**Known limits (state them when reading the alerts):**
- The research alert rates were measured on the newsletter's official index (with its small price adjustment). Live
  uses our rebuilt index without it, so a market within a few points of 5 / 95 can be in or out differently.
- Yahoo's daily close is the last trade, not the exchange settlement; a close within a tick of the previous close
  can read the wrong side.
- The calendar is thinner than the research's: FXEmpire lists a release only a week or two ahead and, on
  2026-11-15, showed no Bank of Canada / RBA / SNB decision rows (those names are unverified until one appears).
- A federal-holiday week moves the CFTC release; the daily job picks it up the day it lands.

## Change log

### 2026-11-15 — live alerts added, no orders (operator "Go")

**Trigger**: his ruling 2026-11-15 — live alerts for the family so the weekly newsletter can score them forward; no orders.

**Evidence**: the live index code reproduces all 120 cells (40 markets x 3 groups) of the 2026-11-03 report from CFTC
data fetched live; feed A, the Friday rule and the two label rules are the research's, unchanged (see Findings). Not a
criteria change — nothing trades. A dry run on real data for 2026-11-09..13 gave 2 alerts (Nasdaq and Wheat on
the 11-10 CPI / WASDE day).

**Anticipated effect**: one message every Friday evening; about 12 daily alert rows a month if live matches the
research rate (it was measured on the official index, so expect a difference); nothing in the main chat.

**Reversion-flag**: NEW.

**Status**: built, not deployed. To revert: remove the two `add_job` blocks in `scheduler.py`; the tables are inert.

### 2026-11-15 — family created (operator)
- Trigger: his words above. Evidence: the research in `~/cmr_lab/docs/` (method.md, index_rebuild.md, step5*.md).
- Nothing runs; no detector, no alerts, no orders.

## Data — 1-minute archive
- What: once a week, one gzip CSV of free 1-minute futures bars (extended hours included; columns market,ticker,ts_et,o,h,l,c,v; timestamps in ET) for every COT market (the `=F` continuous contracts; the dollar index is skipped, it has no 1-minute history).
- Where: `/app/logs/cot_minutes/<run_date_ET>.csv.gz` (bind-mounted host dir, survives deploys). Code: `agents/market_intelligence/cot_minutes_archive.py`. Each run fetches the last 8 days, so files overlap; dedupe on (market, ts_et) at read time.
- Schedule: Saturdays 10:00 ET, intelligence-owned, one audit row per run (`cot_minutes_archive`); a run where every ticker fails pages.
- Why: yfinance keeps only ~30 days of 1-minute history; the first-tick news-failure rule needs a true 1-minute test later. Read-only data; no detector, no alerts, no orders.
- Stock / ETF bars (e.g. 1-minute ETF proxies) for this research: `fetch_bars` in `agents/market_intelligence/research_data.py`, run from the market container — it reads Alpaca through apollo-execution's read-only `POST /data/bars` (`docs/architecture/dual_account.md` §Research market data).

### 2026-11-15 — 1-minute archive job added (operator "Go")
- Weekly save of 1-minute futures bars so the first-tick test can run later. Nothing trades off it.
