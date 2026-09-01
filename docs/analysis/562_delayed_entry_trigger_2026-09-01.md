# #562 — What IS our delayed-entry trigger today, and where do watched names actually die?

**Date:** 2026-09-01 · **Read-only diagnosis** — no code, no thresholds, no strategy changed.
**Acting-rules source:** `live_rules_2026-09-01.txt` (captured 2026-09-01 06:27 PDT, 0 drift findings) — every constant below re-read from code, not memory.

---

## The decision this serves

Operator, 2026-08-11: *"i want to know what is our trigger today given we haven't fully flesh out delay entries yet."* Corrected twice since: the flag stage machine (WATCH→TIGHTENING→COILED→TRIGGERED) is **not** his delayed entry, and delayed entry is a **FAMILY** — *"we wait for a follow-up setup after the EP. The horizon is open — same day, next day, or next week"* — with the 620 chart one timing tool inside it, not the definition.

The decision downstream: which of the four recorded candidate setups (if any) graduates toward a proposal, and what must settle first. Nothing here flips anything — the watch lane is a silent shadow recorder.

**What would change the answer:** if the funnel showed names dying before any rung fires (a firing problem), the fix would be rung definitions; if they fire and then die, the missing piece is selection/management. The data below says the second, emphatically.

## Method / population

- **Population:** `mi_delayed_entry_watch` + `mi_delayed_entry_trigger` in prod, complete first-run state as of the 2026-08-31 17:57–18:46 ET run: **1,269 campaigns (ticker × EP day), 871 tickers, EP days 2026-08-24 → 2026-08-31, 4,414 watch rows** (3,145 forward name-sessions walked). Enrollment population = **every** name `mi_ep_scan_log` saw (alerted or rejected) — deliberately non-outcome-conditioned (the #327 Stage-0 ruling). Era: pattern_version v2, screen_v1, settle_v2 — one era, one run, no mixing.
- Queries: read-only SELECTs via ssh → psql, captured once to `/tmp/562diag/s1_funnel.out` and `s2_followup.out`; column names taken from `information_schema` first.
- Trigger definitions read from `agents/market_intelligence/delayed_entry_shadow.py` at HEAD (deployed server checkout `1931dd7e` per live_rules; 0 drift).
- Dead strategies (`9m_day2`, `fishhook_v3`, `flag_continuation`) touch nothing here; the flag stage machine is deliberately absent from this analysis (operator correction).
- ⚠ **No outcomes are claimed anywhere in this document.** Settlement needs 20 sessions per fire; the first fire-cohort's windows close ~2026-09-23 → ~09-29. Counts of already-settled stop rows appear below as *funnel plumbing* (where names die), never as expectancy.

---

## (1) What our delayed-entry trigger is TODAY — from the code

**On live money: we have NO delayed-entry trigger.** The only live entry is MAGNA53's day-1 ORB bracket; the only live re-entry of any kind is the **same-day** day-1 retry (`order_manager.attempt_day1_reentry`, `MAX_ENTRY_ATTEMPTS = 2` at `broker/order_manager.py:977` — i.e. exactly one retry, flat for every name; fired 7 times, all paper, all early May). Nothing buys day 2+.

**In shadow: four recorded candidate setups**, live since last night in `delayed_entry_shadow.py` (17:57 ET job, `scheduler.py:5644`; SILENT — no Telegram, read by no live path). Each states a buy and a stop, so each is a **SETUP by the CLAUDE.md definition** — but a *candidate* setup being recorded, not anything we trade. Delayed entry itself remains the FAMILY hosting them.

Shared per-bar convention: within a 5-min bar the LOW is processed before the close/high ("pess", stop-first) — a same-bar undercut kills a reclaim before that bar's close can fire it (`delayed_entry_shadow.py:89-95, 347-359`). Each rung fires at most once per campaign (fired_* flags).

| rung | firing condition (gates in order) | buy | stop | cite |
|---|---|---|---|---|
| **ep_low_reclaim** | (a) some 5-min low < EP-day low (undercut seen); (b) a later 5-min bar CLOSES back above the EP-day low | that 5-min close | lowest low since the undercut | `delayed_entry_shadow.py:361-365` |
| **ep_close_reclaim** | (a) NEVER undercut the EP-day low (an undercut kills this rung permanently); (b) some 5-min low < EP-day close; (c) a later 5-min bar closes back above the EP-day close | that 5-min close | lowest low of the dip | `:366-371` |
| **ep_high_break** | (a) clean path — never undercut the EP low AND never dipped below the EP close; (b) any high ≥ EP-day high | the level (EP-day high, stop-buy) | prior session's low; unknown prior low → session abstains, retried | `:372-379` (minute), `:399-404` (daily-provable) |
| **ep_close_620_prox** | (a) band armable: EP-anchored ADR$ computable (mean range of ≤20 pre-EP sessions × EP close, `:466-477`); (b) MACD(6,20) on 5-min closes crosses above its EMA-9 signal **with MACD < 0** (`:510`, constants `:226`); (c) global bar index ≥ 12 (warm-up guard, `:231`, 2 prior sessions seed the EMAs `:232`); (d) basing — prior 8 buckets' high-low range ≤ 0.4×ADR$ (`:512-513, :228-229`); (e) hook — MACD 6-bucket min ≤ 12-bucket min (`:515, :227`); (f) proximity — cross bar's close within **0.5×ADR$** of the EP-day close (`:554, :230`); (g) fill sanity — close > stop, else the next cross is tried (`:556-558`) | the cross bar's 5-min close | low of day so far (the operator's TEAM stop basis) | `:533-565` |

