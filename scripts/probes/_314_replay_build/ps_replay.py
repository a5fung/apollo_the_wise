#!/usr/bin/env python3
"""#314 — the parabolic short, replayed over five years: the runner (docs/analysis/parabolic_short_replay_prereg_2026-10-21.md, round
4, REGISTERED, NOT FROZEN; never edited here). The building blocks are ps_common (paths, pins, constants, ledger, printout helpers),
ps_population (eras, owners, the night table, the detector passes), ps_features (cap, reads 2-5, the 8-K windows, the distribution
evidence), ps_walk (one walk, rule (c), the bars), ps_goldens (the synthetic positive controls) and ps_pull (STEP 0's pulls, run on
the production server by the main loop, never here). ps_rederive.py is the independent re-derivation (pandas only, no runner code).

STAGES (each its own invocation; every one but --dry-run / --print-pins is refused until its gate passes):
  --dry-run          LOCAL files only, no pull, no detector pass over a population, no walk, no outcome: both eras loaded under the
                     seal, every file fact the plan states checked as a claim, the walk goldens and the synthetic detector golden, the
                     flagger's OPLN / ZWS check, and what STEP 0 waits on (the five pulls). Writes ps_replay_dryrun.txt only.
  --print-pins       every pin of this read -> ps_replay_pins.txt (paste below the doc's marker in the freeze / STEP 0 commits).
  --step0 derive     needs the frozen doc, the dry run COMPLETE with 0 MISMATCH by the modules on disk, every registered pin, and the
                     Polygon reference pull. Writes calendar_B.txt, breaks_applied.tsv, owners.tsv, candidate_ciks.txt (the EDGAR pull's
                     input) and its printout.
  --step0 climax     needs derive's files ledgered and the EDGAR pull (submissions + companyfacts). Runs the detector passes in THREE
                     subprocesses (P1 on the untouched module; P2 and the all-small-tier P2 beside with `_MIN_DOLLAR_VOL_TODAY` patched
                     to 2,000,000 at runtime), each asserting its constant; writes climax_list.tsv, distribution_flags.tsv,
                     distribution_suspects.tsv, filings_wanted.tsv, news_wanted.tsv, suspects_wanted.tsv and its printout.
  --step0 features   needs the climax phase ledgered and the instance / news / Alpaca corporate-action pulls. Writes features.tsv,
                     distribution_class.tsv and its printout. Then --print-pins; the STEP 0 pins are pasted in a commit before the walk.
  --walk             needs every pin below the marker (none ABSENT), the ledger verified, no episodes.tsv / .partial. Walks each
                     population in its own subprocess (the constant asserted again), merges episodes.tsv, runs rule (c), the bars, the
                     reads, the costs, the beside rows, G8 (trade_impact.py) per era, then ps_rederive.py; the result is written only on
                     VERDICT MATCH.

READINGS (R1-R43 in ps_common / ps_population / ps_features / ps_walk / ps_pull / ps_goldens; continued here; the main loop decides):
  R44 STEP 0 is gated on the FROZEN registration (the freeze record: "STEP 0 runs only after it is on `main`"): the doc body pin and
      the runner's module pins must be below the marker. The dry run is not gated (it computes nothing the plan pins).
  R45 Each STEP 0 phase appends its outputs and printout to the ledger (`ps_ledger.tsv`, this folder); a phase whose ledger stage
      exists refuses (once means once); the next phase refuses unless the previous phase's rows verify.
  R46 The climax list holds one row per (population, era, ticker, D0) after the `duplicate_company_night` rule; P2small is its own
      population label (R29). The per-gate funnel, the climax candidates removed by an applied break / the earlier-issuer rule /
      the history rule (scored on their last 120 rows as live would, counted only), and the cap-source counts are written by the
      detector subprocess as JSON and printed by the parent.
  R47 A climax is `void_adjustment_event` when a listed adjustment event of its era is dated inside its 120-row window (after the
      window's first bar, the break_mask convention) or on D0+1..D0+7; `distribution_suspect` when a flagged gap (R9) is dated on
      D0+1..D0+7 of the same series. Both are decided from the pinned lists before any walk; both are walked and flagged, never in n.
  R48 The reachability proxy uses the walk's own stop (climax high + min(3% of it, 0.5 x ATR14), `arm_geometry` on the 120 rows):
      reachable when (stop - climax low) / climax low < 0.25. Geometry known at D0; no outcome.
  R49 Every beside row that DROPS climaxes (the guard's literal jump reading, P1's $250M floor, the M&A keyword row, the 8-K row)
      re-runs rule (c) on what is left (a dropped climax never opens an episode, as live's exclusions never arm); a beside row that
      only changes which statuses count in n (adjustment events in, suspects in, `ended_mid_walk` booked) keeps the primary admission.
  R50 G8 runs `scripts/backtest_data_audit/trade_impact.py --kind r1` per era on the settled episodes written in its r1 layout
      (cell PS314, attempt 0, entry_date, exit_j = sessions held - 1, realized_r) and refuses on a non-zero "entered after the cutoff"
      or "hold runs past the last bar kept" count.
  R58 The INBX 2024-05-31 / DOC 2024-03-04 controls: both symbols carry a ONE-session hole at the issuer switch in the Polygon file
      (INBX 2024-05-30, DOC 2024-03-01 missing; the dry run prints "120 consecutive sessions: False"), so the HISTORY rule already
      removes every night whose window spans the switch — "must be excluded" alone would pass with the earlier-issuer rule broken.
      Derive therefore tests the earlier-issuer FLAG itself (computed independently of the history rule). REVISED 10-28 after review
      (a ruling for the main loop): Polygon's delisted_utc lags a name's last bar (the review measured 1 session on 772 and 2 sessions
      on 248 of 1,038 refetched era-A names; not re-measured here), so the OLD record may own the control night by the date rule, where the rule does not apply and the
      first build would have refused a correct pipeline. Now: the records and the night's owner path are printed; an ACTIVE-owned
      control night must carry the flag; an old-record-owned one must be excluded (history or identity) AND the flag must be set on the
      first active-owned session after the old record's delisted_utc (`earlier_issuer_control`).
  R59 The name cross-check (R14) accepts the SEC submissions `name` or any of its `formerNames`: a delisted record carries the name
      the company had when it was delisted (Square's old record vs Block, Inc.), which is the same filer, not a wrong CIK. The EDGAR
      pull keeps `formerNames`.
  R62 (review 10-28) The subprocess entry points --detect / --walk-pop refuse unless their parent launched them: the parent writes a
      one-shot claim (a random token, P.out/.claim_<stage>_<pop>) and passes it in the child's environment; the child verifies and
      deletes it, then re-runs the parent's gate (--walk-pop: with episodes.tsv.partial REQUIRED and its own part file absent). Outside
      the tests (PYTEST_CURRENT_TEST unset) --paths-json is accepted only by those subprocesses and the paths must be the real tree's
      (X.LOCAL), so no stage can be pointed at another registration doc or a pins override.
  R63 (review 10-28) The reference pull removes a stale .partial before it starts (a whole rewrite); derive refuses on any exact duplicate
      reference record and on a file missing either pull.
  R66 (review 10-28) The climax and features gates require every key of the previous phase's wanted lists to have a FINAL record in its
      pull (candidate_ciks.txt -> submissions AND companyfacts; filings_wanted -> instances; news_wanted -> news; suspects_wanted -> the
      corporate actions). Each phase ledgers the pull files it read (`step0_<phase>:input:<pull>`), so a pull re-run or appended after
      the phase that consumed it refuses the next phase and the walk (the intended once-means-once: re-running a pull after its
      consumer is a new run).
  R60 The runner's own test file (tests/test_parabolic_short_replay.py) is pinned: it holds the synthetic detector golden's expected
      values ("written and pinned before STEP 0").

No network, no DB, no production server, no subagent. The pulls are ps_pull.py's, run elsewhere.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import ps_common as X  # noqa: E402
import ps_population as PP  # noqa: E402
import ps_goldens as GD  # noqa: E402

GuardStop = X.GuardStop
Say = X.Say
STAGE = "ps314_"
SCAN_ERA_ORDER = ("A", "B")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# paths across processes (the subprocesses get the parent's Paths, so a synthetic tree runs whole)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def paths_to_json(P: X.Paths) -> str:
    return json.dumps(dataclasses.asdict(P))


def paths_from_json(s: str) -> X.Paths:
    return X.Paths(**json.loads(s))


def header(say, stage: str, P: X.Paths) -> None:
    say(f"# #314 parabolic-short replay — {stage} ({time.strftime('%Y-%m-%d %H:%M')})")
    say("Guards: no network, no DB, no production server, nothing dated after 2024-12-31 read from a bar file (the 2025-26 split rows are "
        "read only to undo era B's adjustment basis), cb702_pre's survivors-only export never opened, no episode walked and no outcome "
        "computed outside --walk.")
    say("- modules: " + X.modules_line(P))


# ═════════════════════════════════════════════════════════════════════════════════════════════
# pins / gates
# ═════════════════════════════════════════════════════════════════════════════════════════════
def print_pins(P: X.Paths = X.LOCAL, out=print) -> dict:
    p = X.pins(P)
    lines = [f"{k}\t{v}" for k, v in p.items()]
    for ln in lines:
        out(ln)
    with open(P.pins_file, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    out(f"(written to {P.pins_file})")
    return p


def _dry_ok(P: X.Paths) -> list:
    problems = []
    if not X.dry_run_complete(P.dry):
        return [f"the dry run has not completed ({os.path.basename(P.dry)})"]
    mm = X.printout_mismatches(P.dry)
    if mm is None:
        problems.append("the dry run's RESULT line is missing or unreadable")
    elif mm > 0:
        problems.append(f"the dry run ended with {mm} MISMATCH")
    ml = X.printout_line(P.dry, "- modules: ")
    if ml != X.modules_line(P):
        problems.append("the dry run was made by other code than the modules on disk (rerun it)" + (f": {ml}" if ml else ""))
    return problems


def frozen_pins(P: X.Paths) -> dict:
    """The pins that must be below the marker before STEP 0: the doc body, every input of the freeze record, the live and imported
    modules, the runner's modules, the dry-run printout (R44)."""
    p = X.pins(P, include_outputs=False)
    keep = set(X.INPUT_PIN_KEYS) | set(X.LIVE_MODULES) | set(X.IMPORTED_HELPERS) | set(X.RUNNER_TESTS) | set(X.MODULE_FILES) | {"doc_body"}
    out = {k: v for k, v in p.items() if k in keep}
    out["dryrun_printout"] = X.sha_or_absent(P.dry)
    return out


