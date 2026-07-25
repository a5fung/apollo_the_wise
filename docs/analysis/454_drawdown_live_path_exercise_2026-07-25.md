# #454 part 3 — drawdown-breaker LIVE-path exercise (2026-07-25)

**Result: ALL 37 CHECKS PASSED. Zero writes, zero residue.**
Harness: `scripts/_454_drawdown_live_path_exercise.py` · run in `apollo-execution` (the container that
owns the money path).

## What this closes — and what it does not

The tiered drawdown breaker is the −12% backstop that every accepted risk in the v1.0 premortem leans
on, and it **has only ever fired on paper**. The gap #454 part 3 names is real but narrower than it
sounds, and the distinction matters:

| | status |
|---|---|
| live *snapshot + compute* half | **already exercised** — runs daily; `mi_safeguard_state` carries a live row (`OK`, −3.297%, peak 2026-07-03), `last_evaluation_at` refreshed by the 16:12 ET cron |
| live *enforcement* half — a non-OK tier reaching `_check_safeguards` and the sizing site | **never executed** ← what this closes |
| a genuine live **fire** | **still event-gated** on a real −12% drawdown. An exercise cannot manufacture this. |

So: this closes *never-executed*, not *never-fired*. Do not let the task read as having proven the
backstop under real conditions.

## Precondition checked first

`DRAWDOWN_BREAKER_PHASE == 'active'` in **both** running containers (`apollo-execution` and
`apollo-market`), read from the containers rather than from the doc — `safeguards.md` line 97 carries
an unresolved "PROMOTION TIMING DISPUTED" note, so the doc alone couldn't settle whether the
enforcement block is live. It is. Had it been inert, the whole exercise would have proved nothing about
production, and that would have been the larger finding.

## Design: in-process injection, no state mutation

The obvious approach — set the live `mi_safeguard_state` row to each tier, then restore — was
**rejected**, and the reason is specific rather than general caution:

- **REDUCE returns `ok=True` with a 0.5× multiplier** (`live_tracker.py:278`). A crash after setting
  REDUCE leaves Monday's live entries **silently half-sized**. Nothing alerts, and the 16:12 ET cron
  does not recompute until *after* the 9:31 entry window. That is a silent strategy alteration on the
  money path — precisely what THE LINE covers. BLOCK would have been loud and fail-safe; REDUCE is not.
- **Synthetic equity snapshots** were rejected outright rather than made safer: a stray high-equity row
  in `mi_account_equity_snapshots` raises the 30-day rolling peak and mis-computes every subsequent
  drawdown → a **false BLOCK days later** with no obvious cause. A delayed money-path failure is worse
  than an immediate one.

Instead the harness patches `read_breaker_state` **in-process** for the duration of each call. Residue
is impossible by construction — the process exits. Everything else stays real: real Alpaca auth, real
position count, real daily-loss query, real `_check_safeguards`, real `'live'` argument. The breaker
gate is **last** in `_check_safeguards`, so reaching it means every prior gate genuinely passed.

The one thing in-process injection cannot prove is that `recompute_drawdown_state('live')` can *write*
a non-OK value to the live row. Verified by reading instead: `mode` is a pure bound parameter (`$2`) in
both the SELECT and the UPDATE (`drawdown_breaker.py:309-386`) and is passed straight through to
`claim_safeguard_state_transition` — there is no mode branch anywhere in the persist path. The live
write is structurally identical to the paper write, which has fired.

## Coverage

| section | what it exercises | checks |
|---|---|---|
| [0] | `DRAWDOWN_BREAKER_PHASE` active in the running container | 1 |
| [A] | `_next_state` transition matrix — trip-side jumps, per-tier release bands, hysteresis dead zones, one-tier-per-evaluation release, legacy `TRIPPED` migration | 16 |
| [B] | `get_tier_multiplier` for all four tiers | 4 |
| [C] | **the never-executed branch** — real `_check_safeguards(account_mode='live')` at each tier | 6 |
| [D] | `_apply_composite_multiplier` — the link from "reports REDUCE" to "position is smaller", incl. per-strategy compounding and the RED-3 clamp | 5 |
| [E] | `intraday_drawdown`, the second consumer of `read_breaker_state` | 5 |
| [F] | residue — live breaker state unchanged | 1 |

### [C] verbatim — the deliverable

```
OK     -> ok=True  reason=None  mult=1.0
WATCH  -> ok=True  reason=None  mult=1.0
REDUCE -> ok=True  reason=None  mult=0.5
BLOCK  -> ok=False reason='block:drawdown_breaker: BLOCK (mode=live, see mi_safeguard_state)' mult=0.0
```

All four tiers behave per `docs/setups/safeguards.md`. BLOCK hard-blocks and carries the
`block:drawdown_breaker` skip-reason, so a real BLOCK would surface to the operator through the normal
`humanize()` path rather than failing silently.

## Three harness expectations were wrong; the code was right

Worth recording, because the corrections are the substance of the verification:

1. **`BLOCK @ −8%` holds BLOCK** (I expected REDUCE). The release threshold is the level equity must
   **recover to**, not a depth it falls past: −8% has not yet reached −7%. Same error on
   `REDUCE @ −5%`. Corrected against `_next_state:118-132`, and the release-boundary cases I had meant
   to write were added (`BLOCK @ −6% → REDUCE`, `REDUCE @ −3% → WATCH`).
2. **`_deepest_crossed_tier(−12%)` returns REDUCE, not BLOCK** — deliberate, and documented in its own
   docstring: the intraday alerter's Stage-1 vocabulary is WATCH/REDUCE only, with the raw dd% carried
   in the alert body. It is an *alerting* tier, not the *enforcement* tier. The asymmetry against
   `_next_state` (which does reach BLOCK) is by design, not drift.

No code defect was found. The exercise's value was forcing every branch to be read and justified
against the SSoT rather than assumed.

## Residue

`mi_safeguard_state` after the run — `updated_at` still shows the 16:12 ET cron write, i.e. the
exercise wrote nothing:

```
drawdown_breaker | live  | OK | -0.03297 | 2026-07-24 20:12:00.099133+00
drawdown_breaker | paper | OK | -0.00713 | 2026-07-24 20:12:00.065920+00
```

## Residual gaps (not closed here)

- A **genuine live fire** remains event-gated on a real −12% drawdown. Unfalsifiable until it happens.
- **Manual deposits/withdrawals** are still undetected (`safeguards.md` line 87) — a withdrawal reads
  as a drawdown and could trip the breaker for a non-market reason. Pre-existing, out of scope here.
- The `safeguards.md` line-97 **promotion-timing dispute** is still unresolved in the doc. The
  container says `active`, so production behaviour is settled; only the doc is ambiguous.
