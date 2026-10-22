# #314 — the parabolic short, replayed over five years: the base count, small caps, his selection rules, the time stop and stealth dilution — pre-registration (2026-10-21, revised 2026-10-22, BEFORE any replay outcome)

**Why.** The live shadow (since 2026-10-17; first market night 10-19) has armed n = 0 episodes, so nothing is known about how the
setup performs. The operator shared a short seller's stated rules (2026-10-20, `docs/methodology/operator_shared_notes.md`; mapped
in `docs/analysis/parabolic_short_vs_shared_short_rules_2026-10-20.md`) and ruled: *"Yes, but let's do this in weekend. Also, his
play is to short small caps, out filters are mainly for EPs, we haven't tested small caps for parabolic shorts"*; and on dilution:
*"it's not recent offering, the whole idea is stealth dilution that is in the horizon. Offering is after the fact"* / *"Eg warrants
that the run up will unlock and convert to shares is the exact example given"*. $0; shadow only; no paper, no live; entry / adds /
exits for money are his call (THE LINE). Revised 2026-10-22 against the review (§Revisions, bottom) — nothing below has been run.

## Method / population

**Bars and the calendar.**
- `apollo_data/cb702/daily_closes_all.csv.gz` (Polygon, split-ADJUSTED as of 2026-10-16; 13,830,569 rows, 20,285 tickers,
  2021-09-27..2026-10-16, columns ticker/date/open/high/low/close/volume, no header; sha256 pinned below = the CB registration's
  pin). Calendar = SPY's 1,270 sessions in the file. The **first scorable climax day D0 = 2022-03-17** (the 120th session: the
  detector is handed its `_HISTORY_DAYS` = 120 rows ending at D0). The **last D0 that can settle = 2026-10-07**, derived from the
  rule, not fixed by hand: the trigger comes by D0 + 3 and the 5th held session (the entry counting as 1) is D0 + 7 = 2026-10-16,
  the file's last day; a later D0 is "open at the end of the file", counted, never in a number.
