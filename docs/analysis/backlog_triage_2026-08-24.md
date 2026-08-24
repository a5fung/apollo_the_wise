# Backlog triage — every open task given a verdict (2026-08-24)

**Why this exists.** The board has sat at 79-87 open tasks for over a month. The growth gate stops it
rising; nothing makes it fall. The only honest lever is deciding some tasks will never be done, and
that is the operator's call. This file does the reading so he can approve in one pass.

**What was done.** All 82 open `PLAN.md` lines read in full. Every CLOSE was checked against git
history and the code, not against PLAN.md prose — PLAN.md is the thing being audited. Nothing was
edited, nothing closed, no code touched.

**Verdicts**
- **KEEP** — changes what the LIVE MAGNA53 money path does today (admit/kill, entry geometry,
  exit/stop, sizing, or a safeguard on those), and is genuinely live.
- **DEFER** — real, not now. Each carries a concrete date or the event that pulls it back.
- **CLOSE** — propose retiring. Only used where the thing is verifiably already done, where the task
  itself declares a close condition that is met, where the gate is an event that realistically never
  fires, or where it duplicates another line (survivor named).

**Counts: 18 KEEP · 44 DEFER · 20 CLOSE. Approving every CLOSE takes the board 82 → 62.**

⚠ One caveat before approving: **12 lines are already shipped and are waiting only on a verify.**
Ten of them close on a date or an event with nobody doing anything — #553 #575 #576 #540 #513 #414
#452 #471 #184 #570. **Two do NOT: #583 needs its handed-over migration actually RUN, and #523 needs
a paper-broker probe** (zero real leg repairs to date, so the probe is the only path). Those two are
work, not waiting.

---

## CLOSE — 20 lines proposed for retirement

| # | Name | Verdict | Reason |
|---|---|---|---|
| **#586** | Kill/scale bands measured the wrong risk number | CLOSE | **Already done.** Fixed, operator-signed and shipped 08-23 (commit `40521378`); verdict re-stated at −14.61R cumulative. The PLAN line still says `blocked`. |
| **#207** | Quarterly review of how we pick models | CLOSE | Its runtime carrier `model_selection_quarterly_review` was retired 2026-08-06 as contradicting his own "track the latest model" ruling — it can never fire again. |
| **#565** | Merge the two theme-candidate writers | CLOSE | The defect it was filed to find does not exist: all four insert paths write an identical column set, deliberately scoped per source. Its own DoD says "if stale, close it with the evidence." |
| **#334** | Theme-revive cooldown latch | CLOSE | It gates a live theme-revive path that does not exist and is not planned — revive is shadow-only and `revived_at` is in no schema. It refiles itself if revive is ever built. |
| **#239** | Two refactors already evaluated and declined | CLOSE | Its own text rules part (b) "won't-do" and part (a) waits on a third permanent consumer that has not appeared in two months. Nothing here is work. |
| **#212** | Questioner/investigator loop for sourcing | CLOSE | **Dropped, not re-homed.** All that exists is a throwaway read-only prototype from June (`scripts/proto_dialogic_dossier.py`, its own header says no DB write, no scheduler), untouched since 06-07, no DoD. Refile from a real case. |
| **#230** | Sourcing-QA detector built on #212 | CLOSE | **Dropped, not re-homed.** A PLAN line only — zero code anywhere — and it hangs off #212, which is also proposed for close. Nothing survives it, and nothing is using it. |
| **#255** | Judge remembers similar past cases | CLOSE | Its own clearing condition — name the corpus table and the row count — has gone unanswered through three re-dates, and the line itself prescribes closing rather than re-dating again. |
| **#307** | Weekly operator-labelling ritual | CLOSE | Its own text: *"if #255 is un-blockable, this one is too."* The labelling half already runs live; the only unbuilt piece IS #255. Survivor: **#255's decision**. |
| **#485** | A second LLM reviews the judge | CLOSE | Its DoD includes "if no, retire the idea." Untouched since it was split out on 7/19, and the judge already has three operator-labelled review streams doing this job. |
| **#281** | Staging environment hardening | CLOSE | Gated on a market-hours staging run that has never been scheduled, and its own folded-in precondition says it is "not needed until one is." |
| **#215** | Remove a known bias from the judge prompt | CLOSE | Its gate — "a clean grade cohort" — resets every time the judge model changes, and it just reset again when the judge moved to opus-5. Unfalsifiable by construction. ⚠ **What is lost:** the known OPTX prompt bias stays unaddressed; refile from a measured case. |
| **#176** | Tooling to detect roster/SoT drift | CLOSE | No code was ever written, three months dormant, no DoD, and no drift incident has been traced to its absence. Refile from a real case. |
| **#261** | Tidy up the scripts/ folder | CLOSE | A cosmetic file move that touches `deploy.sh` and CI, never started, and has yielded to real work eight times. Zero functional gain for real deploy risk. |
| **#308** | v2.0 pillar: experienced judge | CLOSE | *(group — see note below)* A container that enumerates other open task IDs and restates `apollo-v1.1-v2.0.md` Part II. |
| **#309** | v2.0 pillar: full sight | CLOSE | *(group)* Same shape. It is the only open task with **no commit anywhere ever referencing it**. |
| **#311** | v2.0 pillar: multi-setup book | CLOSE | *(group)* Same shape; its live content is #326's dated cut-over decision, which stands on its own. |
| **#312** | v2.0 pillar: capital & autonomy ladder | CLOSE | *(group)* The one safeguard it actually carried — the RED-3 sizing-multiplier clamp — is **verified in code**: `_apply_composite_multiplier` in `broker/entry_pipeline.py`, emitting `sizing_multiplier_clamped`, with its own test file. What remains is roadmap prose. |
| **#313** | v2.0 pillar: institution-grade ops | CLOSE | *(group)* Its cost-governance increment shipped 08-02; the remainder is replay-everything CI, which has its own line (#302). |
| **#314** | v2.0 pillar: trading-ideas detector book | CLOSE | *(group)* A list of other tasks (#283, #54) plus a memory file. |

