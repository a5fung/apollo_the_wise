# #344 Late-Source Replay — the 6/22 launch-gate evidence

**Date:** 2026-06-19 · **Harness:** `scripts/_344_late_source_replay.py` (read-only) ·
**Gate:** operator's "Gate 6/22 on it" decision (launch slips if #344 isn't shadow-validated by 6/22).

## The question

BFLY 6/18 was graded `routine` at 7:00 ET on a **web-only** corpus
(`has_direct_source=false`); the MidJourney/Butterfly PR hit Benzinga ~8:12 ET
(72 min later); the per-day catalyst cache pinned the stale routine grade all day
→ no alert. The proposed fix (#344) was **cache surgery + a re-poll on a
`has_direct_source` False→True transition.** This replay asks the gate question
the advisor framed: **would that fix have recovered any alerts — i.e. is it worth
the hot-path risk?**

## Method (lookahead-free, read-only — see harness docstring)

- **Cohort** = `ep_catalyst_provenance` audit rows with `has_direct_source=false`,
  deduped to the earliest grade per ticker/day (container-restart re-fires log a
  later 2nd row — 6/15's 118 raw rows collapse on dedup).
- For each, gather **primary-subject** direct sources (SEC 8-K/6-K + Benzinga
  press wires) and bucket each by arrival vs the grade time and the **ORB
  submission cutoff (09:45 ET)** — a source after 09:45 can't rescue the 9:31 ORB
  entry no matter what.
- Re-grade **only** the subset where a direct source landed *in* `(grade, 09:45]`,
  on the same no-web corpus minus the late source (so the only moving part is the
  late source; web omitted = lookahead). Re-grade uses the **live**
  `_classify_catalyst_claude` + rubric v3 (freshness/materiality baked in).
- **Fire-through** is bounded from `mi_ep_scan_log` (persisted routine `ep_score` +
  `gap_pct`) + the catalyst raw delta (routine 0 → strong +15 / gc +25) × the
  alert-date regime multiplier + the gap-driven conviction floor — not a
  from-scratch recompute (no rvol/vol_pct re-derivation = no lookahead).

## Result — the funnel (12-day window, 2026-06-07..06-19; all post-Wave-B data)

| Stage | Count |
|---|---|
| 0 — web-only grades (deduped ticker/day) | **21** (19 routine, 2 strong) |
| 1 — had ANY primary-subject direct source (any time) | 12 |
| 2 — direct source arrived IN `(grade, 09:45 ET]` | **2** |
| 3 — re-grades to a HIGHER tier on that late source | **0** |
| 4 — fires a NEW HIGH (not already HIGH-alerted) | **0** |

**The cache-staleness fix would have recovered 0 alerts across every day of
available evidence.** Only 2 of 21 web-only grades even had a late in-window
direct source, and **both grade `routine` on the actual source:**

### Case 1 — BFLY 2026-06-18 (the motivating case) → stays `routine`
In-window source: Benzinga 8:12 ET — *"Butterfly Network Provides Updates On Its
Midjourney Medical And The Midjourney Scanner Tomographic Imaging Machine;
Prototype Incorporates 40 Butterfly Ultrasound-on-Chip Imaging Modules Per
System."*
Re-grade reasoning (verbatim): *"a vague, promotional product update with no
concrete financial details — no revenue figures, no contract value, no FDA
approval, and no named customer or partner. For a $2.3B market [cap] …"* → routine.

**Implication: BFLY would NOT have been rescued by ANY cache/timing fix.** With
the perfect direct source in hand at grade time, the grader still returns routine.
The BFLY miss is therefore **not** a cache-staleness problem — it is either a
**correct rejection** (product/prototype hype, no financials, not EP-grade) or a
**materiality-rubric** question (should a no-financials product PR that gaps the
stock +13.5% grade above routine?).

### Case 2 — BTQ 2026-06-18 → stays `routine`
In-window source: SEC 6-K — an **at-the-market (ATM) equity offering** sales
agreement with Cantor Fitzgerald for up to C$150M. Re-grade reasoning: *"a share
issuance/dilution mechanism, not a positive business catalyst — ATM offerings are
typically neutral-to-negative for existing shareholders and do not explain a
gap-up."* → routine. Agent reads this as a clear correct rejection (dilution is not
a catalyst), but the HARD gate requires the operator's label (below) — the agent
does not self-classify even the easy one.

## Why the verdict holds — the LOAD-BEARING evidence is the enumeration

The spine is **not** the no-web re-grade or the restart experiment — both are
corroboration. The spine is the **complete enumeration plus the hand-read of each
case:**

1. **Stage-2 is a full census, web-independent.** Counting how many web-only grades
   had a primary-subject direct source land in the ORB window uses production's own
   `get_alpaca_news` / `get_sec_recent_filings` / `is_primary_subject_news` — it
   does **not** depend on the no-web re-grade, so the no-web caveat doesn't touch
   it. The answer is **2 of 21**. The addressable surface is tiny and fully
   enumerated.
2. **Both cases read by hand.** BFLY = a no-financials product/prototype PR; BTQ =
   an ATM dilution. Neither is an EP-grade catalyst on its face. This reading never
   relies on the no-web re-grade.

That pairing settles the gate. The two corroborating checks below only fail to
contradict it.

**Corroboration A — production's own restart re-grades (timing-limited).** A
container restart clears `_catalyst_cache`, so a later same-day
`ep_catalyst_provenance` row is a real production re-grade on the full web+direct
corpus. Across **12 eligible** ticker/days (first grade `has_direct_source=false`,
so a `false→true` flip was actually possible; 23 multi-row days total),
`has_direct_source` flipped `false→true` **0** times and **0** re-grades lifted the
tier. Caveat: this only samples *restart-timed* re-grades, not the continuous
re-poll the fix would run — corroboration, not the spine.

**Corroboration B — the #210 flank.** Of the 10 cases with a direct source that was
*not* in-window, **0** were same-day before-grade primary-subject sources — every
one is a prior-day (stale) filing. Production never graded web-only *despite* an
available same-day direct source; no live #210 sourcing gap hiding here.

(Note the no-web reconstruction can only **undercount** recoveries — production's
re-poll keeps web and `with-web grade ≥ no-web grade` — so "0 reconstructed
recoveries" is a floor, not the argument. The enumeration + hand-read is.)

## Gate read

**#344's cache surgery is NOT launch-blocking.** The addressable surface is fully
enumerated at **2 of 21** web-only grades, and both in-window sources are weak
catalysts (product hype, dilution) that grade routine on the merits (BFLY, BTQ) —
so the cache re-poll has nothing to recover. Production's own restart re-grades
corroborate (0 of 12 eligible flipped), and there's no same-day sourcing gap. The
staleness *mechanism* is real but the data doesn't exercise it to a single
recovery — so the hot-path cache surgery is **deferred, not shipped**, for 6/22.
Caveat: the window is short (provenance only since 6/7); the fire-through path is
**unexercised** (0 recoveries → untested code if a wider window ever reaches
stage 3).

**This reframes #344.** The live question the operator raised ("was BFLY a missed
EP?") is now a **catalyst-correctness / materiality** question, not a timing fix:

## ⚖️ Operator labels needed (HARD gate — agent must not self-classify)

1. **BFLY 6/18** — is `routine` the **correct** grade for a no-financials
   product/prototype PR that gapped the stock +13.5%? Or should the
   product/innovation catalyst grade strong+ (a materiality-rubric change)?
2. **BTQ 6/18** — confirm `routine` (ATM dilution) is correct (agent reads it as a
   clear correct rejection, but the gate requires your label).

**If (1) = "routine is correct":** the 6/22 gate is satisfied by *this*
shadow-validation — the cache fix isn't needed and is **deferred** (kept on the
backlog, not built; Check A = 0/23 production flips is the evidence). **If (1) =
"should be higher":** the real work is a catalyst-materiality rubric change for
product/innovation catalysts → CHANGE_PROCESS + N≥10 backtest + sign-off (a NEW
task, NOT the cache fix), and the 6/22 launch gate should be re-pointed at that
question.

## Reproduce

```bash
docker cp scripts/_344_late_source_replay.py apollo-market:/app/scripts/
docker exec apollo-market python scripts/_344_late_source_replay.py --lookback-days 12 --orb-cutoff 09:45
# single case: --ticker BFLY --lookback-days 3
```
