# ADR 0031 — Pivot structure-stops: per-stock-character stop placement (design + shadow)

**Status:** DESIGNED (Fable, 2026-07-11 eve — Block 3 T3, pulled forward from Sunday).
**Requirements SSoT:** `docs/methodology/pivots-and-stock-character.md` (operator, 6/11).
**Nothing here changes live behavior.** The deliverable is a SHADOW that measures two candidate
stop semantics against the live baseline; every flip is gated in §6.

**⛔ SEQUENCING GATE (hard, from the task line + premortem evidence-hygiene rule):** the shadow
MAY coexist with the giveback shadow (both are log-only counterfactuals on closed trades; they
do not interact). **Any LIVE flip queues STRICTLY BEHIND the giveback F1 resolution (8/06
review): never two concurrent live stop changes** — the pivot-stop live fork may not even be
*brought to a sitting* until giveback F1 is adopted-or-killed, or attribution is unrecoverable.

---

## 1. What changes conceptually

Live management today trails a GLOBAL rule: close below the active SMA (10→20 handoff) → exit.
The methodology says the right reference is the **stock's own respected pivot** — some names
live on the 10MA, some on the 20 with habitual undercuts, some on swing structure. One global
MA erases exactly the information that matters (the doc's anti-pattern #1).

**v1 scope = the COMPUTABLE tier only** (MAs + swing lows from daily bars). The structural tier
(volume shelves, congestion) is explicitly deferred to chart-vision (#267) — do not build it here.

## 2. The character profile (deterministic, no LLM)

Computed per ticker from daily bars over the **trend window** = min(since the trend anchor, 120
trading days). *Freshness rule (methodology anti-pattern #3): a close ≥ +50% above the prior
90d max close re-anchors the window at that event's day (an MNTS-class re-rating resets
character).*

**Pullback-episode detection** (per MA in {SMA10, EMA21, SMA20, SMA50}):
- An episode **BEGINS** the first day `low ≤ MA × 1.02` after ≥5 consecutive closes above the MA.
- It **ENDS**: (a) close ≥ the pre-episode 20d swing high → **RESPECTED**; (b) 3 consecutive
  closes below the MA → **BROKEN**; (c) 20 trading days elapse → BROKEN (stale).
- **Undercut depth** of an episode = `max((MA_t − low_t)/MA_t, 0)` over the episode.

**Profile** (per ticker): for each MA, `respect_rate = respected/(respected+broken)` over ≥3
episodes; **home_MA** = the SHORTEST MA with respect_rate ≥ 2/3; **undercut_p80** = 80th-pctile
undercut depth across the home MA's respected episodes; median pullback duration; n_episodes.
**ABSTAIN (first-class outcome):** <3 episodes on every MA, or no MA clears 2/3 → no profile →
pivot logic abstains and the name stays on the current global trail. Abstention rate is itself a
readout (micro-caps with short history may mostly abstain — that is GO/NO-GO evidence, not a bug).
All numeric parameters above are **v1 defaults** (tunable only by shadow evidence, not re-litigated
per name — the profile varies per stock; the *detector* stays fixed).

**Storage (altitude):** v1 computes the profile in-job and snapshots it INTO the shadow row
(auditable, replayable). A standalone `mi_ticker_character` table is deferred until a second
consumer exists (#267 prompts / #255 memory are the named candidates) — don't build shared infra
for one consumer.

## 3. The two candidate stop semantics (measure BOTH; don't pre-decide)

Both apply only in the trail stage (post-partial/breakeven — the ladder stages before that are
untouched; `exit_logic.apply_daily_exit_step` already validates `trail_mode`, and each arm is a
new mode behind that guard):

- **Arm P1 — swing-pivot trail:** stop = the most recent **confirmed** swing low (fractal low,
  `low[i] < low[i±1..2]`, confirmed 2 bars later — the stop moves on the CONFIRMATION date, no
  lookahead). Ratchets up only; never widens below the current stop.
- **Arm P2 — character-MA trail:** exit on close below `home_MA × (1 − undercut_p80)` — the MA
  this name actually respects, with THIS name's own undercut tolerance (so an NBIS-class
  habitual undercutter isn't shaken out by its normal behavior).
- **Baseline:** the live global SMA trail (what actually happened).

## 4. The shadow (the build) — giveback_shadow is the template, deliberately

`agents/market_intelligence/pivot_stop_shadow.py` + table `mi_pivot_stop_shadow` (seeded in
`db.initialize_schema`): nightly intelligence-side job (rides the same slot as the giveback
job), reads CLOSED trades not yet shadowed (`NOT EXISTS` dedup, the giveback idiom), replays
daily bars, computes per-arm counterfactual exits.

Row: `trade_id` (PK/FK) · ticker · baseline_exit_r · p1_exit_r/p1_exit_date · p2_exit_r/
p2_exit_date · mfe_r · capture_pct per arm · `profile jsonb` (the snapshot: home_ma,
undercut_p80, n_episodes, respect_rates, window_anchor) · `abstained bool` + reason. **Per-arm
columns, never blended** (ADR 0013 discipline). Telegram: nothing; audit row per run. **Gated
review** `pivot_stop_shadow_review` wired in the same commit as the job (predicate: ≥10 settled
non-abstained rows; earliest +21d) — the can't-silently-0-row rule (#173 class).

**Interaction with the giveback shadow: none by construction** — both are read-only
counterfactuals over closed trades writing disjoint tables. (If BOTH later go live, the live
stop composes as `max(arm_stop, giveback_floor)` — one precedence rule, stated here so the T4
cross-ADR sweep and ADR 0029's stop-ownership design inherit it rather than re-deriving it.)

## 5. What the readout decides (the eventual sitting's table)

Per arm vs baseline on the same closed-trade cohort: mean/median exit R · MFE capture% · % of
trades where the arm exited EARLIER than baseline on a trade that kept running (the tail-clip
rate — **the dossier's poison test**: any arm that clips the +5R tail loses regardless of its
mean) · abstention rate. Ship-shaped question: "does character-conditioned placement beat the
global trail WITHOUT clipping the tail, at N≥10?"

## 6. Gates (all hard)

1. Shadow → build now (no-money, log-only; the safe-subset rule).
2. **Any live flip:** giveback F1 RESOLVED first (§0 gate) + N≥10 non-abstained shadow rows +
   the §5 tail-clip test passed + CHANGE_PROCESS + SSoT (`docs/setups/` management section) +
   operator sign-off. Also sequenced vs ADR 0029 D1 (stop-ownership) — pivots change WHAT level
   is proposed; 0029 owns WHO moves stops; land 0029-D1 first or explicitly compose.
3. Character-profile consumers beyond management (entry references, #267 prompts) are OUT of
   scope here — each needs its own evidence gate.

## 7. Cards (Opus/Sonnet; ~1 day total)

- **C1 — character profiler** (pure fn, `character_profile(bars) → profile|None`): episode
  detector + respect rates + home-MA + undercut_p80 + the re-rating re-anchor. Tests on
  synthetic bar fixtures (a 10MA-respecter, a 20MA-undercutter, a too-short abstainer, a
  re-rating reset).
- **C2 — pivot detectors** (pure): confirmed fractal swing lows (+ the ratchet); the P2 line
  computation. Tests: confirmation timing (no lookahead), ratchet-never-widens.
- **C3 — shadow job + table + gated review** (giveback_shadow as the literal template): job,
  schema seed, dedup, audit row, `pivot_stop_shadow_review` wiring. Test: end-to-end on a fake
  pool + no-mutation pin.
- **C4 — readout formatter** (the §5 table; rides C3's review surfacing).
- Sequencing: C1 → C2 → C3 (C4 rides). Deploy = market-agent scope only.

## 8. Operator forks

- **F1 — sign the two arms + abstention-as-first-class.** *(Rec: sign — the arms are the two
  computable-tier readings of the methodology doc; the shadow decides between them with R.)*
- **F2 — v1 detector defaults** (episode/confirmation/thresholds in §2–3). *(Rec: sign as
  defaults; they are detector plumbing, not strategy — evidence tunes them.)*
- **F3 — the sequencing gate** as worded in §0/§6. *(Rec: sign hard — the premortem's
  attribution-hygiene rule is the reason; two concurrent live stop changes make the giveback
  evidence unreadable.)*
