# #354 C1 — D3 undercut→reclaim probe (evidence gating the WATCH_UR detector change)

**Date**: 2026-07-26 · **Task**: #354, ADR 0026 §D3 backtest gate (ADR 0026:91-95)
**Probe**: `scripts/probes/_354_undercut_reclaim_probe.py` (read-only; data pulled via SELECT-only
psql from prod, TSV snapshots beside the script)
**Data**: `mi_flag_candidates` 2026-05-04 → 2026-07-24 (full table life) + `mi_daily_closes`
through 2026-07-24. **No detector code was changed; D3 is NOT implemented.**
**Gate**: detection-criterion change — CHANGE_PROCESS applies; the operator rules the flip. This
doc states findings, not rulings.

---

## VERDICT: NO-SHIP (against the ADR 0026:94-95 ship rule, primary definitions)

| Ship-rule leg | Requirement | Measured | Pass? |
|---|---|---|---|
| N | ≥ 10 settled reclaims | **439** | ✅ |
| Forward R positive | reclaim-close entry, stop = undercut low | **mean +0.09R** (bootstrap 95% CI **[−0.05, +0.24]**, includes 0) · **median −0.43R** · win 39% | ❌ effectively — mean is a statistical zero carried by a fat tail; median clearly negative |
| False-revival < 40% | reclaim → immediate re-undercut | **53.4%** at K=5 | ❌ |

### The one definitional axis that could flip the verdict — lead item

The ADR does not define "immediate." The false-revival curve crosses 40% **between K=2 and K=3**:

| K (trading days after reclaim) | 1 | 2 | 3 | 5 (primary) | 10 |
|---|---|---|---|---|---|
| false-revival, pooled | 26.3% | 35.3% | **44.0%** | **53.4%** | 65.0% |
| false-revival, post-HTF regime only | 50.0% | 57.7% | 65.4% | **87.5%** | 91.7% |

So the *letter* of the ship rule ("forward R positive" read as mean-only, "immediate" read as
K≤2) **passes**: mean +0.09R > 0 and 35.3% < 40%. It fails at K≥3 and fails on any
distribution-honest reading of "positive":

- The mean's 95% CI includes zero — "positive" is not statistically supported even pooled.
- Median −0.43R, win 39%, avg winner +1.49R, max +11.44R — exactly the #290 lottery shape ADR
  0026's own F1 guards against for D2 (F1's honesty bar: median ≥ −0.25R AND WR ≥ 25% AND
  mean ≥ 0 — this cohort **fails the median leg** at −0.43R).
- K=1-2 as "immediate" is the least defensible choice: the family's own settlement window
  (`anticipation.SETTLE_FORWARD_BARS = 5`) is the horizon at which this family judges an entry
  event, and a reclaim that closes back under the level on day 3 is a failed revival by any
  trading reading.

**No other methodology choice flips anything** (§4): dedup on/off, strict vs lenient settle,
stop variant, prior-stage slice, SMA/depth-gate slice — every variant keeps median negative
and K≥3 revival >40%.

### The finding that outranks the pooled verdict: the current-regime slice is outright negative

96% of the cohort predates the #356 HTF 90/40 universe flip (~2026-06-28). D3 would ship onto
the **post-HTF** population, and there the signal is not marginal, it is bad:

- post-HTF: 57 events → 26 reclaims decided → **19 settled: mean −0.64R, median −1.00R, win
  11%**, false-revival **87.5%** at K=5 (21/24), 50% by the NEXT DAY.
- pre-HTF: 420 settled, mean +0.12R, median −0.37R, win 41% — the pooled mean's entire
  positivity comes from the retired regime.

n=19 is below the ship rule's own N≥10? No — it clears N≥10, and it is the only
population-representative slice. Read either way it argues NO-SHIP: pooled = fails two legs;
current-regime-only = fails everything decisively.

---

## 1. Cause isolation — exact, not inferred

`mi_flag_candidates.reason` records the invalidation cause verbatim. The undercut branch
(`flag_detector.py:841-843`) writes `close_{c:.2f}_below_base_low_close_{blc:.2f}`; the format
is unchanged since the detector's first commit (`7bfc1e8`). Prod recon: the 2,707 INVALIDATED
rows collapse to exactly two reason shapes — `close_#_below_base_low_close_#` (1,628 =
undercut) and `close_#_below_sma#_#` (1,079 = MA loss; the age/depth/52w gates never fired an
INVALIDATED row). **No cause conflation**: the cohort is the undercut-reason rows only, and the
frozen `base_low_close` is parsed from the reason string (2dp precision, ±0.005 — immaterial at
cohort scale).

Event = first undercut row per (ticker, pivot_high_date): pivots carry forward regardless of
stage (`db.get_yesterday_flag_pivots` has no stage filter), so a base under water re-emits an
INVALIDATED row every scan — 1,628 rows → 701 distinct events. Episode dedup (a same-ticker
"new" event opening inside a prior event's still-open 25d window = the machine re-anchoring the
same episode after INVALIDATED killed it; under D3 it would have been ONE WATCH_UR base)
removed 89 → **612 events** (555 pre-HTF / 57 post-HTF).

## 2. Cohort results

**(i) Reclaim within the remaining age window** (W = 25 − base_age_at_undercut trading days,
age clock uninterrupted; the age-cap check at `flag_detector.py:837` precedes the undercut
branch, so it still kills WATCH_UR names):

- decided 580 (32 censored at the data edge, 0 window-exhausted): **448 reclaimed = 77%**.
- days-to-reclaim: median 2, mean 4.3, p90 11, max 22. The typical undercut is a 1-3 day dip,
  which is also why the false-revival rate is high — the level is porous in both directions.

**(ii) Forward R from the reclaim close, stop = undercut low** (excursion low, undercut day →
reclaim day inclusive; 10-trading-day fixed-stop settle, stop-first, identical geometry to
`_146_triggered_gate_backtest.py::settle` — the other C1 cohort, "settled identically" per ADR
0026 §C1):

| Cohort | n | mean | median | win | total |
|---|---|---|---|---|---|
| **PRIMARY — all reclaimers, strict settle** | **439** | **+0.09R** | **−0.43R** | **39%** | +38.3R |
| lenient partial-window settle (_146 convention) | 448 | +0.08R | −0.44R | 39% | +34.5R |
| stop = undercut-DAY low only (variant B) | 444 | +0.16R | −1.00R | 34% | +72.8R |
| post-HTF regime only | 19 | −0.64R | −1.00R | 11% | −12.2R |
| pre-HTF regime only | 420 | +0.12R | −0.37R | 41% | +50.5R |
| base ever WATCH+ (same pivot) pre-undercut | 173 | +0.05R | −0.52R | 35% | +8.8R |
| ticker qualified ≤14d pre-undercut (loose) | 284 | +0.07R | −0.53R | 36% | +20.2R |
| reclaim day passes SMA20/50/200 gates (F2-live) | 329 | +0.08R | −0.39R | 40% | +26.2R |
| + passes 25%-depth gate too | 269 | +0.12R | −0.30R | 43% | +31.3R |
| no-episode-dedup sensitivity | 504 | +0.06R | −0.53R | 39% | +28.9R |

fwd-max median +1.03R (perfect-exit upper bound) — even omniscient exits only median ~+1R.
Notable: the "base was a real flag (WATCH+)" slice is *worse* than the pooled cohort (+0.05R /
−0.52R) — the reclaim edge, such as it is, does not concentrate in the bases D3 most wants to
save. The best slice (F2 gates + depth, median −0.30R, win 43%) still fails F1's median floor.

**(iii) False-revival** — table in the verdict section. Primary K=5 = 53.4%.

## 3. Methodology choices (all stated, all sensitivity-checked)

1. **Reclaim = first daily close strictly above the FROZEN base_low_close.** Frozen because
   that is the level whose loss fired the transition (the gdl-reclaim shape D3 reuses —
   `anticipation.detect_gdl_reclaim` reclaims a *fixed* level). Verdict-insensitive vs ≥ at 2dp.
2. **"Immediate" = K=5 bars** (family settle window). THE sensitive choice — see lead item.
3. **Stop = excursion low** (undercut→reclaim inclusive; known at the reclaim close, no
   lookahead). Variant B (undercut-day low) trades a higher mean (+0.16R) for median −1.00R /
   win 34% — worse, not better, on honesty.
4. **R horizon = 10 trading days fixed-stop** — named family convention: identical to the _146
   probe (same ADR card, "both cohorts settled identically"). Strict (needs stop-out or full
   window) vs lenient: no difference (+0.09 vs +0.08).
5. **Episode dedup** — no difference (verdict identical without it).
6. **Cohort = ALL undercut-INVALIDATED bases** (verbatim ADR ask; D3's transition is
   unconditional on prior stage). The WATCH+-only reading is *worse*, so no cohort choice
   rescues the rule.

## 4. C3 implementation hazard found while probing (report-only — no code touched)

