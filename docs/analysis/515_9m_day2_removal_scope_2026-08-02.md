# #515 — SCOPE: retire 9M Day 2 (the strategy, not the character)

**Operator 2026-08-01**: *"9m is a stock character, 9m day2 is dead and needs to be gone period."*

**Status: SCOPE ONLY. Nothing removed. The removal touches the shared entry path and needs its own
session + operator sign-off.**

---

## The finding that changes the shape: it is NOT a clean cut

Three couplings mean "delete the Day 2 strategy" is not a self-contained removal. Each is a decision
for the operator, not a judgement call for me.

### ⚠ Coupling 1 — the 5-min ORB SHADOW LANE runs on the Day-2 spec builder

`broker/shadow_orb_tracker.py:27` imports `prepare_9m_day2_orb_order` and calls it at line 177.
That is the **Shadow ORB 5-min** strategy (`phase=shadow`, still enabled), and it is the lane
carrying the **#482 bracket-geometry evidence** — the 0/14 record the operator ruled on 7/19 and
which #482 keeps open pending N≥30.

**So deleting the Day-2 order builder silently kills an ACTIVE evidence lane on a DIFFERENT card.**

▶ **Options**: (a) keep `prepare_9m_day2_orb_order` and re-home it as the shadow lane's own builder
(it is generic ORB order prep, not 9M-specific logic); (b) give the shadow lane its own copy; or
(c) accept losing the lane. **(a) looks right — the function is ORB mechanics, and its name is the
only 9M thing about it — but that is the operator's call.**

### ⚠ Coupling 2 — `ninem_detector.py` mixes both sides in one file

The detector both (i) finds 9M EP characters — **KEEP** — and (ii) writes the Day-2 candidate list
and renders the Day-2 watchlist — **REMOVE**. Day-2 references inside the file: lines 12, 245, 476,
478, 630 (`insert into mi_9m_day2_candidates`, *"9M Sugar Babies — Day 2 Watchlist"* render, the
Day-2 MA gate).

**This is surgery inside a KEEP file, not a file deletion.** Line 245's comment is the trap: the
Day-1/2 IPO MA gate reads as Day-2-only but is part of the character screen — it must be read, not
pattern-matched.

### ⚠ Coupling 3 — `submit_9m_day2_trade` crosses the execution facade

Registered in `execution_client.py` `_CROSS_FNS` (lines 67, 90) with an `_inprocess` body at 367.
Removing it means editing the facade contract, which has a **boot-time route↔client parity
assertion** — so a partial removal fails the boot, loudly. Good, but it means the change spans
market-agent AND execution and needs the two-step deploy.

---

## Inventory

### REMOVE — the Day 2 ORB strategy
| what | where |
|---|---|
| the job | `scheduler.py:4554` `_9m_day2_orb_job`, registered 6110, id `9m_day2_orb` |
| execution-owned job id | `scheduler.py:105` |
| entry fn | `broker/live_tracker.py::submit_9m_day2_trade` + its `submit_trade_entry` call site |
| facade entries | `execution_client.py` 67, 90, 367 (+ the matching route) |
| candidate WRITER | the `mi_9m_day2_candidates` insert in `ninem_detector.py` |
| Day-2 watchlist render | `ninem_detector.py:630` |
| strategy row | `mi_strategies` "9M Day 2 ORB" (`phase=deprecated`, `enabled=true`) |
| failure hook | `scheduler.py:4804` |

### KEEP — the 9M character (verified separable)
| what | where | files |
|---|---|---|
| intraday 9M EP detection | `ninem_detector.py` core | — |
| alerts table | `mi_9m_ep_alerts` | 5 |
| the scan job | `9m_ep_scan` | 2 |
| Pradeep cohort | `mi_sugar_babies_cohort` | 4 |
| `/9m` routing + surfaces | `agent.py` cascade 5a-5c | — |

### RETAIN, do not drop
`mi_9m_day2_candidates` **the TABLE** — history. Drop the writer, keep the rows.

⚠ **The naming trap, restated**: `mi_9m_day2_candidates` was RENAMED FROM `mi_9m_sugar_babies`
(`db.py:589-601`), while `mi_sugar_babies_cohort` is the persistent Pradeep cohort that **stays**.
A grep for `sugar_bab` hits both sides. **Never pattern-match this removal.**

---

## Why it is worth doing (not cosmetic)

The dead strategy still shares `submit_trade_entry` with MAGNA53. That is exactly how #490's
submission-time gap guard came within one code review of applying MAGNA53's 10% floor to a strategy
whose own bar is 3% — caught by `/simplify` on 8/01 and fixed by parameterising the floor. **Dead
code in a live money path is how that class of defect happens.**

## Suggested sequence (needs sign-off before step 2)

1. **Operator rules on Coupling 1** — re-home the ORB builder, or lose the shadow lane.
2. Remove the job + facade entries + entry fn; boot parity assertion proves completeness.
3. Surgery inside `ninem_detector.py`: drop the Day-2 writer and render, keep the character screen.
4. `mi_strategies` row removed or hard-disabled.
5. **Verify-live: 9M CHARACTER detection still writing `mi_9m_ep_alerts`.** That check is the guard
   against over-deletion and is the one that matters.
6. Two-step deploy (market-agent → execution); `broker/` is now correctly routed after the 8/02
   scope fix.
