# #314 — the parabolic short, replayed over five years: the base count, small caps, his selection rules, the time stop and stealth dilution — pre-registration (2026-10-21, revised 2026-10-22, 2026-10-23 and 2026-10-25 twice, BEFORE any replay outcome; REGISTERED, NOT FROZEN)

**Why.** The live shadow (since 2026-10-17; first market night 10-19) has armed n = 0 episodes, so nothing is known about how the
setup performs. The operator shared a short seller's stated rules (2026-10-20, `docs/methodology/operator_shared_notes.md`; mapped
in `docs/analysis/parabolic_short_vs_shared_short_rules_2026-10-20.md`) and ruled: *"Yes, but let's do this in weekend. Also, his
play is to short small caps, out filters are mainly for EPs, we haven't tested small caps for parabolic shorts"*; and on dilution:
*"it's not recent offering, the whole idea is stealth dilution that is in the horizon. Offering is after the fact"* / *"Eg warrants
that the run up will unlock and convert to shares is the exact example given"*. $0; shadow only; no paper, no live; entry / adds /
exits for money are his call (THE LINE). Revised 2026-10-22 against the review and 2026-10-23 against the recheck (§Revisions,
bottom: round 1, then round 2 — the round-2 blockers were survivorship in the type / CIK sources and in P2's population rule),
and 2026-10-25 (round 3) against the rebuilt 2017–21 file `apollo_data/cb702_pre_v2/` (the fix for the recheck's two data
blockers: one company under two symbols, and truly gone companies missing) and the standing data standard
(`docs/methodology/backtest_data_standard.md`), whose sealed-table rule ends era B at 2024-12-31 — nothing below has been run.
Round 4 (2026-10-25, second pass) applies the 10-25 review of round 3 (§Revisions, last table). **No #314 replay outcome exists
on either file** (`cb702_pre` or `cb702`; none was ever run — no climax list or episode file exists anywhere on this machine,
checked 10-25), so this read has no earlier reading to hold or change.

## Method / population

**Bars and the calendar — TWO eras, one bar source each, never straddled (round 2); era A = the rebuilt file, era B ends at
the seal (round 3).** The 10-22 registration ran on the Polygon file alone, which starts 2021-09-27, and Polygon's daily
aggregates on our plan reach back only to 2021-10 (2021-10-01 and earlier return 403; verified 10-23). The earlier years come
from Alpaca, which serves daily bars BY SYMBOL for delisted / acquired names back to 2016 although its `/v2/assets` list omits
them. **Nothing dated after 2024-12-31 is read (round 3):** the 2025–26 table is the sealed holdout, and the data standard's
§4 step 7 forbids reading it for any outcome. The round-2 text ran era B to 2026-10-07, which would have spent the seal.
- **Era B (Polygon) = D0 in [2022-03-17, 2024-12-19]:** `apollo_data/cb702/daily_closes_all.csv.gz` (Polygon, split-ADJUSTED as
  of 2026-10-16; the whole file is 13,830,569 rows / 20,285 tickers / 2021-09-27..2026-10-16, columns
  ticker/date/open/high/low/close/volume, no header; sha256 pinned below = the CB registration's pin). **Read through
  2024-12-31 only: 8,619,626 bars, 15,702 symbols, 821 sessions** (the data standard's printed span); the loader drops the
  5,210,943 later bars unread, and "no bar after 2024-12-31 in any window or walk" is a runner ASSERTION. It INCLUDES names
  delisted since (Polygon-based, point-in-time symbols). Calendar = SPY's 821 sessions to 2024-12-31 (cross-checked against the
  NYSE calendar 10-25: 821), written to `calendar_B.txt` at STEP 0 and pinned there (round 4). The **first scorable climax day D0 = 2022-03-17** (the 120th session: the detector is handed its
  `_HISTORY_DAYS` = 120 rows ending at D0). The **last D0 that can settle = 2024-12-19**, derived from the rule, not fixed by
  hand: the trigger comes by D0 + 3 and the 5th held session (the entry counting as 1) is D0 + 7 = 2024-12-31, the seal. So era
  B has **695 scorable D0 sessions**; a climax on the 7 later sessions (2024-12-20..12-31) is "open at the seal", counted,
  never in a number. The one exception to "nothing after 2024-12-31": the `cb702_splits.psv` rows dated 2025–26 ARE read, only
  to undo the file's 2026-10-16 adjustment basis (RAW close, below) — a corporate-action table, never a bar or a feature.
- **Era A (Alpaca, REBUILT) = D0 in [2016-06-23, 2022-03-16]:** `apollo_data/cb702_pre_v2/` (built 10-23 by
  `scripts/probes/_705_survivorship_1023/08_build_v2.py`: the old export + the delisted refetch, de-duplicated and typed).
  `daily_closes_all.csv.gz` = **12,005,007 rows, 12,532 symbols, 2016-01-04..2022-06-30**, same layout (`export_stats.tsv`). It
  passes every gate of the data standard that runs on the file alone — S0, G1–G7, G9 (`audit_1023/verdict.txt`); G8 needs the
  settled trade list, so it runs on THIS read's episode list AFTER the walk (round 4: it cannot run at STEP 0); G10 is a report. The old survivors-only `cb702_pre` export is
  untouched (its sha256 still equals its round-2 pin) and is **NOT read** by this replay. Pins (sha256 from the files, 10-25):
  the export, its raw companion, `dedupe_applied.tsv`, the type table `small_pulls.psv`, `sessions.txt`, `symbol_guard.tsv`,
  `export_stats.tsv`, the verdict, the build script — freeze record. Calendar = `cb702_pre_v2/sessions.txt` (1,635 sessions,
  2016-01-04..2022-06-30; byte-identical to `cb702_pre/sessions.txt`, same sha256, so round 2's session indices stand); first
  scorable D0 = its 120th session = 2016-06-23; last era-A D0 = 2022-03-16 (session 1,562, the session before era B's first);
  **1,443 scorable D0 sessions**; D0 + 7 = 2022-03-25 < 2022-06-30 (round 2 wrote 03-28 — corrected). A name that stops
  trading before 2022-06-30 can run out of bars mid-walk (3,478 of the 12,532 symbols end early, against 2,384 of 9,944 in the
  survivors-only file) — `ended_mid_walk`, defined under n below.
- **How the truly gone companies are now present in era A (round 3 — the round-2 blocker, closed on file facts):** the
  survivors-only export was built from Alpaca's CURRENT asset list, so every company delisted since was missing. The refetch
  (`01_fetch_delisted.py` + `02_fetch_bars_from_records.py`) took every Polygon `/v3/reference/tickers` `active=false` record of
  type CS / ADRC delisted on or after 2016-01-04, dropped the RENAMES (a record whose composite or share-class FIGI matches an
  active record: 395 skipped — a renamed company that still trades is already in the export under today's symbol) and the
  symbols already in the export, and pulled Alpaca daily bars by symbol, split-adjusted AND raw, 2016-01-04..min(latest
  delisting, 2022-06-30): 3,739 + 31 straggler symbols requested, 0 failed after retries, 3,226 symbols with bars in the
  combined file (2,181,130 bars; `recall_check_combined.txt` — the two fetch logs print 3,203 + 26). The build then dropped the refetched symbols that were twins of a series already in the export
  (549 — Alpaca serves a renamed company under BOTH symbols), Alpaca's zero-volume forward-fill and bad rows (99,172 of
  1,845,030), and kept only (ticker, date) keys both the adjusted and the raw pull carry. **Result: 2,669 symbols added**;
  9,944 − 81 (whole symbols removed by the dedupe) + 2,669 = 12,532. File-level evidence that the gone companies arrived:
  TWTR, ATVI, EA and X carry all 1,635 sessions (data standard §3); the known-gone liquid names missing from era A fell to 29 of 513 = 5.7%
  (the ~9% control level is the acceptance); liquid names per session era A ÷ Polygon = 0.979–0.995 over the 10 overlap months
  (≥ 0.97 passes); liquid names whose series ENDS in each year 2016..2022 H1 = 90 / 129 / 141 / 122 / 109 / 174 / 94 (flat —
  it read 4 / 6 / 46 / 117 / 105 / … before); recall per COMPANY (a rename covered under today's symbol counts) = 259 of 264
  known-gone stock companies (98.1%) and 692 of 723 liquid 2022 stock companies absent by symbol (95.7%)
  (`05_recall_by_company.py`, `recall_by_company.txt`) — **round 4: both figures are a LOWER BOUND, printed BEFORE the 31-symbol
  straggler pass** (`recall_by_company.txt` written 10:57:33; the straggler bars 10:58:00; the combined file 10:58:18). Re-counted
  against v2's symbol list from that printout's own miss lists (file-only, 10-25): the known-gone list's 5 misses were AXNX,
  BBBY, LAZY, SCHN and VIAC — BBBY, LAZY, SCHN and VIAC now have bars in v2 (VIAC with no identifying record, M1 below), so 263
  of 264 have bars, AXNX the one absent; the 2022 list's 31 misses: 23 now have bars in v2 under their own symbol (OBNK, BBBY,
  BHG, CDAY, CPSI, DADA, HSC, LAZY, LPI, MCG, NOVA, PLYA, RLGY, SASR, SCHN, X, VIAC, VIACA) or under today's symbol (BOMN as
  BOC, PFHC as ACDC, SI as SICP, FREY as TE, SGMS as LNW — the 10-25 review's mapping; all five present in v2), leaving 8: 5
  real holes with no bars (ARIS, AXNX, INBX, MSPR, NXU) and 3 exchange test symbols (ZJZZT, ZVZZT, ZWZZT) — 715 of 723 (98.9%),
  715 of the 720 real companies (99.3%). The residual holes are listed under "What this does not answer".
- **Ownership in the overlap (2021-09-27..2022-06-30, both files):** era B owns every D0 ≥ 2022-03-17 (the first D0 with 120
  Polygon rows), era A every earlier D0. An episode's 120-row history AND its walk come from its era's file only — a window or a
  walk crossing the two files would mix two adjustment bases (Alpaca vs Polygon) and two calendars, so "no bar from the other
  file" is a runner ASSERTION, not a convention. STEP 0 prints, over the ticker-days both files hold, the share of adjusted closes
  differing by more than 0.5% (a printed number; decides nothing). Every count, funnel line and result below is printed PER ERA
  and pooled; the verdict is on the pooled settled set, the per-era rows beside with their n.
- **RAW close** (the live price basis on D0's own day). **Era B:** adjusted close × `cb.raw_factor_for(D0, splits)`, splits from
  `cb702_splits.psv` loaded with `runner.load_splits(through=2026-10-16)` (the 85 splits executing after the file's last day are
  dropped — they are not in the adjusted series). **Era A has no split table** (`cb702_splits.psv` starts 2021-09-27): the raw
  close is read per bar from `cb702_pre_v2/daily_raw_close.csv.gz` (headerless `ticker,date,raw_close`; the runner's
  `--raw-close` mechanism — the factor is measured per bar as raw ÷ adjusted). **Round 3: it covers the refetched names too** —
  the build pulled them with `Adjustment.RAW` beside the split-adjusted pull and kept only the (ticker, date) keys BOTH carry
  (about 130 rows where Alpaca's two feeds disagree left both files), so every era-A bar has a raw close and the `raw_unknown`
  funnel row is EXPECTED 0, printed, with the runner asserting that the raw file's key set equals the export's. The rule stays
  for any name without one: it is NOT placed by its adjusted price — it goes to `raw_unknown`, out of BOTH populations: reverse
  splits are routine in exactly these names, and an adjusted close would admit a $0.20 stock as "$10". Every PRICE FLOOR below is tested on the raw close (the CB universe's rule,
  `docs/analysis/cb_preregistration_2026-10-18.md` §pipeline). Dollar volume = close × volume, invariant under adjustment, used as
  is. Ratios, ATR, levels and R stay on adjusted bars. STEP 0 prints the ticker-nights that pass a floor on the adjusted price
  and fail it on the raw price, per era.
- **Units, in one place (round 2 — the double-split finding).** Bars = split-adjusted to the export's as-of date (era A Alpaca,
  era B Polygon). Raw close(D0) = the dollars actually printed on D0. XBRL share counts and per-share prices = the filing's own
  basis: the shares and dollars in force at the fact's `end` date (the cover-page count at the period end). **Every comparison
  is made on D0's RAW basis:** a count from a filing is multiplied, and a per-share price divided, by `S(end, D0)` = the
  cumulative split ratio between the fact's `end` date and D0 — era B: the product of the `cb702_splits.psv` ratios executing in
  (end, D0]; era A: `S(end, D0) = factor(end) ÷ factor(D0)` with factor(d) = raw close(d) ÷ adjusted close(d) from
  `cb702_pre_v2/daily_raw_close.csv.gz`, read on the name's last bar dated ≤ d (a period end on a weekend reads the Friday);
  a fact whose `end` precedes the name's first bar has no factor = unknown (a reverse split gives S < 1, handled identically;
  no raw close on either date = unknown). A split executing between the
  fact's `end` and its `filed` date is a basis the cover page may already carry: that name's cap and dilution = **unknown**,
  counted — never guessed either way.
- **History.** A night is admitted only if the 120 bars ending at D0 are CONSECUTIVE sessions of its era's calendar
  (`cb.contiguous_window_mask`; 6,018 of the whole Polygon file's tickers have a hole inside their span — a 10-22 count over
  2021-09..2026-10, not re-derived because re-deriving it would open the sealed rows: halts, thin names, two companies glued
  onto one reused symbol). **Identity guard — ONE table per era (round 3).** Era A: `cb702_pre_v2/symbol_guard.tsv` (the
  `ext_bars.py` guard re-derived by the build over the MERGED arrays, so it covers the refetched names: **667 of 12,532
  symbols carry a `jump` / `hole` break**; for every original symbol the dedupe did not touch it equals the old guard — 0
  differing, asserted by the build; the old file had 578 of 9,944). Era B: `scripts/backtest_data_audit/runs_2026-10-23/
  universe/symbol_guard_B.tsv` (the B-alone `run_all.sh` run, 1,292 symbols with a break; the data standard's G4 requires it on
  every 2022–24 read — round 2 had no era-B guard at all). **Which breaks count — an EVIDENCE rule (round 4; the review's H1).**
  The guard's `jump` is any > 70% one-session move WITHOUT a 3× volume event (or with a factor change), and its own docstring
  says GME January 2021 trips it ("noted, not tuned"): GME carries `2021-01-27:jump;2021-02-24:jump`, and 194 of the 310 era-A
  symbols with a jump also reach a 20-session dollar volume of $2M — so taking every jump as a splice would remove the
  multi-day squeeze climax, the class a short hunts. The guard tables are read AS PINNED (never re-derived); the runner
  classifies each break and writes the result to `breaks_applied.tsv` (symbol, date, kind, evidence, applied yes / no; pinned
  with the STEP 0 files), and only the APPLIED breaks are passed as `--breaks`:
  - a `jump` is APPLIED only with evidence of a splice or an unabsorbed action: `fac_change` — era A: the pinned
    raw ÷ adjusted factor (Units bullet) on the jump date differs from the prior bar's by more than 1%; era B: a
    `cb702_splits.psv` split executes on the jump date — OR the symbol is **multi-company**: ≥ 2 Polygon reference records
    (STEP 0 pull) with different company keys (company key below). A jump with neither on a one-company symbol is NOT applied:
    the night is admitted and flagged `jump_unevidenced`, counted, and a beside row prints n and mean R with every
    `jump_unevidenced` window removed (the guard's literal reading). A symbol with NO Polygon record has no company evidence
    either way: its jumps stay applied, as the guard reads them, counted;
  - a `hole` is always a hole in the session sequence, so a window containing one already fails the 120-consecutive-session
    rule; what the hole changes is the TYPE of the nights before it (owner rule, era A, below).
  STEP 0 prints, per population and era, the climax candidates removed by applied jumps, by holes, and those kept as
  `jump_unevidenced`. A night with an applied break inside its 120 bars is counted `identity_break`. **Era-B reuse below the guard's thresholds (round 3):** for an active-owned
  (ticker, D0) (Security type, next bullet), the 120-row window may not reach a bar dated on or before the latest
  `delisted_utc` among the symbol's other Polygon records of a DIFFERENT company (company key below differs) — those bars
  belong to an earlier issuer; such a night is counted
  `identity_break` too. This is the rule that catches the data standard's two guard misses (C6): INBX 2024-05-31 (Inhibrx sold
  to Sanofi; Inhibrx Biosciences took the symbol) and DOC 2024-03-04 (Physicians Realty merged; Healthpeak took DOC) —
  executable positive controls at STEP 0. Live scores a name with as few as 60 rows and never checks consecutiveness; those
  nights are counted under the `history` funnel row, disclosed. The walk stops BEFORE the first bar that follows a missing
  session and the episode is `degraded` (counted, never in a number) — R is never booked across a halt or onto another
  company's prices.
- **Security type, identity and CIK — POINT-IN-TIME from Polygon's reference records (round 2).** The 10-22 sources
  (`mi_security_types`, the SIC pull, SEC `company_tickers.json`) are CURRENT-ONLY: a name delisted since has no row in any of
  them, so they re-introduced survivorship through the type and the CIK after the bars had been fixed. Ticker `^[A-Z]{1,5}$` as
  live's pattern (era A: 176 of the 12,532 v2 symbols carry other characters and are out, counted 10-25 from the v2 guard
  table's symbol list; era B: 675 in the whole Polygon file, the 10-22 count); exchange test symbols out (`cb.is_test_symbol`). STEP 0
  pulls Polygon `/v3/reference/tickers` TWICE — `active=true` and `active=false`, `market=stocks`, `limit=1000`, `next_url`
  followed to the end — and saves both (`polygon_reference.jsonl.gz`, pinned). Each record carries ticker, name, type (CS / ADRC
  / ETF / WARRANT / RIGHT / UNIT ...), cik, composite_figi, share_class_figi and, for a delisted record, `delisted_utc` (e.g.
  TWTR: type CS, CIK 0001418091, delisted 2022-10-31 — verified on our plan 10-23). **The record that OWNS a (ticker, D0) —
  one rule PER ERA, because the two files key a symbol differently (round 3).**
  - *Era B (Polygon, point-in-time symbols — a bar under GPS on a date is the company that held GPS that day):* among the
    symbol's records, the delisted one with the smallest `delisted_utc` ≥ D0 if any, else the active record; no record =
    unknown. The owning record's span must contain D0's bars: a bar under the symbol dated after the owning record's
    `delisted_utc` belongs to a later issuer and is never in the window; for an active-owned (ticker, D0) the lower bound is
    the earlier-issuer rule in History above (round 2 called the guard the only lower bound — corrected).
  - *Era A (Alpaca, TODAY's symbol — META holds Facebook's 2016–22 bars, OPLN holds KAR's, XYZ holds Square's; data standard
    F3):* the record owns the whole SERIES, not the (symbol, date). A symbol of the original export = its ACTIVE Polygon record
    (Alpaca's asset list, and so the export, is today's); a symbol the refetch added = its record in
    `refetch_combined_records_1023.tsv` (the one the fetch cut its bars by; the 2 symbols listed with two records, MSPR and
    NXU, have one CIK per pair and no bars in v2 — round 4 removed the "date rule picks between the two" sentence).
    **Placeholder records (round 4; the review's M1):** the 31 straggler records (`stragglers_records.tsv`) were written with
    `delisted` = 2022-06-30 — the FETCH CUT-OFF, not a Polygon `delisted_utc` — and 18 of them own v2 series (BBBY, BHG, CDAY,
    CPSI, DADA, HSC, LAZY, LPI, MCG, NOVA, OBNK, PLYA, RLGY, SASR, SCHN, VIAC, VIACA, X); VIAC and VIACA (555 rows each) carry a
    blank type, CIK and FIGI. At STEP 0 every owning record whose `delisted` equals 2022-06-30 or whose CIK and both FIGIs are
    empty is RE-RESOLVED from the pinned `polygon_reference.jsonl.gz` (same symbol; a record whose span holds the series); the
    runner ASSERTS no owner still carries the 2022-06-30 placeholder date (an unresolved one = its date unknown, so its gone flag
    is unknown); one still empty-keyed after the pull = type / CIK unknown, listed (VIAC and VIACA may stay so — the recall
    printout found no Polygon record for either). 46 refetched v2 symbols have no CIK or FIGI at all (19 reaching $2M a day).
    The era-B date rule is NOT used on era A's original symbols: it would hand
    (META, 2019) to whatever delisted record once held the META symbol (the standard: B's META before 2022-06-09 is a
    different ~$10–16 instrument; `ext_bars.py`: META is Facebook in Alpaca throughout, BNY likewise), so Facebook's history
    would take that instrument's type and CIK. **Nights before a break (round 4; the review's H1 and H2):** a night dated
    before the symbol's last APPLIED break — an applied `jump` (evidence rule above), or a `hole` on a MULTI-COMPANY symbol
    (`ext_bars.py:10`: "two companies on one symbol shows up as a > 30-session hole") — belongs to an earlier, unidentified
    holder = type / CIK unknown, counted. A `hole` on a ONE-company symbol is a halt or a thin stretch: the nights before it keep
    the owner's type, flagged `pre_hole`, counted; a `jump_unevidenced` one-company symbol likewise keeps the owner's type
    before the jump. Of the 667 symbols with a break, 209 are jump-only, 357 hole-only, 101 both (counted 10-25); STEP 0 prints
    how many are one-company, multi-company and no-record. **Dedupe leftovers (round 4; the review's H2):** the set
    `alias_outside_span` is DERIVED from the files — every `dedupe_applied.tsv` dropped_symbol still present in v2: **15
    symbols, 2,927 rows**, all outside their dropped span (0 inside): AGC 667, XL 678, PTIE 340, BRPM 295, ARYA 237, MACQ 162,
    DDMX 151, SNH 125, VICL 101, BIOS 57, RSLS 52, KOOL 43, PRTHU 13, CYTX 3, RXII 3 (rows). They are Alpaca stacking companies
    on one symbol — XL 2016-01-04..2018-09-11 is XL Group, not XL Fleet / SPRU; ARYA 2018-12..2020-07 is ARYA I, not ARYA III /
    NAUT — and because the guard was re-derived after the twin rows were dropped, 13 of the 15 carry NO break (only RSLS and
    KOOL do): the seam left with the twin. Those rows take the **era-B date rule** — the record of that symbol whose
    `delisted_utc` is the smallest ≥ D0, else unknown — and NEVER the later holder's active record; STEP 0 prints the set with
    each row's owner. This is the only era-A use of the date rule: the review's wider "every multi-record symbol takes the date
    rule" is not adopted, because META shows it fails on a continuous today's-symbol series. The data standard's U8 count is 63
    admitted tickers / 0.96% of admitted nights typed by a later holder; and 46 of its 50 overlap reuse cases carry no break at
    all, so the break rules are a partial catch, stated. An
    original symbol with no active record (dropped from Polygon's active list by 10-25) falls to the latest-delisted record of
    that symbol, the path printed (`no active record -> latest delisted`).
  Two delisted records with the same `delisted_utc`, or a record whose `name` disagrees with the SEC submissions `name` for its
  CIK beyond a printed normalisation (corporate suffixes, punctuation, case) = unknown, listed. **Type = the owning record's
  `type`**; only where the symbol has NO Polygon record, the era's type table: era A `cb702_pre_v2/small_pulls.psv` (**17,028
  typed symbols** in 17,172 `sectype` rows — 144 symbols typed twice, 0 with two different types; the 17,172 ROWS (not symbols) = the 14,102 current
  `mi_security_types` rows of the old file + 2,667 refetched names typed from their own Polygon delisted record + 403 in-export
  names typed from a Polygon as-of-2021-12-31 pull; the 18 "left unknown" in `export_stats.tsv` are the untyped names in P1's
  $5 / $10M band (G6), not the whole file — **1,885 v2 symbols have no row in the table at all, all of them original symbols,
  and 460 of those pass the symbol rules and reach $2M a day (P2-band candidates)**; for them the table is a fallback only
  behind the Polygon record, and P2's untyped expectation below rests on that count), era B `cb702/small_pulls.psv` (14,102
  — round 2 wrote 14,101); then the SIC pull's `type` (`cb702_sic.psv`, 3,942 names; the era-A copy is byte-identical to era
  B's), else unknown — the path is printed per name and counted (expected rare). STEP 0 also prints, for era A, the agreement
  between the owning record's type and the v2 table's (the 2,667 refetched rows come from the same Polygon records: expected
  100%; the original rows are today's holder's type, as the series is: expected ≥ 99%, every disagreement listed). **CIK = the owning record's `cik`**, point-in-time for a delisted name exactly as for a live one; every SEC call below
  is BY CIK (`data.sec.gov/submissions/CIK##########.json`, `companyfacts/CIK##########.json`, the Archives path by CIK +
  accession) — NEVER by symbol: `dei:TradingSymbol` does not exist in companyfacts (the 10-22 text leaned on it; gone) and
  `company_tickers.json` lists today's symbols only. **Warrants, units and rights are out of both populations:** by type when
  typed, and by the suffix rule when not — a 5-letter symbol ending in W / U / R (era A v2: 182 / 247 / 39 of 12,532 symbols,
  counted 10-25; era B: 1,274 / 863 / 238 in the whole Polygon file, the 10-22 count; the 10-21 probe's top-60 small-cap
  run-ups held 12 warrants). The suffix rule also drops a real 5-letter common stock ending in W / U / R that has no type —
  rare, printed. P1 admits CS / ADRC / unknown as live's SQL does; **P2 requires CS or
  ADRC by the point-in-time type**, and its unknown-type names go to a counted beside row. The funnel prints `excluded: security
  type` and the type-source split (Polygon record / fallback table / unknown), per era.
- **One company under two symbols — the dedupe and the company key (round 3; the round-2 recheck's blocker 1).**
  - *The dedupe is already applied in the era-A file.* The build's alias map `cb702_pre_v2/dedupe_applied.tsv` (98 pairs,
    61,512 rows dropped; columns dropped_symbol, kept_symbol, first, last, kind, rows) removed one copy of each company carried
    twice: a strict twin (byte-identical bars) drops the retired / hinted symbol's rows on the matched span — 41
    `retired_symbol` (FB → META, 1,620 rows: Facebook's history now sits under META only), 25 `twin_to_window_end`, 3
    `partial_overlap`, 2 `diverged_after_run`; a scaled twin (same company, a later split applied to one copy only; raw closes
    equal) drops the member Alpaca no longer lists active — 26 `scaled_twin_full`, 1 `scaled_twin_partial`. 81 symbols left
    the file entirely. **15 dropped symbols (round 4; round 3 wrote "6 partial / diverged pairs") keep 2,927 rows OUTSIDE
    their dropped span**, across the `retired_symbol`, `scaled_twin_full`, `partial_overlap` and `diverged_after_run` kinds
    (listed under the owner rule above); a climax there is admitted under that symbol, typed by the date rule (never the later
    holder), flagged `alias_outside_span`, counted. Result on the file (G3): 0 strict pairs, 0 duplicate rows,
    0 scaled twins. The price lens's looser rule (≥ 10 identical days) still finds ONE pair, APTV = DLPH (11 identical days;
    29 pairs share any identical bar, 92 rows) — round 4: covered by the guard, NOT the night rule (11 shared days are neither
    byte-identical over 120 rows nor one company key): both symbols carry the `2017-12-05:jump` break at the Delphi → Aptiv /
    Delphi Technologies separation, and the pinned price flags list both as an `adj_event` on that date with a raw-step factor
    change (`fac=0.3333`, `audit_1023/price/A_flags.tsv`) — so the jump is APPLIED under the evidence rule (`fac_change`) and
    a window spanning it is `void_adjustment_event` as well; the 11 shared days (2017-11-17..12-04) all precede it. Era B: G3 found 0 pairs (planted controls
    3 of 3 found), so no alias map; its rename SPLITS (one company as two series at a ticker change: GPS → GAP, RXN → ZWS) are
    handled by the company key.
  - *The company key*, fixed now: the owning record's CIK (after the M1 re-resolution, so two share classes of one company —
    VIAC / VIACA if the pull resolves them — merge on the resolved CIK); else its composite FIGI; else its share-class FIGI;
    else the symbol after the alias map — **the alias map applies only to dates inside its [first, last] span (round 4)**: a
    dropped symbol's row inside the span maps to its kept one; an `alias_outside_span` row keys by its date-rule owner, so XL
    Group's 2016–18 rows never merge with SPRU's. STEP 0 prints the count of SYMBOL-keyed companies (no CIK, no FIGI) per
    population and era — each may be one company counted twice. It is a KEY, not a rebuild: the FIGI-keyed export is parked
    in the data standard's fix queue, and the refetch's own records lack a CIK on 145 of 3,767 and a composite FIGI on 1,928 of
    3,767. Uses: (1) **one open episode per COMPANY** (Substitution (c)) — a rename in era B cannot open a second episode, and
    two share classes of one company (same CIK) are one name; (2) the tail clause counts companies, not tickers; (3) the gone
    test (P2); (4) **one climax row per (company, D0)**: two admitted climax rows on one D0 under one key, or with
    byte-identical OHLCV over the 120-row window under any keys, keep ONE — the alias map's kept symbol, else the higher D0
    dollar volume, else the alphabetically first — and count the other `duplicate_company_night`, listed.

**Two populations — the complement, one rule for every date, no switch at 2026-05-01.**
- **P1 = the live price and dollar-volume floors:** raw close ≥ $5 AND dollar volume ≥ $10M on D0 (`db.get_parabolic_universe`'s
  SQL, db.py:7462-7464). **The $250M market-cap floor is NOT in the deciding P1** — there is no cap history (`mi_market_caps` is one
  overwritten row per name; `mi_parabolic_candidates.market_cap` is a 30-day cache, only since 05-01 and only for names that passed
  the $5 / $10M pre-filter), and the floor is his signed rule (ADR 0020 J4), so it is applied as a BESIDE row, below, never
  silently. Disclosed: the deciding P1 is "the live floors without the cap floor".
- **P2 = small caps = the complement band, GONE COMPANIES IN (round 2; round 3: on the rebuilt file):** (raw close < $5 OR
  dollar volume < $10M) AND raw close ≥ $1 AND dollar volume ≥ $2M, type CS / ADRC **by the owning Polygon record** — so a small
  cap that later collapsed and was delisted (the short's best cases) is in P2 on the nights it traded, typed and CIK-mapped by
  its own delisted record, with its bars from era B's Polygon file or era A's rebuilt file. The 10-22 rule required CS / ADRC
  from current-only tables, which kept mostly survivors; that rule is gone. The $1 / $2M floors are a tradable floor fixed now
  by me, not his; a different floor is his call. By construction **P1 ∩ P2 = ∅ on (ticker, D0)** and **P1 ∪ P2 ∪ P2's
  unknown-type row = every admitted name (symbol, test-symbol and W / U / R rules applied) with raw close ≥ $1 and dollar volume
  ≥ $2M** — both are runner assertions, not expectations. STEP 0 prints P2's point-in-time cap distribution where known (the
  share under $250M), so "P2 is small caps" is a printed number, not a label. The data standard's G6 untyped share (0.3% of
  admitted nights on v2) was measured on the $5 / $10M rule, i.e. P1's band; **P2's band was never measured**, so STEP 0 prints
  P2's untyped share per era.
- **The survivorship check — counts truly GONE companies, not renames (round 3; the round-2 recheck's blocker 2).** A climax
  company is **gone** when its owning record is delisted AND no active Polygon record shares its CIK, composite FIGI or
  share-class FIGI (a match is a RENAME — the company still trades under another symbol — and is not gone). STEP 0 prints, per
  population and per era: (i) the share of climax COMPANIES that are gone, and the subset gone inside the era's own window;
  (ii) for era A, the **refetch-sourced share** — climax companies whose symbol is one of the 2,669 the build added, defined as
  (the pinned `refetch_combined_records_1023.tsv` symbols) ∩ (v2's symbols) — round 4: equal to v2 minus `cb702_pre` (both 2,669,
  checked 10-25 on the guard tables' symbol lists), so the survivors-only file is never opened; a file-only test, no network.
  **An empty-key owner (no CIK, no FIGI) is gone = UNKNOWN, never gone** (round 4: with an empty key "no active record shares
  it" is vacuously true — VIAC, renamed PARA, would read gone); counted. The REFUSAL is structural, not a guessed number: era A refuses unless
  every v2 pin matches (the refetch, its raw companion, the dedupe and the guard are INSIDE those files now), and the run
  refuses when (i) is ZERO in either era or (ii) is ZERO in era A (the gone companies did not arrive). The expected shares
  (≥ 25% era A, ≥ 15% era B for (i)) are EXPECTATIONS below — printed, a miss reported first, never a stop on an unmeasured
  quantity. Why 25% for era A: in the overlap, the most volatile fifth of liquid names was 26.1% absent from the survivors-only
  file after renames were taken out (data standard C8) — a climax name sits in that fifth. A blocker closed on paper is not
  closed; this is the number that shows it took.
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
  not closed by that night's own bar (outcome date > D0, or still open / degraded) is rejected `episode_already_open`, counted.
  **"Name" = the company key (round 3)**, not the ticker — live keys by ticker, and on live's point-in-time symbols the two
  differ only at a rename or across share classes; the count of rejections the key adds beyond a ticker key is printed. A
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
  `degraded` (the walk met a hole), `void_distribution_suspect` (next bullet), `void_adjustment_event` (the bullet after),
  **`ended_mid_walk`** (round 3: the name's last bar in its era's file is dated before the era's last session and falls inside
  the walk, so `replay_episode` runs out of rows — a delisting, not the end of the file), open at the seal (era B, D0 after
  2024-12-19). Mean R, the interval and every read are over settled episodes. **`ended_mid_walk` gets its own beside row,
  because it is where a short's best cases go:** the open position (or the armed, untriggered one: no entry, no R) is booked at
  the last close, split by how the name ended (the data standard's C1 rule: *collapse* = last close < $1 or ≤ −50% over its
  last 60 sessions; *pinned* = its last 10 closes within 1% of each other, deal-like; *other*), n and mean R per group. For a
  short the last-close mark is a LOWER bound on a collapse (the price may have gone lower after the halt) and the pinned group
  is the takeover-premium loss. Era B settles inside the seal by construction and era A inside its file, so `ended_mid_walk`
  and open-at-the-seal are the only open states a correct run can print — a runner assertion. **Round 4 (the data standard's C1,
  the review's M6): a haircut variant, fixed now, ADVERSE to the short** — the collapse group, and any `other` ending whose last
  bar is a one-day fall of 20% or more (C1: SIVB, FRC, SBNY), is also booked covering at **1.25 × the last close** (a halted,
  hard-to-borrow name covered by a buy-in at a premium; the favourable direction — the price went lower — is not booked, because
  a gain on a name that cannot be covered is not realisable); pinned and the rest of `other` stay at the last close. The verdict
  is computed three ways: (a) settled only (the deciding verdict, as registered), (b) settled + `ended_mid_walk` at the last
  close, (c) settled + `ended_mid_walk` with the haircut. **If (b) or (c) gives a different verdict from (a), the result reads
  "<verdict (a)>, depends on N delisted episodes"**, with N and each variant's verdict beside. The data standard's G8
  (`trade_impact.py`) runs on the settled list AFTER the walk (it needs the trades): 0 entered after the cut-off, 0 holds past
  the last kept bar, else refused.
- **Distribution artifacts — a stated rule; a spin-off is never booked as a covered short (round 2).** #705 found 10-23 that the
  Alpaca export adjusts splits but NOT spin-offs or special distributions (OPLN = the KAR → IAA spin-off 2019-06-28 read as a −62%
  session; ZWS 2021-10-05; BEP 2020-07), that Alpaca's split-adjusted and all-adjusted bars are identical on those cases, and
  that its corporate-actions feed covers ~2020+ under the OLD symbol only — so no source can be relied on, and the Polygon file is
  treated the same. For a SHORT such a gap is a windfall, and a −30% open is also what this setup HUNTS — so the rule is stated
  honestly: **no bar-level test discriminates a spin-off from a real collapse** (#705 step 5's "new listing within [−2, +1]
  sessions" matched 1–32 listings on EVERY gap date in `05_local_checks.txt` — SPACs and IPOs list most weeks — so it is a HINT
  column, not the rule). **The rule:** a session in D0 + 1 .. D0 + 7 (the sessions an episode can occupy) whose open ÷ prior
  close − 1 ≤ −0.25 makes the climax a `distribution_suspect`, listed in `distribution_suspects.tsv` (ticker, D0, gap date, gap,
  prior close, the new listings in [−2, +1] as the hint, Alpaca's corporate-actions answer where it has one). **The class —
  a written EVIDENCE rule decided without looking at price (round 4; the review's M5).** The flag IS a ≤ −25% open inside the
  walk, i.e. the short's outcome, so a class written by a person reading the suspects would be made knowing the stock
  collapsed. Round 3's hand marking is gone. A suspect is `distribution` ONLY when one of these is on file: (i) Alpaca's
  corporate-actions feed lists a spin-off or a special cash distribution for the name with an ex-date within [−2, +1] sessions
  of the gap date; (ii) the owning CIK's EDGAR submissions (the pinned `edgar_submissions.jsonl.gz`) show an 8-K with item 2.01
  (completion of an acquisition or disposition) accepted within [gap date − 10, gap date + 4] sessions — the forward 4 because
  an item 2.01 is due within four business days AFTER completion, and the gap date is the completion date or the next session;
  this look past the gap identifies a corporate action that corrupts the bars, it is never a trading feature, so the reads-4/5
  and cap rule "filed < D0" does not apply to it. The STEP 0 EDGAR pull includes the owning CIKs of the two controls below
  whether or not they are climax companies (the check runs independent of the climax list). **No evidence =
  `real_move`, in n.** A Form 10 is filed by the spin-off's own CIK and cannot be tied to the parent without a hand link, so it
  is printed as a hint, not evidence. The runner writes `distribution_class.tsv` (suspect, class, the evidence row) at STEP 0,
  pinned with the STEP 0 files, before any walk. A `distribution` episode is `void_distribution_suspect`: counted, never in a
  number; the beside row prints n and mean R with every suspect in, and the n each class moves, so the size of the exclusion is
  on the record. Executable checks at STEP 0: the flagger run over the raw bars alone, independent of the climax list, must
  list OPLN 2019-06-28 and ZWS 2021-10-05 (on v2 the data standard's own spin-off lens FLAGGED both, and BEP 2020-07-30), AND
  the evidence rule must class both `distribution` — either miss refuses the run (a rule that cannot see the two known
  spin-offs would book them as short winners; a fix is a new registration). BEP 2020-07-30 is an `adj_event` and is voided by
  the next bullet whatever its class. ⚠ Era B has NO testable positive
  control at this cut: OPLN and BEP fall before era B's file, ZWS is a ticker seam there (RXN → ZWS), and the known era-B
  spin-offs (T 2022-04-11 −18.7%, K and DHR 2023-10-02 −11.8% / −13.9%) all sit above the −25% cut (data standard C5) — so the
  rule is applied in era B as registered, and its recall there is unproven, stated.
- **Vendor-booked adjustment breaks — excluded from windows and walks (round 3; the data standard's §4 step 4).** The
  standard's price lens lists the (ticker, date) events where the vendor booked a factor that BREAKS the adjusted series (e.g.
  BEP 2020-07-30 adjusted −81% against a raw −26%) — a fake collapse for a short, and a fake prior move for the detector. Era
  A: the 93 `adj_event` rows of `cb702_pre_v2/audit_1023/price/A_flags.tsv` (3 from the split table + 90 from the raw-close
  step test, 31 of the 90 liquid); era B: the 67 of `apollo_data/audit_runs_2026-10-23/B_flags.tsv` (3 liquid; dated
  ≤ 2024-12-31). A climax whose 120-row window or D0 + 1 .. D0 + 7 span contains one is `void_adjustment_event`: counted,
  listed, never in a number; a beside row prints n and mean R with them in. Fixed from the pinned lists before any walk.
- **ADR P&L for a short, fixed now:** per settled episode Σ over legs of weight × (entry − leg exit) ÷ entry ÷ ADR20%, the flush leg
  = 1/3 at `entry − 1R` when taken (else the exit leg carries all), **ADR20% = the mean of (high − low) / close over the 20 sessions
  ending at D0 − 1** — the session BEFORE the climax, so the climax bar does not set the unit. Size-free, like the CB registration's.
- **Costs beside every headline (round 3; the data standard's §4 step 8):** n, mean R, its interval, ADR P&L and the tail
  count are also printed with an exit slippage of 0.1% and 0.2% per covering leg (a short covers by buying: each leg's exit
  price × (1 + x)); the entry stays at the shadow's fill rule. The VERDICT is decided at zero cost as registered in round 1;
  a PASS whose interval's lower end falls to ≤ 0 at 0.1% is reported as "PASS at zero cost only". Borrow fees are not modelled
  (no history).
- **The tail clause for a 5-session short, fixed now:** PASS needs **at least 3 settled trades at ≥ 3R, from ≥ 3 companies (the
  company key; round 2 said tickers) and ≥ 3 distinct entry months**; fewer = the clause FAILS (never "vacuously true"). Why 3R and not the long book's 5R: the blend is
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
   (`scripts/probes/_314_xbrl_coverage_1021/probe.out`; its population was drawn from 2025–26 bars before the seal — a pre-seal
  touch, logged in the freeze record) mapped 40 of 60 names to a CIK by today's `company_tickers.json` (the
   point-in-time Polygon CIK can map MORE of the delisted ones, never fewer) and counted each tag at ANY filed date, one tag at a
   time: warrant count 12, exercise price 18, conversion price 7, shares outstanding 34; count + price + shares on one filing =
   10 of 60; conversion price + (shares or principal) + shares outstanding = 4 of 60. The tranche sum recovers some of the names
   the one-pair rule lost, by an amount not yet measured; coverage filed BEFORE each climax is lower still. **So with n ≥ 30 per
   bucket this read is still expected to come back CAN'T TELL**; it is registered so the coverage number (names mapped, tranches
   paired, unknown reasons by count) is on the record and the recording rule below can still apply. Each group's N is printed at
   STEP 0, before any walk.

**STEP 0 — derive and count the populations; walk nothing.** Before any outcome column exists the runner writes and prints, per
population AND per era: the funnel (ticker-nights → symbol / test symbol → owning record / security type → `raw_unknown` → raw
price band → dollar volume band → consecutive history → `identity_break` (guard, earlier-issuer rule, pre-break holder) →
`void_adjustment_event` → `duplicate_company_night` (round 4: plus `jump_unevidenced` kept, `pre_hole`, the
`alias_outside_span` rows with their owners) → each detector gate in order: dollar volume (patched in
P2), base anchor, prior move by tier, SMA extension, acceleration, burst score, gapped today, climax volume, days-up streak →
climax), the climax count per calendar year, the cap-tier and cap-source counts, the type-source and CIK-source counts (and
era A's type agreement with the v2 table), P2's untyped share, the gone share and era A's refetch-sourced share of climax
companies (the survivorship floor), `alias_outside_span` nights, the INBX / DOC earlier-issuer controls, the reachability
proxy, the break classes (applied jumps by evidence, `jump_unevidenced`, holes; symbols one-company / multi-company /
no-record) and the climax candidates each removes, the owner records re-resolved from the 2022-06-30 placeholder and those
left empty-keyed, the count of symbol-keyed companies, the tally of adjusted-pass / raw-fail nights, the overlap-disagreement share (the data standard's G10 on v2 already
reads: the same name on the same night in both files 95.8% of era B's members against a ≥ 98% target, closes differing by
more than 0.1% on 1.73% of shared ticker-days — the residue is symbol naming), and the distribution flagger's full list with
its OPLN / ZWS check. The one-open-episode rejection needs
the earlier episode's outcome date, which only the walk produces, so the climax → `episode_already_open` → armed tally is printed
by the WALK's own summary, not here; the pinned list is the pre-walk population through `climax`. It writes
`climax_list.tsv` (ticker, D0, era, the era's calendar file and its sha256 — one calendar per record —, population, company
key and its source, tier, cap, cap source, the owning Polygon record — type, cik, composite / share-class FIGI, `delisted_utc`
or active — type source, gone flag, refetch-sourced flag, earnings flag, reachable flag) and `features.tsv` (pause count, run length, anchor flag; per news pull:
group, item date, HTTP status, pages fetched, truncated flag; swing group, filed date; dilution bucket, ratio, tranche count,
filing accession, filed date, unknown reason; the M&A keyword flag and item date; the 8-K 2.02 flag and acceptance date),
`distribution_suspects.tsv`, `distribution_class.tsv` (the evidence rule's output), `breaks_applied.tsv`, **era B's calendar
file `calendar_B.txt`** (round 4; the review's L2: SPY's 821 sessions 2021-09-27..2024-12-31 written once, the runner asserting
it equals the NYSE calendar over the same span — verified 821 on 10-25 — so "one calendar per record" has a FILE to carry for
era B, whose first scorable D0 is 2022-03-17 and last 2024-12-19), and the saved pulls (`polygon_reference.jsonl.gz`, `xbrl_facts.jsonl.gz`, `xbrl_instances.jsonl.gz`,
`edgar_submissions.jsonl.gz`, `polygon_news.jsonl.gz`). **All of them are pinned (`--print-pins`) in a commit BEFORE the walk; the
walk refuses to start without those pins** — and without every era pin in the freeze record matching (era A: the v2 export,
its raw companion, `dedupe_applied.tsv`, the type table, `sessions.txt`, `symbol_guard.tsv`; era B: the export, the splits,
`symbol_guard_B.tsv`; both: the adjustment-event lists).

**Parity — checked against data that exists (a broken replay must be able to fail).**
- **Walk goldens (synthetic, the test module's own series, `tests/test_parabolic_short_shadow.py`):** `TRIGGER_THEN_TIME_STOP` →
  settled `time_stop` on D5, entry 140.0 `intraday`, flush taken at 116.93, realized R 1.200260078; the same series at
  `time_stop=3` → settled on D3, realized R 0.969079613 (both computed 10-22 from the pure function; matched to 1e-9 on the run
  machine — same platform, never cross-platform). The runner writes the fixture bars in the export's layout, reads them back through
  its own loader and must return a dict byte-equal to `replay_episode` on the fixture dicts, for every scenario the test module's
  `TestGeometry` / `TestFillConvention` / `TestArmWindowAndInvalidation` / `TestManagement` classes hold.
- **Detector goldens — the real-bar ones sit in the SEALED table (round 3).** Round 2 registered AGL 2026-05-07 (`days_up_streak`
  = 2, not climax; `docs/setups/parabolic_short.md`:284) and XMTR 2026-05-07 (`days_up_streak` = 3, `climax` with
  `is_earnings_today=False` and NOT with `True`; :284, :68) as REFUSING goldens at an explicit `market_cap=5_000_000_000`, and
  CAR 2026-04-07 / 2026-04-21 as PRINTED. All four dates are 2026 bars, so under the seal **they do not run in this read**
  (round 4: no bounded touch is asked — his ruling 2026-10-25, "1", `f4d6dfe8`, `operator_shared_notes.md`: the sealed 2025–26
  data stays unspent until an entry and an exit reproduce him, and "no single read spends it first"). They go, exactly as round
  2 registered them, to #710's one combined sealed run as its detector parity. **The synthetic golden below is this read's
  ONLY refusing detector check.** **The seal-safe REFUSING golden that replaces them:** a synthetic detector golden in the
  runner's own test, written and pinned before STEP 0 — one constructed 120-row series that reads `climax` under the pinned
  module at `market_cap=5_000_000_000`, `is_earnings_today=False`, and four one-gate-off copies that each read NOT climax with
  the named gate among its failing checks, not necessarily the only one (the streak is also a burst item,
  so the streak copy may fail the burst count too): `days_up_streak` = 2 (the AGL class), `is_earnings_today=True` (the XMTR
  class), the climax-day gap at 1.9% (under the 2% `gapped_today` cut), the climax-day volume one share under its 20-session
  high. Every expected stage and failing-gate set is written in the test before it is first run; a mismatch refuses the run. It tests the pinned module's gates, not the
  data — the data's checks are the data standard's gates and STEP 0. **PRINTED only, never refusing:** GME 2021-01 in era A (the
  05-01 evidence, "3 anticipations during squeeze", :298, predates the 05-08 gates; every session's stage and gate values printed
  from `cb702_pre_v2`, a miss listed); NVDA 2024-03 in era B (:298, "correctly rejected — not parabolic"; expected not climax on
  every session of 2024-03 — printed, because a detector that never fires would also pass it). **GME is expected INSIDE the
  population (round 4):** one company on the symbol, and no factor change on its two jump dates (its 4-for-1 split came
  2022-07, after era A's file ends, so the raw ÷ adjusted factor is constant through era A) — so its jumps are
  `jump_unevidenced`, its January 2021 nights are admitted and typed by its own record; if STEP 0 finds a second company record
  or a factor change, the print says which and GME is outside. The synthetic walk goldens are
  era-agnostic (both files share the layout) and run against each era's loader.
- **Live rows: none exist on this machine.** No export of `mi_parabolic_candidates` or `mi_parabolic_short_shadow` is stored
  locally (`find` / `grep` 10-22), and the shadow has armed 0 episodes since its first night 10-19 (the 10-25 read: 22 candidate
  rows since 10-17, all `unqualified`), so "parity with the shadow's rows since 10-17" is dropped — it could never fire. Round
  2's optional prod-extract check (`mi_parabolic_candidates` 2026-05-01..10-16) needs the detector run over 2026 bars, so it is
  sealed too (round 3) and goes with the real-bar goldens to #710's combined sealed run (round 4). Without them the goldens
  above ARE the parity, and the result says so.
- **Runner rules from past defects (round 3; each is a test in the runner's suite):** one calendar per record — every
  `climax_list.tsv` / `episodes.tsv` row carries its era and that era's calendar file, and a session count is never taken on
  the other era's calendar; no cache keyed by `id()` of an object the cache does not hold (a freed object's id is reused — key by
  (era, ticker, D0) or hold the object); never `float()` a numpy array — scalars leave numpy by indexing or `.item()`, and a
  length ≠ 1 is an error, not a silent first element.

**Independent re-derivation** from `episodes.tsv` alone (pandas, no runner code): per population n, mean R, the interval, ADR P&L,
the tail spread, and each read's difference (point and interval, same seed) — VERDICT MATCH before the result is written.

## Bars (per population; settled episodes; precedence: n first)

- **The base verdict (primary walk):** PASS = n ≥ 30 AND the month-block 95% interval of mean R (blocks = the ENTRY month, 2,000
  resamples, seed 702, `runner.block_bootstrap_ci`) has its lower end > 0 AND mean ADR P&L > 0 AND the tail clause (≥ 3 trades
  ≥ 3R from ≥ 3 companies and ≥ 3 months). FAIL = n ≥ 30 AND the upper end < 0. Else CAN'T TELL — n < 30 whatever the interval says;
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
  read 3 rises across 2016→2024 (round 3: the seal ends era B at 2024); the read-5 known buckets are under 30 each even with tranche sums (CAN'T TELL); the
  reachable-3R share is under 50% in P1. **Round 2 (round 3: "delisted" now reads "gone", renames out):** the gone share of P2
  climax companies is ≥ 25% in era A and ≥ 15% in era B (printed; the structural refusal is a zero share); the gone companies
  carry a HIGHER settled mean R than the survivors in P2
  (the sign the survivorship fix should show for a short; a miss says the collapse came after the window); era A's climax count
  per calendar year is within 2× of era B's per-year mean (a miss is a source / calendar difference to read, not a rule); of the
  `distribution_suspect` climaxes, under 10% are classed `distribution` by the evidence rule (a parabolic short produces real −25% opens; a miss is
  itself a finding about the window); truncated news pulls are under 1% of pulls; the overlap-disagreement share is under 1%.
  **Round 3:** `raw_unknown` = 0 in era A; **round 4 (the review's M3) — a SUBSET test replaces round 3's share inequality**
  (which rested on "almost always" and could exit a correct run): every gone era-A climax company that is NOT refetch-sourced
  must have the owner path `no active record -> latest delisted` or be an `alias_outside_span` date-rule owner, and is listed
  with its path — a runner ASSERTION that exits only on a gone, not-refetch-sourced company reached by any OTHER owner path
  (an original symbol that HAS an active record can only be gone through a bug in the owner rule); the expectation is the gone share's ≥ 25% above; era A's type agreement with
  the v2 table ≥ 99%; P2's untyped share is under 5% per era (round 4: 460 table-untyped v2 symbols reach $2M a day, so this
  rests on the Polygon record typing nearly all of them — a miss says the fallback carried more than expected); `ended_mid_walk` is under 5% of armed episodes and its collapse group outnumbers its pinned group in P2;
  `duplicate_company_night` and `alias_outside_span` are each under 1% of climax rows; `void_adjustment_event` is under 2% of
  climax rows.
- **WOULD-FAIL-IF (checks the runner PERFORMS; any one exits non-zero and writes no report):** `rows[-1].trade_date == D0` on every
  scored night and the 120 rows are consecutive SPY sessions; a feature dated after its cut-off (news after the window's close
  for read 3 / after D0 for row (a); any filing with `filed` ≥ D0 in reads 4–5 or the cap; an 8-K acceptance after the session it
  is charged to); an episode in two groups of one read, or in none; P1 ∩ P2 ≠ ∅, or P1 ∪ P2 ∪ P2's unknown-type row ≠ the $1 / $2M
  band; a name with two open episodes on one night; the patched constant ≠ 2,000,000 in the P2 process or ≠ 10,000,000 in P1; the
  walk goldens off by more than 1e-9, or the synthetic detector goldens (and the AGL / XMTR goldens, only if he rules the sealed
  touch) off on any gate; the walk's climax set ≠ the pinned
  `climax_list.tsv`; a settled episode whose
  entry ≤ D0 or whose exit > entry + 4 sessions (5-stop) / + 2 (3-stop); a read-1 pair whose two walks differ in entry; a realized
  R not equal to 1/3 + 2/3 × exit-leg R when the flush was taken; the export's sha256 ≠ the pin; any pinned module changed.
  **Round 2:** a 120-row window or a walk drawing a bar from the other era's file; an era-A night walked without the v2 pins
  (round 3: the refetch, its raw companion and the one guard table are inside them); a name placed in a population by an adjusted price; a CIK or a type
  taken from a symbol-keyed current table where an owning Polygon record exists, or any SEC call made by symbol; an owning record
  whose span does not contain D0; a cap or a dilution ratio computed across a split between the fact's `end` and `filed`, or
  with a count and a price on different bases; a dilution ratio on a name with an unpaired tranche; a truncated news pull
  counted as present or absent; a `distribution` -classed episode in n, a class not produced by the written evidence rule, or a class file dated after
  the walk started; the flagger not listing OPLN 2019-06-28 and ZWS 2021-10-05; a gone share (round 2: delisted) of P2 climax companies equal
  to zero in either era; read 5 or the cap reading a filing other than the latest periodic report before D0.
  **Round 3:** any bar dated after 2024-12-31 in a window, a walk or a feature (the seal), or any row read from
  `cb702_pre/daily_closes_all.csv.gz` (the survivors-only file); a v2 pin, `symbol_guard_B.tsv` or an adjustment-event list
  whose sha256 ≠ the freeze record; the raw file's (ticker, date) key set ≠ the export's in era A; a bar of a `dedupe_applied.tsv`
  dropped symbol dated inside its dropped span (the file is not the deduped one); two climax rows kept on one (company key, D0),
  or two open episodes on one company key; an era-A owning record chosen by the era-B date rule for an original symbol, or a
  night before the symbol's last APPLIED break typed by the later holder; an `alias_outside_span` row typed by its kept symbol's
  or a later holder's record, or merged with its kept symbol's company key; a gone era-A climax company that is not
  refetch-sourced and reached by an owner path other than `no active record -> latest delisted` or the `alias_outside_span`
  date rule (round 4: the subset test); an owning record still carrying the
  2022-06-30 placeholder date after the STEP 0 re-resolution (replaced by a real `delisted_utc` or by unknown — an unknown date
  never exits the run); an empty-key owner counted gone; the OPLN 2019-06-28 or ZWS
  2021-10-05 suspect not classed `distribution` by the evidence rule (8-K window [gap − 10, gap + 4] sessions); a `--breaks` set other than the pinned
  `breaks_applied.tsv` rows marked applied; an active-owned era-B window reaching a bar on or
  before an earlier issuer's `delisted_utc` — checked on the INBX 2024-05-31 and DOC 2024-03-04 controls, which must be
  excluded; a climax spanning a listed adjustment event in n; an `ended_mid_walk` or open-at-the-seal episode in n, or any other
  open state at the end of a run; a refetch-sourced share of zero in era A; a `climax_list.tsv` row with no calendar file, or a
  session count taken on another era's calendar.

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

**A PASS at zero cost only (round 4; the review's L4)** — a PASS whose interval's lower end falls to ≤ 0 at 0.1% exit
slippage — takes its PASS cell above, flagged "zero cost only" on every line that goes to him: a P2 PASS is still the lane
proposal (a shadow lane holds no money), and a P1 PASS is still the candidate for the next rung, with the flag; paper stays his
call either way. A verdict that "depends on N delisted episodes" (the `ended_mid_walk` rule) carries that label the same way.

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
  table where a point-in-time record exists; void a `distribution_suspect` without the written evidence rule's STEP 0 class, or class one by hand; move the era
  boundary, the −25% gap cut, the page cap K, the filing rule or the tranche rule after this registration.
- **Round 3:** read any bar dated after 2024-12-31 (the seal) — the real-bar goldens and the prod-extract check included;
  round 4: they belong to #710's combined sealed run, not this read; read the survivors-only `cb702_pre` export at all; re-run
  the dedupe, re-type or re-guard era A inside the runner (the v2 files ARE the data; a different build is a new registration —
  round 4: classifying the pinned guard's breaks by the written evidence rule into `breaks_applied.tsv` is not a re-guard: no
  break is added or re-derived); choose an era-A owner by the era-B date rule outside the `alias_outside_span` rows; move the
  company-key order, the gone test, the `ended_mid_walk` groups, the haircut, the break-evidence rule, the distribution
  evidence rule or the adjustment-event lists after this registration.

## What this does not answer

- Borrow availability and cost (the binding real-world limit on small-cap shorts; assumed easy at both checks); intraday entries
  (his top-day short on "losing momentum") — the replay is daily; his adds / pyramiding; the large-cap "obvious news-driven
  parabolic" judgement; the Perplexity exclusion's real effect (the keyword row is its $0 half); the earnings gate's effect on this
  population (unknown in the primary; the 8-K row is a substitute, not the live source); names live scores on 60–119 rows; XBRL
  coverage limits every read that needs a filing.
- **Survivorship AFTER the fix (round 3: measured, not complete; round 4: re-counted after the straggler pass):** the printed
  recall (98.1% of the known-gone list, 95.7% of the liquid 2022 names) predates the 31 stragglers and is a lower bound; counted
  against v2's symbols it is 263 of 264 and 715 of 723 (the Method bullet). The holes left: **absent, no bars** — ARIS, AXNX,
  INBX, MSPR, NXU (5 companies; MSPR and NXU are the two symbols with two records, one CIK per pair); **present but
  unidentified** — VIAC and VIACA (555 rows each, no Polygon record found by the fetch; type, CIK and gone flag unknown unless
  the STEP 0 pull resolves them); BOMN, PFHC, SI, FREY and SGMS are covered under today's symbols BOC, ACDC, SICP, TE and LNW;
  the list's other 3 are test symbols. And — unmeasured before 2021-09 — a
  dead company whose SYMBOL a current export name now holds (the refetch skipped every symbol already in the export; Physicians
  Realty under DOC is one; data standard C7): the old company is missing, and the guard is the only catch where a by-name fetch
  splices two issuers. The recall
  measurements are on the overlap and the known-gone list; 2016–20 recall is inferred from the flat ended-by-year count, not
  measured name by name. The gone share printed at STEP 0 bounds the fix; it does not prove completeness. Borrow is the harder
  limit for exactly these names: hard-to-borrow is the norm in a collapsing small cap, so P2's n overstates what could have
  been shorted even more than P1's (assumed easy at both checks, as before).
- **The company key is a key, not a FIGI rebuild (round 3):** the data standard's FIGI-keyed export is parked; the key falls back
  to FIGI and then to the symbol where a record has no CIK (145 of the 3,767 refetch records), so a rename with neither CIK nor
  FIGI on its old record can still count as two companies. G4 on v2 records 51 symbols (26 liquid, 0.84% of shared dollar volume)
  where era A and era B carry a different series under one symbol in the overlap — a recorded floor, mostly A's today's-symbol
  keying; climaxes on them are flagged, not excluded.
- **Vendor differences between the eras:** era A's volume runs about 3% above Polygon's (median ratio 1.031 in the overlap), so
  the $10M / $2M dollar-volume bands admit slightly more in era A; the two vendors book corporate actions differently (era A's
  adjustment-event list is 93 rows, era B's 67). Per-era rows are printed beside the pooled verdict for this reason.
- **The sealed 2025–26 table:** about 1.8 years of era B (2025-01-02..2026-10-16) are not read. They are the named holdout for one
  later registered read, not part of this one.
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

## Revisions 2026-10-25 (round 3 — era A on the rebuilt file, era B at the seal; each fixed in the body; nothing run)

Facts used, all from files on this machine 10-25 (no network, no bar after 2024-12-31 opened, no outcome computed): the v2
build's `export_stats.tsv`, `dedupe_applied.tsv`, `sessions.txt`, `symbol_guard.tsv`, `small_pulls.psv` and
`audit_1023/{verdict.txt, price.console.txt, universe.console.txt, sectype.console.txt}`; the refetch's logs, records and recall
printouts in `cb702_pre/survivorship_1023/`; the data standard; sha256 of every pinned file; the NYSE calendar for era B's
sessions to 2024-12-31 (821, equal to the standard's printed count). Still REGISTERED, NOT FROZEN.

| # | what changed | was (round 2) | now (round 3) | why |
|---|---|---|---|---|
| 1 | era A's bar file | `cb702_pre` (survivors-only, 10,320,661 rows, 9,944 symbols) + a refetch "running, pasted when it lands" + a RAW companion that "does not exist yet" + two guard tables | `cb702_pre_v2` only: 12,005,007 rows, 12,532 symbols (9,944 − 81 deduped away + 2,669 added), raw companion and one guard table built in; old file not read | the two round-2 data blockers have their fix in this file; it passes every file-only gate (S0, G1–G7, G9) |
| 2 | era B's end | D0 ≤ 2026-10-07, calendar = 1,270 SPY sessions to 2026-10-16 | D0 ≤ 2024-12-19, calendar = 821 sessions to 2024-12-31; 695 scorable D0 sessions; 7 later D0s open at the seal; a runner assertion that no later bar is read | the data standard's sealed-table rule (§4 step 7); round 2 would have spent the holdout |
| 3 | era A's scorable D0s | 2016-06-23..2022-03-16, "D0 + 7 ≤ 2022-03-28" | same dates (sessions file byte-identical), 1,443 D0 sessions, D0 + 7 = 2022-03-25 | a counting slip corrected |
| 4 | the owning record in era A | one point-in-time (symbol, date) rule for both eras | era B keeps it; era A uses the SERIES owner (original symbol = its active record; refetched = its fetch record) and types nights before a symbol's last `jump` break as unknown (row 18) | Alpaca keys history by today's symbol: the date rule would give Facebook's 2016–22 bars (now under META) to a different, earlier META instrument |
| 5 | one company under two symbols | a blocker: no company key, no dedupe | the v2 alias map is applied (98 pairs, 61,512 rows; FB → META); a company key (CIK, else composite FIGI, else share-class FIGI, else the aliased symbol) drives one open episode per company, the tail spread, the gone test and one climax row per (company, D0) — `duplicate_company_night` counted (APTV = DLPH, 11 identical days, is the one residual pair the looser lens finds — round 4: covered by the guard, row 29) | the recheck's blocker 1 |
| 6 | the survivorship check | the share of P2 climax names whose record is DELISTED (renames counted as gone) | the share of climax COMPANIES truly gone (delisted, and no active record shares the CIK or a FIGI), plus era A's refetch-sourced share (2,669 added symbols); zero in either refuses | the recheck's blocker 2; recall per company on file: 98.1% (259 of 264) and 95.7% (692 of 723) — round 4: a lower bound printed before the straggler pass; 263 of 264 and 715 of 723 on v2 (row 22) |
| 7 | the raw close in era A | a refetched name could have no raw close (`raw_unknown`) | every v2 bar carries one (keys both feeds carry); `raw_unknown` expected 0, the key-set equality asserted | the raw pull landed and was joined by the build |
| 8 | identity in era B | no era-B guard; "the guard is the only lower bound" for an active-owned night | `symbol_guard_B.tsv` (1,292 symbols) passed as `--breaks`; a window may not reach an earlier issuer's `delisted_utc`; INBX 2024-05-31 and DOC 2024-03-04 are executable controls | the data standard's G4 and its C6 misses |
| 9 | delistings inside a walk | silent: "every era-A episode settles inside the file" | `ended_mid_walk`, never in n, its own beside row booked at the last close and split collapse / pinned / other; 3,478 of 12,532 era-A symbols end before 2022-06-30 | with the gone companies in, a short's best cases can run out of bars mid-walk (data standard C1) |
| 10 | vendor-booked adjustment breaks | not handled (only the −25% distribution rule) | `void_adjustment_event` from the pinned lists: era A 93 events, era B 67 | the data standard's §4 step 4; a broken factor reads as a fake collapse for a short |
| 11 | detector goldens | AGL / XMTR 2026-05-07 refusing, CAR 2026-04 printed, an optional 2026 prod extract | those are sealed — run only on his ruling of a bounded touch; a synthetic detector golden (one climax series, four one-gate-off copies) refuses instead; GME 2021-01 and NVDA 2024-03 printed | the seal; the detector must still be able to fail the run |
| 12 | type sources and counts | `small_pulls.psv` "14,101 names" for both eras | era A: v2 table, 17,028 typed symbols (14,102 + 2,667 refetched + 403 as-of), 18 unknown in P1's band (round 4: 1,885 symbols have no row — row 27); era B: 14,102; era-A agreement printed; P2's untyped share printed (G6's 0.3% is P1's band only) | re-derived from the files |
| 13 | symbol-rule counts | 675 other-character and 1,274 / 863 / 238 W / U / R symbols (the Polygon file's) | era A v2: 176 and 182 / 247 / 39 of 12,532; era B's whole-file counts kept and labelled, not re-derived (it would open sealed rows) | re-derived where the seal allows |
| 14 | tail clause | ≥ 3 tickers | ≥ 3 companies | a renamed or dual-class company is one company |
| 15 | runner rules | — | one calendar per record; no `id()`-keyed cache without the held object; never `float()` a numpy array — each a test | past defects in this workstream |
| 16 | the 2016→2026 expectation and new ones | "present" share rises 2016→2026 | 2016→2024; new expectations for `raw_unknown`, the refetch-sourced share, type agreement, P2 untyped, `ended_mid_walk`, duplicate nights, adjustment voids | follows rows 1–10 |
| 17 | costs | none | every headline also at 0.1% / 0.2% exit slippage per leg; the verdict stays at zero cost, a cost-fragile PASS is labelled | the data standard's §4 step 8: no edge claim without the slippage line |
| 18 | the pre-break type rule (era A) | — | nights before a `jump` break are an unknown holder; before a `hole`-only break they keep the owner's type, flagged (209 jump-only / 357 hole-only / 101 both of 667) | a hole is a halt, not a new company — round 4: on ONE-company symbols only, and a jump counts only with evidence (rows 19–20) |

## Revisions 2026-10-25 (round 4 — the 10-25 review of round 3; each finding checked against the files, fixed in the body; nothing run)

Facts used, all from files on this machine 10-25 (no network, nothing after 2024-12-31 opened, no outcome computed): the v2
guard table, `dedupe_applied.tsv`, `small_pulls.psv`, `audit_1023/price/A_flags.tsv` and `dup/A_pairs.tsv`; the refetch's
`stragglers_records.tsv`, `refetch_combined_records_1023.tsv` and `recall_by_company.txt` with their file times;
`ext_bars.py`'s docstring; `git log` of the two modules; `probe.out`; commit `f4d6dfe8`. Every finding was reproduced (the
counts below are the re-derived ones); one premise and one clause were corrected, not taken as written. Still REGISTERED,
NOT FROZEN.

| # | finding | was (round 3) | now (round 4) | evidence |
|---|---|---|---|---|
| 19 | H1 — the jump rule removed real squeezes | every guard `jump` excluded its windows and typed earlier nights unknown | a jump is APPLIED only with a factor change or a multi-company symbol (≥ 2 Polygon records, different company keys); else `jump_unevidenced`, admitted, flagged, a beside row without them; no-record symbols keep the guard; `breaks_applied.tsv` pinned; STEP 0 prints removals by jump vs hole; GME stated INSIDE | GME `2021-01-27:jump;2021-02-24:jump`; 194 of 310 jump symbols reach $2M a day; the docstring's "GME Jan-2021 trips the refined test" |
| 20 | H2 — the hole rule and the dedupe leftovers | a hole = a halt, same company; "6 partial / diverged pairs" keep rows outside the span; the alias map over the whole symbol | a hole on a multi-company symbol counts as a splice; `alias_outside_span` derived = 15 symbols / 2,927 rows, typed by the date rule, never the later holder; the alias map only inside [first, last] | `ext_bars.py:10`; 15 dropped symbols present in v2, 0 rows inside their spans, 13 of 15 with no break (only RSLS, KOOL) |
| 20a | H2's wider clause — "every multi-record symbol takes the date rule" | — | NOT adopted outside the 15 leftover symbols | META: Facebook in Alpaca throughout, a ~$10 ETF on the Polygon side until 2022-06 — the date rule would type Facebook's 2016–22 nights as the ETF |
| 21 | M1 — placeholder owner records | refetched symbol = its fetch record, taken as is | records dated 2022-06-30 or empty-keyed are re-resolved at STEP 0 from the pinned reference pull (asserted no placeholder date remains); empty key = gone UNKNOWN; share classes merge on the resolved CIK; symbol-keyed companies counted | all 31 straggler records dated 2022-06-30, 18 own v2 series; VIAC / VIACA blank (555 rows each); 46 refetched v2 symbols with no CIK or FIGI, 19 reaching $2M |
| 22 | M2 — recall and holes out of date | 98.1% / 95.7% as current; VIAC / VIACA "missing"; two-record symbols "may splice two issuers" | figures labelled a lower bound before the straggler pass; re-counted 263 of 264 and 715 of 723 from v2's symbol list; holes = ARIS, AXNX, INBX, MSPR, NXU absent; VIAC / VIACA present, unidentified; the two-record sentences deleted | file times 10:57:33 (recall) < 10:58:00 (straggler bars) < 10:58:18 (combined); MSPR, NXU absent from v2, one CIK per pair |
| 23 | M3 — the refetch-share assertion could exit a correct run | refetch-sourced share ≥ gone share, asserted | a subset test: every gone, not-refetch-sourced era-A company must come by `no active record -> latest delisted` or the leftover date rule; the refetch set = records ∩ v2 symbols | the set equals the 2,669 added (checked); 1,885 original symbols have no type-table row |
| 24 | M4 — re-asking a ruled question; an undisclosed touch | open question 1: a bounded 2026 touch for AGL / XMTR / CAR | not asked; real-bar goldens and the prod-extract check go to #710's combined sealed run; the synthetic golden is the only refusing detector check; the 10-21 probe's 2025–26 population logged as a pre-seal touch | his ruling `f4d6dfe8` ("1": "no single read spends it first"); `probe.out` population line |
| 25 | M5 — the distribution class was written seeing the outcome | a person marks each suspect from bar facts; unclassed = void | a written evidence rule decided without price (an Alpaca corporate action, or an 8-K item 2.01 by the owning CIK within [gap − 10, gap + 4] sessions — 2.01 is filed up to four business days after completion); no evidence = `real_move`, in n; OPLN / ZWS must class `distribution` or the run refuses | the flag is a ≤ −25% open inside the walk (the outcome); OPLN, ZWS are spin-off candidates, not `adj_event` rows, in `A_flags.tsv` |
| 26 | M6 — delisted walks without a haircut | `ended_mid_walk` at the last close only | plus a haircut variant adverse to the short (cover at 1.25 × the last close for collapse ends and ≥ 20% last-day falls); the verdict reads "depends on N delisted episodes" if either variant changes it | the data standard's C1 |
| 27 | L1 — type-table counts | "17,028 typed, 18 left unknown" | the 18 are P1's band; 1,885 v2 symbols have no table row (460 reaching $2M); the 17,172 are rows, not symbols | re-counted from `small_pulls.psv` and the guard table |
| 28 | L2 — pins and era B's calendar | CB and test modules "(pasted before the run)"; no era-B calendar file | both pinned now; `calendar_B.txt` written and pinned at STEP 0, asserted equal to the NYSE calendar | the review's "CB changed 10-24 in `9a8d869e`" is wrong: last change `bf399605` 10-18 — pinned anyway |
| 29 | L3 — G8 timing; APTV = DLPH | G8 "at STEP 0"; the pair "covered by the night rule" | G8 runs after the walk; the pair is covered by the applied 2017-12-05 jump (a factor change) and the adjustment-event void | `A_flags.tsv`: both `adj_event` on 2017-12-05, `fac=0.3333`; 11 shared days, all before it |
| 30 | L4 — a cost-fragile PASS had no cell | — | it takes its PASS cell, flagged "zero cost only" (still a proposal / candidate) | decided now; a shadow lane holds no money |
| 31 | L5 — no earlier reading | unstated | stated in Why: no #314 outcome exists on either file | no climax list or episode file anywhere (checked 10-25) |

<!-- FREEZE -->
## Freeze record

The doc body pin covers every byte above the `<!-- FREEZE -->` marker. The run verifies every pin before it opens the export and
refuses on any mismatch (the `freeze_check` pattern of `scripts/probes/_cb_backtest/runner.py`); STEP 0 runs first and its outputs
are pinned in a second commit before the walk; the RESULT is appended below this record. Pins computed 2026-10-22, 2026-10-23
and 2026-10-25 (`shasum -a 256`) for the data and the two frozen modules; the runner, the CB module (`raw_factor_for` /
`contiguous_window_mask` / `is_test_symbol`), the test module (the goldens), the STEP 0 files and the doc body are printed by
`--print-pins` and pasted here in the commits that precede the run (round 4: the CB and test modules are pinned now, below).
- Era B (read through 2024-12-31 only):
  - cb702/daily_closes_all.csv.gz sha256: `ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba`
  - cb702/cb702_splits.psv sha256: `3199d06d5fb7dcd52ebd34e8c71e148b45ec0ca4a15f7f03ea1b715718882b0b`
  - cb702/small_pulls.psv sha256: `b8d37aae5ef85c25bc52479eef7f6b04a8a4e67557caaef7a426d8ae20194643` (fallback type source only)
  - cb702/cb702_sic.psv sha256: `0e476c4422d56648d615c48d941edb971a348dfb99821023116d0fd98e617346` (fallback type source only;
    byte-identical to the era-A copy)
  - scripts/backtest_data_audit/runs_2026-10-23/universe/symbol_guard_B.tsv sha256:
    `b6cb81b6c4a1f415defc5adcf236402d93cd654c33736aa0b120b78c357b5650` (round 3; 1,292 symbols)
  - apollo_data/audit_runs_2026-10-23/B_flags.tsv sha256: `8bf843859afb70ea59edf6f11cda12160020936c8df3e978b6a819590ea5c3d5`
    (round 3; the 67 adjustment events)
- Era A (`apollo_data/cb702_pre_v2/`, round 3, 10-25):
  - daily_closes_all.csv.gz sha256: `0d5d2d0eb027abc06e4186ddec7d1e8b1234fd86f92c26798a8e15f113db668d` (12,005,007 rows)
  - daily_raw_close.csv.gz sha256: `f978db45074e9109178a1755c232fa1e684a6f83dab96ab007a26b12008f1444`
  - dedupe_applied.tsv sha256: `223d3f360369cc009919c6fae83b3ba0bb37aa437706b45fcbbb70560477cf64` (98 pairs)
  - small_pulls.psv (the type table) sha256: `d18e925b82ede2f5d4ca9ec8993d3d81f34ff10ebebec91b16f8b20e1aab0ff8`
  - cb702_sic.psv sha256: `0e476c4422d56648d615c48d941edb971a348dfb99821023116d0fd98e617346`
  - sessions.txt sha256: `098a9b50c92a1045043bc089a4d4d600a9631bdb45a8e22969d872440672f2f0` (1,635 sessions; = cb702_pre's)
  - symbol_guard.tsv sha256: `876a75ec6d51744579c1ea2744c1b529cbd941355ef12eb8f0451bbe7ba1af08` (667 of 12,532 with a break)
  - export_stats.tsv sha256: `040b50dabb0de4aacd7009e1e4cbb22b8214dab2f0579dc90169777e475ca622`
  - audit_1023/verdict.txt sha256: `02cbb1c0106101cb12e8d5deb9448051ae3ced67966ac11d2475d06f26538de3`
  - audit_1023/price/A_flags.tsv sha256: `5358e31dc1b27d25c5143bdfca7a98b91a6c7a2d5b1da6c9c9d9ed9c55474c1d` (the 93 adjustment
    events)
  - scripts/probes/_705_survivorship_1023/08_build_v2.py sha256:
    `16f861798a1ea9debfe4d633c650d2d0662484b008ce8f3b3f612ab097546a0b` (build provenance)
  - refetch_combined_records_1023.tsv (`cb702_pre/survivorship_1023/`, the era-A series owners of refetched symbols; 3,767 records, 3,765 symbols):
    sha256 `a8c563fffeffee55eef162b6724a490b8db9e43d8b2a9c6c656ece2a1963f9b6`
- History (round 2's era-A pins, the survivors-only file — kept as the record; NOT read by this replay; the export's sha256 still
  equals its pin 10-25): cb702_pre/daily_closes_all.csv.gz `b10eea41775e657939c64e314068cb3c606d23d44de8488649fb67a4ac5ed773`;
  cb702_pre/daily_raw_close.csv.gz `2cd4242e7b4b3f5b3a01e65e055e7e165f3fa5ccf71dda8871be0cc7a31fccde`; cb702_pre/sessions.txt
  `098a9b50c92a1045043bc089a4d4d600a9631bdb45a8e22969d872440672f2f0`; cb702_pre/symbol_guard.tsv
  `6665c69f41bff3bd6ea913c66ccb9d0eab8bed0a9f020c32fa50c85d6cb6e6fc`. The round-2 placeholder for "the delisted refetch, its RAW
  companion, and the refetch's symbol_guard" is closed: all three are inside the v2 files above.
- polygon_reference.jsonl.gz / xbrl_instances.jsonl.gz / distribution_suspects.tsv / distribution_class.tsv /
  breaks_applied.tsv / calendar_B.txt sha256: (pasted after STEP 0, before the walk)
- agents/market_intelligence/parabolic_detector.py sha256: `7530113b4defbdd10b7b02ba32c49b57261fdd32f609f65a28779e419e69cb0b`
- agents/market_intelligence/parabolic_short_shadow.py sha256: `3059e90e07e792e48c8fcf7e2c591786fb1d5da7496396cf3afc5e3e8abebb6b`
- agents/market_intelligence/consolidation_breakout.py sha256: `e14027be38b24352dd3c19fd5a1dcd54bae2e1cf80fc58a064d1ea65c821861b`
  (round 4, 10-25; last changed `bf399605` 2026-10-18 — the review's "changed 10-24 in `9a8d869e`" is not so: that commit
  touched `consolidation_breakout_pp.py` / `_shadow.py`, not this module)
- tests/test_parabolic_short_shadow.py sha256: `f697376ef050aff431d4828e6391cf04196e908f2eb3169004c33b584d4c6d56` (round 4,
  10-25; last changed `1129d042` 2026-10-18; the walk goldens' expected numbers come from it)
- **Pre-seal touch, logged (round 4; the review's M4):** the 10-21 XBRL coverage probe
  (`scripts/probes/_314_xbrl_coverage_1021/probe.py` / `probe.out`) drew its population from 2025–26 bars — "top 60 run-up small
  caps 2025-26 (peak close < $10, >= 3x the 60-session low)" — before the seal was set; it read only the population and its
  XBRL tag coverage (the coverage and warrant counts read 5 cites), no short outcome. No other sealed row is opened by this
  read.
- runner sha256: (pasted before the run)
- climax_list.tsv / features.tsv / xbrl_facts.jsonl.gz / edgar_submissions.jsonl.gz / polygon_news.jsonl.gz sha256: (pasted after
  STEP 0, before the walk)
- doc body sha256: (pasted in the freeze commit)
- freeze commit: the commit that adds this revision on `main`; STEP 0 runs only after it is on `main`, the walk only after the
  STEP 0 pins are.
