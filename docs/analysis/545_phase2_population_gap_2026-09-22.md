# #545 Phase 2 — CLOSE THE POPULATION GAP (2026-09-22)

**Status: EVIDENCE ONLY.** No strategy, stop, target, partial, trigger, sizing or safeguard is
changed. No live table is written. This card widens the POPULATION Phase 1 measured against; it
does not choose a stop, target or partial — that is the operator's, under CHANGE_PROCESS.

---

## Read this before any analysis. Every card gets it verbatim (`ANALYSIS_CARD_PREAMBLE.md`)

**THE GOAL:** *Make EPs profitable: filter the universe on all the factors that matter, not just
a gap, so a small win rate is carried by winners large enough to give positive expectancy.* At a
~20% win rate with 1R losers, the average winner must exceed 4R just to break even. Win rate and
reward are ONE target, never two.

**Rank order:** RECALL (does it catch real EPs at all) → EXPECTED RETURN (mean and median, n on
every figure) → CAPTURE (of the move that was available) → THE TAIL (P3 — how many reach 4R+).

**Win rate is a SELECTION measure, not an entry/exit measure.** Ranking is on the tail first, per
`docs/methodology/analysis_standard.md` §THE STATISTIC.

⚖ THE LINE: strategy, entry/exit discipline, sizing, targets and safeguards are the operator's
sole authority. This card is evidence; it never flips anything.

---

## 🔴 THE ONE CORRECTION THIS CARD CARRIES FORWARD

Phase 1 (`docs/analysis/545_phase1_harvest_hole_2026-09-22.md`) measured its grid against
**`era_c`** (2R partial, breakeven at partial) because the design doc calls it "live". **It is
not.** Prod flipped to **`era_d`** on 2026-09-06 (8R partial, price-armed breakeven at 3R).
Phase 1's own correction re-measured its headline against era_d and found the live ladder settles
5 names ≥3R on the 267-campaign population, not 0.

