#!/usr/bin/env python3
"""Build `walker_cand.py`: the FROZEN COPY of live_fill_counterfactuals.walk_arm with ONE hook set.

Pre-registration §8: "Candidates: a frozen copy of walk_arm (cite blob e9098c36) with ONE hook at
the trigger bar." The copy is GENERATED, not hand-typed, so the whole difference from the live
walker is the list of anchored patches below. Every anchor must match the live source EXACTLY
once or this script stops. The result `walker_cand.py` and a unified diff `walker_diff.out` are
the audit surface: read the diff and you have read every line that differs from live.

With `hook=None` the copy is the live walker (gate G2 proves it on all rows). The hook carries
  rule   : one of RULES below (None = no candidate; the copy just RECORDS both triggers)
  frame  : "A" (trigger = the bar the +8 ORB-R partial books) or "B" (trigger = the bar the +3 ORB-R
           breakeven arm first touches)
  ref    : None | "control_at_close" (depth sale priced at the deciding close) |
           "t20_entry_ref" (#687's rule: at the Frame-A trigger the stop is RESET to entry)
  atr14, day0_close : inputs the chandelier / give-back rules read
  mutate_early : TEST ONLY - own the walk from session 1, before any trigger (must turn G3 red)
  trace  : a dict the walker appends engagement evidence / per-session lines to (G2b, hand-trace)

Read-only. No DB. No prod.
"""
import difflib
import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path("/Users/alvinfung/apollo_the_wise")
SRC = REPO / "agents/market_intelligence/live_fill_counterfactuals.py"
OUT = REPO / "scripts/probes/_runner_recut_1017"
PINNED_BLOB = "e9098c36"

blob = subprocess.check_output(["git", "hash-object", str(SRC)], cwd=REPO, text=True).strip()
assert blob.startswith(PINNED_BLOB), f"live_fill_counterfactuals.py blob {blob} != pinned {PINNED_BLOB}"

text = SRC.read_text()
lo = text.index("def _fresh_walk() -> dict[str, Any]:")
mid = text.index("def walk_arm(*,")
hi = text.index("def live_actual_outcome(")
fresh_src = text[lo:mid]
walk_src = text[mid:hi].rstrip() + "\n"
orig_walk_src = walk_src

PATCHES = []


def patch(anchor: str, repl: str):
    global walk_src
    n = walk_src.count(anchor)
    assert n == 1, f"anchor matched {n} times (need exactly 1):\n{anchor}"
    walk_src = walk_src.replace(anchor, repl)
    PATCHES.append(anchor)


# P0 name + signature
patch("def walk_arm(*,", "def walk_cand(*,")
patch("""             depth_exit: bool = False,
             depth_adr20_pct: Optional[float] = None) -> dict:""",
      """             depth_exit: bool = False,
             depth_adr20_pct: Optional[float] = None,
             hook: Optional[dict] = None) -> dict:  # HOOK: the only new parameter""")

