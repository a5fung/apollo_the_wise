# #479 — Materiality-driven evening brief (DESIGN PROPOSAL, no code changed)

**Supersedes** `479_brief_consolidation_proposal_2026-07-26.md` (same day, rejected on shape).
The operator's correction, which this document is built around:

> "it basically just trims here and rearrange there … What you need to look into is how to
> present material info for the day, each day will differ, areas that had no changes aren't
> important to surface except mention no changes or quick summary, areas that have material
> changes need to capture my attention"

A fixed template shows everything every day and therefore regrows. This design replaces it with
a brief **computed fresh each evening from what changed since the prior trading day, ranked by
materiality**. Unchanged areas collapse to one line. Everything below is grounded in prod data
pulled today (SELECT-only, `ssh apollo@87.99.134.162`); every threshold shows the distribution
that justifies it. **No code was written; nothing behavioral is proposed for any detector,
safeguard, or entry path — this is a display-composition change only (THE LINE untouched).**

---

## Summary (read this, skip the rest if pressed)

- **The central empirical finding: name-level day-over-day churn is noise everywhere in this
  system.** Top-10 RS churns 3/10 names a day; the RS≥99 club (~20 names) turns over 5 in / 5 out
  daily; RISING's top-6 replaces 3/day; RECOVERY's top-12 replaces 4.5/day; 4.2 themes are BORN
  per day (median birth score 86 — born-high is the norm); high-RS themes change lifecycle stage
  4×/day in both directions. A diff-driven brief that surfaced name-level changes would be
  *noisier* than the fixed template. Materiality therefore lives at three levels only:
  1. **State-machine flips** — regime label (1 per ~6 days), crypto verdict (1 per ~6 days),
     breadth-cluster fire, EP-filter threshold change.
  2. **Magnitude moves on persistent entities** — theme `rs_avg` day-over-day |Δ| at p90/p95
     cuts (8 / 12 points), VIX day-move at p90 (2.7).
  3. **Deep jumps, not shuffles, on name lists** — into top-10 from beyond yesterday's #25
     (~1.1/day); everything shallower is a counted shuffle.
- **"Yesterday" already exists for almost everything.** `mi_market_regime`, `mi_stock_scores`,
  `mi_themes` (incl. `rs_avg`), both closes tables, and all event tables are dated;
  `get_rs_velocity/recovery/turners` already take a date parameter, so yesterday's lists are
  recomputable with zero new persistence. Only four things cannot be diffed today (§2):
  ecosystem grouping history, pre-6/24 numeric net score, "what last night's brief showed"
  (repeat-suppression memory), and any sector-clustering of low-RS names (26% sector coverage;
  3 of 69 recovery names had a sector on 7/24).
- **Ranking = fixed class precedence** (predictable, §3): regime-state flips → theme material
  moves → leader deep jumps → scan-recap exceptions → standing counts. Never re-ordered by a
  per-day score.
- **Near-quiet day (real 7/22) = ~700 chars; true-zero night ~560** (§4). Busy day = real
  2026-07-16 data, ~950 chars (§5) — vs 4,948–5,248 chars every night for the last 4 nights of
  the current template.
- **First slice** (§8): a compose-time diff module — read-only SQL against existing dated
  tables, no new tables, no scheduler change. Delivers the whole §4/§5 shape. Slice 2 adds a
  small brief-snapshot table for repeat-suppression and "shown N nights" counters.

---

## 1. Materiality, per signal, from measured distributions

Method note: distributions pulled 2026-07-26 from prod. RS-leader queries approximate
`get_rs_leaders`' Python-side filters (ADV ≥ 500k, close ≥ $10; without `SKIP_TICKERS_LIST` /
sector post-filter — direction of every conclusion is unaffected, the filters remove a handful
of names). Theme diffs join per-name to the *last seen row ≤ 4 days back* (themes legitimately
skip days — a strict yesterday-join manufactures 6.5 phantom "births"/day). Score history is
dense for the recent 60 days (44 score-dates); pre-June sparse days were excluded from churn
stats where noted.

### 1.1 REGIME — material on **label flip** or **EP-filter change**; VIX secondary

180d of `mi_market_regime` (129 rows):

```
label flips              22 / 129 days   (~1 per 6 days)
net-score changes        ~every other day (parseable rows)
VIX |Δ| day-over-day     avg 1.54 · p90 2.70 · max 21.64
```

