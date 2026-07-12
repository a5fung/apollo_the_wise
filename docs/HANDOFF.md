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

## 3. WHERE WE ARE (in-flight, as of 2026-07-11 ~midnight PDT — end of the Fable weekend build)

**Apollo trades REAL money (MAGNA53 live since 6/30; equity ~$4.9k; live record N=3 / −$71 —
below noise; #454 will make the next 15 trades diagnostic).** Prod healthy.

**Sat 7/11 shipped (all committed + pushed, check_plan green):**
- **Lane-1 pre-build (#458) DONE** — 6 read-only probe tables under `docs/analysis/*_2026-07-11.md`,
  all advisor-checked. The sitting rulings: **#395 NO-GO** (coil-finder shadow −1.23R, Monday-crit)
  · **#170 NO-GO** (re-setup dilutes the EP book) · **#357** direction-confirmed/N-gated · **#146
  HOLD** (incumbent gate is tail-positive +0.78R; drop-COILED replay only 4/21-faithful) · **#274
  ✓ PASS** (sign 0025 F1-F3) · **#448 b6** scoped (deterministic no-LLM path).
- **#436 fork B SHIPPED + VERIFIED-LIVE** (real-money safeguard): inert `pending_confirmation`
  proposals no longer count toward the position cap — shared `db.OPEN_POSITION_STATUSES` across
  3 cap sites + coverage-drift, DEPLOYED both money containers, constant confirmed live. Root
  cause = pre-ramp staged-paper proposals, NOT an active bug. Follow-ups filed: **#461** (cap
  check→insert TOCTOU race) · **#436(b)** self-heal (cosmetic hygiene, 7/25, + 2 /simplify
  ride-along cleanups). Advisor-reviewed + /simplify'd; the `_check_safeguards` enforcement test added.
- **Block 3 (Fable) FULLY EXECUTED T1-T6 in one evening:** **ADR 0030** (judge-robustness taxonomy
  + 36-case adversarial corpus `scripts/evals/judge_robustness_corpus_v1.json` + the [5m/7]
  regression gate) · **ADR 0031** (pivot structure-stops, two-arm shadow) · **theme-merge golden
  corpus** (gates 0025-C3) · **R5 drift band** specced · **cross-ADR register** (caught 0026-D2
  evidence-contradicted by #146) · **both sitting packs** (`lane1_sitting_pack_2026-07-13.md` +
  `m1_sitting_pack_2026-07-18.md`) · gap-hunt (program is execution-shaped; Pradeep 39%-bar
  extraction → rides #448).
- **Block 4 filed (#462) — THE IMPLEMENTATION GAUNTLET** (operator: Block 3 too tame): 7 tiers of
  build/audit/eval-run, each ending in running code or a verdict.

**SUNDAY 7/13 — TWO TRIGGERS (operator-owned):**
1. **"run block lane 1"** → task **#459** — the decision sitting; runs off `lane1_sitting_pack`
   (Bundle B = the only 3 real deliberations: #395 kill · 0026-D2 park · #452 scope).
2. **"run fable block 4 tier N"** (or "continue block 4") → task **#462** — T1 (build+run the 0030
   robustness eval) is the 7/18-critical one; roadmap §Block 4.

**Dated spine:** #395 ruled at the sitting (Mon 7/14 target) · **7/18 M1** authority-flip sitting
(#335; pack ready; needs the 0030-C3 map + T2c drift band built this week) · 7/14-21 #425
declaration walk (dossier = spine) · 7/25 ingest dry_run flip + #436(b) · 8/06 giveback F1.

**Verify-lives pending (fire on their own):** fork B's behavioral effect = next live-staged ramp
(no-op for magna53 auto-enter) · #306 first giveback-shadow row · #443 next EP HIGH · #287/#183
next real exit / first live fill (market-gated, resume Mon).

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
