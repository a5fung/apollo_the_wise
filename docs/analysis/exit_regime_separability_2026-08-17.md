# Exit regime separability — `exit_regime_separability` review, run 2026-08-17

**Review:** `exit_regime_separability` in `data_gated_reviews.yaml` (added 2026-08-01, threshold 4,
fired at live-Bull n=9 by the date-joined predicate — 7 days overdue when run).
**Blocker this answers:** `docs/analysis/508_exit_discipline_STATE_2026-08-01.md` §3.4 — regime was
confounded with cohort (Bull was almost all paper, Correcting was all live), so no grid could tell
"bull markets run further" apart from "paper behaves differently from live."

**THE LINE: this document decides nothing.** It measures and reports. Any exit-rule change is
CHANGE_PROCESS + operator sign-off + backtest. Nothing in `broker/`, `exit_logic.py`, or any
strategy/sizing/safeguard code was touched.

**§3.1/§3.2/§3.3 of the state doc are NOT re-opened here** (unit, trigger level, partial-vs-full —
each has its own gate). This document is scoped to §3.4 only.

---

## 1. A methodology fix carried over from #508 (2026-08-08), applied here for the first time

The review's own predicate in `data_gated_reviews.yaml` joins regime by **date**
(`mi_market_regime ON regime_date = alert_date`) — the regime as later **revised**, not the regime
the trade was entered into. On 2026-08-08 the operator's #508 verification found this exact join
disagreeing with the entry-stamped value (`mi_live_trades.regime`) on 5 of 17 live trades, and
ruled: *for any exit-rule read, regime is the value stamped at entry* — because that is the
information the entry decision actually had. `agents/market_intelligence/sell_discipline.py` (not
touched by this review) already carries that fix on the operator-facing surface.

This review asks the identical kind of question, so it inherits the identical fix. Verified directly
against prod, both ways, 2026-08-17:

| join | live/magna53 Bull | Correcting | Choppy | Crisis |
|---|---|---|---|---|
| **date-joined** (the review's predicate, `mi_market_regime`) | **9** | 7 | 4 | 0 |
| **entry-stamped** (this document, `mi_live_trades.regime`) | **6** | 7 | 6 | 1 |

The predicate fired on the inflated number (9). Using the correct one (6), the review still clears
its own n≥4 floor — **the fire was legitimate, just off by 3 trades.** Checked directly against
prod (every trade where the two joins disagree): 5 live/magna53 trades move, not 3 — WULF
(alert 07-06, Choppy at entry → Bull by date-join), TSEM (07-14, Correcting → Choppy), FTNT
(07-30, Crisis → Correcting), BLZE and BTDR (both 08-04, Choppy → Bull). Only WULF/BLZE/BTDR add to
the Bull count (6→9); TSEM and FTNT move between other cells and don't touch it. These are the same
5 tickers #508's 2026-08-08 verification found disagreeing (WULF, TSEM, FTNT, BTDR, BLZE) — this
review's predicate has been carrying the same defect since it was written. `data_gated_reviews.yaml`
itself was left unedited (other agents are concurrently editing this tree; the predicate is a config
file, not this document's job to fix).

## 2. Fresh snapshot — the live cohort has grown 12 → 20 since the 07-30 pull

`scripts/probes/_508_exit_rule_replay.py` (34-candidate replay engine, unchanged, reused as a
library) was pointed at a **fresh prod snapshot pulled 2026-08-17** (read-only `COPY TO STDOUT`,
same 4-table shape as the original) instead of the stale 43-row one. Total sell-discipline rows: 51
(live/magna53 20, paper/magna53 24, paper/9m_day2 7). New script:
`scripts/probes/_508c_regime_separability_2026-08-17.py` — imports the tested engine unmodified and
redirects its data source; the original `_508_exit_rule_replay.py` and its 07-30 TSVs are untouched.

**Live/magna53 by entry-stamped regime: Correcting 7 · Choppy 6 · Bull 6 · Crisis 1.**

## 3. Live-Bull vs live-Correcting — the comparison this review exists to make

Both cells now clear n≥4 for the first time, entirely within the live cohort — no paper trade is
part of this comparison.

| | live-Bull (n=6) | live-Correcting (n=7) |
|---|---|---|
| realized R, mean | −0.66 | −0.97 |
| winners | 1 of 6 (ETON, +0.52R — flagged below, share-count mismatch) | 0 of 7 |
| mean hold | **1.00 day** | **1.71 days** |
| peak R reached, mean | +1.29 | +1.50 |
| peak R reached, P90 | +2.50 | +3.42 |
| peak R reached, max | +2.90 | +3.74 |
| share reaching ≥2R, defensible only* | 17% (1 of 6) | 29% (2 of 7) |
| peak, ADR20-normalised mean | +0.59 ADR | +0.99 ADR |
| peak, ADR20-normalised P90 | +1.28 ADR | +1.95 ADR |
| trades that "ran" (peak ≥ 1.5×ADR20) | **0** | **2** (SMCI 1.68×, NVCR 2.35×) |
| realized, ADR20-normalised mean | −0.25 ADR | −0.66 ADR |

Per-trade detail (peak R is a **floor** — the recorder is blind under ~10 minutes of hold, and
several trades here died inside that window: NET, TEAM, FRMI, BW all show `hold_d=1`; this biases
every "reached" figure in both cells down, roughly equally):

```
Bull (n=6)                                   Correcting (n=7)
NET   08-07  hold1  R -1.00  peak 1.68  0.52 ADR    TSEM  07-14  hold1  R -1.00  peak 0.00  0.00 ADR
FIGS  08-07  hold1  R -0.37  peak 2.90  1.17 ADR    HUT   07-20  hold1  R -1.07  peak 0.00  0.00 ADR
TEAM  08-07  hold1  R -1.02  peak 1.08  0.45 ADR    SMCI  07-22  hold4  R -0.70  peak 3.21  1.68 ADR
FRMI  08-11  hold1  R -0.98  peak 0.00  0.00 ADR    NVCR  07-23  hold2  R -1.00  peak 2.00  2.35 ADR
BW    08-11  hold1  R -1.09  peak 0.00  0.00 ADR    THC   07-24  hold1  R -1.01  peak 0.64  0.60 ADR
ETON  08-14  hold1  R +0.52  peak 2.09  1.38 ADR    WKC   07-24  hold1  R -1.03  peak 0.90  1.00 ADR
                                                     QBTS  07-27  hold2  R -1.00  peak 3.74  1.32 ADR
```

*\*Defensibility check, run against the replay engine's own trigger-finder (not just thresholding
the recorded `peak_r` field): Bull's ETON shows a recorded peak of +2.09R, but the engine's
`sim_r_rule(..., 2.0, full_exit=True)` never actually finds a placeable +2R touch for it
(`triggered=False`) — so it doesn't count as defensible even though the raw number clears 2.0.
Correcting's NVCR clears +2R by 0.0005R (`marginal=True`, a single-touch print inside one cent of
the trigger) — counted here as NOT defensible either. Excluded, the real count is FIGS alone in
Bull (peak 2.90R, `triggered=True, marginal=False`) against SMCI and QBTS in Correcting (both
`triggered=True, marginal=False`). The direction still favors Correcting; the size of the gap
should not be read past 1-of-6 vs 2-of-7.*