- **Material: the label flip** — it is also exactly what changes trading posture
  (`ep_threshold` 70→75 on the 7/16 Choppy→Correcting flip, size multiplier). The brief must
  state the threshold/size consequence on the flip line, because that is what the operator acts
  on.
- **Material: breadth-cluster fire** (existing `cluster_fires` rule) — already fires-only.
- **Secondary: VIX day-move ≥ 2.7 (p90).** Shown only when it fires; on flip days it rides the
  flip line.
- **NOT material alone: net score.** It moved on ~half of all parseable days (15 changes in the
  22 post-6/24 rows) — the label banding exists precisely to absorb this jitter. Net appears as
  context on the flip line and in the quiet-day state line, never as its own item.
- Flip-flap context: flips oscillate between adjacent bands (7/13→7/16 flipped 3× Choppy↔
  Correcting). A flip that reverses a ≤2-session-old flip still shows (it moves the EP filter)
  but carries a "2nd flip this week" annotation so the operator reads chop, not trend.

### 1.2 THEMES — material on **|Δ rs_avg| ≥ 12** (itemized) / **≥ 8** (counted); births and stage flips are NOT events

`mi_themes.rs_avg` is what the scorecard actually diffs against today
(`get_prior_theme_scores` reads it; the rendered Δ is live-code behavior already — this design
promotes that Δ from decoration to the selection criterion). 120d, n=1,774 name-joined
day-pairs (gap ≤ 4d, prior > 0 — a `rs_avg=0` prior row produced one fake +70.6 "move" on 7/24;
the guard is an implementation requirement):

```
|Δ rs_avg|   med 1.85 · p75 4.30 · p90 8.40 · p95 11.70 · p99 30.3
≥ 8   →  206 events / 77 days  ≈ 2.7/day
≥ 12  →  0–3 per day (last 10 days: 1,0,1,1,2,2,1,1,3,3)
```

- **Itemize |Δ| ≥ 8** (p90), capped **top-5 by |Δ|** — typical day 2.7 movers, so the cap binds
  only on busy days (7 movers on 7/23 and 7/24). Each line: name, new level, Δ, stage.
- **⚡-mark |Δ| ≥ 12** (≈p95, 0–3/day) — the emphasis tier; ≥1 such mover is what makes the
  theme class count toward the headline ("⚡ N material tonight").
- **Count the overflow** as one line ("+2 more ≥8 · 44 quiet · `/themes`").
- **Births: count only.** 190 first-ever appearances in 120d ≈ **4.2/day**, median birth
  `rs_avg` **86.3** — themes are born high *by construction* (they emerge from RS leadership),
  so "new theme at 89" is the modal event, not news. Only **55.6%** survive to active-day-7
  (153-birth cohort). The material event is **graduation** — first time a theme reaches 7 days
  alive and still active: ~0.8/day, itemizable ("Graduated: Uranium Fuel Cycle — survived
  validation week"). `mi_themes.days_active` exists to drive this (semantics to confirm at
  build).
- **Stage transitions: NOT individually material.** 361 transitions among rs_avg≥70 themes in
  82 days (4.4/day), and they oscillate — Fading→Accelerating 81 times vs Accelerating→Fading
  77 times in the same window. A stage flip appears only as the annotation on a theme that
  already qualified by |Δ| (e.g. "95.5 +33.5 → Accelerating").
- **Top-5-board churn is also noise**: 1.63 new names/day in the top-5 by rs_avg (median 1;
  only 12 zero-days of 78) — age-gating to ≥5-day-old themes barely helps (1.58). Rank entry is
  therefore *not* a materiality trigger; only magnitude is.

### 1.3 RS LEADERS — material on **entry into top-10 from beyond yesterday's #25**; all else is a counted shuffle

45d dense window (29 adjacent-day pairs):

```
new names in top-10 per day     avg 3.1 · med 3 · p90 4.2 · zero-days 1/29
  … from beyond yesterday #25   32 events ≈ 1.1/day
  … from beyond yesterday #60   21 events ≈ 0.7/day
RS≥99 "club" (value-defined)    ~20 names · 5 in + 5 out per day · zero quiet days
```

Rank churn is partly a **tie artifact**: 8+ names print RS 100 and `ORDER BY rs_composite DESC`
breaks ties arbitrarily — two identical queries run minutes apart returned different owners of
rank 7 for the same date. Even the tie-invariant RS≥99 club turns over 25% daily. So:

