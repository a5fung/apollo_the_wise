# #534 — Theme universe expansion: measured picture, options, recommendation

**Date:** 2026-08-05 · **Status:** DESIGN — nothing changed, nothing deployed; prod read-only throughout.
**Trigger (operator, verbatim):** *"our RS/theme universe is too small (~300 stocks), we need to fundamentally
expand it but intelligently. We don't want a theme with 50 stocks and no way to tell what's in it… but we maybe
need a larger universe and some sub groupings and show the highest RS, biggest, strongest etc. but other stocks
are still in a theme but not at the top."* And on the duplicate defense themes: *"this sounds like there's
multiple defense stocks moving and having EP around the same time, this might be indicator that this group is
coming back alive after a dormant period."*
**Evidence provenance:** every number below is from prod `mi_stock_scores` / `mi_themes` / `mi_ep_alerts` /
`mi_theme_birth_candidates` / `mi_theme_candidates_shadow` / `api_usage` via read-only ssh, captured once to
scratchpad (`534_batch1..6.txt`). $0 spent — no LLM eval was run.

---

## 1. The decisions in front of the operator (everything else in this doc is evidence for these)

| # | Decision | Recommendation | Gate |
|---|---|---|---|
| D1 | **Flip the birth gate observe → on before ANY widening** | Yes — already the agreed plan; its calibration trigger lands ~Fri 08-07. Expansion into the ungated funnel multiplies the corpse rate (18 births on 08-04 alone). | Already operator-gated (CHANGE_PROCESS r3 + judge eval). Nothing new to sign today — only confirm the ORDER: gate first, widen second. |
| D2 | **Widen ASSIGNMENT reach: `ASSIGN_POOL_RS_FLOOR` 90 → 70, ceiling 200 → 600** (all liquid RS≥70 ≈ 517 names) — discovery stays `leaders[:40]` | Yes. This is the "other stocks are still in a theme but not at the top" half of his ask: existing themes gain their mid-RS members instead of new noise themes being born. Cost ≈ +$0.20/day. | Theme axis feeds the shadow judge → same class as the #476 pool change: operator sign-off + forward junk-assign watch. **This is the one genuinely new sign-off in this doc.** |
| D3 | **EP → theme feed: approve the two-part design in §5** — (a) flip the Lane-2 v2 registry (built dark, flag OFF), (b) build a $0 deterministic ecosystem-reactivation detector | Yes — his defense instinct is confirmed by the data (§5). The lane that groups EP alerts into narrative themes ALREADY EXISTS; v1 of it is what minted the duplicate pair. | (a) already operator-gated (replay + ADR-0030 judge eval). (b) is observability-only — ship-full class, no gate beyond normal review. |
| D4 | **Do NOT build a new retirement mechanism** — the 7-day recency cap is not the main killer (§7); the fixes already shipped/queued (#368 F2, birth gate, D2 breadth) attack the real one | No action. Stated so he never has to infer it. | none |

Not proposed: raising the stored-universe size past ~2,400 names (a collector change, §3), hand-authored
themes, hard-coded sectors — the bottom-up north star is untouched everywhere below.

---

## 2. Correction to the framing — measured before designing

Two numbers in the task framing needed correction against prod; the design is built on the corrected ones.

- **"Universe ~9,700" is the raw Polygon scan, not the scored universe.** `mi_stock_scores` stores ~2,426
  names/day (max `rs_rank` = row count = 2,426). After the engine's own liquidity screens (ADV ≥ $500k,
  close ≥ $10 — `get_rs_leaders` defaults) the investable set is **1,762 names**. That is the honest
  expansion ceiling without touching the collector. "Top 3,000" does not exist in stored data.
- **The recurring 7-day theme lifespan is mostly NOT `stale_after_days=7`.** Of 174 ended theme names,
  **156 end with an explicit Retired row**; only 18 age out silently via the recency cap. The 7–8-day
  lifespan mode (34 themes) is dominated by the **5-day weak-Fading retire streak on 2-member themes**
  (born → one member dips → rs_avg-NULL Fading ×5 → Retired). Full numbers in §7.

---

## 3. Q1 — How far can the universe expand before it degrades?

