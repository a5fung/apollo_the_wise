"""#358 — the ENUMERATED registry of cohort-shaping gate constants ADR 0013's provenance rule
governs, + the citation each one carries (or `None` if it currently has none).

WHY THIS EXISTS (root cause, #358 / advisor 6/22): `anticipation.is_entry_tight`'s absolute-range
gate silently contradicted the operator's SIGNED 6/16 volatility-relative conclusion for weeks —
nothing checked code-against-captured-methodology. ADR 0013 (`docs/decisions/
0013-consolidation-plays-post-runup.md`) already states the rule ("every cohort-shaping criterion
must cite a source ... a number with no source may NOT gate or shape the cohort") but it was prose,
unenforced. This registry + `scripts/check_gate_provenance.py` make it mechanical.

WHAT THIS DOES NOT CATCH (be honest about the limit): a citation that is PRESENT and technically
correct can still be *semantically* wrong (the original bug was "absolute range" cited as if it were
the signed "volatility-relative" conclusion — the words matched a topic, not the substance). This
check forces the human checkpoint — you cannot add or keep a cohort gate without writing down its
source in one place — which is the moment a reviewer notices the source says something different
from the code. It does not itself verify semantic fidelity.

SCOPE (deliberately curated, NOT every constant in the repo — extend this list over time):
Family-A gates (`anticipation.py` §327/coil, `flag_detector.py` HTF) + core detection-gate
constants (`ninem_detector.py`, `ep_detector.py`). Telemetry-only / ranking-only constants (e.g.
`TIGHT_CLOSE_PCT` IS included because ADR 0013 §2.4 explicitly discusses it, even though it's
ranking-only, not a hard gate — the ADR still requires it to cite a source) are in scope; pure
implementation plumbing (window sizes with no operator-facing "value", e.g. `COIL_WINDOW`) is not,
to keep the first pass tight per the operator's capacity note. Add entries as new gates land —
CHANGE_PROCESS still governs any VALUE change; this registry only tracks citation + drift.

── CITATION CONVENTION ──────────────────────────────────────────────────────────────────────────
A citation is `{"file": <repo-relative path>, "text": <exact substring>}`. `file` must be one of:
`docs/methodology/operator_shared_notes.md` (the verbatim operator-shared-methodology log — ADR
0013's own named source of truth), a `docs/decisions/*.md` ADR, a `docs/setups/*.md` setup SSoT, or
a `docs/analysis/*.md` backtest/validation writeup (the CHANGE_PROCESS evidence artifact — a
legitimate source distinct from raw operator methodology, e.g. a replay-validated entry-timing
gate). `text` must appear verbatim (whitespace/dash-normalized — see `_normalize` in the checker)
in that file — the checker resolves every citation against the live doc, so a typo'd or
stale-after-a-doc-edit citation is caught as BROKEN, not silently trusted.

A gate with `"citation": None` is a CURRENTLY UNCITED value — a genuine, named operator finding
(ADR 0013's rule says it should NOT be gating the cohort). #358's build does NOT invent a citation
or change the value to make one uncited entry disappear (THE LINE — tooling only) — it is tracked
as ratchet-baseline debt in `scripts/gate_provenance_baseline.json` so it shows up on every run
without blocking commits that don't touch it, and can never grow silently (a NEW uncited gate added
to this registry, or the file scan finding a NEW live constant, fails the gate immediately).

── ENTRY SHAPE ───────────────────────────────────────────────────────────────────────────────────
    id:        unique key ("<module-nickname>.<NAME>") — stable across edits, used by the baseline.
    file:      repo-relative path to the source module.
    kind:      "const"   — a module-level `NAME = <literal>` assignment.
               "default" — a function's keyword-only default; `name` = "func_name:param_name".
    name:      the constant name (const) or "func:param" (default).
    value:     the value recorded HERE at registration time — the drift check re-parses the LIVE
               value from `file` and fails loudly if it no longer matches (numeric equality, not
               string — `0.50 == 0.5`). A legitimate operator-signed value change must update this
               field (+ the citation, if the source changed) in the SAME commit as the code change.
    citation:  {"file", "text"} or None (see above).
    note:      free-text — why cited / why currently uncited (the operator-finding rationale).
"""
from __future__ import annotations

