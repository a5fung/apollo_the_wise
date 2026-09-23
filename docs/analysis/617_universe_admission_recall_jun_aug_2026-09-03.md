# #617 Step 1 — Is universe admission still turning away names our own bracket would have paid ≥4R on? Jun–Aug 2026 (2026-09-03)

**THE ANSWER: No. Across every session from 2026-06-01 to 2026-08-31, no universe filter excluded a
single name that our own bracket would have paid ≥4R on in the 7–9% gap band where the fixture's
debt lives (0 of 188 settled walks), and the D-1 volume floor and the silent no-row set are clean
too (0 of 27 and 0 of 13). The gap floor is NOT the offender in Jun–Aug — and 65% of the 8–9% band
touched ≥9% inside 09:30–09:44 anyway (24% held it for 3 consecutive minutes, the stricter bar the
real-time catch path applies), a cross today's real-time gap authority (live 08-27) re-checks on
the intraday price, not the open. The
only ≥4R names below the floor sit at 5–7% gaps — eleven of them on five days: six gold/silver
miners on two sector days (08-05: NEM, AEM, AGI, KGC, WPM; 08-19: CDE), three earnings gaps on
07-30 (ETN, BBVA, UMAC), SAP 07-24 and WYFI 06-15 — in a band that pays −0.20R to −0.30R per name
on average (−229R across 968 settled walks to recover the eleven) and that nobody has proposed
admitting. The admitted pool itself, walked by the same code, paid 0 ≥4R on 68 settled trades. The
tail is being lost after admission, not at it (the Phase 2 finding, now confirmed from the other
side).**

