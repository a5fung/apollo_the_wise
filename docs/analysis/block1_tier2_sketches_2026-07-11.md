# Block 1 Tier-2 sketches — #333 durability axis · #301 divergence monitor · #299 note (2026-07-11)

**Status: DESIGN SKETCHES** — deliberately thinner than the Tier-1 ADRs; each names its build
gate. Nothing here flips anything.

---

## #333 — Catalyst-durability forward axis (sketch; build gated on #210/#211)

**The gap:** the rubric scores TRAILING acceleration (a1 revenue YoY + decel/accel); Pradeep
durability = **≥2Q realized + ≥4Q PROJECTED** high revenue growth. The forward leg needs
STRUCTURED forward estimates — explicitly not LLM prose (the task's own constraint).

**Shape:**
- **New deterministic rubric axis `a7_durability`** (catalyst-quality → rubric-side per ADR
  0024's F1 split, like a1-a6 — NOT a meta-rubric context axis): score from (i) # of projected
  quarters with consensus revenue growth ≥ a class-relative bar, (ii) the projection's level vs
  the trailing print (accelerating-forward > flat > decelerating-forward). Exact points/weights
  = calibration OUTPUTS (the ADR 0028 discipline), not pre-committed.
- **Data contract (what #210/#211 must deliver before build):** point-in-time
  `{ticker, fiscal_quarter, consensus_rev_estimate, n_analysts, as_of}` — stored at grade time
  so replays classify from STORED fields (the lookahead rule). Neglect interaction: thin names
  (n_analysts < 3) score `a7 = None` → the existing missing-data scaling absorbs it (never
  penalize the un-covered; that's the episodic_neglect class's bread).
- **Build gate:** the sourcing backbone lands + ≥60d of stored estimates accrue → STEP-0
  (durability-split forward returns) → only then the axis ships shadow. Wire the gate as a
  data-gated review at build time, not memory.
- **Composes with #332:** durability salience is a class hypothesis (highest for
  `pradeep_explosive`, low for `mature_leader`) — feeds ADR 0028's P1 replay when both exist.

---

## #301 — Ensemble-divergence monitor (build-spec; clustered post-launch with #320/#321/#335)

**What it is:** a ZERO-AUTHORITY 2nd-model verdict on judge-HIGH alerts only (~2-5/day), logged
for divergence telemetry. Not #233 (that's an input, CHANGE_PROCESS-gated); this only watches.

**Spec (execution-ready):**
- Trigger: after a judge HIGH verdict persists → queue a Sonnet grade over the IDENTICAL payload
  (same `_judge_replay_common` assembly, same prompt scaffold, model swapped). Fail-open: a 2nd-
  model error logs `divergence_check_failed` and never touches the alert.
- Table `mi_judge_divergence`: `(id, alert_id FK, judge_tier, second_tier, second_model,
  diverged BOOL, axis_deltas JSONB, created_at)` — append-only.
- Surface: ONE weekly-review line (divergence rate + direction skew); no Telegram, no per-alert
  noise. Gated review at ≥30 rows: divergence >25% → investigate grounding/prompt (a high rate
  means the verdict is prompt-fragile, not that either model is "right").
- Cost: ~2-5 Sonnet calls/day — no funding fork.
- Build slot: the post-launch grade-quality batch (#320/#321/#335) per the 6/19 deferral —
  unchanged; this spec just makes the card mechanical when the batch opens.

---

## #299 — tape-features full run: NO design needed (operator funding decision)

The rig is DONE + verified (6/17; `eval_tape_judge.py`, turnkey). The only open item is the
funding fork: ~$50-90 directional first pass vs ~$170 full (~3,420 Opus calls). Rec unchanged
from the task: decide at the post-launch grade-quality batch alongside #301/#335 — a directional
first pass is the cheaper way to learn whether the tape axis earns its keep. Nothing for design.