GATE_REGISTRY: list[dict] = [
    # ── Family A — anticipation.py (ADR 0013 §2, signed) ────────────────────────────────────────
    {
        "id": "anticipation.TIGHT_CLOSE_PCT",
        "file": "agents/market_intelligence/anticipation.py",
        "kind": "const",
        "name": "TIGHT_CLOSE_PCT",
        "value": 0.004,
        "citation": {
            "file": "docs/methodology/operator_shared_notes.md",
            "text": "Price percent change today between -.4 and .4",
        },
        "note": "Pradeep's qualifying tightness bar (2026-06-15 tweet, transcribed 6/16).",
    },
    {
        "id": "anticipation.COIL_RUNUP_MIN",
        "file": "agents/market_intelligence/anticipation.py",
        "kind": "const",
        "name": "COIL_RUNUP_MIN",
        "value": 1.15,
        "citation": {
            "file": "docs/decisions/0013-consolidation-plays-post-runup.md",
            "text": "MAX(close) / MIN(close) ≥ 1.15",
        },
        "note": "ADR 0013 §2.1 run-up gate, signed 2026-06-16/17 (the COO-canary criterion).",
    },
    {
        "id": "anticipation.COIL_HOLD_LIMIT",
        "file": "agents/market_intelligence/anticipation.py",
        "kind": "const",
        "name": "COIL_HOLD_LIMIT",
        "value": 0.50,
        "citation": {
            "file": "docs/decisions/0013-consolidation-plays-post-runup.md",
            "text": "(=0.50, soft / operator-tunable)",
        },
        "note": "ADR 0013 changelog 2026-06-27 — coil-finder's runup-retrace hold cap.",
    },
    {
        "id": "anticipation.ENTRY_RMV_MAX",
        "file": "agents/market_intelligence/anticipation.py",
        "kind": "const",
        "name": "ENTRY_RMV_MAX",
        "value": 30.0,
        "citation": {
            "file": "docs/decisions/0013-consolidation-plays-post-runup.md",
            "text": "<30 = getting tight",
        },
        "note": "ADR 0013 changelog 2026-06-27 — RMV creator-confirmed threshold (PROVISIONAL, "
                "operator labeling pass supplies the N>=10 calibration evidence).",
    },
    {
        "id": "anticipation.ENTRY_RANGE_MAX",
        "file": "agents/market_intelligence/anticipation.py",
        "kind": "const",
        "name": "ENTRY_RANGE_MAX",
        "value": 0.07,
        "citation": {
            "file": "docs/analysis/ninem_consolidation_vs_day2_replay_327_2026-06-18.md",
            "text": "range≤5–7%",
        },
        "note": "#327 replay validation (2026-06-18) — the robust region for the entry-timing gate.",
    },
    {
        "id": "anticipation.ENTRY_VOL_MAX",
        "file": "agents/market_intelligence/anticipation.py",
        "kind": "const",
        "name": "ENTRY_VOL_MAX",
        "value": 1.0,
        "citation": {
            "file": "docs/analysis/ninem_consolidation_vs_day2_replay_327_2026-06-18.md",
            "text": "vol≤1.0",
        },
        "note": "#327 replay validation (2026-06-18).",
    },
    {
        "id": "anticipation.ENTRY_TIGHT_N",
        "file": "agents/market_intelligence/anticipation.py",
        "kind": "const",
        "name": "ENTRY_TIGHT_N",
        "value": 3,
        "citation": {
            "file": "docs/analysis/ninem_consolidation_vs_day2_replay_327_2026-06-18.md",
            "text": "N=3 is the readable sweet spot",
        },
        "note": "#327 replay validation (2026-06-18) — persistence, not RMV depth, times the entry.",
    },
    # ── Family A — db.py get_anticipation_universe (ADR 0013 §2, signed defaults) ───────────────
    {
        "id": "db.get_anticipation_universe:runup_min",
        "file": "agents/market_intelligence/db.py",
        "kind": "default",
        "name": "get_anticipation_universe:runup_min",
        "value": 1.15,
        "citation": {
            "file": "docs/decisions/0013-consolidation-plays-post-runup.md",
            "text": "MAX(close) / MIN(close) ≥ 1.15",
        },
        "note": "Same signed run-up gate as anticipation.COIL_RUNUP_MIN, mirrored as the SQL "
                "proposer's default kwarg.",
    },
    {
        "id": "db.get_anticipation_universe:incl_max",
        "file": "agents/market_intelligence/db.py",
        "kind": "default",
        "name": "get_anticipation_universe:incl_max",
        "value": 0.010,
        "citation": {
            "file": "docs/decisions/0013-consolidation-plays-post-runup.md",
            "text": "close %chg today| ≤ 1.0%",
        },
        "note": "ADR 0013 §2.2 today-compression inclusion gate (the wide-net 1.0%, NOT the 0.4% "
                "ranking marker).",
    },
    {
        "id": "db.get_anticipation_universe:dvol_min",
        "file": "agents/market_intelligence/db.py",
        "kind": "default",
        "name": "get_anticipation_universe:dvol_min",
        "value": 20_000_000.0,
        "citation": {
            "file": "docs/decisions/0013-consolidation-plays-post-runup.md",
            "text": "≥$20M/day dollar-volume (probe value)",
        },
        "note": "Operator-signed $20M as-is 2026-07-18 (#481): ADR 0013 §2.3 liquidity floor, an "
                "EXPLICIT PROBE (the ADR's own text: 'sanity floor, not a selection edge — sign "
                "off the exact number'). The 6/16 funnel (1478->751) ran on this value; revisit at "
                "the next Family-A calibration.",
    },
    # ── Family A — flag_detector.py HTF (sourced O'Neil/Minervini/Qullamaggie spec, 2026-06-22) ─
    {
        "id": "flag_detector._RUNUP_LOOKBACK_DAYS",
        "file": "agents/market_intelligence/flag_detector.py",
        "kind": "const",
        "name": "_RUNUP_LOOKBACK_DAYS",
        "value": 40,
        "citation": {
            "file": "docs/methodology/operator_shared_notes.md",
            "text": "Lookback 40 days",
        },
        "note": "HTF flagpole spec, replaces the unsourced n=1 '50%/60d' (#356).",
    },
    {
        "id": "flag_detector._RUNUP_MIN_RATIO",
        "file": "agents/market_intelligence/flag_detector.py",
        "kind": "const",
        "name": "_RUNUP_MIN_RATIO",
        "value": 1.90,
        "citation": {
            "file": "docs/methodology/operator_shared_notes.md",
            "text": "close ≥90% above the close 40 trading days ago",
        },
        "note": "HTF flagpole surge floor (O'Neil-sourced, relaxed from 100-120% canonical to 90%).",
    },
    {
        "id": "flag_detector._FLAG_DEPTH_MIN",
        "file": "agents/market_intelligence/flag_detector.py",
        "kind": "const",
        "name": "_FLAG_DEPTH_MIN",
        "value": 0.75,
        "citation": {
            "file": "docs/methodology/operator_shared_notes.md",
            "text": "within 25% of the 40-day high",
        },
        "note": "HTF flag depth floor (<=25% pullback near the 40d high).",
    },
    {
        "id": "flag_detector._HTF_MIN_ADV_SHARES",
        "file": "agents/market_intelligence/flag_detector.py",
        "kind": "const",
        "name": "_HTF_MIN_ADV_SHARES",
        "value": 500_000,
        "citation": {
            "file": "docs/methodology/operator_shared_notes.md",
            "text": "ADV > 500,000 shares",
        },
        "note": "HTF liquidity floor.",
    },
    {
        "id": "flag_detector._HTF_MAX_LOSS_PCT",
        "file": "agents/market_intelligence/flag_detector.py",
        "kind": "const",
        "name": "_HTF_MAX_LOSS_PCT",
        "value": 0.08,
        "citation": {
            "file": "docs/methodology/operator_shared_notes.md",
            "text": "max-loss cap **5–8%** from entry",
        },
        "note": "HTF hard max-loss cap — code takes the upper (looser) bound of the sourced 5-8% "
                "range.",
    },
    {
        "id": "flag_detector._HTF_MIN_ADR_PCT",
        "file": "agents/market_intelligence/flag_detector.py",
        "kind": "const",
        "name": "_HTF_MIN_ADR_PCT",
        "value": 0.04,
        "citation": {
            "file": "docs/methodology/operator_shared_notes.md",
            "text": "ADR > 4%",
        },
        "note": "HTF ADR floor — sourced verbatim from the 2026-06-22 operator-shared HTF blueprint "
                "(same sentence as _HTF_MIN_ADV_SHARES's citation). The code comment's 'sources run "
                "3-6%' is literature context; the data-gated tune (htf_adr_threshold_tune) remains "
                "the calibration path. Cited 2026-07-18 (#481).",
    },
    # ── Family B / detection — ninem_detector.py (docs/setups/ninem.md SSoT) ────────────────────
    {
        "id": "ninem_detector._MIN_PRICE",
        "file": "agents/market_intelligence/ninem_detector.py",
        "kind": "const",
        "name": "_MIN_PRICE",
        "value": 5.00,
        "citation": {"file": "docs/setups/ninem.md", "text": "Price**: ≥ $5"},
        "note": "9M universe price floor.",
    },
    {
        "id": "ninem_detector._MIN_DOLLAR_VOL_ACTUAL",
        "file": "agents/market_intelligence/ninem_detector.py",
        "kind": "const",
        "name": "_MIN_DOLLAR_VOL_ACTUAL",
        "value": 50_000_000,
        "citation": {"file": "docs/setups/ninem.md", "text": "≥ $50M actual (confirmed)"},
        "note": "9M confirmed-alert dollar-volume floor.",
    },
    {
        "id": "ninem_detector._ADV_ANOMALY_MULTIPLIER",
        "file": "agents/market_intelligence/ninem_detector.py",
        "kind": "const",
        "name": "_ADV_ANOMALY_MULTIPLIER",
        "value": 3,
        "citation": {"file": "docs/setups/ninem.md", "text": "effective_vol ≥ 3 × adv_20"},
        "note": "9M ADV-anomaly ratio gate.",
    },
    {
        "id": "ninem_detector._MIN_GAP_PCT",
        "file": "agents/market_intelligence/ninem_detector.py",
        "kind": "const",
        "name": "_MIN_GAP_PCT",
        "value": 3.0,
        "citation": {"file": "docs/setups/ninem.md", "text": "gap ≥ 3% OR intraday gain ≥ 4%"},
        "note": "9M directional gate (gap leg).",
    },
    {
        "id": "ninem_detector._MIN_INTRADAY_GAIN_PCT",
        "file": "agents/market_intelligence/ninem_detector.py",
        "kind": "const",
        "name": "_MIN_INTRADAY_GAIN_PCT",
        "value": 4.0,
        "citation": {"file": "docs/setups/ninem.md", "text": "gap ≥ 3% OR intraday gain ≥ 4%"},
        "note": "9M directional gate (intraday leg).",
    },
    # ── Family B / detection — ep_detector.py (docs/setups/magna53_ep.md SSoT + ADR 0003) ───────
    {
        "id": "ep_detector.MIN_PREV_CLOSE",
        "file": "agents/market_intelligence/ep_detector.py",
        "kind": "const",
        "name": "MIN_PREV_CLOSE",
        "value": 5.0,
        "citation": {"file": "docs/setups/magna53_ep.md", "text": "prev_close ≥ $5"},
        "note": "MAGNA53 price floor.",
    },
    {
        "id": "ep_detector.EP_COOLDOWN_DAYS",
        "file": "agents/market_intelligence/ep_detector.py",
        "kind": "const",
        "name": "EP_COOLDOWN_DAYS",
        "value": 60,
        "citation": {
            "file": "docs/setups/magna53_ep.md",
            "text": "60-day cooldown after any prior EP alert",
        },
        "note": "MAGNA53 re-fire cooldown.",
    },
    {
        "id": "ep_detector._MIN_GAP_PCT_DEFAULT",
        "file": "agents/market_intelligence/ep_detector.py",
        "kind": "const",
        "name": "_MIN_GAP_PCT_DEFAULT",
        "value": 9.0,
        "citation": {
            "file": "docs/setups/magna53_ep.md",
            "text": "9.0% hard floor, env `EP_MIN_GAP_PCT`",
        },
        "note": "2026-08-19 operator-signed REVERSAL of the 2026-05-17 R2 8.0->10.0 raise "
                "(ADR 0003 §3's win-rate N=8 read predates P3/tail-first evidence discipline — "
                "see magna53_ep.md 2026-08-19 change log + ADR 0003's superseded addendum). "
                "Priced in docs/analysis/gap_floor_decision_table_2026-08-19.md.",
    },
    {
        "id": "ep_detector.MAX_EXTENSION_PCT",
        "file": "agents/market_intelligence/ep_detector.py",
        "kind": "const",
        "name": "MAX_EXTENSION_PCT",
        "value": 50.0,
        "citation": {
            "file": "docs/setups/magna53_ep.md",
            "text": "MAX_EXTENSION_PCT=50.0",
        },
        "note": "Operator-ruled 2026-07-18 (#481): the live 50%/5-day-MIN rule IS the intended "
                "criterion (authoritative since 2026-05-07); the SSoT's prior 'prev_close <= 1.50x "
                "SMA-10' was a birth transcription error (never in code), corrected same-day "
                "(magna53_ep.md lines 19/30/53 + change log). Live criterion unchanged.",
    },
]
