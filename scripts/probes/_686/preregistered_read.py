#!/usr/bin/env python3
"""#686 — THE PRE-REGISTERED READ of the September block (scan dates 2026-09-04 .. 2026-09-25).

Written 2026-10-04 and FROZEN before any outcome of that block existed (the 15th session behind
09-25 is 2026-10-16). The registration itself is `docs/analysis/686_preregistration_2026-10-04.md`;
this file is its machinery, and the two are bound by sha256 (the doc's §Freeze record carries this
file's hash; this file checks its own hash and the doc body's hash before it runs). Nothing in here
may be edited after 2026-10-16 — a changed byte fails the freeze check and the run refuses.

WHAT IT DOES (one run, $0, reads captured files only — never prod):
  STEP 0  composition of the new block, printed BEFORE any outcome is computed.
  STEP 1  features: #684's `features.py` run unchanged on the new block's captured files.
  STEP 2  frame A outcome: #684's `study.add_outcomes` (run from the gap-day close, ADR units).
  STEP 3  frame B outcome: the run from the live entry, modelled on TODAY's order path (HIGH alerts
          only, 09:31-09:44 window, rt-gap floor 9%, 1.5x-ATR ORB check, #500 market-or-skip with
          the 1.5x chase cap, 10:00 cancel) — see `entry_today` and the doc §Frame B.
  STEP 4  the 63 #684 draws + the 2 reversed leads, discovery legs FROZEN from #684's committed
          data (recomputed with seed 684 and asserted equal to results.tsv), the new block as the
          held-out leg with its own week-block permutation p (seed 686).
  STEP 5  verdicts by the rule in the doc §Pass/fail; outputs to out/.

MODES:
  (default)             the real read. REFUSES before 2026-10-17 PT, refuses if data/ lacks a SPY
                        bar dated >= 2026-10-16, refuses on any freeze-hash mismatch.
  --dry-run-old-block   proves the machinery on #684's OLD blocks only (05-01..09-03, files in
                        scripts/probes/_684/). Never opens scripts/probes/_686/data/. The frame-A
                        leg must reproduce #684's published results.tsv exactly; frame B on the old
                        blocks is today's mechanics replayed uniformly (no published number to match
                        — #684's frame B used the pre-#500 walk and any-tier first pass).
  --no-freeze-check     honoured ONLY together with --dry-run-old-block (development before the doc
                        footer exists). The real read cannot skip the freeze check.

REUSE (import by path, no copies): `_684/gate.py` (load_psv, annotate), `_684/features.py`
(main), `_684/study.py` (DRAWS, load_features, load_daily, add_outcomes, fav_mask, tercile_cuts,
diff_stat, rate, perm_p, auc), `_684/study_orb.py` (run_pass, per_feature — the four-condition bar),
`_684/study_orb_live.py` (load_bars, compute_atr14_prior, validate_orb_entry, stop_limit_buy_price,
entry_walk, load_psv, fnum). `entry_today` below is copied-with-adaptation from
`_684/check_late/recompute.py::entry_live500` (the independent critic's model of #500, which the
#684 doc's refutation of the late-alert section rests on) — that file exec()s a scratchpad path and
cannot be imported. `perm_both` and the stratified-lead functions extend `study.perm_p` to a second
tail and to strata; they add no feature.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
P684 = HERE.parent / "_684"
DATA686 = HERE / "data"
OUT = HERE / "out"
DOC = REPO / "docs" / "analysis" / "686_preregistration_2026-10-04.md"
EXTRACT = HERE / "extract.sh"

sys.path.insert(0, str(P684))
import gate            # noqa: E402  (#684)
import features        # noqa: E402  (#684)
import study           # noqa: E402  (#684)
import study_orb       # noqa: E402  (#684)
import study_orb_live  # noqa: E402  (#684)

# ── REGISTERED CONSTANTS (the doc §Registration is the prose of these) ────────────────────────
BLOCK_START = "2026-09-04"
BLOCK_END = "2026-09-25"
LAST_SESSION_NEEDED = "2026-10-16"      # 15th NYSE session after BLOCK_END (xcals XNYS; 09-07 holiday, 10-12 is a session)
EARLIEST_RUN_PT = dt.date(2026, 10, 17)  # the 10-16 daily bar lands with that evening's nightly pull
OLD_BLOCK_END = "2026-09-03"            # #684's last scan date — dry-run rows must all be <= this
SEED_684 = study.SEED                   # 684 — the frozen discovery legs
SEED_686 = 686                          # the new-block leg and the two leads
N_PERM = study.N_PERM                   # 2000
ALPHA = 0.05
RUNNER_ADR = 5.0                        # study.add_outcomes: runner5 = run_xadr >= 5 (also >= 8 reported)
THIN_RUNNERS, THIN_SIDE = 3, 8          # study.py pass bar: held-out with < 3 runners or < 8 rows a side = can't tell
# today's order path (cited in the doc §Frame B)
RT_GAP_FLOOR_PCT = 9.0                  # live_tracker._MAGNA53_MIN_GAP_PCT, 9.0 since 2026-08-19; toggle ON since 08-02
CHASE_CAP = 1.5                         # order_manager.CHASE_RISK_INFLATION_CAP default
LIMIT_BUMP = 1.002                      # order_manager.submit_entry._pick_entry: latest x 1.002
WINDOW_CLOSE = "09:45"                  # scheduler.py:1211  hour == 9 and minute < 45
SUBMIT_FLOOR = "09:31"                  # an order cannot submit before the first bar closes
CANCEL = "10:00"                        # scheduler.py:2857 — the 10:00 ET unfilled-cancel job
ATR_LOOKBACK_DAYS = study_orb_live.ATR_LOOKBACK_DAYS  # 40 calendar days (compute_atr14_prior)

# the two reversed leads (#684 VERIFIED section wording), declared sign NEGATIVE: "that third runs LESS"
LEADS = [
    ("L1", "PRE_base_range20_pct", "LOWER", "the quietest third (20-day close range as % of price) runs LESS than the rest"),
    ("L2", "CLOSE_range_xadr", "HIGHER", "the widest gap-day-range third (day range / ADR) runs LESS than the rest"),
]
ADR_CONTROL_COL = "PRE_adr20_pct"       # strata = #684 discovery terciles of ADR %


# ── freeze ───────────────────────────────────────────────────────────────────────────────────
def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def doc_body_sha(doc_text: str) -> str:
    body = doc_text.split("<!-- FREEZE -->", 1)[0]
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def freeze_check() -> list[str]:
    """Return a list of problems (empty = frozen artefacts match the doc's footer)."""
    problems: list[str] = []
    if not DOC.is_file():
        return [f"registration doc missing: {DOC}"]
    text = DOC.read_text(encoding="utf-8")
    if "<!-- FREEZE -->" not in text:
        return ["registration doc has no <!-- FREEZE --> marker"]
    footer = text.split("<!-- FREEZE -->", 1)[1]
    want = {k: (m.group(1) if (m := re.search(rf"{k}\s*sha256:\s*`?([0-9a-f]{{64}})", footer)) else None)
            for k in ("script", "extract.sh", "doc body")}
    got = {"script": sha256_file(Path(__file__).resolve()), "extract.sh": sha256_file(EXTRACT) if EXTRACT.is_file() else None,
           "doc body": doc_body_sha(text)}
    for k in want:
        if want[k] is None:
            problems.append(f"footer carries no {k} sha256")
        elif got[k] != want[k]:
            problems.append(f"{k} sha256 mismatch: footer {want[k][:12]}… vs now {got[k][:12] if got[k] else None}… — the frozen artefact was edited")
    return problems


# ── small helpers (extensions of study.perm_p; no new feature) ──────────────────────────────
def _mins(hhmm: str) -> int:
    hh, mm = hhmm.split(":")
    return int(hh) * 60 + int(mm)


def perm_both(labels: list[int], fav: list[bool], blocks: list, observed: float, rng) -> tuple[float, float]:
    """study.perm_p's shuffle (labels permuted WITHIN block), both tails from the same draws:
    (P[s >= observed], P[s <= observed])."""
    by_block: dict = defaultdict(list)
    for i, b in enumerate(blocks):
        by_block[b].append(i)
    groups = list(by_block.values())
    hi = lo = 0
    lab = list(labels)
    for _ in range(N_PERM):
        for g in groups:
            vals = [lab[i] for i in g]
            rng.shuffle(vals)
            for i, v in zip(g, vals):
                lab[i] = v
        s = study.diff_stat(lab, fav)
        if s is None:
            continue
        if s >= observed - 1e-12:
            hi += 1
        if s <= observed + 1e-12:
            lo += 1
    return hi / N_PERM, lo / N_PERM


def strat_diff(labels: list[int], grp: list[bool], strata: list) -> float | None:
    """Stratum-size-weighted mean of (rate in the named third − rate in the rest) within each stratum."""
    num = den = 0.0
    for s in set(strata):
        idx = [i for i, x in enumerate(strata) if x == s]
        a = [labels[i] for i in idx if grp[i]]
        b = [labels[i] for i in idx if not grp[i]]
        if a and b:
            num += len(idx) * (sum(a) / len(a) - sum(b) / len(b))
            den += len(idx)
    return num / den if den else None


def perm_strat(labels: list[int], grp: list[bool], blocks: list, strata: list, observed: float, rng) -> tuple[float, float]:
    """Labels shuffled within (ISO week × ADR-tercile) blocks; both tails of strat_diff."""
    by_block: dict = defaultdict(list)
    for i, b in enumerate(blocks):
        by_block[b].append(i)
    groups = list(by_block.values())
    hi = lo = 0
    lab = list(labels)
    for _ in range(N_PERM):
        for g in groups:
            vals = [lab[i] for i in g]
            rng.shuffle(vals)
            for i, v in zip(g, vals):
                lab[i] = v
        s = strat_diff(lab, grp, strata)
        if s is None:
            continue
        if s >= observed - 1e-12:
            hi += 1
        if s <= observed + 1e-12:
            lo += 1
    return hi / N_PERM, lo / N_PERM


def adr_stratum(v: float | None, cut: tuple[float, float]) -> str | None:
    if v is None:
        return None
    lo, hi = cut
    return "lowADR" if v <= lo else "highADR" if v >= hi else "midADR"


def derive_alert_unscheduled(rows: list[dict]) -> None:
    """study.main's inline derivation (not in load_features) — replicated verbatim."""
    for r in rows:
        if r.get("ALERT_expct_scheduled") in ("scheduled", "unscheduled"):
            r["ALERT_expct_unscheduled"] = 1.0 if r["ALERT_expct_scheduled"] == "unscheduled" else 0.0
        else:
            r["ALERT_expct_unscheduled"] = None


def rate_s(xs: list[int]) -> str:
    return f"{len(xs)}/{100 * study.rate(xs):.1f}%" if xs else "0/—"


# ── frame B: today's order path ──────────────────────────────────────────────────────────────
def entry_today(bars: list[tuple[str, float, float, float]], H: float, L: float, submit: str, cancel: str) -> dict:
    """TODAY's `order_manager.submit_entry` (#500 + ask-aware, both ON) replayed on stored 1-minute bars.
    Adapted from `_684/check_late/recompute.py::entry_live500` (px_mode='open'), tuple bars (hhmm,o,h,l).

    latest trade / ask at submission is approximated by the OPEN of the first bar at/after `submit`
    (the finest grain stored; stated in the doc). If that price is ABOVE the ORB high the live code
    places a marketable limit at price x 1.002 (`_pick_entry`), bounded by the chase cap
    (`_chase_cap_reason`: limit − stop <= 1.5 x (H − stop), stop = 2L − H) — beyond the cap it SKIPS
    (setup:chase_cap_exceeded, no order). A marketable limit fills at once: fill price = that open.
    If the price is at/below the ORB high the live code places the stop-limit bracket at H with limit
    `stop_limit_buy_price(H)` and the walk is `study_orb_live.entry_walk` (mirrors
    sustain_reject_replay.entry_walk) through the 10:00 cancel."""
    stop = 2 * L - H
    b0 = next((b for b in bars if b[0] >= submit), None)
    if b0 is None:
        return {"status": "abstain", "reason": "no_submit_bar"}
    px = b0[1]
    if px > H:
        lim = round(px * LIMIT_BUMP, 2)
        if lim - stop > CHASE_CAP * (H - stop):
            return {"status": "chase_cap_skip", "reason": f"price_above_orb_high_by_{(px - H) / (H - L):.2f}_orb_ranges"}
        if b0[3] <= lim:
            return {"status": "filled", "kind": "market_or_skip_limit", "px": px, "minute": b0[0]}
        return {"status": "no_entry", "reason": "marketable_limit_not_reached"}
    f = study_orb_live.entry_walk(bars, H, submit, cancel)
    if f["status"] == "filled":
        f["kind"] = "stop_limit_bracket"
    return f


def frame_b(rows: list[dict], pop: dict, bars_by_key: dict, daily: dict, dry_run: bool) -> Counter:
    """Writes orb_status / filled / entry_px / run_xadr_B / runnerB5 / runnerB8 / orderable onto each row.
    POPULATION B1 = every row with a frame-A outcome; rows today's path never orders are readable with
    filled = 0 and runnerB = 0 (status says why). B2 = the rows for which today's path PLACES an order
    (orderable == 1): HIGH, first HIGH tick before 09:45, both admission gates passed."""
    counters: Counter = Counter()
    for r in rows:
        t, d = r["ticker"], r["scan_date"]
        for k in ("orb_status", "filled", "fill_minute", "entry_px", "run_xadr_B", "runnerB5", "runnerB8"):
            r[k] = None
        r["orb_readable"] = 0
        r["orderable"] = 0
        if r.get("runner5") is None:
            r["orb_status"] = "no_15session_outcome"
            counters["unreadable_no_outcome"] += 1
            continue
        pr = pop.get((t, d), {})
        # HIGH = the ALERT row's tier, never the scan tick's: mi_ep_scan_log is written BEFORE the judge
        # override (ep_detector.py:6746 vs the W2c override at :7141), so a scan tick can be HIGH and the
        # live system still never ordered it (judge demotion), or MODERATE and ordered (judge promotion) —
        # 15 and 28 such rows in #684's own data. The order fires off the alert, so submit = the first
        # HIGH alert row's creation minute (floored to 09:31 below).
        if dry_run:
            # #684's pop.tsv carries only the FIRST live alert row's tier/time (alert rows exist from
            # 05-11; before that the scan-log PASS tick is the only record and its tier stands in).
            # DRY RUN ONLY — an approximation, stated in the doc.
            is_high = (pr.get("alert_tier") == "HIGH") or (pr.get("alert_id") == "" and d < "2026-05-11" and pr.get("score_tier") == "HIGH")
            t0 = (pr.get("alert_created_et") or "")[-5:] if pr.get("alert_tier") == "HIGH" else (pr.get("first_pass_time") or "")
        else:
            is_high = pr.get("any_high_alert") == "t"
            t0 = pr.get("first_high_alert_et") or pr.get("first_high_time") or ""

        def _zero(status: str) -> None:
            r["orb_status"] = status
            r["filled"] = 0
            r["runnerB5"], r["runnerB8"] = 0, 0
            r["orb_readable"] = 1
            counters[status.split(":")[0]] += 1

        if not is_high:
            _zero("not_high_never_ordered")
            continue
        if not t0:
            r["orb_status"] = "no_high_tick_time"
            counters["unreadable_no_high_tick_time"] += 1
            continue
        if t0 >= WINDOW_CLOSE:
            _zero("window_out_of_orb")
            continue
        submit = max(t0, SUBMIT_FLOOR)
        bk = bars_by_key.get((t, d))
        orb_bar = bk["by_hhmm"].get("09:30") if bk else None
        if orb_bar is None:
            r["orb_status"] = "no_930_bar"
            counters["unreadable_no_930_bar"] += 1
            continue
        _o, H, L = orb_bar
        db = daily.get(t, [])
        dates = [b[0] for b in db]
        i0 = dates.index(d) if d in dates else None
        prior_hlc: list = []
        prev_close = None
        if i0 is not None:
            cut = (dt.date.fromisoformat(d) - dt.timedelta(days=ATR_LOOKBACK_DAYS)).isoformat()
            prior_hlc = [(b[2], b[3], b[4]) for b in db[:i0] if b[0] >= cut]
            prev_close = db[i0 - 1][4] if i0 >= 1 else None
        atr14 = study_orb_live.compute_atr14_prior(prior_hlc)
        # pipeline order: 4b rt-gap floor (fails OPEN on a missing price/denominator), then 5 validate_orb_entry
        sb = bk["by_hhmm"].get(submit)
        if sb is not None and prev_close:
            if (sb[0] - prev_close) / prev_close * 100 < RT_GAP_FLOOR_PCT:
                _zero("gap_below_floor")
                continue
        ok, why = study_orb_live.validate_orb_entry(H, L, atr14)
        if not ok:
            _zero(f"orb_invalid:{why}")
            continue
        r["orderable"] = 1
        f = entry_today(bk["list"], H, L, submit, CANCEL)
        r["orb_status"] = f["status"] + (f":{f.get('kind') or f.get('reason')}" if (f.get("kind") or f.get("reason")) else "")
        if f["status"] == "abstain":
            counters["unreadable_abstain"] += 1
            continue
        r["orb_readable"] = 1
        if f["status"] != "filled":
            r["filled"] = 0
            r["runnerB5"], r["runnerB8"] = 0, 0
            counters[f["status"]] += 1
            continue
        r["filled"] = 1
        r["entry_px"] = f["px"]
        r["fill_minute"] = f["minute"]
        counters["filled"] += 1
        post = max((h for hhmm, o, h, l in bk["list"] if hhmm >= f["minute"]), default=None)
        fwd = db[i0 + 1:i0 + 16] if i0 is not None else []
        if post is None or len(fwd) < 15 or r.get("adr_dollar_ep") is None:
            r["orb_readable"] = 0
            counters["filled_incomplete"] += 1
            continue
        mx = max([post] + [b[2] for b in fwd])
        rb = (mx - f["px"]) / r["adr_dollar_ep"]
        r["run_xadr_B"] = rb
        r["runnerB5"], r["runnerB8"] = int(rb >= RUNNER_ADR), int(rb >= 8)
    return counters


# ── the per-draw new-block leg + verdict ─────────────────────────────────────────────────────
def held_leg(col, kind, fav, cut, held_rows, label_key, rng) -> dict:
    hr = [r for r in held_rows if r.get(col) is not None and r.get(label_key) is not None]
    if not hr:
        return {"n": 0}
    fm = study.fav_mask(hr, col, kind, fav, cut)
    labels = [int(r[label_key]) for r in hr]
    weeks = [r["iso_week"] for r in hr]
    a = [l for l, f in zip(labels, fm) if f]
    b = [l for l, f in zip(labels, fm) if not f]
    d = study.diff_stat(labels, fm)
    thin = not (sum(labels) >= THIN_RUNNERS and len(a) >= THIN_SIDE and len(b) >= THIN_SIDE)
    p_dec = p_rev = None
    if d is not None:
        p_dec, p_rev = perm_both(labels, fm, weeks, d, rng)
    return {"n": len(hr), "n_fav": len(a), "rate_fav": study.rate(a), "n_rest": len(b), "rate_rest": study.rate(b),
            "diff": d, "sign": ("+" if d > 0 else "-" if d < 0 else "0") if d is not None else "—",
            "p_dec": p_dec, "p_rev": p_rev, "thin": thin, "runners": sum(labels)}


def verdict_for(disc: dict, held: dict, block_runners: int, frame: str = "A") -> tuple[str, bool]:
    """Returns (verdict, passes_684_bar). Rule = doc §Pass/fail. Frame B carries no discovery leg, so it
    can reach HOLDS but never CONFIRMED."""
    legs_ok = (disc.get("p_disc") is not None and disc["p_disc"] < ALPHA and (disc.get("diff") or 0) > 0
               and disc.get("drop_week_p") is not None and disc["drop_week_p"] < ALPHA and (disc.get("drop_week_diff") or 0) > 0
               and disc.get("drop_two_p") is not None and disc["drop_two_p"] < ALPHA and (disc.get("drop_two_diff") or 0) > 0)
    if held.get("n", 0) == 0:
        return "no data", False
    if held.get("diff") is None:
        return "no data (every row on one side of the cut)", False
    if block_runners < THIN_RUNNERS or held["thin"]:
        return "can't tell (thin)", False
    pass684 = legs_ok and held["diff"] > 0
    if held["diff"] > 0 and held["p_dec"] < ALPHA:
        if frame != "A":
            return "HOLDS (frame B — report only, no discovery leg)", pass684
        return ("CONFIRMED" if legs_ok else "HOLDS (new lead — did not clear #684's discovery leg; report only)"), pass684
    if held["diff"] < 0 and held["p_rev"] < ALPHA:
        return "AGAINST", pass684
    return "can't tell", pass684


def lead_leg(lead, rows, cut, adr_cut, rng, label_key="runner5") -> dict:
    """One reversed lead on one row set: raw third-vs-rest difference and the ADR-controlled
    (stratified) difference, each with both permutation tails. Declared sign NEGATIVE."""
    code, col, side, _ = lead
    rr = [r for r in rows if r.get(col) is not None and r.get(ADR_CONTROL_COL) is not None and r.get(label_key) is not None]
    if not rr:
        return {"n": 0}
    lo, hi = cut
    grp = [(r[col] <= lo) if side == "LOWER" else (r[col] >= hi) for r in rr]
    labels = [int(r[label_key]) for r in rr]
    weeks = [r["iso_week"] for r in rr]
    strata = [adr_stratum(r[ADR_CONTROL_COL], adr_cut) for r in rr]
    a = [l for l, g in zip(labels, grp) if g]
    b = [l for l, g in zip(labels, grp) if not g]
    d_raw = study.diff_stat(labels, grp)
    p_raw_hi, p_raw_lo = perm_both(labels, grp, weeks, d_raw, rng) if d_raw is not None else (None, None)
    d_ctl = strat_diff(labels, grp, strata)
    p_ctl_hi, p_ctl_lo = perm_strat(labels, grp, list(zip(weeks, strata)), strata, d_ctl, rng) if d_ctl is not None else (None, None)
    thin = not (sum(labels) >= THIN_RUNNERS and len(a) >= THIN_SIDE and len(b) >= THIN_SIDE)
    return {"n": len(rr), "n_third": len(a), "rate_third": study.rate(a), "n_rest": len(b), "rate_rest": study.rate(b),
            "diff_raw": d_raw, "p_raw_less": p_raw_lo, "p_raw_more": p_raw_hi,
            "diff_ctl": d_ctl, "p_ctl_less": p_ctl_lo, "p_ctl_more": p_ctl_hi, "thin": thin, "runners": sum(labels)}


def lead_verdict(disc_ctl: dict, dw: dict, dn: dict, held: dict, block_runners: int) -> str:
    legs_ok = (disc_ctl.get("diff_ctl") is not None and disc_ctl["diff_ctl"] < 0 and disc_ctl["p_ctl_less"] < ALPHA
               and dw.get("diff_ctl") is not None and dw["diff_ctl"] < 0 and dw["p_ctl_less"] < ALPHA
               and dn.get("diff_ctl") is not None and dn["diff_ctl"] < 0 and dn["p_ctl_less"] < ALPHA)
    if held.get("n", 0) == 0 or held.get("diff_ctl") is None:
        return "no data"
    if block_runners < THIN_RUNNERS or held["thin"]:
        return "can't tell (thin)"
    if held["diff_ctl"] < 0 and held["p_ctl_less"] < ALPHA:
        return "CONFIRMED" if legs_ok else "HOLDS (ADR-controlled discovery leg did not clear — report only)"
    if held["diff_ctl"] > 0 and held["p_ctl_more"] < ALPHA:
        return "AGAINST"
    return "can't tell"


def labelled_in_block(start: str, end: str) -> list[tuple[str, str]]:
    """Operator-labelled EPs (docs/methodology/operator_labelled_eps.md table) dated inside the block."""
    p = REPO / "docs" / "methodology" / "operator_labelled_eps.md"
    if not p.is_file():
        return []
    out = []
    for m in re.finditer(r"^\|\s*\*\*([A-Z.]+)\*\*\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|", p.read_text(encoding="utf-8"), re.M):
        if start <= m.group(2) <= end:
            out.append((m.group(1), m.group(2)))
    return out


# ── main ─────────────────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--dry-run-old-block", action="store_true")
    ap.add_argument("--no-freeze-check", action="store_true")
    args = ap.parse_args()
    dry = args.dry_run_old_block
    OUT.mkdir(exist_ok=True)
    tag = "dryrun" if dry else "686"

    # calendar: confirm the hardcoded dates against the NYSE calendar when the library is present
    try:
        import exchange_calendars as xcals
        s = [x.strftime("%Y-%m-%d") for x in xcals.get_calendar("XNYS").sessions_in_range("2026-09-01", "2026-11-30")]
        fifteenth = s[s.index(BLOCK_END) + 15]
        assert fifteenth == LAST_SESSION_NEEDED, f"calendar says the 15th session after {BLOCK_END} is {fifteenth}, not {LAST_SESSION_NEEDED}"
        block_sessions = [x for x in s if BLOCK_START <= x <= BLOCK_END]
    except ImportError:
        block_sessions = None
        print("WARNING: exchange_calendars not installed — using the hardcoded calendar facts", file=sys.stderr)

    # gates
    if not dry:
        today_pt = dt.datetime.now(ZoneInfo("America/Los_Angeles")).date()
        if today_pt < EARLIEST_RUN_PT:
            print(f"REFUSED: the block's 15th session is {LAST_SESSION_NEEDED}; earliest read is {EARLIEST_RUN_PT} PT (today {today_pt}). "
                  f"Use --dry-run-old-block to exercise the machinery on #684's old blocks.", file=sys.stderr)
            return 3
    if args.no_freeze_check and not dry:
        print("REFUSED: --no-freeze-check is honoured only with --dry-run-old-block.", file=sys.stderr)
        return 2
    if not args.no_freeze_check:
        probs = freeze_check()
        if probs:
            print("REFUSED: freeze check failed —\n  " + "\n  ".join(probs), file=sys.stderr)
            return 2

    out: list[str] = []
    p = out.append
    p(f"#686 PRE-REGISTERED READ — mode: {'DRY RUN on #684 old blocks (05-01..09-03)' if dry else f'THE READ, block {BLOCK_START}..{BLOCK_END}'}")
    p(f"registration: {DOC.relative_to(REPO)}   script sha256 {sha256_file(Path(__file__).resolve())}")
    p(f"seeds: discovery legs {SEED_684} (frozen, #684), new-block leg + leads {SEED_686}; permutation draws {N_PERM}; alpha {ALPHA}; runner >= {RUNNER_ADR:g} ADR")
    p("")

    # ── frozen #684 data (discovery + old held-out) ──────────────────────────────────────────
    study.HERE = P684
    rows684 = study.load_features()
    daily684 = study.load_daily()
    study.add_outcomes(rows684, daily684)
    derive_alert_unscheduled(rows684)
    scored684 = [r for r in rows684 if r["runner5"] is not None]
    assert max(r["scan_date"] for r in rows684) <= OLD_BLOCK_END, "the #684 files hold rows past 09-03 — not the frozen population"
    disc684 = [r for r in scored684 if r["block"] == "DISCOVERY"]
    adr_cut = study.tercile_cuts([r[ADR_CONTROL_COL] for r in disc684 if r.get(ADR_CONTROL_COL) is not None])

    # ── the new block (or, in a dry run, #684's own held-out) ───────────────────────────────
    if dry:
        new_rows = [r for r in scored684 if r["block"] == "HELD-OUT"]
        pop_rows = study_orb_live.load_psv(P684 / "pop.tsv")
        study_orb_live.HERE = P684
        bars = study_orb_live.load_bars()
        daily_new = daily684
        rows_new_all = [r for r in rows684 if r["block"] == "HELD-OUT"]
    else:
        for f in ("pop.tsv", "hist.tsv", "scores.tsv", "themes.tsv", "prior.tsv", "orb.tsv", "regime.tsv", "sector.tsv", "daily.tsv.gz", "live_entry_bars.tsv"):
            if not (DATA686 / f).is_file():
                print(f"REFUSED: data/{f} missing — run extract.sh first (it refuses before {EARLIEST_RUN_PT} too).", file=sys.stderr)
                return 4
        features.HERE = DATA686
        study.HERE = DATA686
        study_orb_live.HERE = DATA686
        daily_new = study.load_daily()
        spy = daily_new.get("SPY", [])
        if not spy or spy[-1][0] < LAST_SESSION_NEEDED:
            print(f"REFUSED: data/daily.tsv.gz has no SPY session dated >= {LAST_SESSION_NEEDED} (last {spy[-1][0] if spy else None}) — the block has not matured in the pulled data.", file=sys.stderr)
            return 4
        features.main()                       # STEP 1 — #684's feature code, unchanged, on the new block's files
        rows_new_all = study.load_features()
        assert all(BLOCK_START <= r["scan_date"] <= BLOCK_END for r in rows_new_all), "a row outside the registered block is in data/pop.tsv"
        study.add_outcomes(rows_new_all, daily_new)   # STEP 2 — frame A
        derive_alert_unscheduled(rows_new_all)
        new_rows = [r for r in rows_new_all if r["runner5"] is not None]
        pop_rows = study_orb_live.load_psv(DATA686 / "pop.tsv")
        bars = study_orb_live.load_bars()
    pop = {(r["ticker"], r["scan_date"]): r for r in pop_rows}

    # ── STEP 0 composition (written before any outcome line below) ──────────────────────────
    p("STEP 0 — COMPOSITION of the block (no outcome in this section)")
    by_date = Counter(r["scan_date"] for r in rows_new_all)
    p(f"  rows {len(rows_new_all)} on {len(by_date)} scan dates" + (f" (calendar sessions in block: {len(block_sessions)})" if (block_sessions and not dry) else "") + f": {dict(sorted(by_date.items()))}")
    n_alert = sum(int(r["alerted"]) for r in rows_new_all)
    if dry:
        def _hi(pr, d):
            return (pr.get("alert_tier") == "HIGH") or (pr.get("alert_id") == "" and d < "2026-05-11" and pr.get("score_tier") == "HIGH")

        def _t0(pr):
            return (pr.get("alert_created_et") or "")[-5:] if pr.get("alert_tier") == "HIGH" else (pr.get("first_pass_time") or "")
    else:
        def _hi(pr, d):
            return pr.get("any_high_alert") == "t"

        def _t0(pr):
            return pr.get("first_high_alert_et") or pr.get("first_high_time") or ""
    n_high = sum(1 for r in rows_new_all if _hi(pop.get((r["ticker"], r["scan_date"]), {}), r["scan_date"]))
    n_high_in = sum(1 for r in rows_new_all if _hi(pop.get((r["ticker"], r["scan_date"]), {}), r["scan_date"]) and (_t0(pop.get((r["ticker"], r["scan_date"]), {})) or "99") < WINDOW_CLOSE)
    n_scan_high_not_alert_high = sum(1 for r in rows_new_all if pop.get((r["ticker"], r["scan_date"]), {}).get("score_tier") == "HIGH" and not _hi(pop.get((r["ticker"], r["scan_date"]), {}), r["scan_date"]))
    p(f"  alerted (scan pass, any tier) {n_alert}; scored-not-alerted {len(rows_new_all) - n_alert}; HIGH (alert row tier, post-judge) {n_high}; HIGH with its first HIGH alert before {WINDOW_CLOSE} (orderable window) {n_high_in}; "
      f"scan-tick HIGH but no HIGH alert (judge demotion — never ordered) {n_scan_high_not_alert_high}")
    p(f"  era: {dict(Counter(r['era'] for r in rows_new_all))}   ISO weeks: {dict(Counter(r['iso_week'] for r in rows_new_all))}")
    gaps = [r["PRE_gap_pct_scan"] for r in rows_new_all if r.get("PRE_gap_pct_scan") is not None]
    scs = [r["ep_score"] for r in rows_new_all if r.get("ep_score") is not None]
    p(f"  median gap at the scan {statistics.median(gaps):.1f}%; median ep_score {statistics.median(scs):.0f}; 09:45 minute coverage {sum(1 for r in rows_new_all if r.get('O945_covered') == 1)} of {len(rows_new_all)}; "
      f"rows without 20 prior sessions (no bar features) {sum(1 for r in rows_new_all if r.get('n_pre_bars', 0) < 21)}")
    cens = [r for r in rows_new_all if r["runner5"] is None]
    p(f"  rows without a 15-session outcome (censored, counted): {len(cens)} " + (", ".join(f"{r['ticker']} {r['scan_date']}" for r in cens) if cens else ""))
    lab = labelled_in_block(BLOCK_START if not dry else "2026-08-15", BLOCK_END if not dry else OLD_BLOCK_END)
    p(f"  operator-labelled EPs dated inside the block (operator_labelled_eps.md at run time): {lab if lab else 'none'}")
    p("")

    # ── frame A on the new block ─────────────────────────────────────────────────────────────
    block_runners = sum(r["runner5"] for r in new_rows)
    p(f"FRAME A (run from the gap-day close): n {len(new_rows)}, runners >= 5 ADR {block_runners} ({100 * study.rate([r['runner5'] for r in new_rows]):.1f}%), >= 8 ADR {sum(r['runner8'] for r in new_rows)}; "
      f"alerted n {sum(int(r['alerted']) for r in new_rows)} runners {sum(r['runner5'] for r in new_rows if r['alerted'])}; not-alerted n {sum(1 for r in new_rows if not r['alerted'])} runners {sum(r['runner5'] for r in new_rows if not r['alerted'])}")
    if block_runners < THIN_RUNNERS:
        p(f"  ⚠ fewer than {THIN_RUNNERS} runners in the block — by the registered rule EVERY verdict below is 'can't tell (thin)'; the block cannot carry a sign.")
    p("")

    # ── frame B ──────────────────────────────────────────────────────────────────────────────
    cB = frame_b(new_rows, pop, bars, daily_new, dry)
    b1 = [r for r in new_rows if r["orb_readable"] and r["runnerB5"] is not None]
    b2 = [r for r in b1 if r["orderable"] == 1]
    p(f"FRAME B (run from the live entry, TODAY's order path{' — DRY RUN: HIGH = the FIRST alert row tier only (pre-05-11: the scan PASS tick), submit = that alert minute' if dry else ''}):")
    p(f"  status counts: {dict(cB)}")
    p(f"  B1 (every row; never-ordered rows = 0): n {len(b1)}, runners_B {sum(r['runnerB5'] for r in b1)};   B2 (today's path places an order): n {len(b2)}, filled {sum(r['filled'] for r in b2)}, runners_B {sum(r['runnerB5'] for r in b2)}")
    fills = [r for r in b2 if r["filled"] == 1]
    p(f"  fills by kind: {dict(Counter(r['orb_status'].split(':')[1] for r in fills if ':' in r['orb_status']))}; chase-cap skips {sum(1 for r in b2 if r['orb_status'].startswith('chase_cap_skip'))}; no_entry {sum(1 for r in b2 if r['orb_status'].startswith('no_entry'))}")
    a_runners_unfilled = [r for r in new_rows if r["runner5"] and r["orb_readable"] and r["filled"] == 0]
    p(f"  frame-A runners today's path never buys: {len(a_runners_unfilled)} of {block_runners} — by status {dict(Counter(r['orb_status'].split(':')[0] for r in a_runners_unfilled))}")
    p("")

    # ── STEP 4: the 63 draws — frozen discovery legs + the new held-out leg ─────────────────
    # run_pass (study_orb) = study.main's loop: same DRAWS order, same rng sequence (seed 684) → the
    # discovery legs reproduce results.tsv exactly; the held-out leg is whatever rows carry block HELD-OUT.
    results, disc_rows, held_rows, best_week, best_two = study_orb.run_pass(disc684 + new_rows, "runner5", "runner8", SEED_684)
    pub: dict[str, dict] = {}
    with (P684 / "results.tsv").open() as fh:
        cols = fh.readline().rstrip("\n").split("\t")
        for line in fh:
            rr = dict(zip(cols, line.rstrip("\n").split("\t")))
            pub[rr["feature"]] = rr
    mism = []
    for res in results:
        pr = pub.get(res["feature"])
        if pr is None or res.get("verdict") == "no data":
            continue
        for k in ("n_disc", "n_fav", "p_disc", "drop_week_p", "drop_two_p"):
            a, b = res.get(k), pr.get(k)
            if a is None or b in (None, ""):
                continue
            if abs(float(a) - float(b)) > 1e-4:
                mism.append(f"{res['feature']}.{k}: recomputed {a} vs published {b}")
        if dry:
            for k in ("held_n_fav", "held_n_rest", "held_sign"):
                if str(res.get(k)) != str(pr.get(k)):
                    mism.append(f"{res['feature']}.{k}: recomputed {res.get(k)} vs published {pr.get(k)}")
            if res.get("verdict", "").split(" ⚠")[0] != pr.get("verdict", "").split(" ⚠")[0]:
                mism.append(f"{res['feature']}.verdict: recomputed [{res.get('verdict')}] vs published [{pr.get('verdict')}]")
    p(f"FROZEN DISCOVERY LEGS vs #684 results.tsv (n_disc, n_fav, p_disc, drop-week p, drop-two p{', held-out n/sign/verdict' if dry else ''}): "
      f"{'IDENTICAL on all ' + str(len([r for r in results if r.get('verdict') != 'no data'])) + ' bar-tested draws' if not mism else str(len(mism)) + ' MISMATCHES'}")
    for m in mism:
        p("  " + m)
    if mism:
        p("  ⚠ the discovery legs did not reproduce — the read is INVALID; stop here.")
    p(f"discovery best week {best_week}, best two names {best_two} (frozen, #684)")
    p("")

    cuts: list[tuple] = []
    rng_new = __import__("random").Random(SEED_686)
    verdict_rows: list[dict] = []
    header = ("feature | when | favourable | FROZEN #684 disc: n, fav rate vs rest, p | legs(3)(4) ok | NEW BLOCK frame A: fav n/rate vs rest n/rate | sign | p(declared) | p(reverse) | #684 bar (sign-only held-out) | VERDICT A"
              " || frame B1: fav vs rest, sign, p(dec) | verdict B1 || frame B2: fav vs rest, sign, p(dec) | verdict B2")
    p("PER-DRAW (cut points = #684 DISCOVERY terciles, applied unchanged; rates = share >= 5 ADR):")
    p(header)
    for (col, kind, fav, when, name), res in zip(study.DRAWS, results):
        dr = [r for r in disc684 if r.get(col) is not None]
        if len(dr) < 30:
            p(f"{col} | {when} | {fav} | no data")
            continue
        cut = study.tercile_cuts([r[col] for r in dr]) if kind == "cont" else None
        cuts.append((col, kind, fav, when, name, cut))
        legs_ok = (res["p_disc"] < ALPHA and res["diff"] > 0 and res["drop_week_p"] < ALPHA and res["drop_week_diff"] > 0
                   and res["drop_two_p"] < ALPHA and res["drop_two_diff"] > 0)
        hA = held_leg(col, kind, fav, cut, new_rows, "runner5", rng_new)
        vA, pass684 = verdict_for(res, hA, block_runners)
        hB1 = held_leg(col, kind, fav, cut, b1, "runnerB5", rng_new)
        vB1, _ = verdict_for({"p_disc": None}, hB1, sum(r["runnerB5"] for r in b1), frame="B1")
        hB2 = held_leg(col, kind, fav, cut, b2, "runnerB5", rng_new)
        vB2, _ = verdict_for({"p_disc": None}, hB2, sum(r["runnerB5"] for r in b2), frame="B2")

        def fmt(h):
            if h.get("n", 0) == 0 or h.get("diff") is None:
                return f"{h.get('n_fav', 0)} vs {h.get('n_rest', 0)} | — | — | —"
            return (f"{h['n_fav']}/{100 * h['rate_fav']:.1f}% vs {h['n_rest']}/{100 * h['rate_rest']:.1f}% | {h['sign']}{' thin' if h['thin'] else ''} | "
                    f"{h['p_dec']:.3f} | {h['p_rev']:.3f}")

        def fmtb(h, v):
            if h.get("n", 0) == 0 or h.get("diff") is None:
                return f"{h.get('n_fav', 0)} vs {h.get('n_rest', 0)} | " + v
            return f"{h['n_fav']}/{100 * h['rate_fav']:.1f}% vs {h['n_rest']}/{100 * h['rate_rest']:.1f}%, {h['sign']}{' thin' if h['thin'] else ''}, p {h['p_dec']:.3f} | {v}"
        p(f"{col} | {when} | {fav} | {res['n_disc']}, {100 * res['rate_fav']:.1f}% vs {100 * res['rate_rest']:.1f}%, p {res['p_disc']:.3f} | {'yes' if legs_ok else 'no'} | "
          f"{fmt(hA)} | {'PASS' if pass684 else 'no'} | {vA} || {fmtb(hB1, vB1)} || {fmtb(hB2, vB2)}")
        verdict_rows.append({"feature": col, "when": when, "name": name, "fav": fav, "cut": cut, "disc_p": res["p_disc"], "disc_legs_ok": legs_ok,
                             "A": hA, "verdict_A": vA, "pass_684_bar": pass684, "B1": hB1, "verdict_B1": vB1, "B2": hB2, "verdict_B2": vB2})
    p("")

    # ── the two reversed leads ───────────────────────────────────────────────────────────────
    p("THE TWO REVERSED LEADS (declared: that third runs LESS; ADR % controlled by stratifying on #684 discovery ADR-% terciles "
      f"{adr_cut[0]:.2f} / {adr_cut[1]:.2f} and shuffling within ISO week × ADR stratum). 'less' p = P[diff <= observed].")
    p("lead | third defined as | FROZEN #684 discovery: raw third vs rest, p(less) | controlled diff, p(less) | drop-week ctl p | drop-two ctl p | NEW BLOCK: raw third vs rest, p(less) | controlled diff, p(less) | VERDICT")
    rng_lead = __import__("random").Random(SEED_686 + 1)
    lead_rows: list[dict] = []
    for lead in LEADS:
        code, col, side, text = lead
        cut = study.tercile_cuts([r[col] for r in disc684 if r.get(col) is not None])
        d_all = lead_leg(lead, disc684, cut, adr_cut, rng_lead)
        d_w = lead_leg(lead, [r for r in disc684 if r["iso_week"] != best_week], cut, adr_cut, rng_lead)
        d_n = lead_leg(lead, [r for r in disc684 if r["ticker"] not in best_two], cut, adr_cut, rng_lead)
        h = lead_leg(lead, new_rows, cut, adr_cut, rng_lead)
        v = lead_verdict(d_all, d_w, d_n, h, block_runners)
        third = f"{col} {'<=' if side == 'LOWER' else '>='} {cut[0] if side == 'LOWER' else cut[1]:.4g}"

        def lf(x):
            if x.get("n", 0) == 0 or x.get("diff_raw") is None:
                return "— | —"
            ctl = f"{100 * x['diff_ctl']:+.1f}pp, p {x['p_ctl_less']:.3f}" if x.get("diff_ctl") is not None else "—"
            return f"{x['n_third']}/{100 * x['rate_third']:.1f}% vs {x['n_rest']}/{100 * x['rate_rest']:.1f}%, p {x['p_raw_less']:.3f} | {ctl}"
        p(f"{code} {text} | {third} | {lf(d_all)} | {d_w.get('p_ctl_less', float('nan')):.3f} | {d_n.get('p_ctl_less', float('nan')):.3f} | {lf(h)}{' thin' if h.get('thin') else ''} | {v}")
        lead_rows.append({"lead": code, "col": col, "third": third, "disc": d_all, "drop_week": d_w, "drop_two": d_n, "new": h, "verdict": v})
    p("")

    # ── summary for his ruling (counts only; the one-paragraph proposal is written by hand from these) ─
    conf = [v["feature"] for v in verdict_rows if v["verdict_A"] == "CONFIRMED"] + [l["lead"] for l in lead_rows if l["verdict"] == "CONFIRMED"]
    holds = [v["feature"] for v in verdict_rows if v["verdict_A"].startswith("HOLDS")] + [l["lead"] for l in lead_rows if l["verdict"].startswith("HOLDS")]
    against = [v["feature"] for v in verdict_rows if v["verdict_A"] == "AGAINST"] + [l["lead"] for l in lead_rows if l["verdict"] == "AGAINST"]
    n_draws = len(verdict_rows) + len(lead_rows)
    p(f"SUMMARY (frame A): draws tested {n_draws}; CONFIRMED {len(conf)} {conf}; HOLDS-only (new leads, chance band ≈ {ALPHA * n_draws:.1f} at p<0.05) {len(holds)} {holds}; AGAINST {len(against)} {against}; "
      f"'none hold' = zero CONFIRMED → {'TRUE' if not conf else 'FALSE'}")
    p(f"SUMMARY (frame B): B1 HOLDS {[v['feature'] for v in verdict_rows if v['verdict_B1'].startswith('HOLDS')]}; B2 HOLDS {[v['feature'] for v in verdict_rows if v['verdict_B2'].startswith('HOLDS')]} "
      f"(frame B carries no discovery leg → HOLDS-only; a frame-A CONFIRMED feature is named to him with its frame-B reading beside it)")
    text = "\n".join(out) + "\n"
    (OUT / f"{tag}_results_out.txt").write_text(text)
    with (OUT / f"{tag}_cuts.tsv").open("w") as fh:
        fh.write("feature\tkind\tfavourable\twhen\tname\tcut_lo\tcut_hi\n")
        for col, kind, fav, when, name, cut in cuts:
            fh.write(f"{col}\t{kind}\t{fav}\t{when}\t{name}\t{'' if cut is None else f'{cut[0]:.6g}'}\t{'' if cut is None else f'{cut[1]:.6g}'}\n")
    with (OUT / f"{tag}_outcomes.tsv").open("w") as fh:
        fh.write("ticker\tscan_date\talerted\torderable\torb_status\tfilled\tfill_minute\tentry_px\trun_xadr\trunner5\trun_xadr_B\trunnerB5\n")
        for r in new_rows:
            rb = "" if r.get("run_xadr_B") is None else f"{r['run_xadr_B']:.3f}"
            fh.write(f"{r['ticker']}\t{r['scan_date']}\t{int(r['alerted'])}\t{r['orderable']}\t{r['orb_status']}\t{r.get('filled')}\t{r.get('fill_minute') or ''}\t{r.get('entry_px') or ''}\t"
                     f"{r['run_xadr']:.3f}\t{r['runner5']}\t{rb}\t{r.get('runnerB5')}\n")
    (OUT / f"{tag}_summary.json").write_text(json.dumps({
        "mode": "dry-run-old-block" if dry else "read", "block": [BLOCK_START, BLOCK_END] if not dry else ["2026-08-15", OLD_BLOCK_END],
        "n_rows": len(rows_new_all), "n_scored": len(new_rows), "runners5": block_runners, "frozen_legs_reproduced": not mism,
        "confirmed": conf, "holds_only": holds, "against": against,
        "verdicts_A": {v["feature"]: v["verdict_A"] for v in verdict_rows}, "leads": {l["lead"]: l["verdict"] for l in lead_rows},
        "verdicts_B1": {v["feature"]: v["verdict_B1"] for v in verdict_rows}, "verdicts_B2": {v["feature"]: v["verdict_B2"] for v in verdict_rows},
        "frame_b_status": dict(cB)}, indent=1, default=str))
    print(text)
    return 0 if not mism else 5


if __name__ == "__main__":
    sys.exit(main())
