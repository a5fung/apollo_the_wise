# Weekend push — 2026-07-18/19 execution plan (prepped 7/17 eve)

**Status: PREP ONLY. No code changed, no cards spawned. Awaiting operator go.**

## Correction from the first-pass triage (why prep mattered)

The meta-rubric cluster (#328–#332) is **designed + signed already** — ADR 0015
(theme axis), 0016 (structure axis), 0024 (composition, F1 closed), 0028
(methodology-fit). STEP-0 calibrations done. So its weekend work is **shadow
BUILD (Sonnet), not Fable design**, and the *live* value is gated on #335's
batched Opus re-grade ($ + operator sign). I do NOT force Fable onto signed
work — that's manufacturing work to feed it. Fable goes where design is
genuinely open (below) + as the reviewer of every money-adjacent shadow build.

## Model assignment

### FABLE — genuinely-open design / red-team + review-of-builds
- **#450** adversarial pre-mortem ("how does Apollo lose 20% in a month") — open red-team.
- **#461** TOCTOU cap-check → transactional — DESIGN (safeguard concurrency; operator-sign, safeguard-flavored).
- **#306** W3 exit-management tune — DESIGN only (partial size / trail-by-character / capture_pct / time-stop = **sell discipline = THE LINE**; operator signs any flip).
- **#471** theme-ecosystem Phase 2-3 — DESIGN (N≥10-gated; can't flip, can design).
- **Reviewer**: Fable adversarially reviews each Sonnet shadow build below before it ships dark (money-adjacent → premium review; this is the heavy-Fable lever that adds real value).

### SONNET — build (design already exists)
| # | build | notes |
|---|---|---|
| #330 | `structure_axis_shadow.py` (new) + db accessor + scheduler job | follow `theme_axis_shadow.py` pattern; ADR 0016 + STEP-0 done |
| #331 | gap-alignment shadow | **sequences AFTER #330** (needs its primitives) |
| #332 | C1 deterministic setup-class classifier tag | ADR 0028; classifier doesn't exist yet — genuine build |
| #358 | ADR 0013 provenance-rule lint (new script + CI wire) | fails on uncited cohort-shaping gate const |
| #379 | cost-watchdog Phase 3 | extends `cost_board.py` (shipped 7/17) |
| #402 | HTF Phase-3 shadow /simplify cleanup | all shadow |
| #322 | theme-detection gap (JBL AI-infra miss) | `theme_engine.py` — solo-ish (theme_engine overlap) |
| #185 | corrupt-stop exclusion-count display fix | small; card locates the render site |
| #446 | dead-zone reeval residual | analysis doc, no code |
| #420 | external uptime pinger + kuma disposition | infra script |

## Conflict map → batching (cards run worktree-isolated; this governs MERGE order)

- **Parallel-safe batch A** (independent files): #185, #358, #379, #402, #446, #420, #330 (new file). Fire together, worktree-isolated.
- **Solo / sequential** (wide or safeguard footprint — merge alone, verify hard):
  - **#444** mode-label sweep — ~10 files incl. `broker/` (dual-account label backbone). Solo, careful.
  - **#461** TOCTOU — `entry_pipeline`/`live_tracker` safeguard path. Fable-design first, then build solo, operator-aware.
  - **#322** theme_engine.py — sequence vs #330's db.py touches.
  - **#331** after #330 lands.

## Gated — NOT weekend-doable without operator (surface, don't touch)
- **#335 batched Opus re-grade** ($ + sign) — **gates the meta-rubric's LIVE value.** THE FORK (below).
- Operator decisions → batch to Sunday digest: #299 funding · #357 sugar-baby role · #368 weighting labels · #197 · #269 (AKTS event) · account-minutes #195/#280/#384/#194.
- Blocked on operator action: #195 password · #280 paper acct · #425 declaration walk (FL-4 ~7/23) · #287 partial-exit verify.

## THE FORK the operator must settle to unlock the big prize
The meta-rubric shadows can all be BUILT this weekend (Sonnet) — but they only
become *live grade-affecting* value via **#335's one batched Opus re-grade of
the labeled cohort** (has_direct_source + theme-heat + structure + gap + tape).
That costs ~$50 (subset) to ~$170 (full) and needs your sign-off.
**Decision: fund + run the batched eval this weekend, or build-shadow-only and
hold the eval for a later checkpoint?** (The build proceeds either way; this
only decides whether Monday can see a live-wire proposal or just shadow diffs.)

## Sequence (front-loaded)
- **Sat AM**: parallel-safe Sonnet batch A (worktree) + Fable #450 premortem.
- **Sat PM**: land batch A (Fable reviews each), Fable #461 + #306 design, run #444 solo.
- **Sun**: #322 / #331 / #332 builds (Fable-reviewed), wire shadows dark, I consolidate every operator item into ONE digest so Monday is turnkey.

## WAVE 1 — LAUNCHED 7/17 eve (in flight)
5 worktree Sonnet code cards + 2 analysis cards. Integrate each on return (test-gate
per merge; do NOT commit code to main while worktrees are live).
- #330 structure-axis shadow · #379 cost-watchdog · #402 HTF shadow cleanup (scoped) ·
  #358 provenance lint · #185 corrupt-stop display — all Sonnet, worktree.
- #446 cancelled-unfilled diagnosis (Sonnet, doc) · #450 pre-mortem (Fable, doc).
- Dropped from the fleet: #420 (operator-action-blocked — UptimeRobot account) → digest.

## WAVE 2 — queued (fire after wave 1 merges; scale up if wave 1 lands clean)
Sonnet builds:
- #331 gap-alignment shadow — **AFTER #330** (needs its structure primitives; write the
  card referencing the actual structure_axis_shadow.py #330 produces).
- #332 C1 deterministic setup-class classifier (ADR 0028; new — independent, parallel-ok).
- #322 theme-detection gap — investigate + feed the JBL-class miss into P2/P4 narrative
  radar (#309/#311); scope is loose → card investigates first.
- #444 mode-label sweep — **AFTER #330** (both touch scheduler.py); solo, money-adjacent
  (dual-account label backbone: bar_stream/telegram_confirm/ep_detector/scheduler sites).
Dashboards (operator-added 7/17 — Sonnet, cross-repo, NOT worktree since they edit
sibling repo `../portfolio-app2`; I run the prod export + Streamlit push/deploy):
- #480 trades dash → cut to LIVE book (add `account_mode='live'` filter + rename the
  paper-named snapshot + relabel the page). Verify the deployed SURFACE.
- #472 themes dash → surface the ADR-0032 ecosystem hierarchy (already tracked; depends
  on #194 carrying the ecosystem-mapping column — may need a manual snapshot regen).
Fable design (paced — don't fire all at once; capacity is shared):
- #461 TOCTOU → transactional cap-check — **Fable designs** (concurrency correctness),
  then careful build, **operator-signs the deploy** (safeguard-flavored).
- #306 W3 exit-management tune — **Fable design only** (partial size/trail-by-character/
  time-stop = SELL DISCIPLINE = THE LINE); operator signs.
- #471 theme-ecosystem Phase 2-3 — **Fable design** + dark parts; N≥10 + CHANGE_PROCESS
  gates the flip. Acceptance fixture: the 2 killed vuln-mgmt births survive as children.
- #354 merge flag_continuation into consolidation + #327 remaining — **Fable design**,
  Family-A entry = LINE-adjacent, operator signs. #353 graduation stays EVENT-gated
  (needs #327's live-edge to show on the #94 watcher — not weekend-forceable).

## Honest burndown shape
Full closes this weekend: analysis/display/lint (#185, #358, #446, #402). The
shadow/hardening builds **ship-dark and verify-live Monday** — done-done lands
Monday for anything that deploys. Tier-3/4 items are yours, not my burndown.

## Capacity guard (the 7/17 lesson)
Every card carries an explicit `model:` tag (`sonnet` or `fable`) — never a bare
spawn that inherits Fable into a self-replicating fleet (that burned 75% on
7/17). Fable fired in small deliberate batches.