PHASES = ("derive", "climax", "features")
PHASE_OUTPUTS = {
    "derive": ("calendar_B", "breaks_applied", "owners", "candidate_ciks"),
    "climax": ("climax_list", "distribution_flags", "distribution_suspects", "filings_wanted", "news_wanted", "suspects_wanted"),
    "features": ("features", "distribution_class"),
}
PHASE_PULLS = {"derive": ("polygon_reference",), "climax": ("edgar_submissions", "xbrl_facts"),
               "features": ("xbrl_instances", "polygon_news", "alpaca_ca")}


def gate_step0(P: X.Paths, phase: str, child: bool = False) -> list:
    """`child` = the --detect subprocess re-running its parent's gate (R62): the same clauses, the pull-coverage read excepted (the
    parent read it moments before under the same one-shot claim)."""
    problems = list(X.doc_frozen(P.doc))
    problems += _dry_ok(P)
    problems += X.registered_pin_problems(P)
    if os.path.exists(P.doc):
        miss = X.freeze_missing(P.doc, frozen_pins(P))
        if miss:
            problems.append("pins not below the doc's marker (freeze commit: --print-pins, paste): " + ", ".join(miss))
    for k in PHASE_PULLS[phase]:
        if not os.path.exists(getattr(P, k)):
            problems.append(f"the {k} pull is not in hand ({getattr(P, k)}): run ps_pull.py on the server first")
    if not child and not problems:
        problems += pull_coverage(P, phase)
    k = PHASES.index(phase)
    for prev in PHASES[:k]:
        if not X.ledger_has_stage(P.ledger, STAGE + "step0_" + prev):
            problems.append(f"STEP 0 phase {prev!r} has not run (no ledger row)")
    if X.ledger_has_stage(P.ledger, STAGE + "step0_" + phase):
        problems.append(f"STEP 0 phase {phase!r} already ran (once means once): its ledger rows exist")
    existing = [getattr(P, o) for o in PHASE_OUTPUTS[phase] if os.path.exists(getattr(P, o))]
    if existing:
        problems.append("outputs exist: " + ", ".join(existing))
    if os.path.exists(P.ledger):
        bad = X.ledger_verify(P.ledger)
        if bad:
            problems.append("ledger: " + "; ".join(bad))
    return problems


