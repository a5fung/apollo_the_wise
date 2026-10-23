# Backtest data standard — what can be wrong with the data, how we check it, and how a backtest is run here

**Status:** standing standard from 2026-10-23 (operator: *"we're still finding issues, let's take a moment to categorize
problems we know or potential ones we don't know and verify the data, and do so for future runs as well. Let's document this,
and this should be in our trading brain/doc once we have it, how to best run backtests."*). First page to move into the
trading knowledge vault (#707) when it exists. The checks live in `scripts/backtest_data_audit/` (README there; `run_all.sh`
runs every lens in order). Numbers below are the 2026-10-23 audit of the two daily-bar exports; every count carries its n and
is named the way the script computed it (five auditors measured some families with different rules — where their numbers
differ, both are given with their rule, never averaged).

**The one-line verdict today:** **era A (2016-01..2022-06, Alpaca) FAILS the STEP 0 gate on three counts** — about 14% of
liquid names and 26% of liquid +100%-in-60-session runners are absent (survivorship), 71 companies are carried under two
symbols, and 8.35% of admitted universe nights have no security type. **Era B (2021-09..2024-12, Polygon) passes the data
gate** but 57 of its 8,984 published trades depend on sealed 2025 bars and it had no identity guard until today. Every
2017-21 number is labelled *survivors only* until the delisted refetch and the dedupe land.

**2026-10-23 update — a rebuilt era A clears every check that runs on the file alone.** `apollo_data/cb702_pre_v2/` (the delisted refetch + the dedupe + the
type join, `scripts/probes/_705_survivorship_1023/08_build_v2.py`) passes S0, G1–G7 and G9 (`cb702_pre_v2/audit_1023/verdict.txt`);
the verdict still reads REFUSED on G8, which needs a trade list and runs with each read. G10 (overlap parity, a REPORT) stays at
95.8% against its ≥ 98% target: the residue is symbol naming (110 B tickers that A carries under today's symbol, e.g. ABC = COR, and 85
the other way) plus 439 tickers on the universe's edge where Alpaca's volume runs ~3% above Polygon's — a company-keyed parity needs
the FIGI key and is parked with that rebuild. `cb702_pre` itself is unchanged (its files are hash-pinned by two freezes). **No read has been re-run on
v2 yet**, so every published 2017-21 number still carries the *survivors only* label.

**The two exports** (read-only; format `ticker,date,open,high,low,close,volume`, no header):

| | era A | era B |
|---|---|---|
| file | `~/apollo_data/cb702_pre/daily_closes_all.csv.gz` | `~/apollo_data/cb702/daily_closes_all.csv.gz` |
| vendor / build | Alpaca daily bars, split-adjusted, fetched by TODAY's Alpaca asset list | Polygon-based, point-in-time symbols, includes delisted names |
| span used | 2016-01-04..2022-06-30: 10,320,661 bars, 9,944 symbols, 1,635 sessions | 2021-09-27..2024-12-31: 8,619,626 bars, 15,702 symbols, 821 sessions (5,210,943 later bars dropped unread — **the 2025-26 table is sealed**) |
| sidecars | `daily_raw_close.csv.gz` (measured raw close), `symbol_guard.tsv` (identity breaks) | `cb702_splits.psv`, `cb702_sic.psv`, `small_pulls.psv` (security types as of 2026-10-16); `symbol_guard_B.tsv` written by `universe_check.py` on 2026-10-23 |

Three "liquid" rules appear below; the family tables say which one each number uses:
- **L2** (`universe_check.py`): ≥ 60 bars in 2021-09-27..2022-06-30, median close×volume ≥ $2M, median close ≥ $2 (per-session variant: that day's close×volume ≥ $2M and close ≥ $2).
- **L10** (`price_integrity_check.py`): prior-20-session median close×volume ≥ $10M, ticker `^[A-Z]{1,5}$`, type CS/ADRC/unknown.
- **U** (`security_type_check.py`, `pit_lint.py`): the setup's own universe rule — raw close ≥ $5, 20-session median close×volume ≥ $10M, 130 consecutive sessions, regex, not a test symbol ("member-nights").

---

## 1. Taxonomy — every problem family, KNOWN (confirmed, counted) and POTENTIAL (suspected or not yet measured)

Status words: **confirmed** = measured and real; **suspected** = measured but the signature is not discriminating, or the cause is unverified; **ruled out** = measured, immaterial on the liquid universe; **unmeasured** = no auditor touched it.

### F1 — Survivorship: the universe is missing the names that later died

| | era A | era B |
|---|---|---|
| status | **confirmed** | n/a (B carries delisted names by construction) |
| size, per session (L2) | liquid names per session, monthly medians Oct 2021–Jun 2022: A 3,883–4,116 vs B 4,477–4,819; **A/B = 0.852–0.867 in all 10 months** → ~14% of the liquid universe absent | — |
| size, by name (L2) | known-gone group (B names whose last bar < 2024-12-24, liquid, not warrant/unit/pfd/test; n=529): **335 missing or partial in A = 63.3%** (the `run_all.sh` rerun reads 323 of 514 = 62.8%: it also passes `--sic`, whose types exclude 15 more names from the gone group — verified by rerunning without `--sic`, which gives 529/335 again with the same `small_pulls.psv`); excluding 118 probable renames: 282 of 411 = 68.6%. Control (liquid, alive at 2024-12-31, n=2,732): 247 missing = 9.0% — those are 2025-26 exits (X, EA, WBA, HES, DFS…), so the loss continues into the sealed period | — |
| size, universe rule (U, overlap 2022-03-28..06-30) | members per night median A 1,873 vs B 2,072; **335 per night absent from A**, from 420 tickers: ~86 renames A carries under today's symbol, ~334 genuinely gone (TWTR, WBA, X, VMW, ZEN, ZI…) | — |
| worse further back | liquid non-derivative symbols whose LAST bar falls in each year of A: 2016: 12, 2017: 15, 2018: 53, 2019: 122, 2020: 112, 2021: 156, 2022 H1: 80 — against 130–200 a year in B. **Suspected:** A keeps ~8–10% of dying liquid names in 2016-17 (modelled on a constant death rate; not measured) | B: 96 (Sep–Dec 2021), 201 (2022), 144 (2023), 132 (2024) |
| impact | **Population and tail.** Of 552 liquid runners in the overlap (close ≥ 2× a liquid start-day close within 60 sessions), **146 absent from A = 26.4%**; ≥3×: 30 of 98; ≥4×: 11 of 43. Names NOT covered by A (snapshot 2021-12-31, n=547): median total return to last bar −29.1%, 24.3% lost ≥ 80%; covered (n=2,605): −10.9%, 8.9%. So A lacks about a quarter of the big runners (recall ceiling, P1) AND under-represents blow-ups — every per-trade R, drawdown and stop-out on A is flattered in an unknown direction. RS percentiles: 122 of B's 8,763 overlap watch nights change side of the 98 line under A's denominator (net +106 = +7.0%) | — |
| check | `universe_check.py` KNOWN-GONE + IMPACT (`gone_list.tsv`, `liquid_per_session_by_month.tsv`, `ended_by_year_{A,B}.tsv`); `pit_lint.py overlap` | |
| fix | the delisted refetch (`scripts/probes/_705_survivorship_1023/01_fetch_delisted.py`, FIGI/CIK sidecar) → rebuild A → rerun; **acceptance = the known-gone missing rate falls to the 9% control level and `ended_by_year_A` reads roughly flat 130–200/yr back to 2016** | |
| result (10-23) | **met on `cb702_pre_v2`:** known-gone missing 29 of 513 = 5.7%; liquid names per session v2/B 0.979–0.995; liquid names ending by year 2016–22H1: 90 / 129 / 141 / 122 / 109 / 174 / 94 (was 4 / 6 / 46 / 117 / 105 / …). Recall per COMPANY (a rename covered under today's symbol counts): 98% of the known-gone list, 96% of the 808 liquid 2022 names absent by symbol; 5 names Alpaca has no bars for (ARIS AXNX INBX MSPR NXU). Identity on the 2022 overlap: 585 of 590 refetched names within 1% of Polygon's close; outside: SUM, TEF, BBBY (×1.10 — the symbol was reused in 2025), ELP, TGI | `refetch: 03_recall_check.py`, `05_recall_by_company.py` |

### F2 — Duplicate companies: one company under two symbols

| | era A | era B |
|---|---|---|
| status | **confirmed** | **ruled out** (0 confirmed pairs; positive controls planted in B's own file were all found) |
| strict twins (byte-identical OHLCV) | three rules, three counts — **158 pairs** with any shared day / 40,822 second-copy ticker-days = 0.40% of bars (`universe_check`); **71 confirmed pairs** (≥5 matched days, not coincidence) / 40,722 duplicate rows / 141 symbols (`duplicate_series_check`); **72 pairs ≥10 identical days** / 75,640 rows counted as the union of both symbols (`price_integrity_check`). 25 pairs identical to the end of A (EYES=VANI, INT=WKC, IAC=PPLI, FB=META, FACT=SPWR), 41 renames where the old symbol stops | 2,626 second copies in 2,460 pairs, none ≥ 20 days, 0 liquid: SPAC-unit prints near $10, not twins |
| scaled twins (same company, different price scale; dollar volume equal) | **27 pairs, 54 symbols, 19,976 rows**; 12 factors equal a later split applied to one symbol only (ONTX/TRAW ×25, RCD/RSPD ×3); MGNI/RUBI factor 58,500 = RUBI's four later splits applied to Rubicon's 2016 bars (RUBI 2016 close $937,170 vs raw $16.02) | 0 of 1,207,695 scanned rows |
| impact | n and the tail inflated, mean R almost unmoved: breakout-scale rows (gap ≥10%, close×volume ≥$1M) double-counted 266 of 18,106 = 1.47%, and the share drifts by year (4.2% in 2017, 0.35% in 2022); return ≥50% rows 56 of 2,325 = 2.4%. On trades: 29 phantom copies of 60,202 `trades_pre_exitpb` fills (−13.35R of −787.8R; none ≥4R) by one join; 10 of 13,363 published C0 trades the same trade twice by another. META, WKC-class winners count twice in any tail list | 0 |
| check | `duplicate_series_check.py` TEST 1/2 (gate: confirmed pairs 0, duplicate rows 0, scaled twins 0); `universe_check.py` DUPLICATE COMPANIES (`dup_pairs_A.tsv`); `price_integrity_check.py` `[duplicate]` | |
| fix | dedupe BEFORE any scan: one series per company per date, the point-in-time symbol kept, never alphabetical; the retired symbol dropped for the 41 renames (`eraA_dedupe_map.tsv` `drop_hint`); scaled twins: keep the series whose adjusted/raw ratio is explained by the surviving issuer's own splits. Add a one-entry-per-company-per-date guard to the runner | |

### F3 — Symbol identity: the symbol is not the company

| | era A | era B |
|---|---|---|
| status | **confirmed** | **confirmed** (its own reuse; no identity guard existed) |
| keying | history keyed by TODAY's symbol: XYZ holds Square's 2016-22 bars, OPLN holds KAR's, META = FB. 86 tickers / 4,379 member-nights in the overlap carry a symbol B does not have yet; 580 A-only symbols map to a B symbol by rename matching | point-in-time: FB to 2022-06-08, META from 2022-06-09; B's META before that is a different ~$10-16 instrument (87 bars); RXN→ZWS is one company as two series |
| different company on the same symbol, overlap 2021-09-27..2022-06-30 | of 7,316 shared symbols with ≥20 shared days: **50 different series** (return corr < 0.9; 27 liquid-L2; 0.86% of shared dollar volume), 85 same series at another level, 14 undetermined. The existing `symbol_guard.tsv` flags only 4 of the 50 — not a guard defect: 46 have no hole or jump in A's own series. `security_type_check` P1x counts 116 different-company tickers of 7,460 (6,080 bars) by a 0.2%-return-match rule | 717 holes > 30 sessions on 397 symbols (20 liquid-L2; INFO 658 sessions, FI 421, COR 420 — CoreSite then Cencora); 4,994 unexplained jumps > 70% on 984 symbols (22 liquid); **1,302 symbols with any break, 34 liquid**; test symbol ZVZZT moves of +3,130× |
| guard blind spot (10–30-session holes with a 2×/0.5× price AND 10×/0.1× dollar-volume change) | 14 rows on 12 symbols, 2 liquid — **ruled out** | 47 rows on 39 symbols, 0 liquid |
| impact | every symbol-keyed join lands on another company: the labelled-EP list, caption tickers, alert history, SIC / type / splits tables (small_pulls gives FB type ETF — the symbol's CURRENT holder), any A↔B stitch at the 2022-06-30 seam (71 constant-scale + 35 varying mismatches of 7,460 shared symbols). The mismatch rate before 2021-09 is unmeasurable offline and can only be larger | a reused symbol with no hole reads as one company; a fake +100% runner or blow-up at the splice |
| check | `universe_check.py` IDENTITY ACROSS EXPORTS (`pair_identity.tsv`) + IDENTITY BREAKS (`symbol_guard_{A,B}.tsv` in the runner's `--breaks` format); `duplicate_series_check.py --vs`; `security_type_check.py --vs-export` | |
| fix | key every export by FIGI / CIK + date, symbol as a label (the refetch sidecar `records.tsv` carries both); pass `symbol_guard_B.tsv` as `--breaks` on every 2022-24 read; never stitch eras by symbol; when joining operator-labelled EPs, check the bar's price against the labelled price on that date | |

### F4 — Corporate actions and price integrity

| | era A | era B |
|---|---|---|
| vendor-BOOKED wrong adjustment (the raw/adjusted ratio steps but the adjusted series still breaks) | **confirmed:** 1,106 adjustment steps (883 tickers), **75 DISCONTINUOUS (24 liquid-L10)**; in 45 the raw price moved < 50%. RTX 2020-04-03 adjusted −71% vs raw −42%; AA 2016-11-01 −73% vs −20%; BEP 2020-07-30 −81% vs −26%. Alpaca does not merely miss spin-offs — for these it books a factor that makes the drop WORSE. Exposure 2,829 liquid ticker-days (0.103%) inside 126 sessions after one | no raw-close file, so invisible this way. Against 1,452 material listed splits: 1,385 continuous, **67 break the series (3 liquid)**, 8 by exactly the listed ratio (applied in the wrong direction: SQFT, XELAP, SNES…) |
| unadjusted spin-offs / special distributions | **suspected (signature weak):** candidates (persistent ≥25% drop, volume ≥2× median) 3,630 (709 liquid-L10), mechanical subset 597 (142 liquid); child-listing match is NOT discriminating (0.161 real vs 0.171 placebo). Controls OPLN, ZWS, BEP all FLAGGED. Confirmed set = 3 controls + the 75 above, nothing more | candidates 8,462 (569 liquid), mechanical 947 (135 liquid); Polygon adjusts SOME spin-offs A does not (LEN ×1.033, MMM ×1.196, MDU ×2.63 — the seam) |
| split-like ratios with no known event | suspected: 647 (78 liquid), volume-confirmed 25 (8 liquid): real meme/ETF moves (AMC 2021-06-02), the ZWS seam, unlisted splits | 2,929 (60 liquid), volume-confirmed 77 (5 liquid; ZVZZT, MSGE 2023-04-21 reuse seam) |
| price LEVEL is not a price | ruled out for ratio reads, **confirmed for any dollar threshold:** 431 tickers / 199,388 rows with adjusted close ≥ $1,000; RUBI 2016 $937,170 vs raw $16.02; 85 shared symbols at a different level from B (52 explained by a split/spin after 2022-06-30: MMM, SVC) | 376 tickers / 110,576 rows ≥ $1,000, max 1.77e13; 39 non-positive rows (ELOX, WTER), 9,616 rows < $0.01 |
| volume basis | A/B volume ratio on 1,302,338 shared ticker-days: median 1.034, P5 1.000, P95 1.240 — A ~3% higher; a dollar-volume floor admits slightly more in A | B = consolidated; 99,612 zero-volume rows (1.156%) on 1,779 tickers, 74 rows on 25 liquid-L2 symbols |
| impact | C0 (n=13,363): 0 holds touched by a discontinuous event; the harm is **long-hold cells**: R1 A20_X3_P0 (n=9,281) worst trade −33.9R → −10.1R and mean +0.0747 → +0.0767 with the union removed; A20_X1_P1 worst −21.9 → −9.7R. The ranking side: a fake −70..−90% collapse hides a name for up to 126 sessions (invisible recall loss). **Persistent ≥25% UP gaps are the tail, not artifacts** (67 C0 trades, mean +14.5R, 28 of them ≥10R — never "clean" them) | C0 (n=8,984): 4 holds touched by a mechanical spin-off candidate (mean −2.9R); R1 cells move ≤ 0.002R |
| check | `price_integrity_check.py` `[adj_event] DISCONTINUOUS`, `[spinoff]` (controls; exit 3), `[splitlike]`, `[level]`, `[gap]`, `[volume]`; `trade_impact.py` on every trade list quoted | |
| fix | the 75 (ticker, date) events = exclusion list for RS/return windows until re-adjusted; keep raw beside adjusted on every refetch (fetch raw closes for B once so the step check can run); read the ~13 volume-confirmed liquid split-like rows by hand and add real ones to the split reference; **any NEW dollar threshold uses the RAW close** | |

### F5 — Security type: non-stocks in the universe, and the type table is not point-in-time

| | era A | era B |
|---|---|---|
| status | **confirmed** | **confirmed** (small) |
| untyped names ADMITTED (the runner admits an unknown type "as prod does") | **419 of 3,019 admitted tickers (13.9%) / 169,143 of 2,026,137 admitted member-nights (8.35%)** (U rule); by year 2017 11.6% → 2021 3.6%. Most are real companies acquired before the type table existed (XLNX, NUAN, KSU, AGN, CELG…): 967 primary-arm trades +73.0R, 47 of 500 ≥4R — legitimate signal, unverifiable type. By L2: 135 of 3,900 liquid symbols untyped (3.5%; 1.9% when `--sic` adds the SIC pull's types) | 0 of 3,071 admitted tickers; by L2 802 of 4,499 liquid symbols (17.8%) untyped because delisted names have no type row |
| non-common instruments that PASS the filters | **23 tickers, hand-verified** (3×/inverse crude and gas ETNs UWT, DWT, GASL, RUSL, MRRL; FRLG; bond/country ETFs BSCJ, BSCK, BSJJ, BSJK, BSJL, IBDL, IBDM, ERUS; WTRU; BDXA; SPAC shells PSTH, AGC, IPOA, TACO, SAMA, MUDS, HCAC): 2,613 of 2,026,137 admitted nights (0.13%), 204 of 192,897 watch rows, 20 of 11,011 primary-arm trades = −17.2R of +432.4R, 0 of 500 ≥4R. **DWT: admitted 628 nights 2017-06-16..2020-04-02 at median raw close $8.91, median 20-day dollar volume $71.5M** | 5 SPAC shells typed CS (PSTH, ASZ, CVII, GGPI, IPOF; 310 nights): 0 watch rows, 0 of 7,330 entries |
| the type gate is the ONLY barrier for look-alikes | excluded by type alone: 805 tickers / 472,418 nights (18.9% of price+liquidity+regex passers): ETF 721, ETV 35, FUND 38, ETN 6 | 895 tickers / 368,491 nights (21.6%): ETF 814, ETN 12 (FNGU, BULZ, NRGU…), ETS 5 (TSLY, CONY…), WARRANT 1 (DJTWW passes the regex) |
| type source not point-in-time | one row per ticker as of 2026-10-16 (or the delisting date); 49 admitted tickers have an identity break AFTER member nights: 18,344 nights (0.91%) typed by the later holder | mi vs SIC-pull disagree on 5 of 2,508 members, 0 across the admit line |
| false EXCLUSION (operating companies typed non-common by the symbol's current holder) | 11 tickers / 1,250 nights (DHC typed FUND, MNR typed UNIT, ILPT…) | 6 tickers / 120 nights + IIVI 110 nights (II-VI typed SP because the symbol was reused by a preferred) |
| de-SPAC trust-price history inside the 130-bar window | 48 admitted tickers, 1,528 member nights, 52 primary-arm trades = −8.6R — a SELECTION question (fork), not a type error | 8 tickers, 212 nights, 1 entry |
| OTC-today / regex / ADR mislabel | **ruled out**: OTC-today 47 tickers (fell off an exchange later), 3 foreign-suffix lines = 2 trades −2.0R; regex drops 10 liquid dotted class shares (BRK.B…), matching prod; ADR disagreement 3 of 2,253 | OTC-today 6 tickers; regex drops 10 preferreds (lowercase p notation) |
| impact | contamination exists and does not move the read (mean R 0.0393 → 0.0409 without the 23); **but every refetched delisted name arrives untyped, so without a type join the refetch RAISES this share** and dead ETNs/warrants enter as stocks exactly where the tail is being repaired | none today |
| check | `security_type_check.py` U1/U2 + `--verified-real <hand list>` + `--max-unknown-share 0.02` (exit 3) + `--breaks symbol_guard.tsv` (U8) + `--impact`; `universe_check.py` NON-EQUITY ITEMS (tripwire: > 5% of liquid-L2 symbols untyped) | |
| fix | join Polygon `type` from the refetch `records.tsv` (and a point-in-time reference pull for the 419 already-in-export unknowns) before any scan; fail the build if > 2% of admitted nights are untyped. **Whether the backtest REJECTS untyped / non-common / de-SPAC-phase nights where prod admits them is an OPERATOR FORK** (§5) | |

### F6 — Bar integrity, calendar, stale bars, tooling hazards

| | era A | era B |
|---|---|---|
| duplicate keys / NaN / OHLC order / weekend bars / off-calendar | **ruled out**: 0 of 10,320,661 on every test; 59 business days with no bar (holidays + 2018-12-05); 0 thin sessions of 1,635 | 0 of 8,619,626 except 39 non-positive rows; 31 holiday days; 0 thin of 821. Caveat: zero OHLC violations in a whole vendor export may mean high/low were clamped upstream (unverified) |
| stale / forward-filled | ruled out: 0 zero-volume rows (the build drops Alpaca's forward-fill into a real hole); 508 frozen copies on 264 symbols, 2 liquid-L2 | 5,180 carried closes on 334 symbols, 23 with a run ≥3 (longest 807–814 = test symbols); 4,727 frozen copies, 0 liquid |
| missing sessions against SPY | 503,456 of 10,824,117 expected (4.65%) in 4,074 tickers; liquid-L10 holes 165 (73 ≥5 sessions); 0 trades in any tested population with a ≥5-session hole in the hold or the 60 pre-bars | 509,245 of 9,128,871 (5.58%); liquid holes 48. **The no-trade convention differs: A omits the bar, B writes a zero-volume flat bar** — "N consecutive sessions" means different things per era |
| exchange test symbols | 0 | **15 tickers, 5,712 rows** (ZVZZT, ZTST, ZTEST, ZBZX, PTEST, ZIEXT, ATEST…); the universe excludes them but they generate gap/split flags |
| ticker `NA` parses as NaN with pandas defaults | none | Nano Labs, 620 rows: vanishes from every groupby; 11 of 33 scripts reading the export lack `keep_default_na=False` |
| impact | none on liquid names or trades | none on trades; the convention difference matters for any history-length rule |
| check | `universe_check.py` INTEGRITY / COVERAGE / STALE; `price_integrity_check.py` `[ohlc]`, `[calendar]`, `[volume]`, `[test_symbol]` | |
| fix | none needed; keep as the first section of the gate (the tripwire for a bad refetch). Loader rule: `keep_default_na=False`, `dtype={ticker: str}`, drop `v == 0` and `close <= 0` before any gap/base/history logic, drop the test-symbol regex at export build | |

### F7 — Point-in-time inputs (the backtest's own inputs, not the bars)

| item | status | size | impact | check |
|---|---|---|---|---|
| N3/N4 RS denominator = that night's export members (survivors only in A; duplicates counted twice; not prod's `mi_stock_scores` ~2,400 rows) | confirmed | overlap window: rs_best differs ≥1 pct-pt on 13.0% of 109,239 member-nights; rs_best ≥98: 4,869 in A vs 4,455 in B; 122 of 8,763 B watch nights change side (net +7.0%) | RS percentiles do not compare across eras; the RS gate admits ~7% more in A on the same dates | `pit_lint.py overlap` |
| N1 SIC as of 2026-10-16, one row per ticker | confirmed | A: 1,026 member tickers no SIC = 412,843 member-nights (20.4%); B: 411 tickers = 155,934 (11.6%) | only C2/C6 read `grp_pct`; they read False on 20% of A nights vs 12% of B | `pit_lint.py inputs` |
| N2 security type today's, unknown admitted | confirmed | see F5 | see F5 | `pit_lint.py inputs --assets` |
| N5 regex applied to today's symbol | suspected | 161 (A) / 563 (B) export symbols excluded outright | a company whose current symbol carries a class suffix loses its whole A history; liquid names hit not measured | `pit_lint.py inputs` |
| N7 thresholds cut on the whole discovery distribution (TRAIL_SPEED_ADR_CUT, report terciles) | suspected | only the 5 `tspd` exploratory arms of 25; never the primary | low; flag those arms as in-sample | `pit_lint.py lint` |
| N6 market cap/float, N8 split list | ruled out | not used / guarded by test | — | `lint` |

### F8 — Look-ahead inside the walk

| item | status | size | impact | check |
|---|---|---|---|---|
| L4 stop = low of the day THROUGH the fill minute, including that minute's own low | confirmed | A: 73 of 13,368 filled tl orh5 (0.5%), stop a median 0.17% of price under the pre-fill low; B: 35 of 8,961 | small, optimistic | `pit_lint.py entries --minutes` |
| L5 minute-vs-daily abstain decided on the WHOLE day's minutes | suspected | A drops 46 of 17,405 first breaks (0.26%); B 145 of 12,250 (1.18%, 110 whole-day scale shifts = corporate action or reused symbol) | mostly a correct data guard; the dropped population differs 4.5× by era | `pit_lint.py entries --candidates` |
| L8 (+L6) walks whose data ends inside the 121-session window end "degraded" and leave every decisive number — a population chosen by the stock's future; an identity break inside an A walk is not cut | confirmed | A: 687 of 38,054 first breaks (1.81%) + 61 missing-session + 30 crossing an uncut break; B: 942 of 41,112 (2.29%) + 84 | acquisitions (premium then a pinned price) and bankruptcies both leave the decisive set; A under-represents them already | `pit_lint.py horizon` |
| L7 discovery walks near 2024-12-31 read sealed 2025 bars | confirmed | B: 7,311 of 41,112 first-break windows reach past the seal (17.8%); 4,409 filled rows actually read past it | contaminates the sealed-holdout principle for long exits; selection unchanged | `pit_lint.py horizon` |
| L10 chain key built from poles after D | ruled out | 2 of 30,036 (A), 0 of 36,298 (B) differ | none | `pit_lint.py chain` |
| L1/L2/L3/L9/L11/L12 | ruled out, each guarded by a named test | — | — | `pit_lint.py lint` (exit 1 if an anchor moves) |

### F9 — Feed and calendar

| item | status | size | impact | check |
|---|---|---|---|---|
| F1 minute fetcher keeps 09:30–16:00 every day → 13:00–16:00 after-hours prints enter the minute engine on early-close days | confirmed | A: 5,728 of 164,702 minute bars on 11 early-close days (3.5%); 100 of 13,368 fills have E on an early close, all carrying after-hours minutes; B: 89 of 8,961 | 0.7–1.0% of fills: a thin print can book a false day-0 stop or set the stall-cut peak | `pit_lint.py calendar --minutes` |
| F2 two daily vendors (A Alpaca, B Polygon) | confirmed | on 451,515 common ticker-days: high differs > 0.5% on 1.55%, low 1.53%, close > 0.1% on 1.92%; volume A/B median 1.031; universe membership differs on 4,171 ticker-days | ~1–2% vendor noise on every era comparison; corporate-action handling differs by era | `pit_lint.py overlap` |
| F6 minute and daily bars on different scales under the 1% abstain | ruled out | A 0 of 13,268; B 3 of 8,872 | negligible; re-run after any re-pull | `pit_lint.py entries --candidates` |
| F3/F4 feed = SIP both eras; sessions per year = NYSE; 0 bars off SPY's calendar | ruled out | — | — | `pit_lint.py calendar` |

### F10 — Walk assumptions and costs (not data defects, but they decide whether a data-clean result is an edge)

| item | status | size | impact | check |
|---|---|---|---|---|
| W2 exits pay NO slippage (only entry 0.1%) | confirmed | median stop width 1.86% (A, n=13,368) / 1.91% (B, n=8,961) → **0.1% per exit leg costs 0.067R mean, 0.12R at P90** | about the size of era A's whole published edge (C0 +0.0254R, n=13,363; R1 first trades +0.050/+0.075R). An edge that disappears at 0.1% exit slippage is not an edge | `pit_lint.py entries` W2 line |
| W3 a stop-buy fills AT level × 1.001 whenever the minute opened at or below it | suspected | 76.4% (A) / 73.4% (B) of fills at the level; fill-minute high above the level median 0.11%, P90 0.47% (0.25R at P90) | fast breakouts (~a tenth of fills, the tail candidates) understated by up to ~0.25R | `pit_lint.py entries --minutes` |
| W1/W4/W5/W6 | ruled out | fees ~0.0016R; long-only; stop-and-target bar books the stop; gap through stop exits at the open | — | `lint` |

### F11 — Sealed-table dependence (the 2025-26 table)

| | era A | era B |
|---|---|---|
| status | n/a (0 of 13,363 trades) | **confirmed** |
| size | — | **57 of 8,984 published C0 trades: 28 entered 2025-01-02 (sum −5.2R), 29 more whose hold runs past the last 2024 bar (sum +126.1R, mean +4.35R, 2 ≥10R)** — `trade_impact.py` prints these as "28 entered after the cutoff" and "57 holds run past the last bar kept" (the second count includes the first); 7 R1 A20_X3_P0 era-A holds also run past the kept bars |
| impact | — | published 2022-24 mean R −0.1691 is lifted +0.0146R (≈9% of its magnitude) by trades that need sealed data; tail share unchanged (0.946 ≥10R per 100) |
| check | `trade_impact.py` prints "trades entered after the cutoff" and "holds past the last bar kept" for every trade list | |
| fix | censor or drop any trade whose entry or whole exit path is not inside the cut window before quoting a 2022-24 number; assert `E + exit_session ≤ cutoff` at trade generation | |

### POTENTIAL — not yet measured (the "ones we don't know"). One line each: what it is, how it would be measured, $0 unless stated.

| item | why it could matter | how to measure |
|---|---|---|
| **Minute-bar integrity** (OHLC order, zero-volume minutes, missing minutes inside a session, pre-market prints before 09:30, duplicated timestamps) | the fill, the stop and the day-0 walk all come from minutes; no auditor opened a minute file for integrity | a `minute_integrity_check.py` over `cb702*/minutes/*.psv.gz`: per-day counts vs 390 (or 210 on early close), OHLC order, first/last timestamp, zero-volume share, duplicates — same selftest pattern |
| **Dividends** (A is split-only; B's adjustment basis for cash dividends unknown) | a large special dividend reads as a drop; a yield name's total return is understated in any hold | compare A vs B close ratio steps on ex-dates from a free dividend list; count ratio steps 0.1–5% in `daily_raw_close` (10 found, none investigated) |
| **Era B raw closes do not exist** | the vendor-booked-factor check (the one that found RTX/AA/BEP) cannot run on B; 67 breaking splits may be the visible part | fetch raw daily closes for B once (free, Alpaca `adjustment=raw` or Polygon unadjusted), then run `price_integrity_check.py --raw-close` on B |
| **Identity mismatch rate before 2021-09** | measured only in the 9-month overlap (50 of 7,316); current-symbol keying means it grows going back | after the FIGI-keyed rebuild, count symbols whose FIGI changes inside A's span; until then, flag every A symbol with a probable rename as untrusted before 2021-09 |
| **LULD / regulatory halts and IPO first-day bars** | a halted session looks like a hole or a flat bar; an IPO's first bar has no prior close so gap logic is undefined | count tickers whose first bar is inside the span and whose first-day range ≥ 25%; count single-session holes on liquid names against a free halt list |
| **High/low clamping upstream** | 0 OHLC violations in 18.9M bars is suspicious; a clamped high hides a wick that would have stopped a trade | compare daily high/low against the minute max/min on the same day for every filled entry (the data exists: `pit_lint.py entries --candidates` already computes both sides) |
| **The sealed 2025-26 table itself** | every check above stopped at 2024-12-31 by rule; the sealed table has never passed a data gate, and its first read is the one-shot holdout | the gate run on the sealed table is itself a read: run `run_all.sh` on it ONCE with `--allow-sealed`, pin the console output, and count that run as the only pre-read touch (operator's call when) |
| **Alpaca asset-list drift between fetch dates** | A was fetched from one day's asset list; a later refetch sees a different list, so two builds are not comparable | store the asset list hash with every export (`export_stats.tsv` + a `data_fingerprint` line, §6) |
| **Era A volume basis (SIP vs consolidated) before 2021-09** | volume A/B measured 1.03 in the overlap only | once B raw closes/volumes exist for 2016-21 (Polygon re-pull), recompute the ratio by year |

---

## 2. STEP 0 — the DATA GATE every registered read passes before any outcome is opened

Run `bash scripts/backtest_data_audit/run_all.sh <era-dir> <label> [richer-era-dir]` (README has each command). The gate is the table below; **a refusal means the read does not start** — it is not a caveat to carry. Every check keeps `--cutoff 2024-12-31` (the scripts refuse a later one); the sealed table is never opened by a gate run except the one pinned run in §1 POTENTIAL.

| # | check | script and flag | threshold (PASS) | what refuses | era A today | era B today |
|---|---|---|---|---|---|---|
| G1 | bar integrity | `price_integrity_check.py [ohlc] [calendar] [test_symbol]`; `universe_check.py` INTEGRITY | 0 duplicate keys, 0 NaN, 0 OHLC violations, 0 off-calendar bars, 0 test symbols in the universe | any non-zero → stop (a refetch is broken) | PASS (0/0/0/0/0) | PASS except 15 test tickers present in the export (universe excludes them) |
| G2 | universe completeness | `universe_check.py --other <richer export>` liquid-per-session ratio + KNOWN-GONE | ratio ≥ 0.97 of the richer export; known-gone missing rate at the 2025-26 control level (~9%) | ratio < 0.97 → **REFUSE** (survivors only) | **FAIL: 0.852–0.867; 63.3% of 529 gone names missing** | n/a (the richer side) |
| G3 | duplicate companies | `duplicate_series_check.py` TEST 1/2 | confirmed pairs = 0, duplicate rows = 0, scaled twins = 0 | any confirmed pair → **REFUSE** until deduped | **FAIL: 71 pairs + 27 scaled** | PASS (0) |
| G4 | identity | `universe_check.py` IDENTITY (`pair_identity.tsv`, `symbol_guard_<label>.tsv`) | liquid `MISMATCH_different_series` = 0 once FIGI-keyed (today's measured floor: 27 liquid); liquid short-hole level shifts ≤ 0 (A) / ≤ 5 (B); a `--breaks` file EXISTS and is passed to the runner | no `--breaks` file for the era → refuse; liquid mismatches above the recorded floor → refuse | floor 27 liquid (recorded); guard file exists | 0 liquid mismatches at the seam by B's own series; `symbol_guard_B.tsv` now exists — **must be passed** |
| G5 | corporate actions | `price_integrity_check.py --raw-close/--splits --controls` | the three positive controls FLAGGED or NOT_TESTABLE-with-reason (script exits 3 otherwise); the DISCONTINUOUS list written and carried as the RS/return exclusion list | exit 3 → refuse | PASS (75 events listed) | PASS (67 listed; controls out of range / seam) |
| G6 | security type | `security_type_check.py --max-unknown-share 0.02 --verified-real <list>` | untyped ≤ 2% of admitted member-nights (U rule); the 23 verified non-common reported (count, not yet a refusal — operator fork §5) | exit 3 → **REFUSE** | **FAIL: 8.35%** | PASS: 0% of admitted nights (the report-only `universe_check` tripwire still fires: 6.0% of 4,499 liquid-L2 symbols untyped with `--sic`, 17.8% without — delisted names with no type row, which the universe rule does not admit) |
| G7 | point-in-time lint | `pit_lint.py lint` | every anchor found (exit 0); the 16 confirmed/suspected unguarded items listed in the read's registration doc | exit 1 (an anchor moved) → refuse until the checklist is re-anchored | PASS (33 items, 0 missing) | same |
| G8 | sealed-trade dependence | `trade_impact.py` on EVERY trade list about to be quoted | entered-after-cutoff = 0 and holds-past-last-bar = 0 (or the list is censored and the count printed beside the headline) | a quoted number with uncensored sealed-dependent trades → refuse | PASS (0/0) | **REFUSE as published: 28 entered after + 57 holds past (= 28 + 29) of 8,984** → censor |
| G9 | calendar + early close | `pit_lint.py calendar --minutes` | sessions/year = NYSE; after-hours minute bars on early-close days = 0 after the fix (F1), else the count printed beside every fill statistic | — (report) | 5,728 after-hours minute bars; 100 fills exposed | 7,281; 89 fills |
| G10 | overlap parity (only when two eras are compared) | `pit_lint.py overlap` | member-night agreement ≥ 98% after the rebuild; the vendor-agreement line printed beside every era comparison | — (report; a comparison without the line is incomplete) | members per night in both exports 1,736 = 83.8% of B's 2,072; 335 absent from A | — |

**Era A today: refused by G2, G3, G6** (`run_all.sh` 2026-10-23, verdict in `scripts/backtest_data_audit/runs_2026-10-23/run_all_A/verdict.txt`: S0 4 of 4 selftests pass; G1, G4, G5, G7, G8, G9 PASS; G2, G3, G6 REFUSE; exit 2). Until the refetch + dedupe + type join land, every 2017-21 figure carries the literal label *"survivors only: about 14% of liquid names and 26% of liquid runners absent; 71 duplicate companies; 8.35% of nights untyped"*. **Era B today: refused by G8 only** (`runs_2026-10-23/run_all_B/verdict.txt`: G1, G3, G4, G5, G6, G7, G9 PASS; G2/G10 not measurable without a richer export; G8 REFUSE on the published C0 list — censor the 57 and quote the count; `symbol_guard_B.tsv` must be passed as `--breaks` on every 2022-24 read; the 15 test tickers sit in the export and the universe rule excludes them).

**Exit codes, so a shell can refuse:** `price_integrity_check.py` 3 (control not flagged); `security_type_check.py` 3 (`--max-unknown-share` / `--max-verified-nights`); `pit_lint.py lint` 1 (anchor missing); every script `sys.exit` on a cutoff past 2024-12-31. `universe_check.py` and `duplicate_series_check.py` exit 0 always (reports) — `run_all.sh` reads their verdict lines for G2/G3.

## 3. Positive controls — a check that cannot see its known case is not a check

Each check carries a case it MUST find. **Reported here as they stand today, not as intended.** A new or rebuilt export re-runs all of them; a control that stops firing is a broken check or a broken export, never "fixed data" until shown.

| control | family | what must happen | state 2026-10-23 |
|---|---|---|---|
| **OPLN 2019-06-28** (KAR→IAA spin-off, read as a −34R loss) | F4 | `price_integrity_check.py [spinoff]` FLAGGED, or exit 3 | A: **FLAGGED** (mechanical candidate, rc −0.597). B: NOT_IN_EXPORT_RANGE (before 2021-09-27) |
| **ZWS 2021-10-05** (Rexnord/Zurn distribution) | F4 | FLAGGED | A: **FLAGGED** (mechanical, rc −0.491). B: **NOT_TESTABLE** — B carries the company as RXN to 2021-10-04 and ZWS from 10-05, so the event is a ticker seam, not a gap (an identity case, F3) |
| **BEP 2020-07-30** | F4 | FLAGGED | A: **FLAGGED as a vendor-booked factor with a broken series** (adjusted −81% vs raw −26%). B: out of range |
| **FB = META** (one company, two symbols, byte-identical) | F2 | `duplicate_series_check.py` lists the pair; `universe_check.py` dup_pairs lists it | A: **found** (1,620 identical days; switch 2022-06-09 within one session of the public date). B: correctly NOT a twin (B's META before 2022-06-09 is a different instrument) |
| **planted twins in B's own file** (AAPL copied as AAPLX exact; NVDA ×1.00004; MSFT ×10 price ÷10 volume) | F2 | all three found, nothing else | **found 3 of 3, 0 false** — so B's zero is a real zero |
| **selftests** (`universe_check.py --selftest` plants 5 defects; `duplicate_series_check.py --selftest`; `price_integrity_check.py --selftest` injects one defect per check; `security_type_check.py --selftest` the name classifier; `pit_lint.py chain` reproduces the documented bridging-pole case) | all | every planted defect found by its own check | universe 10 of 10; duplicate pass; price pass; security pass; chain fires on the synthetic case |
| **TWTR present in era A after the refetch** (and ATVI, MRO, X, WBA — the 334 gone names) | F1 | `gone_list.tsv` status `in_primary` for TWTR; known-gone missing rate ≈ 9% | **PASS on `cb702_pre_v2` (10-23):** TWTR, ATVI, EA, X carry all 1,635 sessions; known-gone missing 5.7% |
| **DWT** (3× inverse crude ETN, untyped) | F5 | `security_type_check.py` U2 names it; **after the operator rules, 0 admitted nights** | **detected, NOT excluded**: 628 admitted nights, in the hand-verified list of 23. Exclusion from the backtest universe is the operator's fork (§5); today it stays, as prod admits it |
| **the existing `symbol_guard.tsv`** | F3 | `universe_check.py` breaks test reproduces it | **578 of 578 symbols reproduced**, 0 only on either side |
| **ZVZZT and the test symbols** | F6 | `[test_symbol]` lists them in B; the universe admits none | 15 tickers listed; 0 trades in any population |

## 4. How a backtest is run here, end to end

This section adds only what is DATA-specific. The rest is owned elsewhere and is not copied (a second copy drifts — #707's own failure condition): how an analysis is framed and ranked → `docs/methodology/analysis_standard.md` + `ANALYSIS_CARD_PREAMBLE.md`; the registered-read scaffold (freeze map, `--print-pins`, once-only, option refusals, dry run, verdict file) → `scripts/probes/_cb_backtest/registered_read.py` header + `README.md` §#705(a); the sealed holdout and its one read → `docs/analysis/cb_rs_alone_prereg_2026-10-22.md`.

1. **Population first — and the population starts with the DATA, not the filter.** Before the funnel: which export, which build date, which era, what the gate said (§2 table, verbatim, with the A-today refusals). `live_rules.py` first for the acting rules.
2. **STEP 0 data gate** (`run_all.sh`) on every export the read will open, and `trade_impact.py` on every trade list it will quote. The console goes into the registration doc. A refusal stops the read; a report line goes beside the headline.
3. **Point-in-time inputs, declared:** symbol keying (today's vs at-the-date), type source and its snapshot date, SIC as-of, split list as-of, the RS denominator (export members, not prod's `mi_stock_scores`), the `--breaks` file. If an input is not point-in-time, the read says which numbers it can move (F7).
4. **Dedupe + identity map before any scan:** one series per company per date; renamed names joined through the rename map, never by bare symbol; the DISCONTINUOUS corporate-action list (F4) excluded from RS/return windows; raw close for every dollar threshold.
5. **Pins:** the export's hash and row count, the gate console, the sidecar hashes (`symbol_guard`, `small_pulls`, `cb702_splits`, `cb702_sic`), the minute tree, the module SHA — all in the freeze map, all before the first bar is opened (the scaffold refuses otherwise).
6. **The matched control** is what is actually live (analysis_standard §3), computed on the SAME gated data with the SAME dedupe — a control on raw data beside a treatment on clean data is a data comparison, not a strategy comparison.
7. **Sealed-table rule:** nothing after 2024-12-31 is read for any outcome; walks are censored at the seal and the censored count printed (F11, L7).
8. **Costs beside every headline:** every R number at 0 / 0.1% / 0.2% exit slippage per leg (W2); fills at the level and at half the fill-minute run-through (W3). An edge that disappears at 0.1% is not an edge.
9. **Independent verifiers check the population first** (memory: check-the-population-before-the-analysis), then the quantity named vs the quantity computed (preamble 2026-10-22), then re-derive the verdict from the pinned files.
10. **What a result may claim.** Era A: *survivors only* (the §2 label) until G2/G3/G6 pass — a recall ceiling of about a quarter of the big runners, and a left tail that is under-represented; R comparisons across eras carry the vendor gap (F9) and the RS-denominator gap (F7) and are not like-for-like. Era B: population-complete; costs as in step 8; sealed-dependent trades censored. **No result may claim an edge without the slippage line, the n after dedupe, the per-year duplicate share, and the gate verdict in the same table.** Plain words, every number with its n and its meaning (CLAUDE.md report format).

## 5. Fix queue — who owns it and what each fix changes

Two columns on purpose: the left is data pipeline work that needs no ruling; the right is a universe/selection change and waits for the operator (THE LINE: the backtest universe mirrors what prod admits, so changing it is his call). Nothing here is a PLAN.md line; the owning task is #705 (data) and #707 (the vault page).

| fix | owner | what it changes | acceptance (the control that flips) |
|---|---|---|---|
| **Delisted refetch** (`01_fetch_delisted.py`, DONE 10-23: 3,226 symbols, 2.18M bars) back to 2016-01-04, FIGI/CIK sidecar `records.tsv` | data pipeline (me) | era A gains the ~334 gone names + their blow-ups and runners; `ended_by_year_A` flattens | TWTR `in_primary`; known-gone missing rate ≈ 9%; liquid ratio ≥ 0.97 |
| **Rebuild era A keyed by FIGI/CIK + date**, symbol as label; rename map; dedupe (strict + scaled) | data pipeline | G3 → 0 pairs; G4 liquid mismatches → 0; joins to labelled EPs hit the right company; n and tail counts no longer inflated 1.5–2.7% | `duplicate_series_check` 0/0/0; FB=META collapses to one series with the switch date |
| **Type join** from `records.tsv` + a point-in-time Polygon reference pull for the 419 in-export unknowns | data pipeline (needs network, $0) | G6 ≤ 2%; refetched names arrive typed | unknown share on the rebuilt A ≤ 2% |
| **Fetch era B raw closes once** | data pipeline ($0) | the vendor-booked-factor check runs on B | DISCONTINUOUS list for B exists |
| **Runner guards:** one entry per company per date; `--breaks symbol_guard_B.tsv` default for 2022-24; `fwd_end` cuts identity breaks; degraded walks booked at the last close as a settled exit (`delisted_mark`, deal price for acquisitions) and reported with/without; `assert E + exit_session ≤ cutoff`; h60 early-close trim applied before `entry_variants`; stop = min(lows BEFORE the fill minute) with an ambiguous same-minute stop booked pessimistic; exit-slippage parameter on every exit leg (reporting at 0/0.1/0.2%) | runner (me) — backtest reporting only, no live constant changes | F8/F9/F10/F11 sizes go to 0 or get printed; pinned reads' outputs change → **re-pin before any re-run** | `pit_lint.py` measurements read 0 on the fixed items |
| **Loader rule** (`keep_default_na=False`, ticker str, drop v==0 / close≤0 / test symbols) in one shared loader used by every script | data pipeline | `NA` stops vanishing; B's no-trade convention matches A | grep -L keep_default_na = 0 over export readers |
| **Minute integrity check** (§1 POTENTIAL) | data pipeline | the one input no lens opened gets a gate | selftest + a planted defect |
| OPERATOR FORK — **reject untyped names in the backtest universe** (prod admits them) | **operator** | A: 8.35% of nights leave (mostly real acquired companies, +73.0R, 47 of 500 ≥4R); the 23 verified non-common (−17.2R) leave with them | DWT 0 admitted nights |
| OPERATOR FORK — **exclude the hand-verified non-common list only** (keep untyped companies) | **operator** | −17.2R of +432.4R leaves; mean R 0.039 → 0.041; tail unchanged | DWT 0 admitted nights |
| OPERATOR FORK — **drop de-SPAC trust-price history nights** from RS / prior-move / base inputs | **operator** | 1,528 member nights, 52 trades −8.6R (A); 212 nights (B) | U5 count 0 |
| OPERATOR FORK — **regex / share-class handling** (BRK.B-class names, lowercase-p preferreds) | **operator** | 10 liquid dotted names enter A; prod parity breaks | — |
| OPERATOR FORK — **one daily vendor for both eras** (re-pull 2016-22 from Polygon, paid) vs restate every comparison beside the vendor gap | **operator** (spend) | F9 F2 noise 1–2% → 0; corporate-action handling symmetric | overlap close agreement → ~100% |

## 6. The Alpaca trading-backtest skill — what it adds, what it does not fix

Read: `~/.claude/skills/alpaca-trading-backtest/SKILL.md` and `reference.md`. It is a reproducible-run workflow for ONE strategy on named symbols via the Alpaca CLI (`alpaca data bars --symbol … --feed sip --adjustment split`), not a universe scanner and not a data-quality tool.

**What it adds that we should borrow (cheap, all of it):**
- **`data_fingerprint.json`** per symbol (provider, feed, adjustment, timeframe, bars fetched / after filter, first/last bar, close_sum, volume_sum, calendar filter, raw and normalized file hashes) and the rule *reuse data only when the fingerprint matches* — our freeze map pins the export hash; adopt the per-symbol close_sum/volume_sum and the asset-list hash so two builds are provably the same input.
- **`fee_source.json`** (the Alpaca Brokerage Fee Schedule PDF, revision date, modeled vs excluded categories) — W4 is ~0.0016R here, but the "state what is excluded" discipline is the point.
- **Mandatory buy-and-hold benchmark** with the same fills and friction — we have no passive benchmark line beside a cell; add equal-weight buy-and-hold of the gated universe as a report row.
- **Fill-model vocabulary** (`next_open` / `time_based` / `same_bar` with a documented look-ahead warning; stop fills at `max(open, stop)` for buys and `min(open, stop)` for sells; quote-aware fills ask+slippage / bid−slippage; conservative intrabar policy when stop and target touch) — the same conventions as W1/W6, and a cleaner frame for the W2/W3 fixes (exit friction as `bid × (1 − friction)`).
- **The run checklist** (dividends, splits, friction, calendar, look-ahead, survivorship, walk-forward, overfitting on repeated variants) and `warnings.json` — the "state every inferred assumption in `notes.md`" rule is our pre-registration doc in miniature.

**What it does NOT fix — the same holes as era A, because it is the same vendor:**
- **Universe = symbols you name, from Alpaca's CURRENT asset list** — the exact mechanism that built era A survivor-only; "survivorship bias" appears in its checklist as a word with no mechanism behind it.
- **History keyed by today's symbol** (F3): `--symbol META` returns FB's bars; no FIGI/CIK, no rename map.
- **Spin-offs and special distributions:** its `adjustment` modes are split / dividend / all; `04_ca_feed.py` (`scripts/probes/_705_corp_actions_1023/`) measured that Alpaca's corporate-actions feed misses the OPLN/ZWS/BEP class, and F4 shows Alpaca BOOKS wrong factors for 75 events in A.
- **Security type:** nothing distinguishes DWT from a stock; our type gate is ours to run.
- **One strategy, named symbols, a single `run.py`** — no cross-section (RS denominator), no universe funnel, no sealed holdout, no registered-read freeze. It cannot replace the #702 runner; it could run a single-name sanity replay of one of our trades under its fill model.
- Needs the Alpaca CLI + paper keys and network — **not usable inside the $0 offline gate.**

**Verdict:** borrow the fingerprint, the fee/assumption disclosure, the benchmark row and the fill vocabulary into our registration docs and `run_all.sh` output; do not route any read through it. (This repeats the 10-23 note in `operator_shared_notes.md`; the detail lives here.)

---

## Appendix — file index

| what | where |
|---|---|
| the checks + README + `run_all.sh` | `scripts/backtest_data_audit/` |
| universe / survivorship / identity run (2026-10-23) | `scripts/backtest_data_audit/runs_2026-10-23/universe/` (the auditor's A-vs-B run, no `--sic`: `console.txt`, `flagged_rows.tsv`, `gone_list.tsv`, `pair_identity.tsv`, `dup_pairs_A.tsv`, `liquid_per_session_by_month.tsv`, `ended_by_year_{A,B}.tsv`). ⚠ `symbol_guard_B.tsv` there is from the B-ALONE `run_all.sh` run (1,292 symbols): 10 fewer than the A-vs-B run's file because split-date jumps are explained away only on the primary export (`--splits` applies to `--export`, not `--other`; e.g. FIXX 2024-03-25, AIU 2024-07-29) — use the B-alone file as `--breaks` |
| the two `run_all.sh` gate runs (consoles + verdicts; scratch paths replaced by `<OUT>`) | `scripts/backtest_data_audit/runs_2026-10-23/run_all_A/` (A vs B), `run_all_B/` (B alone) |
| duplicate-series run + the trade join | `scripts/probes/_705_dup_series_1023/` (`eraA_dedupe_map.tsv`, `eraA_scaled_twins.tsv`, `trade_join.txt`) |
| price / corporate-action run + trade impact | `scripts/backtest_data_audit/runs_2026-10-23/{A,B}_console.txt`, `_flags.tsv`, `_summary.tsv`, `_trade_impact.txt`, `_r1_*_impact.txt` |
| security-type run | `scripts/backtest_data_audit/out_1023/run_{A,B}.txt`, `flagged_tickers_{A,B}.tsv`, `type_table_{A,B}.tsv`, `impact_*.tsv` |
| point-in-time run | `scripts/probes/_705_pit_1023/pit_run_1023.txt`, `pit_lint_checklist.tsv`, `pit_*.tsv` |
| the earlier probes that found the families | `scripts/probes/_705_corp_actions_1023/` (gap events, adjusted check, CA feed, local checks, `06_impact.txt`), `scripts/probes/_705_survivorship_1023/01_fetch_delisted.py` |
| the operator's ask, verbatim | `docs/methodology/operator_shared_notes.md` 2026-10-23 |

---

## Critic additions (2026-10-23)

A completeness pass over §1–§6 and the scripts: problem families the taxonomy does not carry, checks with no positive control, thresholds that pass a broken export, and claims above that the measurements do not support. Every number below was measured locally today ($0, read-only, bars ≤ 2024-12-31 only; no 2025-26 bar, minute file or holdout trade was opened). The one-off probes are scratch scripts, not pinned; each line names what was computed so it can be redone. Status words as in §1.

### New or re-scoped problem families

| # | gap | status | measured (n) | check that would catch it | fix |
|---|---|---|---|---|---|
| C1 | **Delisting mid-trade: how the exit is priced.** The runner marks a walk whose ticker stops printing at the last close (`consolidation_breakout._degraded`, status `degraded`) and the published lists drop it (`mature=0`) | **confirmed** (small today) | C0 rows (pp/orh5/tl, E ≤ cut): A 5 of 13,368 degraded on a ticker that died (CSFL, WPX, QTNA, PE, TSRO — all acquisitions, mean +3.9R); B 4 of 8,961 (HARP, ALPN, LBPH acquisitions; GPS = the GPS→GAP rename, a B identity split — see the §4 claim below), mean +22.3R (LBPH +77.4R). Putting them back: A mean R +0.0254 → +0.0268, B −0.1690 → −0.1590. **Today the exclusion drops takeover winners.** The other side: of B's 411 liquid deaths with no probable rename (`gone_list.tsv`), 86 end in a collapse (last close < $1 or ≤ −50% over 60 sessions; median last close $0.36), 180 pinned (10-day close spread < 1%, deal-like), 145 other; **33 end on a one-day fall of 20% or more** — SIVB's last bar is 2023-03-09 at $106.04 (halted, then delisted), FRC 2023-04-28 $3.51, SBNY 2023-03-10 $70. A last-close mark is an upper bound for those. 0 trades in today's lists end that way; the refetched era A will add them | none: `trade_impact.py`'s "holds past the last bar kept" lumps a delisting with the seal and counts mature trades only. Needed: per ticker, last bar < export end AND inside the hold → its own line | report degraded walks WITH and WITHOUT; mark deal-like ends at the last close, collapse ends at the last close AND at a delisting haircut (state the haircut), and print both; split the trade_impact line into "ticker ended" vs "seal" |
| C2 | **The minute tree is Alpaca-keyed in BOTH eras** (`fetch_minutes.py:183-184`, SIP, split-adjusted, by symbol) — era B's point-in-time Polygon daily bars sit on a today's-symbol minute tree | **confirmed** | empty minute fetches (`minutes/_done.psv`): A 111 of 126,922 pairs, every one on a retired twin/renamed symbol (ECA 35, APXT 33, XON 13, IAC 11, LIFE 9, XPER 5, RUBI 3, AGC 2) — a plausible part of F2's open "106 entry events taken under one symbol only" (not joined). B ≤ 2024: 111 of 80,858 empty; empty rate on known-gone names 52 of 4,671 (1.1%) vs 59 of 76,187 (0.08%) on the rest; AXNX 46 of 46 and INBX 43 of 43 empty. **Identity: B's GOLD (Barrick to 2024) minutes are another company** (minute close $39.27 vs daily $17.29 on 2024-05-22). 40 sampled days: daily close vs the last regular-hours minute close off by > 2% on 49 of 4,682 B series (1.05%, 22 tickers) vs 4 of 4,232 A series (0.09%) | none (§1 POTENTIAL "minute-bar integrity" is open). Needed: per (ticker, day) minute vs daily close agreement, empties by gone/rename status | fetch B minutes from the same vendor as B's daily bars, or key the minute fetch by FIGI; a reused symbol at a similar price passes the 1% abstain (L5) today |
| C3 | **L5's drop set is chosen by FUTURE corporate actions** (look-ahead in selection, not in prices) | **confirmed** | the 22 B tickers in C2 are names Polygon's daily bars adjust for events Alpaca's minutes do not carry, mostly dated after the seal (rows in `cb702_splits.psv`): HON 2025-10-30, DD 2025-11-03 (×2.39), XRX 2026-02-09, AZN 2026-02-02 (ADR ratio 2:1), LEN 2025-01-21, MDU 2024-11-01, and yearly stock dividends / scrip on ITUB, SBS, PHG, NGG, SCCO, RYN, OUT, GGB. So whether a 2022-24 breakout on those names abstains depends on a 2025-26 event. Size = L5's 145 of 12,250 B first breaks (110 whole-day scale shifts) | `pit_lint.py entries --candidates` counts it; nothing classes it by cause | rescale minutes to the daily basis with the split-table factor between the vendors before L5, so L5 abstains only on identity; §1 F8's "mostly a correct data guard" stands for the guard, not for the population it removes |
| C4 | **Daily bars vs regular-hours minutes: extended-hours prints in daily high/low; upstream clamping** (§1 POTENTIAL) | **ruled out** | same-scale series (close within 2%) with ≥ 100 traded minutes on 40 sampled days, A n=4,191, B n=4,541: daily low below the 09:30–15:59 minute low by > 1%: 2 / 1; daily high above the minute high by > 1%: 0 / 0; any side > 0.25%: ≤ 0.17%. Daily high/low are regular-session; the 0 OHLC violations are not clamping. What DOES differ: daily close = official closing auction, ≠ the 15:59 minute close by > 0.1% on 14.0% (A) / 12.2% (B); minute volume / daily volume median 0.855 / 0.856 (the 16:00 cross is outside the minute tree). That ratio also confirms SIP minutes (IEX would read a few %) | the same comparison as a gate step (the data is on disk for every candidate day) | none for high/low; any minute-engine exit "at the close" uses the 15:59 print, not the official close — state it beside time-exit results |
| C5 | **Spin-off detector recall, and era B has no testable control** | **confirmed** (defect in the check) | 8 known spin-offs inside the exports (**dates and causes from memory, no network: confirm each against Polygon's reference data or the psv before promoting it to a control**), **0 flagged** — every one is below the ≥ 25% candidate floor: A: T 2022-04-11 (WBD) −18.7%, IBM 2021-11-04 (Kyndryl) −4.9%, BIIB 2017-02-02 −6.2%, MRK 2021-06-03 −2.6%, PFE 2020-11-17 −3.5%; B: T 2022-04-11 −18.7%, K 2023-10-02 (WK Kellogg) −11.8%, DHR 2023-10-02 (Veralto) −13.9%. In the 8 B cases checked, B adjusted the 5 that carry a fractional row in `cb702_splits.psv` (GE 2023-01-04 ×1.281 and 2024-04-02 ×1.253, MMM 2024-04-01 ×1.196, IBM 2021-11-04 ×1.046, MDU) and left the 3 without one raw (T, K, DHR) — a pattern, not a proof. The three §3 controls are all ≥ 34% drops, i.e. inside the detector's own range; **G5 on B PASSes with 0 testable controls** (all three out of range / seam) | `price_integrity_check.py [spinoff]` with these as controls — today they would read NOT FLAGGED | add T 2022-04-11 (both eras), K and DHR 2023-10-02 (B), IBM 2021-11-04 (A) to `--controls`; use the psv fractional rows as a free spin-off list for 2021-09..2024; until the detector sees a −12% spin, G5 covers the big-spin tail only. Trade impact small (large caps), RS impact up to 126 sessions per event |
| C6 | **B's identity guard misses reuse below its thresholds** | **confirmed** | liquid (prior-20 median close×volume ≥ $10M) B rows that cross a 1–30-session hole with a 35–70% move: 6 rows on 6 tickers, **5 not in `symbol_guard_B.tsv`**: INBX 2024-05-31 (Inhibrx acquired by Sanofi; Inhibrx Biosciences took the symbol; −52% across a 1-session hole), DOC 2024-03-04 (Physicians Realty merged; Healthpeak took DOC), BBIG 2022-08-16, RETA 2021-12-09, VERU 2022-11-10 (the last three may be real moves; unverified). A: 4 rows, all in its guard. INBX also sits in `gone_list.tsv` as "ALIVE_at_cutoff(control)", so the 9% control rate carries reuse noise | the identity-break test with these two as positive controls (today: missed) | add INBX 2024-05-31 and DOC 2024-03-04 as B guard controls; flag a ≥ 35% move when it coincides with any hole; the real fix is FIGI keying (F3) |
| C7 | **The refetch cannot restore a dead company whose symbol was reused, and its acceptance test checks presence, not identity** | **suspected** (size partly measured) | `01_fetch_delisted.py` skips any delisted record whose ticker is already in the export (`if x["ticker"] in have: continue`), and A holds TODAY's holder of a reused symbol — so the old company stays missing (Physicians Realty under DOC is one). Candidates in the overlap: the 50 different-series symbols of F3 (27 liquid-L2); before 2021-09 unmeasured. A by-name fetch can also return the current holder's bars (C2: GOLD), which the §3 acceptance "TWTR `in_primary`; missing rate ≈ 9%" would score as restored | none | per refetched name, require its close to agree with B within 1% on ≥ 95% of shared overlap days; key the skip rule by FIGI, not symbol |
| C8 | **Survivorship differs by volatility, so the matched control does not cancel it** (§4 step 6) | **confirmed** | overlap 2021-09-27..2022-06-30, liquid-L2 B symbols (n=4,457; 774 not in A's symbol list, of which 209 renames are excluded — mapped to an A symbol by identical open and close on ≥ 50% of days, or a `gone_list` probable rename) absent from A by quintile of mean daily range (n 836–869 each): **4.4% (calmest), 6.0%, 10.9%, 19.8%, 26.1% (most volatile)**; renames themselves lean volatile too (23 in Q1, 56 in Q5). A momentum treatment sits in the top quintiles, a broad control lower, so the treatment − control difference carries its own survivorship gap; "the same gated data" is necessary, not sufficient | the absent share computed for the treatment population and for the control population, printed beside the delta | until the refetch lands, match the control on daily range too and print both absent shares |
| C9 | **Market-wide volume-event days** (index rebalances, quad witching, Russell reconstitution) | **confirmed** (two checks lean on volume) | share of liquid names with volume ≥ 2× their 20-day median: median session 5.8% (A) / 5.7% (B); top sessions are the third Fridays of Mar/Jun/Sep/Dec and reconstitution days (A: 2020-02-28 69%, 2016-06-24 65%, 2021-09-17 64%, 2018-12-21 59%; B: 2024-12-20 56%, 2023-12-15 53%, 2024-09-20 52%). **2019-06-28, the OPLN control date, is a Russell reconstitution day: 42.1% of liquid names had a 2× volume event.** The spin-off rule's "volume ≥ 2× median" and the identity guard's "explained by a ≥ 3× volume event" lose their discrimination on ~16 sessions a year | volume events measured against that day's cross-sectional median | normalise the volume-event test by the day's cross-section, or exclude index-event days from "explained" |
| C10 | **Class shares and symbol forms** | **confirmed** | B has **no dotted symbol at all: 0 of 15,702** (BRK.A, BRK.B, BF.B, LEN.B, HEI.A, MOG.A absent); preferreds use a lowercase p (563 symbols). A has 165 dotted symbols (BRK.B, BF.B, LEN.B, HEI.A, MOG.A present, plus .U units). `small_pulls.psv` types the dotted form (BF.B). The universe regex drops dotted names in both eras, so 0 trades move; any breadth, benchmark, cap-weighted or cross-section read on B is missing Berkshire and the other class shares | count of dotted / lowercase forms per export in `universe_check.py` INTEGRITY | normalise `.` / `p` forms in the shared loader before any join; state the class-share gap beside any B cross-section |
| C11 | **Corporate-action date vs ex-date** | **ruled out** (splits, overlap) | 119 material splits in `cb702_splits.psv` dated 2021-09-27..2022-06-30 with A raw bars: A's raw-close step located for 96, all 96 on the table date (offset 0 sessions); 23 not located. Spin-off and dividend dates not tested | the same offset test, kept as a tripwire | none |
| C12 | **Adjustment as-of date and vendor revision between fetches** | **confirmed** | A is adjusted as of about 2026-10-16, not 2022-06: its last-bar adjusted/raw factor applies 959 of 996 decidable material splits dated 2022-07..2026-11 (latest applied KNDI 2026-10-16), so A's levels embed 2025-26 actions just as B's do (B: PARA ×20 for a 2026-05-08 reverse split, LEN 2025-01-21). The 37 not applied are spin / ADR / stock-dividend factors (XPO, MDU, XRX, LINK, AZN) and splits Alpaca never booked (SVC 2026-07-07 5:1, GORO, BULZ, UHAL, BTCS, PYPD, IMTE, MDXH, SONX, CYAN, OMEX) plus ones announced after 10-16. **The same vendor disagrees with itself:** A's daily SVC is unadjusted for the 2026-07-07 reverse split while A's minutes (fetched 2026-10-19) are adjusted ($41.00 minute vs $8.20 daily on 2020-08-14). The three alternate B minute trees (`minutes_pre_com_1018`, `minutes_com_delta_1018`, `cb702_minutes_delta_out`) are byte-identical to `minutes/` on 2,492,256 overlapping minute rows (60 sampled days per tree). `minutes/fetch.log` repeats `minutes_pre_com_1018`'s 10-17 lines (a copy), but `minutes_com_delta_1018` is its own 10-19 fetch ("already done 0"): so either a merged copy or a two-day re-fetch with zero drift on 765,366 rows — the merge provenance is not recorded, and drift over a longer gap is unmeasured | none: `export_stats.tsv` carries no fetch timestamp | pin fetch timestamp + vendor + adjustment mode per export and per-symbol close_sum (§6 fingerprint); the "A is the unadjusted side" reading in the price-family finding is Alpaca missing specific events, not an older as-of date |
| C13 | **Trading halts** (§1 POTENTIAL) | **ruled out** at the minute level | interior no-trade gaps on active minute series (≥ 300 traded minutes, 40 sampled days): ≥ 5 min 6.9% (A, 219 of 3,157) / 6.1% (B, 196 of 3,241) — mostly thin trading; ≥ 10 min 3 / 2; ≥ 30 min 0 / 1. Whole-session halts appear as holes (F6); halt-then-delist is C1 | the gap count as a tripwire | none |
| C14 | **Feed parity with prod** | **unmeasured** (needs the server env) | backtest minutes are SIP (C4); prod resolves `ALPACA_DATA_FEED` with default `iex` (`execution_client.py:310`). If prod runs IEX, its live volume and RVOL are on a small slice of consolidated volume while the backtest's are SIP | read the server's env once | state the prod feed in every registration doc |
| C15 | **No minutes for 2022-01-04..2022-03-31 in either tree** (A minutes end 2022-01-03, B start 2022-04-01; by watch-window design) | **confirmed** | 0 minute files in that quarter | `pit_lint.py calendar --minutes` per-year counts | a stitched A+B read has no day-0 walk for Q1 2022 — say so |
| C16 | **Reverse splits on penny stocks** (the $5 floor read on adjusted prices) | **already covered** — security_type P1 / P1x | B: 13,338 watch-window nights on 178 tickers are adjusted ≥ $5 but raw < $5 (TLRY, FUBO, DNA, FCEL, NKLA); 1,860 nights the other way; cross-era raw-floor decision differs on 61 bars / 9 tickers | `security_type_check.py` P1 / P1x | the existing rule: every dollar threshold on the RAW close |
| C17 | **IPO first-day bars** (§1 POTENTIAL) | **unmeasured** | — | as §1 POTENTIAL | — |
| C18 | **Dividends** (§1 POTENTIAL) | **confirmed price-only in both eras** (inferred) | A: 70 dividend-sized raw/adjusted steps of 967,203 non-unit factor bars (security_type P1) = split-only. B: 94.95% of 1,302,551 shared overlap closes equal A's exactly — a dividend-adjusted B would drift on every payer. Holding-period dividends and their ex-date drops are unmodelled; size not measured | ex-date list (free) joined to holds | report the yield exposure of the treatment once; low for momentum names |

### Thresholds and gates that pass a broken export

- **`gate_verdict.py` reads an absent LINE as PASS (planted test).** Consoles with no parseable line, an empty `symbol_guard_X.tsv` and one selftest gave: S0 PASS "1 of 1", G1 PASS, G3 PASS, G4 PASS, G5 PASS ("no control lines"), G6 PASS ("no UNKNOWN line"), VERDICT PASS, exit 0. The README's "a missing console reads as not run, never as PASS" holds per console, not per line. Fix: every regex a gate rests on must match or the gate reads REFUSE ("unreadable"); S0 must see 4 of 4 selftests; give `gate_verdict.py` and `trade_impact.py` a planted-console selftest.
- **G4 refuses only a missing file.** §2's "liquid mismatches above the recorded floor (27) → refuse" is not coded; an empty guard file passes.
- **G2 covers only the 10 overlap months, and is REPORT with no comparator.** The rebuilt era A can be compared to B only for 2021-09..2022-06, so the 2016-20 thinning (§1 F1 "worse further back") has no gate; `ended_by_year_{A,B}.tsv` — the only evidence for it — is not read by the verdict. A run without a richer export can end PASS with no survivorship check at all. Fix: add an ended-by-year flatness test (the §5 acceptance "roughly flat 130–200 a year") to G2, and make "no comparator" REFUSE for an era not yet audited against one.
- **G5 on B is vacuous** (C5): 0 of 3 controls testable.
- **G2's refetch acceptance counts presence, not identity** (C7).
- **G8 conflates a delisting with the seal** (C1) and counts mature trades only.

### Claims above to read with these corrections

- **§4 step 10 "Era B: population-complete".** Daily deaths are there: 13 of 13 named failures and acquisitions present and ending on their last trading day (SIVB 2023-03-09, SBNY 2023-03-10, FRC 2023-04-28, BBBY 2023-05-02, TWTR 2022-10-27, ATVI 2023-10-12, SI, PACW, WE, YELL, RAD, FSR, AXNX), typed through the SIC pull (so G6's "0 untyped admitted" for B is genuine). Not complete: class shares (C10), the minute tree (C2), a rename splits one company into two series (GPS→GAP cut a C0 walk on 2024-08-21; RXN→ZWS), and a reused symbol splices two companies into one (C6). Read as "complete for deaths in the daily bars; identity and minute tree not".
- **§1 F4 "Polygon adjusts SOME spin-offs A does not".** Sharper: B adjusts the spin-offs that have a fractional row in `cb702_splits.psv` and no others (C5); the table is the list.
- **§1 F9 "F6 minute and daily bars on different scales — ruled out".** Its n (13,268 / 8,872) reads as fills, i.e. after L5 had already abstained (inferred from the standard's own n, not traced in `pit_lint.py`). On all sampled minute series it is 1.05% in B vs 0.09% in A, and the B cases are selected by 2025-26 events (C3).
- **§3 "the three positive controls FLAGGED"** is true and narrow: all three are ≥ 34% drops; 0 of the 8 ordinary spin-offs found in the exports is flagged (C5).
- **The price-family note "A is adjusted as of 2022-06"** (behind §1 F4's level row) is wrong; A is adjusted as of about 2026-10-16 (C12).

## Main-loop fixes after the critic (2026-10-23)

- **`gate_verdict.py` no longer passes what it did not measure** (the critic's first finding):
  - a missing summary line in G1 is a refusal, not a zero;
  - no selftests refuses S0;
  - G5 passes only if every spin-off control (OPLN, ZWS, BEP) reads FLAGGED;
  - G6 passes only if its UNKNOWN line was read;
  - a required gate (S0, G1–G8) left at REPORT — not run, line unreadable, or no richer export for G2 — refuses.
  - Re-tested: an empty run dir → REFUSED by all 9 required gates; era A → REFUSED by G2 / G3 / G4 / G6; era B → REFUSED by G4 / G5 /
    G8.
- **Moved out of the repo:** the two large flag files (`A_flags.tsv` 5.3 MB, `B_flags.tsv` 18 MB) are in
  `apollo_data/audit_runs_2026-10-23/`; `run_all.sh` regenerates them.

## What the first rebuild taught (2026-10-23)

- **Alpaca serves a renamed company's whole history under BOTH its old and its new symbol** (ABB and ABBNY, IDRA and ACGN). A refetch by
  old symbols re-adds them: 549 of the 3,226 refetched symbols were twins of a series the export already carried (395 strict, 152 at a
  later split scale). Run the duplicate lens on every merged trial BEFORE trusting a merge; drop the refetched twin.
- **Inside a scaled twin the raw closes are equal** (ratio 1.000 on 15 of 16 pairs checked; AQB / XON the exception); only the later
  reverse-split scale differs, so either copy gives the same returns and the same $5 floor.
- **A refetch carries Alpaca's zero-volume forward-fill rows** (99,172 here): apply the export's own row rules (`ext_bars.build`) to
  any new rows, never append raw.
- **Alpaca's split-adjusted and raw feeds disagree on ~130 rows** (mostly blank-check companies): keep only the keys both carry.
- **`run_all.sh` silently used the 2022-24 window for any label other than A or B** — a trial of era A read only Mar–Jun 2022 and
  looked clean. Fixed: an unknown label now needs WATCH_START and WATCH_END.
- **The identity guard re-derived over the merged arrays matched the original for every untouched symbol (0 differences)** — keep
  that parity assert in every rebuild; it is what proves the build path did not change.

