# #482 Bracket-geometry read — the 5-minute opening-range basis vs the live 1-minute bracket

**2026-08-18 · read-only · $0 · probe: `scripts/probes/bracket_geometry_read_482.py`**
(capture SQL in the probe docstring; raw probe output reproduced at the bottom; nothing on prod
was written; no code in any strategy path was touched)

## The answer, up front

**The 5-minute opening-range basis does not beat the live 1-minute bracket.** On the 17
name-days both lanes traded, it is a tie at the median in R units and **loses in
volatility (ADR) units** — 12 of 17 pairs worse, paired sum −7.34 vs −6.70 ADR. Its
wider stop is still hit at full loss **76% of the time** (live 1-min: 73%) — widening
the bar from 1 to 5 minutes does not move the stop out of the noise path, it only pays
more per stop-out in stock terms. And the wider R unit demonstrably destroys the +2R
partial (mechanism 5 below). Meanwhile the operator-signed 2026-08-16 bracket (stop =
entry − 2R at half size, target unmoved) already gives a **wider stop than the 5-minute
basis would** (median stop distance ≈ 6.5% of entry vs the 5-min lane's 4.8%) **without**
raising the partial target — the exact combination this read says you want, with zero
closed-trade evidence yet (era C, n=0).

## What was read

| population | n | provenance |
|---|---|---|
| shadow 5-min, closed, **NOT quarantined** | 42 | 19 accrued in real time + 23 replayed from real Polygon daily history |
| — of which magna53 (the stop-geometry contrast) | **29** | 17 accrued + 12 replayed |
| — of which 9m_day2 | 13 | prior-day-low stop in BOTH lanes — carries **no** stop contrast |
| shadow 5-min, open (still accruing) | 10 | — |
| live 1-min, closed, usable | 53 (45 magna53) | real Alpaca fills; 25 paper-account, 20 real-money; 1 excluded (`pnl_attribution` incident row) |
| **paired** — same ticker + alert_date closed in both lanes | **17 magna53** (+2 9m) | 7 of the 17 shadow sides are replayed reconstructions |

The 28 quarantined rows are excluded in the capture SQL (`AND NOT quarantined`) and
re-asserted excluded by the probe. **Note for the operator: the N≥30 gate was met at 42
counting the whole lane, but only 29 of those rows carry the 1-min-vs-5-min stop
contrast** — the 13 9m rows use the same prior-day-low stop in both lanes.

**Units.** `risk_dollars` is planned risk and the position-size cap binds on a third of
rows, so the primary unit here is per-share stop-distance R = (pnl/share)/(entry −
hard_stop); the system-convention pnl/planned-risk numbers are also reported and do not
change any conclusion. ADR units = per-share pnl ÷ the stock's own 20-day mean daily
range (from `mi_daily_closes`; 95/95 rows covered) — the same denominator for both
lanes, which is what makes it the un-riggable comparison for a question that is *about*
volatility.

## 1. Paired comparison (primary), n=17 magna53

| metric | live 1-min | shadow 5-min | verdict |
|---|---|---|---|
| sum R (per-share unit) | −16.61 | −11.63 | 5m "better" by +4.99 — **but +3.57 of that is one artifact row (SYRE, below)** |
| sum R (planned-risk unit) | −12.25 | −11.00 | 5m better by +1.25 — noise |
| median R | −1.00 | −1.00 | tie |
| median pair delta | — | — | **+0.01 ≈ zero** |
| sum ADR units | −6.70 | **−7.34** | **5m loses** |
| median pair delta, ADR | — | — | **−0.22 per pair against 5m** |
| pairs better / worse / tied (R) | — | — | 7 / 4 / 6 |
| pairs worse in ADR units | — | — | **12 of 17** |

**Excluding SYRE** (the artifact row): sum dR **+1.42 over 16 pairs** (median 0.00) and
sum dADR **−2.96** (median −0.22). The R-unit "advantage" is a rounding error produced
by a sim that cannot lose more than −1R; the volatility-unit read is consistently
against the 5-minute basis.

**The SYRE artifact — why the summed-R headline cannot be taken at face value.**
SYRE 2026-06-22: live entered 98.49, stop 95.00; on 06-24 the stock **opened at 83.22**,
gapping through the stop; the real fill was 82.54 → **−4.57R lived**. The shadow ladder
fills a breached stop *at the stop price*: it booked exactly −1.00R at 95.00 on a day the
stock's high was 88.15 — **a fill that never existed**. The sim structurally cannot
record a worse-than-full loss; the live cohort has **14** of them. Every summed-R gap in
the 5-min lane's favour inherits this optimism.

**The per-pair shape** is the more instructive read: on ordinary losing days the 5-min
lane converts partial 1-min losses into *full* losses (MANE −0.23 lived vs −1.00 sim;
SMCI −0.70 vs −1.00; WULF/CRCL/QBTS/BTDR ≈ −1 vs −1). The wider stop rarely rescues the
same trade; it mostly deepens the same loss in stock terms.

## 2. By exit era — one segment readable

| era | live-side rules | live 1-min magna53 | shadow 5-min magna53 | paired |
|---|---|---|---|---|
| A (< 08-05) | no +2R partial, ORB-low stop | n=39, sum −33.33, med −1.02, p90 +0.29 | n=27, sum −3.97, med −1.00, p90 +1.16 | n=16 — the read above minus NET |
| B (08-05 → 08-16) | +2R partial live, ORB-low stop | n=6, sum −3.93, 1 win (partial fired on 2: FIGS −0.37, ETON +0.52) | **n=2 — not readable** | n=1 — not readable |
| C (≥ 08-17) | stop = entry−2R, half size | **n=0 — not readable** | n=0 — not readable | n=0 |

Everything decision-grade in this read is **era A** — the old live bracket without the
partial. Era B is not readable on the shadow side and era C — **the bracket actually
live today** — has no closed evidence at all yet.

## 3. Tail and cohort-vs-cohort (SECONDARY — different populations)

Whole-cohort, all eras, magna53 (the populations differ: 23 shadow-closed rows have no
live twin, 16 live rows have no shadow twin):

- realized R (per-share): live n=45 sum −37.26, med −1.01, p90 +0.49, max +3.83, 7 wins
  · shadow n=29 sum −5.97, med −1.00, p90 +1.16, **max +11.01**, 5 wins
- ADR units: live sum −22.35, med −0.43, max +1.53 · shadow sum −4.10, med −0.58,
  **max +6.21**
- **Both lanes are negative.** Neither bracket has positive expectancy on its own
  cohort. Geometry is not the edge lever — same conclusion the 7/19 read reached, now
  on honest data.

The 5-min lane's fatter tail is real in the table but rests on evidence that cannot
support the geometry claim:

1. **The entire tail is one reconstructed row.** AMBQ 2026-05-12, +11.01R, replayed —
   on a day the live lane **skipped on an infra failure** (`account_fetch_failed`, the
   ALPACA_LIVE_API_KEY incident class). It is evidence the *lane's universe* caught a
   winner, not that the 5-min *geometry* did: the stock opened at its low (53.14) and
   never traded below it again — any bracket entered that morning survives, and the
   tighter 1-min unit would have booked *more* R multiples on the same path, not fewer.
2. **The lane self-censors its widest names.** 49 of its 56 gate_blocked rows are
   `stop_too_wide` (the 5-min range fails 1.5×ATR more often than the 1-min range by
   construction) — the shadow cohort is pre-filtered toward tamer geometry, flattering
   its averages against a live cohort that carries names like SYRE.
3. **Three structural optimisms, all one-directional:** no day-0 evaluation (neither
   accrual nor replay ever sees the alert day — the live lane's modal loss day), stop
   fills at the stop price on gap-throughs, and daily-bar granularity. The lane can
   under-count losses; it cannot under-count wins.

## 4. Mechanism 5 — confirmed present

The wider basis widens the R unit, which raises the +2R partial target:

- Own-cohort: **36%** of live 1-min trades touched their own +2R within hold; only
  **24%** of 5-min shadow trades touched theirs.
- Paired head-to-head: **4 of 17 pairs** (AMD, DELL, MANE, QBTS) reached the 1-min +2R
  target but **never** reached the 5-min one — on those paths the wider bracket
  forfeits the partial the live bracket banks. The reverse case (5m target reached, 1m
  not) is impossible by construction.

This is the mechanism that refuted the k=0.75 stop-floor on 2026-08-06, showing up
again in forward data. It is also precisely what the signed era-C bracket avoids: the
stop widened, **the target did not move**.

## 5. Reconstruction vs lived — what kind of evidence this is

- **No shadow row is a real fill.** All 42 are EOD daily-bar simulations. Within them,
  the provenance split is deterministic, not random: any row that survived its first
  daily step froze (the #216 bug corrupted on first update), so **every closed
  multi-day path — including all 5 winners — is a replayed reconstruction**; every
  real-time-accrued close is a one-step −1.00R stop-out (17/17). The replay is faithful
  to the same ladder, but all tail evidence in this lane is reconstruction.
- **Every live row is a lived fill** (25 paper-account, 20 real-money), including real
  slippage the sim cannot express.
- The 9m_day2 secondary read (same stop both lanes, entry-level only): shadow n=13 sum
  +0.81, live n=8 sum +0.26 per-share — small, mildly pro-5m-entry, not a stop-geometry
  datum, and moot while #515 removes 9M Day 2.

## What the evidence supports (informs — decides nothing; THE LINE)

1. **Do not switch the bracket to a 5-minute bar.** At matched name-days it ties in R,
   loses in volatility units, still stops out at full loss 76% of the time, and pays
   for its wider stop by pushing the +2R partial out of reach on ~1 in 4 winning paths.
   The only numbers in its favour are artifacts (a sim that fills gapped stops at the
   stop price, a tail that is one reconstructed infra-skip row).
2. **The live era-C bracket signed 2026-08-16 already dominates the 5-minute variant on
   this read's own mechanism**: stop distance ~2× the 1-min range (wider than the
   5-min basis) while the +2R target stays on the 1-min unit. It has n=0 closed trades.
   The highest-value next evidence is simply letting era C accrue.
3. The shadow lane stays worth running as telemetry, but any future read should carry
   this doc's three structural-optimism caveats; its summed R can never be compared
   raw against lived fills.

**The fork in front of the operator:** keep the 1-minute basis with the era-C 2R stop
and let it accrue evidence (recommended — one line: *the 5-minute experiment answered
its question: wider bar ≠ better bracket; your signed 2R stop is the wider stop done
right*), or direct a different variant (re-entry / intraday-low / ATR-stop, #482's
remaining arms) into the shadow lab.

---

## Appendix — probe output (verbatim)

Probe: `scripts/probes/bracket_geometry_read_482.py` against the 2026-08-18 prod
capture (SQL in the probe docstring). Key blocks:

```text
UNIT NOTE: the position-size cap binds on 33/95 rows; PRIMARY unit is per-share
stop-distance R = (pnl/share)/(entry-hard_stop); planned-risk R secondary.

1. PAIRED magna53 n=17 (era A n=16, era B n=1):
   SUM R:   1m -16.61  vs 5m -11.63   (paired delta sum +4.99; excl SYRE +1.42/16)
   MEDIAN:  1m -1.00   vs 5m -1.00    median pair-delta +0.01
   ADR SUM: 1m -6.70   vs 5m -7.34    (excl SYRE: dADR sum -2.96, median -0.22)
   planned-risk unit: 1m sum -12.25 med -0.78  vs 5m sum -11.00 med -0.99
   5m better on 7, worse on 4, tied on 6 (|dR|<=0.05); worse in ADR on 12 of 17

2. ERA A cohorts: live n=39 sum -33.33 med -1.02 p90 +0.29 max +3.83 win 6/39
                  5m   n=27 sum  -3.97 med -1.00 p90 +1.16 max +11.01 win 5/27
   ERA B: live n=6 sum -3.93 (1 win); 5m n=2 not readable. ERA C: n=0 everywhere.

3. COHORT (secondary), all-era magna53:
   per-share R: live n=45 sum -37.26 med -1.01 | 5m n=29 sum -5.97 med -1.00
   ADR units:   live sum -22.35 med -0.43 max +1.53 | 5m sum -4.10 med -0.58 max +6.21
   stop distance % of entry: live med 3.26% | 5m med 4.76%
   full-loss rate (R<=-0.95): live 33/45 (73%) | 5m 22/29 (76%)
   worse-than-full-loss rows (gap/slippage): live 14 | 5m 0 (sim cannot produce one)

4. MECHANISM 5: own +2R touched within hold: live 16/45 (36%) | 5m 7/29 (24%)
   pairs where 1m's +2R touched but 5m's never: 4/17 (AMD, DELL, MANE, QBTS)

5. PROVENANCE: 5m winners 5/5 replayed; accrued closes 17/17 exactly -1.00R.
   Shadow gate_blocked composition: stop_too_wide 49/56, faded_from_orb 7/56.
```
