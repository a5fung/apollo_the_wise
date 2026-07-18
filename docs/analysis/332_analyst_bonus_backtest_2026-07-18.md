# #332 Analyst-Bonus Backtest — fix vs remove vs keep (2026-07-18)

**Status: ANALYSIS ONLY.** No scoring code was changed (THE LINE — any live scoring
change is the operator's sign-off, via CHANGE_PROCESS). Probe:
`scripts/probes/_332_analyst_bonus_backtest.py` (read-only; every SQL statement a
SELECT, run over ssh against prod postgres; Yahoo fetches cached in
`/tmp/_332_yahoo_cache.json`).

## TL;DR

1. **The bug is real but has never changed a score.** The cached-tick hardcode
   (`upgrades_30d = 0`, `ep_detector.py:1944`) is inconsistent with the uncached
   path in code — but the uncached path **also always computes 0**, because the
   feed itself is dead (finding 2). Realized fix impact: **0 alerts, 0 tier flips**
   across all 251 retained live alerts (2026-04-13 → 2026-07-17).
2. **The deeper finding: the analyst-upgrades feed has been structurally dead
   since 2026-03-14.** `get_fmp_analyst_ratings` (collector.py:431) reads yfinance
   `Ticker.recommendations`, which in every installed version (prod container:
   yfinance **1.5.1**, verified in-container 7/18) returns the AGGREGATE count
   table (`period|strongBuy|buy|hold|sell|strongSell`). The grade-string matcher
   (`str(g).lower() in ("strong buy", "buy", "outperform", "overweight")`) is
   applied to **integer counts** — it can never match. Verified by running the
   REAL production function inside the live `apollo-market` container:
   `upgrades_30d = 0` for NVDA, AAPL, PLTR — the most analyst-covered names in
   the market — and 0 for all 20 sampled alerted tickers locally. Before
   2026-03-14 the FMP endpoint 403'd on the free tier (commit `5c3f25b`) → also
   always `[]` → 0. **The `>= 3` bonus has never fired in production, ever.**
3. **The bonus carries no outcome signal** (reconstructed counterfactual,
   N=203 alerts with fwd-10d outcomes): bonus-eligible alerts do **not**
   outperform (permutation p = 0.29 overall, 0.18 within-HIGH; mean fwd-10d
   actually *lower* for eligible). At the honest "true upgrades" semantic,
   `>= 3` occurred **once** in 3 months — the threshold is essentially
   unreachable in the EP universe.
4. **Recommendation: REMOVE** (§6). Threading the cached value ("fix") would
   change nothing — it threads a constant 0. Repairing the feed and keeping the
   bonus would add a large-cap analyst-coverage proxy with no measured edge,
   *against* the small/neglected-name profile of the setup.
5. **⚠ Load-bearing downstream implication for #332 itself**: the in-flight C1
   setup-class classifier (worktree `agent-a86701cd0342f4941`,
   `setup_class_classifier.py:75`) gates `episodic_neglect` on
   `upgrades_30d == 0` — under the dead feed **every ticker satisfies it**, so
   that criterion is currently vacuous (the class degenerates to
   mcap-band + price < 70% of 52w-high). The operator pinned this criterion
   7/18; it needs a repaired source (e.g. `upgrades_downgrades`) or a
   different low-coverage proxy before it can discriminate anything.

---

## 1. Mechanism (code facts, at HEAD)

- Bonus: `breakdown["analyst"] = min(analyst_upgrades * 2, 5) if analyst_upgrades >= 3 else 0`
  (`ep_detector.py:1133`). Since `min(3*2, 5) = 5`, the bonus is **always exactly
  +5 raw points** once it fires (never 6; the `* 2` scaling is decorative).
- The +5 lands in `raw_score` **before** the multiplier:
  `final_score = raw_score * regime_multiplier` where the passed multiplier is
  `regime_multiplier * confidence_multiplier` (`:2810`, `:1212`) and
  `regime_multiplier = 1.2 if Bull else 1.0` (`:1370`). So the bonus is worth
  **5.0–7.2 final points** (max: Bull × 1.2 Perplexity-agreement boost).
- Tier: `HIGH if ep_score >= ep_threshold else MODERATE` (`:2826`);
  `ep_threshold` is regime-dependent (`mi_market_regime.ep_threshold`: 65 on
  222 of the retained alert days, 70 on 26, 75 on 4 — the borderline analysis
  uses each alert's own threshold). A MODERATE within bonus-reach of the
  threshold is the flip-risk band.
- Uncached (first-grade) tick: `upgrades_30d` computed from
  `get_fmp_analyst_ratings` (`:2062`, aggregation `:2074`).
  Cached tick: `upgrades_30d = 0` hardcoded (`:1944`) — the #332 bug. The
  proposed fix shape (`_resolve_cached_upgrades_30d`) = add an
  `upgrades_30d` field to `CachedGrade` (`:142`) and thread it; **not built**
  (gated on this backtest).
- `score_breakdown` is **never persisted** — it exists only in the in-memory
  result dict (`:3007`); `mi_ep_alerts` has no breakdown column
  (db.py:2711 insert). The per-tick cached-vs-uncached delta is therefore not
  directly observable in stored data — method + fidelity in §5.
- One alert row per ticker/day: once inserted (score ≥ 50), later ticks skip the
  ticker (`already_today`, `:1853`). So an alert inserted on a cached tick means
  its **earlier graded ticks scored < 50 or were filter-held** — exactly the
  population where a vanishing bonus could bite.

## 2. The feed is dead (Part A — the finding that reframes the card)

Live-mechanism check (the REAL `get_fmp_analyst_ratings` + the verbatim `:2074`
aggregation, per memory `rigor-before-paid-eval-spend`):

| Where run | Tickers | `upgrades_30d` |
|---|---|---|
| Inside prod `apollo-market` container (yfinance 1.5.1) | NVDA, AAPL, PLTR | **0, 0, 0** (4 aggregate rows each) |
| Locally (yfinance 1.5.1, same shape) | NVDA AAPL MSFT PLTR TSLA + 20 alerted tickers | **0 for all 25** |

Root cause: yfinance ≥ 0.2.x moved dated grade rows to `upgrades_downgrades`;
`recommendations` returns the aggregate table. `collector.py:446` finds
`strongBuy` in the columns, then string-matches integer counts against grade
names → 0 rows counted, always. Era history: FMP `/v3/analyst-stock-recommendations`
403'd (free tier) until commit `5c3f25b` (2026-03-14) swapped to yfinance —
so the feed returned 0/empty in **both** eras. All 251 retained alerts
(90-day retention; 2026-04-13 →) were scored with `upgrades_30d = 0` on **every**
tick, cached or not. Two side-effects of the same rot: the "30d" name is also
wrong (the old code read `.tail(10)` = last 10 rows ever), and the function name
says FMP while the body is yfinance.

## 3. Fix impact (Part B)

**Realized impact of the cached-tick hardcode: 0 alerts, 0 tier flips.**
Cached − uncached = 0 − 0 on every tick of every retained alert. "Threading the
real cached value" (the fix in the card) would today thread a constant 0 —
it makes the code honest but changes no score, no tier, no alert.

Mechanical footprint (had the feed worked — the latent exposure of the bug class):

- **34 / 251** alerts were inserted on a **cached tick** (scan-log trajectory
  method, §5): the population whose stored score would have silently lacked a
  real bonus. 152 inserted on their first graded tick; 65 undeterminable
  (pre-2026-04-30 scan-log upsert era).
- **17** stored MODERATEs sit in the borderline band
  (`ep_score < threshold ≤ ep_score + 5×mult`).
- **Would-have-flipped under the bug** (cached tick AND ≥ 3 reconstructed
  upgrades): **0**. The cached-tick borderlines (ASTI 5/27, KSS 5/28) both
  reconstruct to 0 upgrades.
- Would-have-been-HIGH **under a repaired feed** (any tick — this is the feed
  counterfactual, not the bug): 7 of the 17 borderline MODERATEs reconstruct
  ≥ 3 "positive grades" in 30d — TXN (12), VRNS (9), QBTS (5), APPF (3),
  QCOM (3), OKLO (3), KTOS (3). Note the skew: TXN/QCOM/APPF/VRNS are exactly
  the well-covered mature names the eligible cohort over-represents (§4) —
  promoting these is what a repaired `>= 3` count-of-positive-grades bonus
  would actually do.
- **Phantom missed-alert band** (graded ticks that never produced an alert,
  best score in [42.8, 50) — a working bonus could have crossed the 50 insert
  bar): 45 candidate (ticker, day)s; **10** reconstruct ≥ 3 — RCL (5),
  ROKU (14), IFF (3), DDOG (9), RL (4), IMAX (5), WDAY (6), ZM (10), DLTR (3),
  GNRC (3) — uniformly mature, coverage-heavy names (upper bound, since the
  band uses the max 7.2-pt effect). None of these is a cached-tick artifact
  either — the bonus was equally absent on their first ticks.

## 4. Bonus value (Part C — keep-vs-remove evidence)

No realized treatment group exists (the bonus never fired), so the signal is
tested on the **reconstructed** counterfactual: dated analyst events from
yfinance `upgrades_downgrades`, counted in the 30 calendar days ≤ alert_date,
joined to `mi_ep_scan_outcomes` forward returns (same join as
`judge_review.py:31`). Two semantics:

- **code-faithful** — events whose ToGrade ∈ {strong buy, buy, outperform,
  overweight}, any Action (what the live grade-set counts: includes
  reiterations, initiations, even *downgrades into* Buy);
- **strict** — same set AND Action = `up` (a true upgrade).

Results (251 alerts, 203 with fwd-10d):

| Cohort | N (fwd10) | med fwd5 | med fwd10 | mean fwd10 | win10 | perm p (mean fwd10) |
|---|---|---|---|---|---|---|
| ALL, eligible (faithful ≥ 3) | 69 (58) | +8.3% | +10.7% | +12.0% | 93% | — |
| ALL, not eligible | 182 (145) | +6.0% | +8.5% | **+15.1%** | 95% | **0.29** |
| HIGH only, eligible | 46 (39) | +8.4% | +10.3% | +10.8% | 95% | — |
| HIGH only, not eligible | 115 (95) | +6.7% | +8.8% | **+14.9%** | 95% | **0.18** |

- Medians tilt ~+2pp toward eligible; means tilt the **other way** (a few
  large winners sit in the no-coverage cohort — consistent with the
  small/neglected-name profile of the setup); win rates identical. Permutation
  p-values 0.18–0.29: **noise, no reliable edge in either direction.**
- Strict semantic: `>= 1` true upgrade → p-irrelevant tiny tilt (15 vs 188,
  med +11.1 vs +8.8, mean +14.4 vs +14.2 — nothing); `>= 2` → N=3; **`>= 3`
  (the live threshold) → N=1** in three months. The bonus's own threshold, under
  the honest definition of "upgrade", virtually never occurs on an EP candidate.
- What `faithful >= 3` actually selects is **analyst-coverage breadth** (the
  eligible names in evidence: TXN, QCOM, ROKU, DDOG, WDAY, ZM, RCL, DLTR class)
  — a mature-large-cap proxy, i.e. the opposite of the neglect axis the MAGNA53
  rubric already scores directly (`breakdown["neglect"]`, `:1135-1148`).

**Conclusion: the analyst bonus is not signal.** Fwd-return caveat: outcomes are
unconditional close-to-close forward returns on gappers (not trade R); fine for
the relative comparison, not an absolute expectancy claim.

## 5. Method + fidelity limits (stated, not overclaimed)

- **Cached-tick identification is a reconstruction, not a log.** The per-tick
  breakdown is never persisted, so "inserted on a cached tick" is inferred from
  `mi_ep_scan_log` same-day trajectories (an earlier graded row — non-empty
  `catalyst_quality` — precedes the passing row). Blind spots: (a) pre-2026-04-30
  the scan log UPSERTed one row/ticker/day (no trajectory ⇒ 65 alerts
  unclassifiable); (b) a container restart between grade tick and alert tick
  clears the in-memory cache, making the alert tick actually uncached
  (undetectable, rare); (c) pre-#405 (2026-07-03) filter-held tickers weren't
  cached, so some "cached" classifications in that era were really re-grades.
  None of this moves the realized-impact answer, which rests on the feed being
  0 on *both* paths (§2 — verified against the live mechanism, not inferred).
- **Reconstructed upgrade counts are as-known-today.** Yahoo's
  `upgrades_downgrades` is the current snapshot of dated events (revisions/
  pruning possible; window is only ~3 months back, so exposure is low). It is
  used for the *counterfactual* ("what would a working feed have seen"), never
  presented as what the code computed (which was 0, known exactly).
- **Borderline/phantom bands use the max multiplier** where the per-tick
  confidence multiplier isn't stored (phantom band) → upper bounds.
- 251 (ticker, day) alerts from 252 rows (MANE 7/15 double-insert collapses);
  6 rows have judge-voided tier `none` (excluded from tier splits, included in
  ALL); fwd-10d missing for late-window alerts (settling) — Ns stated per cell.

## 6. Recommendation (operator decision; CHANGE_PROCESS + sign-off before any change)

**REMOVE the analyst bonus** — and treat the feed, not the cache-thread, as the
real defect. Evidence stack:

1. Fix-as-scoped is a no-op: threading the cached value threads a constant 0
   (realized impact of the bug: 0 alerts, ever).
2. The bonus has never fired in production; removal is behavior-preserving
   **by construction** on every historical and current tick — the rare
   no-real-money-at-risk case where removal is provably identical to status quo.
3. If the feed were repaired instead, the `>= 3` bonus would select analyst
   coverage breadth, which shows **no outcome edge** (p = 0.29/0.18, mean
   direction negative) and would systematically promote mature covered names
   (TXN/QCOM class) against the setup's neglect thesis; the honest "true
   upgrades ≥ 3" event is a once-a-quarter occurrence — nothing to calibrate on.
4. Keep-as-is preserves dead code plus a misleadingly-named feed
   (`get_fmp_analyst_ratings` is yfinance; "30d" was `.tail(10)`) that a future
   yfinance change could silently re-animate at an uncalibrated +5.

Scope of the removal (when signed): delete the `breakdown["analyst"]` term +
`analyst_upgrades` param threading + the `:1944` hardcode + (grep-check) the
`get_fmp_analyst_ratings` call/fetch if no other consumer; SSoT
`docs/setups/magna53_ep.md` updated in the same commit. **Separately and before
C1 ships**: re-source or re-define the #332 classifier's
`episodic_neglect: upgrades_30d == 0` criterion (§TL;DR-5) — e.g. compute a real
30d upgrade count from `upgrades_downgrades`, or switch the low-coverage proxy —
otherwise the class boundary is vacuously satisfied by every candidate.

If the operator instead wants an analyst axis someday: that is a NEW signal
(real dated-events source, its own threshold calibration, N≥30 via
`data_gated_reviews.yaml`) — not a resurrection of this bonus.

## 7. Reproduce

```bash
# full run (ssh -> prod psql, read-only; Yahoo fetches cached in /tmp)
python scripts/probes/_332_analyst_bonus_backtest.py
# DB-only parts / just the SQL
python scripts/probes/_332_analyst_bonus_backtest.py --skip-yahoo
python scripts/probes/_332_analyst_bonus_backtest.py --print-sql
```

The exact prod SQL (Q1 alerts+regime+outcomes, Q2 scan trajectories, Q3 phantom
band) is embedded in the probe and dumped verbatim by `--print-sql`; all three
are plain SELECTs.
