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

## 3. WHERE WE ARE (in-flight, as of 2026-07-07 Tue eve)

**Apollo trades REAL money (MAGNA53 live since 6/30). The system runs autonomously — a machine
switch changes nothing on the Hetzner prod box.** Prod verified healthy 7/7 eve (all containers up,
0 job failures/24h).

**Design debt is ZERO** — ADRs 0011–0024 all operator-signed. Everything from here is pure execution
(Fable designed, Opus/Sonnet execute). Fable is exhausted for the week.

**v1.0 glide path**: FL-1 5/10 · FL-3 1/7 · FL-8 4/4✓ · blocking 17 · **declaration projected ~7/14,
HARD walk 7/21 (#425)**. The M1 judge-composition sitting is **7/18 (#335)** — an operator gate.

**The execution queue (from the signed ADRs + PLAN.md):**
- **Wed 7/8**: the tomorrow-AM verify-lives of Tue's deploy (all fire on their own — confirm at OPEN):
  #183 check_fills clean/no false-naked · #287 `jsonb_typeof='array'` on the next new exit (→ then #287
  closes) · #440 theme ping only-on-new · #405-P2 suppress-audit on next direct-source HIGH · #441 FL-3
  counts 7/7 as clean (deploy blip excluded). THEN: **ADR 0023 cards** C1 peak-lock hook (dark) / C2
  harvest-sweep harness+run / C5 9:00 gap alert → sweep doc; **ADR 0024 M1 prep** M1-a compose_final_tier
  (dark) / M1-b the ONE batched regrade / M1-c rubric-amendment draft.
- **Fri 7/10**: 0023 card 6 (entry no-trigger backtest) + #184b broker-order ingest build.
- **Sun 7/12**: FL-3/FL-8 clocks complete · #412 write-path verify · weekly review.
- **7/18**: the M1 sitting (operator). **~7/14–7/21**: the #425 v1.0 declaration walk (operator).

**Carry items**: #405 Part-1 (has_direct_source cache-tuple) · #436 (phantom-creation prevention) ·
#261 ops/evals reorg (7/13) · #442 (FL-3 watchdog-regex hardening, 7/31) · the recurring
harvest_rule_effectiveness review (post-0023-flip, in data_gated_reviews.yaml).

**Tuesday 7/7 shipped**: 2 money-path fixes deployed+verified (#183 enum boundary, #287 jsonb
double-encode incl. a 40-row data cleanup) · #405 verified-live + #317 closed · #440/#441 deployed
(FL-3 1/7 live) · advisor + /simplify clean · #418 v1.0 finish line SIGNED · #303 closed · ADRs 0023 +
0024 written + signed.

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