- **RAW close** (the live price basis on D0's own day) = adjusted close × `cb.raw_factor_for(D0, splits)`, splits from
  `cb702_splits.psv` loaded with `runner.load_splits(through=2026-10-16)` (the 85 splits executing after the file's last day are
  dropped — they are not in the adjusted series). Every PRICE FLOOR below is tested on the raw close, so a later reverse split
  cannot admit a $0.20 stock as "$10" (the CB universe's rule, `docs/analysis/cb_preregistration_2026-10-18.md` §pipeline). Dollar
  volume = close × volume, invariant under adjustment, used as is. Ratios, ATR, levels and R stay on adjusted bars. STEP 0 prints
  the ticker-nights that pass a floor on the adjusted price and fail it on the raw price.
- **History.** A night is admitted only if the 120 bars ending at D0 are CONSECUTIVE SPY sessions (`cb.contiguous_window_mask`;
  6,018 of the file's tickers have a hole inside their span: halts, thin names, two companies glued onto one reused symbol). Live
  scores a name with as few as 60 rows and never checks consecutiveness; those nights are counted under the `history` funnel row,
  disclosed. The walk stops BEFORE the first bar that follows a missing session and the episode is `degraded` (counted, never in a
  number) — R is never booked across a halt or onto another company's prices.
- **Security type and symbol.** Ticker `^[A-Z]{1,5}$` as live's pattern (675 export symbols with other characters are out);
  exchange test symbols out (`cb.is_test_symbol`). Type = `mi_security_types` (`small_pulls.psv` `sectype` rows, 14,101 names), else
  the SIC pull's `type` (`cb702_sic.psv`, 3,942 names), else unknown. **Warrants, units and rights are out of both populations:**
  by type when typed, and by the suffix rule when not — a 5-letter symbol ending in W / U / R (1,274 / 863 / 238 in the export; the
  10-21 probe's top-60 small-cap run-ups held 12 warrants). P1 admits CS / ADRC / unknown as live's SQL does; **P2 requires CS or
  ADRC**, and its unknown-type names go to a counted beside row. The funnel prints an `excluded: security type` line.

**Two populations — the complement, one rule for every date, no switch at 2026-05-01.**
- **P1 = the live price and dollar-volume floors:** raw close ≥ $5 AND dollar volume ≥ $10M on D0 (`db.get_parabolic_universe`'s
  SQL, db.py:7462-7464). **The $250M market-cap floor is NOT in the deciding P1** — there is no cap history (`mi_market_caps` is one
  overwritten row per name; `mi_parabolic_candidates.market_cap` is a 30-day cache, only since 05-01 and only for names that passed
  the $5 / $10M pre-filter), and the floor is his signed rule (ADR 0020 J4), so it is applied as a BESIDE row, below, never
  silently. Disclosed: the deciding P1 is "the live floors without the cap floor".
- **P2 = small caps = the complement band:** (raw close < $5 OR dollar volume < $10M) AND raw close ≥ $1 AND dollar volume ≥ $2M,
  type CS / ADRC. The $1 / $2M floors are a tradable floor fixed now by me, not his; a different floor is his call. By
  construction **P1 ∩ P2 = ∅ on (ticker, D0)** and **P1 ∪ P2 ∪ P2's unknown-type row = every admitted name (symbol, test-symbol
  and W / U / R rules applied) with raw close ≥ $1 and dollar volume ≥ $2M** — both are runner assertions, not expectations. STEP 0 prints P2's point-in-time cap distribution where known (the share under
  $250M), so "P2 is small caps" is a printed number, not a label.
- **The SQL pre-filter's two other conditions are not re-applied because the detector re-tests them:** `close / sma_50 ≥ 1.5` is
  gate 3 (`_MIN_EXT_VS_SMA50`), and `close / low_60d ≥ 1.5` is implied by gate 2 (the base low is a low inside the last 60
  sessions, so the prior move ≥ 50% at any tier implies it). Only type, the price floor, the dollar-volume floor and history are the
  runner's to apply; everything after is `compute_parabolic_metrics` on the 120 rows, `rows[-1].trade_date == D0` asserted.

**One cap rule for every date (point-in-time, from the pull read 5 needs anyway).** cap(D0) = the latest SEC XBRL companyfacts
`dei:EntityCommonStockSharesOutstanding` with `filed` < D0, put on D0's share basis (× the product of the `cb702_splits.psv` ratios
of splits executing between the fact's period end and D0), × RAW close(D0). No CIK, no fact filed before D0, or more than one
undimensioned value on the same filing (multi-class names) = **unknown**, counted. Used three ways: (1) **the detector's tier in BOTH
populations** — `_classify_cap_tier(cap)` as live (≥ $10B 50%, $2–10B 100%, under $2B 200%); unknown goes down the detector's own
`market_cap=None` branch (mid, 100%), counted and disclosed. (2) **P2 beside, decides nothing:** every P2 name at the small tier
(200%, the live rule for a sub-$2B name) by passing `market_cap=1` as a sentinel — never written anywhere as a cap. The tier changes
gate 2, so this is a SECOND detector pass with its own climax list and its own STEP 0 count, not a re-read of the same episodes.
(3) **P1 beside,
decides nothing:** the $250M floor on this cap, an unknown cap REJECTED as live does (`filter:mcap_unknown`, shadow.py:488-491),
both counts printed — what his signed floor does to the P1 result.

**Calling the detector with explicit parameters (the module is NOT edited; its sha256 is pinned).** `compute_parabolic_metrics(rows,
market_cap=cap, is_earnings_today=None)` is called per night. The $10M dollar-volume gate is a module global
(`_MIN_DOLLAR_VOL_TODAY`, detector.py:67) read at call time, so **P2 runs in its own process that does
`setattr(parabolic_detector, "_MIN_DOLLAR_VOL_TODAY", 2_000_000)` before the first call; P1 runs in a separate process on the
untouched module.** Each process asserts the constant it expects (2,000,000 / 10,000,000) and prints it in its summary; a P2 process
that finds 10,000,000, or a P1 process that finds anything else, exits non-zero. The patch exists only at runtime.

**Substitutions — the four live rules that sit OUTSIDE the pure functions, and what stands in for each (none is "unchanged").**
- (a) **The Perplexity one-shot-news exclusion** (detector.py:514-537, :716-723) cannot be replayed into the past: NOT applied, every
  climax is admitted (the replay includes names live would have removed). Beside, pre-named: a row that drops episodes with a $0
  keyword candidate in Polygon news dated [D0 − 30 calendar days, D0] — a title / description match on
  `ma_filter._MNA_CANDIDATE_KEYWORDS` under the #88 rule (the ticker is in the item's `tickers` AND its `insights` name it; the
  module's `_candidate_articles`). The paid deal question (`headline_deal_scan`) is NOT asked; the row is the filter's $0 half.
- (b) **The borrow check** (easy-to-borrow at the arm and at the trigger, shadow.py:498, :639): historical borrow is not visible, so
  easy-to-borrow is ASSUMED at both checks. n therefore overstates what could have been shorted, most of all in P2.
- (c) **One open episode per name, advance-before-decide, oldest climax first** (shadow.py:485-487, :695-713) live in async DB code,
  not in `replay_episode`: re-implemented per population — sessions walked in ascending order; on each night the open episodes are
  advanced through that night's bar first, then that night's climaxes are decided; a climax on a name whose earlier episode has
  not closed by that night's own bar (outcome date > D0, or still open / degraded) is rejected `episode_already_open`, counted. A
  test runs the test module's in-memory harness (`tests/test_parabolic_short_shadow.py` `Env`, two back-to-back climaxes on one
  name) through `run_parabolic_short_shadow` and asserts the replay's decision list equals it.
- (d) **The earnings gate and the earnings exit.** Checked for a stored source and there is none: `mi_ep_fundamentals` (the 10-21
  draft's source) does not exist in the repo; `mi_fundamental_flags.next_earnings_date` is kept 30 days (db.py:705-715);
  `mi_ep_catalyst_metrics` covers EP earnings alerts only; `scripts/fetch_ep_fundamentals.py` is a 50-name sample with no date
  bound; live earnings are yfinance on demand (`earnings_calendar.py:159-199`), not stored. **Primary: the gate and the exit are NOT
  applied; every climax carries `earnings = unknown`** (disclosed: the AGL / XMTR flat-base earnings-gap class the 05-08 gate removes
  is admitted). **Beside, a real point-in-time source:** the EDGAR submissions list (`data.sec.gov/submissions/CIK##########.json`
  `form` / `items` / `acceptanceDateTime` plus the older files it lists — the JSON `collector.get_sec_recent_filings` already reads,
  collector.py:1262-1300): an **8-K with item 2.02** accepted on D0 − 1 or D0 (acceptance converted to ET; after 16:00 ET = the next
  session, the live `_within_window` {yesterday, today}) = "earnings on the climax day" and the beside row drops the episode; an
  item 2.02 accepted after a held session's close and before the next open = the earnings exit at that close (the live
  `default_earnings_before_next_open` window), walked with `earnings_after`. No CIK, no filing history, or a 6-K filer (no item
  2.02 exists for them) = **unknown, its own group**, never "no earnings" — the live fail-closed / fail-open split does not arise.

**The primary walk = `replay_episode` unchanged** (shadow.py:197; its sha256 pinned): arm on the climax night (`armed_on` = D0),
short a break of the prior session's low within 3 sessions (fill kinds as the SSoT's daily-bar honesty), stop at the climax high +
min(3%, 0.5 × ATR14), trail to the prior session's high, cover a third at +1R, time stop at the close of the 5th held session (the
entry session = 1), no earnings exit in the primary. R against the entry stop.
- **n = SETTLED episodes** (triggered, then exited by `stop`, `trail_stop`, `time_stop` — or `earnings_exit` in the 8-K beside
  row). Counted beside, never in a number: `invalidated` and `expired_untriggered` (closed untriggered), `void_bad_geometry`,
  `degraded` (the walk met a hole), open at the end of the file. Mean R, the interval and every read are over settled episodes.
