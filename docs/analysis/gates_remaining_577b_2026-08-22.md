# #577 Card B — Pricing the remaining tail gates (2026-08-22)

**MEASUREMENT ONLY. No criterion changed. Any loosening is CHANGE_PROCESS + operator
sign-off (THE LINE). Card A owns `extension_gate` / `outside_top20` in parallel — not
touched here.**

## Scope and basis

Six gates, ranked by #577's head-start read (excluded names later reaching a ≥100%
20-day peak): `session_rvol_low`, `atr_high`, `pm_rvol_low`, `score_below_50`,
`high_unentered`, `window_missed`.

- Source: `mi_ep_missed_outcomes`, all history through 2026-08-21, read-only, $0.
- **Return basis verified**: every `ret_*`/`max_high_*` is measured from `open_d0`, the
  gap-day OPEN (`missed_outcomes.py:480`) — a day-2 chaser's price, not our ORB-high
  entry. Nothing here is a fill unless explicitly modeled (only `window_missed`'s cutoff
  counts are modeled, and those are submissions, not fills — see below).
- **Maturity**: all 20-day tail/median figures are gated on `ret_20d IS NOT NULL` (a
  settled 20th trading-day close). `max_high_20d` alone is NOT a maturity signal — the
  SQL returns a partial-window max for alerts younger than 20 sessions, which silently
  understates recent rows if not filtered. Several of the freshest genuine
  `window_missed` names (AKTS, BLZE) are still in that unsettled state and are called
  out, not counted.
- **Baseline, so every "survivor" number has something to be compared against**: all
  live HIGH-tier alerts today (filled or not), same open_d0 basis, **price-matched to
  the survivor comparisons below (`open_d0 ≥ $10`)** — **n=164, 86 mature, 7 hits
  ≥50% (8.1%), 0 hits ≥100% (0.0%), median ret_20d −3.2%.** (Unmatched-price version:
  n=184, 99 mature, 9.1%/1.0% — not used below; mixing an unfiltered baseline against
  price-cleaned survivor cohorts would repeat the exact composition error this pass
  corrects elsewhere.) This is what the funnel already produces; a gate is only
  interesting if what it WOULD admit beats this, not some other excluded bucket.
- **Price-correction**: two of six findings below inflate on raw percentages because
  penny stocks move a larger % for the same dollar move (the exact defect the operator
  corrected in `a5680b5`). Every tail rate below that matters for a verdict is split
  `open_d0 < $10` vs `>= $10`, compared against the price-matched baseline above.

## Cascade order (governs which gates below can be checked for downstream survival)

`ep_detector.py`: top-20 gap cap (2798) → **RVOL@T gate** (2929, `session_rvol_low`/
`pm_rvol_low`) → cooldown (2953) → duplicate-scan (3011) → extension (3017,
Card A) → `check_filters`: ADV → **ATR%** (3027, `atr_high`) → market cap →
catalyst/scoring → **score < 50** (4045, last). `high_unentered` and `window_missed`
are downstream of ALL of this — they are alerts that already scored HIGH and cleared
every filter above; they fail at order-submission/fill, not detection.

So: `session_rvol_low`/`pm_rvol_low` populations were never tested against cooldown,
ADV, ATR%, mcap, or score. `atr_high`'s population already cleared RVOL, cooldown,
extension and ADV. `score_below_50` is clean — nothing follows it. `high_unentered`/
`window_missed` are clean in the same sense, but carry a different problem (below).

---

## 1. `session_rvol_low` — the only directional case, and it's inside noise on the ≥50% read

314 blocked / 57 reach ≥50% peak. Current threshold: RVOL@T ≥ 1.0x (unified
2026-05-06 from a legacy 2.0x metric — the raw data mixes both eras; not split
further here, noted as a caveat).

**Downstream survival** (cooldown + extension + ADV + ATR% + cached market cap,
recomputed locally from `mi_daily_closes`/`mi_ep_alerts`/`mi_market_caps`; validated
at 0% false-positive rate by re-running the same checks against `atr_high`'s own
population, which is known to have passed ADV/cooldown/extension live and did in the
replica 100% of the time):

