# Dead-zone re-eval (ORB-window extension precision) — 2026-07-09

**#290 · `dead_zone_reevaluation` gated review fired ready** (predicate = distinct missed-HIGH
≥10% winners post-2026-03-20; grew 29 → 155 → this run's 330 unique HIGH_missed). Re-ran the
2026-04-30 analysis on the fatter, trustworthy-timestamp cohort to confirm the conclusion holds.

**Pipeline (prod, read-only):** `scripts.probes.backfill_dead_zone_v2 --days 120` (covers the
2026-03-20 cutoff) → `/tmp/dead_zone_v2.csv` (563 rows post-cutoff) → `analyze_late_detection_v3`.

## The core result — ORB-window extension precision (unique, post-2026-03-20)

late_detection cohort: n=252, positives=58 (a "positive" = a ≥10% forward-5d winner that was missed).

| Extend ORB cutoff to | captures | positives | **precision** | recall |
|---|---|---|---|---|
| 9:50 | 1 | 0 | 0.0% | 0.0% |
| 9:55 | 26 | 5 | **19.2%** | 8.6% |
| 10:00 | 38 | 7 | **18.4%** | 12.1% |
| 10:30 | 38 | 7 | **18.4%** | 12.1% |
| 11:00 | 168 | 40 | 23.8% | 69.0% |

**The real comparator is NOT an asserted 20% — it's this run's own control.** `HIGH_entered`
(the HIGHs we actually took), deduped by (ticker,date): **5/25 = 20.0%** hit ≥10% forward
(raw 7/36 = 19.4%). So the "~20% baseline" the 4/30 write-up asserted is genuinely ~this — and
the extension must be read *against it*, both ways:
- **Near-window (9:55–10:30) = 18–19% ≈ the ~20% control** → statistically indistinguishable from
  the trades we already take, at this N. Modestly extending the cutoff neither clearly beats nor
  clearly trails what we do now.
- **Extend to 11:00 = 23.8% > the control, recall 69%** (40/58 missed winners recoverable) → the
  review's literal trigger ("if precision crosses 20%, reopen") **did fire**. But this captures
  168 tuples (4.4× the 10:00 net) — it abandons the ORB *timing* discipline for an all-day
  late-entry policy, a fundamentally larger entry-discipline change (THE LINE, operator's call).

Precision did rise 12.5% (4/30) → 18–24% here with the fatter cohort. This is **not a clean close**:
late-window precision ≈ entered-trade precision, and the widest window exceeds it at 69% recall.

## Secondary observations (not the review question)
- **Mechanism breakdown:** late_detection 23.0% pos (n=252); **cancelled_unfilled 36.7% pos
  (n=30, 11 winners)** — NOT sparse (criterion (b) expected it sparse post-SIP-flip). These are
  HIGHs cancelled before fill (the 10:00 ET unfilled-cancel job) — 11 were ≥10% winners. Distinct
  from the ORB-extension question; a possible separate thread (why 30 HIGHs go cancelled_unfilled).
- **By-minute:** the 10:30–10:59 bucket is the richest (n=130, 25.4% pos, med_fwd 22.6%) — but
  entering there is the all-day policy, not an ORB extension.

## Decision — operator's (THE LINE); presented straight, not pre-loaded
The literal review trigger fired (23.8% > 20% at the 11:00 window), and late-window precision ≈
entered-trade precision — so this is a genuine fork, not a close-by-default:
- **CLOSE** — accept the residual: the *near-window* extension (~19%) only matches what we already
  take, and the only window that beats it (11:00, 69% recall) means abandoning ORB timing — a
  bigger discipline change than the marginal precision edge justifies. Accept ~1 winner/quarter lost.
- **REOPEN the entry-path question** — 23.8% precision at 69% recall exceeds our own entered-trade
  precision; the missed-winner $ (DGXX +64%, HTCO +60%, TE +49%, APPS +39% — all late_detection)
  is real. Scope a proper late-entry backtest (precision × realized-R × the ORB-timing cost), not
  just precision, before any change. Any live entry-window change = CHANGE_PROCESS + sign-off.

Separately: **cancelled_unfilled = 36.7% pos (n=30, 11 winners)** was expected sparse post-SIP and
is not — a distinct thread worth filing if wanted (why 30 HIGHs go cancelled-before-fill).

*Analysis is read-only; no trade change made.*