### ⚠ The one group that needs his eyes, not a tick

**#308 / #309 / #311 / #312 / #313 / #314** are six of the twenty. They are the v2.0 pillars, and
they are genuinely *containers* — they enumerate other open task IDs and duplicate the roadmap spec.
But closing six lines because "another document holds them" is close to the reclassify-and-hide that
the burndown rule forbids, so it is stated plainly rather than buried: **approving this group means
accepting `docs/roadmap/apollo-v1.1-v2.0.md` as the home for the v2.0 horizon, with no PLAN line
carrying it.** If he wants a PLAN presence for the long horizon, the honest shape is ONE line, not six.

---

## DEFER — 44 lines, each with the date or event that pulls it back

### Already shipped — the verify date closes them (no decision needed)

*(#570, #583 and #523 are the same shape but sit under KEEP — they are on the EP money path.)*

| # | Name | Pulls back |
|---|---|---|
| #553 | Themes falsely merging into each other | 08-25 — separate repo (portfolio-app2), could not verify here |
| #575 | Theme batch size ratchets down forever | 08-26 — two clean nightly runs after tonight |
| #513 | Monthly sweep message was unreadable | 09-01 — the sweep next fires then. ⚠ Also waiting on HIM: the curated slash-command menu |
| #471 | Theme re-granularization phases 2-3 | 09-02 — the gate ripens at 20 resolved seed decisions |
| #452 | Five slots could all be one bet | Event — 3 real family-breach rows |
| #576 | Two false money-path alerts in one morning | Event — the next duplicate ORB trigger or breakeven-arm |
| #540 | Alpaca told us why it rejected us | Event — the next genuine broker rejection |
| #414 | Entry tuning for stop-limit no-triggers | Event — a Day-2 position needing its stop moved at 09:35 |
| #184 | Broker is the source of truth for trade state | Event — a genuine broker/DB disagreement (machinery verified alive) |

### Other setups — behind EP by his own standing ruling (P10)

| # | Name | Pulls back |
|---|---|---|
| #327 | Consolidation entry-watch | 09-01 — Family A sits behind EP |
| #353 | Consolidation → paper graduation | 08-31 — blocked behind #327's read |
| #354 | Fold flag-continuation into Family A | 09-15 — 9 shadow rows all-time, not tunable |
| #356 | HTF breakout shadow accrual | 08-26 — ⚠ the cheap half (WHY it accrues at 1 row/week) is doable now |
| #397 | Does HTF breakout trading make money | 08-31 — needs the shadow #356 cannot fill |
| #283 | Wick-fill promotion | 09-01 — ⚠ **headline is WRONG**: it says shadow→live and the real next rung is shadow→PAPER. Fix before anyone approves it |
| #297 | Family B EP rework | 08-30 — ⚠ ADR 0027 header still reads "awaiting operator sign-off" though PLAN claims signed 7/12 |
| #394 | Tune the coil finder | 10-05 — needs a week of forward candidates |
| #168 | Quality filter before a detector may ping | Event — any detector proposed for live pings |

### Judge and rubric — real, sequenced behind selection

| # | Name | Pulls back |
|---|---|---|
| #331 | Does the gap punch through resistance | 08-25 — ⚠ **its blocker is factually wrong**: #330's shadow shipped 2026-07-17. Registry gate at 700 rows |
| #504 | Meta-rubric roadmap ADR | 08-29 — needs an operator session |
| #368 | Operator labels the theme cohort | 09-11 — needs HIS labelling |
| #333 | Catalyst durability forward axis | 08-31 — needs 60 days of stored estimates |
| #486 | Judge vs theme-engine cross-check | 08-28 — needs a stable theme engine, which is mid-consolidation |
| #210 | Catalyst sourcing backbone | 08-27 — umbrella; needs a real work/descope/split decision |
| #233 | Reposition Perplexity | 08-27 — rides #210 |
| #299 | Tape features for the judge | 09-09 — ⚠ **a live operator fork: ~$170 of eval spend, his call** |

### Themes and dashboard — tier 4, no money path

| # | Name | Pulls back |
|---|---|---|
| #555 | Theme identity needs a model not a tenth guard | 09-17 |
| #561 | Replace Rank Flow with a named movers list | 09-01 — follows #555 |
| #560 | Steady-state cost of theme assignment | 09-19 — registry-gated |
| #580 | Theme strength must carry breadth | 09-30 |
| #529 | Crypto ↔ AI-infrastructure merge family | 09-21 — blocked by #471 |
| #505 | Parent-child must hold on every path | 09-24 — behind the birth gate |
| #506 | Nightly theme-hierarchy health check | 09-26 — behind #505 |
| #491 | Themes anchored to a dead thesis | 09-28 — behind #471 |
| #589 | Funnel drop-off over time in the dashboard | 09-07 — deliberately waiting until he has used `/scanned` a week |

### Hygiene and hardening

| # | Name | Pulls back |
|---|---|---|
| #554 | 11 readers that can hit a 1-row day | Event — #564 ships AND the four historical stray dates (05-30, 07-05, 07-12, 08-08) are pruned. Until then the rows are still being written and the old ones still sit there |
| #573 | Review-readiness detector degrades silently | 08-30 — confirmed still a hand-maintained dict |
| #574 | Two minute-bar jobs duplicate 25 lines | 08-31 — confirmed still duplicated |
| #582 | Theme synthesis has no truncation guard | 09-14 — confirmed absent; `theme_split` has it |
| #488 | Authoritative halt data | 08-28 — ⚠ **the build lives only on an unmerged branch** (`ba7533b`), nothing on main. Gated on his merge decision |
| #316 | PDT rule relaxation | 08-28 — external: Alpaca's own 4210 rollout |
| #121 | Telegram Markdown → HTML | 10-03 — 27 legacy sites remain, 17 in `channels/telegram.py` |
| #501 | Wire 13 gate-invisible silent failures | 11-05 |
| #466 | Drive silent-failure baseline to zero | 10-08 |

---

## KEEP — 18 lines on the EP money path

| # | Name | Reason |
|---|---|---|
| #584 | Re-check liquidity on the gap morning | Admission change; the D-1 floors carry the fattest tails we drop |
| #559 | Trusting live prices at alert time | Admission fork, re-cut due 08-27; a trade was already lost to feed latency |
| #588 | A partial exit is double-counted against the stop | Corrupts `realized_r` and every exit study we tune on |
| #516 | The M&A filter suppressed 3 of 4 real movers | Recall failure = P1. Needs HIS filter-list sign-off |
| #482 | Alternative entry/stop geometries | The live 1-min ORB bracket is near-zero-edge on HIGHs |
| #545 | Entry/exit tactics program | The operator's own framing of the core problem |
| #359 | Is $500M the right market-cap floor | #556 makes it the binding admission gate — the ADV floor cannot move without it |
| #533 | Given 10 alerts and 5 slots, did we take the right ones | The within-day ranking question; nothing else measures it |
| #562 | What our delayed-entry trigger actually is | Only 1 of 104 watched names ever reached the trigger |
| #519 | Prove chart reading offline, then earn it back | RULE 0b — a continuous judgement forced into a binary test |
| #335 | Make the composite grade load-bearing | ⚠ **needs a ruling from him** — see the fork below |
| #197 | The cap-plus-one slot | Decides which alert gets scarce capital |
| #564 | A weekend ticker lookup writes a fake score row | It broke the evening brief once; cheap writer-side fix |
| #579 | Apollo should tell him, not wait for a weekly slot | His explicit ask, with a proven case already measured |
| #448 | Does the rubric downgrade losers more than winners | The core rubric-validity question; cohort is accruing |
| #570 | The silent universe floors | Shipped; verify 08-25 |
| #583 | Stale rows corrupt every gate study | Shipped; verify 08-25 + migration to run |
| #523 | Widening a broker-leg stop | Shipped; verify 08-25 |

---

## Free closes — already done, never closed

**#586 is the only one.** It was fixed, operator-signed, shipped and deployed on 08-23 (commit
`40521378`), its verdict was re-stated on the corrected series, and the PLAN line still reads
`blocked` with a pending sign-off that already happened.

