# Evaluation — Alpaca Skills Library (backtesting skill) for Apollo dev research

**Task:** #350 · **Date:** 2026-06-20 · **Upstream:** `github.com/alpacahq/alpaca-skills` @ `8b2d86b`
(2026-06-17), **Apache-2.0** · **Status: PROVISIONAL adopt — pending a first real CLI run.**
(An unrun skill is the dev-tooling equivalent of "deployed but not confirmed" — same VERIFIED-LIVE
discipline we apply to everything else.)

## What it is
Open-source `SKILL.md` workflows for AI coding agents (Claude Code / Cursor / Codex). The one
shipped skill, `alpaca-trading-backtest`, drives a disciplined backtest: idea → formalized rules →
confirmed assumptions → **Alpaca CLI** data fetch → a single readable `run.py` → structured
artifacts → report. The value isn't a new engine — it's the **reproducibility discipline** baked in.

## The call — provisionally ADOPT for price/execution research; NOT for signal-dependent studies

| Study type | Fit | Why |
|---|---|---|
| Entry/execution mechanics — ORB geometry, 5-min OR, skip-wide-open (the **W2 class**) | ✅ | pure price/bar logic; the skill's guardrails are exactly the W2-artifact protection |
| SIP-vs-IEX cohort reconstruction (#180/#182, the paper-IEX selection-bias gate) | ✅ | the CLI fetches **SIP** bars directly → reconstruct cohorts off-DB |
| Single-symbol / universe price backtests | ✅ | self-contained |
| Selection replay — judge promote/demote (#268) | ❌ | needs our decision rows |
| RS / EP / theme signal-dependent backtests | ❌ | derived signals live ONLY in our DB; the CLI can't reconstruct them |

## Key finding — the data path (answers #350's KEY QUESTION)
History comes via **Alpaca CLI → Alpaca Market-Data API**, *not* our Postgres. So **price-based
backtests can run without the Hetzner DB** — relaxing `memory feedback_backtest_server` for that
class (local has no DB data). Caveat: "without DB" holds only for studies that don't need our
*derived* signals (see ❌ rows). **Unverified until a first CLI run** (Remaining, below).

## Prerequisite — the binding constraint (OPERATOR step, can't be done agent-side)
The skill is **inert without the Alpaca CLI**:
- Install: `go install github.com/alpacahq/cli/cmd/alpaca@latest` (Windows → needs Go on PATH,
  commonly `~/go/bin`; the `brew install alpacahq/tap/cli` path is macOS/Linux only).
- Auth: **paper** creds via `alpaca profile login` (interactive) or `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`
  env; confirm with `alpaca doctor` green.
Until this is done the skill can't be exercised → adoption stays **provisional**.

## Off-limits
- The optional **paper forward-validation handoff** generates an `alpaca_order_adapter.py` that
  **submits paper orders**. Do **not** use the order-submission half — it collides with the hard
  no-trade-state-mutation rule (`feedback_no_docker_exec_for_trade_state`). Historical-backtest half only.
- **Do not vendor the skill into the repo yet.** Vendor-vs-global is a decision for *after* a working
  run earns it a place; vendoring now installs markdown we can't exercise + an Apache NOTICE obligation.

## Reusable discipline to fold into our studies NOW (no CLI needed — the portable prize)
Adopt this regardless of whether the CLI ever gets set up. Distilled from the SKILL.md guardrails +
our own W2 +49%-artifact lesson:
1. **Data fingerprint** every run (symbol · feed · adjustment · timeframe · range · calendar) — reuse
   cached data ONLY when the fingerprint matches; different fingerprint = different input data.
2. **Separate signal timing from fill timing** — signal on bar-T close, fill on T+1 open
   (`next_open` default); never same-bar without a documented model + a look-ahead warning.
3. **Keep the generated run code** — never discard it; an un-auditable result is not a result.
4. **Run-considerations checklist before running**: look-ahead bias · survivorship · **outlier-
   concentration / overfitting on repeated variants** (the W2 +49% artifact — decompose winners) ·
   out-of-sample / walk-forward for any parameter tuning.
5. **Verify the filter OPERATED across the cohort** (our W2 lesson = the skill's "don't pretend vague
   rules were specified"; put every assumption in `notes.md`).
6. **Sample stddev (N-1) for Sharpe**; keep daily-vs-per-bar return basis consistent with the report.
7. **Structured artifacts**: assumptions in `notes.md`, machine-readable `summary.json`, a `report.md`
   that leads with strategy-vs-benchmark.

## Remaining (the verify step → flips PROVISIONAL to ADOPTED)
Operator installs the Alpaca CLI + paper creds → run ONE real backtest (a W2-class price study is the
natural first target) → confirm it runs off Alpaca data with no Hetzner DB → then flip the status and
decide vendor (`.claude/skills/`) vs global (`~/.claude/skills/`).