- **Itemize: a name entering the top-10 from beyond yesterday's #25** (~1/day), with its rank
  path — this is the "came out of nowhere" event worth charts tonight. Real example, 7/16:
  `CDNA #82 → #3`, `MAN #49 → #4`.
- **Everything shallower: one count line** ("top-10 otherwise: shuffle only"). The full list is
  one pull away — the phrase "rs leaders" routes to `_handle_rs_query` (verified,
  `agent.py:938→949,4734`).

### 1.4 CRYPTO vs MARKET — material on **verdict band flip**; recomputable, no snapshot needed

Recomputed the shipped formula (avg BTC/ETH 4-wk return − QQQ 4-wk, ±3 bands) for every day,
68 trading days:

```
verdict flips        11 / 68 days  (~1 per 6 days)
|Δ lead_4w| daily    avg 2.70 · p90 5.86
```

- **Material: the band flip** (LEADING↔IN LINE↔LAGGING). Secondary: |Δ lead| ≥ 6 (p90) without
  a flip.
- Otherwise one state-line entry ("Crypto LEADING, 6th day"). "Yesterday" is recomputed from
  `crypto_daily_closes` + `mi_daily_closes` at compose time — **no new persistence**.

### 1.5 EP RECAP — material on **terminal-state exceptions**, never on detection

HIGHs are already alerted in real time intraday (151 in 90d ≈ 2.4/trading-day; ≥1 HIGH on ~78%
of days). By evening, detection is old news; what the operator hasn't seen is the **terminal
state**: entered / filled / skipped-with-reason / missed-window.

- **Itemize: any HIGH that produced an entry, or a HIGH that ended in an anomalous terminal
  state** (no terminal state, `infra:*` skip).
- **Count: everything else** ("EP: 0 HIGH · 2 MODERATE · no entries" — the real 7/24 line).
- History stays reachable via the phrase "ep outcome" (verified `agent.py:883`).

### 1.6 The churny lenses — RISING / RECOVERY / ROTATION: honest verdict — **cannot be made name-material with today's data**

```
RISING  top-6 churn    3.0 new/day (30d window) — half the list daily
RECOVERY top-12 churn  4.55 new/day · zero quiet days in 80
RECOVERY raw filter    avg 76 qualifying/day · 35 new/day
ROTATION substrate     requires sector — see below
```

The obvious upgrade — "a recovery *cluster* forming in one sector" (the July crypto-proxy
case) — is **blocked by sector coverage**: `mi_stock_scores` carries sector for only the
enriched top slice (26.1% of 7/24 rows; **3 of the 69** recovery-band names). `get_rs_turners`
already silently operates on that sliver (it requires `sector IS NOT NULL`). Until sector
coverage widens, these three lenses collapse to **one aggregate state line each with their #1
name** ("Recovery: 69 qualify (avg 76), top BMNR" ) — never itemized, never silently absent
(an explicit line on quiet days confirms the check ran). They have **no drill-down command
anywhere** (verified again: `get_rs_velocity`/`get_rs_recovery`/`get_rs_turners` have no
operator-facing caller outside `briefing.py`) — since the lines stay inline, nothing is
orphaned; whether to *build* a `/turning` command is §9-Q1.

### 1.7 UNANCHORED (RS≥80 leaders in no theme) — a standing population, not an event; its natural home is a **delta-counted state line + persistence alarms**

Recomputed daily for 62 days (top-30 leaders × same-date `mi_themes` membership):

```
standing count   avg 16.0/day · max 24 · zero-days 0
new entrants     4.3/day
persistent set   6 names unanchored ALL of the last 5 sessions at RS≥90:
                 CDNA · CLMT · FBRX · TRAX · TXG · URGN
```

The old fires-only section would have shouted 10 capped names **every single night** — it was
never a rare event. Materiality-driven presentation *does* give it a natural home, in two
parts: (a) a standing state line with delta ("Unanchored 16 (±0)"), and (b) an **itemized event
only when the persistent set changes** — a name crossing 5 consecutive unanchored sessions at
RS≥90 (a theme-engine coverage gap: today that set contains the #1–#4 RS leaders, which is a
real finding about theme coverage, surfaced once, not nightly). This is the signal's only home
in the system (re-verified: no other surface computes it).