# P1 hook setup, right after the first `out = _fresh_walk()`
patch("""    out = _fresh_walk()
    if stop is None or entry is None or entry - stop <= 0:""",
      """    out = _fresh_walk()
    # ── HOOK SETUP (everything between the HOOK markers is new; nothing else in this function moved) ──
    _H = hook or {}
    _rule, _frame, _ref = _H.get("rule"), _H.get("frame"), _H.get("ref")
    _trace = _H.get("trace")
    _atr14 = _H.get("atr14")
    trig_rec: dict = {}              # which -> {"idx": session index (0 = day 0), "F": stop resting then}
    out["trig"] = trig_rec           # control instrumentation: BOTH frames' triggers are recorded, acted on or not

    def note_trigger(which, idx, F):
        if which not in trig_rec:
            trig_rec[which] = {"idx": idx, "F": F}

    def _owned(idx):
        # the candidate owns the close decision from its trigger bar (inclusive); a day-0 trigger
        # hands over at session 1 (the 16:45 job never decides on the entry day)
        if _rule is None:
            return False
        if _H.get("mutate_early") and _frame not in trig_rec:
            note_trigger(_frame, idx, max(resting, entry))      # TEST ONLY: own the walk before any trigger
        rec = trig_rec.get(_frame)
        return rec is not None and (rec["idx"] == 0 or idx >= rec["idx"])

    def _synth_step(idx, d, b):
        # The candidate's decision for rules with NO moving average line (hold-N, chandelier,
        # give-back). Mirrors apply_daily_exit_step: (1) the resting stop is tested on the bar's
        # low first, at the stop price (the caller then fills at the open on a gap); (2) then the rule.
        rec = trig_rec[_frame]
        rem = state["remaining_shares"]
        ex = list(state.get("exits") or [])
        base = dict(new_remaining=rem, new_partial_taken=state["partial_taken"],
                    new_breakeven_active=state["breakeven_active"],
                    new_running_closes=list(state.get("running_closes") or []) + [b["c"]], new_exits=ex)
        if resting and b["l"] <= resting:
            leg = {"time": str(d), "price": resting, "reason": "stop_hit", "shares": rem,
                   "pnl": (resting - entry) * rem}
            return SimpleNamespace(**{**base, "closed": True, "close_reason": "stop_hit",
                                      "close_price": resting, "effective_stop": resting,
                                      "new_remaining": 0, "new_exits": ex + [leg]})
        level, why, px = resting, None, None
        if _rule.startswith("t") and _rule.endswith("_be"):
            if idx - rec["idx"] >= int(_rule[1:-3]):
                why, px = "time_close", b["c"]                       # market-on-close, date known in advance
        elif _rule in ("gb25_be", "gb50_be"):
            keep = 0.75 if _rule == "gb25_be" else 0.50
            if held_peak > entry and b["c"] < entry + keep * (held_peak - entry):
                why, px = "sma_trail_stop", b["c"]                   # decided on the close, sold at the next open
        elif _rule in ("atr1_be", "atr2_be"):
            k = 1.0 if _rule == "atr1_be" else 2.0
            if _atr14:
                level = max(resting, held_peak - k * _atr14)         # rests from the NEXT session
        else:
            raise ValueError(f"_synth_step: unknown rule {_rule!r}")
        if why:
            leg = {"time": str(d), "price": px, "reason": why, "shares": rem, "pnl": (px - entry) * rem}
            return SimpleNamespace(**{**base, "closed": True, "close_reason": why, "close_price": px,
                                      "effective_stop": level, "new_remaining": 0, "new_exits": ex + [leg]})
        return SimpleNamespace(**{**base, "closed": False, "close_reason": None, "close_price": None,
                                  "effective_stop": level})

    def _note_depth(idx, d, step, dsp, resting_before):
        if _trace is None:
            return
        floor = max(stop, entry) if (state["breakeven_active"] and entry) else stop
        _trace.setdefault("depth", []).append(dict(
            idx=idx, d=str(d), line=step.effective_stop, adr20=depth_adr20_pct, floor=round(floor, 2),
            depth_stop=dsp, resting_before=resting_before,
            binding=bool(dsp > round(floor, 2) + 1e-9), raised=bool(dsp > resting_before + 1e-9)))
    # ── END HOOK SETUP ──
    if stop is None or entry is None or entry - stop <= 0:""")

# P1b: last_close on every pending/horizon return so a data-end mark can be priced
patch("""        out.update(status="pending", reason=reason, pending_at=at)
        out["exits"] = exits""",
      """        out.update(status="pending", reason=reason, pending_at=at)
        out["last_close"] = last_close  # HOOK
        out["exits"] = exits""")

# P2 day 0: fill bar partial -> Frame A trigger (F = the stop then resting)
patch("""        if take_partial(target, fb["m"]) and be_floor:
            cur_stop = max(cur_stop, entry)
    if not closed and be_trigger is not None and fb["h"] >= be_trigger:""",
      """        if take_partial(target, fb["m"]) and be_floor:
            cur_stop = max(cur_stop, entry)
        if partial_taken:  # HOOK
            note_trigger("A", 0, cur_stop)  # HOOK
    if not closed and be_trigger is not None and fb["h"] >= be_trigger:""")

