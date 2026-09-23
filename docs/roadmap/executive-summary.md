# Apollo — Executive Summary (the vision one-pager)

**Written 2026-07-05 (v1.0 close-out weekend). Audience: the operator-as-CEO. Companion docs:
`v1-closeout-productization.md` (#418, the finish line) · `apollo-v1.1-v2.0.md` PART II (#419,
the Phase-2 program) · ADRs 0017-0022 (the execution-depth designs).**

**The one-liner.** Apollo is an autonomous trading firm in a box: a proven human momentum
methodology run end-to-end by software, with LLM judgment installed at exactly the decision
points where a discretionary trader's skill lives — and deterministic guardrails everywhere
else. Trading real money, unattended, since June 30.

## The thesis
Elite discretionary traders (the Qullamaggie/Bonde playbook) generate returns from judgment at
a handful of decision points. That judgment never scaled: one human, a few hours a day, fatigue
and emotion. LLMs are the first technology that replicates the judgment layer. The architecture
is precise about the division of labor: **the LLM judges; the machine executes; the human
governs.** Everything mechanical stays mechanical. The LLM sits only where the human used to
sit, outputs bounded to enumerated actions, authority earned rung by rung on labeled evidence —
and the judgment layer improves for free on the vendor curve (proven: a one-evening
evidence-gated model flip, 9-2 on labels).

## What is already real
- **Live loop, real capital**: detect -> grade -> enter -> manage -> exit -> self-audit, daily,
  without intervention.
- **The judge is load-bearing and measured**: 5/5 correct demotes on operator labels — including
  demoting a stock that ran +152%, because the reasoning was right and the outcome was luck.
  We grade attribution, not outcomes. That discipline is the product.
- **Institutional ops at one-person cost**: 13-gate deploys; nightly backups with a
  proven-nightly restore (first run caught a real DR gap); service watchdog; three-tier
  self-audit; money-paths 100% clean of silent failures with a ratchet that only goes down.
- **A learning loop**: weekly self-review, operator label sittings, and no strategy-touching
  change without evidence and sign-off.

## The gap being funded
One long-only strategy in one regime, and the most human function — managing winners — still
mechanical: **18% of winners' peak excursions captured** vs a tier-one bar of >50%. The layers
that close the gap are designed, reviewed, and unbuilt: that is Phase 2.

## The plan
**v1.0 — declare the product shipped (~7/21-7/31)**: eight measurable exit criteria (soak,
ops streaks, mirror completeness, docs-only recovery, cost envelope), a daily countdown in the
evening briefing, a hard-dated declaration walk. Idle is structurally impossible — slipped
dates fail the build.

**Phase 2 — the tier-one trader (Q3-Q4), five pillars on milestones M1-M5:**
1. **Management Judge** (ADR 0017) — LLM judgment on open positions; 18% -> >50% capture
   target; proposes against each stock's OWN character; promotion human, demotion automatic.
2. **Experience Stack** (ADR 0018) — the moat: every judged alert + outcome + label becomes
   retrievable precedent; weekly self-review distills rubric amendments the operator signs.
   Compounds weekly; cannot be bought or copied.
3. **Full Sight** (ADR 0021) — same-day narrative-cohort radar (the theme at 10:00, not 18:05)
   + a negative-catalyst axis (dilution overhang makes breakouts untradeable).
4. **Multi-Setup Book** (ADR 0020) — consolidation entries, the first short book,
   regime-adaptive allocation: multiple edges across market weather.
5. **Autonomy Ladder + Replay-CI** (ADR 0022) — allocation that proposes and the human signs,
   Kelly-capped per strategy AND globally (0.40); a methodology change that degrades replayed
   expectancy cannot deploy.

## Why believe the execution
The close-out weekend as evidence: three days -> the hardening backlog cleared, two new
production safety systems (one caught a real DR gap on first run), the v1.0 plan, all 104
workstreams dispositioned, Phase 2 roadmapped with dated milestones, six execution-ready
designs through four review layers (~20 corrections, zero architectural objections). Expensive
model designs and reviews; cheap models build. That cost structure IS the operating model.

## Risk & controls
The human owns all money decisions — hard line. Bounded-enum LLM outputs, never free-form
orders. Evidence-gated authority rungs with automatic demotion on harm. The LLM never
discovers facts — it judges primary-source documents we fetched. Kill switches at every
layer; a 0.40 global Kelly ceiling makes portfolio over-leverage arithmetically impossible;
the whole methodology version-controlled, replay-tested, recoverable from docs alone.

## The ask
1. **Sign-off** on ADRs 0017-0022 -> ACTIVE; execution starts on rails.
2. **Operating envelope**: current tracked monthly budget, alarms armed; no increase for
   Phase 2 as designed.
3. **Capital scaling stays evidence-bound**: kill/scale bands + propose-then-sign allocation.

**The compounding case in one sentence:** model capability improves on the vendor's dime,
sight improves with each grounded source, experience accrues with every labeled trade — three
compounding axes on a methodology that already works, inside a machine that provably runs
itself.