**A second confound sits on this exact comparison and needs to be named, not just tail-checked.**
Every live-Bull trade alerted 08-07 through 08-14 — entirely AFTER `PROFIT_TRIGGER_R = 2.0` went
live on 2026-08-01 (commit `ccd641b`). Every live-Correcting trade alerted 07-14 through 07-27 —
entirely BEFORE it. Two of the six Bull trades (FIGS, ETON) show `partial_taken=True`; zero of the
seven Correcting trades do. So regime and exit-era move together in this specific comparison, the
same shape as §3.4's original cohort confound and its "paper is also old entry mechanics" corollary.
**The direction of the bias plausibly favors this document's finding, not against it — but this is
argued, not verified.** `peak_price` is tracked from `highest_price_seen`, which this document
assumes stops updating once a position fully closes (not directly confirmed against the tracking
job's code, which lives in `agents/market_intelligence/` and was not touched here); on that
assumption, a partial that arms a tighter breakeven stop would close the remainder sooner than a
single wide stop on the same price path, shortening the observation window and biasing recorded
Bull peaks down. FIGS is a weak test of this: the whole trade lived 21 minutes, its partial fired at
+1.13R with the remainder stopping 16 minutes later, and it still recorded a peak of 2.90R — so
if this effect is real here, it is not large enough to have suppressed FIGS's own headline number.
Treat the direction as a plausible, unverified argument (repeated in §7(c)), not a correction applied
to the table above. (One
of the two partialed Bull trades, ETON, additionally has a legs total of 22 shares against an entry
of 17 — a share-sum mismatch matching the "double-fire" artifact class the replay engine already
flags on several April/early-May trades; noted here as a live data-quality finding worth someone's
attention, not investigated or fixed by this review.)

**Reading this plainly:** on every axis measured — how far trades ran (R and ADR-normalised),
how many crossed the "actually ran" bar on defensible evidence, and how long they were held —
**the live-Correcting cohort shows the bigger tail, not the live-Bull cohort.** Bull trades died
faster (1.0 day average vs 1.7) and closer to breakeven; Correcting produced the two trades that
"ran" by the 1.5×ADR bar and the two largest realized peaks (3.21R/1.68×ADR on SMCI, 3.74R/1.32×ADR
on QBTS).

**This is the opposite direction from the operator's 2026-08-01 hypothesis** ("runners probably
happen more often in bull markets... let runners go in bull markets"). It is not a refutation — n=6
and n=7 mean one trade moving from a stop-out to a runner would shift either mean by roughly
0.15–0.2R — but it is a real, readable comparison now, and it does not point the way the hypothesis
predicted.

## 4. The regime-conditional arms — does "let it run in Bull" score well on live cells?

`rgm_<bull>/<chop>/<corr>` family, live-only cells (mean kept R; `None` = hold, no profit-take):

```
rule                              Bull(n6)      Choppy(n6)      Corr(n7)
rgm_none/2R/2R_part1/3+BE         -0.53          -0.74           -0.30
rgm_none/1R/1R_part1/3+BE         -0.53          -0.34           -0.44
rgm_4R/2R/1R_part1/3+BE           -0.53          -0.74           -0.44
rgm_4R/3R/2R_part1/3+BE           -0.53          -0.68           -0.30
rgm_3R/2R/2R_part1/3+BE           -0.53          -0.74           -0.30
rgm_6R/3R/2R_part1/3+BE           -0.53          -0.68           -0.30
rgm_none/2R/2R_exit_all           -0.53          -0.52           +0.27
rgm_none/3R/2R_exit_all           -0.53          -0.35           +0.27
```

Every arm that lets Bull run (`bull: None`) scores the SAME −0.53 in the Bull cell — because on this
cohort no Bull trade's peak ever cleared 3R (max peak was 2.90R), so "hold" and "wait for 3R" are
indistinguishable here; it is the do-nothing baseline, not evidence the hold arm is neutral in
general. The un-triggered candidates (which is what "hold" reduces to) fall back to `nothing_r` —
the trade's own recorded terminal exit price. For five of the six Bull trades that baseline is a
clean full-ride counterfactual: FIGS's `nothing_r` comes from its terminal `stop_hit` leg at 15.16
(the partial only removed 20 of its 61 shares upstream of that stop; it did not produce the stop
price), so FIGS is clean despite carrying a partial. **ETON alone is the contaminated one** — its
legs sum to 22 shares against a 17-share entry (the mismatch flagged above), and its terminal leg is
the anomalous `partial_profit` fill at 59.58, six hours after a full-size 17-share `stop_hit` at
55.05 had already closed the position; `nothing_r` for ETON is built from that anomalous leg, not
from an undisturbed hold. **So the "hold" side of the Bull vs Correcting comparison in this table is
not uniformly clean — one of six trades carries this asymmetry — and a same-cohort read of "early
trimming beats holding" should not be drawn from it as stated** — several candidates DO score better
than the hold arms in Bull (`R1_part1/3+BE` at −0.12, `R1.5_exit_all` at +0.24, vs the hold arms'
−0.53), but with one trade's baseline in question that comparison is weaker evidence than the
tail-shape finding above and is reported here without a directional claim attached. Correcting's
candidate grid is not affected the same way — none of its seven trades ever had a partial fire, so
`nothing_r` there is a clean full-ride baseline throughout, and `rgm_none/2R/2R_exit_all` (+0.27) and
`ADR1_exit_all` (+0.49) beating the actual (−0.97) is not subject to the same caveat.

**Full 34-candidate live-only grid (Bull vs Correcting)** is in
`scripts/probes/_508c_regime_separability_2026-08-17.py`'s output — every row pairs the two cells
with their own n so nothing is read past what n=6/n=7 supports.

## 5. Choppy and Crisis, for completeness — not the ask, reported briefly

- **Choppy, live-only, n=6** (up from 4): realized R mean −0.89, 0 winners. Dominated by MANE
  (peak +7.92R / only 1.21×ADR — the emblematic give-back case from §2.2 of the state doc; its tight
  stop relative to its own range inflates its R-multiple far past its ADR-multiple, the exact §2.4
  R-is-not-a-consistent-unit effect). Now separable on its own (n≥4) but not part of this review's
  specific ask.
- **Crisis, live-only, n=1** (FTNT): **not a result.** Below the n≥4 floor this probe's own table
  enforces; not reported as a comparison.

## 6. Paper cells — reported separately, never mixed into the live read

| | Bull | Choppy | Correcting |
|---|---|---|---|
| paper/magna53 | n=19, realized R mean −0.62, 5 winners | n=5, mean −1.47, 1 winner | **n=0** |

Paper has never once traded a Correcting-regime magna53 setup — which is itself the reason the
paper cohort could never have answered this question. That gap is exactly what §3.4 identified as
the confound, and it still holds for paper; it is the live cohort's growth that closed it.

## 7. Answer to the review's three-part ask

**(a) Which regimes are now separable, live-only:** Bull (n=6) and Correcting (n=7) — both clear
n≥4 for the first time; Choppy (n=6) is separable on its own too but is not part of this review's
comparison. **Crisis (n=1) is not separable.**

**(b) Do the regime-conditional arms, including "let runners go in Bull," differ meaningfully?**
The two live cells are now measurably different — but on the axis this review can measure cleanest
(how far trades actually ran, in R and in ADR20 terms, on defensible evidence), the direction
contradicts the hypothesis being tested rather than confirms it: live-Bull trades ran less far and
died faster than live-Correcting trades. On the narrower axis of "does holding beat trimming inside
Bull," the evidence is real but weaker — a third of the Bull cell had its own baseline already
touched by a live partial-profit fill, which this document flags rather than resolves (§3). Taken
together: **"let it run in Bull, take profit aggressively elsewhere" is not supported by the tail
evidence; the pattern found points the other way. The specific hold-vs-trim comparison inside Bull
is suggestive in the same direction but is not clean enough on its own to state as a finding.**

**(c) What is deliberately NOT concluded, and why:**
- **Not a decision.** Nothing here recommends adopting any candidate rule. That is THE LINE.
- **Not "refuted."** n=6 and n=7 are thin enough that one trade in either cell would move its mean
  by ~0.15–0.2R and could flip which regime looks like it "ran more." The correct word is
  "not supported, and pointing the other way" — not "disproven."
- **Not a clean hold-vs-trim read inside Bull.** One of six Bull trades (ETON) has a share-count
  mismatch that puts its recorded terminal price in question; §4 reports the candidate numbers but
  does not draw a directional "trimming beats holding" conclusion from that cell for that reason.
- **Not adjusted for the exit-era confound beyond noting its direction, and the direction itself is
  unverified.** Live-Bull entries are all post-2026-08-01 (after `PROFIT_TRIGGER_R=2.0` went live);
  live-Correcting entries are all pre-2026-08-01. This document ARGUES the resulting bias on
  recorded peaks runs against its own finding (assuming `highest_price_seen` tracking stops at full
  close, a partial+tighter-stop would shorten Bull's observation window, understating rather than
  manufacturing a Correcting-favoring gap) — but that assumption about the tracking mechanism is not
  confirmed against the code, and FIGS's own numbers (peak 2.90R recorded despite a 21-minute total
  hold) suggest the effect, if real, is not large. Treat it as a plausible direction, not a
  correction applied to any number in this document.