# P3 day 0: fill bar breakeven touch -> Frame B trigger
patch("""        # cannot stop the newly-armed leg (its stop case already returned above).
        cur_stop = max(cur_stop, entry)""",
      """        # cannot stop the newly-armed leg (its stop case already returned above).
        cur_stop = max(cur_stop, entry)
        note_trigger("B", 0, cur_stop)  # HOOK""")

# P4 day 0 loop: breakeven touch
patch("""            # cannot stop the leg on this same bar.
            cur_stop = max(cur_stop, entry)""",
      """            # cannot stop the leg on this same bar.
            cur_stop = max(cur_stop, entry)
            note_trigger("B", 0, cur_stop)  # HOOK""")

# P5 day 0 loop: partial
patch("""        elif hit_tgt:
            if take_partial(target, b["m"]) and be_floor:
                cur_stop = max(cur_stop, entry)
    if closed:
        out["exit_session"] = 0""",
      """        elif hit_tgt:
            if take_partial(target, b["m"]) and be_floor:
                cur_stop = max(cur_stop, entry)
            if partial_taken:  # HOOK
                note_trigger("A", 0, cur_stop)  # HOOK
    if closed:
        out["exit_session"] = 0""")

# P6 held-close peak (day-0 close joins; nothing is DECIDED on day 0)
patch("""    last_close = day0_bars[-1]["c"] if day0_bars else entry
    horizon_reason = "open_at_horizon\"""",
      """    last_close = day0_bars[-1]["c"] if day0_bars else entry
    held_peak = _H.get("day0_close") or last_close  # HOOK: peak held close, for the chandelier / give-back rules
    horizon_reason = "open_at_horizon\"""")

# P7 session loop: peak update after last_close
patch("""            last_close = b["c"]
            if be_ambiguous(b["l"], b["h"], resting):""",
      """            last_close = b["c"]
            held_peak = max(held_peak, b["c"])  # HOOK
            if be_ambiguous(b["l"], b["h"], resting):""")

# P8 session loop: breakeven touch -> Frame B trigger
patch("""            if be_trigger is not None and b["h"] >= be_trigger:
                resting = max(resting, entry)
            hit_tgt = (use_target and not state["partial_taken"] and b["h"] >= target)""",
      """            if be_trigger is not None and b["h"] >= be_trigger:
                resting = max(resting, entry)
                note_trigger("B", idx, resting)  # HOOK
            hit_tgt = (use_target and not state["partial_taken"] and b["h"] >= target)""")

# P9 session loop: partial -> Frame A trigger (+ the t20_entry_ref reset to entry)
patch("""                if take_partial(target, d) and be_floor:
                    resting = max(resting, entry)
                state["remaining_shares"] = remaining""",
      """                if take_partial(target, d) and be_floor:
                    resting = max(resting, entry)
                note_trigger("A", idx, resting)  # HOOK
                if _ref == "t20_entry_ref" and trig_rec["A"]["idx"] == idx:  # HOOK: #687's rule resets the stop to entry
                    resting = entry  # HOOK
                state["remaining_shares"] = remaining""")