def pull_coverage(P: X.Paths, phase: str) -> list:
    """R66: every key the previous phase asked for has a FINAL record in its pull (ps_pull R64) — a missing CIK would read cap
    `not_pulled` (the detector's mid tier) and a missing filing / news / corporate-action record a silent `not_pulled` unknown."""
    import ps_pull as PL
    try:
        if phase == "climax":
            ciks = PL.read_ciks(P.candidate_ciks)
            checks = [("edgar_submissions", "candidate_ciks.txt", ciks), ("xbrl_facts", "candidate_ciks.txt", ciks)]
        elif phase == "features":
            checks = [("xbrl_instances", "filings_wanted.tsv", [(f["cik"], f["accn"]) for f in PL.read_filings_wanted(P.filings_wanted)]),
                      ("polygon_news", "news_wanted.tsv", [(r["ticker"], r["d0"], r["kind"]) for r in PL.read_news_wanted(P.news_wanted)]),
                      ("alpaca_ca", "suspects_wanted.tsv", [(r["ticker"], r["gap_date"]) for r in PL.read_suspects_wanted(P.suspects_wanted)])]
        else:
            return []
        out = []
        for k, src, wanted in checks:
            miss = PL.not_done(getattr(P, k), PL.KEYS[k], wanted)
            if miss:
                out.append(f"the {k} pull does not cover {src}: {len(miss):,} of {len(wanted):,} keys have no final record (absent, transient or a "
                           f"failed older file; re-run ps_pull.py --{PL.STAGE_OF[k]} --run): {miss[:10]}")
        return out
    except PL.PullStop as ex:
        return [str(ex)]