`base_low_close` is **recomputed daily** from the base window (`flag_detector.py:781`). Once
the undercut day enters the window, the running min IS the undercut close — so a minimal-diff
C3 ("change line 842's stage to WATCH_UR") would fire "reclaim" on the first
non-new-closing-low day: measured, that definition "reclaims" 448/580 (77%) at **median k=1
day** — degenerate. If D3 ever ships, C3 must freeze the reclaim level at the undercut (and the
probe's numbers are the frozen-level numbers). Related: on any day still below the frozen
level, the current check order means the SMA gates are shadowed by the undercut branch; on the
reclaim day they resume — the F2-live slice above measures that world (n=329, verdict
unchanged).

## 5. Honest limits

- **Regime pooling**: 96% of events predate the HTF 90/40 universe (#356, ~6/28). The pooled
  N=439 is statistically comfortable but measures a population the detector no longer scans.
  The population D3 ships onto has only n=19 settled — clearly negative, but 19 events over 4
  weeks in one market tape. If the operator wants a regime-pure N≥10-with-conviction read,
  that accrues at roughly ~15-20 settled reclaims/month of HTF-regime data.
- Single market period (May-Jul 2026), one tape; no regime diversity.
- 32 events right-censored (windows still open at 7/24); excluded from denominators, not
  guessed.
- `mi_daily_closes` is ingest-time split-adjusted; the three largest winners (DELL +11.4R,
  FCEL +5.7R, SPRC) were hand-checked against volume signatures — real moves, not split
  artifacts.
- The probe measures the D3 *entry signal* (reclaim close → 10d fixed-stop R), not the full
  U&R shadow-settlement with partials (`SETTLE_RULE`); a partial-harvest reading would shrink
  both tails but cannot turn a median-negative, 53%-whipsaw signal positive.

## 6. What the evidence says, in one line

Undercut bases do reclaim (77%), fast (median 2d) — the operator's "undercut is OK" intuition
is *directionally* right about invalidation being premature — but the reclaim close is not a
positive-expectancy entry (median −0.43R, mean ≈ 0, CI spans 0) and the level whipsaws (53%
re-undercut within 5d; 87% in the current regime), so the U&R entry as specified fails its own
ship rule. NO-SHIP as specified; the WATCH_UR *stage* question (keep watching vs kill) is
severable from the U&R *entry* question and the operator may want to rule on them separately.

---

## Appendix A — Cohort printout 1: reclaimers (the operator-review list)

Columns: undercut date, base_age at undercut, k = days to reclaim, best prior qualified stage
(same pivot), frozen base_low_close, entry (reclaim close), stop (excursion low), R at 10d
fixed-stop, fwd-max R, exit type, re-undercut day (— = none within 10d), gates = reclaim-day
SMA20/50/200 + 25%-depth pass/fail.

```
ticker undercut     age   k  prior            blc    entry     stop  R(10d)  fwdmaxR  exit     re-uc  gates
ELVR   2026-05-04     3   2  -              96.56    98.80    89.10   -1.00    +0.28  stop         1  sma+dep+
INV    2026-05-04     5   2  -               6.29     6.97     6.01   -1.00    +0.93  stop         1  sma+dep+
KFRC   2026-05-04     3  17  -              44.03    44.70    38.59   +0.85    +0.86  horizon      -  sma+dep+
PBI    2026-05-04     7   1  -              15.37    15.54    15.06   -1.00    +2.13  stop         1  sma+dep+
RMAX   2026-05-04     3   3  -              10.70    11.06    10.35   -1.00    +0.23  stop         1  sma+dep+
CNC    2026-05-05     3   1  -              53.34    55.33    52.00   +0.89    +1.63  horizon      -  sma+dep+
ETSY   2026-05-05     3   1  -              63.17    64.97    62.73   -1.00    +0.03  stop         3  sma+dep+
MOH    2026-05-05     4   1  -             192.70   197.44   191.65   -1.00    +0.54  stop         1  sma+dep+
SPRC   2026-05-05     5  16  -               7.24    10.55     4.00   -0.19    +0.80  horizon      -  sma-dep-
ACDC   2026-05-06     4   8  WATCH           7.32     7.81     6.05   -1.00    +0.23  stop         4  sma+dep+
BWLP   2026-05-06     4   1  WATCH          19.91    20.21    19.64   +3.67    +4.76  horizon      -  sma+dep+
FCEL   2026-05-06     4   2  WATCH          13.00    13.70    11.72   +5.71    +6.88  horizon      -  sma+dep+
LBRT   2026-05-06     4   2  WATCH          32.68    33.11    30.75   -0.54    +0.58  horizon     10  sma+dep+
NBR    2026-05-06     4   4  WATCH         100.97   101.97    94.17   -0.56    +1.40  horizon     10  sma+dep+
AMBQ   2026-05-07     3   1  -              39.36    44.18    37.43   +5.55    +5.58  horizon      -  sma+dep+
ATOM   2026-05-07     3   4  -               9.13     9.89     7.71   -1.00    +1.14  stop         2  sma+dep-
BE     2026-05-07     5   2  WATCH         283.36   283.92   249.10   -1.00    +1.12  stop         1  sma+dep+
CORT   2026-05-07     3   1  -              51.33    52.28    49.83   +3.23    +3.53  horizon      1  sma-dep+
ESI    2026-05-07     5   1  WATCH          42.59    43.90    42.08   -1.00    +0.89  stop         5  sma+dep+
NOK    2026-05-07     3   2  -              13.14    13.92    12.13   +1.42    +1.51  horizon      -  sma+dep+
NXPI   2026-05-07     5   1  WATCH         290.76   294.75   288.48   -1.00    +3.52  stop         -  sma+dep+
OBE    2026-05-07     3   2  -              12.88    12.89    11.55   -1.00    +0.71  stop         6  sma+dep+
PTEN   2026-05-07     3   2  -              11.58    11.86    11.08   +0.33    +1.56  horizon      -  sma+dep+
TTMI   2026-05-07     4   2  WATCH         157.47   162.99   150.42   -1.00    +3.00  stop         -  sma+dep+
VIAV   2026-05-07     4   2  WATCH          52.49    54.93    49.75   -1.00    +0.17  stop         4  sma+dep+
XXI    2026-05-07     3   2  -               8.69     8.73     8.16   -1.00    -0.28  stop         1  sma+dep+
AXSM   2026-05-08     3   2  -             220.22   224.03   213.19   +0.97    +1.34  horizon      -  sma+dep+
CHRD   2026-05-08     3   1  -             137.75   140.07   135.50   -0.48    +2.60  horizon      -  sma+dep+
RSI    2026-05-08     6   1  WATCH          27.75    28.13    27.25   -1.00    +0.18  stop         1  sma+dep+
SOUN   2026-05-08     3  15  -               9.14     9.25     7.85   -1.00    -0.06  stop         1  sma-dep+
AXGN   2026-05-11     8   5  WATCH          41.77    41.95    39.52   -1.00    +0.93  stop         3  sma+dep+
BLZE   2026-05-11     3   5  -               7.40     7.41     6.70   +2.08    +2.86  horizon      3  sma+dep+
FIVN   2026-05-11     3   6  -              21.90    22.52    19.83   +0.53    +1.64  horizon      2  sma+dep+
GBTG   2026-05-11     4   5  WATCH           9.43     9.44     9.34   -1.00    +0.67  stop         1  sma+dep+
PRCH   2026-05-11     3  14  -              10.97    11.03     9.46   -1.00    +0.11  stop         1  sma-dep+
RLYB   2026-05-11     3   7  -              14.38    14.58    13.61   +1.67    +3.09  horizon      -  sma+dep+
SILC   2026-05-11     3   2  -              44.19    46.93    40.54   -1.00    +0.88  stop         3  sma+dep+
TEAM   2026-05-11     4   5  WATCH          88.80    89.44    78.20   +1.75    +2.67  horizon      1  sma-dep+
ALGM   2026-05-12     3   9  -              47.93    50.76    39.57   -0.37    +0.33  horizon      3  sma+dep+
ARM    2026-05-12     3   1  -             212.65   221.21   200.89   +5.61    +6.31  horizon      2  sma+dep+
CECO   2026-05-12     3   1  -              81.38    83.14    78.01   -1.00    +1.73  stop         2  sma+dep+
CIFR   2026-05-12     3   1  -              20.28    21.24    18.65   -1.00    +1.67  stop         3  sma+dep+
EDSA   2026-05-12     6   1  WATCH          14.99    15.24    12.66   -1.00    -0.01  stop         1  sma+dep-
MANE   2026-05-12     4   1  WATCH         106.14   107.14   102.70   -1.00    +1.21  stop         1  sma+dep+
TEN    2026-05-12     3   6  -              43.44    44.11    41.43   -1.00    +0.65  stop         2  sma+dep+
THR    2026-05-12     4   1  WATCH          65.32    66.60    63.23   -1.00    +1.56  stop         2  sma+dep+
TRT    2026-05-12    11   2  WATCH          11.14    14.02    10.50   -0.37    +2.09  horizon      -  sma+dep-
TWLO   2026-05-12     3   2  -             197.07   198.04   188.18   -1.00    +0.45  stop         3  sma+dep+
WS     2026-05-12     3   2  -              40.43    40.66    38.45   -1.00    +0.90  stop         1  sma+dep+
WULF   2026-05-12     3   2  -              23.37    24.17    21.64   -1.00    +1.22  stop         1  sma+dep+
ZM     2026-05-12     4   8  -             105.13   105.64    95.36   -0.44    +0.89  horizon      1  sma+dep+
ACVA   2026-05-13     3   2  -               5.84     5.92     5.55   +1.68    +2.38  horizon      -  sma-dep+
CGNX   2026-05-13     3   1  -              65.66    66.09    63.21   -1.00    +1.01  stop         1  sma+dep+
DINO   2026-05-13     5   4  WATCH          70.50    71.82    68.20   -1.00    +0.71  stop         2  sma+dep+
DK     2026-05-13     5   2  WATCH          44.70    44.81    43.40   -1.00    +1.48  stop         3  sma+dep+
EZPW   2026-05-13     3   7  -              33.54    33.79    31.66   -1.00    +0.49  stop         2  sma+dep+
FLYW   2026-05-13     4  12  WATCH          16.46    16.61    15.54   -1.00    -0.21  stop         1  sma+dep+
FTRE   2026-05-13     3  10  -              14.61    15.00    13.00   +0.94    +1.28  horizon      -  sma+dep+
GRAL   2026-05-13     4   1  WATCH          61.26    61.80    59.50   -1.00    +7.70  stop         1  sma-dep+
HELE   2026-05-13     3   4  -              23.97    24.36    22.20   +0.56    +1.90  horizon      1  sma+dep+
HNGE   2026-05-13     4   4  WATCH          54.74    54.96    51.72   +1.14    +2.20  horizon      4  sma+dep+
LAC    2026-05-13     4  13  WATCH           5.57     5.75     4.55   -1.00    -0.17  stop         1  sma+dep-
RDVT   2026-05-13     3   2  -              46.90    46.93    43.98   +4.20    +4.22  horizon      -  sma-dep+
CRSR   2026-05-14     3   6  -               7.42     7.70     6.66   +0.95    +5.19  horizon      -  sma+dep+
CSIQ   2026-05-14     3   9  -              19.41    20.26    15.13   -1.00    +0.23  stop         1  sma+dep-
FA     2026-05-14     4   9  WATCH          15.56    15.90    14.51   -0.24    +0.85  horizon      -  sma+dep+
FLNC   2026-05-14     3   6  -              21.28    21.49    17.23   +0.61    +1.99  horizon      2  sma+dep-
FSTR   2026-05-14     5   9  WATCH          40.36    40.40    36.51   +0.44    +0.68  horizon      -  sma+dep+
ICLR   2026-05-14     4   8  -             117.38   118.45   108.89   +2.73    +3.95  horizon      -  sma-dep+
INTC   2026-05-14     3   7  -             120.29   123.52   102.40   -1.00    +0.15  stop         3  sma+dep+
IPX    2026-05-14     3  10  -              40.48    41.36    33.10   -0.64    +0.50  horizon      3  sma+dep+
TDOC   2026-05-14     3   9  -               6.77     7.51     6.26   -0.16    +0.42  horizon      -  sma+dep+
TGTX   2026-05-14     4  17  WATCH          42.54    43.37    36.48   +1.48    +2.03  horizon      -  sma+dep+
ABSI   2026-05-15     3   8  -               5.30     6.08     4.49   +0.27    +0.82  horizon      -  sma+dep-
ACLS   2026-05-15     6   6  WATCH         158.66   164.27   137.84   +0.01    +0.68  horizon      1  sma+dep+
AIOS   2026-05-15     9   4  COILED         15.52    17.80    13.01   -1.00    +0.17  stop         3  sma+dep-
AMD    2026-05-15     3   3  -             445.50   447.58   393.36   +1.39    +1.82  horizon      -  sma+dep+
AMN    2026-05-15     3  11  -              29.47    30.25    25.54   +0.35    +0.48  horizon      6  sma+dep+
ASPI   2026-05-15     3   6  -               5.97     6.93     4.80   -0.25    +0.76  horizon      -  sma-dep-
CIEN   2026-05-15     3   4  -             577.15   587.23   499.01   -1.00    +0.57  stop         4  sma+dep+
CLYM   2026-05-15     6   6  WATCH          11.12    11.39     9.25   -0.12    +0.38  horizon      3  sma+dep-
CRNC   2026-05-15     8   5  WATCH           9.86    10.98     8.97   +0.03    +1.14  horizon      -  sma+dep+
FEIM   2026-05-15     4   5  WATCH          60.30    68.01    55.11   +0.15    +0.65  horizon      -  sma+dep+
FLEX   2026-05-15     3   6  -             139.69   143.24   121.30   +0.18    +1.08  horizon      -  sma+dep+
GFS    2026-05-15     5   4  WATCH          72.15    81.35    65.51   -0.37    +0.71  horizon      -  sma+dep+
GLW    2026-05-15     3  11  -             198.24   200.40   169.80   -1.00    +0.27  stop         2  sma+dep+
HIMX   2026-05-15     3   2  -              19.11    19.29    17.31   +2.48    +2.93  horizon      1  sma+dep+
HNRG   2026-05-15     5   6  WATCH          18.81    19.02    17.16   -1.00    +0.56  stop         6  sma+dep+
HOG    2026-05-15     3  16  -              25.33    25.49    22.40   +0.02    +0.32  horizon      1  sma+dep+
IMOS   2026-05-15     5   6  WATCH          53.60    55.23    47.13   +0.41    +1.95  horizon      -  sma+dep+
IONQ   2026-05-15     3   4  -              55.26    58.89    45.51   -0.16    +1.10  horizon      -  sma+dep+
KGS    2026-05-15     3   1  -              74.23    75.78    72.60   -1.00    +0.60  stop         2  sma+dep+
KN     2026-05-15     3   5  -              35.25    36.66    33.26   +0.46    +0.96  horizon      -  sma+dep+
LITE   2026-05-15     3  11  -             992.37  1029.15   806.62   -1.00    +0.09  stop         1  sma+dep+
LRCX   2026-05-15     6   3  WATCH         286.52   292.09   263.71   +1.56    +1.91  horizon      -  sma+dep+
MARA   2026-05-15     3   3  -              12.72    13.15    11.53   +0.45    +1.34  horizon      -  sma+dep+
MEC    2026-05-15     3   5  -              25.39    25.45    21.00   +1.83    +2.16  horizon      -  sma+dep-
MKSI   2026-05-15     5   4  COILED        311.72   313.16   280.83   -0.36    +0.89  horizon     10  sma+dep+
MU     2026-05-15     3   6  -             766.58   895.88   652.21   +0.16    +0.79  horizon      -  sma+dep+
NVCR   2026-05-15     3   6  -              18.05    18.26    16.86   -1.00    +0.09  stop         1  sma+dep+
NVEC   2026-05-15     3   6  -              91.89    96.76    80.48   +0.52    +1.08  horizon      -  sma+dep-
PI     2026-05-15    10   5  WATCH         143.18   149.76   129.62   -1.00    +0.68  stop         5  sma-dep+
QBTS   2026-05-15     3   4  -              21.44    25.74    17.73   -0.24    +0.73  horizon      -  sma+dep-
QURE   2026-05-15     4   9  WATCH          27.64    28.53    24.00   -0.21    +0.55  horizon      2  sma+dep+
RIOT   2026-05-15     3   6  -              24.51    26.08    21.73   -0.18    +0.66  horizon      -  sma+dep+
ROKU   2026-05-15     3   6  -             125.68   127.61   119.59   -1.00    +0.73  stop         6  sma+dep+
RUM    2026-05-15     4   4  WATCH           7.92     8.06     6.82   -0.39    +2.00  horizon     10  sma+dep+
SANM   2026-05-15     4   5  WATCH         235.84   246.44   213.47   +0.17    +1.28  horizon      -  sma+dep+
SMCI   2026-05-15     3   3  -              32.00    33.46    29.46   +3.36    +4.49  horizon      -  sma-dep+
STX    2026-05-15     3   4  -             804.76   810.46   695.14   +0.32    +1.36  horizon      -  sma+dep+
SYRE   2026-05-15     3  13  -              75.04    78.48    64.67   +0.71    +0.91  horizon      1  sma+dep+
TPB    2026-05-15     4   3  WATCH          89.80    91.20    86.79   -1.00    +0.13  stop         3  sma-dep+
URGN   2026-05-15     3   3  -              29.68    30.22    27.34   -1.00    +0.16  stop         2  sma+dep+
USAR   2026-05-15     5   5  -              24.83    25.30    19.36   -0.52    +1.26  horizon      9  sma+dep-
VSAT   2026-05-15     3   1  -              70.58    71.52    69.24   -1.00    +8.01  stop         -  sma+dep+
WDC    2026-05-15     3   6  -             488.74   524.65   434.00   -0.08    +0.86  horizon      -  sma+dep+
WSC    2026-05-15     4  12  WATCH          25.89    25.92    22.68   +0.59    +0.97  horizon      -  sma+dep+
AMPX   2026-05-18    18   5  TIGHTENING     16.11    17.83    14.25   -0.11    +1.79  horizon      -  sma-dep-
ASYS   2026-05-18     5   3  WATCH          20.71    20.95    18.54   -1.00    +1.47  stop         6  sma+dep+
AXTI   2026-05-18     4   3  WATCH         114.98   121.02   101.88   -1.00    +1.16  stop         5  sma+dep+
BHE    2026-05-18     6   2  WATCH          83.38    83.45    79.49   +1.28    +1.50  horizon      1  sma+dep+
BLMN   2026-05-18     7   6  WATCH           7.95     8.30     7.29   -1.00    +0.47  stop         4  sma+dep+
CADL   2026-05-18     4  11  WATCH           8.72     8.80     7.47   -0.61    +0.58  horizon      2  sma+dep+
CCRN   2026-05-18     6  12  COILED         13.12    13.19    13.02   -0.12    +0.24  horizon      -  sma+dep+
CRCL   2026-05-18     3   3  -             114.00   114.88   107.21   -1.00    +0.52  stop         1  sma+dep+
CRML   2026-05-18    14   5  WATCH          11.18    11.74     9.71   -1.00    +0.42  stop         6  sma-dep-
DELL   2026-05-18     5   2  WATCH         238.94   242.93   227.27  +11.44   +14.47  horizon      -  sma+dep+
DOCN   2026-05-18     7   2  WATCH         150.43   160.11   139.21   +0.98    +1.17  horizon      4  sma+dep+
ENS    2026-05-18     4   3  WATCH         232.64   238.91   211.30   -0.43    +0.18  horizon      1  sma+dep+
FSLY   2026-05-18     7   2  -              17.00    17.12    16.18   -1.00    +5.24  stop         1  sma-dep-
HLIT   2026-05-18     3   3  -              12.54    12.70    11.97   +0.79    +6.87  horizon      -  sma+dep+
HPP    2026-05-18     6   3  WATCH          10.95    11.28    10.39   +2.76    +3.31  horizon      -  sma-dep+
HRI    2026-05-18     3   6  -             136.91   137.93   127.12   -1.00    +1.49  stop         2  sma+dep+
HUT    2026-05-18     7   3  WATCH          98.46   105.26    86.82   +0.38    +1.93  horizon      -  sma+dep+
IESC   2026-05-18     7   5  WATCH         665.63   696.85   605.99   +0.32    +0.78  horizon      -  sma+dep+
IMSR   2026-05-18    16   3  WATCH           6.80     6.93     6.05   +0.70    +3.65  horizon      -  sma-dep-
INFQ   2026-05-18    20   3  -              11.89    14.70    10.32   -0.03    +1.38  horizon      -  sma+dep-
JMIA   2026-05-18     6   3  -               7.00     7.10     6.55   -1.00    +1.02  stop         1  sma-dep-
KOPN   2026-05-18     3   4  -               5.02     5.14     4.20   +0.35    +1.56  horizon      -  sma+dep-
LFUS   2026-05-18     7   3  WATCH         441.58   443.91   417.31   +0.50    +2.13  horizon      -  sma+dep+
MCHP   2026-05-18     5   2  -              93.85    94.02    90.00   -1.00    +1.55  stop         1  sma-dep+
MP     2026-05-18     5   3  -              60.31    61.74    53.57   -0.31    +1.44  horizon     10  sma-dep-
MXL    2026-05-18     4   1  WATCH          87.73    94.86    82.53   -0.28    +0.93  horizon      8  sma+dep+
NVT    2026-05-18     7   5  WATCH         166.73   169.29   152.20   -0.32    +0.51  horizon      2  sma+dep+
PGY    2026-05-18     6   2  -              13.16    13.44    12.15   +1.57    +2.19  horizon      1  sma-dep-
PN     2026-05-18     8   5  -               4.31     4.32     3.83   -1.00    +7.47  stop         1  sma-dep-
QUBT   2026-05-18     3   3  -              10.51    11.41     9.14   -0.64    +0.87  horizon     10  sma-dep-
SIMO   2026-05-18     4   3  WATCH         258.71   263.51   230.05   -0.14    +1.52  horizon     10  sma+dep+
SNDK   2026-05-18     4   1  WATCH        1382.72  1383.29  1277.33   +4.23    +4.51  horizon      -  sma+dep+
STRL   2026-05-18     7   7  WATCH         811.41   842.96   702.51   -0.03    +1.16  horizon      9  sma+dep+
U      2026-05-18     6   6  WATCH          26.84    27.76    25.00   -0.40    +1.74  horizon     10  sma-dep+
USAS   2026-05-18     3  10  -               6.25     6.43     5.40   -1.00    -0.15  stop         1  sma+dep-
UUUU   2026-05-18     6   7  -              18.41    18.44    16.03   -1.00    +0.54  stop         1  sma-dep-
VECO   2026-05-18     7   3  WATCH          57.72    57.74    51.94   +0.12    +1.26  horizon      5  sma+dep+
VRDN   2026-05-18     8   2  TIGHTENING     16.61    17.63    15.65   -0.54    +0.29  horizon      8  sma-dep+
WCC    2026-05-18     3   4  -             358.72   363.57   329.62   -0.30    +0.42  horizon      5  sma+dep+
WEST   2026-05-18     4   2  WATCH           8.36     8.46     7.97   -1.00    +0.63  stop         2  sma+dep+
WLDN   2026-05-18     4   2  WATCH          91.06    92.60    87.05   +0.95    +1.51  horizon      1  sma-dep+
AAOI   2026-05-19     3   2  -             173.26   176.81   160.10   -1.00    +1.96  stop         4  sma+dep-
AAON   2026-05-19     7   1  WATCH         133.66   133.76   126.67   +1.39    +2.36  horizon      1  sma+dep+
AEVA   2026-05-19     3   1  -              19.45    21.11    17.33   +0.87    +2.30  horizon      -  sma+dep+
AKAM   2026-05-19     3   8  -             150.77   154.01   138.10   -1.00    +0.68  stop         4  sma+dep+
AMBA   2026-05-19     3   1  -              78.88    83.00    74.33   -1.00    +1.54  stop         6  sma+dep+
AUR    2026-05-19     3   8  -               7.42     7.47     6.70   -1.00    +0.78  stop         2  sma+dep+
BLLN   2026-05-19     5   1  -              82.63    83.38    78.01   +3.95    +4.96  horizon      -  sma-dep+
CEVA   2026-05-19     4   1  WATCH          36.51    38.03    34.92   +3.72    +4.25  horizon      -  sma+dep+
CLFD   2026-05-19     5   2  WATCH          42.51    42.78    39.69   -1.00    +3.22  stop        10  sma+dep+
CLNN   2026-05-19    10   1  TIGHTENING      6.50     6.90     6.31   -1.00    +0.05  stop         7  sma+dep-
COHR   2026-05-19     3   2  -             362.83   378.00   336.70   -0.02    +1.50  horizon      5  sma+dep+
COMP   2026-05-19     8   1  -               7.75     8.34     7.41   -1.00    +0.56  stop         9  sma-dep+
CYRX   2026-05-19     6   1  WATCH          13.04    14.07    12.98   +1.92    +2.44  horizon      -  sma+dep+
DGII   2026-05-19     7   1  TIGHTENING     61.53    62.25    60.44   +3.87    +4.72  horizon      -  sma+dep+
ENVX   2026-05-19     3   1  -               5.93     6.36     5.39   +2.06    +2.88  horizon      -  sma-dep-
EOSE   2026-05-19     3   2  -               7.43     8.17     6.73   -0.76    +1.06  horizon     10  sma-dep-
GSIT   2026-05-19     3   1  -               8.96     9.12     8.31   +0.53    +3.10  horizon      -  sma+dep-
INOD   2026-05-19     5   1  WATCH          89.95    94.71    85.01   +2.76    +3.14  horizon      4  sma+dep-
IREN   2026-05-19     6   1  WATCH          50.46    52.71    46.00   +1.36    +2.68  horizon      -  sma+dep-
JEF    2026-05-19     3   2  -              51.85    52.45    50.81   +1.98    +2.80  horizon      -  sma-dep+
KLIC   2026-05-19     7   1  WATCH          98.00   101.23    94.31   +0.91    +1.38  horizon      -  sma+dep+
LASR   2026-05-19     6   1  WATCH          70.83    71.30    65.91   +0.67    +2.20  horizon      7  sma-dep+
LINC   2026-05-19     3   8  -              49.10    49.39    45.85   -1.00    +0.64  stop         1  sma+dep+
MEI    2026-05-19     3   1  -              10.53    10.85     9.93   +2.03    +2.91  horizon      -  sma+dep-
MRAM   2026-05-19     3   3  -              33.35    33.68    28.20   -1.00    +0.18  stop         1  sma+dep-
MTRN   2026-05-19     3   1  -             202.29   206.05   193.55   +1.71    +2.19  horizon      -  sma+dep+
NG     2026-05-19    21   1  -               7.80     7.97     7.66   +0.71    +2.31  horizon      1  sma-dep-
NWPX   2026-05-19     9   1  WATCH         109.48   109.53   105.00   +2.89    +3.08  horizon      1  sma+dep+
NXT    2026-05-19     3   5  -             134.48   135.78   117.39   -1.00    +1.49  stop         7  sma+dep-
OSS    2026-05-19     4   2  WATCH          15.86    16.51    14.35   +0.18    +2.02  horizon      -  sma+dep+
PDFS   2026-05-19     5   1  -              43.64    44.78    41.04   +3.10    +3.57  horizon      -  sma-dep-
PINS   2026-05-19     9   3  -              19.03    19.29    18.02   +2.13    +2.42  horizon      -  sma-dep-
Q      2026-05-19     4   1  -             149.03   153.04   141.57   +0.15    +1.22  horizon      -  sma+dep+
QCOM   2026-05-19     5   1  WATCH         200.08   202.51   191.02   +3.49    +5.00  horizon      -  sma+dep+
RAL    2026-05-19     3   1  -              58.84    59.65    56.85   +0.99    +1.31  horizon      -  sma+dep+
RLAY   2026-05-19    19   1  -              12.10    13.02    11.62   +1.09    +3.18  horizon      -  sma-dep-
ST     2026-05-19     3   3  -              47.82    48.59    45.37   +0.49    +1.64  horizon      -  sma+dep+
SVM    2026-05-19     3   9  -              13.16    13.21    11.58   -1.00    -0.14  stop         1  sma+dep-
VELO   2026-05-19     3   2  -              18.59    20.33    15.59   -1.00    +1.30  stop        10  sma+dep-
VRT    2026-05-19     3  22  -             339.73   357.96   275.18   -0.63    -0.22  horizon      1  sma+dep-
WOLF   2026-05-19     3   2  -              59.35    69.50    53.78   -1.00    +0.72  stop         5  sma+dep-
XYZ    2026-05-19     6   1  -              69.78    70.89    67.80   -1.00    +2.18  stop         1  sma-dep+
CSCO   2026-05-20     3   1  -             115.38   118.20   113.57   +0.74    +2.63  horizon      -  sma+dep+
HTCO   2026-05-20    16   1  -               5.82     5.87     5.55   -1.00    +0.96  stop         1  sma-dep-
MTZ    2026-05-20     9   1  TIGHTENING    385.00   388.77   380.01   -1.00    +0.82  stop         1  sma-dep+
NBIS   2026-05-20     3   1  -             197.73   219.93   190.64   +0.27    +2.01  horizon      -  sma+dep+
PTON   2026-05-20     8   2  WATCH           5.18     5.71     4.89   -0.06    +1.01  horizon      -  sma-dep+
SHAZ   2026-05-20     6   1  WATCH          52.10    57.70    48.76   +1.09    +3.27  horizon      -  sma+dep+
ASTH   2026-05-21     8   2  WATCH          37.97    38.54    36.95   -1.00    +0.48  stop         3  sma+dep+
CVI    2026-05-21    15   4  TIGHTENING     32.58    33.62    30.59   -1.00    +0.93  stop         8  sma+dep+
HUM    2026-05-21     3   1  -             304.10   307.95   300.00   +6.04    +6.05  horizon      1  sma+dep+
NUTX   2026-05-21    12   2  TIGHTENING    121.00   123.20   115.81   +1.65    +2.13  horizon      1  sma-dep-
OMDA   2026-05-21     3   1  -              16.47    16.51    15.97   +2.54    +4.07  horizon      1  sma-dep+
TXN    2026-05-21     5   1  WATCH         300.60   309.21   294.78   -1.00    +1.55  stop         5  sma+dep+
VNET   2026-05-21     5   3  WATCH          10.09    10.71     9.14   -1.00    +0.59  stop         2  sma+dep+
BW     2026-05-22     4   1  WATCH          19.17    19.65    18.42   -1.00    +0.55  stop         3  sma+dep+
COCO   2026-05-22     4   1  WATCH          76.45    76.49    75.36   -1.00    +2.55  stop         3  sma+dep+
EOLS   2026-05-22    12   3  TIGHTENING      6.32     6.57     6.01   -1.00    +0.66  stop         3  sma+dep+
ONDS   2026-05-22     4   1  -               9.12     9.77     9.06   -1.00    +6.18  stop         -  sma-dep-
PCT    2026-05-22     3   1  -              11.33    12.27    10.93   -1.00    +1.43  stop        10  sma+dep+
TH     2026-05-22     4   1  WATCH          18.00    18.35    17.84   -1.00    +0.72  stop         2  sma+dep+
AGYS   2026-05-26     3   2  -              79.50    82.62    77.38   +1.75    +2.14  horizon      -  sma-dep+
GEMI   2026-05-26     5   2  WATCH           4.95     5.20     4.62   -1.00    +0.22  stop         4  sma+dep-
GEO    2026-05-26     6   2  COILED         22.81    23.11    22.29   +6.72    +7.05  horizon      1  sma+dep+
MDB    2026-05-26     3   2  -             317.50   325.68   292.72   +0.87    +2.62  horizon      -  sma+dep+
OSCR   2026-05-26     4   2  WATCH          22.14    22.33    21.52   -1.00    +8.75  stop         3  sma+dep+
RAMP   2026-05-26     4   1  WATCH          37.68    37.69    37.58   -1.00    +2.09  stop         1  sma+dep+
STUB   2026-05-26     3   3  -               9.84     9.86     9.44   -1.00    +3.83  stop         2  sma+dep+
FIG    2026-05-27     4   1  WATCH          21.59    23.46    21.09   -1.00    +1.80  stop         7  sma-dep+
FROG   2026-05-27     3   1  -              71.44    72.77    70.34   +2.35    +6.74  horizon      -  sma+dep+
HPK    2026-05-27     3   2  -               7.06     7.10     6.64   +1.63    +3.17  horizon      -  sma+dep+
IMVT   2026-05-27     3  15  -              33.83    34.71    30.24   +0.91    +1.02  horizon      -  sma+dep+
LPG    2026-05-27     3  12  -              44.88    45.19    39.82   -1.00    -0.24  stop         1  sma+dep+
SM     2026-05-27     3   3  -              31.79    32.67    30.06   -1.00    +0.77  stop         6  sma+dep+
TENB   2026-05-27     3   1  -              25.17    25.95    24.30   +0.56    +3.02  horizon      -  sma+dep+
VRNS   2026-05-27     3   1  -              30.66    31.81    30.12   +0.98    +2.64  horizon      -  sma-dep+
WNW    2026-05-27     3   2  -               3.33     3.80     3.06   -1.00    +0.26  stop         2  sma-dep-
WTTR   2026-05-27     3  21  -              19.28    19.66    17.32   -0.05    +0.17  horizon      3  sma+dep+
ROOT   2026-05-28    13   2  TIGHTENING     53.63    57.42    51.00   -0.40    +0.13  horizon      2  sma-dep+
AVR    2026-05-29     3   1  -               8.77     9.10     8.43   +0.48    +1.55  horizon      -  sma+dep+
GTX    2026-05-29     3   9  -              33.30    33.40    30.90   +0.68    +0.80  horizon      -  sma+dep+
POET   2026-05-29     9   1  TIGHTENING     13.07    13.89    11.50   -1.00    +0.86  stop         4  sma+dep-
ATKR   2026-06-01     3   1  -              82.06    84.16    79.82   -1.00    +0.28  stop         3  sma+dep+
IRDM   2026-06-01     3   3  -              51.26    52.07    47.27   -1.00    -0.23  stop         1  sma+dep+
LEGN   2026-06-01    17   1  COILED         25.58    36.28    24.81   -0.25    +0.11  horizon      -  sma+dep+
LION   2026-06-01     4   9  WATCH          14.00    14.32    13.19   +1.16    +2.11  horizon      -  sma+dep+
LSCC   2026-06-01     3   1  -             147.08   151.35   140.21   -1.00    +0.40  stop         3  sma+dep+
NP     2026-06-01    15   7  COILED         26.70    26.95    23.75   +0.15    +1.03  horizon      -  sma+dep+
NVTS   2026-06-01     3   2  -              26.60    30.84    23.59   -1.00    +0.10  stop         2  sma+dep-
OSG    2026-06-01    15   3  COILED          5.37     5.41     5.05   +0.97    +1.43  horizon      -  sma-dep+
SOC    2026-06-01     7   1  WATCH          13.13    13.57    12.21   -1.00    +0.18  stop         3  sma-dep+
TSEM   2026-06-01     3   1  -             255.23   274.71   240.97   -1.00    +0.50  stop         3  sma+dep+
AAL    2026-06-02     3   7  -              14.34    14.65    13.18   +2.18    +2.30  horizon      -  sma+dep+
CROX   2026-06-02     3   2  -             118.62   121.52   115.70   +0.61    +1.42  horizon      -  sma+dep+
DAL    2026-06-02     3   7  -              81.47    81.83    76.40   +1.98    +2.45  horizon      -  sma+dep+
DY     2026-06-02     3  18  -             493.89   506.80   431.87   -1.00    +0.09  stop         2  sma+dep+
PLSE   2026-06-02    11   1  TIGHTENING     24.55    24.99    23.60   +0.33    +2.55  horizon      7  sma+dep+
AGL    2026-06-03     3   1  -              86.75    95.23    80.00   +1.22    +1.51  horizon      -  sma+dep+
AIRS   2026-06-03     3   1  -               5.22     5.71     4.83   -1.00    -0.02  stop         1  sma+dep+
ASPN   2026-06-03     3   1  -               6.22     6.23     5.71   -1.00    +0.33  stop         1  sma+dep+
CAL    2026-06-03     4   1  WATCH          14.19    14.21    13.14   -1.00    +0.75  stop         1  sma+dep+
FICO   2026-06-03     3  20  -            1250.59  1270.83  1065.69   -0.07    +0.32  horizon      7  sma-dep+
GH     2026-06-03     3   1  -             129.14   133.06   125.50   -1.00    +0.26  stop         1  sma+dep+
LPTH   2026-06-03     3   1  -              16.08    17.62    14.70   -1.00    -0.24  stop         1  sma+dep+
PIII   2026-06-03     3   3  -              12.18    12.25     9.80   -0.11    +0.80  horizon      5  sma+dep-
RDW    2026-06-03     3   1  -              20.58    21.43    18.27   -1.00    -0.08  stop         1  sma+dep-
S      2026-06-03     6  17  WATCH          16.55    16.73    14.30   +1.32    +1.46  horizon      -  sma+dep+
SEZL   2026-06-03     3   1  -             118.15   120.97   108.51   +3.40    +3.48  horizon      1  sma+dep+
TRT    2026-06-03    11   1  WATCH          12.20    12.67    11.73   -1.00    +5.21  stop         1  sma-dep-
UMC    2026-06-03     4   8  WATCH          22.18    23.08    18.70   +0.94    +1.34  horizon      1  sma+dep+
VOYG   2026-06-03     3   1  -              47.49    47.70    43.16   -1.00    +0.44  stop         1  sma+dep+
PRFX   2026-06-04     3   7  -               1.86     2.49     1.33   -0.96    -0.18  horizon      1  sma-dep-
ABCL   2026-06-05     3  10  -               5.72     5.74     5.01   +2.67    +3.70  horizon      1  sma+dep-
ACMR   2026-06-05     5   4  WATCH          82.05    91.70    74.19   +0.73    +1.13  horizon      -  sma+dep+
AI     2026-06-05     3   1  -              10.58    10.60     9.92   -1.00    +1.12  stop         7  sma-dep+
AMPL   2026-06-05     3  17  -               7.75     8.55     6.30   +0.49    +0.63  horizon      -  sma-dep-
ASTI   2026-06-05     4   1  WATCH           6.91     7.48     6.25   -1.00    +1.75  stop         1  sma+dep-
ASX    2026-06-05     6   6  WATCH          38.17    38.50    32.73   +1.15    +1.18  horizon      1  sma+dep+
ATEX   2026-06-05     3   4  -              66.90    81.44    61.51   +0.41    +0.43  horizon      -  sma+dep+
BBAR   2026-06-05     3   2  -              17.71    18.14    17.18   +0.85    +4.53  horizon      1  sma+dep+
BBBY   2026-06-05     6  11  WATCH           6.13     6.61     5.37   -1.00    +0.40  stop         4  sma+dep+
BRZE   2026-06-05     3  18  -              23.14    23.81    18.65   +0.52    +0.62  horizon      -  sma-dep-
CGNT   2026-06-05     3  19  -               9.23     9.31     7.78   -0.40    +0.12  horizon      1  sma-dep-
CLSK   2026-06-05     3   6  -              16.78    17.14    14.06   -0.84    +0.62  horizon      6  sma+dep-
CMPS   2026-06-05     3  13  -              12.69    13.58    10.72   +0.02    +0.64  horizon      -  sma+dep-
CRML   2026-06-05    21   1  -               9.80    10.11     9.50   -1.00    +0.88  stop         1  sma-dep-
CVLT   2026-06-05     3   1  -             120.85   122.09   116.97   +0.61    +1.88  horizon      -  sma-dep+
DDOG   2026-06-05     3  15  -             243.60   248.57   212.73   +0.62    +0.64  horizon      -  sma+dep+
ERAS   2026-06-05     3   2  -              13.18    13.41    11.80   +1.02    +1.46  horizon      -  sma-dep+
GEN    2026-06-05     3  18  -              26.50    26.67    22.46   +0.02    +0.14  horizon      3  sma+dep+
HKIT   2026-06-05     3   1  -               0.33     7.87     5.75   -0.28    +7.06  horizon      -  sma-dep-
IBM    2026-06-05     3  20  -             301.77   306.13   243.68   -1.00    -0.04  stop         2  sma+dep-
IOT    2026-06-05     3  18  -              35.21    35.93    28.77   +0.33    +0.49  horizon      -  sma+dep-
MGM    2026-06-05     3   5  -              47.94    48.97    46.16   -1.00    +0.56  stop         3  sma+dep+
MPTI   2026-06-05     3   1  -              90.93    91.76    86.84   +0.29    +2.08  horizon      -  sma+dep+
NAVN   2026-06-05     3   4  -              22.16    22.63    19.67   -1.00    +0.09  stop         1  sma+dep+
NEXA   2026-06-05    20   5  COILED         13.31    13.73    12.02   -0.89    +0.82  horizon      7  sma-dep-
OKTA   2026-06-05     3  14  -             123.48   124.28   107.00   +0.88    +1.67  horizon      -  sma+dep+
OSPN   2026-06-05     3  17  -              14.44    14.74    13.00   +0.46    +0.71  horizon      -  sma+dep+
PANW   2026-06-05     3   4  -             279.25   279.53   251.15   +0.87    +0.94  horizon      -  sma+dep+
PAYS   2026-06-05     3   2  -               6.81     6.89     6.62   -1.00    +3.93  stop         2  sma+dep+
PD     2026-06-05     3  15  -               9.30     9.38     8.14   +1.30    +1.54  horizon      -  sma-dep+
PENN   2026-06-05     3   2  -              19.63    20.32    18.79   +0.04    +1.33  horizon      -  sma+dep+
PRE    2026-06-05     4   2  WATCH          20.39    20.93    19.22   -1.00    +0.75  stop         1  sma+dep+
PURR   2026-06-05     3   7  -               9.49    10.04     7.54   -0.73    +0.16  horizon      2  sma+dep-
QFIN   2026-06-05     3   5  -              15.20    15.40    13.93   +0.18    +0.58  horizon      2  sma-dep+
QLYS   2026-06-05     3   6  -             111.53   114.65   106.75   +2.89    +3.40  horizon      3  sma-dep+
RBRK   2026-06-05     3  16  -              77.00    80.28    66.37   +0.01    +0.73  horizon      -  sma+dep+
RNW    2026-06-05     3   4  -               6.25     6.34     5.95   -0.38    +0.47  horizon      4  sma+dep+
RPD    2026-06-05     3  15  -               7.67     7.82     6.28   +3.34    +3.56  horizon      -  sma-dep-
SLP    2026-06-05     3   4  -              16.17    16.49    15.64   +2.01    +2.44  horizon      -  sma+dep+
SNOW   2026-06-05     3  14  -             241.28   248.96   217.48   +0.63    +0.82  horizon      -  sma+dep+
SPT    2026-06-05     3   5  -               7.24     7.29     6.71   -1.00    +0.83  stop         2  sma-dep+
YPF    2026-06-05     3   4  -              54.90    56.35    52.30   -1.00    +0.14  stop         2  sma+dep+
BLFS   2026-06-08     3   1  -              26.65    27.55    26.04   -1.00    +0.34  stop         2  sma+dep+
CLF    2026-06-08     3   3  -              13.53    13.71    12.12   -1.00    +0.33  stop         3  sma+dep+
GRRR   2026-06-08     3   3  -              17.14    17.78    15.42   -0.13    +0.38  horizon      5  sma+dep-
IMSR   2026-06-08     4   5  -               7.55     7.56     6.65   -1.00    +1.25  stop         1  sma-dep-
MT     2026-06-08     3   3  -              67.21    69.09    63.60   -1.00    +0.44  stop         4  sma+dep+
NCT    2026-06-08     6   1  WATCH           2.79     2.95     1.92   -0.03    +1.00  horizon      -  sma-dep-
NET    2026-06-08     3  19  -             250.11   268.83   212.32   +0.06    +0.39  horizon      -  sma+dep+
NSIT   2026-06-08     3  11  -             111.07   113.30   102.67   +0.45    +1.10  horizon      -  sma+dep+
NTNX   2026-06-08     4  19  WATCH          53.04    53.76    44.84   +0.05    +0.55  horizon      -  sma+dep+
NUE    2026-06-08     3   3  -             254.39   260.90   245.33   -1.00    +0.64  stop         4  sma+dep+
POWI   2026-06-08     7   3  WATCH          77.02    77.76    69.37   +0.19    +1.60  horizon      -  sma+dep+
PUBM   2026-06-08     4   1  WATCH          11.38    11.51    11.01   -1.00    +1.26  stop         1  sma+dep+
SLS    2026-06-08     5   9  WATCH           8.19     8.53     7.07   +3.40    +5.03  horizon      -  sma+dep-
SPCE   2026-06-08     4   1  -               4.29     4.59     4.12   -1.00    +3.36  stop         3  sma+dep-
STG    2026-06-08     5   8  -               3.39     3.41     2.44   +0.63    +1.27  horizon      -  sma-dep-
TE     2026-06-08     3   9  -               9.43    10.40     7.36   -1.00    -0.07  stop         1  sma+dep-
AEHR   2026-06-09     3   2  -              95.58   103.03    84.61   -0.61    +1.28  horizon      8  sma+dep-
BJDX   2026-06-09     4   2  WATCH           4.51     4.74     4.10   -1.00    +0.30  stop         4  sma+dep-
BTDR   2026-06-09     3   2  -              17.47    17.65    15.97   -1.00    +1.03  stop         6  sma+dep+
CRWV   2026-06-09    22   3  TIGHTENING     99.81   100.55    91.02   -1.00    +2.25  stop         8  sma-dep-
GTLB   2026-06-09     5  15  WATCH          30.84    31.53    25.22   +0.04    +0.59  horizon      -  sma-dep-
INFQ   2026-06-09     4   4  -              14.56    14.82    13.15   -1.00    +1.06  stop         1  sma-dep-
MSTR   2026-06-09    19   3  -             120.44   123.97   113.27   -1.00    +1.15  stop         3  sma-dep-
OUST   2026-06-09     4   3  WATCH          39.68    39.80    35.30   +3.17    +3.26  horizon      -  sma+dep-
QUIK   2026-06-09     9   2  WATCH          20.00    21.80    18.07   -1.00    +0.25  stop         7  sma+dep+
SXC    2026-06-09     4   1  WATCH           9.08     9.11     8.84   -1.00    +2.18  stop         4  sma+dep+
XOS    2026-06-09     3   2  -               3.96     4.27     3.30   -1.00    -0.02  stop         1  sma+dep-
ZS     2026-06-09     9   3  WATCH         126.41   129.52   119.50   +0.81    +1.09  horizon      3  sma-dep-
AIRO   2026-06-10     5   1  WATCH           8.29     8.46     7.75   -1.00    +0.09  stop         1  sma-dep+
AVGO   2026-06-10     4   3  -             385.73   393.94   370.55   -1.00    +0.88  stop         1  sma-dep-
AXON   2026-06-10     3   9  -             452.51   456.73   402.00   +2.29    +3.81  horizon      1  sma-dep+
BB     2026-06-10     3   1  -               8.84     9.29     8.70   -1.00    +3.73  stop         4  sma+dep+
BRKR   2026-06-10     3   3  -              56.26    56.63    52.90   +0.95    +1.55  horizon      1  sma+dep+
BWA    2026-06-10     4   1  WATCH          72.63    74.85    71.24   -1.00    +0.46  stop         3  sma+dep+
CORZ   2026-06-10     5   1  WATCH          25.85    27.22    25.24   -0.01    +1.62  horizon      -  sma+dep+
FPS    2026-06-10     3   1  -              57.15    58.21    51.82   -0.48    +1.22  horizon     10  sma+dep+
MOD    2026-06-10    10   1  TIGHTENING    270.70   271.51   251.38   -0.77    +1.56  horizon     10  sma-dep+
MOV    2026-06-10     7   1  WATCH          36.44    38.29    35.92   +0.54    +0.57  horizon      -  sma+dep+
MRCY   2026-06-10     3   1  -             108.82   119.32   105.87   -1.00    +0.21  stop         8  sma+dep+
MRVL   2026-06-10     4   1  WATCH         263.47   280.71   252.26   -0.49    +1.73  horizon      -  sma+dep+
PENG   2026-06-10     5   1  WATCH          59.86    64.33    57.00   -0.28    +1.78  horizon      4  sma+dep+
PSNL   2026-06-10     3   3  -               9.75     9.79     9.14   +5.55    +6.58  horizon      1  sma+dep-
QDEL   2026-06-10     3   1  -              13.94    14.09    12.87   -1.00    +0.74  stop         4  sma-dep+
REPL   2026-06-10     3   5  -               8.97    10.00     8.25   +0.90    +1.43  horizon      -  sma+dep+
RLAY   2026-06-10     5   1  WATCH          13.52    14.24    13.44   +5.37    +5.84  horizon      -  sma+dep-
SDGR   2026-06-10     3   1  -              14.38    14.60    13.90   +3.23    +4.57  horizon      -  sma-dep+
SNX    2026-06-10     5   1  WATCH         268.80   277.09   265.01   -1.00    +1.60  stop        10  sma+dep+
SPRC   2026-06-10     8   1  WATCH           8.73     9.31     8.50   -1.00    -0.10  stop         1  sma-dep-
TWST   2026-06-10     3   1  -              69.22    74.05    67.24   +3.79    +4.43  horizon      -  sma+dep+
TXG    2026-06-10     3   3  -              29.18    32.22    28.01   +1.45    +1.53  horizon      -  sma+dep+
URI    2026-06-10     3   1  -            1067.77  1068.49  1045.92   +2.36    +3.33  horizon      4  sma+dep+
VERU   2026-06-10     3   1  -               3.00     3.26     2.85   -1.00    +0.20  stop         4  sma+dep-
VSH    2026-06-10     4   1  WATCH          57.20    58.60    53.66   -1.00    +2.20  stop         8  sma+dep+
AVBP   2026-06-11     4   1  WATCH          30.35    30.54    30.00   -1.00    +9.80  stop         1  sma+dep+
NMAX   2026-06-11     4  13  WATCH           8.89     9.37     6.52   -0.30    +0.05  horizon      3  sma+dep-
TTAN   2026-06-11     3  13  -              70.71    74.03    60.51   +0.11    +0.63  horizon      -  sma-dep-
VSA    2026-06-11     6   1  WATCH           4.41     4.58     4.13   -1.00    +1.18  stop         5  sma-dep-
AKTX   2026-06-12    10  15  TIGHTENING     13.43    15.48     9.20   -1.00    -0.04  stop         2  sma+dep-
NPT    2026-06-12     3   2  -               2.35     2.38     2.13   +0.28    +3.33  horizon      4  sma-dep-
RDDT   2026-06-12     5   1  WATCH         171.13   181.88   158.36   -1.00    +0.02  stop         2  sma-dep+
CCTG   2026-06-15     3   1  -               0.86     1.48     0.74   -1.00    -0.15  stop         3  sma-dep-
HAE    2026-06-15     3  21  -              78.20    78.50    71.81    cens                        1  sma+dep+
ODC    2026-06-15     3   3  -              94.45    95.10    91.92   +1.45    +3.69  horizon      1  sma+dep+
PAVS   2026-06-15     3   1  -               0.21    19.30    17.01   -1.00    -0.26  stop         -  sma-dep-
ROLR   2026-06-15     6  14  -               6.33     6.56     4.90   +0.10    +0.40  horizon      1  sma-dep-
RXO    2026-06-15     3  21  -              28.35    28.54    24.68    cens                        5  sma+dep+
APPS   2026-06-16     3   5  -               9.76    10.14     8.21   +0.56    +1.80  horizon      -  sma+dep+
CNC    2026-06-16     5   3  WATCH          63.40    63.68    59.90   +0.65    +1.48  horizon      1  sma+dep+
FTRE   2026-06-16     7   4  WATCH          16.08    16.46    14.88   +0.35    +1.19  horizon      -  sma+dep+
HIW    2026-06-16     3   4  -              29.47    29.53    28.45   +1.59    +2.72  horizon      1  sma+dep+
HPP    2026-06-16     4   7  WATCH          15.06    15.37    13.35   +0.02    +0.91  horizon      -  sma+dep+
NEO    2026-06-16     3   2  -              11.09    11.13    10.05   +3.73    +4.11  horizon      -  sma+dep+
NSP    2026-06-16     3   1  -              36.22    37.24    33.50   -1.00    +2.25  stop         2  sma+dep+
OCC    2026-06-16     3   1  -              20.72    21.73    18.80   -1.00    +0.72  stop         3  sma+dep-
PN     2026-06-16     5   9  -               3.73     3.77     3.40   -0.03    +1.01  horizon      -  sma-dep-
VNO    2026-06-16     4   7  WATCH          38.27    39.11    36.31   -0.29    +0.68  horizon      7  sma+dep+
ADPT   2026-06-17     3   1  -              17.22    17.53    16.43   +3.59    +4.77  horizon      -  sma+dep+
BBNX   2026-06-17     5   1  WATCH          13.72    13.88    13.17   -1.00    +4.65  stop         1  sma-dep+
CAR    2026-06-17     6   1  WATCH         181.34   188.43   178.32   -1.00    +0.88  stop         3  sma-dep+
CORT   2026-06-17     3   5  -              82.91    84.75    77.38   +0.97    +1.41  horizon      -  sma+dep+
MBLY   2026-06-17    10   8  -               9.14     9.68     7.66   -0.12    +0.33  horizon      -  sma-dep-
SPHL   2026-06-17     7  12  COILED          3.29     3.31     2.42   -0.89    +0.33  horizon      1  sma-dep-
AZI    2026-06-18     6   4  COILED          1.55     1.98     1.14   -0.52    +1.81  horizon     10  sma-dep-
CCSI   2026-06-22    13   1  TIGHTENING     33.50    33.77    32.36   +1.83    +5.43  horizon      -  sma+dep+
CUPR   2026-06-22     3   2  -               4.37     5.74     3.76   -0.23    +1.27  horizon      -  sma+dep-
DSY    2026-06-22     6   8  WATCH           3.88     4.47     2.52   -0.69    +0.14  horizon      6  sma-dep-
RGNT   2026-06-22     3   7  -               4.29     4.57     3.24   -1.00    -0.02  stop         1  sma+dep-
ROKU   2026-06-22     4   6  WATCH         137.29   138.14   134.36   +1.37    +1.43  horizon      -  sma+dep+
SEPN   2026-06-22     3   1  -              35.17    36.57    34.28   -1.00    +0.62  stop         2  sma+dep+
TRIP   2026-06-22     3   2  -              12.61    12.98    12.07   +0.38    +1.46  horizon      -  sma-dep+
ACLS   2026-06-23     4   2  WATCH         175.44   180.70   164.49   -1.00    +0.65  stop         1  sma+dep+
AIP    2026-06-23     3   2  -              42.14    43.59    39.89   -1.00    +1.80  stop         5  sma+dep+
COHU   2026-06-23     3   2  -              65.45    67.36    62.05   -1.00    +1.36  stop         1  sma+dep+
FWRD   2026-06-23     5   2  WATCH          13.56    14.29    13.05   -1.00    +0.57  stop         3  sma-dep+
ONTO   2026-06-23     4   1  WATCH         316.15   322.24   308.23   -1.00    +4.58  stop         6  sma+dep+
PDFS   2026-06-23     4   1  WATCH          61.07    63.56    59.76   -1.00    +2.14  stop         6  sma+dep+
QTTB   2026-06-23    11   2  COILED         11.89    11.95    10.55   -0.53    +2.19  horizon     10  sma-dep-
VECO   2026-06-23     4   2  WATCH          75.20    75.45    69.36   -1.00    +0.16  stop         1  sma+dep+
HOOD   2026-06-24     3   5  -             103.25   108.65    92.80   -0.17    +0.72  horizon      -  sma+dep+
JBL    2026-06-24     3   1  -             371.88   374.64   365.00   -1.00    +1.22  stop         1  sma+dep+
SHAZ   2026-06-24     3   4  -              84.36    84.66    74.20   -1.00    -0.01  stop         1  sma+dep+
BROS   2026-06-25     3   1  -              67.03    71.85    65.77   -1.00    +0.36  stop         6  sma+dep+
MGNI   2026-06-25     4   1  WATCH          17.45    18.73    17.27   +1.15    +1.84  horizon      -  sma+dep+
QUBT   2026-06-25    21   2  -               9.51     9.92     8.83   -1.00    +0.09  stop         2  sma-dep-
SITM   2026-06-25     6   2  -             677.21   710.47   625.84   -1.00    +0.56  stop         3  sma+dep+
ALAB   2026-06-26     3   1  -             397.02   455.96   372.50   -1.00    +0.52  stop         5  sma+dep+
CRDO   2026-06-26     3   2  -             268.03   271.95   225.66   -1.00    +0.18  stop         1  sma+dep-
EOSE   2026-06-26    16   1  -               6.06     6.09     5.73   -1.00    +0.35  stop         1  sma-dep-
SIMO   2026-06-26     3   1  -             319.00   331.94   294.00   -1.00    +0.24  stop         2  sma+dep+
WDC    2026-06-26     4   1  WATCH         643.83   651.88   579.51   -1.00    +0.17  stop         1  sma+dep-
CRVO   2026-06-29     5   2  WATCH           3.26     3.69     3.05   -1.00    +0.16  stop         8  sma-dep-  [postHTF]
WYFI   2026-06-29     4   1  -              36.82    38.85    32.25   -1.00    +0.29  stop         1  sma+dep-  [postHTF]
EHGO   2026-06-30     7   1  WATCH           1.80     2.66     1.12   -0.44    +0.12  horizon      4  sma-dep-  [postHTF]
NUAI   2026-07-01     6  13  -               5.85     5.91     3.73    cens                        1  sma+dep-  [postHTF]
QUBT   2026-07-02    21   1  -               9.09     9.37     8.94   -1.00    -0.09  stop         1  sma-dep-  [postHTF]
QURE   2026-07-02     9   4  WATCH          44.39    44.48    39.50   -1.00    +0.07  stop         1  sma+dep+  [postHTF]
VCYT   2026-07-02     4   4  WATCH          58.73    59.30    54.25   -0.28    +0.30  horizon      1  sma+dep+  [postHTF]
WNC    2026-07-06     4   6  WATCH          13.25    13.42    11.98   -1.00    +0.40  stop         1  sma+dep+  [postHTF]
BFLY   2026-07-07     4   2  WATCH           7.68     8.02     7.21   -1.00    +0.48  stop         4  sma+dep-  [postHTF]
SVRE   2026-07-07     3   2  -               2.54     2.69     2.30   +2.62    +2.72  horizon      -  sma-dep-  [postHTF]
ULCC   2026-07-07     6   2  WATCH           7.50     7.70     6.92   -1.00    -0.19  stop         1  sma+dep+  [postHTF]
ABSI   2026-07-08     5   1  WATCH          11.11    11.47    10.41   -1.00    -0.05  stop         1  sma+dep+  [postHTF]
CBRL   2026-07-08     3   1  -              49.50    49.51    47.07   +0.95    +2.55  horizon      -  sma+dep+  [postHTF]
GH     2026-07-08     3   1  -             162.92   164.08   152.64   -1.00    +0.08  stop         1  sma+dep+  [postHTF]
SHPH   2026-07-10     8   2  -               3.25     4.16     2.71    cens                        3  sma-dep-  [postHTF]
SLS    2026-07-10     7   2  WATCH          13.27    13.39    12.33   -1.00    +0.32  stop         1  sma+dep+  [postHTF]
MRNA   2026-07-13     4   2  -              68.27    68.28    65.54   -1.00    -0.31  stop         1  sma+dep+  [postHTF]
QLYS   2026-07-13     3   1  -             152.69   164.12   148.31   -1.00    +0.24  stop         5  sma+dep+  [postHTF]
WGS    2026-07-13     5   2  -              65.42    66.14    59.95   -1.00    +0.21  stop         1  sma-dep+  [postHTF]
ODD    2026-07-14     6   1  -              16.52    17.43    16.10   -1.00    -0.01  stop         1  sma-dep+  [postHTF]
VRAX   2026-07-15     3   1  -               3.74     3.90     3.32   -1.00    +0.36  stop         4  sma-dep-  [postHTF]
AMBQ   2026-07-16    17   3  TIGHTENING     75.48    78.14    66.25    cens                        2  sma-dep-  [postHTF]
ATEX   2026-07-16     8   2  WATCH         100.90   101.90    91.00    cens                        3  sma+dep+  [postHTF]
GMM    2026-07-17     4   1  -               3.07     3.51     2.51    cens                        2  sma-dep-  [postHTF]
AGEN   2026-07-20     4   1  -               5.00     5.58     4.94    cens                        -  sma+dep-  [postHTF]
TXG    2026-07-20     3   1  -              43.74    47.20    41.93    cens                        -  sma+dep+  [postHTF]
```

## Appendix B — Cohort printout 2: non-reclaimers / censored

```
ticker undercut     age win  prior      outcome           
BIRD   2026-05-04    12  13  -          no_reclaim        
ROLR   2026-05-04     4  21  -          no_reclaim        
WSHP   2026-05-05    12  13  -          no_reclaim        
MUSA   2026-05-06     3  22  -          no_reclaim        
TORO   2026-05-06     6  19  WATCH      no_reclaim        
AKAN   2026-05-08     4  21  -          no_reclaim        
DNA    2026-05-08     3  22  -          no_reclaim        
HCAI   2026-05-08     3  22  -          no_reclaim        
SKK    2026-05-08     3  22  -          no_reclaim        
AURA   2026-05-11     3  22  -          no_reclaim        
CNSP   2026-05-11     4  21  WATCH      no_reclaim        
EVER   2026-05-11     3  22  -          no_reclaim        
ANAB   2026-05-12     3  22  -          no_reclaim        
CUE    2026-05-12     3  22  -          no_reclaim        
INBX   2026-05-12    13  12  WATCH      no_reclaim        
MCHPP  2026-05-12     3  22  -          no_reclaim        
AVTX   2026-05-13     3  22  -          no_reclaim        
LAR    2026-05-13     3  22  -          no_reclaim        
LIFE   2026-05-13     3  22  -          no_reclaim        
PKX    2026-05-13     3  22  -          no_reclaim        
POWL   2026-05-13     4  21  WATCH      no_reclaim        
RELY   2026-05-13     3  22  -          no_reclaim        
SGMT   2026-05-13    11  14  TIGHTENING no_reclaim        
SNEX   2026-05-13     3  22  -          no_reclaim        
LGN    2026-05-14     5  20  WATCH      no_reclaim        
STRO   2026-05-14     3  22  -          no_reclaim        
ECG    2026-05-15     7  18  WATCH      no_reclaim        
FIX    2026-05-15     3  22  -          no_reclaim        
LWLG   2026-05-15     8  17  WATCH      no_reclaim        
NAMS   2026-05-15     3  22  -          no_reclaim        
SITM   2026-05-15     3  22  -          no_reclaim        
MWH    2026-05-18     3  22  -          no_reclaim        
PWR    2026-05-18     6  19  WATCH      no_reclaim        
NIO    2026-05-19    22   3  -          no_reclaim        
ORN    2026-05-19     9  16  WATCH      no_reclaim        
WRBY   2026-05-19     6  19  WATCH      no_reclaim        
WT     2026-05-19     3  22  -          no_reclaim        
MIAX   2026-05-21     3  22  -          no_reclaim        
NEXT   2026-05-21     3  22  -          no_reclaim        
SLE    2026-05-21     3  22  -          no_reclaim        
CISS   2026-05-22     3  22  -          no_reclaim        
GKOS   2026-05-22    15  10  TIGHTENING no_reclaim        
PBT    2026-05-26     3  22  -          no_reclaim        
VG     2026-05-26     3  22  -          no_reclaim        
EFXT   2026-05-27    11  14  COILED     no_reclaim        
STAA   2026-05-27     7  18  WATCH      no_reclaim        
ARX    2026-05-29     3  22  -          no_reclaim        
ASST   2026-05-29     3  22  -          no_reclaim        
BKKT   2026-05-29     3  22  -          no_reclaim        
SHMD   2026-05-29     3  22  -          no_reclaim        
CELC   2026-06-01    18   7  TIGHTENING no_reclaim        
DXYZ   2026-06-01     3  22  -          no_reclaim        
ERNA   2026-06-01    12  13  TIGHTENING no_reclaim        
FLY    2026-06-01     3  22  -          no_reclaim        
ODYS   2026-06-01    13  12  COILED     no_reclaim        
PCLA   2026-06-01     3  22  -          no_reclaim        
PL     2026-06-01     3  22  -          no_reclaim        
RYOJ   2026-06-01     4  21  WATCH      no_reclaim        
SATL   2026-06-01     3  22  -          no_reclaim        
BRAI   2026-06-02     4  21  WATCH      no_reclaim        
MNTS   2026-06-02     3  22  -          no_reclaim        
NVAX   2026-06-02     3  22  -          no_reclaim        
SG     2026-06-02     5  20  WATCH      no_reclaim        
AMRC   2026-06-03     4  21  WATCH      no_reclaim        
APLD   2026-06-03     3  22  -          no_reclaim        
CPSH   2026-06-03     4  21  WATCH      no_reclaim        
DPRO   2026-06-03     3  22  -          no_reclaim        
LTRX   2026-06-03     3  22  -          no_reclaim        
LUNR   2026-06-03     3  22  -          no_reclaim        
MLGO   2026-06-03     8  17  TIGHTENING no_reclaim        
PDYN   2026-06-03     3  22  -          no_reclaim        
RGTI   2026-06-03     6  19  WATCH      no_reclaim        
RKLB   2026-06-03     4  21  WATCH      no_reclaim        
APP    2026-06-04     3  22  -          no_reclaim        
OLOX   2026-06-04     3  22  -          no_reclaim        
SEDG   2026-06-04     3  22  -          no_reclaim        
ASAN   2026-06-05     3  22  -          no_reclaim        
ASTC   2026-06-05     4  21  WATCH      no_reclaim        
ASTS   2026-06-05     6  19  WATCH      no_reclaim        
CDNS   2026-06-05     3  22  -          no_reclaim        
CMPR   2026-06-05    11  14  TIGHTENING no_reclaim        
CRWD   2026-06-05     3  22  -          no_reclaim        
DGXX   2026-06-05    15  10  TIGHTENING no_reclaim        
DUOT   2026-06-05     6  19  WATCH      no_reclaim        
ESTC   2026-06-05     3  22  -          no_reclaim        
F      2026-06-05     4  21  -          no_reclaim        
HPQ    2026-06-05     3  22  -          no_reclaim        
IPWR   2026-06-05     6  19  WATCH      no_reclaim        
MNDY   2026-06-05     3  22  -          no_reclaim        
MX     2026-06-05     4  21  WATCH      no_reclaim        
NOW    2026-06-05     3  22  -          no_reclaim        
NTAP   2026-06-05     4  21  WATCH      no_reclaim        
ORCL   2026-06-05     3  22  -          no_reclaim        
OXM    2026-06-05     5  20  WATCH      no_reclaim        
RCAT   2026-06-05     3  22  -          no_reclaim        
SAIL   2026-06-05     3  22  -          no_reclaim        
SKLZ   2026-06-05     3  22  -          censored_window   
SRTA   2026-06-05     5  20  WATCH      no_reclaim        
VCIG   2026-06-05     4  21  WATCH      no_reclaim        
ZETA   2026-06-05     3  22  -          no_reclaim        
AMPX   2026-06-08     3  22  -          no_reclaim        
CODX   2026-06-08     6  19  -          no_reclaim        
MASK   2026-06-08     4  21  WATCH      no_reclaim        
UMAC   2026-06-08     3  22  -          no_reclaim        
APTV   2026-06-09     3  22  -          no_reclaim        
ENPH   2026-06-09     8  17  WATCH      no_reclaim        
FSLR   2026-06-09     3  22  -          no_reclaim        
HPE    2026-06-09     4  21  WATCH      no_reclaim        
SWMR   2026-06-10     5  20  -          no_reclaim        
FJET   2026-06-11     4  21  WATCH      no_reclaim        
MRLN   2026-06-11     3  22  -          no_reclaim        
ARCB   2026-06-15     3  22  -          no_reclaim        
LFVN   2026-06-15     8  17  WATCH      no_reclaim        
AXSM   2026-06-16     3  22  -          no_reclaim        
EDHL   2026-06-17     3  22  -          no_reclaim        
GENI   2026-06-17     5  20  WATCH      no_reclaim        
PPCB   2026-06-17     3  22  -          no_reclaim        
LEGN   2026-06-18    10  15  TIGHTENING no_reclaim        
MSTR   2026-06-18    23   2  -          no_reclaim        
STI    2026-06-18     8  17  WATCH      no_reclaim        
AAOI   2026-06-23     8  17  -          no_reclaim        
AXTI   2026-06-23    19   6  WATCH      no_reclaim        
CRE    2026-06-23     3  22  -          no_reclaim        
GLXY   2026-06-23     5  20  WATCH      no_reclaim        
VELO   2026-06-23     6  19  WATCH      no_reclaim        
AMKR   2026-06-24     4  21  WATCH      no_reclaim        
AMPG   2026-06-24     3  22  -          censored_window   
INV    2026-06-24     3  22  -          censored_window   
RXT    2026-06-24     3  22  -          censored_window   
BNAI   2026-06-25    12  13  TIGHTENING no_reclaim        
TRT    2026-06-25     3  22  -          censored_window   
NXTS   2026-06-26     3  22  -          censored_window   
QCOM   2026-06-26    21   4  WATCH      no_reclaim        
ICCM   2026-06-29     6  19  WATCH      censored_window     [postHTF]
BIRD   2026-06-30     5  20  -          censored_window     [postHTF]
PLSM   2026-06-30     3  22  -          censored_window     [postHTF]
CAST   2026-07-01     7  18  -          censored_window     [postHTF]
NWL    2026-07-02     3  22  -          censored_window     [postHTF]
EVC    2026-07-06     3  22  -          censored_window     [postHTF]
DCOY   2026-07-07     4  21  -          censored_window     [postHTF]
ENPH   2026-07-07    24   1  -          no_reclaim          [postHTF]
FCEL   2026-07-07     3  22  -          censored_window     [postHTF]
QBTS   2026-07-07    23   2  -          no_reclaim          [postHTF]
CANF   2026-07-08     3  22  -          censored_window     [postHTF]
UPC    2026-07-09     6  19  -          censored_window     [postHTF]
LHSW   2026-07-10     3  22  -          censored_window     [postHTF]
SLDB   2026-07-10     3  22  -          censored_window     [postHTF]
ABVX   2026-07-13     5  20  -          censored_window     [postHTF]
RGNX   2026-07-13     3  22  -          censored_window     [postHTF]
UMAC   2026-07-13    24   1  -          no_reclaim          [postHTF]
BLZE   2026-07-15     3  22  -          censored_window     [postHTF]
PENG   2026-07-15     3  22  -          censored_window     [postHTF]
RUBI   2026-07-16    21   4  -          no_reclaim          [postHTF]
TDIC   2026-07-17    20   5  -          no_reclaim          [postHTF]
PSNL   2026-07-20     4  21  WATCH      censored_window     [postHTF]
ALIT   2026-07-21     3  22  -          censored_window     [postHTF]
OKTA   2026-07-21     4  21  WATCH      censored_window     [postHTF]
RPD    2026-07-21     3  22  -          censored_window     [postHTF]
CDNA   2026-07-22     3  22  -          censored_window     [postHTF]
DAVE   2026-07-22     3  22  -          censored_window     [postHTF]
MAN    2026-07-23     3  22  -          censored_window     [postHTF]
NVVE   2026-07-23     5  20  -          censored_window     [postHTF]
BIYA   2026-07-24     3  22  -          censored_window     [postHTF]
LCID   2026-07-24     3  22  -          censored_window     [postHTF]
```
