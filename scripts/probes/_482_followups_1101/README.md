# #482 follow-ups (2026-11-01) — OLD-vs-NEW proof for the trail-arming era switch

`lfc_old_vs_new_probe.py` runs, on the tree `REPO` points at: the five `tests/_lfc_equality_scenarios`
recorder runs (59 rows) and 44 `walk_arm` fixtures (every harvest x stop arm, the +8R/3R variant, a
below-line buy; 2026-08- and 2017-dated sessions) and prints one JSON document.

Run once on the base tree (`62a7ddf4`, where `live_fill_counterfactuals.py` is the #705-pinned
`6bdb44b9...`) and once on the changed tree; the two documents are byte-identical:
`lfc_old_vs_new.before.sha256` / `lfc_old_vs_new.after.sha256` (same hash). Every session in the probe
precedes 2026-10-29, as every session the frozen #705 reads walk does (2016-2022).

    REPO=/path/to/base   python3 lfc_old_vs_new_probe.py > before.json
    REPO=/path/to/change python3 lfc_old_vs_new_probe.py > after.json
    cmp before.json after.json

## Follow-up (3) — the tracker / book-arm cleanups (`tracker_old_vs_new_probe.py`)

Drives 26 hour-lane scenarios, the 5-minute lane, 5 exit-pass scenarios, 2 one-time replays and 10
book-arm scenarios (the two test suites' own fixtures) and prints every INSERT / UPDATE payload, count
and audit event. Captured at `bc641105` (before the cleanups) and after them: the payloads are
byte-identical (`tracker_old_vs_new.{before,after}.sha256`, hashed with the `fetches` key removed).
The `fetches` key is the one INTENDED change — the exit pass's daily-bar fetch count per scenario:
`day0_skip` 1 -> 0, `mixed` (six rows: two AAA siblings, CCC, a pre-alert DDD, a stale EEE, a
nothing-left FFF) 5 -> 2, `fetch_raises` 2 -> 2 (a failed fetch is not cached), `hour_row_closed` and
`no_bar` 1 -> 1.