**Every "live" number in this card uses `era_d`.** Where an era_c number is quoted (the design
doc's "7 per 57" pass-bar reference, and the literal `_623_replay_out.tsv` group-by the design
doc's own text asks for) it is labelled **RETIRED**, and a fresh era_d version sits beside it.

---

## The decision this serves

Phase 1's own limit, carried unchanged from the design doc §5.1: a stop/harvest verdict on the
267-campaign alert population rests on 4–13 tail names because everything the `stop_too_wide`
rule refused, everything before 05-11, everything the scan skipped before it became an alert, and
every name after 08-28 has NO bars in any replay capture. This card is the $0 build that closes
that gap (design doc §7 Phase 2), so any later stop/harvest verdict is a sweep with a stated
population, not 4–13 names.

**What would change the read:** a refused-population cell or a skip-bucket that clears the
pre-stated pass bar (n≥10 replayable, ≥3R count per 100 entries beats the admitted reference) is
a candidate for the forward gate (#482); one that does not is recorded as evidence against, not
silently dropped.

---

## Method and population

**Five source populations, each named, none pooled:**

| label | rows | window | source |
|---|---|---|---|
| **REFUSALS** | 16 magna53 `stop_too_wide` refusals (deduped from 28 raw `mi_live_trades` rows; 12 dropped as the deprecated `9m_day2` strategy, `analysis_standard.md` §2; 0 collapsed as true (ticker,date) duplicates — every row was already distinct) | 2026-04-23 → 2026-09-08 | `mi_live_trades` live query, 2026-09-22 (§ dedupe probe below) |
| **P-REPLAY reference** | the 267-campaign, era_c-admission population Phase 1 built (142 admitted on THIS run — see note below) | 2026-05-11 → 2026-08-28 | `scripts/probes/_545_phase1_harvest_sweep.py::load_all` / `walk_alerts`, reused unmodified |
| **POST-0828** | 17 new live-source `mi_ep_alerts` campaigns (18 pulled 2026-09-03 → 2026-09-22; the 09-22 row, ONON, is the live/incomplete session and excluded) | 2026-09-03 → 2026-09-21 | `mi_ep_alerts` live query, 2026-09-22 |
| **P-623 skip buckets** | 3,458 `mi_ep_scan_log` ticker-days (the full scan-candidate universe, admitted + rejected), walked once already under era_c (`_623_replay_out.tsv`, RETIRED) and re-walked here under era_d / 0.5×ADR-on-era_d | scan population **2026-06-08 → 2026-09-03** (unchanged from #623's own capture); this card's re-walk horizon **2026-09-21** | `scripts/probes/_623_replay.py`'s own loaders, reused unmodified; no new fetch |
| CHPT 2026-09-03 | confirmed **NOT present in `mi_ep_alerts` under any `source`** (direct query, 0 rows) | — | never reached alert level — a scan-level miss (`filter:mcap_too_small`), same bucket TYPE as the P-623 skip population, not the alert-refusal population |

**Every campaign is walked on the LIVE code paths** (`ep_replay.py`: `validate_orb_entry`,
`stop_limit_buy_price`, `profit_target_r_per_share`, `seed_exit_state` /
`apply_daily_exit_step`), never a re-implementation — same fidelity contract Phase 1 used.
Horizon for REFUSALS/POST-0828/P-623-refresh: **2026-09-21** (the most recent complete ET
session; 2026-09-22 is live/incomplete and excluded, same discipline `_623_replay.py` uses for
its own capture day). This is LATER than Phase 1's 2026-08-31 horizon — stated, not silent; it
does not change Phase 1's own numbers, which this card does not re-run.

**The dedupe probe** (design doc §5.1's own SQL, run read-only against prod):
```
SELECT ticker, alert_date, signal_type, account_mode, COUNT(*) FROM mi_live_trades
WHERE skip_reason LIKE 'setup:stop_too_wide%' GROUP BY 1,2,3,4 ORDER BY 2;
```
**28 rows** (not 27 — one more than the design doc's 08-17 snapshot: ROIV 2026-09-08, refused
after the design doc was written). Split: **16 magna53** (10 paper, 6 live) + **12 `9m_day2`**
(deprecated, dropped per `analysis_standard.md` §2). **0 collapsed as duplicates** — every
(ticker, alert_date) pair among the 16 is already distinct; the design doc's "dedupe" concern
did not materialize for this population.

**Of the 16 magna53 names, 8 already have bars captured in `scripts/ep_replay_data/`** (within
the 05-11→08-28 P-REPLAY window: AIP, GO, PONY, CORT, AEVA, ATRO, HTFL, BULL — confirmed against
`docs/analysis/stopwide_replay_era_c_2026-09-05.txt`'s own "8 present" count). **The other 8**
(pre-05-11 or post-08-28) needed a fetch: **TLRY, WST, WKC, BAND, TTMI, EVER, STRL, ROIV** — the
same 4 the design doc names (BAND, STRL, EVER, TTMI) plus 4 more the dedupe surfaced (TLRY, WST,
WKC, ROIV).

**What was fetched, and its cost — $0, stated explicitly:**
- **Day-0 SIP 1-minute bars**, Alpaca (Algo Trader Plus subscription, same endpoint/method as
  `_623_fetch_bars.py`): 8 ticker-days, **5 requests, 3,084 bars, $0**
  (`scripts/probes/_545p2_fetch_bars.py` → `_545p2_bars.psv.gz`). Nothing else needed a paid
  fetch.
- **Daily bars** for those same 8 tickers (2026-01-01 → today): read-only `mi_daily_closes`
  query, $0, 1,440 rows.
- **The 17 POST-0828 campaigns' day-0 minute bars**: already in `mi_intraday_bars` (real-time
  capture) — **no Alpaca fetch needed**, read-only query, $0, 6,562 rows covering all 17 (373–391
  bars each, full RTH coverage).
- **Daily bars for the 17 POST-0828 tickers**: read-only `mi_daily_closes` query, $0, 3,231 rows.
- **P-623 skip-bucket re-walk**: **zero new I/O** — reuses `_623_bars.psv.gz` /
  `_623_have_minute_bars_out.txt` / `_623_daily_bars_out.txt`, already in the repo from the
  06-08→09-03 capture.
- **Nothing in this card cost money beyond the 5 Alpaca requests above**, and nothing would have
  — every other read was a `psql` SELECT against prod (read-only) or a local file.

**The one code change** (`scripts/ep_replay.py`): `walk_campaign(bypass_stop_too_wide=True)`.
The REFUSALS population is, by definition, every campaign `validate_orb_entry` refused for
`SETUP_STOP_TOO_WIDE` — that check runs BEFORE `rs.stop_mode` is applied, so no stop-basis choice
can ever answer "what would this have done under a different stop" without walking past it.
Scoped to that ONE reason (a zero-range ORB still refuses, even with the flag); every row's
**original** gate verdict is recorded in `out["gate_skip"]`, bypassed or not — never silent.
2 new tests (`tests/test_ep_replay.py`), mutation-proof (default-path vs bypass-path both
asserted; the zero-range exclusion asserted directly). `python scripts/ep_replay.py validate` —
byte-identical before/after (100%/100%/97%/83%, matching the 2026-09-01 floors). Full suite
`tests/ -k "ep_replay or 545"`: **82/82 pass** (80 pre-existing + 2 new).

**Admission is NOT re-derived for REFUSALS or POST-0828** — unlike P-REPLAY's 267, which the
design doc re-scores under today's admission stack because their original alerts ran under
OLDER rules. REFUSALS already passed admission historically (they reached order preparation,
refused only at the entry-mechanics gate); POST-0828 alerts were generated by the CURRENT
alerting pipeline days-to-weeks ago, not months. Stated as a limit, not guessed around.

**A live discrepancy, noted and NOT re-derived by hand:** re-running Phase 1's own
`load_all()` today (several hours after Phase 1's run) admits **142 of 267**, not 145 — 3 rows
shifted into the float-band-straddle abstain bucket between the two runs. `reject=81` is
unchanged. This points at a live input (float data) the admission scorer reads fresh each call,
not a static capture — outside this card's scope to chase, and immaterial below (a <3% shift in
the reference denominator, and every REFUSALS cell fails the n≥10 bar regardless).

**(B)'s daily bars are capped at 2026-09-01** — it reuses Phase 1's own `_pull2_out.txt` capture
unmodified, whose `DAILY` section ends there. This card's `LAST_SETTLED=2026-09-21` has **no
effect on (B)**: nothing in it has a bar past 09-01 to walk into, which is exactly why (B)'s
`era_d_stop_ladder` row (65 settled, 5 ≥3R, sum +12.1) matches Phase 1's own era_d-correction
number to the decimal. The 8 REFUSALS names already present in `scripts/ep_replay_data/` ride
the same 09-01 cap — checked directly: none of them (AIP, GO, PONY, BULL never enter; CORT,
AEVA, ATRO, HTFL always settle) reaches `open_at_horizon` in any of the 9 cells, so the cap has
no effect on (A) either. Only the 8 FETCHED refusal names' daily bars (pulled fresh today,
through 2026-09-21) actually use the extended horizon — which is why BAND is the only REFUSALS
name that shows an open mark (under `hard`, §A).

**ATR14 fidelity check** (advisor-requested, and corrected after a first pass mislabelled the
comparison): the harness's `atr14_abs()` (Wilder true range off stored daily bars) was first
compared directly to the number printed after "1.5x ATR $" in each historical `skip_reason`, and
read as an ATR-vs-ATR disagreement of 17–34%. **That comparison is wrong** — the printed number
is `1.5x ATR $Y`, not `ATR $Y`, and `live_Y ÷ (1.5 × harness_atr)` is the correct check. Two
distinct, clean groups fall out:

- **The 9 comparable refusals from 2026-05-13 onward** (AIP, GO, PONY, CORT, AEVA, ATRO, HTFL,
  BULL, ROIV): ratio **0.998–1.009** — essentially exact agreement. The live-logged number IS the
  1.5×ATR threshold, built from the SAME underlying ATR the harness independently computes.
- **All 6 pre-2026-05-14 refusals** (WST, WKC, TTMI, BAND, STRL, EVER): ratio **0.510–0.568** —
  a real, consistent divergence, not noise. **STRL's own ratio (0.553) matches
  `filters.py::compute_atr_14`'s own already-documented "canonical miss" almost to the decimal**
  (its docstring: close-only ATR $13.55 vs Wilder true range $24.52 → 13.55 ÷ 24.52 = 0.553) —
  the live gate was computing ATR a different, since-superseded way for this whole early window
  (`mi_daily_closes` was "backfilled 2026-04-25" per the same docstring; the fix appears to be in
  place by 05-13, consistent with the clean split above).
- TLRY's skip text uses a wholly different rule (`order_manager.py:7537`'s 15%-stop-distance
  check, not the 1.5×ATR gate this bypass targets) and is not ATR-comparable at all.

**The load-bearing fact this surfaces: for 5 of the 6 pre-05-14 names — WST, TTMI, BAND, STRL,
EVER — the (corrected, harness) ATR is now large enough that their own ORB range no longer
exceeds 1.5×ATR at all; today's gate would not refuse them.** `WKC`'s ORB range ($2.70) stays
wide enough to still trip the gate even at the corrected (larger) ATR — it shares the SAME
computation gap as the other 5, it just doesn't flip its verdict. **Only 10 of the 16 — WKC,
AIP, GO, CORT, AEVA, ATRO, HTFL, BULL, ROIV, TLRY — would still be refused under the rule we
actually run today**; the other 6 (WST, TTMI, BAND, STRL, EVER, PONY) would already pass it, no
bypass needed. **BAND — the single largest contributor to every ≥3R count in (A) below — is one
of the 6.** This is a population-composition fact (what fraction of "the 16" the current
1.5×ATR gate would even still touch), not a word about widening it. None of it changes any
entry/stop/target math below: `bypass_stop_too_wide` walks every one of the 16 regardless, and
the 0.5×ADR stop uses `adr20_pct()` (a %-range calculation, never ATR) — the divergence never
reaches a replayed number, only the informational `gate_skip` field.

---

## (A) The 16 refusals, bypassed — 9 cells, era_d framing

3 stop bases (`era_d_stop` = the LIVE stop entry−2R; `orb_low`; `adr_0.5` = 0.5×ADR20) × 3
post-partial runners (`ladder` = era_d's own SMA10/20 trail; `t3`; `hard`), all built from
`RULESETS["era_d"]` (8R partial, breakeven armed at +3R price) so `era_d_stop_ladder` **is**
today's live rule, unmodified.

| cell | entered | settled n / ≥3R / ≥5R / p90 / sum | marks (n / sum) | settled+marks ≥3R |
|---|---:|---|---|---:|
| era_d_stop_ladder | 9 | 9 / **1** / 0 / +1.64 / +4.8 | 0 / +0.0 | 1 |
| era_d_stop_t3 | 9 | 9 / **1** / 0 / +1.64 / +3.5 | 0 / +0.0 | 1 |
| era_d_stop_hard | 9 | 8 / 0 / 0 / +0.75 / −0.6 | 1 / +4.4 | 1 |
| orb_low_ladder | 9 | 9 / **2** / 1 / +3.28 / +10.4 | 0 / +0.0 | 2 |
| orb_low_t3 | 9 | 9 / **2** / 1 / +3.28 / +8.2 | 0 / +0.0 | 2 |
| orb_low_hard | 9 | 8 / 1 / 0 / +1.50 / +0.3 | 1 / +8.6 | 2 |
| adr_0.5_ladder | 9 | 5 / **2** / 2 / +18.00 / +23.1 | 0 / +0.0 | 2 |
| adr_0.5_t3 | 9 | 5 / **2** / 2 / +15.76 / +20.8 | 0 / +0.0 | 2 |
| adr_0.5_hard | 9 | 4 / 1 / 1 / +8.23 / +5.1 | 1 / +17.0 | 2 |

**Only 9 of 16 refusals ever enter, under ANY stop basis** (identical set: TLRY, TTMI, AIP, GO,
PONY, BULL never crossed the ORB high at all that day — a fact independent of the
`stop_too_wide` gate; the harness reports this honestly rather than fabricating a fill). WKC
abstains on every cell (`entry_window_gaps:1_of_29` — a single missing minute bar in the fetched
window). At the 0.5×ADR stop, 4 more names (STRL, EVER, CORT, ATRO) abstain
(`day0_fill_bar_straddles_stop` — the 1-minute grain cannot order the stop and target inside one
bar), leaving only **5 entered names settled**.

**≥3R names, every cell: BAND and HTFL only** (plus ROIV, negative, never ≥3R). **Drop-best
(removing BAND, checked on settled+marks per cell) collapses the 3 `era_d_stop_*` cells to 0
≥3R and the 6 `orb_low_*`/`adr_0.5_*` cells to 1 (HTFL, which clears ≥3R on its own only under
the tighter stops)** — **two names carry this entire population's tail, at n this small that is
expected, not a finding.** ⚠ **BAND is one of the 6 names today's 1.5×ATR gate would not even
refuse** (§ Method)
— it does not need a bypass or a different stop basis to be tradeable today, it needs nothing at
all. **HTFL is genuinely still refused under the current gate** — it is the one name in this
whole population where "what would a different stop have done" is the real question the
`stop_too_wide` rule is actually gating. Of the 9 entered names, 4 (WST, BAND, STRL, EVER) would
pass today's gate outright; 5 (CORT, AEVA, ATRO, HTFL, ROIV) are genuinely still refused.

**Submit time defaulted to 09:31 for all 16** (the standard default `walk_campaign` uses); 9 of
the 16 have an `mi_ep_alerts` record with a `detected_at_et`, mostly ≤09:31 except GO's own
09:35:00 second-tick row — not wired into submit for this card. A LATER submit can only shrink
the entry window, so this cannot manufacture an entry the wider default window did not already
find; it is stated as a limitation, not corrected, because it cannot flip a `no_entry` verdict to
an entry.

---

## (B) The reference: P-REPLAY admitted, SAME 9 cells, era_d framing

| cell | entered | settled n / ≥3R / ≥5R / p90 / sum | ≥3R per 100 entries | ≥3R per 100 settled |
|---|---:|---|---:|---:|
| era_d_stop_ladder | 69 | 65 / 5 / 1 / +2.58 / +12.1 | 7.2 | **7.7** |
| era_d_stop_t3 | 69 | 65 / 8 / 3 / +3.29 / +20.5 | 11.6 | 12.3 |
| era_d_stop_hard | 69 | 61 / 0 / 0 / +1.12 / −16.2 | 0.0 | 0.0 |
| orb_low_ladder | 69 | 60 / 10 / 6 / +4.08 / +28.7 | 14.5 | 16.7 |
| orb_low_t3 | 69 | 60 / 12 / 8 / +5.15 / +48.2 | 17.4 | 20.0 |
| orb_low_hard | 69 | 58 / 4 / 1 / +2.00 / −8.3 | 5.8 | 6.9 |
| adr_0.5_ladder | 69 | 58 / 9 / 7 / +5.06 / +26.1 | 13.0 | **15.5** |
| adr_0.5_t3 | 69 | 57 / 11 / 8 / +5.53 / +33.7 | 15.9 | 19.3 |
| adr_0.5_hard | 69 | 56 / 4 / 3 / +1.94 / −5.7 | 5.8 | 7.1 |

(`era_d_stop_ladder` here — 65 settled, 5 ≥3R, sum +12.1 — matches Phase 1's own
era_d-correction number exactly, on the paired-65 cut: agreement check passed. **The two bold
rows (7.7 and 15.5, per 100 settled) are the "7 per 57"-style reference (D) is compared
against** — the design doc's own phrasing was itself per-settled, not per-entered.)

---

## (C) POST-0828: 17 new campaigns, era_d (their own live era)

18 pulled, 1 (ONON, 2026-09-22) excluded as the live/incomplete session.

| ticker | date | tier | status | R / mark |
|---|---|---|---|---|
| AGX | 09-03 | HIGH | abstain (entry_window_gaps) | — |
| HOOD | 09-03 | HIGH | no_entry (triggered above limit) | — |
| SNOW | 09-03 | HIGH | no_entry (never crossed ORB high) | — |
| ALAB | 09-04 | MODERATE | no_trade (window_out_of_orb) | — |
| ERO | 09-08 | MODERATE | no_trade (window_out_of_orb) | — |
| IONQ | 09-08 | HIGH | settled | −1.00R |
| PHVS | 09-08 | HIGH | settled | −1.00R |
| QCOM | 09-08 | HIGH | settled | −1.00R |
| ROIV | 09-08 | HIGH | settled | −0.36R |
| SEI | 09-08 | HIGH | settled | 0.00R |
| DFTX | 09-14 | HIGH | settled | −1.00R |
| SRRK | 09-14 | HIGH | no_entry (never crossed ORB high) | — |
| CIFR | 09-16 | MODERATE | no_trade (window_out_of_orb) | — |
| GNRC | 09-17 | HIGH | no_entry (never crossed ORB high) | — |
| VICR | 09-17 | HIGH | open (mark) | +1.10R |
| INTC | 09-21 | MODERATE | open (mark) | +0.41R |
| MSTR | 09-21 | none | open (mark) | +0.27R |

**Settled: n=6, 0 ≥3R, sum −4.4R. Open marks: n=3, sum +1.8R.** No September name has settled
≥3R yet — too few and too fresh to say anything about the tail (n=6 settled, `analysis_standard.md`
§5: "under ~10, state it and draw no conclusion").

**CHPT 2026-09-03 does NOT enter P-REPLAY via this pull** — confirmed by a direct query
(`SELECT ... FROM mi_ep_alerts WHERE ticker='CHPT'` → 0 rows, any `source`). It never became an
alert; it is a scan-level miss (`mcap_too_small`), the SAME population type as the P-623 skip
buckets below, not the alert-refusal population this half of Phase 2 covers. Re-pulling
`mi_ep_alerts` cannot surface a name that was never written to that table.

---

## (D) The P-623 scan-level skip buckets — including CHPT

**CHPT 2026-09-03 IS in this population** (P-623's scan log, unlike P-REPLAY's alert log — §C
above already established it never reached `mi_ep_alerts`). Pulled directly from this card's own
re-walk: **entered=True, entry 7.08, stop 6.34 (era_d), still `open_at_horizon` at the
2026-09-21 cut — mark +2.69R under the live stack, +11.60R under a 0.5×ADR stop.** This is the
one concrete, currently-live answer the design doc's "so CHPT enters P-REPLAY" ask ends up with:
CHPT is not a settled return (it is a mark, and marks can round-trip — same caveat every open
number in this program carries), but it is a real, entered, currently-winning position in this
population, at a size the tail objective cares about. A second CHPT row exists the next day
(2026-09-04, a fresh scan-log tick, `filter:universe_below_gap_floor`): abstains under era_d,
settles +0.19R under 0.5×ADR — a different, much smaller campaign, not double-counted with the
09-03 mark.

**Part 1 — literal, as the design doc's text asks: a group-by straight from the existing
`_623_replay_out.tsv`.** This is **era_c, RETIRED 2026-09-06** — quoted only because the design
doc's own words ask for exactly this read, and labelled so it is never cited as current.

| bucket (era_c, RETIRED) | n settled | ≥3R | ≥5R | sum | ≥3R per 100 settled |
|---|---:|---:|---:|---:|---:|
| P-623's OWN admitted (ever_scored) reference | 264 | 6 | 4 | +43.8 | 2.3 |
| outside_top20 | 139 | 6 | 2 | +68.0 | 4.3 |
| score_below_50 | 118 | 5 | 4 | +36.9 | 4.2 |
| session_rvol_low | 98 | 4 | 2 | +15.1 | 4.1 |
| mcap_low | 96 | 2 | 1 | +3.1 | 2.1 |
| adv_low | 79 | 2 | 0 | −10.2 | 2.5 |

**Part 2 — THE CORRECTION: the same #623 population (3,458 scan-log ticker-days, zero new
fetch), re-walked under `era_d` (LIVE) and 0.5×ADR-on-`era_d`.** **25 near-zero-stop rows
excluded under era_d** (the same `|entry−stop|/entry < 0.5%` screen P-623's own doc applies — 25,
not the 13 P-623's original 09-04/era_c read found; a different partial/breakeven shape and a
longer horizon change WHICH trades settle, not the stop formula, which is unchanged from era_c);
**0 excluded under 0.5×ADR** (checked directly against the same screen — the 0.5×ADR stop is
still a dollar distance, `0.5 × ADR20$`, so it CAN land near-zero if a name's ADR% itself is
under ~1%; none of the 1,531 settled rows in this cell happened to have one that low).

🔴 **THE PASS BAR NAMES A SPECIFIC REFERENCE — "beats the admitted cohort's — 7 per 57 under
0.5×ADR" — and that number is (B)'s, not P-623's own.** (B)'s `adr_0.5_ladder`, era_d: **9 ≥3R /
58 settled = 15.5 per 100 settled**. (B)'s `era_d_stop_ladder` (the plain live stop): **5 ≥3R /
65 settled = 7.7 per 100 settled**. A first pass of this card compared each bucket only to
P-623's own, much looser `ever_scored` reference (2.3–11.4 per 100) and reported two buckets as
clearing — **wrong reference, corrected below.** P-623's own reference is kept, labelled, for
internal context only.

| bucket | ≥3R/100 settled (era_d) | vs (B) live-stop ref **7.7** | vs P-623's own ref (6.2) | ≥3R/100 settled (0.5×ADR) | vs (B) 0.5×ADR ref **15.5** | vs P-623's own ref (11.4) |
|---|---:|---|---|---:|---|---|
| outside_top20 | 12.3 | beats | beats | 11.7 | does not beat | beats (marginal) |
| score_below_50 | 8.0 | beats (marginal, +0.3) | beats | 13.1 | does not beat | beats |
| session_rvol_low | 5.2 | does not beat | does not beat | 5.3 | does not beat | does not beat |
| mcap_low | 6.5 | does not beat | beats (marginal) | 9.7 | does not beat | does not beat |
| adv_low | 3.8 | does not beat | does not beat | 8.0 | does not beat | does not beat |

**Against the reference the pass bar actually names: nothing clears the 0.5×ADR comparison.**
Only `score_below_50` clears the plain live-stop comparison, and by 0.3 points — inside rounding
noise for a bucket this size, not a clean beat.

⚠ **`outside_top20` is a RETIRED filter tag — it is not a candidate for anything, regardless of
its numbers.** Checked directly (`analysis_standard.md` §3b's own warning: "Dead strategies are
not evidence... check before citing any signal_type" applies here to a dead FILTER the same way):
of 138 `outside_top20` rows in the era_d re-walk, **the last scan_date is 2026-08-07 — zero rows
after 2026-08-22**, the date the top-20-by-gap shortlist was replaced by the three-term
pre-score. There is no live mechanism today that still produces this rejection reason, so there
is nothing to forward-gate — its historical tail is a fact about a rule we no longer run, on
exactly the same footing as (D) Part 1's era_c numbers: retired, informative, not actionable.

**`score_below_50` remains an active tag** (scan dates through 2026-09-04, inside the current
era) and is the only bucket with a real, if marginal, positive read against the live-stop
reference — but it fails against the tighter 0.5×ADR reference, which is the reference the pass
bar names. **No bucket here is a clean candidate under the stated bar.**

---

## Which cells clear the pass bar — applied as written, no softening

**Pass bar (pre-stated, §7): n ≥ 10 replayable refusals before ANY word about 1.5×.**

**Every one of the 9 REFUSALS cells in (A) has 9 or 5 replayable names (settled+marks) — below
10 in all nine.** Per the rule: **say so and write nothing about widening the stop.** No cell in
(A) is a candidate; none is rejected either — the population is simply too small to judge, and
is reported as evidence, not silently dropped. (The 2 ≥3R names that DO appear — BAND, HTFL —
repeat across every cell and are drop-best-fragile, §A above; a direction, never a verdict.)

**The P-623 skip-bucket read in (D) DOES clear n≥10** (75–139 per bucket) and, against the
reference the pass bar actually names (B), **nothing clears at 0.5×ADR; `score_below_50`
marginally clears at the plain live stop; `outside_top20` is numerically the strongest but is a
RETIRED filter tag with no live mechanism to gate.**

---

## What this does not answer

- **Whether the 1.5×ATR gate (`stop_too_wide`) should widen, size-down, or stay.** n=9 (or 5
  under 0.5×ADR) replayable refusals is below the pre-stated n≥10 floor — by the pass bar's own
  rule, no word is said about it. The population gap this card set out to close is now
  MEASURED, not guessed — but it measured out to "too small to judge," which is itself the
  answer to "is there a sweep-scale population here": no, not among magna53's own historical
  refusals.
- **Why 6 of the 9 fetched refusal names never crossed the ORB high under the fetched bars.**
  Reported as `never_crossed_orb_high` (an honest, non-fabricated result), not investigated
  further — could be gap-fade, a data-timing edge, or genuinely no breakout that day.
- **TLRY's own admission gate** (`order_manager.py:7537`'s 15%-stop-distance rule, not the
  1.5×ATR gate this bypass targets) — why a magna53-tagged row hit a differently-worded check is
  not chased; TLRY never enters under any cell regardless (never crossed ORB high).
- **The exact code change that fixed the pre-05-13 ATR computation** is not located — the STRL
  docstring names the symptom (close-only vs Wilder true range) and this card confirms the split
  date empirically (clean agreement from 05-13, clean divergence before), but does not find the
  commit. Immaterial to any number here (§ Method).
- **Whether `score_below_50`'s marginal live-stop beat (8.0 vs 7.7 per 100) survives re-scoring
  under the SAME full admission stack (B) uses**, rather than being read off `nearest_filter_reason`
  text directly — not attempted; the margin is inside rounding noise regardless.
- **Whether the current admission stack's REAL score floor (65 under separation scoring, not the
  "50" the pre-08-22 `score_below_50` tag text still shows) changes which rows belong in that
  bucket for dates after 2026-08-22** — not re-derived; the bucket is built from the scan log's
  own logged text, which may itself be stale for post-08-22 rows.
- **Portfolio interaction, fill reality, and the September cohort's true tail** — same limits
  Phase 1 and the design doc state: every campaign priced alone; POST-0828 has 6 settled names,
  far too few to judge (§C); the harness fills at the ORB high, real fills differ.
- **Re-scoring REFUSALS or POST-0828 under today's admission stack** — not attempted (§ Method);
  a REFUSALS name that would also fail today's admission scorer (separately from the
  `stop_too_wide` entry gate) is not distinguished from one that would pass.
- **Whether CHPT's mark survives to settlement.** CHPT (§D) is an OPEN position at the 2026-09-21
  cut, up +2.69R (era_d) / +11.60R (0.5×ADR) — a mark, not a return; it can round-trip like every
  other open number in this program. Whether other CHPT-class scan-level names beyond this one
  belong in a future capture is not built here either.

---

## ⚖ THE LINE

Nothing here changes a stop, target, partial, trigger, re-entry rule, sizing, admission threshold
or any live table. No prod write, no mutation, no job run — every DB access was a read-only
SELECT. The only paid step (5 Alpaca SIP requests, $0 under the existing subscription) is
disclosed above; nothing else cost anything. The candidate buckets in (D) and the "too small to
judge" verdict in (A) are evidence for the operator's own decision under CHANGE_PROCESS, the
#151 harness and his sign-off — never a recommendation.

---
*Sources: `scripts/probes/_545p2_refusal_replay.py` → `_545p2_refusal_replay_out.txt` (every
number in (A)/(B)/(C)) and `_545p2_refusal_replay.tsv` (144 per-cell×campaign rows).
`scripts/probes/_545p2_623_era_walk.py` → `_545p2_623_era_walk_out.txt` (every number in (D))
and `_545p2_623_era_walk.tsv` (6,862 rows). `scripts/probes/_545p2_fetch_bars.py` →
`_545p2_bars.psv.gz` (the 8-ticker-day Alpaca fetch). `scripts/probes/_545p2_common.py` (the
psql-capture parser shared by both). `scripts/probes/_545p2_q1_out.txt` / `_545p2_q2_out.txt`
(the read-only prod pulls: refusal alerts, 8-ticker daily bars, post-0828 alerts, post-0828
minute+daily bars, regime). Code: `scripts/ep_replay.py`
(`walk_campaign(bypass_stop_too_wide=...)`). Tests: `tests/test_ep_replay.py` (82/82 pass).
Reused unmodified: `scripts/probes/_545_phase1_harvest_sweep.py` (`load_all`/`walk_alerts`,
population B), `scripts/probes/_623_replay.py` (loaders, population D),
`scripts/probes/_623_replay_out.tsv` (D Part 1), `scripts/ep_replay_data/` (P-REPLAY bars/daily
for the 8 already-present refusal names), `scripts/probes/_562bf_minute.tsv.gz` (post-day0
minutes). Prior work, cited not re-derived: `docs/design/545_entry_exit_program_2026-09-05.md`
§5.1, §7; `docs/analysis/545_phase1_harvest_hole_2026-09-22.md`;
`docs/analysis/stopwide_replay_era_c_2026-09-05.txt`;
`docs/methodology/analysis_standard.md`, `ANALYSIS_CARD_PREAMBLE.md`.
`scripts/live_rules.py` output, 2026-09-22 (Phase 1's run; not re-run by this card).
Related: PLAN #545 · #623 · #482.*