**Where the 319 covered tickers sit today (liquid universe, 2026-08-04):**

| RS band (liquid: ADV≥$500k, close≥$10) | names | covered by any active theme | coverage |
|---|---|---|---|
| RS ≥ 90 | 163 | 63 | **39%** |
| RS 80–89 | 180 | 42 | 23% |
| RS 70–79 | 174 | 36 | 21% |
| RS 50–69 | 351 | 55 | 16% |

Even the elite band is 61% uncovered — ~100 liquid RS-90+ names are in no theme. The constraint is exactly
what the operator said: pool reach (discovery top-40; assignment RS≥90 within top-200 ≈ 83 names) and member
width (57 of 101 active themes have exactly 2 members; avg 3.3).

**What each expansion step produces (translating his 400/1000/3000 into how the code actually selects —
floor + ceiling over the liquid set):**

| Pool definition | pool size | uncovered today | ≈ his "N" |
|---|---|---|---|
| today: RS≥90 in top-200 | ~83 | ~40 | ~200 |
| liquid RS≥80 | 343 | ~240 | ~400 |
| liquid RS≥70 | 517 | ~376 | ~600 |
| liquid RS≥50 | 868 | ~670 | ~1,000 |
| all liquid | 1,762 | ~1,450 | — |
| "3,000" | **not reachable** — collector stores 2,426 | — | — |

**Cost — measured from `api_usage` (30 days), not guessed.** The entire theme stack today costs
**~$14.2/30d ≈ $0.50/day**: discovery $6.28 (115 Sonnet calls, avg 9.5k in / 1.7k out), assignment $2.11,
Opus advisor $1.71, synthesis $1.54, ecosystem-assign $0.98, validation $0.94 (1,065 tiny per-member calls),
merge $0.30, descriptions $0.18. Unit prices back-derived from the same rows (Sonnet $3/$15 per Mtok, Haiku
$1/$5, Opus 4-8 $5/$25 — each reproduces the logged cost to the cent). Projected deltas:

- **Assignment at RS≥70 liquid (D2):** ~376 uncovered lines vs ~40 today ≈ +12k input tokens/call ≈
  +$0.04/call ≈ **+$0.15–0.25/day**.
- **Discovery widened 10× (NOT recommended, §below):** ≈ +$0.4/day if chunked ×5.
- **Description backfill one-off:** 87% of liquid RS≥70 already have descriptions (451/517); the rest is a
  few Haiku chunk calls, **< $1 once**. Sector is the thinner input (only 655 of 2,426 rows carry one) —
  backfill via the existing `mi_ticker_overrides` path, also ~free.
- **Validation scales with MEMBERS, not pool** — tripling membership ≈ +$0.06/day.

**Total at ~1,000-name reach: theme stack ≈ $1.5–2/day. Cost is a non-issue at every size measured.**

**Where it actually degrades — three real limits, none of them dollars:**

1. **Birth pressure.** More uncovered names in front of discovery = more births. The board already grew
   60 → 100 active themes in one month (07-06 → 08-04) at ~6 births/day, 18 on 08-04 alone, with a 56%
   2-member-noise share. Widening discovery before the birth gate acts pours into the leaky funnel — this
   is why D1 precedes everything.
2. **Single-call LLM clustering quality.** Discovery is one Sonnet call with a 4,000-token output cap that
   has already hit silent-stop truncation at today's 40-name pool (2026-05-12/13). A 400-line one-shot
   cluster is asking one call to do the whole market's taxonomy. Assignment does NOT share this failure
   shape — it maps names onto an existing theme list (bounded output, join-biased), which is why D2 widens
   assignment and leaves discovery narrow. Widening discovery safely would need chunking (by ecosystem) —
   deferred; the seeded lanes (§5) are the better discovery-widening mechanism.
3. **Readability** — his own constraint. Answered by structure (§4), not by staying small.

**Could NOT measure at $0:** LLM assignment/discovery *quality* at 5–10× prompt size. A proper check is a
replay of ~20 nights' assignment at the widened pool ≈ **$5–8 one-off** (40 Sonnet calls at ~22k in). Worth
running as D2's backtest evidence before the flip if the operator wants more than the #476 precedent
(the 60→200 ceiling widen shipped on design + forward junk-watch and was clean).

