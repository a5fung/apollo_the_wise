# #314 — the parabolic short, replayed over five years: the base count, small caps, his selection rules, the time stop and stealth dilution — pre-registration (2026-10-21, revised 2026-10-22 and 2026-10-23, BEFORE any replay outcome)

**Why.** The live shadow (since 2026-10-17; first market night 10-19) has armed n = 0 episodes, so nothing is known about how the
setup performs. The operator shared a short seller's stated rules (2026-10-20, `docs/methodology/operator_shared_notes.md`; mapped
in `docs/analysis/parabolic_short_vs_shared_short_rules_2026-10-20.md`) and ruled: *"Yes, but let's do this in weekend. Also, his
play is to short small caps, out filters are mainly for EPs, we haven't tested small caps for parabolic shorts"*; and on dilution:
*"it's not recent offering, the whole idea is stealth dilution that is in the horizon. Offering is after the fact"* / *"Eg warrants
that the run up will unlock and convert to shares is the exact example given"*. $0; shadow only; no paper, no live; entry / adds /
exits for money are his call (THE LINE). Revised 2026-10-22 against the review and 2026-10-23 against the recheck (§Revisions,
bottom: round 1, then round 2 — the round-2 blockers were survivorship in the type / CIK sources and in P2's population rule) —
nothing below has been run.

## Method / population

**Bars and the calendar — TWO eras, one bar source each, never straddled (round 2).** The 10-22 registration ran on the Polygon
file alone, which starts 2021-09-27 — four and a half years, not five — and Polygon's daily aggregates on our plan reach back only
to 2021-10 (2021-10-01 and earlier return 403; verified 10-23). The earlier years come from Alpaca, which serves daily bars BY
SYMBOL for delisted / acquired names back to 2016 (TWTR, ATVI, IAA, KAR, EA, MRO, X, WBA all returned 2019 bars 10-23) although
its `/v2/assets` list omits them.
- **Era B (Polygon) = D0 in [2022-03-17, 2026-10-07]:** `apollo_data/cb702/daily_closes_all.csv.gz` (Polygon, split-ADJUSTED as
  of 2026-10-16; 13,830,569 rows, 20,285 tickers, 2021-09-27..2026-10-16, columns ticker/date/open/high/low/close/volume, no
  header; sha256 pinned below = the CB registration's pin). It INCLUDES names delisted since (Polygon-based). Calendar = SPY's
  1,270 sessions in the file. The **first scorable climax day D0 = 2022-03-17** (the 120th session: the detector is handed its
  `_HISTORY_DAYS` = 120 rows ending at D0). The **last D0 that can settle = 2026-10-07**, derived from the rule, not fixed by hand:
  the trigger comes by D0 + 3 and the 5th held session (the entry counting as 1) is D0 + 7 = 2026-10-16, the file's last day; a
  later D0 is "open at the end of the file", counted, never in a number.
- **Era A (Alpaca) = D0 in [2016-06-23, 2022-03-16]:** `apollo_data/cb702_pre/daily_closes_all.csv.gz` (Alpaca SIP,
  split-adjusted as of its export; 10,320,661 rows, 9,944 symbols, 2016-01-04..2022-06-30, same layout; `export_stats.tsv`)
  **PLUS the delisted refetch** — the output of `scripts/probes/_705_survivorship_1023/01_fetch_delisted.py` (Polygon
  `/v3/reference/tickers` `active=false`, types CS / ADRC, delisted on or after 2016-01-04, minus the symbols already in the
  export; Alpaca split-adjusted daily bars by symbol, 2016-01-04..min(delist date, 2022-06-30); running 10-23, path and sha256
  pasted in the freeze record when it lands). The export alone is SURVIVORS-ONLY — built from Alpaca's CURRENT asset list, so
  every stock delisted since is missing (415 liquid names in H1 2022 alone, #705 10-23). That is the round-2 blocker: the names
  that collapse — the short's best cases — are exactly the ones a survivors-only file lacks. **The walk REFUSES era A unless the
  refetch file, its RAW companion (next bullet) and both identity-guard tables (History, below) are pinned.** Calendar =
  `cb702_pre/sessions.txt` (1,635 sessions, 2016-01-04..2022-06-30; pinned); first scorable D0 = its 120th session = 2016-06-23;
  last era-A D0 = 2022-03-16 (the session before era B's first); every era-A episode settles inside the file (D0 + 7 ≤
  2022-03-28 < 2022-06-30).
- **Ownership in the overlap (2021-09-27..2022-06-30, both files):** era B owns every D0 ≥ 2022-03-17 (the first D0 with 120
  Polygon rows), era A every earlier D0. An episode's 120-row history AND its walk come from its era's file only — a window or a
  walk crossing the two files would mix two adjustment bases (Alpaca vs Polygon) and two calendars, so "no bar from the other
  file" is a runner ASSERTION, not a convention. STEP 0 prints, over the ticker-days both files hold, the share of adjusted closes
  differing by more than 0.5% (a printed number; decides nothing). Every count, funnel line and result below is printed PER ERA
  and pooled; the verdict is on the pooled settled set, the per-era rows beside with their n.
- **RAW close** (the live price basis on D0's own day). **Era B:** adjusted close × `cb.raw_factor_for(D0, splits)`, splits from
  `cb702_splits.psv` loaded with `runner.load_splits(through=2026-10-16)` (the 85 splits executing after the file's last day are
  dropped — they are not in the adjusted series). **Era A has no split table** (`cb702_splits.psv` starts 2021-09-27): the raw
  close is read per bar from `cb702_pre/daily_raw_close.csv.gz` (headerless `ticker,date,raw_close`; the runner's `--raw-close`
  mechanism — the factor is measured per bar as raw ÷ adjusted) and, for the refetched delisted names, from a **RAW companion
  pull = the same refetch call with `Adjustment.RAW`, registered here as a REQUIRED output. It does not exist yet: the refetch
  running 10-23 writes split-adjusted bars only.** A refetched name with no raw close is NOT placed by its adjusted price — it goes
  to a counted `raw_unknown` funnel row, out of BOTH populations: reverse splits are routine in exactly these names, and an
  adjusted close would admit a $0.20 stock as "$10". Every PRICE FLOOR below is tested on the raw close (the CB universe's rule,
  `docs/analysis/cb_preregistration_2026-10-18.md` §pipeline). Dollar volume = close × volume, invariant under adjustment, used as
  is. Ratios, ATR, levels and R stay on adjusted bars. STEP 0 prints the ticker-nights that pass a floor on the adjusted price
  and fail it on the raw price, per era.
- **Units, in one place (round 2 — the double-split finding).** Bars = split-adjusted to the export's as-of date (era A Alpaca,
  era B Polygon). Raw close(D0) = the dollars actually printed on D0. XBRL share counts and per-share prices = the filing's own
  basis: the shares and dollars in force at the fact's `end` date (the cover-page count at the period end). **Every comparison
  is made on D0's RAW basis:** a count from a filing is multiplied, and a per-share price divided, by `S(end, D0)` = the
  cumulative split ratio between the fact's `end` date and D0 — era B: the product of the `cb702_splits.psv` ratios executing in
  (end, D0]; era A: `S(end, D0) = factor(end) ÷ factor(D0)` with factor(d) = raw close(d) ÷ adjusted close(d) from the raw file
  (a reverse split gives S < 1, handled identically; no raw close on either date = unknown). A split executing between the
  fact's `end` and its `filed` date is a basis the cover page may already carry: that name's cap and dilution = **unknown**,
  counted — never guessed either way.
- **History.** A night is admitted only if the 120 bars ending at D0 are CONSECUTIVE sessions of its era's calendar
  (`cb.contiguous_window_mask`; 6,018 of the Polygon file's tickers have a hole inside their span: halts, thin names, two
  companies glued onto one reused symbol). **Identity guard (round 2):** `cb702_pre/symbol_guard.tsv` (the `ext_bars.py` guard:
  578 of 9,944 symbols carry a `jump` / `hole` break) is passed as `--breaks`, a night with a break inside its 120 bars is counted
  `identity_break`; **the SAME guard is run over the refetch output** (a symbol REUSED by a later company keeps that company's
  bars under the old name — the refetch's own docstring) and its table is pinned beside the refetch. Live scores a name with as
  few as 60 rows and never checks consecutiveness; those nights are counted under the `history` funnel row, disclosed. The walk
  stops BEFORE the first bar that follows a missing session and the episode is `degraded` (counted, never in a number) — R is
  never booked across a halt or onto another company's prices.
- **Security type, identity and CIK — POINT-IN-TIME from Polygon's reference records (round 2).** The 10-22 sources
  (`mi_security_types`, the SIC pull, SEC `company_tickers.json`) are CURRENT-ONLY: a name delisted since has no row in any of
  them, so they re-introduced survivorship through the type and the CIK after the bars had been fixed. Ticker `^[A-Z]{1,5}$` as
  live's pattern (675 export symbols with other characters are out); exchange test symbols out (`cb.is_test_symbol`). STEP 0
  pulls Polygon `/v3/reference/tickers` TWICE — `active=true` and `active=false`, `market=stocks`, `limit=1000`, `next_url`
  followed to the end — and saves both (`polygon_reference.jsonl.gz`, pinned). Each record carries ticker, name, type (CS / ADRC
  / ETF / WARRANT / RIGHT / UNIT ...), cik, composite_figi, share_class_figi and, for a delisted record, `delisted_utc` (e.g.
  TWTR: type CS, CIK 0001418091, delisted 2022-10-31 — verified on our plan 10-23). **The record that OWNS a (ticker, D0):**
  among the symbol's records, the delisted one with the smallest `delisted_utc` ≥ D0 if any, else the active record; no record =
  unknown. The owning record's span must contain D0's bars: a bar under the symbol dated after the owning record's
  `delisted_utc` belongs to a later issuer and is never in the window; the active record carries no listing date here, so for an
  active-owned (ticker, D0) the identity guard above is the only lower bound (a symbol reused after an earlier delisting is
  caught first by that earlier record's `delisted_utc` ≥ D0). Two
  delisted records with the same `delisted_utc`, or a record whose `name` disagrees with the SEC submissions `name` for its CIK
  beyond a printed normalisation (corporate suffixes, punctuation, case) = unknown, listed. **Type = the owning record's
  `type`**; only where the symbol has NO Polygon record: `mi_security_types` (`small_pulls.psv` `sectype` rows, 14,101 names),
  else the SIC pull's `type` (`cb702_sic.psv`, 3,942 names), else unknown — the path is printed per name and counted (expected
  rare). **CIK = the owning record's `cik`**, point-in-time for a delisted name exactly as for a live one; every SEC call below
  is BY CIK (`data.sec.gov/submissions/CIK##########.json`, `companyfacts/CIK##########.json`, the Archives path by CIK +
  accession) — NEVER by symbol: `dei:TradingSymbol` does not exist in companyfacts (the 10-22 text leaned on it; gone) and
  `company_tickers.json` lists today's symbols only. **Warrants, units and rights are out of both populations:** by type when
  typed, and by the suffix rule when not — a 5-letter symbol ending in W / U / R (1,274 / 863 / 238 in the Polygon export; the
  10-21 probe's top-60 small-cap run-ups held 12 warrants). P1 admits CS / ADRC / unknown as live's SQL does; **P2 requires CS or
  ADRC by the point-in-time type**, and its unknown-type names go to a counted beside row. The funnel prints `excluded: security
  type` and the type-source split (Polygon record / fallback table / unknown), per era.

**Two populations — the complement, one rule for every date, no switch at 2026-05-01.**
- **P1 = the live price and dollar-volume floors:** raw close ≥ $5 AND dollar volume ≥ $10M on D0 (`db.get_parabolic_universe`'s
  SQL, db.py:7462-7464). **The $250M market-cap floor is NOT in the deciding P1** — there is no cap history (`mi_market_caps` is one
  overwritten row per name; `mi_parabolic_candidates.market_cap` is a 30-day cache, only since 05-01 and only for names that passed
  the $5 / $10M pre-filter), and the floor is his signed rule (ADR 0020 J4), so it is applied as a BESIDE row, below, never
  silently. Disclosed: the deciding P1 is "the live floors without the cap floor".
- **P2 = small caps = the complement band, DELISTED NAMES IN (round 2):** (raw close < $5 OR dollar volume < $10M) AND raw
  close ≥ $1 AND dollar volume ≥ $2M, type CS / ADRC **by the point-in-time Polygon record** — so a small cap that later
  collapsed and was delisted (the short's best cases) is in P2 on the nights it traded, typed and CIK-mapped by its own delisted
  record, with its bars from era B's Polygon file or era A's refetch. The 10-22 rule required CS / ADRC from current-only tables,
  which kept mostly survivors; that rule is gone. The $1 / $2M floors are a tradable floor fixed now by me, not his; a different
  floor is his call. By construction **P1 ∩ P2 = ∅ on (ticker, D0)** and **P1 ∪ P2 ∪ P2's unknown-type row = every admitted
  name (symbol, test-symbol and W / U / R rules applied) with raw close ≥ $1 and dollar volume ≥ $2M** — both are runner
  assertions, not expectations. STEP 0 prints P2's point-in-time cap distribution where known (the share under $250M), so "P2 is
  small caps" is a printed number, not a label — **and the survivorship check: the share of P2 climax names whose owning record
  is a DELISTED one, per era.** The REFUSAL is structural, not a guessed number: era A refuses without the refetch, its RAW
  companion and both guard tables pinned, and either era refuses when that share is ZERO (the delisted names did not arrive).
  The expected shares (≥ 25% era A, ≥ 15% era B) are EXPECTATIONS below — printed, a miss reported first, never a stop on an
  unmeasured quantity. A blocker closed on paper is not closed; this is the number that shows it took.
- **The SQL pre-filter's two other conditions are not re-applied because the detector re-tests them:** `close / sma_50 ≥ 1.5` is
  gate 3 (`_MIN_EXT_VS_SMA50`), and `close / low_60d ≥ 1.5` is implied by gate 2 (the base low is a low inside the last 60
  sessions, so the prior move ≥ 50% at any tier implies it). Only type, the price floor, the dollar-volume floor and history are the
  runner's to apply; everything after is `compute_parabolic_metrics` on the 120 rows, `rows[-1].trade_date == D0` asserted.

**One cap rule for every date (point-in-time, from the pull read 5 needs anyway).** cap(D0) = the latest SEC XBRL companyfacts
`dei:EntityCommonStockSharesOutstanding` of the latest PERIODIC report (10-K / 10-Q / 10-KT / 10-QT / 20-F) with `filed` < D0 in
the submissions list (fetched by the owning Polygon record's CIK; the fact matched to the filing by `accn` — the same filing read
5 reads), × `S(end, D0)` (the Units bullet: the filing's count moved onto D0's raw share basis), × RAW close(D0). No CIK, no
periodic report filed before D0, no cover-page fact on it, more than one undimensioned value on it (multi-class names), a split
between the fact's `end` and its `filed` date, or no raw close on either date = **unknown**, counted. Used three ways: (1) **the detector's tier in BOTH
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
  collector.py:1262-1300; fetched by the owning Polygon record's CIK, never by symbol): an **8-K with item 2.02** accepted on D0 − 1 or D0 (acceptance converted to ET; after 16:00 ET = the next
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
  `degraded` (the walk met a hole), `void_distribution_suspect` (next bullet), open at the end of the file. Mean R, the interval
  and every read are over settled episodes.
- **Distribution artifacts — a stated rule; a spin-off is never booked as a covered short (round 2).** #705 found 10-23 that the
  Alpaca export adjusts splits but NOT spin-offs or special distributions (OPLN = the KAR → IAA spin-off 2019-06-28 read as a −62%
  session; ZWS 2021-10-05; BEP 2020-07), that Alpaca's split-adjusted and all-adjusted bars are identical on those cases, and
  that its corporate-actions feed covers ~2020+ under the OLD symbol only — so no source can be relied on, and the Polygon file is
  treated the same. For a SHORT such a gap is a windfall, and a −30% open is also what this setup HUNTS — so the rule is stated
  honestly: **no bar-level test discriminates a spin-off from a real collapse** (#705 step 5's "new listing within [−2, +1]
  sessions" matched 1–32 listings on EVERY gap date in `05_local_checks.txt` — SPACs and IPOs list most weeks — so it is a HINT
  column, not the rule). **The rule:** a session in D0 + 1 .. D0 + 7 (the sessions an episode can occupy) whose open ÷ prior
  close − 1 ≤ −0.25 makes the climax a `distribution_suspect`, listed in `distribution_suspects.tsv` (ticker, D0, gap date, gap,
  prior close, the new listings in [−2, +1] as the hint, Alpaca's corporate-actions answer where it has one); **the class is
  written at STEP 0, from bar facts, BEFORE any walk** — the operator or the main loop marks each `real_move` / `distribution`
  in `distribution_class.tsv` (pinned with the STEP 0 files), so no class is made knowing which void restores a winner. A
  `distribution` episode is `void_distribution_suspect`: counted, never in a number; an UNCLASSED suspect stays void; the beside
  row prints n and mean R with every suspect in, so the size of the exclusion is on the record. Executable check at STEP 0: the
  flagger run over the raw bars alone, independent of the climax list, must list OPLN 2019-06-28 and ZWS 2021-10-05, or the run
  refuses.
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
   printed by year beside the read (Polygon's coverage changes over time). **Pagination (round 2):** TWO pulls per episode, each
   with its own window — this read's three-session window, and row (a)'s [D0 − 30 calendar days, D0] (the 10-22 text sliced one
   pull for both, which fails whenever the run start lies more than 30 days before D0). Each pull asks `limit=1000` (Polygon's
   page maximum), `order=desc`, `sort=published_utc`, and follows `next_url` for at most **K = 3 pages (3,000 items)**. A pull
   whose 3rd page still carries a `next_url` is `truncated`: under `order=desc` the items lost are the OLDEST in the window, so
   the feature cannot be read either way and that pull's feature = **unknown** (read 3 unknown; row (a) drops nothing on an
   unknown and prints its count) — never "absent", never "present". Pages fetched and the truncated flag are columns of
   `features.tsv`; the pulls are saved once (`polygon_news.jsonl.gz`).
4. **A loss-to-profit swing blocks** — from companyfacts `us-gaap:NetIncomeLoss` (USD): a quarter = a fact whose period spans
   80–100 days; Q4 = the fiscal-year fact minus that year's 9-month fact when no 3-month Q4 fact exists; `filed` < D0. Swing = the
   latest such quarter positive AND the quarter before it negative. **Primary = a swing whose `filed` date falls inside
   [base_date, D0]** (his rule 5: the swing IS the news behind the run); beside = the last quarter filed before the climax,
   whenever filed. **Groups swing / no swing / unknown** (no CIK, no facts, fewer than two consecutive quarters); **difference =
   (no swing) − (swing)**, unknown excluded.
5. **Stealth dilution — P2 DECIDES, P1 beside.** Ratio = shares issuable from warrants and convertibles **newly unlocked by the
   run** ÷ shares outstanding, every term from the LAST filing with `filed` < D0. **"Unlocked" = the exercise / conversion price
   lies in (base low, raw climax close]** — the run-up crossed it from below (his words: "warrants that the run up will unlock");
   terms already deep in the money before the run are a beside row ("in the money at the climax", all of them). **Price basis:**
   both sides on D0's RAW basis — the raw close(D0) against the reported price ÷ `S(end, D0)`, share counts × `S(end, D0)` (the
   Units bullet: era B from the splits file, era A from the raw ÷ adjusted factor; a split between `end` and `filed`, or no raw
   close = unknown). **Company match:** the owning Polygon record's CIK (the identity rule above; point-in-time for delisted
   names); the submissions `name` is printed beside the record's name as the cross-check; no owning record = unknown. **Pairing —
   the SUM over tranches, not one pair (round 2).** Warrants and convertibles come in several tranches, so one undimensioned
   (count, price) pair rarely holds: companyfacts carries only undimensioned facts, and the 10-22 rule could pair 10 of 60. The
   FILING = the latest PERIODIC report (10-K / 10-Q / 10-KT / 10-QT / 20-F) with `filed` < D0 in the submissions list — the SAME
   filing the cap rule's cover-page count comes from (companyfacts matched to it by `accn`), never "the last filing that carries
   a tag": that rule would reach back to a quarter whose warrants were since exercised and count an overhang that no longer
   exists. Its XBRL INSTANCE — the instance document named in the filing index (`_htm.xml` for inline XBRL from 2019; the dated
   `<prefix>-<date>.xml` earlier, era A's 2016–2018 filings) by CIK + accession, saved as `xbrl_instances.jsonl.gz` — gives every
   fact of the tags below WITH its context, and a **tranche = one axis-member set** (e.g. the `ClassOfWarrantOrRightAxis`
   members) at the filing's balance-sheet date; tags are read from THAT instance only. Per tranche: warrant shares =
   `ClassOfWarrantOrRightNumberOfSecuritiesCalledByWarrantsOrRights` if present, else `ClassOfWarrantOrRightOutstanding` × 1 (one
   share per warrant, stated); price = `ClassOfWarrantOrRightExercisePriceOfWarrantsOrRights1`; convertible shares =
   `DebtInstrumentConvertibleNumberOfEquityInstruments` if present, else principal (`ConvertibleNotesPayable` / `ConvertibleDebt`,
   current or non-current) ÷ `DebtInstrumentConvertibleConversionPrice1`, same tranche; a variable-price convertible has no fixed
   price. The undimensioned fact is itself a tranche ONLY when the instance holds no dimensioned fact for that tag. **Overhang,
   primary = Σ over tranches whose price, on D0's raw basis, lies in (base low, raw climax close]** — newly unlocked by the run,
   his words; **beside = Σ over ALL tranches with price ≤ raw climax close** (in the money at the climax). Denominator = the
   cover-page shares of the SAME filing, on D0's basis. **Unknown, pre-decided:** a tranche with a count but no price, or a price
   but no count, makes the whole NAME unknown (never a lower bound, never the paired subset); a filing with none of the tags is
   ratio 0 ONLY when the instance was fetched and parsed (HTTP 200, well-formed) — a fetch or parse failure is unknown; no CIK, no
   filing before D0, a 6-K / 20-F filer whose instance carries no us-gaap warrant or convertible tag, a split between `end` and
   `filed` = unknown, each reason its own count. Buckets **≥ 20% / < 20% / unknown**; **difference = (≥ 20%) − (< 20%)**, unknown
   excluded, never imputed. **Coverage, restated honestly:** the 10-21 probe
   (`scripts/probes/_314_xbrl_coverage_1021/probe.out`) mapped 40 of 60 names to a CIK by today's `company_tickers.json` (the
   point-in-time Polygon CIK can map MORE of the delisted ones, never fewer) and counted each tag at ANY filed date, one tag at a
   time: warrant count 12, exercise price 18, conversion price 7, shares outstanding 34; count + price + shares on one filing =
   10 of 60; conversion price + (shares or principal) + shares outstanding = 4 of 60. The tranche sum recovers some of the names
   the one-pair rule lost, by an amount not yet measured; coverage filed BEFORE each climax is lower still. **So with n ≥ 30 per
   bucket this read is still expected to come back CAN'T TELL**; it is registered so the coverage number (names mapped, tranches
   paired, unknown reasons by count) is on the record and the recording rule below can still apply. Each group's N is printed at
   STEP 0, before any walk.

**STEP 0 — derive and count the populations; walk nothing.** Before any outcome column exists the runner writes and prints, per
population AND per era: the funnel (ticker-nights → symbol / test symbol → owning record / security type → `raw_unknown` → raw
price band → dollar volume band → consecutive history → `identity_break` → each detector gate in order: dollar volume (patched in
P2), base anchor, prior move by tier, SMA extension, acceleration, burst score, gapped today, climax volume, days-up streak →
climax), the climax count per calendar year, the cap-tier and cap-source counts, the type-source and CIK-source counts, the
delisted share of P2 climax names (the survivorship floor), the reachability proxy, the tally of adjusted-pass / raw-fail nights,
the overlap-disagreement share, and the distribution flagger's full list with its OPLN / ZWS check. The one-open-episode rejection needs
the earlier episode's outcome date, which only the walk produces, so the climax → `episode_already_open` → armed tally is printed
by the WALK's own summary, not here; the pinned list is the pre-walk population through `climax`. It writes
`climax_list.tsv` (ticker, D0, era, population, tier, cap, cap source, the owning Polygon record — type, cik, `delisted_utc` or
active — type source, earnings flag, reachable flag) and `features.tsv` (pause count, run length, anchor flag; per news pull:
group, item date, HTTP status, pages fetched, truncated flag; swing group, filed date; dilution bucket, ratio, tranche count,
filing accession, filed date, unknown reason; the M&A keyword flag and item date; the 8-K 2.02 flag and acceptance date),
`distribution_suspects.tsv`, and the saved pulls (`polygon_reference.jsonl.gz`, `xbrl_facts.jsonl.gz`, `xbrl_instances.jsonl.gz`,
`edgar_submissions.jsonl.gz`, `polygon_news.jsonl.gz`). **All of them are pinned (`--print-pins`) in a commit BEFORE the walk; the
walk refuses to start without those pins** — and, for era A, without the refetch, its RAW companion and both identity-guard tables.

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
  AGL or XMTR lists its gate and REFUSES the run. **Era A golden, PRINTED only (round 2):** GME January 2021 — the 05-01
  initial-ship evidence (`docs/setups/parabolic_short.md`:298, "3 anticipations during squeeze") predates the 05-08 gates, so the
  runner prints GME's stage and every gate value for each session of 2021-01 from the Alpaca file and lists a miss, never a
  refusal; the synthetic walk goldens are era-agnostic (both files share the layout) and run against each era's loader.
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
  read 3 rises across 2016→2026; the read-5 known buckets are under 30 each even with tranche sums (CAN'T TELL); the
  reachable-3R share is under 50% in P1. **Round 2:** the delisted share of P2 climax names is ≥ 25% in era A and ≥ 15% in era
  B (printed; the structural refusal is a zero share); the delisted names carry a HIGHER settled mean R than the survivors in P2
  (the sign the survivorship fix should show for a short; a miss says the collapse came after the window); era A's climax count
  per calendar year is within 2× of era B's per-year mean (a miss is a source / calendar difference to read, not a rule); of the
  `distribution_suspect` climaxes, under 10% are classed `distribution` (a parabolic short produces real −25% opens; a miss is
  itself a finding about the window); truncated news pulls are under 1% of pulls; the overlap-disagreement share is under 1%.
- **WOULD-FAIL-IF (checks the runner PERFORMS; any one exits non-zero and writes no report):** `rows[-1].trade_date == D0` on every
  scored night and the 120 rows are consecutive SPY sessions; a feature dated after its cut-off (news after the window's close
  for read 3 / after D0 for row (a); any filing with `filed` ≥ D0 in reads 4–5 or the cap; an 8-K acceptance after the session it
  is charged to); an episode in two groups of one read, or in none; P1 ∩ P2 ≠ ∅, or P1 ∪ P2 ∪ P2's unknown-type row ≠ the $1 / $2M
  band; a name with two open episodes on one night; the patched constant ≠ 2,000,000 in the P2 process or ≠ 10,000,000 in P1; the
  walk goldens off by more than 1e-9 or the AGL / XMTR goldens off on any gate; the walk's climax set ≠ the pinned
  `climax_list.tsv`; a settled episode whose
  entry ≤ D0 or whose exit > entry + 4 sessions (5-stop) / + 2 (3-stop); a read-1 pair whose two walks differ in entry; a realized
  R not equal to 1/3 + 2/3 × exit-leg R when the flush was taken; the export's sha256 ≠ the pin; any pinned module changed.
  **Round 2:** a 120-row window or a walk drawing a bar from the other era's file; an era-A night walked without the refetch,
  its RAW companion and both identity-guard tables pinned; a name placed in a population by an adjusted price; a CIK or a type
  taken from a symbol-keyed current table where an owning Polygon record exists, or any SEC call made by symbol; an owning record
  whose span does not contain D0; a cap or a dilution ratio computed across a split between the fact's `end` and `filed`, or
  with a count and a price on different bases; a dilution ratio on a name with an unpaired tranche; a truncated news pull
  counted as present or absent; a `distribution_suspect` episode in n without a `real_move` class, or a class file dated after
  the walk started; the flagger not listing OPLN 2019-06-28 and ZWS 2021-10-05; a delisted share of P2 climax names equal to
  zero in either era; read 5 or the cap reading a filing other than the latest periodic report before D0.

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

**The consequence grid — every cell named (round 2; the 10-22 text left the CAN'T TELL cells and the unknown groups implicit).**
"Proposal" = put to him with n; nothing is flipped by this doc. The base verdict, P1 × P2 (n on every cell when read):

| P1 ↓ · P2 → | P2 PASS | P2 CAN'T TELL | P2 FAIL |
|---|---|---|---|
| **P1 PASS** | proposal: a P2 shadow lane with its own borrow check (the $250M floor is his signed rule — CHANGE_PROCESS); P1 = the candidate for the next rung (paper is his call) | P1 as the left cell; P2: no lane; the shortfall (n or tail) named with what would make it decidable, a dated re-read filed only if a dated event supplies it | P1 as the left cell; P2: no lane; "small caps as floored here FAIL" reported with n — the floor question closes on this evidence and reopens only under a new registration |
| **P1 CAN'T TELL** | P1: the live shadow continues unchanged, no rung; P2: the lane proposal as above | nothing changes anywhere; both shortfalls named; no re-read without a dated event (data cannot be manufactured) | P1: nothing; P2: the FAIL reported with n, no lane |
| **P1 FAIL** | P1: the live shadow keeps running and the FAIL goes to him with n — retiring the lane is his call (the 10-21 stretch item); P2: the lane proposal, flagged that the floored version failed | P1 FAIL to him as left; P2: nothing | both FAILs to him with n; the setup review (the 10-21 stretch) carries them; nothing live changes |

Per read, per population (a read run on both populations that separates in one and not the other is recorded for BOTH — the
feature is one column — with the per-population result on the record):

| read outcome | consequence |
|---|---|
| separates in HIS direction (lower end > 0; n ≥ 30 per group) | RECORDED on the shadow's rows as a feature (pause count / news group / swing group / dilution ratio + tranche count / 8-K flag) — a recording, not a rule, a CANDIDATE (the 22% chance note); adopting it as a gate or an exit = CHANGE_PROCESS + his sign-off; read 1 (a signed value) is reported to him, never applied |
| separates AGAINST him (upper end < 0) | reported with its sign and n; NOT recorded; nothing changes |
| CAN'T TELL (a group under 30, or the interval spans zero) | NOT recorded; the group sizes printed; no re-read without a new registration |
| unknown-dominated (the unknown group > 50% of the population's settled episodes) | the row reads "coverage-bound": NOT recorded whatever the known groups show; the consequence is a DATA proposal to him (a point-in-time source for the missing input), never a rule |
| read 5 with known buckets under 30 (the expected reading) | CAN'T TELL as above; the coverage number — names mapped, tranches paired, unknown reasons by count — IS the deliverable and goes on the record |
| the unknown-dilution group itself (no CIK / no filing before D0 / unpaired tranche / split between `end` and `filed` / fetch or parse failure / 6-K filer) | never imputed, never pooled; its N and reason mix printed; in the FORWARD shadow an unknown-dilution name is NOT rejected (there is no dilution gate; a recording only) |
| the `not recorded` outcome of any read | the shadow's rows do not gain that column; the replay's `features.tsv` keeps the value for a later registered read; nothing else |

## What the read may NOT do

- Switch the deciding population band, the P2 floors, a read's primary variant, a cut (≤ 2 / ≥ 3, 20%, 0.20), the time-stop
  counting, the n floor, the seed or the draw count — after this registration, for any reason. A beside row is never a finding.
- Impute an unknown into a group; pool unknown into "the rest"; walk before the STEP 0 pins are committed; run a population twice
  (the `episodes.tsv` and its `.partial` refuse a second run; the operator removes them by hand); edit this document above the
  marker after the freeze commit.
- Walk era A on the survivors-only export alone; place a name by an adjusted price; take a CIK or a type by symbol from a current
  table where a point-in-time record exists; restore a `distribution_suspect` without a written STEP 0 class; move the era
  boundary, the −25% gap cut, the page cap K, the filing rule or the tranche rule after this registration.

## What this does not answer

- Borrow availability and cost (the binding real-world limit on small-cap shorts; assumed easy at both checks); intraday entries
  (his top-day short on "losing momentum") — the replay is daily; his adds / pyramiding; the large-cap "obvious news-driven
  parabolic" judgement; the Perplexity exclusion's real effect (the keyword row is its $0 half); the earnings gate's effect on this
  population (unknown in the primary; the 8-K row is a substitute, not the live source); names live scores on 60–119 rows; XBRL
  coverage limits every read that needs a filing.
- **Survivorship AFTER the fix:** a delisted name that Polygon's reference lacks, or whose Alpaca bars are not served by symbol,
  is still missing — the delisted share printed at STEP 0 bounds the fix, it does not prove completeness; era-A names with no raw
  close (`raw_unknown`) are out of both populations, counted. Borrow is the harder limit for exactly these names: hard-to-borrow
  is the norm in a collapsing small cap, so P2's n overstates what could have been shorted even more than P1's (assumed easy at
  both checks, as before).
- **Spin-offs the distribution rule cannot see** — a distribution with no new listing in either file (a cash distribution, a
  foreign-listed spin): the hand class on the listed suspects is the only backstop, and the beside row with suspects in bounds
  the effect on the result. Polygon's file was not checked for spin-off adjustment either; it is treated as unadjusted.
- **Foreign private issuers (20-F / 6-K):** no 8-K item 2.02 exists, and their instances often carry no us-gaap warrant or
  convertible tag — unknown in reads 4–5 and the 8-K row, their own count, never "none".
- **The tranche parser's reach:** a filing that reports warrants only in text (no dimensioned fact) reads as ratio 0 if the
  instance parses — a false "no overhang" the rule cannot distinguish; the count of ratio-0 names with warrant-related text tags
  (`ClassOfWarrantOrRightTitleOfSecurityWarrantsOrRightsOutstanding`) is printed as the bound.

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

## Revisions 2026-10-23 (round 2 — the 10-22 recheck's findings; each fixed in the body before any outcome; nothing run)

Facts used, verified by the main loop 10-23 (not re-verified here; no network): Polygon `/v3/reference/tickers` `active=false`
is on our plan and returns type + CIK + `delisted_utc` per delisted ticker; Polygon daily aggregates reach back only to 2021-10;
Alpaca serves split-adjusted daily bars by symbol for delisted names back to 2016; the 2017-21 export is survivors-only and a
free refetch of the delisted names is running; Alpaca's bars and corporate-actions feed do not cover spin-offs; the 10-21 XBRL
probe mapped 40 of 60 and found exercise prices for 18, conversion prices for 7.

- **BLOCKER 1 — the CIK and security-type sources were current-only (survivorship through the type and the CIK)** → fixed:
  §Security type, identity and CIK — type AND CIK come from the Polygon reference record that OWNS (ticker, D0) (delisted record
  with the smallest `delisted_utc` ≥ D0, else the active one), pulled twice at STEP 0 (`active=true` / `false`) and pinned; the
  current tables are a printed, counted fallback only where no record exists; every SEC call is by that CIK. Bars for delisted
  names: era B's Polygon file already holds them; era A gets the delisted refetch.
- **BLOCKER 2 — P2's CS / ADRC rule kept mostly survivors** → fixed: P2 restated with the point-in-time type, delisted names
  IN; the survivorship check is a printed number (the delisted share of P2 climax names per era) with a STRUCTURAL refusal (the
  refetch, its RAW companion and the guards pinned; a zero share refuses) and the numbers (≥ 25% era A / ≥ 15% era B) as
  expectations that can miss — so the blocker's closure is visible in the output, not asserted, and no unmeasured floor stops
  the run.
- **MAJOR — `dei:TradingSymbol` does not exist in companyfacts** → fixed: removed; the company match is the owning record's CIK,
  the submissions `name` a printed cross-check; `company_tickers.json` dropped (today's symbols only).
- **MAJOR — double-split risk** → fixed: the Units bullet — bars split-adjusted to the export's as-of date; raw close(D0) the
  printed dollars; filing counts and prices on the fact's `end` basis; every comparison on D0's raw basis via `S(end, D0)` (era B
  the splits file, era A the raw ÷ adjusted factor); a split between `end` and `filed` = unknown; the cap rule and read 5's price
  basis both point at it.
- **MAJOR — one (count, price) pair rarely holds** → fixed: read 5 pairs PER TRANCHE from the filing's XBRL instance (axis
  members), overhang = the SUM over tranches with price in (base low, raw climax close] (primary, newly unlocked, his words) and
  over all tranches with price ≤ climax close (beside); an unpaired tranche makes the name unknown, never a lower bound;
  ratio 0 only on a parsed instance; the instance pulls saved and pinned. The primary was NOT flipped — the finding fixed the
  pairing, not the cut.
- **MAJOR — news pagination unstated** → fixed: two pulls per episode (read 3's window and row (a)'s — the one-pull slice failed
  when the run start was more than 30 days before D0), `limit=1000` per page, K = 3 pages, a 4th `next_url` = truncated = unknown
  for that pull (the oldest items are what `order=desc` loses); pages and the flag are `features.tsv` columns.
- **MAJOR — consequence-table gaps** → fixed: the grid — P1 × P2 (nine cells) and the per-read table including CAN'T TELL,
  unknown-dominated, read 5's expected reading, the unknown-dilution group itself and the `not recorded` outcome.
- **ALSO — the era** → fixed: two eras, one bar source each (era A Alpaca D0 2016-06-23..2022-03-16 on the pre-export + refetch;
  era B Polygon 2022-03-17..2026-10-07), ownership in the overlap stated, no straddling as an assertion, per-era printing; the
  raw close in era A from `daily_raw_close.csv.gz` and a RAW companion of the refetch (registered as required; does not exist
  yet); the identity guard on both files; the GME 2021-01 printed golden.
- **ALSO — distribution artifacts** → fixed: the stated rule — a ≤ −25% open in D0 + 1 .. D0 + 7 makes the climax a suspect
  (the #705 new-listing match is a printed hint, not a discriminator: it fires on every gap date), the class written at STEP 0
  from bar facts before any walk, `distribution` = void with a beside row, an unclassed suspect void, the OPLN / ZWS executable
  check.
- **ALSO — read 5's filing** (found in the round-2 review): "the last filing carrying a tag" would resurrect exercised tranches
  → the filing is the latest periodic report before D0, the same one the cap's cover-page count comes from; the instance name
  follows the filing index (pre-2019 instances are the dated `.xml`, not `_htm.xml`).
- **ALSO — borrow** → kept as a stated limit, restated for delisted small caps under "What this does not answer".

<!-- FREEZE -->
## Freeze record

The doc body pin covers every byte above the `<!-- FREEZE -->` marker. The run verifies every pin before it opens the export and
refuses on any mismatch (the `freeze_check` pattern of `scripts/probes/_cb_backtest/runner.py`); STEP 0 runs first and its outputs
are pinned in a second commit before the walk; the RESULT is appended below this record. Pins computed 2026-10-22 and 2026-10-23
(`shasum -a 256`) for the data and the two frozen modules; the runner, the CB module (`raw_factor_for` / `contiguous_window_mask`
/ `is_test_symbol`), the test module (the goldens), the STEP 0 files and the doc body are printed by `--print-pins` and pasted
here in the commits that precede the run.
- cb702/daily_closes_all.csv.gz sha256: `ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba`
- cb702/cb702_splits.psv sha256: `3199d06d5fb7dcd52ebd34e8c71e148b45ec0ca4a15f7f03ea1b715718882b0b`
- cb702/small_pulls.psv sha256: `b8d37aae5ef85c25bc52479eef7f6b04a8a4e67557caaef7a426d8ae20194643` (fallback type source only)
- cb702/cb702_sic.psv sha256: `0e476c4422d56648d615c48d941edb971a348dfb99821023116d0fd98e617346` (fallback type source only)
- cb702_pre/daily_closes_all.csv.gz sha256: `b10eea41775e657939c64e314068cb3c606d23d44de8488649fb67a4ac5ed773` (10-23)
- cb702_pre/daily_raw_close.csv.gz sha256: `2cd4242e7b4b3f5b3a01e65e055e7e165f3fa5ccf71dda8871be0cc7a31fccde` (10-23)
- cb702_pre/sessions.txt sha256: `098a9b50c92a1045043bc089a4d4d600a9631bdb45a8e22969d872440672f2f0` (10-23)
- cb702_pre/symbol_guard.tsv sha256: `6665c69f41bff3bd6ea913c66ccb9d0eab8bed0a9f020c32fa50c85d6cb6e6fc` (10-23)
- the delisted refetch (`01_fetch_delisted.py` output + `.log`), its RAW companion, and the refetch's symbol_guard sha256:
  (pasted when they land, BEFORE STEP 0; era A refuses without all three)
- polygon_reference.jsonl.gz / xbrl_instances.jsonl.gz / distribution_suspects.tsv / distribution_class.tsv sha256: (pasted after
  STEP 0, before the walk)
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
