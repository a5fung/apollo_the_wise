# #482 — Bracket-Geometry Evidence Lab: design + FIRST backtest read (2026-07-18)

**⛔ THE LINE — MEASURE-BEFORE-WIRE.** Operator ruling 7/18: the live 1-min ORB bracket
STAYS; alternatives are SHADOWED; the decision comes from evidence. This doc changes NO
entry/stop/exit/sizing code. Everything here is read-only reconstruction over already-pulled
data + a design for forward telemetry. Any live geometry change = operator sign-off +
`docs/setups/CHANGE_PROCESS.md` + the evidence gates below.

**Inputs (all local, re-runnable offline):** the #468 TSVs
(`scripts/probes/_468_{cohort,trades,daily,minute}.tsv` — REUSED, not re-pulled; minute data
is DAY-0 ONLY) + the #468 reconstruction machinery
(`scripts/probes/_468_moderate_realized_r.py`, `anticipation.simulate`/`build_mixed_path`/
`SETTLE_RULE` — the #327 primitives).
**Generator for every number here:** `scripts/probes/_482_bracket_geometry_lab.py`
(parity-asserted against the #468 reconstruction row-by-row: 0 mismatches on 105 evaluable).
**Baseline context:** `docs/analysis/468b_high_realized_r_diagnosis_2026-07-18.md` — the
1-min bracket is ~zero-edge on the HIGH cohort (recon mean +0.02R, win 29%, top-3 = 449% of
total; 20/21 losers on stocks that then rose; median 12-min hold). NB: the realized cohort is
paper-dominant (26 paper / 5 live) — this is SETUP realized-R, not the live book.

---

## 0. TL;DR — first-read verdict

| Variant | Filled mean R (n) | vs BASE +0.02R (72) | Verdict |
|---|---|---|---|
| **(d) V-ATR 0.5×** (stop = entry − 0.5·ATR14, same entries) | **+0.11R (72), total +7.8R, ex-top3 mean +0.03R** | best single lever: de-lotteries the edge (top-3 share 449%→77%) | **PROMISING but period-fragile** — all lift is in the polluted window; clean n=30 reads −0.10R vs BASE +0.11R. Forward-shadow it. |
| (d) V-ATR 1.0×/1.5× (the literal wider-stop hypothesis) | +0.01R (72) | flat; win% rises to 40-47% but R shrinks | **NOT CONFIRMED in this frame** — but the SETTLE frame structurally punishes wide stops (§5); needs the %-target re-frame before ruling out |
| (a) V-5M (5-min ORB bar) | +0.14R (31) | full-universe +0.07R vs +0.01R — but paired per-name −0.14R and the lift decomposes into a width-FILTER artifact (§4a) | **WEAK** — apparent edge is selection, period-fragile, clean n=11 = −0.56R. The #94 forward lane already accrues this — read it (§7 Q1) before building anything |
| (d) V-STRUCT (stop = prior-day low) | −0.04R (72) | stop 18.3% of entry — R-geometry uninvestable at day-5 horizon | drop (or re-frame with %-targets) |
| (b) V-REENTRY v0 (day-0 re-break, ≤2 re-entries) | −0.05R (72) | 19 chains, re-entry attempts net **−5.1R** | **NEGATIVE in v0** — day-0 chop begets chop. Day-1+ chains unmeasured (needs the §6 pull) |
| (c) V-ESTLOW v0 (15-min established low, reclaim entry) | −0.11R (65) | paired −0.41R vs BASE | **NEGATIVE in v0** — waiting costs price (median fill 9:48) without R compensation. Day-1 reclaims + alternative triggers unmeasured (§6) |

**Honest headline: NO variant robustly beats the ~zero-edge baseline on the clean window at
this N.** The strongest signal (V-ATR 0.5×) is a *redistribution* — more frequent small wins,
capped tails (it turned QURE +1.56R→−1.00R, KURA/ABSI/STRL +2R→0R) — not a fix for the
shakeout mechanism (it rescued only 12 of 30 recon losers-on-rising-stocks; day-0 exits went
UP, 67/72). This corroborates #468b's ranking: **the leak is exit-management first (#306 W3),
geometry second** — and the geometry decision should be made from forward-shadow evidence,
not from this backtest alone.

---

## 1. Lab architecture

Two arms, one set of pinned variant definitions (§2 is the SSoT for both — backtest and
shadow must measure the SAME rules or the comparison is garbage).

**Arm 1 — backtest (this read, extensible):** pure-local reconstruction over the #468 TSVs.
All variants share one fill engine (the live stop-limit model: crossed-in-bar → trigger px;
open between trigger and limit → open; gap-past-limit → armed, fills on pullback into limit)
and one exit frame (`SETTLE_RULE` +1R/+3R halves, day-5 time stop, `pess` intrabar bound,
over `build_mixed_path` day-0-minute + daily-forward). Identical rule across arms ⇒ the
comparison isolates geometry. Extends at full fidelity once the §6 pull lands.

**Arm 2 — forward shadow (measure-before-wire):**
- **Variant (a) already HAS a live forward lane** — `broker/shadow_orb_tracker.py` (#94):
  strategy `shadow_orb_5m`, phase `shadow`, table `mi_orb_shadow_trades`, crons
  `shadow_orb_entry` 10:00 ET + `shadow_orb_exit` 16:30 ET, registered promotion thresholds
  (`unpaired_r`, `min_closed: 30`). **First action is a READ, not a build** — §7 Q1/Q2 tell
  us how much 5-min evidence has already accrued and whether the switch is on.
- **Variants (b)/(c)/(d) get a new EOD shadow pass** (Sunday build, §8): a 16:35 ET job that
  takes the same candidate universe as #94 (`_fetch_magna53_high_pre_open` — HIGHs created
  before 09:31, the alert-race-correct set), fetches day-0 minute bars
  (`alpaca.get_minute_bars_window`), runs the SAME pure reconstruction functions as this
  probe (lifted into a broker-import-free module), and writes one row per variant per
  candidate into `mi_orb_shadow_trades` with a `variant` tag (new nullable TEXT column;
  existing #94 rows keep `variant IS NULL` semantics). Settlement: a sweep in the same job
  settles rows ≥5 forward trading bars old under `SETTLE_RULE` (frame-consistent with this
  backtest so forward evidence EXTENDS these curves; #94's 5m lane keeps its live-exit
  `apply_daily_exit_step` frame — do not touch it, note the frame difference in any render).
  Pure compute + DB + audit log. **No Alpaca submits, no Telegram, no live-table writes.**

**Decision gate (operator-owned):** per-variant `min_closed ≥ 30` settled shadow rows
(matches the registered #94 threshold), then an operator read of median/mean/win/ex-top3 vs
the concurrent live 1-min book — filed as an evidence-gated review referencing #482. No
variant ships without CHANGE_PROCESS + backtest-at-full-fidelity + operator sign-off.

## 2. Pinned variant definitions (the lab SSoT)

- **BASE (live):** ORB bar = earliest 1-min bar in 9:30–9:35; entry = stop-limit buy,
  trigger @ ORB-high, limit = max(hi·1.005, hi+$0.02); stop = ORB-low; width gate: range >
  1.5×ATR14 (prior-close Wilder) → skip; submission = max(detection, 9:31), detection ≥ 9:45
  → out-of-window; unfilled at 10:00 → cancel.
- **(a) V-5M:** ORB hi/lo over ALL 9:30–9:34 1-min bars; armed from 9:35; everything else
  identical to BASE (incl. the 1.5×ATR width gate — mirrors `shadow_orb_tracker`).
- **(b) V-REENTRY v0:** BASE first; after a FULL day-0 stop (single fill, day-0, full
  position, r<0), re-arm trigger @ the ORIGINAL 1-min ORB-high; stop = the pullback low
  between the stop-out bar and the re-break bar; ≤2 re-entries; re-entry fills until 15:30
  ET; equal $-risk per attempt (chain R = Σ attempt R). Day-1+ stops do NOT chain in v0
  (data limit, §6).
- **(c) V-ESTLOW v0:** running intraday low; **"established" = un-undercut for ≥15
  consecutive minutes** (an undercut resets the clock; pess ordering — an undercutting bar
  cannot also fill); once established, first bar at/above the 1-min ORB-high fills (open if
  already above, else trigger px); stop = the established low; fills until 15:30 ET; day-0
  only in v0. v1 candidates (doc'd, unmeasured): trigger = high-since-the-low
  (higher-low reclaim) instead of ORB-high; M = 10/20/30 min grid; day-1 reclaim window.
- **(d) V-ATR(k):** entries identical to BASE (same fills — isolates the stop lever); stop =
  entry − k·ATR14, k ∈ {0.5, 1.0, 1.5, 2.0} ("pure"), and max(ORB-low, entry − k·ATR14)
  ("capped" — the tighter-of form; degenerates to BASE for k ≥ 1.5, verified). ATR known for
  all 72 fills. **V-STRUCT:** stop = prior day's low (9M-style).

## 3. First read — the numbers (HIGH cohort, n=105 evaluable, 2026-03→07)

Eligibility funnel (identical to #468 primary): alerts 161 → window_out_of_orb 52,
not_settleable 4 → 105 evaluable. Clean = outside 2026-05-11→06-24 (the judge-pollution
window, per #468).

| Variant | fill rate | n | median | mean | win% | total | top3-share | ex-top3 mean | day-0 exits (neg) | stop dist | paired Δ vs BASE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **BASE 1-min** | 72/99 (73%) | 72 | −1.00R | **+0.02R** | 29% | +1.3R | 449% | −0.07R | 61 (35) | 3.0% | — |
| V-5M | 31/60 (52%) | 31 | +0.00R | +0.14R | 35% | +4.5R | 135% | −0.06R | 18 (13) | 4.9% | −0.14R (n=31) |
| **V-ATR 0.5× pure** | 72/99 (73%) | 72 | +0.00R | **+0.11R** | 32% | **+7.8R** | **77%** | **+0.03R** | 67 (31) | 2.4% | **+0.09R** (n=72) |
| V-ATR 0.5× capped | 72/99 | 72 | +0.00R | +0.11R | 32% | +7.9R | 76% | +0.03R | 70 (32) | 2.1% | +0.09R |
| V-ATR 1.0× pure | 72/99 | 72 | +0.00R | +0.01R | 31% | +0.8R | 745% | −0.08R | 45 (28) | 4.7% | −0.01R |
| V-ATR 1.5× pure | 72/99 | 72 | +0.00R | +0.01R | 40% | +0.5R | 1180% | −0.08R | 26 (22) | 7.1% | −0.01R |
| V-ATR 2.0× pure | 72/99 | 72 | −0.01R | −0.05R | 44% | −3.7R | — | −0.14R | 18 (18) | 9.4% | −0.07R |
| V-STRUCT (prior-day low) | 72/99 | 72 | −0.04R | −0.04R | 47% | −2.8R | — | −0.12R | 5 (4) | 18.3% | −0.06R |
| V-REENTRY v0 | 72/99 | 72 | +0.00R | −0.05R | 32% | −3.8R | — | −0.14R | 42 (16) | 3.0% | −0.07R |
| V-ESTLOW v0 | 65/105 (62%) | 65 | −1.00R | −0.11R | 32% | −6.9R | — | −0.21R | 23 (21) | 6.2% | −0.41R (n=56) |

Clean/polluted splits (the stability check):

| Variant | clean filled | polluted filled |
|---|---|---|
| BASE | n=30 **+0.11R** (win 30%) | n=42 −0.05R |
| V-5M | n=11 **−0.56R** (win 9%) | n=20 +0.53R (win 50%) |
| V-ATR 0.5× pure | n=30 **−0.10R** | n=42 +0.26R |
| V-ATR 1.5× pure | n=30 +0.09R (win 47%) | n=42 −0.05R |
| V-ESTLOW v0 | n=30 −0.04R | n=35 −0.16R |

## 4. Reading each variant

**(a) V-5M — the apparent lift is a filter artifact, not better geometry.** Its 1.5×ATR
width gate at 5-min scale skips 45/105 (vs 6 at 1-min); on the 31 names both arms fill, 5-min
is WORSE per-name (Δ −0.14R mean; improved 4 / worsened 11 / same 16). The 30 BASE-filled
names it skips had BASE mean +0.11R — and applying "skip if 5-min range > 1.5×ATR" as a pure
filter ON the 1-min bracket reads NEGATIVE (kept n=42 mean −0.05R vs skipped +0.11R), with a
perfect clean/polluted sign flip (clean skipped names were the BEST base performers, +0.59R).
At this N the width-filter "signal" is period-anticorrelated noise. **Verdict: weak; the #94
forward lane is the right adjudicator — read its accrual first (§7 Q1).**

**(b) V-REENTRY v0 — negative.** 19 of the 35 day-0 full stops re-broke the ORB-high same
day; those re-entry attempts summed **−5.1R** (attempt histogram 1×53 / 2×17 / 3×2). On this
cohort, a day-0 shakeout followed by a same-day re-break is mostly another chop leg, not the
real move. Unmeasured in v0: chains after day-1+ stops (needs §6) and re-entry off a
HIGHER-low trigger rather than the same ORB-high. Not a build candidate until the fuller
read.

**(c) V-ESTLOW v0 — negative as specified.** Median entry 9:48 (establishment can't complete
before 9:46); by then runners are extended (v0 pays the market price at establishment if
above trigger) and the stop (established low) is 6.2% away — the R-denominator doubles while
entry worsens. Paired Δ −0.41R is the worst of any variant. The interesting unmeasured
version is the PULLBACK case: names that break, fail, put in a HIGHER low, and reclaim — that
needs the higher-low trigger variant + day-1 window (§6).

**(d) V-ATR — the one promising lever, with honest caveats.** 0.5×ATR re-stopping (tighter
than ORB-low on 43/72, wider on 29) lifts total from +1.3R→+7.8R and flips ex-top3 mean
positive (+0.03R): the edge stops being a 3-name lottery (top-3 share 449%→77%). Mechanism:
risk shrinks ⇒ the +1R/+3R targets come proportionally closer ⇒ the same day-0 movement
banks partials far more often. It is a *scalp-ification* of the bracket, NOT the
"wider stop stops shakeouts" fix — day-0 exits went UP (67/72), it rescued only 12/30
geometry victims, and it CAPS tails (QURE +1.56→−1.00, ABSI/KURA/STRL +2.00→0.00). And the
lift is entirely in the polluted window (clean −0.10R vs BASE +0.11R). The literal
wider-stop forms (1.0–2.0×) read flat-to-negative **in this frame** — but see §5: the frame
itself penalizes them. **Verdict: forward-shadow V-ATR 0.5× (and 1.5× as the wide
representative); do not ship anything off this read.**

## 5. Fidelity limits (pre-committed honesty)

1. **Day-0-minute-only:** days 1–5 settle on DAILY bars under `pess` (stop-first on
   ambiguous bars, gap-throughs fill at open). Wider stops are hit less often on daily bars,
   so this mostly penalizes tight stops — the direction is conservative for V-ATR 0.5×.
2. **The SETTLE frame structurally punishes wide stops:** targets scale with risk (+1R at a
   9.4% stop = a 9.4% move within 5 days) and the day-5 time stop closes the rest at ~0R.
   V-ATR 1.5×/2.0×/V-STRUCT "flat" reads are therefore NOT a fair kill — a wide-stop variant
   needs %-move targets or a longer settle horizon to be judged (Sunday item, §8-3). The
   R-comparison across risk bases is itself fair (equal $-risk sizing), but the exit rule's
   R-parameterization means each V-ATR(k) is a different whole trade plan, not just a stop.
3. **Small N, period-concentrated:** clean-window cells are n=11–30; every variant's
   clean/polluted split flips somewhere. The #468 tail-sensitivity holds: one or two ±2R
   tails swing any mean by ±0.3R.
4. **Cohort caveats carried from #468/#468b:** paper-dominant realized book (26/5), the
   −0.40R live-vs-SETTLE calibration haircut applies to ALL arms equally (paired frame), and
   the reconstruction's stop-limit fill model showed +4.3R of partial-fill accounting
   distortion in the live book that NO reconstruction (base or variant) carries — variant
   deltas are geometry-clean but absolute levels are idealized.
5. **V-REENTRY/V-ESTLOW are v0 truncations** (day-0 only, single trigger definition) — their
   negatives are informative but not terminal.

## 6. What needs more data — the pull (WRITTEN, not run; orchestrator executes)

**Who needs it:** (b) re-entry chains after day-1+ stops · (c) est-low day-1 reclaims +
the higher-low trigger grid · (bonus) minute-fidelity day-1..5 exits for ALL arms (removes
fidelity limit §5-1).

**The pull** — extends minute coverage from day-0 to day-0..+9 calendar days for the same 245
(ticker, alert_date) pairs, via the same in-container Polygon read path as #468 (read-only
market data; ~245 range calls, ~30–45 MB TSV):

```bash
python scripts/probes/_482_bracket_geometry_lab.py --pull-minute-fwd
# writes scripts/probes/_482_minute_fwd.tsv (ticker \t t_ms \t o h l c v)
```

(Implementation already in the probe: `pull_minute_fwd()` — one
`v2/aggs/ticker/{t}/range/1/minute/{alert_date}/{alert_date+9d}` call per pair through
`ssh apollo@87.99.134.162 docker exec apollo-market python`, 0.12s throttle, stderr `# ERR`
capture. Nothing else in the probe touches prod.)

## 7. Prod SELECTs for the orchestrator (read-only)

**Q1 — how much 5-min forward evidence has the #94 lane ALREADY accrued?** (If ≥30 closed,
variant (a) may already be decidable without building anything.)
```sql
SELECT status, COUNT(*) AS n, MIN(alert_date) AS first, MAX(alert_date) AS last
FROM mi_orb_shadow_trades
WHERE signal_type = 'magna53'
GROUP BY status ORDER BY status;
```

**Q1b — its closed R distribution (live-exit frame; compare vs BASE actual, not vs §3):**
```sql
SELECT ticker, alert_date, entry_price, stop_price, risk_dollars, total_pnl,
       ROUND((total_pnl / NULLIF(risk_dollars, 0))::numeric, 2) AS r_mult
FROM mi_orb_shadow_trades
WHERE signal_type = 'magna53' AND status = 'closed' AND risk_dollars > 0
ORDER BY alert_date;
```

**Q2 — is the shadow_orb_5m master switch on?** (`should_run` fail-opens if unregistered.)
```sql
SELECT strategy_id, enabled, phase FROM mi_strategies
WHERE strategy_id = 'shadow_orb_5m';
```

## 8. Sunday BUILD plan (concrete; no live entry/stop code anywhere in it)

1. **Read Q1/Q2/Q1b** (5 min). If the #94 lane has ≥30 closed 5m rows → summarize for the
   operator alongside §3-4a; the (a) decision may be evidence-ready with zero build.
2. **Run the fuller pull** (`--pull-minute-fwd`, ~10 min incl. throttle).
3. **Extend the probe to full fidelity** (~1-2h, local only): loader for
   `_482_minute_fwd.tsv`; minute-fidelity settle for all arms (mixed path day-0..5 minute);
   re-entry chains across day-1+ stops; est-low day-1 window + higher-low-trigger and
   M ∈ {10, 20, 30} grid; the %-target re-frame for wide stops (§5-2) — re-issue §3 as the
   SECOND read.
4. **Build the variant shadow pass** (~2-3h, market-agent scope):
   - Lift `fill_scan` / `reconstruct_5m` / `reentry_chain` / `reconstruct_estlow` + the ATR
     re-stop into a pure module (e.g. `agents/market_intelligence/broker/bracket_lab.py`,
     zero broker-submit imports) — probe imports it back (one source of truth for the
     definitions in §2).
   - Migration: `ALTER TABLE mi_orb_shadow_trades ADD COLUMN variant TEXT` (nullable; #94
     rows stay NULL). Telemetry table only — no live-trade surface.
   - New 16:35 ET job (`bracket_lab_shadow`, EXECUTION-owned, after `shadow_orb_exit`):
     universe = `_fetch_magna53_high_pre_open(today)` (reused); day-0 bars via
     `alpaca.get_minute_bars_window`; write one row per variant (V-ATR0.5, V-ATR1.5,
     V-REENTRY, V-ESTLOW) per candidate; a settle sweep in the same job settles rows with
     ≥5 forward trading bars under `SETTLE_RULE` (frame-consistent with the backtest).
     Failures → `mi_audit_log` + `notify_job_failure` (existing pattern).
   - Tests: golden per-variant reconstruction on a fixture day from the TSVs; funnel counts
     pinned; a no-broker-imports guard test on `bracket_lab.py`.
5. **Surface** (orchestrator-scope check): extend `/audit shadow_orb` to render per-variant
   cuts (n, settled, median/mean/win, frame label). **Verify the operator-facing render**,
   not just the rows ([[verify-operator-facing-surface]]).
6. **File the evidence gate:** PLAN.md task under the EP project (ETA = first review date) +
   `data_gated_reviews.yaml` predicate `variant settled_n >= 30` referencing #482 — the
   decision is the operator's, from the accrued evidence.

Deploy scope for 4: `market-agent` (+ `orchestrator` only if step 5 touches
`channels/telegram.py`). Verify-live = shadow rows present for the next live EP day + the
/audit render showing them.

---

*Written 2026-07-18 under THE LINE: measure-before-wire, no live entry/stop change, not
committed. Generator: `scripts/probes/_482_bracket_geometry_lab.py` (parity vs #468: OK).*