---

## 4. Q2 — How does a wider universe stay readable? (mostly already designed — this is #471/ADR-0032 plus one new display rule)

The operator's sketch — *"sub groupings and show the highest RS, biggest, strongest… other stocks are still
in a theme but not at the top"* — is, almost verbatim, ADR 0032 + #471 Phase 2 plus **one missing display
element**. Say it plainly: **most of Q2's answer already exists; do not build a new lane.**

Already built / in flight:
- **Ecosystem layer (ADR 0032 Phase 1, LIVE):** 21 ecosystems, 170 theme mappings; breadth-weighted D3
  score is deliberately fragmentation-proof (member-union dedup — splitting a cohort can't inflate it);
  `/themes` v2 renders ecosystems ranked with themes nested. This is the top level of readability.
- **Sub-themes (#471 Phase 2, SHIPPED + FLIPPED):** the Route-B split decomposed the 12-member cyber blob
  into parent + 3-member child; parent-link persistence fixed 7/25. #505 (parenting on every path) and
  #506 (hierarchy health metrics) are filed and sequenced behind the gate flip.
- **MAX_THEME_STOCKS=20 + fat-split:** the "50-stock theme nobody can validate" already cannot exist; a
  wide theme splits into named children instead.

The ONE new piece (small build, display-only):
- **Ranked member surfacing.** Data model unchanged — a theme keeps ALL its members in `tickers` (D2 is
  what puts the mid-RS members there). Display sorts members by `rs_composite` and shows the top K
  (proposal: 5) with `+N more (avg RS x)` — the reactive `/themes <name>` lookup already shows the full
  list. So: everyone in the theme, only the strongest on the board. One rendering change in
  `agent.py::_handle_theme_query` + the brief composer; no schema change, no new command.

What the operator sees after D2 + this: `E-DEF ▸ Defense Electronics & Subsystems (8): DFNS AADX ARXS MRCY
KTOS +3 · avg RS 84 · igniting` — one line instead of five duplicate 2-member themes.

---

## 5. Q3 — Should EP alerts feed theme discovery? Yes — and the mechanism half-exists

**His hypothesis is confirmed by measurement.** 73 HIGH alerts in 60 days (deduped ticker-day):

- **Pool expansion cannot reach them.** On their own alert date: 21/73 were inside today's top-200 reach;
  37/73 inside top-1,000; only 30/73 had RS ≥ 70, and only 40/73 had RS ≥ 50 at all. **RS is a 1/3/6-month
  lookback — a dormant group waking up has low RS by construction.** Even assigning against the entire
  liquid RS≥50 set reaches at most ~55% of alerts. This is the arithmetic behind the task-framing's "not an
  RS-floor problem", and it means D2 alone leaves the alert gap open: **EP alerts are the only signal in
  the system that sees a wake-up on day one.** That is a legitimate bottom-up input — it is price action
  (gap + volume), not a hypothesis.
- **The themeless alerts are cluster-shaped.** Of 47 themeless alerts (my in-theme definition: a live theme
  row within 7 days holding the ticker; the task brief's stricter same-day definition gives 51 — same
  picture), **30 (64%) had ≥2 other same-sector HIGH alerts within ±5 days; 36 (77%) had ≥1**. The
  themeless-alert problem is mostly GROUPS arriving together — exactly "a group coming back alive," not
  scattered one-offs. (Sector-proxy caveat, both directions: the late-July "Technology cluster of 14" is
  the earnings surge, not one theme — over-counts; and the defense cluster SPANS FMP sectors — PLTR/TSAT
  Technology, VOYG/AMRC/KTOS Industrials — so sector grouping under-counts real thematic clusters. The
  grouping that gets this right is narrative/LLM grouping, which is Lane 2's exact job.)
- **The defense worked example, fully traced.** On 08-04, three INDEPENDENT lanes lit on the same
  neighbourhood within 24h: Lane-2 co-gap produced `U.S. Government/Defense Spending Surge`
  {PLTR,TSAT,VOYG,AMRC}; the judge's theme-gap feed wrote two sector stubs covering AEIS/AMRC/CAT/VOYG and
  BTDR/PLTR/TSAT; shadow_v2 added `Government & Defense IT Services`; KTOS followed 08-05. The signal the
  operator wants ("this group is waking up") EXISTS in prod, expressed as five duplicate births nobody
  aggregates.

**Design (two parts, both consolidation not new lanes):**

- **(a) Flip the Lane-2 v2 narrative REGISTRY** (built dark 07-27, flag `lane2_grouping_v2`, OFF). The v1
  lane re-derives the dominant story nightly — that re-derivation is precisely what minted the duplicate
  pair (both defense dupes trace to `narrative_cogap` auto-promote). v2 is state-carrying: JOIN an active
  narrative / BIRTH from 2+ names / SEED a lone alert for cross-day accretion — the WULF 07-06 seed +
  CLSK 07-14 alert = 2-member birth chain is its acceptance case, and the defense cluster is a second,
  stronger one. Already operator-gated (registry replay + ADR-0030 judge eval); this doc adds urgency, not
  scope.
- **(b) NEW, small: a deterministic ecosystem-reactivation detector ($0 LLM).** The dormant-group memory
  already exists: `mi_theme_ecosystems` maps 12 historical theme names to E-DEF even though the defense
  themes all died (their 2-member lineages weak-Faded out in July — GD/LMT, LMT/RTX, ASTS/RKLB all Retired).
  Detector: nightly, map each EP alert ticker to its ecosystem (via historical theme membership or
  sector/override), and fire when an ecosystem with no live theme (or all-Fading) collects ≥3 distinct
  alert tickers within 5 trading days vs a quiet trailing baseline (defense: 5 alerts in 2 days vs 1 in
  the prior three weeks — the fixture). Output: an operator line ("E-DEF reactivating: 5 EPs/2d, no live
  theme") + a seeded discovery candidate carrying the alert cohort + the ecosystem's historical members.
  Pure read-model over `mi_ep_alerts` + `mi_theme_ecosystems` + `mi_themes`; observability + a discovery
  seed, never an auto-promote — the birth gate still owns whether it becomes a theme.

**False-theme cost:** bounded by the same walls that exist today — the birth gate floor/two-sighting/join
arms (a reactivation cohort still has to pass), Lane-2's 2-member same-day anchor, and no new auto-promote
source. The earnings-season caveat is real (the 14-peer "Technology cluster") — the reactivation detector's
dormancy precondition (quiet baseline + no live theme) is what separates a wake-up from a broad earnings
week; state that threshold derivation goes through the normal derive-don't-pick review at build time.

---

## 6. Q4 — Duplicates as a signal, not just a defect

**The machinery to convert duplicates into signal is already built and was watching it happen.** The
observe-mode birth gate, on the night of 08-04 itself, marked `U.S. Government/Defense Spending Surge` as
**join, overlap 1.00, target = U.S. Government/Defense Contract Surge** — and in observe mode correctly did
not act. Gate ON: the duplicate is never born; it becomes a **second sighting of the same cohort**, recorded
in the ledger with `sightings += 1`.

Observe totals since 07-29 (34 candidates): 22 await-second-sighting · 8 join · 3 birth · 1 held-floor —
i.e., the gate would have cut ~6 births/day to ~1-2 while CAPTURING the repeat-detections that today surface
as duplicate themes. Rebirth churn measured across the whole history says this is the norm, not a defense
quirk: **40 of 173 ended themes (23%) were re-born under a different name with ≥50% member overlap within
14 days** — the engine repeatedly re-derives what it just forgot.

**What to DO with the signal (new, small, display-layer):** an **ignition marker**. When a cohort
accumulates ≥N sightings/joins within K days (gate ledger) — or the §5 reactivation detector fires — the
theme/ecosystem line renders "igniting" with the count ("3 detections in 4 days"). Convergent detections
across lanes (Lane-2 + judge stubs + shadow, as on 08-04) are today's strongest emergence evidence and are
currently invisible. Reads `mi_theme_birth_candidates` + the gate's audit counters; no new table.

---

## 7. Q5 — What does the 7-day recency cap actually cost?

Measured across all 301 theme names ever:

- 174 ended. **156 ended by explicit Retired row** (lifecycle retire, weak-Fading streak, engine-drop
  synthetic retire, Arm-A dissolve). **Only 18 ended silently via the recency cap**, of which **12 were
  healthy at their last row (rs_avg ≥ 70, e.g. 10 not even Fading)**.
- So the cap's direct cost ≈ **12 healthy themes killed over ~4.5 months** — real, but ~7% of endings.
  The task-brief hypothesis ("the 7-day lifespan is the cap") is corrected in §2: the dominant fixed-clock
  killer is the **weak-Fading 5-day retire streak on 2-member themes** (the 7–8-day lifespan bucket alone:
  34 themes, 32 of them explicitly Retired; 1–2-day lifespans: 30 more).
- Both killers are already being attacked by shipped/queued work, which is why D4 recommends no new
  mechanism: **#368 F2** (healthy-held Fading rows no longer count toward the streak — 14 wrong
  retirements Jun–Aug), **the birth gate** (fewer fragile 2-member births to die in week one), **#531**
  (nightly alert on retired-while-healthy — the cap's silent kills now have a watchdog), and **D2 breadth**
  (a 6-member theme does not weak-Fade because one member dips; 2-member themes structurally do).
- The one thing the cap-killed themes lose that matters is MEMORY — and §5(b) restores it: the ecosystem
  mapping retains the lineage after the theme dies, so a dormant group's return is recognized instead of
  re-discovered. Raising `stale_after_days` is NOT recommended: it exists to stop zombie re-validation
  (135 spurious cooldowns, 2026-04-24), and 12 kills in 4.5 months does not justify re-opening that.

---

## 8. Options considered and rejected

- **Widen discovery to 400+ names in one call** — rejected: output-cap fragility is already observed at 40
  names; birth pressure multiplies pre-gate; the seeded lanes reach wake-ups that RS pools structurally
  cannot (§5). Discovery stays narrow; seeding + assignment carry the width.
- **Raise the RS floor to cut themeless alerts** — rejected by arithmetic: themeless rate is 80% in the
  RS 70–89 band; alerts are majority sub-RS-70 on alert day. Confirms the task framing.
- **A new "EP theme lane" separate from Lane 2** — rejected: Lane-2 co-gap IS the EP-groups-into-themes
  lane; building a sibling re-creates the 7-source sprawl the 07-27 consolidation just collapsed. §5 adds
  one deterministic detector and flips what is already built.
- **Merge duplicate themes after birth (#529-style)** — rejected as the primary tool: prevention at birth
  (gate join arm) is already built and cheaper than post-hoc adjudication; #529 stays parked per its own
  operator correction.
- **Expand the stored universe past ~2,400 (collector change)** — not proposed: no evidence need — the
  liquid 1,762 already contains 3× more RS≥70 names than the system covers; revisit only after D2's
  coverage gain is absorbed.

## 9. What the operator must decide vs what can just be built

**Decide (sign-off needed):** D1 order-confirmation (gate first) · D2 assignment floor 90→70 + ceiling
600 (the one new criteria change; CHANGE_PROCESS entry + optional $5–8 replay backtest first, operator's
call) · D3(a) Lane-2 v2 flip (already gated on its replay + judge eval — this doc just links the defense
fixture to it).

**Just build (no-money, ship-full class):** ranked member display (§4) · ecosystem-reactivation detector
(§5b, thresholds via derive-don't-pick review) · ignition marker (§6) · description/sector backfill (<$1).

**Explicitly not measured (honest gaps):** LLM quality at widened prompts (cost to measure: $5–8 replay) ·
true theme-level cluster rate of themeless alerts (sector proxy used; an LLM regrouping replay ≈ $2) ·
the brief's "4 exact-duplicate pairs live" — as of this measurement 1 exact pair remains on the latest-row
board (the defense pair); the others resolved/renamed between the 08-05 morning measurement and mine ·
forward junk-assign rate at the wider pool (a watch, per the #476 precedent, not a pre-measurement).