**⚖ THE LINE — MEASUREMENT ONLY. Nothing was flipped: no admission gate, floor, score bar, stop,
target, sizing or safeguard. `MIN_GAP_PCT` stays 9.0. Any change is CHANGE_PROCESS + backtest +
operator sign-off (Step 3 of #617, his alone).**

---

## 1. The decision this serves, and what would change it

**Decision:** whether Step 3 of #617 (an operator-only `MIN_GAP_PCT` or D-1 floor change) has a
recall case behind it on the operator's own measure — *"did it turn away real EPs, those that
would've made us 4R+ or, to a lesser extent, those that would've made us positive return at all"*
(2026-09-03, ruling on #593) — and whether the offender, if any, is still the gap floor or has moved.

**What would change the decision:** any band whose never-admitted names, walked through the CURRENT
bracket, produce ≥4R at a rate above the admitted pool's, at a volume cost (P14) the five slots and
the grading budget can carry. **What would make this document wrong:** (a) the walker mis-pricing
a fill — guarded by `ep_replay.py validate` = PASS before any number was read; (b) a phantom gap
from a split-adjusted capture read as a real one — guarded by a split-adjusted Alpaca pass (§6);
(c) the grading/score layer, which is NOT replayed, admitting fewer of these names than the walk
assumes — so every recall number here is an UPPER bound on what a filter cost; (d) an incomplete
bar fetch read as "no entry" — the first fetch WAS truncated by the SDK's total-item cap and every
number was re-derived on the complete one (§7 item 0); (e) too few sessions — 64, stated on every
row.

## 2. Method / population — read before any number

**Population:** every (ticker, session) in `mi_daily_closes` from 2026-06-01 to 2026-08-31 whose
session OPEN gapped ≥5% over the strictly-prior close, or whose HIGH cleared +9% — 42,081 rows,
captured once read-only on 2026-09-03 (`scripts/probes/_617_population.sql` →
`_617_population_out.txt`, with every `mi_ep_scan_log` row of the window (32,559), the 196
live-source `mi_ep_alerts`, 135 magna53 `mi_live_trades`, `mi_security_types`, a scan-day census
(64 sessions, none missing) and stored minute-bar coverage). **Attribution** mirrors the live
universe loop's ORDER (`ep_detector.run_ep_scan` ~L3074-3150): ticker shape → security type (P2.0b)
→ `MIN_PREV_CLOSE` $5 → `MIN_PREV_DAY_VOLUME` 50k → gap floor (10.0 until 08-18, 9.0 from 08-19).
A scan_log row is the ground truth for "entered the funnel"; the open-gap band is the proxy for
why a row-less name never did (`_617_classify.py`). **Not re-reviewed:** anything with a downstream
scan_log stage — shortlist cap, extension, quality filters, grading, score bar, post-grade filters —
which #545 Phase 2 (`545p2_missed_ep_tail_read_2026-09-02.md`) already measured. Names whose open
was <5% but whose high crossed 9% (5,055 rows) are intraday runs, not gaps: counted, not walked.

**Replay set:** the 3,473 never-admitted pairs (no funnel row, or only a #605 below-floor capture
row), 1,738 tickers. Day-0 1-minute RTH bars + daily bars 04-15→09-02 fetched ONCE from Alpaca SIP,
`adjustment=raw`, inside the market container (`_617_fetch_bars.py` → `_617_bars.psv.gz`, 135
requests, 966k minute + 163k daily rows, $0 — covered by the existing subscription; nothing
written to any table). **Walker:** `scripts/ep_replay.walk_campaign` under rule-set `current`
(era C: entry−2R stop, +2R partial, breakeven at partial, 10:00 unfilled cancel;
`validate_orb_entry`, `stop_limit_buy_price`, `profit_target_r_per_share`, `apply_daily_exit_step`
— the live modules), `atr_14` passed so the stop-too-wide rule acts, detection assumed at
**09:31** (the most optimistic case for an excluded name; a 09:36 sensitivity is reported in §6).
Horizon 2026-09-02; open-at-horizon marks are reported as marks, never as R. **Denominator:** the
196 Jun–Aug alerts walked by the same harness (`scripts/ep_replay_data/campaigns_era_c.tsv`) —
walked at `max(09:31, detected_at)`, while the excluded sets are walked at 09:31 flat, so the
comparison FAVOURS the excluded sets; the conclusion's direction is robust to that, its size is not
like-for-like. Post-processing (`_617_replay.py`, `_617_post.py`) re-derived the two D-1 floors on
the RAW Alpaca prior close/volume — what the snapshot saw on the day — because `mi_daily_closes`
is rewritten split-ADJUSTED after a reverse split (§7). `scripts/live_rules.py --drift-only` run
first (`_617_live_rules_out.txt`): one unrelated stale doc-claim finding, not this scope.

**Units.** R = each walk's own stop distance under the current bracket (entry − stop). Gap % =
session open vs strictly-prior close unless "in-window": **touch** = the day's 09:30–09:44
minute-bar high vs the raw prior close (an upper bound on real-time admission); **sustain** = 3
consecutive minute CLOSES ≥ +9% inside that window — the `_sustain_ok` bar (`ep_rt_sustain_enabled`
ON since 08-02) that the real-time CATCH path (`_apply_rt_universe_overlay`, names the delayed
screen never showed) applies. For a name the delayed screen admits at ≥5%, today's admission is
the Pass-2 re-check of the 9% floor on the accepted real-time tick price under the Q1–Q4 quality
guards — no sustain — so **touch over-states and sustain under-states what that re-check sees;
the truth is between the two columns.** Era: floor 10.0 for 55 of the 64 sessions, 9.0 for 9;
real-time gap authority for the last 3 (08-27 flipped at 13:55 ET).

## 3. The per-filter table — recall AND base rate

Every row: names the filter kept out of the funnel, walked through OUR bracket. "Decided" = the
walk reached a verdict (settled, no-entry, or refused by the ORB rule); the rest abstained (§6).

| universe filter (Jun–Aug 2026) | excluded (n) | decided | settled | **≥4R** | ≥2R | any positive | sum R (settled) | mean R | what the ≥4R names are |
|---|---|---|---|---|---|---|---|---|---|
| **MIN_GAP_PCT — open gap 8–9%** (the fixture's band) | 111 | 88 | 56 | **0** | 2 | 22 (39%) | −13.4R | −0.24 | — (best: WHD +3.6R, OUST +3.0R, both 07-30 earnings) |
| MIN_GAP_PCT — open gap 7–8% | 246 | 196 | 132 | **0** | 6 | 56 (42%) | −29.4R | −0.22 | — |
| MIN_GAP_PCT — open gap 6–7% | 473 | 393 | 290 | **5** | 16 | 109 (38%) | −86.9R | −0.30 | NEM, AEM, AGI (08-05, gold miners); UMAC +8.4R and BBVA (07-30; BBVA on a 0.49% stop) |
| MIN_GAP_PCT — open gap 5–6% | 795 | 669 | 490 | **6** | 26 | 198 (40%) | −99.1R | −0.20 | SAP (07-24 earnings, +14.5R), KGC +8.8R and WPM (08-05), CDE (08-19), ETN (07-30), WYFI (06-15) |
| gap 9–10% under the old 10% floor (admitted since 08-19) | 60 | 45 | 22 | 0 | 0 | 7 (32%) | −11.3R | −0.51 | — (what the 08-19 change bought: nothing on this measure, n=22) |
| **MIN_PREV_CLOSE** (raw D-1 close < $5, open gap ≥9%) | 1,417 | 1,091 | 642 | **9** | 14 | 333 (52%) | +78.8R | +0.12 | 5 tick-bound (NEXR $0.33, AERT $0.57, LGCL $0.95, CYCU $0.34, RGNT $1.71 — stops of 2–8¢, one tick is 25–50% of R); 4 not: STAK $1.21 and LUNG $1.40 on 12¢ stops, DFNS $7 / JLHL $4 with 10–17% stops |
| **MIN_PREV_DAY_VOLUME** (raw D-1 volume < 50k, gap ≥9%) | 140 | 61 | 27 | **0** | 1 | 17 (63%) | −1.2R | −0.05 | — |
| silent: gap ≥9%, floors passed, NO row at all | 44 | 30 | 13 | **0** | 1 | 5 (38%) | −3.1R | −0.24 | — (40 of 44 touched ≥9% in-window, 24 sustained it: the delayed price, not a filter, kept them out; 2 rows after 08-27, both on the flip morning) |
| security type unclassified / no Alpaca daily | 187 | 0 | 0 | — | — | — | — | — | OTC symbols (…F, …Y) never on Alpaca — not tradeable, not a miss |
| **denominator — the ADMITTED pool (196 alerts), same walker** | 196 | 160 | 68 | **0** | 3 | 34 (50%) | −5.7R | −0.08 | — |

Reading it against the operator's two questions:
- **≥4R:** the 7–9% band, the D-1 volume floor and the silent set turned away **nothing**. The
  eleven ≥4R names below 7% are six sector-sympathy moves on two days (08-05: NEM, AEM, AGI, KGC,
  WPM; 08-19: CDE), three earnings gaps on one day (07-30: ETN, BBVA, UMAC), SAP and WYFI — the
  first six are shapes the catalyst grade, which is not replayed, is built to mark routine. The nine
  under `MIN_PREV_CLOSE` are penny stocks: five with R manufactured by 2–8¢ stops, four at $1–7 with
  10–17% stops; none is an EP anyone wants in a slot.
- **Any positive return:** every excluded gap band runs BELOW the admitted pool's 50% positive rate
  and its −0.08R mean (bands: −0.20R to −0.30R per settled name). Admitting the whole 5–9% band
  would have added −229R of settled walks across 968 names to recover eleven winners.

## 4. Is the gap floor STILL the offender — or has it moved?

- **Not in Jun–Aug, on either measure.** Under the current bracket the 7–9% band paid 0 ≥4R on
  188 settled walks; the fixture's April names (STRL, ASX, NBIS, HUT, IREN, SMTC, QCOM) have no
  June–August counterpart.
- **The floor's basis moved on 08-27 and that changes what "excluded" means.** 65% of the 8–9%
  band (72 of 111) and 41% of the 7–8% band (102 of 246) TOUCHED ≥9% inside 09:30–09:44; 24% and
  14% HELD it for 3 consecutive minutes. Since `ep_rt_gap_authoritative` went live, the 9% floor
  is re-checked on the real-time tick price, so a share of this band between those two columns is
  admitted today on the intraday cross — the open-basis fixture over-counts the live miss. Of the
  eleven ≥4R names below the floor, two touched ≥9% in-window (CDE, WYFI) and one held it (CDE).
- **No other universe filter has taken its place.** `MIN_PREV_DAY_VOLUME` and the security-type
  gate cost nothing measurable; `MIN_PREV_CLOSE` excludes the noisiest 1,417 names for nine
  penny-stock "winners" no real bracket could have collected at those prices and tick sizes.
- **Where the ≥4R tail went:** the admitted pool — 196 alerts — paid 0 ≥4R through the same walker
  (68 settled, 27 never crossed the ORB high, 65 refused by the ORB rule, 34 abstained). The loss is
  downstream of admission, which is Phase 2's conclusion reached from the excluded side.

## 5. P14 both directions — what admitting each band would COST, per session (64 sessions)

| band admitted in addition to today | extra names / session (gross) | net of names that held ≥9% 3 min in-window (conservative proxy for today's RT re-check; the touch basis nets out more) | est. extra alerts (at the adjacent 9–10% band's 5.3% conversion, n=8/150) | ≥4R gained (n settled) | settled R added |
|---|---|---|---|---|---|
| 8–9% | +1.7 | +1.3 | ~4 / quarter | 0 (n=56) | −13.4R |
| 7–9% | +5.6 | +4.6 | ~16 / quarter | 0 (n=188) | −42.8R |
| 6–9% | +13.0 | +11.3 | ~38 / quarter | 5 (n=478) | −129.7R |
| 5–9% | +25.4 | +23.2 | ~79 / quarter | 11 (n=968) | −228.8R |

- Today's funnel admits ~13 names/session at ≥9% (834 over 64 sessions on the first pass's
  adjusted-basis count, floors passed) and alerts on ~2/session (n=133 of those 834). Going to 7%
  adds 43% more names for zero ≥4R; going to 5% nearly triples the funnel for eleven, six of them
  one-sector-day sympathy moves.
- Grading budget: the shortlist is capped at 20 per tick — extra admissions displace, they do not
  only add — and his attention is the alert count, not the candidate count. Slots: five; the
  eleven ≥4R names cluster on five days (08-05 ×5, 07-30 ×3), so at most a few could have been
  held at once anyway.
- The gain side is an UPPER bound (grading not replayed); on the cost side the candidate volume is
  exact and the alert count is an estimate from the adjacent band.

## 6. Coverage and honesty — what could not be replayed

| set (raw D-1 basis) | n | artifact / OTC, no Alpaca data | no minute bars for that day | no 09:30 bar | entry-window gaps (09:31–10:00 incomplete) | same-bar stop+target / straddle | decided |
|---|---|---|---|---|---|---|---|
| gap 5–9% bands (4 sets) | 1,625 | 0 | 0 | 57 | 186 | 36 | 1,346 (83%) |
| 9–10% under the old floor | 60 | 0 | 0 | 3 | 12 | 0 | 45 (75%) |
| silent no-row | 44 | 0 | 0 | 4 | 9 | 1 | 30 (68%) |
| MIN_PREV_CLOSE | 1,417 | 0 | 0 | 174 | 125 | 27 | 1,091 (77%) |
| MIN_PREV_DAY_VOLUME | 140 | 0 | 1 | 70 | 6 | 2 | 61 (44%) |
| unclassified / OTC / phantom gap | 187 | 187 | — | — | — | — | 0 |
| **total** | **3,473** | **187** | **1** | **308** | **338** | **66** | **2,573 (74%)** |

- Every abstain is the harness refusing to fabricate: a missing 09:30 bar means no ORB (illiquid
  names that printed no trade in the first minute — the D-1 floors' own populations, by
  construction); a hole in the 09:31–10:00 minute stream means a cross cannot be proven absent.
  Not one number above was filled by a guess.
- **09:36 sensitivity** (first 5-minute scan tick instead of 09:31): the 7–9% band stays at 0 ≥4R
  (n=151 settled); the 6–7% band drops from 5 to 4 (n=218), 5–6% stays at 6 (n=385),
  `MIN_PREV_CLOSE` from 9 to 5, and one `MIN_PREV_DAY_VOLUME` name reaches ≥4R (n=27). Later
  detection can only move these counts down in the bands that matter.
- Two campaigns were open at the 09-02 horizon (both `MIN_PREV_CLOSE`: VFF mark +1.7R, USDE
  +2.6R) — marks, not R, and neither ≥4R.
- No fetch chunk failed; no prod table was written; `ep_replay.py validate` PASS (stop formula
  44/44, entry decision 100%, exit class 97%, realized R within 0.25R on 83%).

## 7. What turned out to be wrong — in the brief, and in my own first pass

0. **My first bar fetch was silently truncated** (caught by the advisor review): alpaca-py's
   `limit` is a TOTAL cap across pages, not a page size, and the multi-symbol response is ordered
   symbol-then-time, so `limit=10000` on 50-symbol minute chunks (~19,500 bars) returned nothing
   for the alphabetical tail of 55 of 99 chunks (554 zero-bar names in chunk tails vs 39 in heads).
   Re-fetched with `limit=None` (966k bars vs 769k); decided coverage rose from 60% to 74%; the
   7–9% band's zero held; the 5–7% band's ≥4R count moved 9 → 11 (UMAC, KGC added). Every table
   here is from the complete fetch; the truncated one is kept outside the repo, not cited.
1. **"7 excluded winners and nobody has looked since April"** — looked now: the same band, in
   the three months since, holds none, and most of it touches ≥9% in-window anyway (a quarter
   holds it 3 minutes) — which today's real-time re-check sees and the open does not. The debt is
   real on the fixture's open basis and April data;
   it is not a live leak in Jun–Aug.
2. **The live floor is not enforced on the open.** 46 of the 196 Jun–Aug alerts came from names
   whose OPEN gap was under 9% (13 under 5%, 14 at 8–9%; 7 more had no ≥5% open at all). Any
   recall read on the open basis over-counts what the live path misses; the in-window columns
   above are the honest ones, and "touch" is itself only an upper bound on "sustain".
3. **`mi_daily_closes` is split-adjusted after the fact.** LGCL read $118.94 in the capture and
   traded at $0.95 on the day; 71 "silent" rows and 128 rows in the gap bands were sub-$5 AT THE
   TIME and belong to `MIN_PREV_CLOSE`. The per-filter table is on raw D-1 closes; the first pass
   (`_617_classify_out.txt`) is kept for the audit trail and its silent count (119) is superseded
   by 44.
4. **The +86R / +57R / +36R "winners" under `MIN_PREV_CLOSE` are R inflation, not EPs**: $0.33,
   $0.57 and $1.71 stocks with 2–8¢ stops. Reported, flagged, not counted as recall.
5. **165 "unclassified security type" names are OTC symbols** with no Alpaca data at all — a
   coverage fact about Polygon's universe, not a filter finding.

## 8. What this does not answer

- **Whether any excluded name would have SURVIVED grading and the score bar.** The LLM catalyst
  grade, the pre-score shortlist and the 50-point bar are not replayed ($0 rule), so every recall
  figure is an upper bound and every alert-cost figure is an estimate from the adjacent band.
- **April.** The fixture's seven names are outside the window; whether they printed 9% in-window
  cannot be read without their minute bars (the 08-19 decision table already states this).
- **Detection latency.** 09:31 is assumed; the live scan's first tick and the 09:45 ORB cutoff can
  only cost entries, never add them — the 09:36 read in §6 shows the direction, not the full size.
- **Portfolio interaction.** Slots, breakers and loss limits are not replayed; the eleven ≥4R
  names cluster on five days, so their portfolio value is smaller than their count.
- **Three sessions of real-time authority.** The post-08-27 silent set is 2 rows on the flip
  morning; whether the RT path has a miss class of its own needs the standing review (Step 2).
- **The in-window "sustain" column is a mirror, not the live call** — it uses the 09:30–09:44
  minute closes; the live rule reads its own bar series per tick. Same rule, same threshold,
  different clock; treat it as close, not exact.

## 9. What this changes about the picture (P7)

The recall debt lives in April's tape and the fixture's open basis; in the last three months the
universe stack did not turn away a ≥4R name in the band anyone has proposed admitting, and the
admitted pool converted zero ≥4R itself. The remaining probability mass is downstream — entry
conversion (27 of 196 alerts never crossed the ORB high, 65 refused by the ORB rule) and geometry —
not at the floor. Step 2 (a standing review on this measure) should be wired to the RAW D-1 basis
and the in-window sustain cross, so the next read does not need a hand-run pass; Step 3 has no
evidence behind it from this window.

---
Artifacts (all $0, read-only): `scripts/probes/_617_population.sql` + `_617_population_out.txt`
(capture, 9MB), `_617_classify.py` + `_617_classify_out.txt` (first pass, adjusted basis),
`_617_fetch_bars.py` + `_617_bars.psv.gz` (Alpaca SIP raw bars, complete re-fetch, 17MB),
`_617_replay.py` + `_617_replay_out.tsv` + `_617_replay_summary.txt` (the walk),
`_617_post.py` + `_617_post_out.txt` + `_617_post_rows.tsv` (raw-basis reclassification, the
tables above), `_617_live_rules_out.txt`.
