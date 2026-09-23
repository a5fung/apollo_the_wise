# MONDAY RULINGS PACK — the 6 forks queued 7/12 (Fable, pre-argued)

**How to use:** these are the six operator rulings that came out of 7/12's red-teams + builds —
none covered by the existing Lane-1/M1 packs. Each: context → the fork → rec. Total sitting
time if recs are taken wholesale: ~15 min. Sources are linked; nothing here changes anything
until you rule (THE LINE). Ordered: time-critical first.

---

## R1 · FL-4 promotion criterion — unblocks TODAY's F2 flip
**Doc:** `fl4_ingest_promotion_criterion_2026-07-12.md` · **Gates:** the dry_run flip you planned Monday.
The signed criterion ("≥3 clean LIVE R1 proposals") is unsatisfiable — R1 proposals fire on the
drift the hardening prevents; a healthy system produces ~0, so FL-4 can never green on live evidence.
**Fork:** (a) adopt the replacement — 3 clean SYNTHETIC R1 repairs via the existing
`_184b_ingest_paper_exercise.py` (incl. one dead-pointer variant) + ≥5 dry_run days with zero *wrong*
proposals (zero-proposal days count clean); pull `earliest_review_date` 7/25→7/17 · (b) keep the live
criterion and accept an open-ended FL-4 slip.
**REC: (a).** It still proves the repair path executes end-to-end (R1's live write is DB-only; the
read side is already live-exercised every 15 min) and adds the healthy-book-specificity leg live
evidence would have given. Timeline: dry_run today → sign live_r1 ~7/17 → FL-4 green ~7/24.

