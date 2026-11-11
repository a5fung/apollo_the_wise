# B6 composite gate (composite_min = 22) under the post-2026-08-22 admission system — 2026-11-10

Review `b6_gate_inversion_post_rescale` fired (predicate 22 of 15). $0 read: one read-only pull
(`scripts/probes/_b6_post_rescale_1110/q1.sql` → `q1.out`, last bar 2026-11-09), stats in `stats.py` → `stats.out`.

**Result: the tail LEANS inverted under today's rules, but the sample cannot carry a live change.**

| 5-session return from alert-day open | n | ≥ +20% | p90 | median | win |
|---|---|---|---|---|---|
| post-rescale PASS | 24 | **0 (0%)** | +10.3% | −0.6% | 50% |
| post-rescale DOWNGRADE | 84 | **7 (8%)** | +17.6% | +2.5% | 56% |
| pre-rescale PASS (separate column, never pooled) | 57 | 4 (7%) | +15.5% | −3.0% | 44% |
| pre-rescale DOWNGRADE | 150 | 10 (7%) | +15.8% | +1.1% | 58% |

- 20 sessions: post PASS 0 of 7 reached +20% vs DOWNGRADE 3 of 31; too few settled to read.
- Zero of 24 happens 12% of the time even if PASS names were exactly as good as DOWNGRADE names (8% per name) — suggestive, not evidence.
- The downgraded names that ran: NTSK 09-14, FPS 09-15, BETR 10-15 (+106%), EAF 10-26, HRI 10-27, HAYW 10-28, GDYN 10-30.
- No downgrade carried a non-composite reason (0 OTHER rows), so PASS/DOWNGRADE are exhaustive, as on 09-15.

## Population and method
- **Rows:** every `mi_ep_catalyst_metrics` row with `q_revenue_yoy_pct` not null, alert_date 2026-05-19..2026-11-10 (413 rows), split at the 2026-08-22 rescale into pre and post. The post era is today's admission system; the two eras are never pooled.
- **Live verdict:** PASS = no `catalyst_earnings_revenue_weak_downgrade` audit event of any reason for that (ticker, alert_date) — the predicate's own definition; DOWNGRADE = an event whose reason is `rubric_composite_*`. 0 rows carried another reason.
- **Outcome:** from raw bars in `mi_daily_closes` — close N sessions after the alert day minus the alert-day open, over the alert-day open (N = 5 and 20; the alert day's own bar must exist). Only settled rows count. p90 is nearest-rank, as in the 09-15 doc.

## The inherited side finding, explained
- A `mi_ep_catalyst_metrics` row is written during ENRICHMENT (`ep_detector.py` ~5453: earnings-day + strong/game_changer catalyst), BEFORE the tier decision; `mi_ep_alerts` only gets rows that go on to alert. So a scored row with no alert = a candidate the scorer later dropped for another reason.
- Post-rescale that is most of them: 33 of 54 PASS rows and 148 of 152 DOWNGRADE rows have no alert. The gate does act — of 152 names it cut, 4 still alerted.
- Alerted-only post-rescale: PASS 0 of 9 ≥ +20%, DOWNGRADE 0 of 2 — no read possible. The full scored population stays primary because it answers the gate's own question: did the names it cut do better than the names it kept?

## Decision
- Fork B (neutralise the composite's downgrade authority) is the operator's call (THE LINE). Status quo (keep 22) needs no sign-off.
- Recommendation: keep 22; re-read at 50 settled post-rescale PASS rows, judged on the same tail rule declared here BEFORE the data: bring fork B if PASS's share ≥ +20% at 5 sessions is under half DOWNGRADE's with ≥ 50 PASS rows; close for good if it is at least equal; anything in between keeps 22 and re-reads once at 100 settled PASS rows on the same rule.

## What this does not answer
- Realized trade returns: every figure is a day-0-open buyer with no stop and no R.
- Regime (market) adjustment; the gap-size subset; why the 10-15..10-30 downgraded runners were cut (their composites were not re-derived).
- Whether the gate is right — only whether, so far, it cuts better names than it keeps; at n = 24 it cannot say.