# P10 the decision: candidate-owned sessions use the candidate's rule
patch("""            step = apply_daily_exit_step(
                state, bar, d,
                integer_partial_shares=False,
                skip_partial_decision=not ladder_partial,
                prior_closes=(list(prior_closes) if trail_prior_closes else None),
                **ladder_kw)""",
      """            # ── HOOK: candidate ownership (the default path below is the live call, unchanged) ──
            owned = _owned(idx)
            ratchet = "depth" if depth_exit else "plain"
            if owned and _rule in ("close_only", "sma10_depth", "sma20_depth"):
                step = apply_daily_exit_step(
                    state, bar, d,
                    integer_partial_shares=False,
                    skip_partial_decision=not ladder_partial,
                    prior_closes=(list(prior_closes) if trail_prior_closes else None),
                    trail_mode={"close_only": "sma", "sma10_depth": "sma10", "sma20_depth": "sma20"}[_rule])
                ratchet = "none" if _rule == "close_only" else "depth"
            elif owned:
                step = _synth_step(idx, d, b)
                ratchet = "plain"
            else:
                step = apply_daily_exit_step(
                    state, bar, d,
                    integer_partial_shares=False,
                    skip_partial_decision=not ladder_partial,
                    prior_closes=(list(prior_closes) if trail_prior_closes else None),
                    **ladder_kw)
            if _trace is not None:
                _trace.setdefault("sessions", []).append(dict(
                    idx=idx, d=str(d), o=b.get("o"), h=b["h"], l=b["l"], c=b["c"], owned=owned,
                    resting_in=resting, eff_stop=step.effective_stop, sma=getattr(step, "active_sma", None),
                    closed=step.closed, reason=step.close_reason))
            # ── END HOOK ──""")

# P11 the depth sale: the control_at_close reference prices it at the deciding close instead
patch("""                if depth_exit and reason == "sma_trail_stop":""",
      """                if depth_exit and reason == "sma_trail_stop" and _ref != "control_at_close":  # HOOK: ref only""")

# P12 the ratchet: 'none' (close_only rests only F), 'depth', or 'plain' (live non-depth path)
patch("""                if depth_exit:
                    # #687: the resting stop is the live 16:45 job's own `depth_stop_price` on the""",
      """                if ratchet == "none":  # HOOK
                    pass  # HOOK
                elif ratchet == "depth":  # HOOK (was: if depth_exit:)
                    # #687: the resting stop is the live 16:45 job's own `depth_stop_price` on the""")
patch("""                    resting = max(resting, depth_stop_price(
                        line=step.effective_stop, hard_stop=stop, entry_price=entry,
                        breakeven_active=bool(state["breakeven_active"]),
                        adr20_pct=depth_adr20_pct))""",
      """                    _dsp = depth_stop_price(  # HOOK: computed first so the trace can see it
                        line=step.effective_stop, hard_stop=stop, entry_price=entry,
                        breakeven_active=bool(state["breakeven_active"]),
                        adr20_pct=depth_adr20_pct)
                    _note_depth(idx, d, step, _dsp, resting)  # HOOK
                    resting = max(resting, _dsp)  # HOOK""")

# P13 last_close on the terminal returns (the data-end mark)
patch("""    out["exits"] = exits
    out["remaining"] = remaining
    pnl = sum(e["pnl"] for e in exits)""",
      """    out["exits"] = exits
    out["remaining"] = remaining
    out["last_close"] = last_close if not closed else None  # HOOK
    pnl = sum(e["pnl"] for e in exits)""")

header = '''"""GENERATED by make_walker.py - DO NOT EDIT. Frozen copy of
agents/market_intelligence/live_fill_counterfactuals.py::walk_arm (git blob e9098c36) + the hook set.
See walker_diff.out for every line that differs from the live walker."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any, Optional

from agents.market_intelligence.broker.exit_logic import (
    apply_daily_exit_step, depth_stop_price, seed_exit_state)
from agents.market_intelligence.live_fill_counterfactuals import (
    HARVEST_RULES, HORIZON_SESSIONS, TRAIL_RULES)


'''
(OUT / "walker_cand.py").write_text(header + fresh_src.rstrip() + "\n\n\n" + walk_src)

diff = "".join(difflib.unified_diff(orig_walk_src.splitlines(True), walk_src.splitlines(True),
                                    "live walk_arm (blob e9098c36)", "walker_cand.walk_cand", n=1))
(OUT / "walker_diff.out").write_text(diff)
print(f"patches applied: {len(PATCHES)}; walker_cand.py {len((OUT / 'walker_cand.py').read_text().splitlines())} lines; "
      f"diff {len(diff.splitlines())} lines; sha256(walker_cand.py)="
      f"{hashlib.sha256((OUT / 'walker_cand.py').read_bytes()).hexdigest()[:16]}")