## R2 · Readiness RED-1 — the soak clocks + the unsafe auto-pull
**Doc:** `v1_readiness_redteam_2026-07-12.md` RED-1 · **Gates:** #425 (the declaration itself).
The meter (`v1_closeout_status.py` `FL1_SOAK_START=6/30`, reads 8/10 today, green ~Wed) and the
walk-pack's strict ruling (reset 7/7 → soak completes ~7/22) disagree; #425's "PULL EARLIER on
countdown green" auto-pulls onto the optimistic clock.
**Fork:** (a) rule STRICT (repairs reset 7/7; the walk-pack's own rec) + set `FL1_SOAK_START=2026-07-08`
in the meter the same sitting + rewrite #425's pull-trigger to "after F1 ruled + meter reconciled" ·
(b) rule LENIENT (reviewed scripts = designed surfaces; streak from 7/3) and declare sooner on a soak
containing manual repairs.
**REC: (a).** The lenient soak is hollow by the pack's own words; the cost is ~2 days. One constant +
one PLAN-line edit; I execute both on your word.

## R3 · 0025 merge-arm — the MERGE vs PARENT_CHILD boundary
**Source:** last night's corpus run — hard pairs **5/5 PASS** (all legit-kill anchors safe); gate FAILED
only on M03/M04/M05: golden=MERGE, adjudicator=PARENT_CHILD, all three with "identical driver, narrower
slice" reasoning (coastal-multifamily ⊂ multifamily · pure-play-quantum ⊂ quantum · precision-onc ⊂
clinical-onc).
**The substantive point:** PARENT_CHILD keeps BOTH themes (sub-theme machinery) — it does not reduce
theme count. #274 exists because 78 active themes vs 40 median; these three pairs are exactly the
near-dup fragmentation class. An adjudicator that answers PARENT_CHILD to identical-driver slices
leaves the fragmentation unfixed.
**Fork:** (a) goldens are right → one prompt amendment ("drivers IDENTICAL + the narrower theme adds
only a slice qualifier (geography/purity/modality) with NO distinct sub-catalyst → MERGE;
PARENT_CHILD requires a distinct sub-driver") → re-eval; flip eligible only if hard pairs stay 5/5
(M01/M12 are the anti-overcorrection controls — both have genuinely distinct sub-drivers) ·
(b) adjudicator is right → relabel M03/04/05 to accept PARENT_CHILD → gate greens with zero
fragmentation reduction on this class.
**REC: (a).** It is the ADR's stated purpose; the anti-overcorrection control is already in the corpus.
~30 min: amend → re-run (~14 Haiku calls) → pass record → the flip becomes YOUR separate call.

## R4 · Composition RED-1 — the giveback enforcement surface (designed both ways, below)
**Doc:** `composition_redteam_2026-07-12.md` RED-1 · **Gates:** the 8/06 giveback flip.
The +$8,075 evidence is close-below (l=c bars); the current wiring would enforce it as a resting
Alpaca stop (intraday-touch). **These are different rules** — the resting stop exits on any midday
wick the evidence never saw (tail-clip direction).

**The design fact that reframes the fork (grounded in code):** the system ALREADY runs both surfaces.
- The SMA trail is a **close-below decision-line**: decided 16:45 ET post-close (`sma_stopped` →
  `execute_full_exit`), which after-hours queues the sell to **next open** (order_manager ~2040:
  documented). You have already accepted that decision-at-close/fill-at-open delta for the trail.
- The ladder stop is a **resting broker stop** via `update_stop` (live_tracker:573) — intraday-touch.

So the floor can join EITHER surface, and there is a third with precedent (#361 moved partials
intraday to 15:45 for same-day settlement):

| Surface | Rule vs evidence | Fill vs evidence | Overnight gap risk | Build |
|---|---|---|---|---|
| (a) resting stop (current wiring) | **CHANGES THE RULE** — intraday touch exits; un-validated; clips wicks | fills AT the floor | none | zero (wired) — but requires re-derived intraday-aware evidence before flip |
| (b) EOD decision-line 16:45 (SMA-trail surface) | matches close-below exactly | **next-open fill** — overnight gap between signal and exit | real (gap-down overnight) | small: floor becomes a decision branch beside `sma_stopped`, NOT a max() input |
| (c) near-close decision ~15:50 (#361 surface) | close-proxy (15:50 ≈ close; small proxy error) | fills ~at the close the sweep assumed | none | small-medium: a 15:50 check job + market sell before bell |

**REC: (b) for the 8/06 flip, (c) as the follow-on refinement if (b)'s gap deltas annoy.**
(b) is the smallest honest step: same enforcement surface as the already-accepted SMA trail, matches
the evidence's RULE exactly, and the composition changes cleanly (the floor exits like a trail-stop
rather than feeding the resting-stop max() — note T4-R8's `max(arm_stop, giveback_floor)` precedence
line was written assuming (a) and gets restated as "the floor is an exit TRIGGER, not a stop level").
(a) is only right if you *want* intraday-touch semantics — in which case the sweep must be re-derived
on intraday lows first (real work, and the +$8k number will shrink).

## R5 · Composition RED-3 — bound the sizing multiplier (ready-to-build card)
**Doc:** `composition_redteam_2026-07-12.md` RED-3 · **Gates:** allocator-live (#312, post-8/4). Latent today.
`entry_pipeline.py:418` applies the composite multiplier AFTER the 20%-capital/1%-risk caps with no
re-cap — the first >1.0 allocator step sizes through every safeguard.
**Fork:** (a) structural — after step 5b, recompute position_size/risk_dollars and RE-CLAMP to the
same 20%/1% caps (safe under any future multiplier; ~10 lines + tests) · (b) minimal — hard-bound
`composite_multiplier ≤ 1.0` until the allocator ships, revisit then.
**REC: (a), built this week, deployed with the next money-path batch.** It's cap-restoring (can only
shrink size back inside limits you already signed), future-proof, and removes a standing foot-gun.
Sizing code → your sign-off + the #151-style careful path; on your word it's a ~1h build.

## R6 · #416 M&A-FP amendment — sign or fork
**Doc:** `416_mna_fp_amendment_2026-07-12.md` §6 (due 7/16).
Three sub-forks: (1) assessed-FP scope — **rec: confirm IMAX** (speculation-flavored, ran +) and leave
D/PZZA for the classifier-path follow-on; (2) Guard-C depth — **rec: the surgical port** of the
existing polygon acquirer-heuristic (mirrors a tested mechanism); (3) the FP/FN asymmetry — **rec:
accept** (the filter is a suppressor; its errors cost winners; the deal-break tail is real but bounded
by the same stop discipline every position carries — priced, not ignored). On sign-off: the precise
full-text simulation is the pre-deploy N-gate, then Guards A/B/C behind one predicate.

---

## Not on Monday's docket (parked correctly)
- **Composition RED-2** (update_stop advisory lock + never-lower guard) — gates 0031 (~8/09), not this
  week; it is the concrete content of ADR 0029-D1 and rides the pivot pre-flip gate already wired.
- The walk itself (#425) — after R2's reconcile, earliest honest declare ≈ **7/24** (FL-4-bound via R1).

**If all six recs are taken wholesale:** F2 flips today · the soak clock becomes honest · the merge
arm re-evals toward its flip · the giveback flip gets a designed, evidence-matching surface · the
allocator foot-gun dies this week · #416 ships its guards. Every one lands inside existing tasks —
zero new PLAN lines.