def gate_walk(P: X.Paths, child: bool = False) -> list:
    """`child` = the --walk-pop subprocess (R62): the parent's claim `episodes.tsv.partial` must EXIST (the parent wrote it after this
    gate passed), every other clause as the parent's."""
    problems = list(X.doc_frozen(P.doc)) + _dry_ok(P) + X.registered_pin_problems(P)
    for ph in PHASES:
        if not X.ledger_has_stage(P.ledger, STAGE + "step0_" + ph):
            problems.append(f"STEP 0 phase {ph!r} has not run")
    p = X.pins(P, include_outputs=False)
    p["dryrun_printout"] = X.sha_or_absent(P.dry)
    for ph in PHASES:
        p[f"step0_{ph}_printout"] = X.sha_or_absent(P.step0_printout(ph))
    p.pop("episodes", None)
    absent = [k for k, v in p.items() if v == "ABSENT"]
    if absent:
        problems.append("pins reading ABSENT (the file must exist and be pinned): " + ", ".join(absent))
    if os.path.exists(P.doc):
        miss = X.freeze_missing(P.doc, p)
        if miss:
            problems.append("pins not below the doc's marker (the STEP 0 commit: --print-pins, paste): " + ", ".join(miss))
    bad = X.ledger_verify(P.ledger) if os.path.exists(P.ledger) else ["ledger missing"]
    if bad:
        problems.append("ledger: " + "; ".join(bad))
    for q in (P.episodes, P.episodes + ".partial", P.result) + tuple(P.o(f"episodes_part_{pop}.tsv") for pop in ("P1", "P2", "P2small")):
        if child and q == P.episodes + ".partial":
            if not os.path.exists(q):
                problems.append(f"{q} is missing: the walk subprocess runs only inside a parent walk that claimed the run")
            continue
        if child and q.endswith(".tsv") and os.path.basename(q).startswith("episodes_part_"):
            continue                                            # the child checks its own part (child_refusal)
        if os.path.exists(q):
            problems.append(f"{q} exists: a population is run once (the operator removes it by hand)")
    if X.ledger_has_stage(P.ledger, STAGE + "walk"):
        problems.append("a walk ledger row exists (once means once)")
    return problems


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the dry run (file facts only)
# ═════════════════════════════════════════════════════════════════════════════════════════════

def reach_counts(e, symbols: list) -> dict:
    """R12: of `symbols`, how many reach $2M by the 20-session rolling median / mean / a single day."""
    ids = [e.tid[s] for s in symbols if s in e.tid]
    med = PP.dv20_max_by_ticker_subset(e, ids, "median")
    mean = PP.dv20_max_by_ticker_subset(e, ids, "mean")
    one = np.array([e.dv[a:b].max() if b > a else np.nan for a, b in (e.rows_of(t) for t in ids)])
    f = X.BAND_DV_FLOOR
    return {"median": int(np.nansum(med >= f)), "mean": int(np.nansum(mean >= f)), "single_day": int(np.nansum(one >= f)), "n": len(ids)}


def dry_run(P: X.Paths = X.LOCAL, facts: dict = None, say=None, goldens: bool = True) -> int:
    """The LOCAL dry run (see the module docstring). `facts` = the plan's file facts (X.FACTS for the real tree; a synthetic test passes
    its own). Writes only P.dry."""
    facts = X.FACTS if facts is None else facts
    say = say or Say()
    header(say, "DRY RUN (local files only; no pull, no population detector pass, no walk)", P)
    C = X.Claims(say)
    try:
        say("\n## Pins (the freeze record against the files on disk)")
        probs = X.registered_pin_problems(P)
        reg = json.load(open(P.pins_override)) if P.pins_override else X.REGISTERED_PINS
        for k in reg:
            bad = [q for q in probs if q.startswith(k + ":")]
            C(f"pin {k}", "match", "match" if not bad else bad[0])
        say("\n## The synthetic positive controls (refusing at STEP 0 and the walk)")
        if goldens:
            import tempfile
            tmp = tempfile.mkdtemp(prefix="ps314_goldens_")          # the golden fixture's export lives in a temp dir, never the data tree
            wp = GD.walk_goldens(tmp, say)
            C("walk goldens (time stop 5 / 3, through the loader and walk_one)", 0, len(wp))
            dp = GD.detector_golden_check(say)
            C("synthetic detector golden (climax + four one-gate-off copies)", 0, len(dp))
        cap_A = _dry_era_A(P, facts, C, say)
        _dry_era_B(P, facts, C, say, cap_A)
        say("\n## What STEP 0 waits on (the pulls; ps_pull.py on the production server, never here)")
        import ps_pull as PL
        for st in PL.STAGES:
            plan = PL.PLANS[st](P)
            say(f"- {st}: " + "; ".join(f"{k} = {v}" for k, v in plan.items()))
        say("- derive waits on: polygon_reference.jsonl.gz (owners, types, CIKs, company keys, the break evidence, the earlier-issuer rule, "
            "the INBX / DOC controls, the gone test)")
        say("- climax waits on: edgar_submissions.jsonl.gz + xbrl_facts.jsonl.gz (the cap -> the detector's tier; the name cross-check; "
            "GME 2021-01 / NVDA 2024-03 printed at their point-in-time tier)")
        say("- features waits on: xbrl_instances, polygon_news, alpaca_corporate_actions (reads 3-5, row (a), the distribution class with "
            "the OPLN / ZWS evidence controls)")
    except GuardStop as ex:
        say(f"\nDRY RUN STOPPED: {ex}")
        say(C.result())
        say.write(P.dry)
        return 2
    say("")
    say(C.result())
    say("DRY RUN COMPLETE")
    say.write(P.dry)
    return 0