**#207 is the second-order case** — not built, but its runtime carrier was deliberately retired on
2026-08-06 and the PLAN line never learned.

The `LIKELY-BUILT` surface currently suppresses five lines under a fresh `swept:` marker
(**#261 #327 #354 #519 #491**). All five were re-checked here: the classification is honest in four —
they contain built markers for shipped sub-parts while the named remainder is genuinely unstarted.
#261 is the exception and is proposed for CLOSE on different grounds (the remainder is not worth doing).

---

## Could not judge

| # | Why |
|---|---|
| #553 #555 #561 #580 #589 | They live in **portfolio-app2**, a separate repository not present here. Verdicts are on priority and PLAN evidence only; the code claims are unverified. |
| #299 | The value of ~$170 of tape-feature eval spend is his judgement, not mine. Listed as DEFER, but it is really an open fork. |
| #533 #562 | Both hinge on live rows accruing to ~mid-October. Whether that window is worth waiting for is a call about the selection rebuild's results, which do not exist yet. |

---

## Three things he should decide, separate from the closes

1. **#335** — the meta-rubric flip's gate may now be **frozen**: the 08-22 rescale removed the MODERATE
   tier, so the themed-MODERATE reads it waits for stop accruing. Either the near-miss band substitutes,
   or the task re-scopes to the new bands. It cannot be re-dated honestly again.
2. **#488** — a month-old, entitlement-proven halt-capture build is sitting on an **unmerged branch**
   with nothing on main. Merge it (default OFF) or drop it; leaving it there is how work is lost.
3. **#283** — its headline reads "shadow→live". The real next rung is shadow→**paper**. Approving the
   line as written would jump a shadow strategy straight to real money. Fix the title whatever the verdict.
