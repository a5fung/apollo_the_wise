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
  units of the market's 20-day daily range; stored signed the crowd's way, printed in price terms (up / down); "big" at 0.25 or more. Measured on the future's
  own 1-minute bars (the research measured it on ETF minute bars in ETF-range units — not the same number).
- *News vs consensus:* stated for the market (bullish / bearish Silver, in line with forecast, no clear read), from actual vs forecast; the stored class stays WITH / AGAINST the crowd (since 2026-11-25 the alert text, `news[].fact` / `news[].read` and the news-watch sentence carry the price-terms reading, and the crowd is named once, in the set-up line)
  (surprise ÷ the series' 2023–2026 typical surprise, in line under 0.25; the research's mapping of which way a
  surprise pushes each market). Central-bank decisions other than the Fed, and WASDE, have no consensus: unknown.
  *In plain words (2026-11-27):* every news line says WHOSE release and WHICH one with its period ("US GDP (Q3, second
  estimate)", "Australia CPI inflation (October)"), the FIGURES (actual vs forecast, previous; each series' own way:
  stronger / hotter / as forecast, unemployment above forecast = weaker), and WHY it is bullish / bearish for this market
  in one chain ("stronger US growth lifts US interest rates and the US dollar against the New Zealand Dollar → bearish New
  Zealand Dollar"). The chain comes from `cot_family.WHY`, keyed (event family, market group); each entry declares the sign
  it explains and must equal `news_sign` (a test walks every pair the calendar can attach). A pair with no read (news_sign 0
  or no mapping) and an in-line surprise state the fact and give no reason. Stored per item in `detail.news[]`: `country`,
  `release`, `series`, `surprise`, `why`, `text`. A non-US release (Australian CPI, a central bank) prints its figures off
  its own country page with no read. The Friday confirmation names the releases (no figures: it reads none).
  Fed minutes, RBA minutes, Australian jobs (Employment Change) and Australian wages (Wage Price Index QoQ) are
  watched news days too (2026-11-17) with no consensus read: unknown.
  Added 2026-11-22: **PCE** carries a consensus read (the four PCE price series, mapped like CPI); **Australian CPI**
  (Inflation Rate MoM on the Australian page), **OPEC+ meetings** and **USDA weekly export sales** have none: unknown.
  An OPEC+ meeting has no release minute, so its first-minute label reads "no release time".

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

**News watch scoring (2026-11-25, his ruling "news to watch for and what's expectation, once news is here, we assess vs expectation"):**
the judged row's news read, verdict and `strict` are scored against the LINED-UP forecast: the frozen pre-release figure
(`series[].forecast` / `forecast_seen_at`), never the figure the source lists after the release (`forecast_after`). If no
pre-release figure was ever stored the release-day read stands and the card labels it "forecast read after the release". In a mixed event (some series stored, some not) only the stored-forecast series are scored; the others are marked "(not scored: no forecast lined up)".
The card prints the figure it was scored on and, when the after-release figure differs, a second small note; where the alert
label (`mi_cot_alerts.news_class`, release-day read, unchanged) differs, one short line says so (it claims a "release-day forecast" only when a stored forecast exists and the later figure differs; otherwise it says the alert label was a day-level read, since two releases can share a day). A row left `pending` (no bar
at the 17:15 run) is judged again by the next runs within the 7-day window once a bar exists. A watch error never pages; its
count is on the audit summary line ("NEWS WATCH ERRORS n") and the page captions a null `news_watch_asof`.

**News watch (2026-11-25, display only):** his ask — *"What Shapiro does is watch for news failure, so ideally we'll have
news lined up already, so setup or close setup should expand for news to watch for and what's expectation, once news is
here, we assess vs expectation, bullish v bearish, and market action after it"* — makes a set-up or near-set-up card
expandable. Spec and the fork list: `docs/design/cot_news_watch_2026-11-25.md` (a finding, not an owner; THIS section
owns the rules). Table `mi_cot_news_watch`, one row per (session day, event, market), written by the two existing jobs
and read by nothing that alerts, trades or sizes: `detect()`, the alert rule and the Telegram messages are unchanged.
- **Before a release** (every `cot_daily` run, next 7 days, the newest stored COT week; `cot_weekly` rebuilds the same
  rows when it stores a week, with no calendar request): the forecast and prior as the source lists them, and one plain
  sentence written in Python from `news_sign` x the crowd — e.g. "Crowd is SHORT Silver. News that favours the crowd:
  jobs stronger than forecast (payrolls above 82.0K, unemployment below 4.2%) = bearish Silver. Failure to watch for:
  that news, a first move down, then a close UP." The favouring side is `crowd_sign(direction) * news_sign`; a test
  pins that the sentence and `news_class` agree for every mapped pair. Three kinds of event: **A** forecast + crowd read
  (US macro, Fed decision, EIA, earnings), **B** forecast shown, no crowd read (Australian data, other central banks,
  any pair `news_sign` calls ambiguous — NOT upgraded to a read here: that needs a frozen typical-surprise number and a
  mapping from the research), **C** no forecast (WASDE, OPEC+, export sales, minutes).
- **The forecast is frozen at the release:** a read made BEFORE `release_et` that carries a figure refreshes `forecast`
  and stamps `forecast_seen_at` (so the stamp is the LATEST pre-release read, not the first); a blank read never erases;
  a read at or after the release only fills `actual` and keeps the figure then listed apart, as `forecast_after`.
- **After a release** (judged in the 17:15 run, for every set-up or near-set-up market with an event today, alert or not,
  on the week known BEFORE today — the week the alert used): three steps — (1) actual vs forecast -> bullish or bearish
  -> with or against the crowd, (2) the first minute, (3) the close vs the crowd — and a verdict. The news read, first
  minute and close are the SAME values the alert label uses. `strict` = the three-step rule (news favours the crowd, first
  minute their way by more than 0.01 of a day's range, close against); `alerted` = a news alert row exists (the live rule:
  any event + a close against). Both are stored on every row, so the strict-vs-live comparison builds itself, including
  the days no alert fired. `strict` is per EVENT row (two releases on one day are two rows): count a market-day as strict
  when ANY of its rows is, and as alerted when any is (the alert is per market-day). Verdicts: `failure_full`, `failure`, `followed_news`, `against_unread`, `shrugged`,
  `no_failure`, `pending` (table in the design doc §1.3).
- **Extra reads:** one more FXEmpire request a weekday (next week's US page, so a Friday card holds its own figures; its
  trigger rows replace that week's stored ones only when the answer holds one — an empty or failed read is recorded, never
  paged), reused from the Monday refresh on a full-refresh day; a non-US event today adds that country's page for its
  actual; one 1-minute pull per set-up market with a timed event today (shared with the alert label); yfinance earnings
  rows for the tickers involved. They run AFTER the alert path, each part in its own try: a failure is recorded in the
  audit row (`news_watch.errors`) and changes no alert, message or outcome.

**Sources (all free, read-only):** CFTC public reporting API (legacy futures-only; the yearly history zip as the
fallback); Yahoo continuous futures via yfinance for daily and 1-minute bars; FXEmpire's economic calendar for US
macro, EIA, Fed minutes, central-bank decisions and the Australian minutes / jobs / wages (this week re-read every day, three more weeks every Monday); USDA's WASDE
release dates; yfinance earnings dates for NVDA MSFT AAPL AMZN GOOGL META TSLA MU INTC AVGO. Since 2026-11-22 the
same FXEmpire pages also give PCE (US page, re-read every day) and Australian CPI (Australian page, Monday refresh),
and two sources are NOT read from the network: **OPEC+ meetings** are a dated table in the code
(`OPEC_MEETINGS`, each date as announced in an opec.org press release) and **USDA weekly export sales** is a rule
(Thursday 8:30 ET; Friday in a federal-holiday week). Neither schedule could be read by a script on 2026-11-22
(opec.org and www.fas.usda.gov answered 403; two guessed apps.fas.usda.gov paths answered 404).
Their rows are written by the Monday refresh (or when the last full refresh is over a week old).

**STANDING STEP — every weekly CMR scoring (operator 2026-11-22: *"yes, we should continually expand our news
failure sources"*).** When a week's issue is scored, list EVERY event he names as a news-failure trigger that our
calendar does not carry (`EVENT_MARKETS` is the list of what it carries), and add each one the same way, that week:
1. Find the source: the exact served name on the FXEmpire page for its country (read it from a stored answer under
   `scripts/probes/` or one polite fetch), else an official schedule, else a dated table or a rule with its source
   named in the code.
2. Add the type: its markets (`EVENT_MARKETS`), its name (`FX_US_TRIGGERS` / `FX_COUNTRY_EVENTS`) and its release
   time (`RELEASE_CONVENTION`).
3. Consensus read ONLY when a frozen typical-surprise number already exists in `~/cmr_lab`
   (`data/event_surprises_components.csv`) and the research's mapping covers the type; otherwise it reads unknown.
   Never fit a new number for the label inside this step.
4. Tests (markets, time, class, the parse from a real answer), a change-log entry here (NEW, trigger = the issue
   date), and the open list below when a source could not be confirmed.
The dated OPEC+ table is part of this step: a test fails once its newest meeting is more than 21 days past (the seven-country meeting is monthly, so a longer
wait could let a meeting pass unseen). It is a wall-clock TEST only: nothing in production says the table has no
meeting ahead. With only 2026-11-29 in it, it goes red on 2026-12-21 unless the next date is added.

**Tables:** `mi_cot_nets_weekly` (CFTC nets cache), `mi_cot_weeks` (report week, known_from, message sent),
`mi_cot_index_weekly` (report_date, market, comm, lspec, sspec, setup, close_setup), `mi_cot_calendar` (scheduled
events), `mi_cot_alerts` (one row per alert day / market / direction / kind, with entry, stop and the two labels),
`mi_cot_news_watch` (the news watch above: one row per session day / event / market).

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
- **OPEC+ meetings are a hand-kept table** (one announced date at a time). An extraordinary meeting, or a date moved
  after the announcement, is not seen until the table is edited. The seven-country monthly meeting and the full
  ministerial meeting are not told apart: every announced date is one OPEC day for crude oil, heating oil, gasoline.
- **USDA weekly export sales is a rule, not a read.** FAS states: Thursdays 8:30 ET unless a change is announced, and
  Friday when the Monday or the Friday before is a national holiday. INFERRED (not on the FAS page as we read it): a
  holiday on the Tuesday, Wednesday or Thursday also moves it to Friday — Thanksgiving week 2026 gives Fri 11-27, the
  date in his issue; the rule's 2024 output (Fri 06-21, Fri 07-05, Fri 12-27) matches what we recall of that year but
  was not checked against a FAS page. OUR OWN GUESS, from no source: when that Friday is itself a federal holiday
  the rule takes the next working day (first case: New Year's Day, Fri 2027-01-01 → Mon 2027-01-04 — check that
  week against FAS before trusting it). A change FAS announces on its own (a shutdown week) cannot be seen.
- A missed day re-run by the job-recovery sweep holds its Telegram (the sweep's summary names it); it does not run
  the weekly catch-up and leaves the alert rows unmarked.
- A federal-holiday week moves the CFTC release; the daily job picks it up the day it lands.

## Change log

### 2026-11-27 — news lines say whose release, the figures and why (operator: "what GDP, US GDP or Australia GDP, why is it bearish ... compare to what")

**Trigger**: his 11-27 screenshot of the 11-25 SILVER and NEW ZEALAND DOLLAR tiles reading "GDP bearish Silver" with no
country, figure or reason. His 11-25 ruling stands: state the fact, read it bullish / bearish for the asset, the crowd named once.

**Evidence**: none needed — words only. `news_sign`, `SURPRISE_COMPONENTS`, `news_class`, `detect()`, the alert rule and
every threshold are unchanged; the chain is derived from the same sign. Checked on the 11-25 FXEmpire rows
(`scripts/probes/_cot_newswatch_design_1125/nw_fx_1123_1206.json`): GDP 4.3% vs 3.5% gives z 2.954, the stored value; PCE
z 0.312 comes from core PCE y/y 3.3% vs 3.2% alone (the other three on forecast), which the line now shows.

**Anticipated effect** (BASELINE: "GDP: growth stronger than forecast (GDP Growth Rate QoQ 2nd Est 4.3% vs 3.5%) = bearish
Silver" in Telegram; "GDP bearish Silver" on the page): Telegram, `detail.news[]`, the news-watch sentence and the page
print the release with its period, the figures and the chain. Old alerts (the 14 in the 11-26 snapshot) get country,
release and why from the nightly export, and NO figures: the job never stored them (except the nine 11-25 alerts, see the review fixes below) (`detail.news[]` held only event / z /
class / first minute and no news-watch row exists for 11-25). One more FXEmpire read per run only on a day a set-up market
alerts on a non-US release, and the news watch reuses it (no new request on those days in total).

**Review fixes (same day)**: US GDP prints as "GDP q/q annualized" (FXEmpire's US quarterly rate is the annual pace: 4.3%
is not 4.3% in one quarter). "Previous" is the source's `revised` figure when it lists one (11-25 PCE y/y: previous 3.7%,
revised 3.6% → 3.6%), on the alert and on the news-watch card (a revision arriving with the release replaces the stored
previous). A figure's own word is not repeated before a chain that opens with it ("4.3% vs 3.5% forecast → stronger US
growth ...", not ": stronger → stronger ..."); when the figures came out different ways (CPI m/m hotter, y/y cooler) each
keeps its word and the chain reads "on balance hotter US inflation ...". The nine 11-25 alerts CAN get their figures (built, not yet run on prod): the raw
11-25 rows survive in the probe file above and reproduce every stored class and z (16 of 16 items), so
`cot_family.fill_news_item_from_fx` rebuilds country / release / series from them (refusing any item they do not
reproduce) and `scripts/probes/_cot_newsfacts_backfill_1127/backfill_1125.sql` writes them (stored keys win; `why` stays
the export's; aborts unless 9 alerts / 16 items change; dry-run on a local Postgres 16: 9 / 16, a rerun changes nothing,
a tampered z aborts).

**Reversion-flag**: NEW (additive words). **Status**: built, not deployed; scope `market-agent` only (`cot_family.py` is
not in `scripts/exec_loaded_modules.txt`; `db.py` untouched) plus a server `git pull` for the SQL, then a portfolio-app2 push.

### 2026-11-25 — news watch: each set-up card lists the news to watch for and its verdict (operator "Ok", display only)

**Trigger**: his 11-25 ask quoted under "News watch" above, plus his "Ok" to testing the design doc's stricter
news-failure rule (news favours the crowd, first reaction the crowd's way, close against) against the live looser one.

**Evidence**: none needed — display and labels only; no detection criterion, threshold or alert rule changes, so no
backtest. The forecast figures come from the same FXEmpire rows the job already read and threw away (read 2026-11-25:
NFP Fri 12-04 lists 82.0K / 4.2% nine days ahead; EIA stock figures were blank a week ahead).

**Anticipated effect** (BASELINE: no `news_watch` key in the snapshot, set-up cards do not expand, a news day with no
alert stores nothing, forecasts are never stored): cards of markets with an event in the window expand to the forecast and
the sentence; judged rows exist for no-alert days too; `detect()`, `_alert_row`, the messages and every threshold are
byte-identical; the added requests are listed under "Extra reads". EXPECT / DONE-WHEN / WOULD-FAIL-IF: design doc §5.

**Reversion-flag**: NEW (additive). Not deployed at the time of writing; scope `market-agent` AND `execution` (`db.py` is in
`scripts/exec_loaded_modules.txt`, so a market-agent-only deploy leaves the execution service on the old `db.py`; the table is
created by `initialize_schema()` at market-agent boot), then a portfolio-app2 push.

### 2026-11-22 — four more watched news events: PCE, Australian CPI, OPEC+ meetings, USDA weekly export sales (operator "yes, we should continually expand our news failure sources")

**Trigger**: his 11-22 issue named four events our calendar did not carry — US PCE (11-25), Australian CPI (11-24
evening ET), the OPEC+ meeting (11-29) and USDA weekly export sales for Soybean Oil (11-27). His ruling the same day:
keep expanding the sources (the STANDING STEP under "Sources" above).

**Evidence**: no detection threshold changes; these are calendar additions.
- PCE: `PCE Price Index MoM` on the FXEmpire US page — 4 rows = 4 releases in the stored answer of 2026-11-17
  (`scripts/probes/_cot_events_1117/united-states.json`, 2026-07-20 to 2026-11-20), all 8:30 ET. One fresh read of
  the US week of 11-23 (2026-11-22) lists it for Wed 11-25 at 8:30 ET, forecast 0.3%, and lists no export sales or
  OPEC row. The Australian page was not re-read. Consensus read: the research already holds a frozen typical surprise for the four PCE price series
  (`~/cmr_lab/data/event_surprises_components.csv`, 39 releases 2023-08-31 → 2026-10-29: 0.0531085 / 0.0599145 /
  0.0767948 / 0.0800641) and maps PCE with CPI and PPI (`surprise_rules.py` INFL), so PCE is read like CPI.
  ⚠ The research did NOT count PCE as a news-failure trigger (it scored PCE days only as extra events); this adds it
  on his issue, not on that study.
- Australian CPI: `Inflation Rate MoM` on the Australian page (same stored answer: 4 releases, 11:30 Sydney; the
  quarterly rows come out the same day). No frozen typical surprise exists: unknown.
- OPEC+: opec.org answered 403 to a script. One announced date, 2026-11-29, from the opec.org press release of
  1 November 2026 ("The next meeting will be held on 29 November 2026",
  https://www.opec.org/pr-detail/620-1-november-2026.html). A Sunday meeting is Monday's session (11-30).
- USDA weekly export sales: www.fas.usda.gov answered 403 to a script; a rule (see Known limits for what is stated,
  what is inferred and what is our own guess). His issue named it for Soybean Oil only; Soybeans, Soybean Meal, Corn
  and Wheat are added because the same report covers them.

**Anticipated effect** (alerts only; no orders, no sizing):
- **Every Thursday (Friday in a holiday week) becomes a news day for five grain markets** — the largest change: a
  set-up grain market that closes against the crowd on that day now alerts as a news failure (before: only on
  WASDE days, about one a month, or through its peers).
- PCE: about one more news day a month for every US macro market (stock indices, bonds, currencies, metals, crypto).
- Australian CPI: about one more Australian Dollar news day a month. OPEC+: about one more a month for crude oil,
  heating oil and gasoline, on the dates in the table.
- The Friday confirmation sees the same extra news days.
- Existing event types are unchanged. Four existing tests changed on purpose: (1) `test_market_table_is_whole` no
  longer forbids a PCE type (ISM still forbidden); (2) `test_calendar_rows_take_exact_names_only` used
  `PCE Price Index MoM` as its "not read" example — now `PCE Prices QoQ Adv`; (3) the first-run Friday check names
  Thu 11-05 as "WASDE, USDA EXPORTS"; (4) a WASDE-blind first run still finds that Thursday through the export
  sales rule (one Friday alert where there was none).

**Reversion-flag**: NEW (additive; the existing events are untouched).

**Status**: built on branch `cot-news-sources`, not deployed; deploy scope market-agent. The OPEC+, export sales and
Australian CPI rows are written by the next full calendar refresh (Monday's 17:15 run, before that day's alerts are
judged); PCE comes with the daily read. So this week's Australian CPI (session Wed 11-25) and export sales (Fri 11-27)
are watched only if it is deployed before Mon 11-23 17:15 ET; PCE needs it before Wed 11-25 17:15 ET.

### 2026-11-17 — four more watched news events: Fed minutes, RBA minutes, Australian jobs, Australian wages (operator "go")

**Trigger**: his 11-16 issue named RBA minutes, Australian wages, Fed minutes and Australian employment as
news-failure triggers for AUD; our calendar watched rate decisions only.

**Evidence**: names read from the live FXEmpire answers 2026-11-17 (`scripts/probes/_cot_events_1117/`, 2026-07-20 to
2026-11-20): `FOMC Minutes` (US page, 3 releases, 14:00 ET), `RBA Meeting Minutes` (3), `Employment Change` (5, one
row per release; the Full Time / Part Time / Unemployment / Participation rows are not read) and `Wage Price Index
QoQ` (2; the YoY row is not read), all on the australia page already read for the RBA decision. Types FED_MINUTES
(same markets as the other US macro types), RBA_MINUTES / AU_JOBS / AU_WAGES (Australian Dollar). Release times by
convention: 14:00 New York, 11:30 Sydney. The country map is now name -> type per country; existing types unchanged.

**Anticipated effect**: news alerts on Australian Dollar rise on the roughly 3 AU release days a month beyond the RBA
decision, and the Fed-minutes day (~8 a year) is a news day for every US macro market. These types carry no
actual-vs-consensus read, so their news label reads "unknown". No orders, no sizing.

**Reversion-flag**: NEW (additive; the existing events are untouched).

**Status**: built; deploy scope market-agent.

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