- **Not §3.5** (why live trades die in 1.5 days). This document reports the Bull-vs-Correcting hold
  gap (1.00 vs 1.71 days) as a fact of the comparison; it does not investigate the cause, which has
  its own trigger and its own open evidence (the shadow-trade control) already on record.
- **Not §3.1–§3.3.** Unit, trigger level, and partial-vs-full remain exactly as unsettled as the
  state doc left them; nothing here reopens them.
- **Not the recorded-peak instrumentation gap.** Several trades in both cells died inside the
  ~10-minute blind window (NET, TEAM, FRMI, BW in Bull), so every "reached" and "ran" figure above
  is a floor for both cells roughly equally — it narrows the gap's true size less than it changes
  its direction, but it is not zero.
- **Not the ETON share-count mismatch.** Flagged (§3) as a live data-quality finding — 22 shares of
  legs against a 17-share entry, matching a known artifact class — and reported, not diagnosed or
  fixed; that is outside this review and outside `agents/market_intelligence/`, which this review
  did not touch.

## 8. Provenance

- Predicate check (both joins) and cohort counts: run directly against prod, 2026-08-17,
  read-only `psql` (`docker exec apollo-postgres psql -U apollo -d apollo`).
- Snapshot: 4 TSVs pulled 2026-08-17 via read-only `COPY (...) TO STDOUT`, stored outside the repo
  (session scratchpad) — not committed, matching the review's $0/read-only/no-deploy constraints.
- Engine: `scripts/probes/_508_exit_rule_replay.py`, imported unmodified.
- New script: `scripts/probes/_508c_regime_separability_2026-08-17.py` (not committed — left in the
  working tree per instruction).
- `data_gated_reviews.yaml` was **not edited** — status remains `pending` in the file; this document
  is the record of the run.