### 1.8 The count-collapsed remainder

```
cooldowns    4.2 new/day (265/90d) — count + active total ("17 active (+7)"); list = "show cooldowns" (agent.py:833)
wick         1.1/day — count; 30d fill-rate on Fridays only; "/wick" + "wick watch" (agent.py:5463, 861)
U&R          0.06/day (4 in 90d!) — line only when nonzero; /detectors (agent.py:5476)
flag-breaks  2.5/day but bursty (26 active days of 90) — count when nonzero; /detectors
fund flags   dated (mi_fundamental_flags.flag_date) — stays a per-row suffix on itemized names, not a signal
signal quality (Fri)  30d aggregate, no diff meaningful — Friday-only block, unchanged from prior proposal
9M / sugar babies     DROPPED per operator ruling today (strategy retired; /9m + /sugarbabies verified reachable, agent.py:5451, 5467)
MA pullbacks          pull-tool, on-demand only — phrase "pullback" (agent.py:954)
v1.0 closeout line    stale since the 7/24 declaration — retire (carried from prior doc §0.5)
```

---

## 2. Where "yesterday" comes from — the diff substrate

| Signal | Prior state source | Status |
|---|---|---|
| Regime label / VIX / ep_threshold / breadth | `mi_market_regime` (365 rows, PK regime_date; breadth_monitor since 3/23) | **diffable now** |
| Theme rs_avg / stage / tickers / days_active | `mi_themes` (3,527 rows since 3/19; per-name LAG ≤4d, prior>0 guard) | **diffable now** |
| RS ranks / clubs / unanchored | `mi_stock_scores` (dated; dense 44/60 recent days; ~2,400 rows/day) | **diffable now** |
| RISING / RECOVERY / ROTATION lists | recomputable — the three functions already take a date param | **diffable now, zero new code beyond a second call** |
| Crypto verdict | recomputed from `crypto_daily_closes` + `mi_daily_closes` | **diffable now** |
| Cooldowns | `mi_validation_cooldowns` (removed_at + cooldown_until reconstruct any past active set) | **diffable now** |
| EP / wick / U&R / flag events | event tables, dated by nature — events ARE diffs | **diffable now** |

**Cannot be diffed today** (the design constraint, stated plainly):

1. **Ecosystem grouping** — `mi_theme_ecosystems` is current-state only
   (`theme_name, e_code, method, assigned_at`; no dated rows). Yesterday's grouping is
   unrecoverable after a reassignment. *Consequence:* no ecosystem-level aggregate diffs; theme
   diffs run at theme level (which needs nothing from this table — grouping is presentational).
2. **Numeric net score before 2026-06-24** — only 22 of 129 recent regime rows carry "Net
   score" in description text; older rows would need recomputation from stored components.
   *Consequence:* none going forward; net-score deltas are secondary context anyway.
3. **"What last night's brief showed"** — `evening_brief_sent` audit rows store char counts,
   not content. *Consequence:* repeat-suppression ("same theme led two nights running") and
   "shown N nights" counters need a small snapshot table — deferred to slice 2; daily diffs are
   largely self-limiting without it.
4. **Sector-clustered materiality for sub-top-300 names** — 26% sector coverage; 3/69 in the
   recovery band. *Consequence:* §1.6's aggregate-only treatment. Widening sector enrichment is
   a separate (paid-API-cost) decision, not assumed here.

---

## 3. The ranking rule — fixed class precedence

When several things are material, order is **by class, always the same** (surprise in the top
slot is the enemy of trust — the operator should know where flips live before opening the
message). Within a class, magnitude descends. Classes with nothing material emit nothing here
and collapse into the state block.

```
1. REGIME-STATE FLIPS   regime label · breadth-cluster fire · EP-filter change · crypto verdict flip · VIX ≥ p90
2. THEME MOVES          |Δ| ≥ 12 itemized (top-5) · graduations · persistent-unanchored set changes
3. LEADER DEEP JUMPS    beyond-#25 → top-10, with rank path
4. RECAP EXCEPTIONS     EP entries / anomalous terminal states · detector lines when nonzero
5. STATE BLOCK          one line per quiet area, fixed order (regime · crypto · themes · leaders · lenses · EP · detectors · unanchored · cooldowns)
```

