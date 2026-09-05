# THE ROUTER — for any topic, this says which ONE file owns it

**Start here. Always.** Operator, 2026-08-29: *"We need a SoT, and prevent things diverting from
it or it getting out of date or things fragmented. We built SoT for that purpose, but for
whatever reason, it didn't work, we need to stop this goose chase all the time."*

## Why the old arrangement did not work

It was never wrong — it was never finished. Measured 2026-08-29:

- **An index existed for SETUPS only** (`docs/setups/README.md`). Architecture, methodology,
  decisions, process and the principles had no index at all.
- **99 files use the word "SSoT"**, including analysis documents that declare themselves one. So
  "SSoT" was a word any file could claim, not a structure.
- **The SSoT files did not carry their own findings.** `magna53_ep.md` links 22 analyses and
  works; `exit_discipline.md` links 2 of 6, `htf.md` 1 of 3, `flag_continuation.md` and
  `undercut_rally.md` link none. **The discipline held exactly where attention was, and nowhere
  else — because nothing checked it.**

**So the three failures are: no router, no ownership, no enforcement.** This file is the router.
`tests/test_ssot_router_complete.py` is the enforcement. Ownership is the table below.

## The rules

1. **This file holds NO content — only pointers.** It cannot go stale about a topic because it
   says nothing about any topic. That is the point.
2. **Exactly one file owns a topic.** If two files describe the same thing, one is the owner and
   the other must say so and point here.
3. **The owner carries its own findings.** Every analysis or design document about a topic must
   be referenced from that topic's owner, saying what it ESTABLISHED — not what it was about. An
   orphaned finding is a finding that gets re-derived.
4. **A new SSoT must be registered here in the same commit that creates it.**

⚖ **THE LINE sits above every file listed here.** Nothing in any SSoT authorizes a change to
strategy, entry/exit discipline, sizing, targets, safeguards or live trade state.

---

## Work, process and rules

| topic | owner |
|---|---|
| **All planned work** — every task, ETA, status | **`PLAN.md`** (repo root) |
| Always-loaded operating rules | `CLAUDE.md` |
| **The EP profitability goal + THE PRINCIPLES (P1–P15)** | **`docs/roadmap/ep_profitability_program.md`** |
| How a setup change may be made | `docs/setups/CHANGE_PROCESS.md` |
| **How analysis is done here** | **`docs/methodology/analysis_standard.md`** |
| **The preamble every analysis card gets verbatim** | **`docs/methodology/ANALYSIS_CARD_PREAMBLE.md`** |
| Evidence-gated review triggers | `data_gated_reviews.yaml` |
| Compressed history | `CHANGELOG.md` |
| Cross-machine bootstrap | `docs/HANDOFF.md` |
| Architectural decisions (the *why*, when it outlives the code) | `docs/decisions/NNNN-*.md` |

## Trading setups

Index: `docs/setups/README.md` (phase + last-changed per setup). Each file below owns its
setup's criteria, change log and findings.

| topic | owner |
|---|---|
| MAGNA53 EP — the live setup | `docs/setups/magna53_ep.md` |
| **Delayed-EP re-entry** — incl. the **CONTEXT LEDGER** | `docs/setups/delayed_ep_reentry.md` |
| Exit discipline | `docs/setups/exit_discipline.md` |
| 9M EP + Sugar Baby | `docs/setups/ninem.md` |
| HTF — high tight flag | `docs/setups/htf.md` |
| Undercut & rally | `docs/setups/undercut_rally.md` |
| Wick fill | `docs/setups/wick_fill.md` |
| Parabolic short | `docs/setups/parabolic_short.md` |
| Convergence | `docs/setups/convergence.md` |
| Continuation flag (RETIRED → folded into HTF) | `docs/setups/flag_continuation.md` |
| Portfolio safeguards | `docs/setups/safeguards.md` |
| Catalyst rubric (LIVE gate) | `docs/setups/catalyst_rubric.md` |
| Meta rubric | `docs/setups/meta_rubric.md` |
| Meta rubric — what it is, the REAL dependency graph, the anti-block table (decision record, #504) | `docs/decisions/0035-meta-rubric-architecture.md` |
| Portfolio | `docs/setups/PORTFOLIO.md` |

## Architecture

| topic | owner |
|---|---|
| Entry pipeline (the single funnel) | `docs/architecture/entry_pipeline.md` |
| Theme engine | `docs/architecture/theme_engine.md` |
| Dual-account (paper/live routing) | `docs/architecture/dual_account.md` |
| Trade-state ownership | `docs/architecture/trade-state-ownership.md` |
| Model selection | `docs/model_selection_baseline.md` |

## Methodology — the operator's own words

| topic | owner |
|---|---|
| **EPs he named himself — THE ground truth list** | **`docs/methodology/operator_labelled_eps.md`** |
| Notes he has shared directly | `docs/methodology/operator_shared_notes.md` |
| Pivots + per-stock character | `docs/methodology/pivots-and-stock-character.md` |
| The 620 chart | `docs/methodology/620_chart.md` |
| Structure as a supply ladder | `docs/methodology/structure_model.md` |
| How we find EPs | `docs/methodology/how_we_find_eps_2026-08-22.md` |
| Primitives | `docs/methodology/primitives.md` |

## Operations

| topic | owner |
|---|---|
| Disaster recovery | `docs/ops/disaster_recovery.md` |
| Google Drive backup recovery | `docs/ops/gdrive_backup_recovery.md` |

---

## What is NOT an SSoT

`docs/analysis/**` and `docs/design/**` are **findings and proposals — never owners.** A finding
earns its place by being referenced from the topic owner above; on its own it is a dated
snapshot, and several have been retracted. Where an analysis document calls itself an SSoT, the
owner in this router wins.
