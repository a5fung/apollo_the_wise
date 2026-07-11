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

## 3. WHERE WE ARE (in-flight, as of 2026-07-11 Sat eve — THE FABLE WEEKEND)

**Apollo trades REAL money (MAGNA53 live since 6/30; equity ~$4.9k; live record N=3 / −$71 —
below noise, the drift line #454 will make the next 15 trades diagnostic).** Prod healthy.

**The weekend produced (all committed, check_plan green):**
- **Block 1 (Fable designs):** ADRs **0025** (theme fragmentation) · **0026** (consolidation
  unification: flag→Confirm entry + COILED-prereq drop + WATCH_UR) · **0027** (Family-B gap
  lifecycle — the #326 9/15 evidence source) · **0028** (setup-class salience profiles) ·
  **0029** (entry-bracket: stop-ownership + gap-through fork) + design docs #170/#357/#394 +
  Tier-2 sketches (#333/#301). ALL flips await operator forks — nothing behavioral shipped.
- **Block 2:** **#450 pre-mortem** (top risk = the correlated book, R1 → #452 family-slot cap;
  also #454 calibration-honesty, #455 intraday drawdown alert, #456 residuals; the draft PDT
  risk was WITHDRAWN on verification — FINRA retired the rule itself) + **#451 edge dossier**
  (selection creates the R, entry is done, management leaks — peak-lock +$8k/11-winners is the
  top lever and its shadow is LIVE; "the edge IS the tail"; honesty ledger for the #425 walk).

**THE THREE TRIGGERS (operator-owned):** "pre-build the Lane-1 probes" = OPUS, task #458 ·
"run block lane 1" = the decision sitting (Fable + operator), task #459, docket on the line ·
"run fable weekend block 3" = Sun 7/13 tiered maximal day, task #457 (judge robustness →
regression gate is T1; roadmap §Block 3; cut from the bottom).

**Dated spine:** #395 GO/NO-GO due Mon 7/14 (ruled at the sitting) · #460 flip /model default
back to Opus · 7/18 M1 sitting (#335; T1's robustness map + R5 preconditions feed it) ·
7/14-21 the #425 declaration walk (dossier = evidence spine) · 7/25 ingest dry_run · 8/06
giveback review.

**Verify-lives pending (fire on their own):** #306 first giveback-shadow row · #443 next EP
HIGH · #287 next real exit · #183 first live fill.

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
  main-loop verify/deploy/review. Fable window = this weekend only (Block 3 Sun 7/13 + the Lane-1
  sitting); after that Fable is unavailable for a while — everything else runs Opus/Sonnet.
- **jsonb double-encode class**: the pool codec auto-`json.dumps` every jsonb param — NEVER pre-`json.dumps`
  a jsonb value (double-encodes to a string). Pass the plain object; keep the `::jsonb` cast. (#177/#287/#412.)

---
*Keep this file's §3 roughly current if you do a long stint on the laptop; but PLAN.md is always the
authoritative task state. When the operator is back on the desktop, the machine-local memory resumes.*