Rationale: class 1 changes *how the operator trades tomorrow* (filter, size); class 2 changes
*where to look*; class 3 changes *which charts*; class 4 closes today's loop; class 5 proves
every check ran. A headline count ("⚡ 3 material tonight") caps the top so a glance sizes the
night.

---

## 4. Quiet-day shape

Near-quiet, real pattern (2026-07-22: no regime flip since 7/16, one ⚡ theme mover, 3 total
≥8, 10 births, no HIGH) — one small material block, then the state block:

```
*Apollo Evening Brief — 2026-07-22*
⚡ 1 material tonight

1️⃣ 📊 *THEME BREAK*
⚡`Copper Mining   66 -13.0`  Nascent
   _+2 more ≥8 · 47 quiet · 10 seeded · `/themes`_

— no change —
Regime CORRECTING (5th day) · net -1 · VIX 16.6 (-0.4) · filter ≥75 · size ≈0.75×
Crypto IN LINE (unch) · EP: 0 HIGH · 2 MOD · no entries · Detectors: quiet
Leaders: top-10 shuffle only, no deep jumps
Lenses: Rising 14 qual · Recovery 71 qual · Rotation none ≥3wk
Unanchored 16 (±0) · Cooldowns 17 (+3) — `show cooldowns`

detail: `/regime` `/themes` "rs leaders" `/eps` "ep outcome" `/detectors` `/wick` "pullback"

_Do your review. Pull up charts. Apply your judgment._
```

**652 chars (measured), one message.** A TRUE zero-material night (no flip, no ⚡ mover, no deep jump, no
entry) drops block 1️⃣ entirely and the header reads "✅ Nothing material tonight" — 11 lines,
~560 chars. Note the §1 base rates imply *some* material item is the modal night (⚡ theme
movers alone had only 1 zero-day in the last 10) — the quiet shape is the floor, not the
average; the average night is the 7/22 shape. Every state line asserts "checked, nothing";
silence never means "not run".

---

## 5. Busy-day mock — real 2026-07-16 data

Everything below is from prod rows for 7/15→7/16 except the lines marked ⓘ (illustrative —
requires computations not run for that date).

```
*Apollo Evening Brief — 2026-07-16*
⚡ 3 material tonight — regime flipped

1️⃣ 🟠 *REGIME: CHOPPY → CORRECTING*
   EP filter 70 → 75 (tightened) · size ≈0.75×
   Net +1 → 0 · VIX 16.7 (+1.1) · 2nd flip this week — chop
   `/regime` full matrix

2️⃣ 📊 *THEMES — 6 moved ≥8, top 4:*
⚡`Semi Wafer Foundry    60 -12.1`  Fading
`Immunology Biologics  84 -11.5`
`Protein Degradation   83 -11.5`
`Digital Ad Platforms  98 +10.9`  ← now #1
   _+2 more ≥8 · 44 quiet · 9 seeded · `/themes`_

3️⃣ 🚀 *LEADERS — 2 deep jumps into top-10*
`CDNA  RS 100   #82 → #3`  molecular diagnostics
`MAN   RS 100   #49 → #4`  staffing
   _other slots: shuffle only · "rs leaders"_

— no change —
🪙 Crypto LEADING (+8.8 vs QQQ 4wk) ⓘ6th day
ⓘEP: 0 HIGH · 2 MODERATE · no entries · Detectors: 1 wick
ⓘLenses: Rising 12 qual · Recovery 68 qual · Rotation none ≥3wk
ⓘGraduated: none · Unanchored 16 (+1) · Cooldowns 15 (+2)

