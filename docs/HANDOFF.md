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

## 3. WHERE WE ARE (in-flight, as of CLOSE 2026-07-13 ~00:30 PDT — the rulings-pack night)

**The 7/12→13 marathon:** growth gate shipped (check_plan hard-caps session task growth) · #178/#412/#385
closed verified (board 118→**113**, all real) · TWO Fable red-teams (composition + v1-readiness; every
finding code-verified; 1 of 6 REDs was over-rated — verify premium-model output) · readiness fixes
DEPLOYED (soak fail-opens closed · drawdown fail-open now alerts · FL-4 meter gated on promotion) ·
0025 C1-C3 built DARK · **the 6-fork rulings pack approved wholesale + EXECUTED**
(`docs/analysis/monday_rulings_pack_2026-07-13.md` — the what-and-why of every ruling).

**Live state (Monday verifies):**
- Soak FL-1 = STRICT clock, start **7/8** (the constant IS the ruling); reads 4/10; completes EOD 7/21.
- Ingest = **dry_run since 7/13 00:00 PT** (LEG-B day 1 = Mon); live_r1 sign ~7/17 → FL-4 green ≈ 7/24 → declare.
- RED-3 sizing clamp deployed BOTH money containers (multiplier up-never-past-baseline; ≤1.0 identical).
- 0025 merge arm DARK + **corpus-cleared 14/14** (prompt v2 slice→MERGE) — THEME_MERGE_ARM flip = operator's call.
- Giveback 8/06 flip ruled: **close-below DECISION-LINE** (SMA-trail surface, NOT a resting stop); build at flip.
- Monday market-gated verify-lives: pivot 17:42 job · exposure hook · T2c samples · #445 shadows ·
  #443/#463/#405/#183 event-gated · RED-3 watchdog (16:12 no-show) first exercise.

**Open threads (all in PLAN.md):**
1. **#416 guards build (due 7/16, in_progress)** — ⚠ FIRST prove guard-B on FRMI's reconstructed inputs
   (its audit row is truncated-at-write; live guards run PRE-write so unaffected, but don't ship unproven).
   Eyeball the 2 new sim finds (WEN 5/12 · IMVT 5/20).
2. **#460 (operator): /model default is currently FABLE** (saved 7/12 eve) — flip back to Opus.
3. **Possible UNPUSHED commits** — a local network outage (SSH+GitHub DNS) hit ~00:10 PT during CLOSE;
   at OPEN run `git log origin/main..HEAD` and push. All prod deploys completed + verified BEFORE the outage.
4. Sitting docket: CLEAR (the pack ruled everything). Next: M1 authority flip 7/18 (pack ready) · #448 7/16.

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
  main-loop verify/deploy/review. Fable window = this weekend (Block 3 DONE Sat; Sun 7/13 = the
  Lane-1 sitting #459 + Block 4 #462); after Sunday Fable is unavailable for a while — the Block-4
  card builds + everything else run Opus/Sonnet.
- **jsonb double-encode class**: the pool codec auto-`json.dumps` every jsonb param — NEVER pre-`json.dumps`
  a jsonb value (double-encodes to a string). Pass the plain object; keep the `::jsonb` cast. (#177/#287/#412.)

---
*Keep this file's §3 roughly current if you do a long stint on the laptop; but PLAN.md is always the
authoritative task state. When the operator is back on the desktop, the machine-local memory resumes.*