- **ADR P&L for a short, fixed now:** per settled episode Σ over legs of weight × (entry − leg exit) ÷ entry ÷ ADR20%, the flush leg
  = 1/3 at `entry − 1R` when taken (else the exit leg carries all), **ADR20% = the mean of (high − low) / close over the 20 sessions
  ending at D0 − 1** — the session BEFORE the climax, so the climax bar does not set the unit. Size-free, like the CB registration's.
- **The tail clause for a 5-session short, fixed now:** PASS needs **at least 3 settled trades at ≥ 3R, from ≥ 3 tickers and ≥ 3
  distinct entry months**; fewer = the clause FAILS (never "vacuously true"). Why 3R and not the long book's 5R: the blend is
  1/3 × 1R + 2/3 × exit-leg R, and the exit leg cannot exceed entry ÷ risk (a price stops at zero), so 3R needs a 4R exit leg
  (a fall of four stop-distances inside 5 sessions, with the stop within 25% of the entry) — a genuine outlier that is reachable;
  5R needs a 7R leg, near-unreachable by the rule's own algebra. His ~2R average winner (map row 21) is the benchmark, so ≥ 2R
  with the same spread is reported beside. STEP 0 prints a reachability PROXY — the share of climaxes with
  (stop − climax low) / climax low < 0.25, i.e. 3R reachable at an entry on the climax low; the real entry is a later session's
  low, above or below it. Geometry known at D0, no outcome.

