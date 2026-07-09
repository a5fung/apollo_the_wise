# Session HANDOFF — cross-machine bootstrap

**Written 2026-07-07 (desktop). The operator is moving to a LAPTOP for ~1 week and will start
fresh Claude Code sessions there.** This file is IN THE REPO (git-synced), so a laptop session
gets it on `git pull`. It exists because the machine-local context does NOT transfer (see §1).

---

## 1. THE transition fact — what does and does NOT cross machines

| Surface | Location | Crosses to laptop? |
|---|---|---|
| **CLAUDE.md** (rules, protocol, THE LINE, schedules, architecture) | repo root | ✅ via `git pull` |
| **PLAN.md** (every task: project · ETA · status · detail — the SoT) | repo root | ✅ via `git pull` |
| **docs/decisions/** (ADRs 0011–0024, all signed) · **docs/roadmap/** | repo | ✅ via `git pull` |
| **This file (docs/HANDOFF.md)** — the in-flight "where we are" | repo | ✅ via `git pull` |
| **The pickup + MEMORY.md + ~40 feedback/project memories** | `~/.claude/projects/.../memory/` | ❌ **machine-local — NOT on the laptop** |

**So on the laptop, the load-bearing rules (CLAUDE.md) and all tasks (PLAN.md) and all design
(ADRs) ARE present. What's missing is the accumulated memory files.** §4 backstops the most
load-bearing of those; the rest is nuance the signed ADRs + PLAN.md task detail already carry.

## 2. Laptop OPEN ritual (do this first, every session)
1. `git pull origin main`
2. `python scripts/operator_now.py` (you're **PDT**; harness clock is UTC — never trust it for dates)
3. `python scripts/check_plan.py --today` → the day's plan (this reads PLAN.md, the SoT — works fine on the laptop)
4. **Read THIS file (§3) for in-flight context** (it replaces the machine-local pickup you won't have)
5. State the day's plan before reacting.

CLOSE ritual is unchanged (reconcile PLAN.md → `check_plan.py` must pass → commit+push). Your
laptop sessions build their OWN local memory as you go; PLAN.md (synced) stays the source of truth,
so when the operator returns to the desktop, `check_plan --today` off PLAN.md gives the true state
(the desktop's week-old pickup self-heals via PLAN.md).

## 3. WHERE WE ARE (in-flight, as of 2026-07-09 Wed eve)

**Apollo trades REAL money (MAGNA53 live since 6/30). A machine switch changes nothing on the
Hetzner prod box.** Prod healthy 7/9 (both money containers + orchestrator up post-deploy;
`dual_account_boot_verified`).

**Design debt is ZERO** — ADRs 0011–0024 all operator-signed. Pure execution from here (Fable
designs, Opus/Sonnet execute).

**v1.0 glide path**: declaration projected ~7/14, HARD walk 7/21 (#425). M1 judge-composition
sitting **7/18 (#335)** — an operator gate.

**Shipped 7/8–7/9 (laptop days):**
- 7/8: ADR 0023 Cards 1/2/3 (`giveback_floor` + harvest sweep, **+$8,075** F1-evidence, dark) + Card 5
  gap alert; ADR 0024 M1-a `compose_final_tier` (dark) + M1-c draft; #443 alert fix committed.
- 7/9: **ADR 0023 F1 giveback SHADOW DEPLOYED** to both money containers + mechanism-verified (log-only,
  THE LINE held); **#443 alert fix LIVE** on the entry path; **#439 part-b** (paper harness leaves zero
  resting test orders); advisor + /simplify; **#290 CLOSED** (late-entry backtest: don't extend the ORB
  window — the wide window is R-NEGATIVE, no robust edge). Deploy-tooling: a `deploy.sh` drift-guard
  classification fix (`data_gated_reviews.yaml` is market-agent-only, not full 3-svc scope).

**Open verify-lives (fire on their own — CONFIRM AT OPEN):**
- **#306** giveback shadow: first `mi_giveback_shadow` row on the next LIVE round-tripper close (17:38 job).
- **#437** restore-check schema-init: tonight's 03:30 UTC cron writes `backup_restore_check_ok` with the step.
- **#443**: next EP HIGH labels LIVE + the 16:45 digest shows live-primary (market-gated).
- **#439**: next deploy's G6 leaves zero `apollo_paper_integration_test_*` orders + a test-COID reads INFO.
- **#287**: `jsonb_typeof='array'` on the next real exit (market-gated; no exit since 7/7).

**Next up (PLAN.md is SoT — run `check_plan.py --today`)**: #435 /simplify infra follow-ups (7/10) ·
#436 phantom prevention · #433 naked-stop messaging-verify · #425 v1.0 declaration walk (~7/14–7/21) ·
M1 sitting 7/18. **Operator-gated**: #420 (uptime pinger — create the account) · #423 (secrets runbook —
read it) · #353 (consolidation→paper, #327-edge-gated) · #434 (MEMORY.md compact — desktop-only) ·
#446 (cancelled_unfilled 36.7% — low-pri, drop if not worth it).

## 4. Critical operating rules the laptop won't have in memory (backstop — most are also in CLAUDE.md)

- **THE LINE** (CLAUDE.md, absolute): NEVER on your own authority change/disable any strategy, sell/entry
  discipline, sizing, target, safeguard, or anything touching real money / live trade state. In doubt: STOP + ask.
- **Deploys need EXPLICIT operator authorization each time.** Not standing.
- **`deploy.sh both` does NOT recreate `apollo-execution`** — broker/ (order_manager, trade_stream,
  live_tracker, alpaca_client) needs a SECOND `deploy.sh execution`. Verify `docker ps` shows
  apollo-execution "Up <seconds>" after. (The scope guard warns, but confirm.)
- **No `docker exec python -c` for trade-state MUTATION.** Read-only SELECTs are fine. Mutations go through
  a COMMITTED, reviewed, DRY-RUN-first script (see scripts/reap_stale_pending_confirmation.py and
  scripts/fix_double_encoded_exits_287.py as the pattern) — never inline.
- **Max 1 rebump; UNBLOCK+SHIP, not re-date** (CLAUDE.md). A due task → work it, don't roll the date.
- **Never invent a `/command`** — grep `channels/telegram.py` first; a command needs handler + dispatch +
  BotCommand registration in the same commit or it's invisible.
- **Established setups (EP/9M/HTF) → use the PRIMARY methodology definition**; don't invent variants.
- **Timezones**: operator = PDT · harness "today" = UTC (never use for operator dates) · market code = ET.
- **Concise** — no essays; a decision = the fork + a 1-line rec. Never mention session length / ending.
- **`advisor` is Opus-only** — works on Opus 4.8 (the default), fails on Fable-5 as main model.
- **Model split** (operator): Fable = design/review to execution depth · Sonnet = card execution · Opus =
  main-loop verify/deploy/review. Fable is spent for this week.
- **jsonb double-encode class**: the pool codec auto-`json.dumps` every jsonb param — NEVER pre-`json.dumps`
  a jsonb value (double-encodes to a string). Pass the plain object; keep the `::jsonb` cast. (#177/#287/#412.)

---
*Keep this file's §3 roughly current if you do a long stint on the laptop; but PLAN.md is always the
authoritative task state. When the operator is back on the desktop, the machine-local memory resumes.*
