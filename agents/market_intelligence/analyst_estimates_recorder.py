"""2026-08-31 — #333 ANALYST-ESTIMATES RECORDER (the sourcing backbone's 60-day clock).

Pradeep's durability test is FORWARD: ~2 quarters realized PLUS ~4 quarters projected of
high revenue growth. The rubric can only score the trailing leg because we have never
stored a single analyst estimate — #333's build gate is this backbone plus >=60 days of
stored estimates, and the clock starts when this module's first snapshot lands.

THE LINE — read before touching anything here. DATA CAPTURE ONLY:
  - Writes EXACTLY ONE table: `mi_analyst_estimates` (+ `mi_audit_log` via the shared
    `log_audit_event` telemetry helper — never a trade-state table).
  - No rubric axis, no scoring change, no admission change lives here. The #333 axis
    itself needs operator sign-off + CHANGE_PROCESS long after this capture.
  - Read by NO grading / entry / sizing / ordering / safeguard path.
  - Never touches the 09:45 ET scan path — this is an EOD scheduled job (18:12 ET).
  - SILENT: no Telegram on any path. Errors degrade to mi_audit_log + logs; the
    detector-liveness registry (health_checks._DETECTOR_LIVENESS_TABLES,
    mi_analyst_estimates) is the watchdog for a silently-dead writer.

FMP IS GONE FROM THIS JOB (2026-10-16). The annual leg used to call FMP
/stable/analyst-estimates. On the free tier that endpoint serves about 1 ticker in 12
(the `symbol` allow-list, plus `limit` must be 0-10 — measured 2026-09-03), so every other
name wrote an `api_failure_fmp` row (21-26 a night since 10-07; 22 on 10-12) plus one
`analyst_estimates_plan_change` row a night, for no estimate (the one read of the table,
2026-09-04, found 144 rows, all yfinance/quarter, none from FMP). The operator's ruling
2026-09-03 ("start with what
yfinance gives ... re-test at 60 days") makes yfinance the source of record, Finnhub the
cross-check. The FMP leg, its pacing, its 402 handling and its `plan_change` alarm are
DELETED, not flagged off. Consequences, stated so nobody has to rediscover them:
  - THE ANNUAL LEG WAS REPLACED, NOT DROPPED. It was FMP's and only FMP's; it is REBUILT on
    yfinance in the same deploy as the FMP removal (Sat 2026-10-17), so no night runs
    without an annual leg (his ruling 2026-09-03: "two forward quarters PLUS THE ANNUAL") —
    see "THE ANNUAL LEG IS YFINANCE TOO" below. Nothing FMP-shaped came back with it.
  - The ~24s-per-ticker FMP sleeps were also the only thing spacing the yfinance scrapes.
    That cadence is kept, explicitly, as YFINANCE_PACE_SECONDS (enforced in the run loop) so
    this change alters no vendor's request pattern. Lowering it is a separate, measured
    decision.
  - `source='fmp_stable'` / `period_label_method='vendor_reported'` rows already stored stay
    valid history; the schema default and CHECK in db.py are untouched on purpose.
  - Row shape and meaning are unchanged for every row this job still writes, so
    RECORDER_VERSION does not move.
  - scheduler.py's job docstring/comments still say "FMP": left alone deliberately —
    scheduler.py is loaded by apollo-execution, so even a comment edit would drag a
    money-path service into the deploy.
`collector._fmp_get` (and FMP_API_KEY) now have NO live caller anywhere in the repo.

THE HONESTY CONSTRAINT (this decided the whole design). Estimates are point-in-time:
what a vendor returns today for a future period is TODAY'S consensus — stamping it onto a
past alert date is lookahead, the defect class that invalidated the 08-25 structure
study. But there is a genuine, bounded backfill (operator-identified): an estimate for a
future period persists until that period's results land, so today's read IS the estimate
that stood on any date since THAT TICKER'S most recent filing. Hence every row stores:
  as_of_date         the date the value was READ (never inferred by a future reader)
  anchor_filing_date the ticker's most recent 10-Q/10-K-class filingDate at read time
  valid_from_date    = anchor_filing_date (or as_of_date when no anchor resolves —
                       NEVER claim history without an anchor; CHECK-enforced)
The backfill window is PER TICKER, back to its own last filing — never a flat lookback.
Measured on the real alert population (2026-08-31, SEC EDGAR filing dates, 306/335
alert tickers resolved): mean reach 28 days, median 25 — BELOW the ~45-day estimate,
because the measurement ran just past earnings season; the reach is cyclical and grows
toward ~45+ mid-cycle. `docs/analysis/analyst_estimates_backfill_reach_2026-08-31.md`.

NO-ANCHOR IS A FIRST-CLASS OUTCOME, NEVER AN ABORT (v2, 2026-09-01). The first live
run (2026-09-01 18:12 ET) wrote 0 rows with 99 errors: FMP's /income-statement — v1's
filing-date anchor — is 402 Payment Required on our plan, and v1 treated an anchor
fetch failure as a ticker-killing exception. Wrong shape: a ticker whose filing date
cannot be resolved must still record its estimates with a ZERO honest window
(valid_from_date == as_of_date) and be counted — `honest_valid_from` already encodes
that; only the orchestration aborted. NEVER invent or approximate a filing date to
widen a window — no anchor means no claimed history, full stop.

THE ANCHOR SOURCE IS SEC EDGAR (v2, 2026-09-01) — the authority FMP's filingDate is
derived from, keyless and $0, so no payment tier can take it away again:
  https://www.sec.gov/files/company_tickers.json        ticker -> CIK (1 call/run, cached)
  https://data.sec.gov/submissions/CIK##########.json   filings.recent, newest-first
Anchor = the MOST RECENT filing among ANCHOR_FORMS (10-Q/10-K/20-F/6-K + /A) — the
same conservative bound as before: the filing lands at or after the results release,
so anchoring on it claims FEWER days, never more. yfinance earnings dates were probed
and REJECTED: they are ANNOUNCEMENT dates (at-or-before the filing), so anchoring on
them would WIDEN the window — the forbidden direction. The 08-31 reach measurement
used this exact EDGAR path and resolved 306/335 real alert tickers; the unresolved 29
are ETFs/preferreds/non-filers, which buy zero days BY DESIGN. SEC asks for a
declared User-Agent (collector._SEC_UA, `SEC_USER_AGENT` env) and <=10 req/s; the run pace
is ~4 req/s worst case.

RAW VALUES, NEVER A COMPUTED SCORE: thresholds belong to today's rule set; a stored
score goes stale the moment one is swept. The sketch's n_analysts<3 -> None rule is
applied READ-SIDE (`estimate_for_scoring`, threshold parameterized) and the count is
stored, so the rule can be re-tuned without re-fetching.

SOURCES (estimates: yfinance primary + Finnhub calendar; anchor: SEC EDGAR, above):
  yfinance revenue_estimate / earnings_estimate / earnings_dates   the 0q/+1q rows AND (since
                                              2026-10-16) the 0y/+1y annual rows, all with
                                              analyst counts — the only source the
                                              n_analysts<3 rule can admit
  Finnhub /calendar/earnings                  free; forward EPS + revenue, NO count
  SEC EDGAR submissions                       the honest-window anchor + cadence facts
  FMP /income-statement, /earnings            402 on our plan (verified live 2026-09-01,
                                              99/99 tickers) — NEVER call
  FMP /analyst-estimates                      WAS the annual leg; removed 2026-10-16 (above)
COST: $0 — no paid plan is touched. Per ticker per run: 3 yfinance calls (fetched
concurrently — the annual rows ride the SAME two estimate frames, 0 extra), 1 Finnhub call, and 0 extra EDGAR calls (the cadence facts are parsed from
the SAME submissions payload the anchor already fetched) + 1 EDGAR ticker-map call per run.
The daily population (live-source EP alerts, trailing 30 days) is ~20-100 tickers. The
one-shot backfill over the full alert population (~335 tickers) is ~1,300 calls, once.

CREDENTIALS: Finnhub authenticates by QUERY STRING (`?token=`), exactly as FMP did — and
FMP's raw exception text carried the live key into 99 audit rows on 2026-09-01.
`db.log_audit_event` redacts at the chokepoint; every log line here that formats an
exception goes through `redact_secrets` too, so a key never lands in container logs either.

THE QUARTERLY LEG IS YFINANCE (v3, 2026-09-02) — operator-approved after the pacing
root-cause: FMP's `period=quarter` is not on any FMP plan and never will be for
free; `yf.Ticker(t).revenue_estimate` / `.earnings_estimate` give '0q'/'+1q' rows
(avg/low/high/numberOfAnalysts) for $0, no key, already a dependency. Rows land in
the SAME `mi_analyst_estimates` shape the annual leg uses (period_type='quarter'
was already a valid value in the CHECK constraint) — `source` (already a column,
default 'fmp_stable') is set to 'yfinance' so a future reader can tell the two
vendors apart without guessing. No schema change was needed.

THE HARD PART: yfinance's periods are RELATIVE ('0q' = whatever quarter hasn't
reported yet, '+1q' = the one after). A stored row needs an ABSOLUTE
period_end_date or two different runs could both call themselves "the Q3
estimate" while meaning different quarters. REJECTED: anchoring on SEC EDGAR's
last-reported quarter end (reportDate, already fetched for anchor_filing_date —
see quarterly_cadence_facts) and adding a fixed 3 calendar months. Verified
empirically on real EDGAR data: AAPL's 52/53-week calendar only drifts +/-1 day
per step, but COST's 4-4-5 retail calendar missed the correct MONTH outright
(Sept 1 + 3mo = Dec 1; the real next quarter end was Nov 24) — not a rounding
error, a wrong quarter, which is exactly the guessed-date failure THE HONESTY
CONSTRAINT forbids.

CHOSEN (resolve_quarterly_period_ends): anchor '0q' on yfinance's OWN next
scheduled earnings date (next_earnings_date_from_yfinance, from `earnings_dates`
— a real, ticker-specific, always-current value: it moves in lockstep with
whichever quarter revenue_estimate/earnings_estimate currently label '0q'
because both come from the same live system) minus this ticker's OWN observed
RELEASE lag (last_actual_release_date, also from `earnings_dates`, MINUS SEC
EDGAR's last_reported_quarter_end — release compared to release, never release
compared to a filing date, per the house rule of never mixing two vendors'
different event types as if they measured the same thing). '+1q' = '0q' + this
ticker's OWN observed quarter length (last_reported_quarter_end -
prior_reported_quarter_end, an EDGAR-to-EDGAR, same-vendor comparison). Both
offsets are MEASURED facts about this ticker, never a fixed assumption — checked
against AAPL/COST/WMT during design and landed within roughly a week of the true
period end (NOT a tighter "0-2 day" precision — an earlier draft of this design
claimed that from a filing-lag formula that turned out to measure a DIFFERENT
lag than the one it was applied to; see resolve_quarterly_period_ends' own
docstring for the residual this version still carries: a company's Q4/FYE report
often releases later than a regular quarter's, so a lag measured off a regular
quarter under-estimates the FYE transition by roughly a week). This design also
closes the "reporting gap" race (a company's earnings RELEASE can precede its
formal 10-Q/10-K FILING by up to ~40 days; during that window EDGAR's anchor is
one quarter stale) MORE ROBUSTLY than the rejected filing-lag version: comparing
release-to-release, a stale-anchor mismatch inflates the measured lag by roughly
a full quarter-length, which _MAX_RELEASE_LAG_DAYS (75) reliably rejects — the
ticker is skipped and counted for that day rather than mislabeled.

DAY-TO-DAY STABILITY (stabilize_period_end, added after a second design review
caught that the above resolves a DIFFERENT, still-open problem — see next
paragraph). resolve_quarterly_period_ends' inputs are LIVE: next_earnings_date
can shift a few days as yfinance's own estimate refines, and the release
lag / quarter length can swing whenever a NEW SEC filing lands. Recomputing from
scratch every day would mint a slightly different period_end_date for the SAME
fiscal quarter — a NEW primary key — fracturing the very revision series this
table exists to build. Before storing, snapshot_ticker checks
db.get_recent_quarterly_period_ends (this ticker's own already-stored quarter
dates, `source='yfinance'`) and stabilize_period_end REUSES an existing date
within tolerance rather than minting a new one. This — not a calendar heuristic
like snapping to the nearest month-end, which was tried and rejected: it fixes
calendar-aligned filers (AAPL, WMT) but systematically MISDATES a true 4-4-5
retailer like COST, whose real quarter ends sit 1-3 weeks from any month
boundary — is the only fix verified to hold for both filer types, because it
compares against this ticker's OWN recorded history instead of any general rule.
The FINNHUB quarter rows get the same treatment (2026-10-17, #333): their stored
period_end_date is stabilized against that ticker's own Finnhub history
(`source='finnhub_calendar'`, one read per ticker per run), never against yfinance's.
See "FINNHUB ROWS ARE STABILIZED TOO" below.

Sanity-bounded, never a guess passed off as data: an out-of-range lag or quarter
length, or a computed '0q' that doesn't fall after the last reported quarter,
returns None for that period. QUARTERLY_CADENCE_FORMS (10-Q/10-K only, narrower
than ANCHOR_FORMS) excludes 20-F/6-K foreign-filer forms — annual-only/irregular
filing cadences can't support this lag/length arithmetic. Any ticker that cannot
resolve a period this way has that period SKIPPED and COUNTED
(quarter_yf_no_cadence) — never stored against an invented date.
⚠ EXPECT A NONZERO quarter_yf_no_cadence BASELINE EVERY NIGHT, NOT JUST ON A BAD
RUN: on any given day some slice of the population is genuinely mid reporting-gap
(released, not yet filed — see above), and the rejection there is CORRECT
behavior, not a defect to chase. A yfinance
outage or empty frame is a SEPARATE, first-class outcome (quarter_yf_unavailable)
that never touches the Finnhub leg and never raises into the scheduler. When it leaves
the WHOLE run without one yfinance row, _run_over_tickers writes ONE
`analyst_estimates_error` row naming the counts (the FMP-era failures were loud by
accident — a raise per ticker; with FMP gone the primary source must say so on purpose).
Per-ticker rows would be wrong: an ETF legitimately has no estimates. A
get_recent_quarterly_period_ends read failure
degrades to "no history to stabilize against" (today's date may drift a little;
self-heals the next run) rather than aborting anything.

NOT STORED: yfinance's growth/yearAgoRevenue/yearAgoEps/currency fields, even
though they are genuine raw (not computed) values — kept out to hold the
quarterly row to the SAME shape the (since removed) FMP annual leg had, which never
carried them either. Revisit if a future reader actually needs them; they cost nothing to add
later (additive column) and nothing was thrown away (yfinance is queried live).

PACING: revenue_estimate + earnings_estimate + earnings_dates are fetched
concurrently per ticker, the same run_in_executor + wait_for shape
fundamentals.get_fundamentals already uses for this synchronous, scraped library.
YFINANCE_PACE_SECONDS (24s) is slept BETWEEN tickers in _run_over_tickers — the exact
per-ticker cadence the two 12s FMP sleeps used to impose, kept so removing FMP changed no
vendor's request pattern (Yahoo throttles scrapers; a throttled night is a night of
quarter_yf_unavailable and a stalled clock). It is not a measured limit. Lowering it
is a separate decision that needs a measured Yahoo tolerance, and a night's
wall time (~24s x population) is the only thing it costs.

THE ANNUAL LEG IS YFINANCE TOO (2026-10-16 — his ruling 2026-09-03 (1): "start with what
yfinance gives — two forward quarters PLUS THE ANNUAL — and re-test at 60 days"). The same
`revenue_estimate` / `earnings_estimate` frames the quarterly leg already downloads carry
FOUR periods ('0q','+1q','0y','+1y' — yfinance's `_get_periodic_df` slices the one cached
`earningsTrend` fetch to `[:4]`; probed 2026-10-16 on AAPL, COST, WMT, NRIX, AMLX, ETON,
ABCL: all four periods, with analyst counts, on 7 of 7). So the annual rows cost ZERO extra
Yahoo requests — `_fetch_yfinance_quarterly` just reads two more rows out of frames it
already holds (a test spies the Ticker attribute accesses and pins exactly three).
  Rows: `period_type='annual'`, `source='yfinance'`, `period_label_method=
  'yf_fiscal_year_end'` (LABEL_METHOD_YF_FISCAL_YEAR_END), `fiscal_quarter`/`fiscal_year`
  NULL (those columns hold a VENDOR's raw label; this period end is derived, and
  `fiscal_year` would just repeat `period_end_date.year`). Same columns and same raw-value
  mapping as the quarterly row (one shared builder), same honest-window stamping.
  RECORDER_VERSION does not move: no existing row changed shape or meaning, and the 60-day
  reader tells quarterly from annual by `period_type` alone.
  THE LABEL RULE (resolve_annual_period_ends) — yfinance's '0y'/'+1y' are RELATIVE like
  '0q'/'+1q' and the frame carries no date, so an ABSOLUTE fiscal-year end is resolved with
  the same ingredients the quarterly and Finnhub legs already use:
    '0y'  = the first fiscal-year-end after (last_reported_quarter_end + 30 days), where
            the year-end for fiscal year Y is `fiscal_quarter_end_from_label(4, Y, fiscal_
            year_end)` — EDGAR's own `fiscalYearEnd` MMDD, the Finnhub leg's resolver,
            so day-clamping (a "0229") is shared rather than re-implemented — SNAPPED TO
            THE NEAREST MONTH END (below).
    '+1y' = the next year's end by the same function.
  THE SNAP (2026-10-16, reviewer-found BLOCKER): the label is the NEAREST MONTH END to that
  date (0831/0830/0901/0903 -> 08-31; 0926/0927 -> 09-30; 0103 -> the PRECEDING 12-31;
  nearest, not end-of-the-containing-month). Why: EDGAR's `fiscalYearEnd` MMDD is not a
  constant for a 52/53-week filer — it drifts a day or two, at each Q1 10-Q (COST 0831 ->
  0830, AAPL 0927 -> 0926) — and `period_end_date` is part of the row's primary key, so an
  unsnapped label would split ONE fiscal year's revision series into two keys the day the
  MMDD moved. Yahoo itself dates a 52/53-week year at the month end (observed 2026-10-16:
  AAPL 2026-09-30, COST 2027-08-31, WMT 2027-01-31), so the snap also makes the label equal
  Yahoo's on all seven names checked. It is applied to the ANNUAL label only:
  fiscal_quarter_end_from_label (the Finnhub quarterly leg) is deliberately unchanged.
  Why +30 days: EDGAR's MMDD is only approximate for a 52/53-week filer (a 10-K reportDate
  of 09-25 against MMDD "0926"); without the band a year that has JUST reported could be
  re-labelled as still-current. Fiscal year ends are 365 days apart, so 30 days can never
  merge two years. Why the anchor is last_reported_quarter_end and not the quarterly leg's
  stored '0q': it is an exact EDGAR fact, so the annual label does not inherit the
  quarterly reconstruction's ~week of residual imprecision (resolve_quarterly_period_ends'
  own docstring), and it still resolves for a name whose next earnings date Yahoo has not
  published yet.
  THE GATE (same bound as resolve_quarterly_period_ends): last_actual_release_date minus
  last_reported_quarter_end must fall in [_MIN, _MAX]_RELEASE_LAG_DAYS. That is what rejects
  the REPORTING-GAP race — fiscal-year results RELEASED (Yahoo's '0y' has already rolled)
  but the 10-K not yet FILED (EDGAR still shows the third quarter): without it '0y' would be
  labelled a year early for the days (up to ~40, per the module's reporting-gap note above)
  a year each ticker spends in that gap. Skipped
  and counted (`annual_yf_no_label`), never stored against a guessed date. EXPECT A NONZERO
  BASELINE there for the same reason as `quarter_yf_no_cadence`.
  THE 10-K CROSS-CHECK (2026-10-16, measured on 176 live-alert tickers): EDGAR's fiscalYearEnd
  can be STALE after a fiscal-year change — AEHR's 8-K of 2026-04-07 moved its year end from
  late May to late June, its last 10-K reportDate is 2026-05-29, EDGAR still says "1231", so
  the label read 2026-12-31 against Yahoo's 2027-05-31 (the other 304 labels matched Yahoo).
  The fact `last_annual_report_end` (max 10-K/10-K/A reportDate) is compared by snapped month
  with the year end fiscalYearEnd implies; a disagreement skips (`annual_yf_no_label`), never
  guesses. No 10-K on record -> unchanged. Quarterly/Finnhub paths never read it.
  DETERMINISTIC, SO NO STABILIZATION: the label is a pure function of (EDGAR fiscalYearEnd,
  EDGAR last_reported_quarter_end, EDGAR last 10-K). None moves day to day; the one input
  that DOES drift (fiscalYearEnd's MMDD, a day or two at a Q1 10-Q on a 52/53-week filer) is absorbed by the
  month-end snap above rather than by a history read, so unlike the quarterly leg there is no
  `stabilize_period_end` pass (the one existing helper, get_recent_quarterly_period_ends, is
  hardcoded to period_type='quarter' anyway).
  ASSUMPTION THE FIRST FISCAL-YEAR BOUNDARY IN THE DATA CONFIRMS OR BREAKS: Yahoo's '0y'
  rolls to the next year when '0q' does (at the Q4 RELEASE, not at the filing). Observed
  2026-10-16: AAPL's FY ended 09-26 and has not reported (10-29); Yahoo shows BOTH 0q and
  0y ending 2026-09-30 — i.e. 0y stays on the just-ended, unreported year. The after side
  of the roll is not yet observed. If it differs, the signature is an annual
  `period_end_date` that flips on a night the ticker's quarterly '0q' did not cross its
  fiscal year end; the SSoT's DONE-WHEN reads for exactly that.
  Annual rows ride only when the quarterly frame has data (`periods` non-empty — the
  `return None` gate is untouched, so no quarterly counter changed meaning). Annual rows
  do NOT need the quarterly leg to resolve a '0q' date, so a name Yahoo lists no next
  earnings date for still records its annual estimate. The pre-registered bar is counted
  in the run (`annual_yf_tickers` / `quarter_yf_tickers`) and printed on its own short
  `analyst_estimates_snapshot_annual` audit row (annual_coverage_summary) — NOT as a clause
  on the main summary row, because log_audit_event stores only the first 500 characters and
  that row is ~600 characters on any night, so its tail is already cut off.
  Only a row with a revenue_avg OR eps_avg counts as covered (`_has_estimate`): a frame
  row that is all-NaN is stored — "we asked, the vendor had nothing", the same record the
  quarterly leg keeps — but must not pass a coverage bar, or the bar could be met by an
  empty leg.

FINNHUB — A SECOND ESTIMATES SOURCE (v4, 2026-09-03). Verified live with the
operator's own key: `/stock/revenue-estimate` (the consensus SERIES, the same
shape yfinance gives) is HTTP 403 on all seven population small caps — genuinely
premium-walled, never call it. `/calendar/earnings` is FREE and returns forward
EPS + revenue estimates on 7/7, two quarters ahead each, at 30 calls/sec. ITS ONE
GAP: the calendar carries NO ANALYST COUNT, so `n_analysts < 3 -> None`
(estimate_for_scoring) cannot be applied to it — `analyst_count_available=False`
marks that NULL as "this source never reports a count," never to be confused with
`num_analysts_revenue IS NULL` on a yfinance row (which means "we asked and
the vendor had nothing"). Finnhub therefore CANNOT replace yfinance (which stays
PRIMARY, and the only source estimate_for_scoring's rule can ever admit) — it is
an independent second calendar, stored as its own rows (`source='finnhub_calendar'`,
FINNHUB_SOURCE below), same table, same honesty/window stamping.

THE BIGGEST WIN, and why this is worth doing at all: Finnhub's calendar entries
state the fiscal `quarter` + `year` OUTRIGHT — a discrete, non-drifting identity —
where yfinance's '0q'/'+1q' are RELATIVE and must be RECONSTRUCTED (see
resolve_quarterly_period_ends above) into an absolute date that then has to be
STABILIZED against drift (stabilize_period_end). The module's own admission is
"a quarter's label is set by whichever run FIRST sees it ... and held from then
on" — so a MORE RELIABLE first label is a structural win, not an incremental one.
fiscal_quarter_end_from_label converts (quarter, year) into a period_end_date
using this ticker's OWN EDGAR-published `fiscalYearEnd` (MMDD, e.g. AAPL "0926",
COST "0830" — a real fact, zero extra network calls: it rides the SAME submissions
payload _get_edgar_facts already fetches) — NEVER a naive Jan-Dec quarter
assumption. MEASURED, not assumed, against real COST EDGAR report dates: a fixed
3-calendar-month step from the fiscal year end is off by 0-20 days across COST's
four real quarters (worst: Q3 ~20 days). That is WORSE, on a 4-4-5 filer, than
the ~1-week precision resolve_quarterly_period_ends already claims — and is
ACCEPTED anyway, for three reasons that do not apply to that earlier design's
REJECTED fixed-3-month attempt: (1) it is DETERMINISTIC — same (quarter, year,
fiscalYearEnd) always produces the SAME date, so unlike the yfinance leg's live
inputs it cannot drift DAY TO DAY (the one input that does move, EDGAR's MMDD, is
absorbed by the stored-date stabilization — "FINNHUB ROWS ARE STABILIZED TOO"); (2) this
recorder's population is overwhelmingly Dec-fiscal-year small/micro caps, where
the error is ~0; (3) real quarters are ~90 days apart, so a 0-20 day error can
never collide two adjacent quarters. It is a LABEL, not a claim of exact-day
precision — exactly like the yfinance reconstruction it is being compared against.

SELF-CONSISTENCY GUARDS (never trust a vendor label blind — finnhub_period_end_
from_entry). Finnhub's swagger.json describes `/calendar/earnings`'s quarter/year
as "Earnings quarter"/"Earnings year" — vaguer than the explicitly-labeled
"Fiscal quarter"/"Fiscal year" on its OTHER estimate endpoints, so whether they
are fiscal or calendar-year is genuinely undecided from docs alone (checked
2026-09-03; undecidable without a live key on a non-calendar-fiscal-year name).
Rather than trust it, every Finnhub-derived period_end_date must ALSO satisfy:
(a) `entry.date` (Finnhub's own reported announcement date for that quarter)
minus the derived period_end_date falls in the SAME [0, 75]-day release-lag
window resolve_quarterly_period_ends already enforces — a fiscal/calendar-year
or wrong-quarter misread runs the gap off by ~90+ days and fails this outright;
(b) the derived date must fall AFTER SEC EDGAR's own last_reported_quarter_end
(the same sanity bound resolve_quarterly_period_ends applies to '0q'). Either
guard failing -> this Finnhub entry is REJECTED and counted
(quarter_finnhub_no_cadence), never stored against an unverified label — the
guards, not the vendor's word, are what make this safe to use.

PREFER, NEVER REQUIRE: a guard-passed Finnhub period_end_date additionally
CORROBORATES (pair_finnhub_periods_to_slots, tolerance
_FINNHUB_OVERRIDE_TOLERANCE_DAYS=45 — about half a quarter: wide enough to
accept BOTH methods' own few-to-twenty-day imprecision, narrow enough that the
NEXT real quarter (~90 days away) can never be mistaken for the same one) this
ticker's OWN yfinance/EDGAR-reconstructed '0q'/'+1q' candidate. Only when it
corroborates does it OVERRIDE that slot's period_end_date (so the yfinance row
and the Finnhub row for the same real quarter share the identical
period_end_date, which is what makes them joinable for the divergence check
below) — `period_label_method` on that row flips from LABEL_METHOD_YF_RECONSTRUCTED
to LABEL_METHOD_FINNHUB_FISCAL. No corroboration -> the yfinance row keeps its own
reconstructed date untouched; Finnhub's OWN row (this is the resilience win) is
STILL stored independently either way — a Finnhub calendar entry never depends
on yfinance succeeding at all.

THE HONEST STATEMENT OF WHAT "OVERRIDE" MEANS ACROSS RUNS: stabilize_period_end
(see its own docstring — "a quarter's label is set by whichever run FIRST sees it
... and held from then on") still runs on the corroborated candidate. So the
override wins the STORED DATE only when this is the quarter's first sighting, or
when it agrees with the date already on record; if an EARLIER run already
established a different date for this same quarter (e.g. a yfinance-only night
before Finnhub started covering this ticker), that established date wins and
Finnhub's OWN row is realigned to match it (snapshot_ticker mutates the Finnhub
row's period_end_date in place) — `period_label_method` still says Finnhub
identified WHICH quarter this is, which remains true even though the established
key, not Finnhub's freshly-computed date, is what gets stored. This is what keeps
the two sources joinable for the divergence check across every future run, not
only the run where they first agree.

FINNHUB ROWS ARE STABILIZED TOO (2026-10-17, #333; data capture only). The fresh Finnhub
label is a pure function of (quarter, year, EDGAR `fiscalYearEnd` MMDD), and that MMDD
DRIFTS by a day or two at the first-quarter 10-Q of a 52/53-week filer (COST 0831 -> 0830,
AAPL 0927 -> 0926; COST and AAPL are next due Dec / late Jan). Unstabilized, every Finnhub
quarter label of that ticker would move a day on the same night and mint a second primary
key for each quarter — splitting its Finnhub revision series (measured in prod 2026-10-17:
0 split pairs yet in 1,680 Finnhub rows over 105 tickers, because the table only reaches
back to 2026-09-03 and no MMDD changed in it; the drift is ahead, not behind). So the
STORED Finnhub row's period_end_date goes through the same stabilize_period_end (same
_STABILIZE_TOLERANCE_DAYS, same _STABILIZE_LOOKBACK_DAYS) against that ticker's own
`source='finnhub_calendar'` dates — db.get_recent_quarterly_period_ends(source=...),
one read per ticker per run. Deliberately NOT against yfinance history: a 15-day window
must not pull a Finnhub label onto an uncorroborated yfinance reconstruction. Boundaries:
  - `finnhub_period_ends` (the list pair_finnhub_periods_to_slots reads) keeps the FRESH
    guard-passed dates, so the CORROBORATION step is unchanged: which yfinance slot pairs
    with which Finnhub entry is decided on fresh labels exactly as before.
  - The yfinance `candidate` for a corroborated slot is the Finnhub row's own STORED
    (already-stabilized) date, not the fresh label — so on a drift night both sources start
    from ONE key for that quarter. The yfinance rows are therefore NOT byte-identical to
    before on such a night: only `period_end_date` can differ, only on a corroborated
    quarterly row, never an annual row, and only when the Finnhub history held a near date.
    Why this and not the fresh label: yfinance first sees a new +1q quarter only on the 10-Q
    night (the 75-day lag gate drops it earlier), and that same 10-Q is what moves EDGAR's
    MMDD — Finnhub has already stored the quarter under the old MMDD. With the fresh label
    the yfinance row lands on the fresh date, the Finnhub row on the stored one, and
    `period_end == candidate` so no realign fires: the divergence join for that quarter
    would stay split on every later night (reviewer replay: a divergence row on 0 of 8-15
    nights in 7 of 8 timelines; zero lost with the stored date as the candidate).
  - The yfinance block's realign (above) still runs afterwards and still wins the stored
    Finnhub key when yfinance's own history reuses a different date. It converges: the
    realigned row is written tonight, so tomorrow's Finnhub history carries that key first.
  - Nothing known is left split on a drift night: the two sources start from the Finnhub
    row's key and yfinance's own history can only move BOTH rows together (realign).
  - A history-read failure degrades to "no history" (warning, never aborts), like the
    yfinance read; a genuinely new quarter (>= 16 days from every stored date) is kept as is.

DIVERGENCE, NO THRESHOLD (compute_estimate_divergences, mi_analyst_estimates_
divergence table). Where BOTH sources land a row on the exact SAME (ticker,
period_type, period_end_date, as_of_date) — i.e. exactly the corroborated-override
case above — one divergence row stores BOTH sources' raw revenue_avg/eps_avg plus
the plain difference (finnhub minus yfinance). No threshold is applied or chosen
here (operator instruction, 2026-09-03: three thresholds were invented and
re-litigated this week) — the distribution is meant to be READ in ~60 days, not
pre-judged.

FINNHUB IS SILENT AND NEVER RAISES (matches _fetch_yfinance_quarterly's contract
exactly). `_finnhub_get` is a BESPOKE transport, deliberately NOT
collector._fmp_get: that helper routes every failure through
llm_health.maybe_alert_api_failure, which CAN Telegram and writes `api_failure_<vendor>`
audit rows — this recorder is SILENT on every path (THE LINE, top of this file) and
no longer touches that helper at all. It reads and logs the response BODY
(redacted) on an HTTP error, never just the status — the FMP lesson (2026-09-03
root cause): a 402/403 can mean a parameter restriction, not a rate breach, and
the body text is the only way to tell them apart. `FINNHUB_API_KEY` unset,
network failure, malformed shape, or an empty calendar all degrade to
"nothing recorded, counted" (quarter_finnhub_unavailable) and never touch the
yfinance quarterly leg.

PACING: FINNHUB_PACE_SECONDS=1.1s (~54 calls/min, safely under the free tier's
~60/min ceiling) is a REAL elapsed-time throttle (mirrors collector._polygon_get's
last-call-timestamp pattern) — it costs ~0 wall time in practice because tickers
process sequentially and YFINANCE_PACE_SECONDS already space consecutive tickers ~24s
apart, >20x the deficit this throttle would ever need to sleep off; it exists to protect
a future parallel run (a backfill, or a re-architected nightly loop), not because
today's cadence needs it. The fetch itself launches as a task alongside `_yf_task`
(see snapshot_ticker) so the two vendors' round trips overlap.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, timedelta
from typing import Any, Optional

from agents.market_intelligence.db import (
    _f,
    get_analyst_estimate_population,
    get_recent_quarterly_period_ends,
    log_audit_event,
    upsert_analyst_estimates,
    upsert_analyst_estimates_divergence,
)
from shared.secret_redaction import redact_secrets

logger = logging.getLogger(__name__)

RECORDER_VERSION = "v4"           # v2 2026-09-01: anchor source FMP -> SEC EDGAR (402 fix)
                                   # v3 2026-09-02: quarterly leg added (yfinance, see below)
                                   # v4 2026-09-03: Finnhub calendar added as a 2nd source (see below)
                                   # (2026-10-16: the FMP annual leg was REMOVED with no bump on
                                   # purpose — no row this job still writes changed shape or meaning;
                                   # the same day the yfinance ANNUAL leg was ADDED, again no bump:
                                   # annual rows are NEW rows (period_type='annual'), no existing
                                   # row changed shape or meaning)
QUARTERLY_ESTIMATES_SOURCE = "yfinance"  # the QUARTERLY leg (v3) — distinguishes vendor in
                                          # the existing `source` column; no schema change
FINNHUB_SOURCE = "finnhub_calendar"      # the v4 second source — /calendar/earnings only;
                                          # /stock/revenue-estimate is premium-walled (403, 7/7)
POPULATION_LOOKBACK_DAYS = 30     # daily run: tickers with a live-source alert this recent
MIN_ANALYSTS_DEFAULT = 3          # the sketch's n<3 -> None rule (read-side, re-tunable)

# ── period_label_method (v4) — which method produced a QUARTER row's period_end_date ──
# Recorded on EVERY row (annual included) so the Finnhub-labeling improvement is
# MEASURABLE rather than assumed (operator instruction, 2026-09-03).
LABEL_METHOD_YF_RECONSTRUCTED = "yf_reconstructed"   # yfinance quarterly, no Finnhub corroboration
LABEL_METHOD_FINNHUB_FISCAL = "finnhub_fiscal_label"  # period_end_date derived from Finnhub's own
                                                       # (quarter, year) — see fiscal_quarter_end_from_label
LABEL_METHOD_YF_FISCAL_YEAR_END = "yf_fiscal_year_end"  # ANNUAL rows (2026-10-16): period_end_date
                                                         # derived from EDGAR's fiscalYearEnd +
                                                         # last_reported_quarter_end — see
                                                         # resolve_annual_period_ends. The db.py DDL
                                                         # comment lists only the earlier values; it is
                                                         # left alone on purpose (no schema change, and
                                                         # a comment edit there would widen the deploy
                                                         # scope) — this is the vocabulary.
# ── SEC EDGAR anchor source (v2) ──────────────────────────────────────────────────────
# The exact form set the 08-31 reach measurement used (306/335 resolved) — foreign
# filers report on 20-F/6-K; amendments carry the same filing-date semantics.
ANCHOR_FORMS = frozenset({"10-Q", "10-K", "20-F", "6-K", "10-Q/A", "10-K/A", "20-F/A"})
# QUARTERLY_CADENCE_FORMS (v3) — a NARROWER set than ANCHOR_FORMS, used only to derive the
# quarterly-leg's lag/quarter-length facts (quarterly_cadence_facts below). 20-F is annual-only
# and 6-K interim filings are irregular for foreign private issuers — neither supports a
# quarterly cadence, so a ticker anchored only on those gets no cadence facts (its quarterly
# leg is skipped and counted) even though its ANNUAL honesty window still resolves fine.
QUARTERLY_CADENCE_FORMS = frozenset({"10-Q", "10-K", "10-Q/A", "10-K/A"})
_EDGAR_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
_EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
# SEC's access policy asks every client to identify itself — with ONE identity per codebase.
# We declare collector._SEC_UA (env `SEC_USER_AGENT`), which has been this repo's SEC contact
# since #187. This module briefly shipped its own `SEC_EDGAR_USER_AGENT` (2026-09-01), which
# meant SEC saw two different names from one process for the same purpose and an operator could
# set either env var without knowing the other existed. Imported lazily inside the fetch so the
# module keeps its no-collector-at-import-time property.
_EDGAR_TIMEOUT_SECONDS = 30

# One ticker->CIK map fetch per as_of day, success OR failure — a dead sec.gov must
# cost the run ONE timeout, not one per ticker. {"as_of": date|None, "map": dict|None}.
_cik_map_state: dict[str, Any] = {"as_of": None, "map": None}

# ── quarterly leg (v3) — yfinance estimates + SEC-sourced cadence resolution ──────────
_EMPTY_CADENCE_FACTS: dict[str, Any] = {
    "last_reported_quarter_end": None, "prior_reported_quarter_end": None,
    "fiscal_year_end": None,   # v4: EDGAR's own "MMDD" fiscal-year-end fact (e.g. AAPL "0926") —
                                # zero extra network cost, same submissions payload; feeds
                                # fiscal_quarter_end_from_label, the v4 Finnhub labeling leg
    "last_annual_report_end": None,   # the MAX reportDate over 10-K/10-K/A — the company's OWN
                                       # last annual period end; read ONLY by the annual leg
                                       # (resolve_annual_period_ends) to catch a stale fiscalYearEnd
}
# Annual report forms — the only forms last_annual_report_end reads (a subset of
# QUARTERLY_CADENCE_FORMS: a 10-K is annual and rides the same reportDate parse).
_ANNUAL_REPORT_FORMS = frozenset({"10-K", "10-K/A"})
# Sanity bounds for resolve_quarterly_period_ends — an out-of-range lag or quarter length
# means the inputs are bad/mismatched, not that this ticker is unusual; treat it the same
# as unresolvable rather than storing an implausible date.
_MIN_RELEASE_LAG_DAYS = 0
_MAX_RELEASE_LAG_DAYS = 75        # most companies release within ~20-45 days of quarter end;
                                   # 75 is generous headroom AND (deliberately) tight enough to
                                   # reject the "reporting gap" mismatch — see the module
                                   # docstring — where the release just seen belongs to a
                                   # DIFFERENT (newer) quarter than the EDGAR anchor still
                                   # reflects: that mismatch always runs a quarter-length (~90d)
                                   # too long, so it fails this bound and is skipped, not guessed
_MIN_QUARTER_LENGTH_DAYS = 60     # a real fiscal quarter is ~91 days; COST's short Q1 measured
_MAX_QUARTER_LENGTH_DAYS = 130    # at 84 days (4-4-5 retail calendar) — bound loosely around that
_STABILIZE_TOLERANCE_DAYS = 15    # see stabilize_period_end — about half a quarter's worth of
                                   # slack: wide enough to absorb the day-level jitter a
                                   # refining next_earnings_date estimate (or a filing-boundary
                                   # lag swing) introduces run to run, narrow enough that two
                                   # genuinely DIFFERENT quarters (~90 days apart) never collapse
_STABILIZE_LOOKBACK_DAYS = 120    # how far back to look for a prior recorded date to reuse —
                                   # a bit over one quarter, so a population-coverage gap never
                                   # loses the prior snapshot of the SAME quarter
# Slept BETWEEN tickers in _run_over_tickers. 24s is not a Yahoo limit anyone measured: it is
# the per-ticker cadence the two 12s FMP sleeps imposed on every yfinance/Finnhub/EDGAR call
# from 2026-09-04 (the first night the yfinance path ever ran) until the FMP leg was removed
# 2026-10-16, kept so that removal altered no vendor's request pattern. This used to be a
# declared-but-unenforced 1.0 courtesy; it is now enforced.
YFINANCE_PACE_SECONDS = 24.0
_YF_QUARTER_TIMEOUT_SECONDS = 30.0  # mirrors fundamentals.py's _YF_TIMEOUT
_YF_QUARTER_PERIODS = ("0q", "+1q")  # the two QUARTERLY periods — they alone decide
                                      # quarter_yf_unavailable (an annual-only frame is not "available")
_YF_ANNUAL_PERIODS = ("0y", "+1y")   # 2026-10-16: the two ANNUAL periods, read out of the SAME two
                                      # frames (no extra request) — see "THE ANNUAL LEG IS YFINANCE TOO"
_ANNUAL_ROLL_BAND_DAYS = 30          # '0y' is the first fiscal year end MORE than this many days after
                                      # last_reported_quarter_end — absorbs EDGAR's approximate MMDD on
                                      # a 52/53-week filer; year ends are 365 days apart so it can
                                      # never merge two years (see resolve_annual_period_ends). The
                                      # year end itself is then snapped to the nearest month end.

# ── Finnhub /calendar/earnings (v4) — the second estimates source ────────────────────
FINNHUB_BASE = "https://finnhub.io/api/v1"
FINNHUB_PACE_SECONDS = 1.1        # ~54 calls/min, safely under the free tier's ~60/min ceiling —
                                   # a REAL elapsed-time throttle (see _finnhub_get); costs ~0 wall
                                   # time today because YFINANCE_PACE_SECONDS already spaces tickers
                                   # ~24s apart
_FINNHUB_TIMEOUT_SECONDS = 20.0
_FINNHUB_CALENDAR_WINDOW_DAYS = 200   # ~2 quarters ahead — matches the shape verified live
                                       # 2026-09-03 (7/7 population tickers, 2 forward quarters each)
_FINNHUB_MAX_PERIODS = 4          # defensive cap; the verified shape returns ~2 entries/ticker
_FINNHUB_OVERRIDE_TOLERANCE_DAYS = 45  # ~half a quarter: wide enough to accept both labeling
                                        # methods' own few-to-twenty-day imprecision, narrow enough
                                        # that the NEXT real quarter (~90 days away) can never be
                                        # mistaken for the one a yfinance slot already resolved


# ── pure core (mock-free, the house idiom) ────────────────────────────────────────────

def _i(v) -> Optional[int]:
    """None-safe int coercion. NOT db._int_or_none — that one raises on garbage
    (its callers want a BIGINT param to fail loudly); a vendor field must degrade to
    None instead. Float coercion is db._f, imported above."""
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


def _d(v) -> Optional[date]:
    """ISO date string (or date) -> date; anything unparseable -> None, never a guess."""
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _nan_to_none(v: Any) -> Any:
    """yfinance/pandas represents a missing numeric field as float('nan'), not None.
    float(nan) survives db._f unchanged (nan is not None, so _f's guard doesn't
    catch it) and would store NaN into a DOUBLE PRECISION column (FMP's JSON used an
    explicit null for a missing value; yfinance does not).
    Filter it out before handing a value to _f/_i (_i is unaffected: int(nan)
    already raises ValueError, which _i already catches)."""
    try:
        if v is None or v != v:   # NaN is the only value that is not equal to itself
            return None
    except Exception:  # loud-ok: a value that can't even be compared is not a number
        pass
    return v


def honest_valid_from(anchor_filing_date: Optional[date], as_of: date) -> date:
    """The earliest date a value read on `as_of` can honestly be said to have stood.

    GUARD (mutation-tested): no anchor -> as_of (a row may NEVER claim history without
    a resolved filing date — ETFs/non-filers buy zero days, by design). An anchor in
    the future of the read (a bad API date) is clamped to as_of the same way.
    """
    if anchor_filing_date is None or anchor_filing_date > as_of:
        return as_of
    return anchor_filing_date


def latest_filing_from_submissions(payload: Any) -> Optional[date]:
    """EDGAR submissions payload -> the ticker's most recent anchor-form filing date.

    Pure and defensive: takes the MAX parsed date over ANCHOR_FORMS rather than
    trusting EDGAR's newest-first ordering; any malformed payload -> None (which the
    caller records as zero honest window — never a guess, never a widened window).
    """
    try:
        recent = payload["filings"]["recent"]
        forms, dates = recent["form"], recent["filingDate"]
    except (TypeError, KeyError):
        return None
    best: Optional[date] = None
    for form, fdate in zip(forms, dates):
        if form not in ANCHOR_FORMS:
            continue
        parsed = _d(fdate)
        if parsed is not None and (best is None or parsed > best):
            best = parsed
    return best


# ── quarterly leg (v3) — SEC-sourced cadence resolution + yfinance normalization ──────
# See the module docstring's "THE QUARTERLY LEG IS YFINANCE" section for the full design
# rationale, including why the rejected fixed-3-month extrapolation fails on 4-4-5 retail
# calendars and how the chosen lag/quarter-length design closes the reporting-gap race.


def quarterly_cadence_facts(payload: Any) -> dict[str, Any]:
    """The SEC-sourced facts resolve_quarterly_period_ends (and, v4, fiscal_quarter_end_
    from_label) need, pulled from the SAME EDGAR submissions payload already fetched for
    the honesty-window anchor (zero extra network cost):
      last_reported_quarter_end   reportDate of the most recent QUARTERLY_CADENCE_FORMS
                                   (10-Q/10-K only) filing
      prior_reported_quarter_end  reportDate of the filing before that (this ticker's OWN
                                   observed quarter length = last - prior)
      fiscal_year_end             (v4) the submissions payload's OWN top-level "MMDD" fact
                                   (e.g. AAPL "0926", COST "0830") — a different level of the
                                   payload than filings.recent, so it is extracted FIRST and
                                   independently of whether the recent-filings parse below
                                   succeeds at all
      last_annual_report_end      the MAX reportDate over 10-K / 10-K/A filings only (None if
                                   none or unparseable) — the company's OWN last annual period
                                   end. Read ONLY by resolve_annual_period_ends, to cross-check
                                   fiscal_year_end; no quarterly/Finnhub path touches it
    Any field the payload can't support -> None; never a guess. A recent IPO with only one
    filing on record gets last_reported_quarter_end but no prior — '0q' can still resolve,
    '+1q' cannot (resolve_quarterly_period_ends handles that split)."""
    facts: dict[str, Any] = dict(_EMPTY_CADENCE_FACTS)
    if isinstance(payload, dict):
        fye = payload.get("fiscalYearEnd")
        if isinstance(fye, str) and len(fye) == 4 and fye.isdigit():
            facts["fiscal_year_end"] = fye
    try:
        recent = payload["filings"]["recent"]
        forms, report_dates = recent["form"], recent["reportDate"]
    except (TypeError, KeyError):
        return facts
    dates: list[date] = []
    annual_dates: list[date] = []
    for form, rdate in zip(forms, report_dates):
        if form not in QUARTERLY_CADENCE_FORMS:
            continue
        parsed = _d(rdate)
        if parsed is not None:
            dates.append(parsed)
            if form in _ANNUAL_REPORT_FORMS:
                annual_dates.append(parsed)
    if not dates:
        return facts
    facts["last_annual_report_end"] = max(annual_dates) if annual_dates else None
    ordered = sorted(set(dates))
    facts["last_reported_quarter_end"] = ordered[-1]
    facts["prior_reported_quarter_end"] = ordered[-2] if len(ordered) >= 2 else None
    return facts


def resolve_quarterly_period_ends(
    next_earnings_date: Optional[date], last_actual_release_date: Optional[date],
    cadence: dict[str, Optional[date]],
) -> dict[str, Optional[date]]:
    """yfinance's RELATIVE quarter labels ('0q','+1q') -> ABSOLUTE period-end dates.

    '0q' = next_earnings_date - this ticker's OWN observed RELEASE lag
           (last_actual_release_date - last_reported_quarter_end — both are "the world
           learned the results" events, one from yfinance, one from SEC EDGAR's
           reportDate; comparing a RELEASE to a RELEASE, never a release to a filing).
    '+1q' = '0q' + this ticker's OWN observed quarter length (from `cadence` — see
            quarterly_cadence_facts — a same-vendor, same-quarter-type EDGAR-to-EDGAR
            comparison, so no cross-vendor mismatch risk there).
    Both offsets are MEASURED facts about THIS ticker, never a fixed assumption. See
    the module docstring for why this design (anchored on yfinance's own always-
    current next_earnings_date) out-performs a fixed-3-month extrapolation on
    irregular fiscal calendars, and why comparing release-to-release — rather than
    the earlier release-to-FILING design — closes the earnings-release-vs-10-Q-filing
    reporting-gap race more robustly: a stale EDGAR anchor during that gap produces a
    release_lag inflated by roughly one quarter-length, which _MAX_RELEASE_LAG_DAYS
    rejects outright instead of quietly mislabeling the wrong quarter.

    KNOWN RESIDUAL (documented, not solved here): a company's Q4/FYE report often
    takes longer to release than a regular quarter (audited annual figures), so a
    lag measured from a REGULAR quarter slightly under-estimates the FYE quarter's
    true release lag (and vice versa) — checked against real COST/AAPL/WMT EDGAR
    data during design, this shows up as roughly a week of extra imprecision on a
    regular-to-FYE transition, not a wrong-quarter failure. snapshot_ticker's
    stabilize_period_end then LOCKS IN whichever date resolves first, so this
    residual affects a quarter's INITIAL label once, never its day-to-day stability.

    Sanity-bounded, never a guess passed off as data: missing inputs, an out-of-range
    lag or quarter length, or a computed '0q' that doesn't fall after the last
    reported quarter, return None for that period — the caller skips and counts it."""
    out: dict[str, Optional[date]] = {"0q": None, "+1q": None}
    last_q_end = cadence.get("last_reported_quarter_end")
    prior_q_end = cadence.get("prior_reported_quarter_end")
    if next_earnings_date is None or last_q_end is None or last_actual_release_date is None:
        return out
    release_lag_days = (last_actual_release_date - last_q_end).days
    if not (_MIN_RELEASE_LAG_DAYS <= release_lag_days <= _MAX_RELEASE_LAG_DAYS):
        return out
    q0 = next_earnings_date - timedelta(days=release_lag_days)
    if q0 <= last_q_end:
        return out
    out["0q"] = q0
    if prior_q_end is not None:
        quarter_len = (last_q_end - prior_q_end).days
        if _MIN_QUARTER_LENGTH_DAYS <= quarter_len <= _MAX_QUARTER_LENGTH_DAYS:
            out["+1q"] = q0 + timedelta(days=quarter_len)
    return out


def stabilize_period_end(
    candidate: Optional[date], recent_dates: list[date],
    tolerance_days: int = _STABILIZE_TOLERANCE_DAYS,
) -> Optional[date]:
    """THE LABEL-STABILITY FIX: if an EXISTING stored period_end_date for this ticker
    (`recent_dates` — see db.get_recent_quarterly_period_ends, which orders them
    MOST-RECENTLY-WRITTEN FIRST) is within `tolerance_days` of a freshly computed
    `candidate`, REUSE that existing date instead of the new one.

    WHY THIS EXISTS: resolve_quarterly_period_ends anchors on yfinance's live
    next_earnings_date, which can shift a few days as the estimate refines, and on
    the SEC's observed release lag, which can swing when a NEW filing lands (a
    fresh reportDate/lag pair). Recomputing from scratch every day would mint a
    slightly different period_end_date — and therefore a DIFFERENT primary key —
    for what is really the SAME fiscal quarter, fracturing the revision series this
    table exists to build (get_analyst_estimates_asof's
    DISTINCT ON (period_type, period_end_date) would then read one quarter as two
    or three). Reusing recorded history, rather than a calendar heuristic (e.g.
    snapping to the nearest month-end), is the ONLY fix verified to work for BOTH
    calendar-aligned filers (AAPL, WMT) and true 4-4-5 retail filers (COST) — a
    month-end snap fixes the former and systematically misdates the latter (COST's
    real quarter ends land 1-3 weeks from any month boundary).

    TIE-BREAK IS RECENCY, NOT DISTANCE (design review, 2026-09-02): the FIRST entry
    in `recent_dates` within tolerance wins, even if a later (older) entry happens
    to sit a day or two closer to `candidate`. This matters when more than one
    historical date sits within tolerance at once — e.g. an early, poorly-informed
    estimate from months ago (yfinance's date guessed ~6 months before the actual
    report) alongside a recently-confirmed one. Picking "numerically nearest"
    there could resurrect the stale early guess over the label the series most
    recently settled on; picking "most recently written, if plausible" keeps the
    series following its own confirmed history. Requires the caller to pass
    `recent_dates` in that order — get_recent_quarterly_period_ends already does.

    None candidate, or no recent history to check against, passes through
    unchanged (nothing to stabilize; the FIRST time a quarter is seen, its
    freshly resolved date is what gets recorded — and, by construction, becomes
    the label every later run converges back onto)."""
    if candidate is None:
        return candidate
    for stored in recent_dates:
        if abs((stored - candidate).days) <= tolerance_days:
            return stored
    return candidate


# ── v4 — Finnhub fiscal-label resolution (quarter+year -> period_end_date) ────────────
# See the module docstring's "THE BIGGEST WIN" / "SELF-CONSISTENCY GUARDS" / "PREFER,
# NEVER REQUIRE" sections for the full design rationale.


def _shift_months(d: date, months: int) -> date:
    """Pure calendar-month arithmetic (no external dependency): shift `d` by `months`
    (may be negative), clamping the day to the LAST valid day of the target month (e.g.
    Aug 31 - 6mo -> Feb 28/29, never rolls into March). The house's OWN documented
    reason to distrust simple month arithmetic (see resolve_quarterly_period_ends'
    docstring: a fixed 3-month step "missed the correct MONTH outright" on COST) is
    about using it to extrapolate from a LIVE, drifting anchor across runs; here it is
    applied ONCE, deterministically, to a fixed EDGAR fact (fiscal_year_end) plus a
    vendor-stated integer quarter — the failure mode that rejection guarded against
    (day-to-day primary-key fracture) cannot occur here because the inputs do not drift day
    to day; the one that moves rarely (EDGAR's fiscalYearEnd MMDD, a day or two at a
    52/53-week filer's first-quarter 10-Q) is absorbed where the Finnhub row is stored —
    snapshot_ticker's stabilize_period_end against the ticker's own Finnhub dates."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    next_first = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last_day_of_month = (next_first - timedelta(days=1)).day
    return date(year, month, min(d.day, last_day_of_month))


def fiscal_quarter_end_from_label(
    quarter: Optional[int], year: Optional[int], fiscal_year_end: Optional[str],
) -> Optional[date]:
    """Finnhub's explicit (quarter, year) -> an approximate calendar period_end_date,
    anchored on THIS TICKER'S OWN EDGAR-published fiscal_year_end ("MMDD", e.g. AAPL
    "0926", COST "0830" — quarterly_cadence_facts, zero extra network cost) — NEVER a
    generic Jan-Dec quarter assumption. `year` is read as the XBRL/EDGAR convention
    (the calendar year in which fiscal Q4 / the fiscal year END falls); Q(n) is 3*(4-n)
    months before that.

    DELIBERATE, MEASURED IMPRECISION (see the module docstring's "THE BIGGEST WIN" for
    the full justification — deterministic, small-cap-Dec-FYE population, ~90-day
    quarter spacing): MEASURED on COST's real EDGAR report dates, this lands 0-20 days
    off across the 4 real quarters (worst: the May quarter, ~20 days) — WORSE, on a
    true 4-4-5 filer, than resolve_quarterly_period_ends' own ~1-week precision, and
    ACCEPTABLE anyway because it is a deterministic LABEL, not a claim of exact-day
    truth, and finnhub_period_end_from_entry's guards (below) catch anything worse
    (wrong quarter / wrong year convention) rather than trusting this arithmetic blind.

    Sanity-bounded like every other date this module computes: an invalid quarter
    (not 1-4) or a missing input -> None, never a guess."""
    if quarter not in (1, 2, 3, 4) or year is None or not fiscal_year_end:
        return None
    try:
        year = int(year)
        fye_month = int(fiscal_year_end[:2])
        fye_day = int(fiscal_year_end[2:])
    except (TypeError, ValueError):
        return None
    if not (1 <= fye_month <= 12 and 1 <= fye_day <= 31):
        return None
    try:
        next_month_first = (date(year, fye_month + 1, 1) if fye_month < 12
                             else date(year + 1, 1, 1))
        last_day_of_fye_month = (next_month_first - timedelta(days=1)).day
        q4_end = date(year, fye_month, min(fye_day, last_day_of_fye_month))
    except ValueError:
        return None
    return _shift_months(q4_end, -3 * (4 - quarter))


def finnhub_period_end_from_entry(
    entry_date: Optional[date], quarter: Optional[int], year: Optional[int],
    fiscal_year_end: Optional[str], last_reported_quarter_end: Optional[date],
) -> Optional[date]:
    """One Finnhub calendar entry -> a GUARDED period_end_date, or None when either
    self-consistency guard fails (see the module docstring's "SELF-CONSISTENCY GUARDS"):
      (a) entry_date - computed_period_end must fall in the SAME [_MIN_RELEASE_LAG_DAYS,
          _MAX_RELEASE_LAG_DAYS] window resolve_quarterly_period_ends already enforces —
          a fiscal/calendar-year or wrong-quarter misread runs this off by ~90+ days;
      (b) computed_period_end must fall AFTER SEC EDGAR's last_reported_quarter_end
          (the same "not the quarter that already reported" bound '0q' uses).
    Never invents a date: fiscal_quarter_end_from_label failing, or either guard
    failing, returns None — the caller skips and counts this entry
    (quarter_finnhub_no_cadence), it never falls back to a guess."""
    computed = fiscal_quarter_end_from_label(quarter, year, fiscal_year_end)
    if computed is None or entry_date is None:
        return None
    lag_days = (entry_date - computed).days
    if not (_MIN_RELEASE_LAG_DAYS <= lag_days <= _MAX_RELEASE_LAG_DAYS):
        return None
    if last_reported_quarter_end is not None and computed <= last_reported_quarter_end:
        return None
    return computed


def pair_finnhub_periods_to_slots(
    finnhub_period_ends: "list[Optional[date]]", reconstructed: "dict[str, Optional[date]]",
    tolerance_days: int = _FINNHUB_OVERRIDE_TOLERANCE_DAYS,
) -> "dict[str, Optional[int]]":
    """For each yfinance slot ('0q', '+1q'), find the INDEX into `finnhub_period_ends`
    (guard-passed Finnhub-derived dates, see finnhub_period_end_from_entry) that
    CORROBORATES this ticker's own reconstructed candidate for that slot — i.e. sits
    within `tolerance_days` of it (see the module docstring's "PREFER, NEVER REQUIRE").
    Greedy, closest-match-wins, and each Finnhub index can corroborate AT MOST ONE slot
    (two calendar entries about the same real quarter would be a vendor data bug, not a
    genuine double-match). Returns {'0q': index|None, '+1q': index|None} — the caller
    (snapshot_ticker) uses the index to pull that entry's OWN period_end_date AND its
    fiscal_quarter/fiscal_year for tagging. No match (or a missing reconstructed
    candidate) -> None for that slot; the reconstruction stays the fallback, exactly as
    if Finnhub did not cover this ticker at all."""
    out: "dict[str, Optional[int]]" = {"0q": None, "+1q": None}
    used: set = set()
    for slot in ("0q", "+1q"):
        target = reconstructed.get(slot)
        if target is None:
            continue
        best_i, best_gap = None, None
        for i, cand in enumerate(finnhub_period_ends):
            if i in used or cand is None:
                continue
            gap = abs((cand - target).days)
            if gap <= tolerance_days and (best_gap is None or gap < best_gap):
                best_i, best_gap = i, gap
        if best_i is not None:
            out[slot] = best_i
            used.add(best_i)
    return out


def nearest_month_end(d: date) -> date:
    """The month end (last calendar day of a month) NEAREST to `d`: `d` itself when it is
    one; otherwise the closer of the end of d's own month and the end of the PRECEDING month
    (a tie goes to d's own month end — no real fiscal year end is ever mid-month). This is
    NEAREST, not "end of the containing month": 0901 and 0903 snap BACK to 08-31, 0103 to
    the preceding 12-31, while 0926/0927 snap forward to 09-30. Pure calendar arithmetic."""
    prev_end = d.replace(day=1) - timedelta(days=1)
    next_first = date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
    this_end = next_first - timedelta(days=1)
    return this_end if (this_end - d) <= (d - prev_end) else prev_end


def resolve_annual_period_ends(
    last_actual_release_date: Optional[date], cadence: dict[str, Any],
) -> dict[str, Optional[date]]:
    """yfinance's RELATIVE annual labels ('0y','+1y') -> ABSOLUTE fiscal-year-end dates.
    The annual twin of resolve_quarterly_period_ends; the module docstring's "THE ANNUAL
    LEG IS YFINANCE TOO" has the full rationale. The rule, stated once:

      '0y'  = the first fiscal-year end MORE THAN _ANNUAL_ROLL_BAND_DAYS (30) after
              `cadence['last_reported_quarter_end']`; the year end for fiscal year Y is
              nearest_month_end(fiscal_quarter_end_from_label(4, Y, cadence['fiscal_year_end']))
              — the Finnhub leg's resolver, on this ticker's OWN EDGAR fiscalYearEnd, never a
              Jan-Dec guess, snapped to the NEAREST MONTH END.
      '+1y' = the same function one year on.

    WHY THE SNAP: EDGAR's fiscalYearEnd MMDD drifts by a day or two for a 52/53-week filer
    (COST 0831 -> 0830, AAPL 0927 -> 0926, at each Q1 10-Q), and the resolved date is part of
    the row's primary key — unsnapped, one fiscal year would split into two keys the day the
    MMDD moved. Snapped, every drifted spelling of the same year end lands on one date (and
    on Yahoo's own month-end dating). Only this annual label is snapped; the quarterly
    (Finnhub) resolver is untouched.

    GATED by the quarterly leg's own release-lag bound: `last_actual_release_date -
    last_reported_quarter_end` must sit in [_MIN, _MAX]_RELEASE_LAG_DAYS, else both are None.
    That rejects the reporting-gap race (annual results RELEASED, so Yahoo's '0y' has rolled,
    but the 10-K not yet FILED, so EDGAR still shows the third quarter and the rule would name
    the year that just ended). Missing input, a malformed fiscalYearEnd, or a failed gate ->
    None for both — the caller skips and counts (annual_yf_no_label), never a guess.

    CROSS-CHECKED against the company's own last 10-K: EDGAR's top-level fiscalYearEnd can be
    stale after a fiscal-year change (measured 2026-10-16: AEHR's 8-K of 2026-04-07 moved its
    year end from late May to late June and its last 10-K reportDate is 2026-05-29, yet EDGAR
    still reads "1231" -> labels 2026-12-31 against Yahoo's 2027-05-31). When the month of the
    year end implied by fiscalYearEnd differs from the month of the last 10-K's own period end
    (`cadence['last_annual_report_end']`, both snapped), one of the two facts is stale: skip,
    never guess. No 10-K on record (a recent IPO) -> no cross-check, behaviour unchanged.

    PURE and DETERMINISTIC in the EDGAR facts, with the one input that does move (the MMDD)
    absorbed by the snap, so no stabilization pass exists for it (contrast
    stabilize_period_end). The loop walks fiscal years forward from the last reported
    quarter's calendar year and exits at the first SNAPPED year end past the 30-day floor;
    two years reach it for every realistic calendar, the third is a defensive outer bound (a
    pure-function sweep test pins that the answer is always the first year end past the
    floor, whichever iteration finds it). A year end snapped back across New Year (0103 ->
    the preceding 12-31) is still found: the walk starts at last_q_end.year, and an earlier
    fiscal year's snapped end can never exceed the floor."""
    out: dict[str, Optional[date]] = {"0y": None, "+1y": None}
    last_q_end = cadence.get("last_reported_quarter_end")
    fye = cadence.get("fiscal_year_end")
    if last_q_end is None or last_actual_release_date is None or not fye:
        return out
    release_lag_days = (last_actual_release_date - last_q_end).days
    if not (_MIN_RELEASE_LAG_DAYS <= release_lag_days <= _MAX_RELEASE_LAG_DAYS):
        return out
    last_10k_end = cadence.get("last_annual_report_end")
    if last_10k_end is not None:
        implied = fiscal_quarter_end_from_label(4, last_10k_end.year, fye)
        # implied None (malformed fiscalYearEnd) -> fall through to the malformed handling below
        if implied is not None and (nearest_month_end(last_10k_end).month
                                    != nearest_month_end(implied).month):
            return out          # fiscalYearEnd disagrees with the last 10-K's own period end
    floor = last_q_end + timedelta(days=_ANNUAL_ROLL_BAND_DAYS)
    for year in range(last_q_end.year, last_q_end.year + 3):
        raw_year_end = fiscal_quarter_end_from_label(4, year, fye)
        if raw_year_end is None:
            return out          # malformed fiscalYearEnd is malformed for every year
        year_end = nearest_month_end(raw_year_end)   # the SNAP — see the docstring
        if year_end > floor:
            out["0y"] = year_end
            out["+1y"] = nearest_month_end(fiscal_quarter_end_from_label(4, year + 1, fye))
            return out
    return out


def next_earnings_date_from_yfinance(df: Any) -> Optional[date]:
    """The soonest date in a yfinance `earnings_dates` frame that has NO Reported EPS
    yet — yfinance's own live "next quarter to report," which is exactly what
    resolve_quarterly_period_ends anchors '0q' on. Defensive: any shape surprise
    (yfinance is unofficial and scraped) -> None, never a guess."""
    try:
        if df is None or df.empty or "Reported EPS" not in df.columns:
            return None
        pending = df[df["Reported EPS"].isna()]
        if pending.empty:
            return None
        idx = pending.index.min()
        return idx.date() if hasattr(idx, "date") else None
    except Exception:  # loud-ok: optional-parse fallback — yfinance is unofficial and
                        # scraped, any shape surprise here just means "unknown," never a guess
        return None


def last_actual_earnings_date_from_yfinance(df: Any) -> Optional[date]:
    """The MOST RECENT date in a yfinance `earnings_dates` frame that HAS a Reported
    EPS — this ticker's own last actual results RELEASE, the release-side half of
    resolve_quarterly_period_ends' release-to-release lag measurement (the other
    half, last_reported_quarter_end, is SEC EDGAR's reportDate for the SAME
    quarter). Defensive: any shape surprise -> None, never a guess."""
    try:
        if df is None or df.empty or "Reported EPS" not in df.columns:
            return None
        reported = df[df["Reported EPS"].notna()]
        if reported.empty:
            return None
        idx = reported.index.max()
        return idx.date() if hasattr(idx, "date") else None
    except Exception:  # loud-ok: optional-parse fallback — same defensive posture as
                        # next_earnings_date_from_yfinance just above
        return None


def _yf_period_row(df: Any, period: str) -> Optional[dict]:
    """One row of a yfinance revenue_estimate/earnings_estimate DataFrame -> a plain
    dict, or None when the frame is missing/empty/lacks the period (yfinance is
    unofficial and scraped — every shape is untrustworthy by default)."""
    try:
        if df is None or period not in df.index:
            return None
        return df.loc[period].to_dict()
    except Exception:  # loud-ok: optional-parse fallback — same as above, a shape
                        # surprise on a scraped frame degrades to "no row," not a guess
        return None


def normalize_yfinance_quarterly_estimate(
    *, ticker: str, yf_period: str, as_of: date,
    anchor_filing_date: Optional[date], period_end_date: Optional[date],
    revenue_row: Optional[dict], earnings_row: Optional[dict],
    period_label_method: str = LABEL_METHOD_YF_RECONSTRUCTED,
    fiscal_quarter: Optional[int] = None, fiscal_year: Optional[int] = None,
    period_type: str = "quarter",
) -> Optional[dict]:
    """One yfinance revenue_estimate/earnings_estimate period ('0q' or '+1q') -> one
    mi_analyst_estimates row, in the SAME shape every source's rows share — a
    future reader cannot tell which vendor a field came from without checking `source`
    (set to QUARTERLY_ESTIMATES_SOURCE here, FINNHUB_SOURCE for the Finnhub leg).
    Raw capture only: growth/yearAgoRevenue/yearAgoEps/currency are available on the
    yfinance frames but deliberately NOT stored — kept out to hold this row to the
    shape the (since removed) FMP annual leg had, which never carried them either
    (see the module docstring).

    v4: `period_label_method` records WHICH method produced `period_end_date` — the
    caller (snapshot_ticker) passes LABEL_METHOD_FINNHUB_FISCAL + this quarter's
    (fiscal_quarter, fiscal_year) when a Finnhub calendar entry CORROBORATED this
    slot (pair_finnhub_periods_to_slots) and overrode the reconstructed date;
    otherwise the default LABEL_METHOD_YF_RECONSTRUCTED with no fiscal label. This is
    the measurable half of "prefer Finnhub's label over the reconstruction" — a
    future reader can see exactly how often each method fired, rather than assuming.

    Returns None when the period end date could not be resolved (never store against
    a guessed date — the caller already enforces this by only calling with a resolved
    date, but the guard holds here too) or when neither vendor row has any data.
    Missing individual fields store as NULL, never 0 — zero is a claim, NULL is an
    absence (NaN, yfinance's own "missing" sentinel, is normalized to NULL too via
    _nan_to_none).

    `period_type` (2026-10-16) defaults to "quarter", so every existing caller is
    byte-identical; normalize_yfinance_annual_estimate passes "annual" so the annual leg
    shares THIS field mapping (one NaN/None policy, not two that can drift apart)."""
    if period_end_date is None:
        return None
    if not revenue_row and not earnings_row:
        return None
    revenue_row = revenue_row or {}
    earnings_row = earnings_row or {}
    return {
        "ticker": ticker,
        "as_of_date": as_of,
        "anchor_filing_date": anchor_filing_date,
        "valid_from_date": honest_valid_from(anchor_filing_date, as_of),
        "period_type": period_type,
        "period_end_date": period_end_date,
        "revenue_avg": _f(_nan_to_none(revenue_row.get("avg"))),
        "revenue_high": _f(_nan_to_none(revenue_row.get("high"))),
        "revenue_low": _f(_nan_to_none(revenue_row.get("low"))),
        "eps_avg": _f(_nan_to_none(earnings_row.get("avg"))),
        "eps_high": _f(_nan_to_none(earnings_row.get("high"))),
        "eps_low": _f(_nan_to_none(earnings_row.get("low"))),
        "num_analysts_revenue": _i(_nan_to_none(revenue_row.get("numberOfAnalysts"))),
        "num_analysts_eps": _i(_nan_to_none(earnings_row.get("numberOfAnalysts"))),
        "source": QUARTERLY_ESTIMATES_SOURCE,
        "recorder_version": RECORDER_VERSION,
        "analyst_count_available": True,
        "fiscal_quarter": fiscal_quarter, "fiscal_year": fiscal_year,
        "period_label_method": period_label_method,
    }


def normalize_yfinance_annual_estimate(
    *, ticker: str, yf_period: str, as_of: date,
    anchor_filing_date: Optional[date], period_end_date: Optional[date],
    revenue_row: Optional[dict], earnings_row: Optional[dict],
) -> Optional[dict]:
    """One yfinance '0y' or '+1y' period -> one mi_analyst_estimates row with
    period_type='annual', source='yfinance', period_label_method=LABEL_METHOD_YF_FISCAL_YEAR_END
    and NO fiscal_quarter/fiscal_year (those columns hold a vendor's raw label; this
    period end is derived — see the module docstring). Everything else — the raw-value
    mapping, NaN -> NULL, the honest-window stamp, the None-on-unresolved-date guard — is
    the quarterly builder's, by calling it. Returns None under the same conditions."""
    return normalize_yfinance_quarterly_estimate(
        ticker=ticker, yf_period=yf_period, as_of=as_of,
        anchor_filing_date=anchor_filing_date, period_end_date=period_end_date,
        revenue_row=revenue_row, earnings_row=earnings_row,
        period_label_method=LABEL_METHOD_YF_FISCAL_YEAR_END, period_type="annual",
    )


def _has_estimate(row: dict) -> bool:
    """True when a stored row carries an actual estimate (a revenue OR EPS average). An
    all-NaN frame row is stored as an all-NULL row — "we asked, the vendor had nothing" —
    but it must NOT count toward the annual coverage bar, or an empty leg could meet it.
    Zero counts: a vendor's 0 (AMLX '0y' revenue, 2026-10-16) is a stated forecast; the
    read-side question of how $0 reads on a growth axis is his, not this recorder's."""
    return row.get("revenue_avg") is not None or row.get("eps_avg") is not None


def normalize_finnhub_estimate(
    entry: dict, *, ticker: str, as_of: date, anchor_filing_date: Optional[date],
    period_end_date: date,
) -> dict:
    """One guard-passed Finnhub /calendar/earnings entry (see finnhub_period_end_from_entry
    — `entry` is {"date", "quarter", "year", "revenue_estimate", "eps_estimate"}, already
    normalized by _fetch_finnhub_calendar) -> one mi_analyst_estimates row.

    THE ONE GAP, stored explicitly rather than silently: Finnhub's calendar gives no
    high/low spread and NO ANALYST COUNT (verified live 2026-09-03, all 7 population
    tickers) — revenue_high/low and eps_high/low store NULL, and
    analyst_count_available=False marks that NULL as "this source never reports a
    count," never to be confused with num_analysts_revenue=None on a yfinance row
    (which means "we asked and the vendor had nothing"). estimate_for_scoring checks
    this flag explicitly so a future caller cannot apply the n<3 rule to it by
    accident."""
    return {
        "ticker": ticker,
        "as_of_date": as_of,
        "anchor_filing_date": anchor_filing_date,
        "valid_from_date": honest_valid_from(anchor_filing_date, as_of),
        "period_type": "quarter",
        "period_end_date": period_end_date,
        "revenue_avg": entry.get("revenue_estimate"), "revenue_high": None, "revenue_low": None,
        "eps_avg": entry.get("eps_estimate"), "eps_high": None, "eps_low": None,
        "num_analysts_revenue": None, "num_analysts_eps": None,
        "source": FINNHUB_SOURCE,
        "recorder_version": RECORDER_VERSION,
        "analyst_count_available": False,
        "fiscal_quarter": entry.get("quarter"), "fiscal_year": entry.get("year"),
        "period_label_method": LABEL_METHOD_FINNHUB_FISCAL,
    }


def compute_estimate_divergences(rows: "list[dict]") -> "list[dict]":
    """Where BOTH the yfinance and Finnhub quarterly legs land a row on the EXACT SAME
    (ticker, period_end_date, as_of_date) — i.e. the corroborated-override case in
    pair_finnhub_periods_to_slots, which is what makes their period_end_date identical
    in the first place — emit ONE divergence row carrying both sources' raw
    revenue_avg/eps_avg plus the plain difference (finnhub minus yfinance).

    NO THRESHOLD IS APPLIED OR CHOSEN HERE (operator instruction, 2026-09-03: three
    thresholds were invented and re-litigated this week) — this is a RAW capture for a
    distribution to be read in ~60 days, not a judgment. A missing value on either side
    stores a NULL diff, never a wrong number from treating a missing value as zero."""
    by_key: "dict[tuple, dict[str, dict]]" = {}
    for r in rows:
        if r.get("period_type") != "quarter":
            continue
        source = r.get("source")
        if source not in (QUARTERLY_ESTIMATES_SOURCE, FINNHUB_SOURCE):
            continue
        key = (r["ticker"], r["period_end_date"], r["as_of_date"])
        by_key.setdefault(key, {})[source] = r
    out: "list[dict]" = []
    for (ticker, period_end_date, as_of_date), sources in by_key.items():
        yf_row = sources.get(QUARTERLY_ESTIMATES_SOURCE)
        fh_row = sources.get(FINNHUB_SOURCE)
        if yf_row is None or fh_row is None:
            continue
        yf_rev, fh_rev = yf_row.get("revenue_avg"), fh_row.get("revenue_avg")
        yf_eps, fh_eps = yf_row.get("eps_avg"), fh_row.get("eps_avg")
        out.append({
            "ticker": ticker, "as_of_date": as_of_date, "period_type": "quarter",
            "period_end_date": period_end_date,
            "yfinance_revenue_avg": yf_rev, "finnhub_revenue_avg": fh_rev,
            "revenue_diff": (fh_rev - yf_rev) if (fh_rev is not None and yf_rev is not None)
                            else None,
            "yfinance_eps_avg": yf_eps, "finnhub_eps_avg": fh_eps,
            "eps_diff": (fh_eps - yf_eps) if (fh_eps is not None and yf_eps is not None)
                        else None,
        })
    return out


def estimate_for_scoring(
    row: dict, min_analysts: int = MIN_ANALYSTS_DEFAULT
) -> Optional[dict]:
    """READ-SIDE neglect rule (the sketch's contract, mutation-tested): a thin-coverage
    estimate scores None — the missing-data scaling absorbs it; never penalize the
    un-covered. The count is STORED on every row so this threshold can be re-tuned
    without re-fetching. An unknown count is thin by definition (None, not 0 analysts,
    but either way not >= min_analysts).

    THE LINE: no live path calls this today — it exists so the future #333 axis has ONE
    sanctioned accessor instead of re-deriving the rule per caller.

    v4: `analyst_count_available is False` (Finnhub calendar rows — see
    normalize_finnhub_estimate) short-circuits to None EXPLICITLY, in code, not just by
    the `n is None` fallthrough below — the intent (this source structurally never
    reports a count, so its NULL must never be read as "we asked and it was low") is
    the thing a future maintainer needs to see here, not infer from a side effect.
    """
    if row.get("analyst_count_available") is False:
        return None
    n = row.get("num_analysts_revenue")
    if n is None or n < min_analysts:
        return None
    return row


# ── anchor fetch (SEC EDGAR — keyless, $0, no payment tier) ───────────────────────────

async def _edgar_get_json(url: str) -> Any:
    import httpx

    from agents.market_intelligence.collector import _SEC_UA
    # ⚠ KNOWN, MEASURED, DELIBERATELY NOT FIXED HERE: this opens a fresh connection per call —
    # ~100 TLS handshakes on the daily run (est. 5-20s) and ~335 on the backfill. Reusing one
    # client means threading it through snapshot_ticker and _fetch_last_filing_date, both of
    # which the test suite monkeypatches by signature. Seconds on a once-a-day job did not
    # justify churning those the day after this module shipped. Revisit if the population grows.
    async with httpx.AsyncClient(
        timeout=_EDGAR_TIMEOUT_SECONDS, headers=_SEC_UA
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


async def _get_cik_map(as_of: date) -> Optional[dict]:
    """Ticker->CIK map, fetched AT MOST ONCE per as_of day (success or failure) —
    a dead sec.gov costs the run one timeout, never one per ticker. None = the map
    is unavailable today; callers raise so the failure is COUNTED per ticker
    (anchor_errors), distinguishing an EDGAR outage from true non-filers."""
    if _cik_map_state["as_of"] == as_of:
        return _cik_map_state["map"]
    _cik_map_state["as_of"] = as_of
    _cik_map_state["map"] = None
    try:
        raw = await _edgar_get_json(_EDGAR_TICKER_MAP_URL)
        _cik_map_state["map"] = {
            str(v["ticker"]).upper(): int(v["cik_str"]) for v in raw.values()
        }
    except Exception as e:
        logger.warning(f"EDGAR ticker map fetch failed: "
                       f"{redact_secrets(f'{type(e).__name__}: {e}')}")
    return _cik_map_state["map"]


# One EDGAR submissions payload fetched AT MOST ONCE per (ticker, as_of day), reduced
# IMMEDIATELY to the small set of dates this module needs, then discarded — deliberately
# NOT caching the raw payload (a single ticker's submissions JSON can run past 1MB; the
# backfill touches ~335 tickers in one run, so retaining all of them would be real memory).
# Both _fetch_last_filing_date (the honesty-window anchor) and _fetch_quarter_cadence_facts
# (the v3 quarterly-leg cadence facts) read this cache, so one ticker never costs SEC EDGAR
# two requests for the same information. {"as_of": date|None, "facts": {ticker: dict}}.
_edgar_facts_cache_state: dict[str, Any] = {"as_of": None, "facts": {}}


async def _get_edgar_facts(ticker: str, as_of: date) -> dict[str, Any]:
    """Fetch this ticker's EDGAR submissions payload (at most once per ticker per
    as_of day) and immediately reduce it to {"anchor_filing_date": ..., plus the
    quarterly_cadence_facts keys}. None-CIK (ETF/non-filer) resolves to all-None
    facts, not an exception. Raises on transport failure (NOT cached as a failure —
    each ticker is only visited once per run anyway) so the caller can COUNT it
    (anchor_errors); the caller still records the ticker with a zero window rather
    than aborting the snapshot."""
    if _edgar_facts_cache_state["as_of"] != as_of:
        _edgar_facts_cache_state["as_of"] = as_of
        _edgar_facts_cache_state["facts"] = {}
    cache = _edgar_facts_cache_state["facts"]
    key = ticker.upper()
    if key in cache:
        return cache[key]
    cik_map = await _get_cik_map(as_of)
    if cik_map is None:
        raise RuntimeError("EDGAR ticker map unavailable")
    cik = cik_map.get(key)
    if cik is None:
        # ETF / preferred / non-filer — zero honest days AND no cadence facts, by design.
        facts = {"anchor_filing_date": None, **_EMPTY_CADENCE_FACTS}
        cache[key] = facts
        return facts
    payload = await _edgar_get_json(_EDGAR_SUBMISSIONS_URL.format(cik=cik))
    facts = {"anchor_filing_date": latest_filing_from_submissions(payload),
             **quarterly_cadence_facts(payload)}
    cache[key] = facts
    return facts


async def _fetch_last_filing_date(ticker: str, as_of: date) -> Optional[date]:
    """The ticker's most recent anchor-form EDGAR filing date — the honest-window
    anchor. None = the ticker genuinely resolves no filing (not in EDGAR's map, or
    no anchor-form filing) -> zero honest window BY DESIGN. Raises on transport
    failure so the caller can COUNT it (anchor_errors) — but the caller still
    records the ticker with a zero window; no anchor path aborts a snapshot.

    v1 used FMP /income-statement filingDate; it is 402 on our plan (2026-09-01,
    99/99 tickers) — never call it again."""
    facts = await _get_edgar_facts(ticker, as_of)
    return facts["anchor_filing_date"]


async def _fetch_quarter_cadence_facts(ticker: str, as_of: date) -> dict[str, Optional[date]]:
    """The v3 quarterly-leg cadence facts (see quarterly_cadence_facts) for this
    ticker — shares the SAME EDGAR fetch as _fetch_last_filing_date via
    _get_edgar_facts, so this never costs a second network round trip. Raises on
    transport failure exactly like _fetch_last_filing_date (same underlying call);
    snapshot_ticker calls both inside one try block, so an EDGAR outage degrades
    ONE ticker's whole anchor story (annual window AND quarterly cadence) together,
    never independently."""
    facts = await _get_edgar_facts(ticker, as_of)
    return {k: v for k, v in facts.items() if k != "anchor_filing_date"}


# ── quarterly estimates fetch (v3 — yfinance, unofficial and scraped) ────────────────
# THE LINE for this function specifically: every failure mode here (import error, bad
# ticker, timeout, malformed frame, scrape breakage) returns None. It never raises past
# this function and never touches the Finnhub leg — see snapshot_ticker's call site.

async def _fetch_yfinance_quarterly(ticker: str) -> Optional[dict[str, Any]]:
    """revenue_estimate + earnings_estimate + earnings_dates via yfinance, for the two
    quarterly periods ('0q','+1q') plus the next scheduled earnings date AND the last
    actual release date (resolve_quarterly_period_ends needs both — see
    next_earnings_date_from_yfinance / last_actual_earnings_date_from_yfinance).
    Uses the same run_in_executor + wait_for shape as fundamentals.get_fundamentals —
    this repo's house pattern for calling this synchronous, scraped library from
    async code. Returns None (never raises) on any failure, or when neither period has
    any data at all; otherwise {"next_earnings_date": date|None,
    "last_actual_release_date": date|None,
    "periods": {"0q"|"+1q": {"revenue": dict|None, "earnings": dict|None}},
    "annual_periods": {"0y"|"+1y": {"revenue": dict|None, "earnings": dict|None}}}.

    2026-10-16: `annual_periods` is read out of the SAME two frames (they carry '0y'/'+1y'
    beside '0q'/'+1q' — one cached earningsTrend fetch), so it adds ZERO Yahoo requests; a
    test spies the Ticker attribute accesses. It is {} when the frames lack both annual
    periods. It does NOT take part in the `return None` decision: "unavailable" still
    means "no QUARTERLY period", exactly as before, so a quarterly counter keeps its
    meaning and an annual-only frame stays unavailable (annual rows ride only with quarterly)."""
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        loop = asyncio.get_event_loop()
        t = yf.Ticker(ticker.upper())
    except Exception as e:
        logger.warning(f"yfinance Ticker init failed for {ticker}: "
                       f"{redact_secrets(f'{type(e).__name__}: {e}')}")
        return None

    def _fetch_revenue():
        return t.revenue_estimate

    def _fetch_earnings():
        return t.earnings_estimate

    def _fetch_earnings_dates():
        return t.earnings_dates

    try:
        revenue_df, earnings_df, dates_df = await asyncio.gather(
            asyncio.wait_for(loop.run_in_executor(None, _fetch_revenue),
                              timeout=_YF_QUARTER_TIMEOUT_SECONDS),
            asyncio.wait_for(loop.run_in_executor(None, _fetch_earnings),
                              timeout=_YF_QUARTER_TIMEOUT_SECONDS),
            asyncio.wait_for(loop.run_in_executor(None, _fetch_earnings_dates),
                              timeout=_YF_QUARTER_TIMEOUT_SECONDS),
            return_exceptions=True,
        )
    except Exception as e:  # loud-ok: gather itself failing is as good as every leg failing
        logger.warning(f"yfinance quarterly gather failed for {ticker}: "
                       f"{redact_secrets(f'{type(e).__name__}: {e}')}")
        return None
    if isinstance(revenue_df, Exception):
        logger.warning(f"yfinance revenue_estimate failed for {ticker}: "
                       f"{redact_secrets(f'{type(revenue_df).__name__}: {revenue_df}')}")
        revenue_df = None
    if isinstance(earnings_df, Exception):
        logger.warning(f"yfinance earnings_estimate failed for {ticker}: "
                       f"{redact_secrets(f'{type(earnings_df).__name__}: {earnings_df}')}")
        earnings_df = None
    if isinstance(dates_df, Exception):
        logger.warning(f"yfinance earnings_dates failed for {ticker}: "
                       f"{redact_secrets(f'{type(dates_df).__name__}: {dates_df}')}")
        dates_df = None

    periods: dict[str, Any] = {}
    for period in _YF_QUARTER_PERIODS:
        rev_row = _yf_period_row(revenue_df, period)
        earn_row = _yf_period_row(earnings_df, period)
        if rev_row is None and earn_row is None:
            continue
        periods[period] = {"revenue": rev_row, "earnings": earn_row}
    if not periods:
        return None
    annual_periods: dict[str, Any] = {}
    for period in _YF_ANNUAL_PERIODS:
        rev_row = _yf_period_row(revenue_df, period)
        earn_row = _yf_period_row(earnings_df, period)
        if rev_row is None and earn_row is None:
            continue
        annual_periods[period] = {"revenue": rev_row, "earnings": earn_row}
    return {"next_earnings_date": next_earnings_date_from_yfinance(dates_df),
            "last_actual_release_date": last_actual_earnings_date_from_yfinance(dates_df),
            "periods": periods, "annual_periods": annual_periods}


# ── Finnhub /calendar/earnings fetch (v4 — the second estimates source) ──────────────
# THE LINE for this whole section, mirroring _fetch_yfinance_quarterly exactly: every
# failure mode (missing key, network error, bad status, malformed shape, empty
# calendar) degrades to None/nothing-recorded-and-counted. It NEVER raises past
# _fetch_finnhub_calendar and never touches the yfinance leg.

_finnhub_pace_lock = asyncio.Lock()
_finnhub_last_call_state: dict[str, float] = {"t": 0.0}


async def _finnhub_get(path: str, params: dict) -> Any:
    """Bespoke Finnhub GET — deliberately NOT collector._fmp_get: that helper routes
    every failure through llm_health.maybe_alert_api_failure, which CAN Telegram, and
    this recorder is SILENT on every path (THE LINE, top of the module). Authenticates
    by QUERY STRING (`?token=`), exactly like FMP's `?apikey=` — shared.secret_redaction
    already covers `token=` (verified + pinned, 2026-09-03).

    Reads and logs the response BODY (redacted) on an HTTP error, never just the
    status — the FMP lesson (2026-09-03 root cause write-up): a 402/403 can mean a
    parameter restriction, not a rate breach, and the body text is the only way to
    tell them apart.

    FINNHUB_PACE_SECONDS is a REAL elapsed-time throttle (mirrors
    collector._polygon_get's last-call-timestamp pattern) — see the module docstring's
    PACING section for why it costs ~0 wall time today but is real protection for a
    future parallel caller (e.g. a backfill)."""
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        raise RuntimeError("FINNHUB_API_KEY not set")
    import httpx
    async with _finnhub_pace_lock:
        now = asyncio.get_event_loop().time()
        elapsed = now - _finnhub_last_call_state["t"]
        if elapsed < FINNHUB_PACE_SECONDS:
            await asyncio.sleep(FINNHUB_PACE_SECONDS - elapsed)
        try:
            async with httpx.AsyncClient(timeout=_FINNHUB_TIMEOUT_SECONDS) as client:
                r = await client.get(f"{FINNHUB_BASE}{path}",
                                     params={"token": api_key, **params})
                r.raise_for_status()
                return r.json()
        except Exception as e:
            body = ""
            resp = getattr(e, "response", None)
            if resp is not None:
                try:
                    body = f" body={redact_secrets(resp.text[:300])}"
                except Exception:  # loud-ok: best-effort diagnostic extra, never the
                    pass          # reason this call fails
            logger.warning(f"Finnhub GET {path} failed: "
                           f"{redact_secrets(f'{type(e).__name__}: {e}')}{body}")
            raise
        finally:
            _finnhub_last_call_state["t"] = asyncio.get_event_loop().time()


async def _fetch_finnhub_calendar(ticker: str, as_of: date) -> "Optional[list[dict]]":
    """Finnhub /calendar/earnings for one ticker -> a bounded, filtered, sorted list of
    forward-looking entries ({"date", "quarter", "year", "revenue_estimate",
    "eps_estimate"}), or None on ANY failure/empty result — see the section banner
    above. Filters out anything already reported (epsActual/revenueActual not both
    None) or dated before `as_of` — defensive; the from=/to= window already asks for
    forward-only, but a vendor response should never be trusted to match its own
    request. Sorted ascending by date, capped at _FINNHUB_MAX_PERIODS."""
    try:
        payload = await _finnhub_get("/calendar/earnings", {
            "symbol": ticker.upper(),
            "from": as_of.isoformat(),
            "to": (as_of + timedelta(days=_FINNHUB_CALENDAR_WINDOW_DAYS)).isoformat(),
        })
    except Exception:  # loud-ok: _finnhub_get's own except already fired
        # logger.warning (with the redacted response body) before re-raising here —
        # logging again would just duplicate the same line.
        return None
    try:
        raw = payload.get("earningsCalendar") if isinstance(payload, dict) else None
        if not isinstance(raw, list):
            return None
        entries: list[dict] = []
        for rec in raw:
            if not isinstance(rec, dict):
                continue
            if rec.get("epsActual") is not None or rec.get("revenueActual") is not None:
                continue   # already reported — not a forward estimate
            edate = _d(rec.get("date"))
            if edate is None or edate < as_of:
                continue
            revenue = _f(_nan_to_none(rec.get("revenueEstimate")))
            eps = _f(_nan_to_none(rec.get("epsEstimate")))
            if revenue is None and eps is None:
                continue
            entries.append({
                "date": edate, "quarter": _i(rec.get("quarter")), "year": _i(rec.get("year")),
                "revenue_estimate": revenue, "eps_estimate": eps,
            })
        entries.sort(key=lambda e: e["date"])
        return entries[:_FINNHUB_MAX_PERIODS] if entries else None
    except Exception as e:  # loud-ok: optional-parse fallback — a vendor response is
        # untrusted by default, exactly like the yfinance leg's own shape guards
        logger.warning(f"Finnhub calendar parse failed for {ticker}: "
                       f"{redact_secrets(f'{type(e).__name__}: {e}')}")
        return None


async def snapshot_ticker(ticker: str, as_of: date) -> dict[str, Any]:
    """Fetch + normalize one ticker's estimates. Returns {rows, anchor, anchor_error,
    quarter_yf_rows, quarter_yf_unavailable, quarter_yf_no_cadence,
    quarter_finnhub_rows, quarter_finnhub_unavailable, quarter_finnhub_no_cadence,
    divergences, annual_yf_rows, annual_yf_informative, annual_yf_no_label}
    (per-ticker isolation lives in the run loop, not here). The anchor
    NEVER aborts: an unresolvable or failed anchor records the rows with a zero
    honest window (the 2026-09-01 first-run bug was exactly this abort). The v3
    quarterly (yfinance) leg and the v4 Finnhub leg are equally non-fatal: any
    failure in either degrades to nothing-recorded-and-counted and never touches
    the other — Finnhub's own row does not even depend on yfinance succeeding
    (see the module docstring's "PREFER, NEVER REQUIRE")."""
    anchor: Optional[date] = None
    quarter_cadence: dict[str, Any] = dict(_EMPTY_CADENCE_FACTS)
    anchor_error = False
    try:
        anchor = await _fetch_last_filing_date(ticker, as_of)
        quarter_cadence = await _fetch_quarter_cadence_facts(ticker, as_of)
    except Exception as e:
        # FIRST-CLASS no-anchor: zero honest window (annual leg) + no cadence facts
        # (quarterly leg), counted, never fatal. One EDGAR outage degrades this
        # ticker's whole anchor story, not two independent ones (both calls share
        # the same underlying fetch — see _get_edgar_facts).
        anchor_error = True
        logger.warning(f"anchor fetch failed for {ticker} (zero honest window): "
                       f"{redact_secrets(f'{type(e).__name__}: {e}')}")
    # ⏱ THE YFINANCE AND FINNHUB LEGS RUN CONCURRENTLY (2026-09-02, extended 2026-09-03).
    # Different vendors with independent rate limits, so running either in series behind the
    # other just adds latency to every ticker. Launched as tasks, awaited only where their
    # results are needed. Neither can take the run down: both fetch functions catch
    # everything internally.
    _yf_task = asyncio.ensure_future(_fetch_yfinance_quarterly(ticker))
    _finnhub_task = asyncio.ensure_future(_fetch_finnhub_calendar(ticker, as_of))

    rows: list[dict] = []

    # ── Finnhub leg (v4) — guard-passed period_ends, independent of yfinance's fate ──
    quarter_finnhub_unavailable = False
    quarter_finnhub_no_cadence = False
    finnhub_rows: list[dict] = []
    finnhub_row_by_idx: dict[int, dict] = {}   # index into finnhub_raw/finnhub_period_ends
                                                 # -> the row dict already inside `rows`
                                                 # (same object, mutated in place below when
                                                 # stabilize_period_end reuses an older date)
    finnhub_period_ends: list[Optional[date]] = []
    try:
        finnhub_raw = await _finnhub_task   # started above, concurrently with the yfinance fetch
    except Exception as e:  # belt-and-suspenders: _fetch_finnhub_calendar already catches
        # everything internally and returns None, but this leg must NEVER be able to
        # take the yfinance leg down with it if that contract slips.
        finnhub_raw = None
        logger.warning(f"Finnhub calendar fetch failed for {ticker} (yfinance "
                       f"rows unaffected): {redact_secrets(f'{type(e).__name__}: {e}')}")
    if not finnhub_raw:
        quarter_finnhub_unavailable = True
    else:
        fiscal_year_end = quarter_cadence.get("fiscal_year_end")
        last_q_end = quarter_cadence.get("last_reported_quarter_end")
        # `finnhub_period_ends` keeps the FRESH guard-passed dates: they, not the
        # stabilized ones below, feed pair_finnhub_periods_to_slots (which slot a Finnhub
        # entry corroborates is unchanged). The yfinance block then starts a corroborated
        # slot's candidate from the STORED row's date (finnhub_row_by_idx), so both
        # sources share one key on a drift night.
        for entry in finnhub_raw:
            finnhub_period_ends.append(finnhub_period_end_from_entry(
                entry["date"], entry.get("quarter"), entry.get("year"),
                fiscal_year_end, last_q_end))
        # STABILITY (#333, 2026-10-17) — the STORED Finnhub row reuses this ticker's own
        # already-stored Finnhub date within _STABILIZE_TOLERANCE_DAYS, the same
        # stabilize_period_end the yfinance rows get, against ITS OWN source's history
        # (source=FINNHUB_SOURCE, never yfinance: a 15-day window must not pull a Finnhub
        # label onto an uncorroborated yfinance reconstruction). The fresh label is a pure
        # function of (quarter, year, EDGAR fiscalYearEnd MMDD) and that MMDD drifts a day
        # or two at the first-quarter 10-Q of a 52/53-week filer (COST 0831 -> 0830, AAPL
        # 0927 -> 0926), which would otherwise split one fiscal quarter's revision series
        # across two keys. ONE read per ticker per run (not per entry); a read failure
        # degrades to "no history", exactly like the yfinance read below.
        finnhub_recent_period_ends: list[date] = []
        if any(pe is not None for pe in finnhub_period_ends):
            try:
                finnhub_recent_period_ends = await get_recent_quarterly_period_ends(
                    ticker, as_of - timedelta(days=_STABILIZE_LOOKBACK_DAYS),
                    source=FINNHUB_SOURCE)
            except Exception as e:
                logger.warning(f"recent Finnhub period-end lookup failed for {ticker} "
                               f"(today's Finnhub labels may drift; self-heals next run): "
                               f"{redact_secrets(f'{type(e).__name__}: {e}')}")
        for i, entry in enumerate(finnhub_raw):
            fresh_period_end = finnhub_period_ends[i]
            if fresh_period_end is None:
                continue
            row = normalize_finnhub_estimate(
                entry, ticker=ticker, as_of=as_of, anchor_filing_date=anchor,
                period_end_date=stabilize_period_end(
                    fresh_period_end, finnhub_recent_period_ends))
            finnhub_rows.append(row)
            finnhub_row_by_idx[i] = row
        if not finnhub_rows:
            # Finnhub HAD calendar entries but none passed the self-consistency guards
            # (finnhub_period_end_from_entry) — e.g. no EDGAR fiscal_year_end resolved,
            # or the derived date failed the lag/EDGAR sanity bounds. Skipped and
            # counted, never stored against an unverified label.
            quarter_finnhub_no_cadence = True
    rows.extend(finnhub_rows)

    # ── quarterly leg (v3, yfinance) — never raises past this block ──────────────────
    quarter_yf_unavailable = False
    quarter_no_cadence = False
    quarter_rows: list[dict] = []
    annual_rows: list[dict] = []        # 2026-10-16 annual leg — see the block after the quarter loop
    annual_no_label = False
    try:
        yf_data = await _yf_task          # started above, concurrently with the Finnhub fetch
    except Exception as e:  # belt-and-suspenders: _fetch_yfinance_quarterly already
        # catches everything internally and returns None, but this leg must NEVER be
        # able to take the Finnhub rows down with it even if that contract slips.
        yf_data = None
        logger.warning(f"yfinance quarterly fetch failed for {ticker} (Finnhub rows "
                       f"unaffected): {redact_secrets(f'{type(e).__name__}: {e}')}")
    if not yf_data:
        quarter_yf_unavailable = True
    else:
        resolved = resolve_quarterly_period_ends(
            yf_data.get("next_earnings_date"), yf_data.get("last_actual_release_date"),
            quarter_cadence)
        # v4: does a guard-passed Finnhub period_end CORROBORATE this ticker's own
        # reconstructed '0q'/'+1q' candidate (see pair_finnhub_periods_to_slots)? Only
        # a corroborated slot's period_end_date is OVERRIDDEN with Finnhub's — "prefer
        # its label, never require it" (module docstring). No match for a slot leaves
        # the reconstruction untouched, exactly as if Finnhub did not cover this ticker.
        paired = pair_finnhub_periods_to_slots(finnhub_period_ends, resolved)
        # STABILITY (see stabilize_period_end): reuse an already-recorded date for this
        # SAME quarter rather than minting a slightly-different one from today's live
        # inputs. A read failure here degrades to "no history to check" — today's
        # labels may drift, but nothing aborts, and it self-heals the moment the read
        # succeeds again.
        recent_period_ends: list[date] = []
        try:
            recent_period_ends = await get_recent_quarterly_period_ends(
                ticker, as_of - timedelta(days=_STABILIZE_LOOKBACK_DAYS))
        except Exception as e:
            logger.warning(f"recent period-end lookup failed for {ticker} (today's "
                           f"quarterly labels may drift; self-heals next run): "
                           f"{redact_secrets(f'{type(e).__name__}: {e}')}")
        for period, payload in yf_data["periods"].items():
            match_idx = paired.get(period)
            if match_idx is not None:
                matched = finnhub_raw[match_idx]
                # #333: the candidate is the Finnhub row's own STORED date (already
                # stabilized against ITS history above), not today's fresh label. On a
                # drift night the two sources therefore start from ONE key for this
                # quarter; the stabilize below then only has to reconcile it with
                # yfinance's own history. Using the fresh label here instead leaves the
                # yfinance row on the fresh date and the Finnhub row on the established
                # one, with `period_end == candidate` so no realign fires — the
                # divergence join for that quarter would stay split for good.
                candidate = finnhub_row_by_idx[match_idx]["period_end_date"]
                label_method = LABEL_METHOD_FINNHUB_FISCAL
                fiscal_quarter, fiscal_year = matched.get("quarter"), matched.get("year")
            else:
                candidate = resolved.get(period)
                label_method = LABEL_METHOD_YF_RECONSTRUCTED
                fiscal_quarter, fiscal_year = None, None
            period_end = stabilize_period_end(candidate, recent_period_ends)
            if match_idx is not None and period_end != candidate:
                # stabilize_period_end REUSED an already-recorded date instead of
                # today's fresh Finnhub-derived candidate (stabilize_period_end's own
                # rule: "a quarter's label is set by whichever run FIRST sees it ...
                # and held from then on"). Without this, the Finnhub row (built above
                # from `candidate`, before stabilization ran) and this yfinance row
                # would carry TWO DIFFERENT period_end_date keys for the SAME real
                # quarter — fracturing the very revision series stabilize_period_end
                # exists to protect, AND silently killing the divergence join for
                # this quarter forever (compute_estimate_divergences matches on exact
                # key equality). Realign the Finnhub row (same dict object already in
                # `rows` — mutating it here updates it everywhere) to the series'
                # established key; label_method stays Finnhub's, since Finnhub still
                # identified WHICH quarter this is, even though the established date
                # (set by whichever source labelled it first) wins as the stored key.
                finnhub_row_by_idx[match_idx]["period_end_date"] = period_end
            row = normalize_yfinance_quarterly_estimate(
                ticker=ticker, yf_period=period, as_of=as_of,
                anchor_filing_date=anchor, period_end_date=period_end,
                revenue_row=payload.get("revenue"), earnings_row=payload.get("earnings"),
                period_label_method=label_method,
                fiscal_quarter=fiscal_quarter, fiscal_year=fiscal_year,
            )
            if row is not None:
                quarter_rows.append(row)
        if not quarter_rows:
            # yfinance HAD data for this ticker but no period could be resolved to an
            # absolute date (no cadence facts, or every candidate failed the sanity
            # bounds) — skipped and counted, never stored against a guessed date.
            quarter_no_cadence = True
        # ── annual leg (2026-10-16, yfinance '0y'/'+1y') — same frames, zero extra requests ──
        # Reads nothing the quarterly block above produced and writes nothing it reads: the
        # label comes from EDGAR facts + yfinance's last release date alone
        # (resolve_annual_period_ends), so a quarterly skip/override/stabilization cannot move
        # it, and this block cannot move a quarterly row, counter or the divergence join.
        annual_payloads = yf_data.get("annual_periods") or {}
        if annual_payloads:
            annual_period_ends = resolve_annual_period_ends(
                yf_data.get("last_actual_release_date"), quarter_cadence)
            for period, payload in annual_payloads.items():
                row = normalize_yfinance_annual_estimate(
                    ticker=ticker, yf_period=period, as_of=as_of,
                    anchor_filing_date=anchor, period_end_date=annual_period_ends.get(period),
                    revenue_row=payload.get("revenue"), earnings_row=payload.get("earnings"),
                )
                if row is not None:
                    annual_rows.append(row)
            if not annual_rows:
                # The frames HAD annual data but no fiscal year end could be resolved
                # (no EDGAR fiscalYearEnd/last quarter, the reporting-gap gate, or EDGAR's year
                # end disagreeing with the last 10-K's own period, e.g. AEHR) — skipped
                # and counted, never stored against a guessed date.
                annual_no_label = True
    rows.extend(quarter_rows)
    rows.extend(annual_rows)

    # v4: raw values from BOTH sources are already in `rows` — surface where they
    # disagree on the SAME real quarter (see compute_estimate_divergences; only fires
    # when the corroborated-override above made their period_end_date identical).
    divergences = compute_estimate_divergences(rows)

    return {"rows": rows,
            "anchor": anchor, "anchor_error": anchor_error,
            "quarter_yf_rows": len(quarter_rows),
            "quarter_yf_unavailable": quarter_yf_unavailable,
            "quarter_yf_no_cadence": quarter_no_cadence,
            "quarter_finnhub_rows": len(finnhub_rows),
            "quarter_finnhub_unavailable": quarter_finnhub_unavailable,
            "quarter_finnhub_no_cadence": quarter_finnhub_no_cadence,
            "divergences": divergences,
            "annual_yf_rows": len(annual_rows),
            "annual_yf_informative": any(_has_estimate(r) for r in annual_rows),
            "annual_yf_no_label": annual_no_label}


# ── run functions (never raise into the scheduler — the house shadow contract) ────────

async def _run_over_tickers(tickers: list[str], as_of: date, label: str) -> dict[str, Any]:
    out = {"population": len(tickers), "tickers_written": 0, "rows_written": 0,
           "no_anchor": 0, "anchor_errors": 0,
           "errors": 0,
           "quarter_yf_rows_written": 0, "quarter_yf_unavailable": 0,
           "quarter_yf_no_cadence": 0,
           "quarter_finnhub_rows_written": 0, "quarter_finnhub_unavailable": 0,
           "quarter_finnhub_no_cadence": 0, "divergence_rows_written": 0,
           # annual leg (2026-10-16). annual_yf_tickers / quarter_yf_tickers IS the
           # pre-registered bar: tickers with an annual estimate / tickers with quarterly rows.
           "annual_yf_rows_written": 0, "annual_yf_no_label": 0,
           "annual_yf_tickers": 0, "quarter_yf_tickers": 0}
    for i, ticker in enumerate(tickers):
        if i:
            # Between tickers, not after the last: the cadence the FMP sleeps used to impose
            # on every vendor (see YFINANCE_PACE_SECONDS).
            await asyncio.sleep(YFINANCE_PACE_SECONDS)
        try:
            snap = await snapshot_ticker(ticker, as_of)
            written = await upsert_analyst_estimates(snap["rows"])
            out["rows_written"] += written
            if written:
                out["tickers_written"] += 1
            out["quarter_yf_rows_written"] += snap["quarter_yf_rows"]
            if snap["quarter_yf_unavailable"]:
                out["quarter_yf_unavailable"] += 1   # yfinance outage/empty for this ticker
            if snap["quarter_yf_no_cadence"]:
                out["quarter_yf_no_cadence"] += 1    # yfinance had data, period end unresolvable
            out["quarter_finnhub_rows_written"] += snap["quarter_finnhub_rows"]
            if snap["quarter_finnhub_unavailable"]:
                out["quarter_finnhub_unavailable"] += 1   # Finnhub outage/empty for this ticker
            if snap["quarter_finnhub_no_cadence"]:
                out["quarter_finnhub_no_cadence"] += 1    # entries existed, no guard-passed label
            if snap["divergences"]:
                out["divergence_rows_written"] += await upsert_analyst_estimates_divergence(
                    snap["divergences"])
            # annual leg counters — after the write, like the quarterly ones above
            out["annual_yf_rows_written"] += snap["annual_yf_rows"]
            if snap["annual_yf_no_label"]:
                out["annual_yf_no_label"] += 1       # annual frames present, fiscal year end unresolvable
            if snap["quarter_yf_rows"]:
                out["quarter_yf_tickers"] += 1       # the bar's denominator
                if snap["annual_yf_informative"]:
                    out["annual_yf_tickers"] += 1    # the bar's numerator (a stated estimate, not an empty row)
            if snap["anchor_error"]:
                out["anchor_errors"] += 1        # EDGAR outage — NOT the by-design case
            elif snap["anchor"] is None:
                out["no_anchor"] += 1            # true non-filer/ETF — zero days by design
        except Exception as e:  # per-ticker isolation: one bad name never kills the run
            out["errors"] += 1
            logger.warning(redact_secrets(
                f"{label}: {ticker} failed: {type(e).__name__}: {e}"))
            try:
                await log_audit_event(
                    "analyst_estimates_error",
                    f"{label}: {ticker}: {type(e).__name__}: {e}"[:400],
                )
            except Exception:  # loud-ok: logger.warning above already fired
                pass
    if tickers and out["quarter_yf_rows_written"] == 0:
        # The primary source recorded NOTHING for the whole run. With the FMP leg gone this is
        # the one place a yfinance failure speaks for itself: _fetch_yfinance_quarterly returns
        # None on every failure by contract, so per ticker it is indistinguishable from "no
        # coverage" (an ETF) and a per-ticker row would be noise. A run-level zero is not
        # ambiguous: Yahoo throttled/changed shape, or EDGAR cadence facts were down for the
        # whole population. Finnhub rows may still have landed and still advance the
        # as_of_date count — but they carry no analyst count, so nothing the n_analysts<3
        # rule can use was recorded tonight. One audit row; SILENT (no Telegram) like the rest.
        msg = (f"{label}: yfinance wrote 0 quarterly rows for {out['population']} ticker(s) "
               f"({out['quarter_yf_unavailable']} unavailable, {out['quarter_yf_no_cadence']} "
               f"no-cadence-anchor, {out['anchor_errors']} EDGAR anchor-error); Finnhub wrote "
               f"{out['quarter_finnhub_rows_written']} row(s), which carry no analyst count — "
               f"tonight added nothing the n_analysts<3 rule can admit")
        logger.warning(redact_secrets(msg))
        try:
            await log_audit_event("analyst_estimates_error", msg[:400])
        except Exception:  # loud-ok: logger.warning above already fired
            pass
    return out


_EMPTY_RUN = {"population": 0, "tickers_written": 0, "rows_written": 0,
              "no_anchor": 0, "anchor_errors": 0,
              "errors": 1,
              "quarter_yf_rows_written": 0, "quarter_yf_unavailable": 0,
              "quarter_yf_no_cadence": 0,
              "quarter_finnhub_rows_written": 0, "quarter_finnhub_unavailable": 0,
              "quarter_finnhub_no_cadence": 0, "divergence_rows_written": 0,
              "annual_yf_rows_written": 0, "annual_yf_no_label": 0,
              "annual_yf_tickers": 0, "quarter_yf_tickers": 0}


ANNUAL_COVERAGE_BAR = 0.85   # the annual leg's pre-registered bar (2026-10-16): of the tickers that
                             # have quarterly yfinance rows that night, >= 85% also have an annual one


def annual_coverage_summary(out: dict[str, Any], summary_prefix: str = "") -> str:
    """The one-line text of the nightly annual-coverage audit row (event_type
    `<run's event_type>_annual`): the pre-registered bar, readable without a query.
    Kept well under log_audit_event's 500-character cut. The numerator counts only tickers
    with a STATED estimate (a revenue or EPS average) among those with quarterly yfinance
    rows — see _has_estimate. Pure, so the wording is pinned by a test."""
    covered, of = out["annual_yf_tickers"], out["quarter_yf_tickers"]
    pct = f"{100.0 * covered / of:.0f}%" if of else "n/a"
    verdict = ("n/a" if not of
               else ("meets" if covered / of >= ANNUAL_COVERAGE_BAR else "BELOW")
               + f" the >= {ANNUAL_COVERAGE_BAR:.0%} bar")
    return (f"{summary_prefix}annual-from-yfinance: {out['annual_yf_rows_written']} annual row(s) "
            f"(already INCLUDED in the snapshot row's leading row count; subtract them for the "
            f"quarterly-only figure); "
            f"{covered}/{of} ticker(s) with quarterly yfinance rows also have an annual "
            f"estimate ({pct}, {verdict}); {out['annual_yf_no_label']} had annual frames but no "
            f"resolvable fiscal year end (an unresolved year end or mid reporting-gap — a "
            f"nonzero baseline is expected)")


async def _run_and_log(tickers: list[str], today: date, event_type: str,
                       summary_prefix: str = "") -> dict[str, Any]:
    """Run the population and write ONE audit row (plus, since 2026-10-16, one short
    `<event_type>_annual` row carrying the annual leg's coverage bar). The daily snapshot
    and the one-shot backfill are the same run over different populations — extracted so a
    change to the counters or the audit shape lands in one place, not two (the duplication
    class `_persist_minute_bars_for_ticker_day` was pulled apart for the same day).
    Never raises into the scheduler; SILENT (no Telegram on any path)."""
    try:
        out = await _run_over_tickers(tickers, today, event_type)
        try:
            await log_audit_event(
                event_type,
                f"{summary_prefix}{out['rows_written']} row(s) across "
                f"{out['tickers_written']}/{out['population']} ticker(s) "
                f"({out['quarter_yf_rows_written']} quarterly-from-yfinance, "
                f"{out['quarter_finnhub_rows_written']} quarterly-from-finnhub, "
                f"{out['divergence_rows_written']} divergence rows); "
                f"{out['no_anchor']} no-anchor (zero honest days, by design), "
                f"{out['anchor_errors']} anchor-error (zero honest days, EDGAR fetch failed), "
                f"{out['quarter_yf_no_cadence']} quarter-no-cadence-anchor "
                f"(yfinance had data, period end unresolvable — no EDGAR cadence facts, "
                f"OR the ticker is mid reporting-gap today; a nonzero baseline here EVERY "
                f"night is expected, not a defect — see the module docstring), "
                f"{out['quarter_yf_unavailable']} quarter-yfinance-unavailable, "
                f"{out['quarter_finnhub_no_cadence']} quarter-finnhub-label-rejected "
                f"(entries existed, self-consistency guards rejected every one), "
                f"{out['quarter_finnhub_unavailable']} quarter-finnhub-unavailable, "
                f"{out['errors']} error(s)",
            )
        except Exception:  # loud-ok: counters already logged by the scheduler wrapper
            pass
        # The annual leg's pre-registered bar gets its OWN short row (2026-10-16), not a
        # clause on the row above: log_audit_event stores only the first 500 characters and
        # that summary is ~600 long on any night, so a clause appended to it
        # would be silently cut off — and an edit near its front would push the quarterly
        # counters out instead. A separate row also leaves the existing one byte-identical.
        try:
            await log_audit_event(f"{event_type}_annual", annual_coverage_summary(out, summary_prefix))
        except Exception:  # loud-ok: the counters are also on the returned dict
            pass
        return out
    except Exception as e:
        logger.error(f"{event_type} failed: {e}", exc_info=True)
        return dict(_EMPTY_RUN)


async def run_analyst_estimates_snapshot(
    today: date, tickers: "list[str] | None" = None
) -> dict[str, Any]:
    """The daily 18:12 ET snapshot. Population: live-source EP-alert tickers from the
    trailing POPULATION_LOOKBACK_DAYS — today's alerts get their estimates recorded
    the same evening (honest as-of the alert day: as_of_date is the read date, never
    back-stamped), and recent-alert names keep accruing a revision series."""
    try:
        if tickers is None:
            from datetime import timedelta
            since = today - timedelta(days=POPULATION_LOOKBACK_DAYS)
            tickers = await get_analyst_estimate_population(since)
    except Exception as e:
        logger.error(f"analyst_estimates_snapshot population query failed: {e}", exc_info=True)
        return dict(_EMPTY_RUN)
    return await _run_and_log(tickers, today, "analyst_estimates_snapshot")


async def run_analyst_estimates_backfill(today: date) -> dict[str, Any]:
    """The ONE-SHOT bounded backfill (run by hand at deploy, not scheduled): a snapshot
    over the FULL live-source alert population, all history. The per-ticker honest
    window [anchor_filing_date, as_of_date] is baked into every row — the backfill IS
    a snapshot with a wider population; the valid-from semantics do the rest. A ticker
    that reported last week buys days; one with no resolvable filing buys ZERO, by
    design. ~1,000 calls once (~335 tickers x 3)."""
    try:
        tickers = await get_analyst_estimate_population(date(2000, 1, 1))
    except Exception as e:
        logger.error(f"analyst_estimates_backfill population query failed: {e}", exc_info=True)
        return dict(_EMPTY_RUN)
    return await _run_and_log(tickers, today, "analyst_estimates_backfill",
                              summary_prefix="one-shot backfill: ")