_Do your review. Pull up charts. Apply your judgment._
```

**948 chars (measured) — one message with >3,000 chars of headroom** against the 4,096 limit, on a day
carrying a regime flip + 4 near-double-digit theme moves + two 50-rank leader jumps. (Only the
Semis −12.1 clears the ⚡ p95 tier on 7/16 — the other three ride in on the ≥8 top-5 rule, which
is exactly why the itemize bar sits at p90 with a cap rather than p95 alone: an 11.5 break in a
theme at 84 is attention-worthy and a hard 12 cut would have hidden two of them.) The current
live template spent 4,948–5,248 chars on
each of the last four nights — quieter nights than this one — and split into 2 messages every
time. No pipe tables; ticker/theme rows are monospace code lines (Telegram-safe).

---

## 6. Reachability — every collapsed signal has a VERIFIED pull path

Checked directly against `agents/market_intelligence/agent.py` (dispatch dict lines 5449–5501 +
keyword cascade) and `channels/telegram.py::_register_commands` (11-entry menu, line 1770).

| Signal collapsed/counted | Pull path | Verified at |
|---|---|---|
| Full breadth matrix, net-score drivers | `/regime` | agent.py:5455 |
| Full theme board (all 50, ecosystems) | `/themes` | agent.py:5452 |
| Full RS leader list | phrase "rs leaders" (keyword "rs"/"leader") | agent.py:938→949, handler 4734 |
| EP alert detail | `/eps` | agent.py:5450 |
| EP outcomes history | phrase "ep outcome" | agent.py:883 |
| Detector roll-up + per-ticker | `/detectors` | agent.py:5476 |
| Wick telemetry | `/wick` or "wick watch" | agent.py:5463, 861 |
| Cooldown list | "show cooldowns" | agent.py:833 |
| 9M (dropped from brief, operator-ruled) | `/9m` · `/sugarbabies` | agent.py:5451, 5467 |
| MA pullbacks (pull-tool) | phrase "pullback" | agent.py:954 |
| Snapshot front door | `/hud` (menu) | telegram.py:1770, agent.py:5449 |
| RISING / RECOVERY / ROTATION detail | **none exists** — lines stay inline (aggregate), so nothing is orphaned; building `/turning` is §9-Q1 | grep: no caller outside briefing.py |
| Unanchored detail | **none exists** — inline state line + persistence events are its only home (by design, §1.7) | grep: no other surface |

---

## 7. What this design does NOT do

- Does not touch any detection criterion, safeguard, sizing, entry/exit logic, or scheduler
  job — the composer's *inputs* are unchanged; only selection & rendering change (THE LINE).
- Does not resurrect 9M/sugar-babies (operator-ruled off today) or Fishhook (cleanly retired).
- Does not diff at ecosystem level (undated table, §2 item 1) or sector-cluster level (§1.6).
- Does not propose new snapshotting in slice 1 — every slice-1 diff reads existing dated
  tables.
- Does not keep the always-on top-10 list, RECOVERY top-10 rows, or per-name RISING rows —
  replaced by deep-jump itemization + counts (§1.3, §1.6). This is the one real presentation
  loss vs today; flagged as §9-Q2 rather than smoothed over.

## 8. Feasibility & first slice

**Cheap (slice 1 — the whole §4/§5 shape):** one new composer module (pure functions:
`(today_rows, yesterday_rows) → material_items + state_lines`), called by
`send_evening_briefing` in place of the current section stack. Every diff is a LAG/self-join on
an existing dated table or a second call to an existing date-parameterized function. The
existing formatters/fetches stay for the on-demand commands. Testable offline against the
historical tables (the mocks above ARE replays — 7/16 and 7/22 recompute exactly).

**Medium (slice 2):** `mi_brief_snapshots` (brief_date PK, JSONB payload of items shown) for
repeat-suppression + "Nth day" counters; graduation events off `days_active`; persistent-
unanchored set-change events (needs the 5-session rolling computation, cheap SQL). None of it
blocks slice 1.

**Not in scope / separate decisions:** sector-coverage widening (unblocks cluster
materiality); a `/turning` command; menu changes.

## 9. Open questions for the operator

1. **RISING/RECOVERY/ROTATION**: accept aggregate-only lines (name-level is measured noise,
   §1.6), or additionally build a `/turning` drill-down so the full lists exist somewhere?
   **Rec: aggregate-only now; build the command only if you find yourself wanting the lists.**
2. **Losing the always-inline top-10 list** (nightly chart-review habit?): the diff replaces it
   with deep-jumps + "rs leaders" on demand. Keep the replacement, or pin the 10 names as one
   dense line ("`TRAX FBRX CDNA TXG MAN UTZ XNCR SYRE FTRE HPE`", ~60 chars)?
   **Rec: pin the one-line version — costs a line, preserves the habit.**
3. **Threshold sign-off** (all display-only, all from §1 distributions): theme itemize ≥8
   capped top-5, ⚡-emphasis ≥12; leaders beyond-#25; VIX ≥2.7; crypto bands as shipped (±3).
4. **v1.0 closeout line**: retire (stale since 7/24 declaration) — carried from the prior
   proposal, presumably already ruled.