- **Rung 4 carries a mandatory placeholder label** `near_definition='proximity_band_0p5adr_v1'` (`:222-225`, schema-CHECK-enforced): the ±0.5×ADR band is the *rigid instrument* the operator's 08-29 behavioural "near" ruling replaces. A rung-4 null result falsifies **the band only**, never the behavioural idea — which remains unimplemented anywhere.
- **Risk definition:** every trigger row records entry, stop, and **stop width as % of entry first-class** (`:423-431, :56-59`); R = entry − stop.
- **Re-entry recording** (`:61-87, :1454-1521`): after a first attempt settles as a stop, two bounded shapes replay from the *next* session — `same_pattern` (the rung re-armed fresh) and `new_high_break` (break above MAX(EP high, every high through the stop-out); stop = prior session's low) — at most one row each. Same-day re-entry is out of scope by construction (`:85-87`), so every re-entry figure understates it.
- **The abstain rule** (`:96-106, :1041-1070`): a minute-resolution check whose bars are missing marks the session `eval_status='unscoreable'` (reasons: `missing_daily_bar`, `missing_minute_bars`, `missing_prior_low`) and the walker RE-WALKS from the first unscoreable session every run — never a daily-bar fallback for a minute tactic, never a fabricated fill. Settlement never leaps a bar gap (`:713-714`); a row still blocked 45 calendar days after its fire closes as `outcome='unscoreable'` with every R column NULL (`:200-201, :1264-1269`); degenerate geometry (stop ≥ entry) closes unscoreable immediately (`:1207-1210`).

## (2) Where watched names actually die — the funnel from prod

Distinct campaigns (ticker × EP day) and sessions, not rows. "Walked" = the 1,018 campaigns with ≥1 forward session (EP days 08-24..08-28); the 08-31 cohort (251) enrolled last night with zero sessions walked yet.

| stage | n | plain words |
|---|---|---|
| names the EP scan saw, 08-24..08-31 | 1,269 | every one of them |
| **enrolled** | **1,269 (100%)** | recall is perfect — no name the scan saw is missing from the lane |
| campaigns walked ≥1 session | 1,018 | the 08-31 cohort's walk starts tonight |
| sessions walked cleanly | 4,382 of 4,414 rows (99.3%) | only 31 sessions lacked a daily bar + 1 lacked minute bars; 22 campaigns touched — data gaps are near-zero |
| path ever dipped below the EP-day close | 954 of 1,018 (94%) | almost every gap name gives back its EP close within a week |
| path ever undercut the EP-day low | 697 (68%) | two-thirds breach the invalidation line itself |
| path ever exceeded the EP-day high | 454 (45%) | — |
| **fired ≥1 rung** | **925 of 1,018 (91%)** | the rungs fire on almost everything, median fire = session 1 |
| fired ≥2 rungs | 598 (59%) | 395 fired two, 189 three, 14 all four |
| never fired anything | 93 (9%) | even the oldest cohort (5 sessions walked) is 93% fired |
| first-attempt trigger rows | 1,740 | + 693 re-entry rows = 2,433 total |
| — of which already settled as a STOP | **1,292 (74%)** | died at the stop inside the same week; the rest (447) are still open |
| — median time fire → stop, pullback rungs | **0 calendar days** | 262/437 (620), 262/368 (close-reclaim), 297/427 (low-reclaim) stopped the SAME DAY they fired |
| settlement pending | 447 first + 693 re-entry rows open | 20-session windows close ~09-23 → ~09-29 |

Per-rung first fires (each row = distinct campaigns by construction — the unique index is one row per campaign × rung × shape): **ep_low_reclaim 580 · ep_close_620_prox 548 · ep_close_reclaim 469 · ep_high_break 143.** Median stop widths: low-reclaim 2.49%, 620-prox 2.26%, close-reclaim 2.86%, high-break 6.95% of entry. Fire timing is front-loaded: 376/580, 416/548, 421/469, 137/143 fire on session 1.

Context cuts: the six HIGH-alerted campaigns in the window all fired ≥1 rung (n=6 — no conclusion). The 620 band is armable on essentially every walked name (the 252 NULL-ADR rows are last night's not-yet-walked enrollment rows plus EMIS 08-25, which has no daily bar anywhere and sits abstaining as designed).

**One real defect found:** the ex-ante `screen_member` stamp is NULL on **1,267 of 1,269 campaigns**. Driver: `extension_pct` NULL on 1,262 and `catalyst_grade`/`ep_score` NULL on 1,252 — the scan log only carries those for names that reached the graded shortlist (~top 20/day), so the screen the lane was built to read p* against can never populate for ~99% of its own population as wired. Extension is recomputable ex-ante from `mi_daily_closes` at $0; the grade half is structurally absent for ungraded names.

## (3) The binding constraint — a MISSING RULE, not a threshold and not a data gap

- **"Cannot fire" is empty.** Enrollment recall 100%; bar gaps 0.7% of sessions; the 620 band arms on ~every walked name. Nothing structural blocks firing.
- **"Fires rarely" is false — it inverts the old finding.** The #p74 "1 of 104 reached TRIGGERED" number belonged to the flag stage machine the operator ruled out; the actual delayed-entry rungs fire on **91% of watched names within ≤5 sessions**, 59% on two or more rungs at once.
- **So names now die AT THE STOP, immediately:** 74% of first fires already settled as stop-outs; the median pullback-rung stop-out is the same day as the fire, at a median stop 2.3–2.9% of entry. This is the same "the triggers find the turns — the stops die first" mechanism the 08-22 study (`delayed_entry_562_2026-08-22.md`) measured on 44 stopped-out episodes, now visible on a 1,018-campaign non-outcome-conditioned lane — **as a mechanism, not yet as expectancy** (the survivors are exactly the rows still open).
- **What is missing is a rule, in two places:**
  1. **Selection** — nothing decides WHICH of ~350 fires/day to take. The operator's own spec is confidence-scaled ("if super confident of real-EP we may even have multiple retries"), and the campaign study's P13 finding stands: composites need ~8–18% of fires to be real tails vs a ~2.3% base rate. No ex-ante confidence input exists on the trigger rows today beyond the raw EP-day facts.
  2. **The selection instrument the lane shipped with is dark** — the screen stamp (above). Until it populates, the planned "p on the screen-comparable subpopulation" read is impossible.
  3. (Ruled, not missed:) the behavioural "near" is a placeholder band by design; a rung-4 result speaks only to the band.
- **What one night cannot support:** any real-tail rate p, any rung ranking, any expectancy. **What settles it and when:** first fires 08-25..08-31 settle as their 20-session windows close, **~2026-09-23 → ~09-29**. ⚠ The accrual gate (`delayed_entry_shadow_first_read`, 30 settled triggers) is numerically already tripped by 1,292 settled rows — but reading p from settled-only rows now would count only losers (the open rows are the candidate winners). **The honest first read is dated ~09-23, not on the settled count.**

## (4) Options — the fork

This is detection-criterion territory: any threshold move = CHANGE_PROCESS + operator sign-off. Nothing is proposed as a change here; the lane keeps recording either way.

- **(a) Wait for settlement (~09-23)** and answer p + rung ranking on the first non-outcome-conditioned cohort before touching anything.
- **(b) Fix the dark screen stamp now** (shadow-telemetry repair, $0): recompute `extension_pct` ex-ante from `mi_daily_closes` in the enrollment path so `screen_member` can populate; the grade half needs its own operator call (drop grade from screen_v1's definition, or pay to grade lane names).
- **(c) Start the selection-layer design now** (the confidence→take/retry mapping his 08-22 framing asks for) so a proposal is ready when settlement lands.

**One-line recommendation: (b) now — it is a $0 shadow-lane telemetry repair with no criteria change, and without it the settlement read arrives crippled — with (a) as the gate on every outcome claim; (c) in parallel on paper only.**

## What this does not answer

- **Whether any rung has positive expectancy, what p (the real-tail rate) is, or how the rungs rank** — zero outcome claims here; windows close ~09-23 → ~09-29 and the settled-so-far subset is loser-biased by construction.
- **Same-day re-entry** — structurally out of the lane's scope (tick-level state); every re-entry figure understates it, and it is the operator's own TEAM move.
- **The behavioural "near"** — unimplemented anywhere; rung 4 tests only the ±0.5×ADR placeholder band.
- **Whether one week of August gap names generalizes** — one era, one market week, 6 HIGH alerts; the lane needs its month.
- **Confluence (the MNTS two-fold shape)** — still never measured as its own arm (context-ledger open question 3).

## ⚖ THE LINE

Entry discipline, stops, re-entry counts and any threshold are the operator's sole authority. This document changed nothing: no code, no config, no thresholds; all prod access was read-only SELECTs. The watch lane remains a silent shadow observer read by no live path.

---
*Working files: `/tmp/562diag/` (schema pass + two captured query runs). Related: PLAN #562, #327; `docs/setups/delayed_ep_reentry.md § THE CONTEXT LEDGER`.*