def _dry_era_A(P, facts, C, say):
    say("\n## Era A — cb702_pre_v2 (Alpaca, rebuilt), D0 2016-06-23 .. 2022-03-16")
    e = PP.load_era(P, "A")
    C("era A rows", facts["A_rows"], e.info["rows"])
    C("era A symbols (SPY included)", facts["A_symbols"], e.info["symbols"])
    C("era A sessions (= sessions.txt, asserted at load)", facts["A_sessions"], e.info["sessions"])
    C("era A raw-close key set = the export's (both ways, asserted at load): raw_unknown", 0, int((~np.isfinite(e.raw)).sum()))
    C("era A first scorable D0 (the 120th session)", X.A_D0_FIRST, e.cal[e.first_d0])
    C("era A last D0 (the session before era B's first)", X.A_D0_LAST, e.cal[e.last_d0])
    C("era A last D0 is session number", 1562, e.last_d0 + 1)
    C("era A scorable D0 sessions", X.A_SCORABLE, e.last_d0 - e.first_d0 + 1)
    C("era A D0 + 7 of the last D0", "2022-03-25", e.cal[e.last_d0 + X.WALK_AFTER])
    pat, sfx = e.info["pattern_ok"], e.info["suffix"]
    C("era A symbols with characters outside ^[A-Z]{1,5}$", facts["A_other_chars"], int((~pat).sum()))
    for k in ("W", "U", "R"):
        C(f"era A 5-letter symbols ending {k}", facts[f"A_suffix_{k}"], int((sfx == k).sum()))
    C("era A symbols ending before 2022-06-30", facts["A_ended_early"], PP.ended_early(e, X.A_LAST))
    for s in facts["full_session_symbols"]:
        t = e.tid.get(s)
        C(f"era A {s} carries every session", X.A_SESSIONS, (int(e.D.stop[t] - e.D.start[t]) if t is not None else 0))
    # guard + break evidence
    guard = PP.load_guard(P.guard_A)
    bc = PP.break_classes(guard)
    C("era A symbols with a guard break", facts["A_breaks"], bc["symbols"])
    C("era A jump-only / hole-only / both", (facts["A_jump_only"], facts["A_hole_only"], facts["A_both"]),
      (bc["jump_only"], bc["hole_only"], bc["both"]))
    rows = PP.classify_breaks(e, guard, None)
    jump_syms = sorted({r["symbol"] for r in rows if r["kind"] == "jump"})
    C("era A symbols with a jump", facts["A_jump_symbols"], len(jump_syms))
    rc = reach_counts(e, jump_syms)
    C("era A jump symbols reaching $2M (R12: 20-session rolling median)", facts["A_jump_symbols_dv2m"], rc["median"])
    say(f"  (beside, never claimed: by the 20-session mean {rc['mean']}, by a single day {rc['single_day']})")
    fac_rows = [r for r in rows if r["kind"] == "jump"]
    nchg = sum(1 for r in fac_rows if r["evidence"].startswith("fac_change=") and _fac_val(r["evidence"]) is not None
               and _fac_val(r["evidence"]) > X.JUMP_FAC_CHANGE)
    say(f"- era A jumps with a raw / adjusted factor change > 1% on the date (applied whatever the company evidence): {nchg} of {len(fac_rows)}; "
        f"the rest wait on the reference pull's company evidence (`pending`)")
    for s, d, want in facts["fac_change_checks"]:
        chg, rel = PP.fac_change_on(e, s, d)
        C(f"era A {s} {d} jump: factor change > 1%", want, bool(chg))
    if facts.get("guard_breaks_of"):
        gs, gb = facts["guard_breaks_of"]
        C(f"era A {gs} guard breaks", gb, ";".join(f"{d}:{k}" for d, k in guard.get(gs, [])))
    # R17: the split test between a fact's `end` and its `filed` date is a factor STEP above 1% (never S != 1 on cent-rounded closes)
    same = e.row_tid[1:] == e.row_tid[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        stp = np.abs(e.fac[1:] / e.fac[:-1] - 1.0)
    big = same & (stp > X.JUMP_FAC_CHANGE)
    noise = same & (stp > 1e-9) & ~big
    say(f"- era A bar-to-bar raw / adjusted factor steps above 1% (R17's split test): {int(big.sum()):,} on "
        f"{len(np.unique(e.row_tid[1:][big])):,} symbols; steps in (1e-9, 1%] (cent rounding, never a split): {int(noise.sum()):,} "
        f"(printed, never claimed)")
    import ps_stages as S
    basis = S.EraBasis(e)
    for s_, want in facts.get("fac_step_dates", ()):
        t = e.tid.get(s_)
        got = ()
        if t is not None:
            a, b = e.rows_of(t)
            k = np.flatnonzero(big[a: b - 1]) + a + 1
            got = tuple(e.cal[e.D.ci[q]] for q in k)
        C(f"era A {s_}: dates of a factor step above 1%", tuple(want), got)
    for s_, end, filed, want in facts.get("split_between_checks", ()):
        C(f"era A {s_}: a split between end {end} and filed {filed}", want, basis.split_between(s_, end, filed))
    # dedupe leftovers
    dd = PP.load_dedupe(P.dedupe_A)
    C("dedupe pairs", facts["dedupe_pairs"], len(dd))
    C("dedupe rows dropped", facts["dedupe_rows"], sum(int(r["rows"]) for r in dd))
    ao = PP.alias_outside_span(dd, e)
    C("alias_outside_span symbols (dropped symbols still in v2)", facts["alias_outside_symbols"], len(ao))
    C("alias_outside_span rows outside the dropped span", facts["alias_outside_rows"], sum(v["outside"] for v in ao.values()))
    C("rows of a dropped symbol INSIDE its span (a refusal if > 0)", facts["alias_inside_rows"], sum(v["inside"] for v in ao.values()))
    if sum(v["inside"] for v in ao.values()):
        raise GuardStop("a dedupe_applied.tsv dropped symbol has a bar inside its dropped span: the file is not the deduped one")
    C("alias_outside_span rows per symbol", dict(sorted(facts["alias_rows"].items())), {s: v["outside"] for s, v in sorted(ao.items())})
    C("alias_outside_span symbols carrying a guard break", tuple(facts["alias_with_break"]), tuple(sorted(s for s in ao if s in guard)))
    # adjustment events, types, SIC
    adjA = PP.load_adj_events(P.flags_A, X.A_LAST)
    C("era A adjustment events (adj_event rows)", facts["adj_events_A"], PP.adj_event_rows(P.flags_A))
    say(f"  ({len(adjA)} distinct (ticker, date) events: 3 rows of the split table repeat a raw-step row — LEJU, TBLT, TXMD on the real file)")
    types, st = PP.load_type_table(P.types_A)
    C("era A type table rows / symbols / typed twice / conflicts", (facts["types_A_rows"], facts["types_A_symbols"], facts["types_A_twice"],
                                                                     facts["types_A_conflicts"]), (st["rows"], st["symbols"], st["twice"], st["conflicts"]))
    sic = PP.load_sic_types(P.sic_A)
    C("SIC pull names (era-A copy)", facts["sic_names"], PP.sic_names(P.sic_A))
    say(f"  ({len(sic)} of them carry a type; the rest fall through to unknown)")
    C("SIC pull: the era-A copy is byte-identical to era B's", X.sha_or_absent(P.sic_B), X.sha_or_absent(P.sic_A))
    refset, minus_pre = PP.refetch_set(P, e)
    untyped = [s for s in e.tickers if s not in types and s != "SPY"]
    C("era A v2 symbols with no type-table row", facts["A_untyped_symbols"], len(untyped))
    C("  ... of which refetched (expected 0: all are original symbols)", 0, sum(1 for s in untyped if s in refset))
    ok_rule = [s for s in untyped if X.TICKER_RE.fullmatch(s) and not X.is_test_symbol(s) and not
               (len(s) == 5 and s[-1] in X.WUR_SUFFIX)]
    rc2 = reach_counts(e, ok_rule)
    C("  ... passing the symbol rules (suffix rule included) and reaching $2M (R12 median)", facts["A_untyped_reach_2m"], rc2["median"])
    say(f"  (beside: {len(ok_rule)} pass the symbol rules; by the 20-session mean {rc2['mean']}, by a single day {rc2['single_day']})")
    # refetch records
    import pandas as pd
    recs = pd.read_csv(P.refetch_records, sep="\t", dtype=str, keep_default_na=False)
    C("refetch records / symbols", (facts["refetch_records"], facts["refetch_record_symbols"]), (len(recs), recs["ticker"].nunique()))
    C("refetch-sourced symbols (records ∩ v2)", facts["refetch_added"], len(refset))
    C("v2 minus cb702_pre's symbols (its guard table's symbol list; the export never opened)", facts["refetch_added"],
      len(minus_pre) if minus_pre is not None else -1)
    C("the two refetch sets are equal", True, minus_pre is not None and refset == minus_pre)
    strag = pd.read_csv(P.straggler_records, sep="\t", dtype=str, keep_default_na=False)
    C("straggler records", facts["straggler_records"], len(strag))
    C("straggler records dated 2022-06-30 (the fetch cut-off, never a Polygon delisted_utc)", facts["straggler_records"],
      int((strag["delisted"] == X.PLACEHOLDER_DELISTED).sum()))
    owning = tuple(sorted(set(strag["ticker"]) & set(e.tickers)))
    C("straggler records that own a v2 series", tuple(sorted(facts["stragglers_owning"])), owning)
    for s, nrows in facts["blank_record_rows"].items():
        t = e.tid.get(s)
        r = recs[recs["ticker"] == s]
        C(f"{s}: rows in v2 / its record's type, CIK and FIGIs blank", (nrows, True),
          (int(e.D.stop[t] - e.D.start[t]) if t is not None else 0,
           bool(len(r)) and all((r[c] == "").all() for c in ("type", "cik", "composite_figi", "share_class_figi"))))
    rv2 = recs[recs["ticker"].isin(refset)].drop_duplicates("ticker")
    nokey = sorted(rv2[(rv2["cik"] == "") & (rv2["composite_figi"] == "") & (rv2["share_class_figi"] == "")]["ticker"])
    C("refetched v2 symbols with no CIK or FIGI at all", facts["A_refetched_nokey"], len(nokey))
    rc3 = reach_counts(e, nokey)
    C("  ... reaching $2M a day (R12 median)", facts["A_refetched_nokey_dv2m"], rc3["median"])
    say(f"  (beside: by the 20-session mean {rc3['mean']}, by a single day {rc3['single_day']})")
    # the distribution flagger over all bars (climax-independent) and the funnel
    fl = PP.distribution_flags(e)
    keys = set(zip(fl["ticker"], fl["gap_date"]))
    for s, d in facts["distribution_controls"]:
        C(f"the flagger lists {s} {d} (refusing at STEP 0)", True, (s, d) in keys)
    for s, d in X.CONTROLS["distribution_printed"]:
        say(f"- the flagger {'lists' if (s, d) in keys else 'does NOT list'} {s} {d}; it is an adj_event: {(s, d) in set(adjA)} (voided either way)")
    say(f"- era A flagged gaps (open / prior close - 1 <= -25%) over all bars: {len(fl):,}")
    say("\n### era A funnel through the bands (file-only; owners, types, the guard and the detector wait on the pulls)")
    for k, v in PP.funnel_dry(e).items():
        say(f"  {k}: {v:,}" if isinstance(v, int) else f"  {k}: {v}")
    _say_superset(say, e)
    gme = e.tid.get("GME")
    say(f"- GME (printed golden, era A): {int(e.D.stop[gme] - e.D.start[gme]) if gme is not None else 0} bars; its 2021-01 sessions are "
        "scored at STEP 0 climax at their point-in-time tier (the cap needs the EDGAR pull)")
    cap = PP.overlap_capture(e)
    del e
    return cap


def _say_superset(say, e) -> None:
    """The EDGAR pull's size, file-only: the necessary-condition nights (R7) before the owner / type / identity rules, and their
    distinct symbols (an upper bound on the companies derive will send to candidate_ciks.txt)."""
    sup = PP.superset_mask(e)
    syms = len(np.unique(e.row_tid[sup]))
    say(f"- era {e.name} necessary-condition nights (R7; before owners, types and the guard): {int(sup.sum()):,} on {syms:,} symbols "
        "(an upper bound on the EDGAR pull's companies from this era)")


def _fac_val(ev: str):
    try:
        return float(ev.split(";")[0].split("=")[1])
    except (ValueError, IndexError):
        return None


def _dry_era_B(P, facts, C, say, cap_A):
    say("\n## Era B — cb702 (Polygon), read through 2024-12-31 only; D0 2022-03-17 .. 2024-12-19 (+ 7 open at the seal)")
    e = PP.load_era(P, "B")
    C("era B rows read (the whole file)", facts["B_rows_total"], int(e.info["rows_read"]))
    C("era B rows dropped at read (dated after 2024-12-31)", facts["B_rows_dropped"], int(e.info["dated_after_cut"]))
    C("era B rows kept", facts["B_rows_kept"], e.info["rows"])
    C("era B symbols kept", facts["B_symbols_kept"], e.info["symbols"])
    say("  (the whole file's 20,285 tickers are not re-counted: it would need the sealed rows' tickers)")
    C("era B sessions (SPY to 2024-12-31)", facts["B_sessions"], e.info["sessions"])
    C("era B last session", X.CUT_B, e.cal[-1])
    nyse = X.nyse_sessions(X.B_FIRST, X.CUT_B)
    C("era B calendar = the NYSE calendar over 2021-09-27 .. 2024-12-31", True, nyse == e.cal)
    C("era B first scorable D0 (the 120th session)", X.B_D0_FIRST, e.cal[e.first_d0])
    C("era B last D0 that can settle (D0 + 7 = the seal)", X.B_D0_LAST, e.cal[e.last_d0])
    C("era B scorable D0 sessions", X.B_SCORABLE, e.last_d0 - e.first_d0 + 1)
    C("era B open-at-the-seal sessions", 7, e.last_detect - e.last_d0)
    allspl = X.load_splits(Path(P.splits_B))
    cut = X.load_splits(Path(P.splits_B), through=date.fromisoformat(X.SPLITS_THROUGH))
    C("splits executing after the file's last day (dropped)", facts["splits_after_file"],
      sum(len(v) for v in allspl.values()) - sum(len(v) for v in cut.values()))
    adjB = PP.load_adj_events(P.flags_B, X.CUT_B)
    C("era B adjustment events (dated <= 2024-12-31)", facts["adj_events_B"], PP.adj_event_rows(P.flags_B))
    guard = PP.load_guard(P.guard_B)
    C("era B symbols with a guard break", facts["B_breaks"], len(guard))
    rows = PP.classify_breaks(e, guard, None)
    nj = sum(1 for r in rows if r["kind"] == "jump")
    ns = sum(1 for r in rows if r["kind"] == "jump" and r["evidence"].startswith("split_on_date"))
    say(f"- era B jumps with a split executing on the date (applied whatever the company evidence): {ns} of {nj}; the rest wait on the "
        "reference pull")
    types, st = PP.load_type_table(P.types_B)
    C("era B type table rows", facts["types_B_rows"], st["rows"])
    fl = PP.distribution_flags(e)
    say(f"- era B flagged gaps over all bars: {len(fl):,} (no testable positive control at this cut: the plan's ⚠)")
    say("\n### era B funnel through the bands (file-only)")
    for k, v in PP.funnel_dry(e).items():
        say(f"  {k}: {v:,}" if isinstance(v, int) else f"  {k}: {v}")
    _say_superset(say, e)
    ov = PP.overlap_compare(e, cap_A)
    say(f"- the overlap (2021-09-27 .. 2022-06-30): {ov['shared']:,} ticker-days in both files; adjusted closes differing by more than 0.5%: "
        f"{ov['differ']:,} = {100.0 * ov['share']:.2f}% (printed, decides nothing; expectation: under 1%)")
    for s, d in X.CONTROLS["earlier_issuer_B"]:
        i = e.bar_index(s, d)
        first = PP.earlier_issuer_first_bar_date(e, s, d)
        cont = bool(e.contig[i]) if i >= 0 else False
        say(f"- control {s} {d}: bar {'present' if i >= 0 else 'ABSENT'}; 120 consecutive sessions: {cont}; window's first bar {first}; "
            f"guard breaks on {s}: {guard.get(s, [])} (R58: derive tests the earlier-issuer FLAG on this night when the new record owns it, else on the first night it does)")
    nv = e.tid.get("NVDA")
    say(f"- NVDA (printed golden, era B): {int(e.D.stop[nv] - e.D.start[nv]) if nv is not None else 0} bars; its 2024-03 sessions are scored at "
        "STEP 0 climax")
    del e


# ═════════════════════════════════════════════════════════════════════════════════════════════
# main
# ═════════════════════════════════════════════════════════════════════════════════════════════
def entry_refusal(a, P: X.Paths) -> str:
    """R62: outside the tests the runner runs on the real tree only — `--paths-json` (a whole Paths, the doc and the pins override among
    its fields) is accepted only by the runner's own subprocesses and only when it names the real tree; a test sets PYTEST_CURRENT_TEST."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return ""
    if a.paths_json and not (a.detect or a.walk_pop):
        return "--paths-json is accepted only by the runner's own subprocesses (--detect / --walk-pop) and the tests"
    if P != X.LOCAL:
        return "the paths differ from the real tree's (X.LOCAL): another doc, pins override or data tree is accepted only under the tests"
    return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--print-pins", action="store_true")
    g.add_argument("--step0", choices=PHASES)
    g.add_argument("--walk", action="store_true")
    g.add_argument("--detect", choices=("P1", "P2", "P2small"), help=argparse.SUPPRESS)      # the climax phase's subprocesses
    g.add_argument("--walk-pop", choices=("P1", "P2", "P2small"), help=argparse.SUPPRESS)    # the walk's subprocesses
    ap.add_argument("--paths-json", default="", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    P = paths_from_json(a.paths_json) if a.paths_json else X.LOCAL
    bad = entry_refusal(a, P)
    if bad:
        print("REFUSED: " + bad, flush=True)
        return 2
    if a.print_pins:
        print_pins(P)
        return 0
    if a.dry_run:
        return dry_run(P)
    import ps_stages as S
    if a.detect:
        return S.detect_pop(P, a.detect)
    if a.walk_pop:
        return S.walk_pop(P, a.walk_pop)
    say = Say()
    if a.step0:
        return S.step0(P, a.step0, say)
    return S.walk(P, say)


if __name__ == "__main__":
    sys.exit(main())