| | n | survives every checkable gate |
|---|---|---|
| Full population | 314 | 216 (68.8%) — upper bound; mcap cache covers only 32%, biased toward already-known larger names (#556's caveat applies again) |
| Tail winners (≥50% peak) | 57 | 28 (49.1%) |

**Price-corrected tail rate of survivors** (real names only, `open_d0 ≥ $10`, vs the
same-priced baseline above):

| population | n mature (20d) | hits ≥50% | ≥50% peak | hits ≥100% | ≥100% peak |
|---|---|---|---|---|---|
| **Baseline (today's admitted pool, ≥$10)** | 86 | 7 | **8.1%** | 0 | **0.0%** |
| Survivors, ≥$10 | 153 | 18 | **11.8%** | 7 | **4.6%** |
| Survivors, confirmed mcap ≥$500M | 46 | 10 | 21.7% | 4 | 8.7% |
| Blocked-downstream anyway, ≥$10 (unreachable by this gate alone) | 60 | 16 | 26.7% | 6 | 10.0% |
| Survivors, <$10 | 31 | 8 | 25.8% | 5 | 16.1% |

**On separability — the ≥50% comparison does not carry weight on its own.** 18/153 vs
7/86 is a 3.6-point gap against a pooled standard error of ~4.1 points (z≈0.9) — inside
noise, not a distinguishable difference. **The ≥100% comparison is the more suggestive
half**: 7/153 vs 0/86, a 4.6-point gap against a standard error of ~2.3 points (z≈2.0,
borderline) — real winners appear in the survivor pool that don't appear in the
admitted baseline at all, even though the ≥50% rates read similarly. Treat this as
directional, not conclusive, at these sample sizes.

The confirmed-mcap survivor set (46 mature, selected because some other lane already
looked the ticker up, not a random sample — the same coverage bias #556 documented,
noted here rather than let the subset read as a cleaner cut than it is) includes real,
liquid, non-junk names: CRDO ($56B), RKLB ($77B), SIMO ($10B), plus AMAT, INTC, WDC,
STX, UMC, VSH, LWLG, BAND, RGNX, QMCO, BLZE, SATL, FCEL. A $56B name failing a
post-open pace check is a metric artifact (large caps need a huge absolute volume
spike to clear a *relative* pace bar their own huge baseline sets), not a liquidity
judgement.

**The <$10 survivor slice (31 names, 25.8%/16.1%) should not be waved off.** #556
Result 4 established that at live position size ($760) sub-$1M/day names are not a
liquidity constraint — the untradeable case was paper size ($15,399), not live. These
31 names already cleared ADV and cached mcap in the survival check above; excluding
them needs a stated reason (spread cost at entry, which was not checked here) rather
than a blanket "penny, less trustworthy." Flagged as reachable, not dismissed.

**But the bigger prize sits behind another wall.** The population still blocked by
ADV/ATR%/mcap even after RVOL is loosened (60 names, ≥$10) has a HIGHER tail rate
(26.7%/10.0%) than what RVOL loosening alone reaches. Consistent with #556 and P9:
this gate is not the binding constraint for the largest winners in its own bucket.

**Verdict: the only candidate of the six with a directional case to loosen, and it is
not conclusive at this sample size.** The ≥100% split (0/86 baseline vs 7/153
survivors) is suggestive; the ≥50% split is not separable from noise. Priced option,
stated as a direction rather than a settled number: admit names that already clear
cached mcap ≥$500M (or are ≥$10 and clear ADV) even if RVOL@T < 1.0x. The survivor
population this would draw from is the 216-of-314 (≥$10 + <$10 combined) full-population
figure above — not a per-day admission rate; a per-day estimate was not derived and is
not stated to avoid a number the operator can't reconcile against the gap-floor
table's format. Not sequenced ahead of the ADV/mcap floor question (#556, #359) per P9,
and worth a larger sample before acting.

## 2. `pm_rvol_low` — earning its keep

182 blocked / 18 reach ≥50%. Same cascade position as above (pre-market anchor).

| population | n mature (20d) | ≥50% peak | ≥100% peak |
|---|---|---|---|
| Baseline (≥$10) | 86 | 8.1% | 0.0% |
| Survivors, ≥$10 | 64 | **1.6%** | 0.0% |
| Survivors, <$10 | 19 | 5.3% | 5.3% |
| Blocked-downstream anyway, ≥$10 | 28 | 28.6% | 14.3% |

Survivors sit clearly BELOW baseline at real prices. The tail in this bucket lives
almost entirely behind ADV/ATR%/mcap, not the RVOL check itself. **Verdict: no case to
loosen.**

## 3. `atr_high` — earning its keep, redundant with market cap

91 blocked / 21 reach ≥50%. Position: after RVOL/cooldown/extension/ADV, before mcap.

Of the population WITH cached market-cap coverage (47.3%), **62.8% would also fail the
$500M floor**; true rate is likely higher given the cache skews toward already-known
larger names (same bias #556 documented). Only 1 of 21 tail winners survives every
checkable downstream gate, and that one survivor (NBIS) is a boundary artifact of the
local ATR% recompute running ~1-2pp low versus the live figure (true live ATR was
15.6%, confirmed over threshold) — the real independent-survivor count is effectively
zero.

| population | n mature (20d) | ≥50% peak | ≥100% peak |
|---|---|---|---|
| Baseline (≥$10) | 86 | 8.1% | 0.0% |
| Survivors (all prices, n too small to split) | 6 | 0.0% | 0.0% |
| Blocked-downstream anyway | 77 | 26.0% | 13.0% |

**Verdict: fully earning its keep — same conclusion as #556's ADV finding, extended
to ATR%.** Not worth loosening alone; near-total overlap with the market-cap floor.

## 4. `score_below_50` — the signal does not survive price-correction

311 blocked / 22 reach ≥50%. LAST gate in the cascade — the cleanest population of
the six, already survived RVOL, cooldown, extension, ADV, ATR%, mcap and top-20.

Score is not monotone by band; the 45-49 band (immediately below the cutoff) looked
strong on a first pass — 37 rows, 20 mature, 20% ≥50% / 15% ≥100%. **Price-splitting
kills it:**

| band | n mature | ≥50% peak | ≥100% peak |
|---|---|---|---|
| Baseline (≥$10) | 86 | 8.1% | 0.0% |
| Score 45-49, open_d0 < $10 | 6 | **66.7%** | **50.0%** |
| Score 45-49, open_d0 ≥ $10 | 14 | **0.0%** | **0.0%** |

Every ≥50% and every ≥100% hit in the band is a sub-$10 name — POET (two alert-days,
$7.32/$9.03, +184%/+130% peak), FCEL ($9.99, +129% peak), PSNL ($6.82, +84% peak).
Two of the four hits are the same underlying company on consecutive days, not
independent events. At real prices (≥$10, n=14) the band shows literally zero tail
hits — WORSE than baseline, not better.

**Verdict: earning its keep at the real-price margin.** The apparent case to loosen
was penny-stock composition, exactly the defect flagged in `a5680b5`. Only the 45-49
band was checked in this pass (flagged by the first look); other bands were not
individually price-split — noted as not fully determined.

## 5. `high_unentered` — a data-integrity bug dominates this gate's numbers

298 blocked / 47 reach ≥50% / 5 reach ≥100% (the task's stated counts). Position:
post-cascade — the alert already scored HIGH and cleared every filter above; this
category is about what happened at order submission/fill, not detection.

**Finding: 279 of 298 rows (93.6%) are stale.** Verified by checking whether a
live-source HIGH `mi_ep_alerts` row still exists for each ticker/date — 279 do not;
their only matching alert is a bulk `historical_scan` replay batch inserted
2026-06-11 (7 tickers written within 6 seconds — a scripted backfill, not live
scanning). The `#268` fix (`missed_outcomes.py`, `source='live'` filter) exists
specifically to exclude replay rows from being counted as missed opportunities — it
works going forward but never retroactively cleaned rows written before it shipped.

**Root cause**: `refresh_missed_outcomes` only rebuilds a rolling 30-day window and
only INSERTs/UPDATEs rows that currently match the query (`missed_outcomes.py`,
`_REFRESH_WINDOW_DAYS=30`). A row that ages out of the window — or that a later
WHERE-clause fix newly excludes — is never pruned or re-validated; it sits frozen
with its original, now-invalid categorization forever. This is a property of the
whole table, not limited to this one incident.

**Checked and ruled out for the other four gates**: `session_rvol_low`, `pm_rvol_low`,
`atr_high`, `score_below_50` all derive from `mi_ep_scan_log` (`scan_filtered` CTE),
which carries no source/replay column and was not targeted by #268. Re-ran today's
live categorization logic against all 898 stored rows (skip_reason → skip_category)
for these four gates: **zero mismatches.** Card A's `extension_gate`/`outside_top20`
are the same `scan_filtered` lineage, so the same check should hold, not independently
verified here (their card, not touched).

**The true `high_unentered` population is 19 ticker-days** (2026-05-20 →
2026-08-11):

| | n | ≥50% peak | ≥100% peak |
|---|---|---|---|
| Task's stated (contaminated) | 298 | 47 | 5 |
| Genuine, mature (settled 20d close) | 9 of 19 | **2 (22.2%)** — ARM +99.8%, ALAB +67.5% | **0 (0%)** |

The stated "≥100%: 5" is entirely a stale-data artifact — zero among the 9 genuine
rows with a settled 20-day close. The other 10 genuine rows are too recent to have a
mature read yet and are not counted either way.

Of the 19 genuine rows: **12 have a normal, explainable mechanism** — order placed at
the ORB high, price never crossed by the 10:00 cancel ("ORB window unfilled"), or
crossed then reverted before fill (`broker:entry_rejected`/`entry_cancelled`). This is
the stop-buy mechanic working as designed, not a gate defect.

**7 of the remaining 8 (all on ONE day, 2026-05-20) plus LZB (06-17) show ZERO
`mi_live_trades` row at all** — `submit_trade_entry` appears never to have been
invoked. 2026-05-20 also shows 15 `dual_account_boot_verified`/`account_mode_active`
audit events that day — suggestive of repeated container restarts, a plausible infra
explanation, **not confirmed further** within this card's $0/read-only budget.

**Verdict: not a "gate to loosen" in the same sense as the others — it's a data bug
plus (separately) an unexplained submission gap.** Two follow-ups, neither fixed here:
(a) the stale-row bug — file for a one-time prune/re-validate of rows outside the
30-day window, or a periodic full-table re-check against current categorization
logic; (b) the 2026-05-20 zero-row cluster — needs an infra root-cause dive, not a
threshold change.

## 6. `window_missed` (09:45 ORB submission cutoff) — cheap to extend, but the settled real-price tail is currently zero

57 blocked / 5 reach ≥50% (task's stated counts). Same CTE as `high_unentered`, same
exposure.

**19 of 57 (33%) are stale** by the identical test — all dated 2026-04-28 to
2026-05-08, before the #268 fix. True population: **38 genuine ticker-days**
(2026-05-14 onward).

**Cutoff-extension recovery — submissions, not fills; no fill model run** (#557's
caution applies directly: CORZ/COHU/FLNC/KMT-style no-fills are plausible here too,
and one of #557's own modeled cases, ALOY, peaked +98% on paper but was a −1R loser
under the real entry/stop rules):

| extend cutoff to | recovers | % of genuine misses |
|---|---|---|
| 09:50 (+5 min) | 7 of 38 | 18.4% |
| 09:55 (+10 min) | 28 of 38 | 73.7% |
| 10:00 (+15 min) | 34 of 38 | 89.5% |

Of the 12 genuine rows with a settled 20-day close, 1 reached ≥50% peak: ALOY +119%.
**Price-split, the same way the score_below_50 band was: ALOY's `open_d0` is $9.39 —
sub-$10.** At real prices (≥$10, n=10: ARX, QFIN, BBWI, IREN, PENG, POWI, ANF, HAS,
VIK, CPA) the settled evidence is **zero hits**, against the price-matched baseline of
8.1%. The two names that would carry a real-price case, AKTS ($21.36) and BLZE
($13.47), are both ≥$10 but both still unsettled (partial-window reads only: AKTS
+60%, BLZE +78%) and not counted here.

**The TWST anecdote needs a caveat.** The operator's account: real-time gap crossed
10% at 09:30:04, the delayed feed didn't confirm ≥9% until 09:45:11 — 11 seconds after
the cutoff. This table's own logged "detected" timestamp for TWST is **09:55**, ten
minutes later. The table's detection timestamps are a lagging proxy for the true
tick-level miss — meaning the recovery percentages above are a **lower bound**, and
the binding constraint for a case like TWST may be feed latency rather than the 09:45
line itself. That is a different problem with a different fix; not resolved here.

**Verdict: the recovery table is real and cheap to extend, but the case is not yet
"well-bounded" — the settled tail evidence at real prices is zero of 10, and the whole
case currently rests on two unsettled ≥$10 names plus one settled sub-$10 name.** A
5-10 minute cutoff extension is real and priced above (submissions, not fills). Before
any change: (a) let AKTS/BLZE mature and re-check at real prices, (b) run a fill model
on the 38 genuine misses (per #557's method) — a "detected in time" count is not a
trade count, and ALOY, the only settled proof point at any price, is exactly the shape
#557 showed can lose under real entry/stop rules on a different date.

---

## What this pass did NOT determine

- No fill model for `window_missed`'s recovered names — recovery = submission
  eligibility, not trades. Priced as the next step, not run here ($0 budget, time-boxed).
- `high_unentered`'s 2026-05-20 zero-row cluster: infra-instability signal noted
  (15 boot-adjacent audit events that day), not root-caused.
- Only the score 45-49 band was price-split for `score_below_50`; other bands were
  not individually re-examined once the 45-49 signal collapsed.
- Market-cap coverage for the downstream-survival checks is a 32-47% cache, same
  known bias as #556 (skews toward larger, already-known names) — true survival rates
  for `session_rvol_low`/`atr_high` are likely somewhat below what's shown.
- The legacy 2.0x-threshold era mixed into `session_rvol_low`'s raw data (pre
  2026-05-06 unification) was not split out as its own regime — noted, not corrected.

## Scope note

PLAN.md's #577 entry (re-sequenced 2026-08-21) says price only `extension_gate` and
`outside_top20` when the sweep runs, on the view that admission-side work only pays
once conversion works (P9), and that a lone gate move is usually a no-op (#556). This
card was directed by the orchestrator to cover the remaining tail in parallel with
Card A regardless — noted for the record, not re-litigated here; the work is
read-only and priced nothing live.

## Files

- Analysis (this doc): `docs/analysis/gates_remaining_577b_2026-08-22.md`
- Captures (session scratchpad, not committed): `577_all_tail_winners.psv` (shared
  input), `577b_early_gate_rows.psv`, `577b_daily_closes.psv`, `577b_ep_alerts.psv`,
  `577b_market_caps.psv`, `577b_survival.py` + `577b_survival_detail.psv`,
  `577b_admitted_baseline_ge10.sql`, `577b_admitted_baseline_ge10_counts.sql`,
  `577b_srv_price.psv`, `577b_score4549_price.psv`,
  `577b_hu_genuine*.{sql,out}`, `577b_wm_stale_detail.sql`, `577b_wm_mature_price.sql`,
  `577b_0520_incident.sql`.
- Prior related studies: `docs/analysis/adv_floor_556_2026-08-20.md` (method
  template + the mcap-cache bias this reuses), `docs/analysis/cooldown_cost_557_2026-08-21.md`
  (the fill-model caution this reuses for `window_missed`).