**Reads on the same episodes (each a fixed variant beside the primary; nothing tuned; the sign of every difference is written).**
1. **Time stop 3 vs 5** — his "shorts last 1–3 days". Primary variant = `time_stop=3` HELD sessions, the entry session counting
   as 1 (the module's own counting, shadow.py:312); beside = exit at the close of D0 + 3 (his count from the top day). **Paired:
   the same episodes walked twice; the difference = R3 − R5 per episode**, over episodes settled under BOTH stops (the 5-stop is
   the binding one); the interval = the month-block bootstrap of the paired differences. In the 8-K beside row the earnings window
   is passed the same `time_stop`.
2. **Straight-up shape** — the pause count = sessions i in (base_date, D0] with close[i] < close[i − 1] (`base_date` = the
   detector's own, the most recent close ≤ SMA20 within 60 sessions, detector.py:140-157; the base session itself not counted).
   Primary cut ≤ 2 vs ≥ 3; **difference = (≤ 2) − (≥ 3)**. Run length (sessions from base_date to D0) is printed per group because
   the count mostly measures it; beside: pauses ÷ run length split at 0.20 (one down close per five sessions; fixed now, decides
   nothing). A name whose `base_date` is the 60-sessions-ago anchor (no SMA20 touch in 60 sessions) keeps its count and is flagged
   `anchor`, printed.
3. **A news catalyst present vs absent** — run start = the session AFTER `base_date`; window = the three sessions
   [start − 2, start], i.e. items published after 16:00 ET of the session before start − 2 and at or before 16:00 ET of start
   (Polygon `published_utc` is UTC; converted to ET; passed as full timestamps to `published_utc.gte` / `.lte`, never bare dates).
   An item counts only if the ticker is in its `tickers` AND its `insights` name the ticker (#88). The runner calls
   `collector._polygon_get` DIRECTLY and records the HTTP status: any failure, a non-200, or tagged items that carry no `insights`
   at all = **unknown, its own group, never "absent"** (`get_polygon_news` returns [] on every failure and is not used). An
   `anchor` base (read 2) has no run start = unknown. **Difference = present − absent**, unknown excluded. The share "present" is
   printed by year beside the read (Polygon's coverage changes over time). One news pull per episode covers both this window and
   row (a)'s [D0 − 30, D0]; it is saved once and sliced.
4. **A loss-to-profit swing blocks** — from companyfacts `us-gaap:NetIncomeLoss` (USD): a quarter = a fact whose period spans
   80–100 days; Q4 = the fiscal-year fact minus that year's 9-month fact when no 3-month Q4 fact exists; `filed` < D0. Swing = the
   latest such quarter positive AND the quarter before it negative. **Primary = a swing whose `filed` date falls inside
   [base_date, D0]** (his rule 5: the swing IS the news behind the run); beside = the last quarter filed before the climax,
   whenever filed. **Groups swing / no swing / unknown** (no CIK, no facts, fewer than two consecutive quarters); **difference =
   (no swing) − (swing)**, unknown excluded.
5. **Stealth dilution — P2 DECIDES, P1 beside.** Ratio = shares issuable from warrants and convertibles **newly unlocked by the
   run** ÷ shares outstanding, every term from the LAST filing with `filed` < D0. **"Unlocked" = the exercise / conversion price
   lies in (base low, raw climax close]** — the run-up crossed it from below (his words: "warrants that the run up will unlock");
   terms already deep in the money before the run are a beside row ("in the money at the climax", all of them). **Price basis:** both
   sides on D0's basis — the raw close(D0) against the reported price ÷ the split ratios between the fact's period end and D0, share
   counts × the same ratios. **Company match:** CIK from SEC `company_tickers.json` (current), CONFIRMED point-in-time by
   `dei:TradingSymbol` where companyfacts carries it for a filing dated ≤ D0; where it does not, by the submissions endpoint's
   `tickers` field plus the consecutive-history rule above as the reused-symbol guard; the run prints which path each name took;
   neither = unknown. **Pairing:** computed only when that filing carries exactly one (count, price) pair — the securities-called
   count (`ClassOfWarrantOrRightNumberOfSecuritiesCalledByWarrantsOrRights`) if present, else `ClassOfWarrantOrRightOutstanding`
   × 1 (one share per warrant, stated); convertibles: shares = principal (`ConvertibleNotesPayable` / `ConvertibleDebt`, current or
   non-current) ÷ `DebtInstrumentConvertibleConversionPrice1`, same filing; a variable-price convertible has no fixed price = unknown
   (companyfacts holds only undimensioned facts, so multi-tranche terms cannot be paired = unknown). Buckets **≥ 20% / < 20% /
   unknown**; **difference = (≥ 20%) − (< 20%)**, unknown excluded, never imputed. **Coverage, restated honestly:** the 10-21 probe
   (`scripts/probes/_314_xbrl_coverage_1021/probe.out`) mapped 40 of 60 names to a CIK and counted each tag at ANY filed date, one
   tag at a time: warrant count 12, exercise price 18, shares outstanding 34; count + price + shares on one filing = 10 of 60;
   conversion price + (shares or principal) + shares outstanding = 4 of 60. Coverage filed BEFORE each climax is lower still. **So
   with n ≥ 30 per bucket this read is expected to come back CAN'T TELL**; it is registered so the coverage number is on the record
   and the recording rule below can still apply. Each group's N is printed at STEP 0, before any walk.

**STEP 0 — derive and count the populations; walk nothing.** Before any outcome column exists the runner writes and prints, per
population: the funnel (ticker-nights → symbol / test symbol → security type → raw price band → dollar volume band → consecutive
history → each detector gate in order: dollar volume (patched in P2), base anchor, prior move by tier, SMA extension, acceleration,
burst score, gapped today, climax volume, days-up streak → climax), the climax count per calendar year, the cap-tier and
cap-source counts, the reachability proxy, and the tally of adjusted-pass / raw-fail nights. The one-open-episode rejection needs
the earlier episode's outcome date, which only the walk produces, so the climax → `episode_already_open` → armed tally is printed
by the WALK's own summary, not here; the pinned list is the pre-walk population through `climax`. It writes
`climax_list.tsv` (ticker, D0, population, tier, cap, cap source, type source, earnings flag, reachable flag) and `features.tsv`
(pause count, run length, anchor flag; news group, item date, HTTP status; swing group, filed date; dilution bucket, filed date,
company-match path; the M&A keyword flag and item date; the 8-K 2.02 flag and acceptance date) and the saved pulls
(`xbrl_facts.jsonl.gz`, `edgar_submissions.jsonl.gz`, `polygon_news.jsonl.gz`). **All of them are pinned (`--print-pins`) in a
commit BEFORE the walk; the walk refuses to start without those pins.**

**Parity — checked against data that exists (a broken replay must be able to fail).**
- **Walk goldens (synthetic, the test module's own series, `tests/test_parabolic_short_shadow.py`):** `TRIGGER_THEN_TIME_STOP` →
  settled `time_stop` on D5, entry 140.0 `intraday`, flush taken at 116.93, realized R 1.200260078; the same series at
  `time_stop=3` → settled on D3, realized R 0.969079613 (both computed 10-22 from the pure function; matched to 1e-9 on the run
  machine — same platform, never cross-platform). The runner writes the fixture bars in the export's layout, reads them back through
  its own loader and must return a dict byte-equal to `replay_episode` on the fixture dicts, for every scenario the test module's
  `TestGeometry` / `TestFillConvention` / `TestArmWindowAndInvalidation` / `TestManagement` classes hold.
- **Detector goldens on the export's REAL bars (documented live stages, population-level, no outcome).** REFUSING: AGL
  2026-05-07: `days_up_streak` = 2 and not climax (`docs/setups/parabolic_short.md`:284); XMTR 2026-05-07: `days_up_streak` = 3,
  `climax` with `is_earnings_today=False` and NOT with `True` (:284, :68). Both are documented facts about the CURRENT gates (the
  05-08 entries). The golden passes the tier the SSoT's evidence implies EXPLICITLY — `market_cap=5_000_000_000` (mid, 100%; XMTR's
  113% prior move passes only at mid or large) — so the golden tests the detector, not the cap source; the point-in-time cap is
  printed on a separate line. PRINTED, not refusing: CAR 2026-04-07 and 2026-04-21 = `climax` per :298 — that evidence sits under
  the 05-01 initial-ship entry, before the 05-08 gates; the streaks on those days are 5 and 4 (closes checked 10-22) so the streak
  gate passes, but the other gates under today's constants are not documented, so CAR prints its stage and every gate value and a
  miss is listed, never a refusal. All three are in the export with > 1,100 rows before those dates (checked 10-22). A miss on
  AGL or XMTR lists its gate and REFUSES the run.
- **Live rows: none exist on this machine.** No export of `mi_parabolic_candidates` or `mi_parabolic_short_shadow` is stored
  locally (`find` / `grep` 10-22), and the shadow has armed 0 episodes since its first night 10-19, so "parity with the shadow's
  rows since 10-17" is dropped — it could never fire. If he wants the reviewer's stronger check, a read-only extract of
  `mi_parabolic_candidates` 2026-05-01..10-16 (all stages, with `market_cap` and `is_earnings_today`) pulled before the run and
  pinned gives: stage match ≥ 99% of rows and 100% of climax rows, every mismatch listed with its reason, the run refused under
  1,000 rows or 0 climax rows. Without it the goldens above ARE the parity, and the result says so.

**Independent re-derivation** from `episodes.tsv` alone (pandas, no runner code): per population n, mean R, the interval, ADR P&L,
the tail spread, and each read's difference (point and interval, same seed) — VERDICT MATCH before the result is written.

## Bars (per population; settled episodes; precedence: n first)

- **The base verdict (primary walk):** PASS = n ≥ 30 AND the month-block 95% interval of mean R (blocks = the ENTRY month, 2,000
  resamples, seed 702, `runner.block_bootstrap_ci`) has its lower end > 0 AND mean ADR P&L > 0 AND the tail clause (≥ 3 trades
  ≥ 3R from ≥ 3 tickers and ≥ 3 months). FAIL = n ≥ 30 AND the upper end < 0. Else CAN'T TELL — n < 30 whatever the interval says;
  an interval above zero without the tail is "CAN'T TELL (positive, no tail)".
- **Each read:** the difference named in its row (1: R3 − R5 paired; 2: (≤ 2) − (≥ 3); 3: present − absent; 4: (no swing) −
  (swing); 5: (≥ 20%) − (< 20%); unknown groups always excluded, their N printed). Lower end > 0 → the rule separates in HIS
  direction; upper end < 0 → against him; else can't tell. n ≥ 30 per group (read 1: 30 pairs) or the row reads CAN'T TELL.
  **Interval for a difference:** in each resample draw entry-month blocks once, with replacement, from the union of both groups'
  months, recompute both group means from the drawn episodes and take the difference; a resample that leaves a group empty is
  redrawn and the number redrawn is printed; 2,000 draws, seed 702 mixed with the row's key.
- **Chance hits, stated now:** 5 reads × 2 populations = 10 one-sided tests at 2.5% each, so about a 22% chance that at least one
  "separates" by chance under a true zero. A single separating read is only a CANDIDATE for recording (consequence below); nothing
  here is adopted on one read.
- **Expectations, fixed now (each can miss; a miss is reported first and changes no rule):** P2 yields more climax nights than P1
  (small caps run parabolic more often — no longer true by construction, P2 is the complement); the adjusted-pass / raw-fail tally
  in P2 is above zero (reverse splits are routine there); at least 80% of P2's climax names are typed CS; the share "present" in
  read 3 rises across 2022→2026; the read-5 known buckets are under 30 each (CAN'T TELL); the reachable-3R share is under 50% in P1.
- **WOULD-FAIL-IF (checks the runner PERFORMS; any one exits non-zero and writes no report):** `rows[-1].trade_date == D0` on every
  scored night and the 120 rows are consecutive SPY sessions; a feature dated after its cut-off (news after the window's close
  for read 3 / after D0 for row (a); any filing with `filed` ≥ D0 in reads 4–5 or the cap; an 8-K acceptance after the session it
  is charged to); an episode in two groups of one read, or in none; P1 ∩ P2 ≠ ∅, or P1 ∪ P2 ∪ P2's unknown-type row ≠ the $1 / $2M
  band; a name with two open episodes on one night; the patched constant ≠ 2,000,000 in the P2 process or ≠ 10,000,000 in P1; the
  walk goldens off by more than 1e-9 or the AGL / XMTR goldens off on any gate; the walk's climax set ≠ the pinned
  `climax_list.tsv`; a settled episode whose
  entry ≤ D0 or whose exit > entry + 4 sessions (5-stop) / + 2 (3-stop); a read-1 pair whose two walks differ in entry; a realized
  R not equal to 1/3 + 2/3 × exit-leg R when the flush was taken; the export's sha256 ≠ the pin; any pinned module changed.

## Consequence fixed now

- **A P2 PASS goes to him:** it is put to the operator as a PROPOSAL to open a P2 shadow lane (small caps, their own borrow check —
  historical borrow is not visible, so a replay PASS overstates what can be shorted). The $250M floor is his signed rule (ADR 0020
  J4, `SHORT_MCAP_FLOOR_USD`); lifting or re-cutting it is CHANGE_PROCESS + his sign-off, never this doc's.
- **A P1 PASS** makes the live shadow's population the candidate for the next rung — the P1-cap beside row shows what the floor
  does; paper stays his call (THE LINE). A FAIL changes nothing live: the shadow keeps running and the result is reported.
- **A read that separates in his direction is RECORDED** on the shadow's rows (the pause count, the news group, the swing group,
  the dilution ratio, the 8-K flag) — a recording, not a rule, and a candidate only (the chance note); adopting any as a gate or an
  exit goes through CHANGE_PROCESS to him. A read against him is reported, nothing changes. Read 1 touches a signed value (the
  5-session time stop, ADR 0020) — a separation is reported to him, never applied.

## What the read may NOT do

- Switch the deciding population band, the P2 floors, a read's primary variant, a cut (≤ 2 / ≥ 3, 20%, 0.20), the time-stop
  counting, the n floor, the seed or the draw count — after this registration, for any reason. A beside row is never a finding.
- Impute an unknown into a group; pool unknown into "the rest"; walk before the STEP 0 pins are committed; run a population twice
  (the `episodes.tsv` and its `.partial` refuse a second run; the operator removes them by hand); edit this document above the
  marker after the freeze commit.

## What this does not answer

- Borrow availability and cost (the binding real-world limit on small-cap shorts; assumed easy at both checks); intraday entries
  (his top-day short on "losing momentum") — the replay is daily; his adds / pyramiding; the large-cap "obvious news-driven
  parabolic" judgement; the Perplexity exclusion's real effect (the keyword row is its $0 half); the earnings gate's effect on this
  population (unknown in the primary; the 8-K row is a substitute, not the live source); names live scores on 60–119 rows; XBRL
  coverage limits every read that needs a filing.

## Revisions 2026-10-22 (the review's 20 findings; what changed and how; nothing rejected outright)

- **B1 cap floor undefined before 05-01 / cap-history statement wrong** → fixed: the wrong statement is gone; ONE point-in-time
  cap rule for every date (XBRL shares outstanding filed < D0 × raw close); the deciding P1 = the live price / dollar-volume floors
  WITHOUT the cap floor, disclosed; the floor is a P1 beside row with unknown rejected as live does. The reviewer's option (a) as the
  DECIDING rule was not taken: XBRL coverage would empty P1 of every unmapped name, and the floor is his signed rule.
- **B2 P2 cannot run on the detector unchanged** → fixed: the `setattr` patch in P2's own process, asserted and printed; the tier
  chosen now (the point-in-time cap; unknown = the detector's own mid branch), the all-small-tier P2 row beside via the sentinel.
- **B3 parity had no data** → fixed: synthetic walk goldens with their numbers, detector goldens on the export's real bars (AGL
  and XMTR refusing, with the tier passed explicitly; CAR printed only — its SSoT evidence predates the 05-08 gates), live rows
  dropped as impossible and SAID SO; the prod-extract check named as optional (no prod access in this revision — his call whether
  to pull it).
- **B4 sources do not exist** → fixed: `mi_ep_fundamentals` removed; the earnings gate is `unknown` in the primary with the EDGAR
  8-K item 2.02 acceptance row beside (the live windows mapped); read 4 on companyfacts `NetIncomeLoss` with `filed` dates — ⚠ a
  run-time SEC pull, not a stored table, which the main loop's guidance would have dropped to "unknown"; kept because it is the
  same pull read 5 needs, $0 and point-in-time (open question (a) in the return).
- **B5 n, ADR P&L and the tail undefined** → fixed: n = settled; ADR P&L formula and its ADR20 window; the tail = ≥ 3 trades
  ≥ 3R / 3 tickers / 3 months, fewer fails, with the reason from the rule's own algebra; ≥ 2R beside; the reachable share at STEP 0.
- **B6 split look-ahead on the price floors** → fixed: raw close via `cb.raw_factor_for` with splits loaded through 2026-10-16;
  the adjusted-pass / raw-fail tally printed; ratios, ATR and R stay adjusted.
- **M1 four live rules outside the pure functions** → fixed: the Substitutions section (Perplexity → the $0 keyword row; borrow
  assumed; the episode rules re-implemented with a harness test; earnings as B4).
- **M2 warrants / units / rights** → fixed: type rule (`mi_security_types`, SIC pull, unknown) + the W / U / R suffix rule; P2
  requires CS / ADRC; unknown-type P2 names a counted beside row; the funnel line.
- **M3 gaps and reused tickers** → fixed: 120 consecutive SPY sessions ending at D0; `history` funnel row; the walk ends
  `degraded` at a hole.
- **M4 P2 was P1 plus more; expectation true by construction** → fixed: P2 = the complement band ($1 / $2M floors fixed now, mine);
  disjointness and union are assertions; the expectation replaced by ones that can miss; P2's cap distribution printed.
- **M5 read 1 start day and independence** → fixed: `time_stop=3` held sessions with the entry = 1; the D0 + 3 close beside;
  paired difference R3 − R5 over episodes settled under both; the earnings window follows the time stop in the 8-K row.
- **M6 read 3 window, timezone, failed lookup** → fixed: run start = the session after `base_date`; the three-session window as
  ET-close-bounded UTC timestamps; `_polygon_get` direct with the HTTP status; failure / no insights = unknown; #88 rule; the
  present-share by year; anchor bases unknown.
- **M7 read 4 no-data pooled, quarters undefined, window** → fixed: swing / no swing / unknown; ~90-day facts with the Q4
  subtraction, filed < D0; primary = the swing filed inside [base_date, D0], the last quarter beside.
- **M8 read 5 basis, match, pairing, coverage, "unlock"** → fixed: D0 share basis for price and counts; CIK match confirmed
  point-in-time (`dei:TradingSymbol` where present, else the submissions `tickers` + the history rule, path printed); one
  (count, price) pair per filing, securities-called count first, convertibles = principal ÷ price, variable = unknown; primary =
  newly unlocked (base low, climax close]; all-in-the-money beside; P2 decides, P1 beside; coverage restated from the probe's own
  numbers (10 of 60 / 4 of 60, any filed date) and CAN'T TELL named as the expected reading.
- **M9 differences unsigned, read 5's three groups, interval for a difference, chance** → fixed: every difference written with its
  sign; unknown excluded everywhere; the shared-block resample recipe with the empty-group redraw counted; the 22% chance note and
  "candidate only".
- **M10 population not derived or pinned first; WOULD-FAIL-IF not executable** → fixed: STEP 0 funnel, per-year counts,
  `climax_list.tsv` + `features.tsv` + the saved pulls pinned before the walk; the WOULD-FAIL-IF list is runner assertions that exit
  non-zero; the export hash is already pinned.
- **m1 pause count measures run length; boundaries** → fixed: the count's exact window and comparison; run length printed per
  group; the ratio row at 0.20 beside.
- **m2 window edges** → fixed: first D0 2022-03-17, last settling D0 2026-10-07 (derived); open-at-end counted; read 1 pairs
  settled under both stops.
- **m3 a P2 PASS lifts a signed floor** → fixed: the consequence now reads "a proposal to him; the floor is his signed rule
  (CHANGE_PROCESS)".
- Also added (from the house format, missing in the draft): "What the read may NOT do"; the once-only run guard.

<!-- FREEZE -->
## Freeze record

The doc body pin covers every byte above the `<!-- FREEZE -->` marker. The run verifies every pin before it opens the export and
refuses on any mismatch (the `freeze_check` pattern of `scripts/probes/_cb_backtest/runner.py`); STEP 0 runs first and its outputs
are pinned in a second commit before the walk; the RESULT is appended below this record. Pins computed 2026-10-22 (`shasum -a 256`)
for the data and the two frozen modules; the runner, the CB module (`raw_factor_for` / `contiguous_window_mask` /
`is_test_symbol`), the test module (the goldens), the STEP 0 files and the doc body are printed by `--print-pins` and pasted here in
the commits that precede the run.
- cb702/daily_closes_all.csv.gz sha256: `ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba`
- cb702/cb702_splits.psv sha256: `3199d06d5fb7dcd52ebd34e8c71e148b45ec0ca4a15f7f03ea1b715718882b0b`
- cb702/small_pulls.psv sha256: `b8d37aae5ef85c25bc52479eef7f6b04a8a4e67557caaef7a426d8ae20194643`
- cb702/cb702_sic.psv sha256: `0e476c4422d56648d615c48d941edb971a348dfb99821023116d0fd98e617346`
- agents/market_intelligence/parabolic_detector.py sha256: `7530113b4defbdd10b7b02ba32c49b57261fdd32f609f65a28779e419e69cb0b`
- agents/market_intelligence/parabolic_short_shadow.py sha256: `3059e90e07e792e48c8fcf7e2c591786fb1d5da7496396cf3afc5e3e8abebb6b`
- agents/market_intelligence/consolidation_breakout.py sha256: (pasted before the run)
- tests/test_parabolic_short_shadow.py sha256: (pasted before the run)
- runner sha256: (pasted before the run)
- climax_list.tsv / features.tsv / xbrl_facts.jsonl.gz / edgar_submissions.jsonl.gz / polygon_news.jsonl.gz sha256: (pasted after
  STEP 0, before the walk)
- doc body sha256: (pasted in the freeze commit)
- freeze commit: the commit that adds this revision on `main`; STEP 0 runs only after it is on `main`, the walk only after the
  STEP 0 pins are.
