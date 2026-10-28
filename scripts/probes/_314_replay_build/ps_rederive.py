#!/usr/bin/env python3
"""#314 replay — the INDEPENDENT re-derivation (plan §Independent re-derivation): from episodes.tsv ALONE, with pandas / numpy and
nothing of the runner's code, recompute rule (c)'s decisions (and refuse if they differ from the file's), then per population n, mean R,
the month-block interval (2,000 resamples, seed 702 mixed with the row's key by crc32), ADR P&L, the tail spread, the costs, the
three ways, the beside rows and each read's difference with its interval — written as JSON for the runner to compare (VERDICT MATCH).

  python ps_rederive.py <episodes.tsv> <out.json>
"""
import json
import sys
import zlib

import numpy as np
import pandas as pd

N_FLOOR, DRAWS, SEED = 30, 2000, 702
POPS, READ_POPS = ("P1", "P2", "P2small"), ("P1", "P2")


# the plan's consequence grid (§Consequence fixed now), P1 verdict x P2 verdict -> the cell
GRID = {
    ("PASS", "PASS"): "proposal: a P2 shadow lane with its own borrow check (the $250M floor is his signed rule: CHANGE_PROCESS); P1 = the candidate for the next rung (paper is his call)",
    ("PASS", "CAN'T TELL"): "P1 the candidate for the next rung; P2: no lane, the shortfall named",
    ("PASS", "FAIL"): "P1 the candidate for the next rung; P2: no lane, 'small caps as floored here FAIL' reported with n",
    ("CAN'T TELL", "PASS"): "P1: the live shadow continues unchanged, no rung; P2: the lane proposal",
    ("CAN'T TELL", "CAN'T TELL"): "nothing changes anywhere; both shortfalls named; no re-read without a dated event",
    ("CAN'T TELL", "FAIL"): "P1: nothing; P2: the FAIL reported with n, no lane",
    ("FAIL", "PASS"): "P1: the shadow keeps running, the FAIL goes to him with n (retiring the lane is his call); P2: the lane proposal, flagged that the floored version failed",
    ("FAIL", "CAN'T TELL"): "P1 FAIL to him; P2: nothing",
    ("FAIL", "FAIL"): "both FAILs to him with n; the setup review carries them; nothing live changes",
}


def load(path):
    df = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
    return df.to_dict("records")


def f(x):
    return None if x in ("", None, "None", "nan") else float(x)


def close_date(e, lab):
    st = e.get(f"{lab}_status", "")
    if st in ("settled", "invalidated", "expired_untriggered"):
        return e.get(f"{lab}_exit_date") or None
    if st == "void_bad_geometry":
        return e.get(f"{lab}_entry_date") or e["d0"]
    if st in ("degraded", "ended_mid_walk", "open_at_end"):
        return e.get("last_walked_date") or None
    return None


def rule_c(rows, key_col, lab):
    """One open episode per key: a climax whose key's earlier episode closes after D0 (or never) is rejected."""
    out, until = {}, {}
    for e in sorted(rows, key=lambda q: (q["d0"], q["ticker"])):
        k = e[key_col]
        u = until.get(k)
        ident = (e["population"], e["ticker"], e["d0"])
        if u is not None and (u == "" or u > e["d0"]):
            out[ident] = "episode_already_open"
            continue
        out[ident] = "admitted"
        c = close_date(e, lab)
        until[k] = c if c is not None else ""
    return out


def counted(e, lab="r5", dec="decision"):
    return (e.get(dec) == "admitted" and e.get(f"{lab}_status") == "settled" and e.get("void_adjustment_event") != "1"
            and e.get("distribution_class") != "distribution")


def rng(key):
    return np.random.default_rng([SEED, zlib.crc32(key.encode())])


def block_ci(vals, months, key):
    v = np.asarray(vals, float)
    if not len(v):
        return float("nan"), float("nan")
    u, inv = np.unique(np.asarray(months), return_inverse=True)
    m = len(u)
    s = np.bincount(inv, weights=v, minlength=m)
    c = np.bincount(inv, minlength=m).astype(float)
    idx = rng(key).integers(0, m, size=(DRAWS, m))
    means = s[idx].sum(1) / c[idx].sum(1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def diff_interval(va, ma, vb, mb, key):
    va, vb = np.asarray(va, float), np.asarray(vb, float)
    if not len(va) or not len(vb):
        return float("nan"), float("nan"), float("nan"), 0
    months = np.unique(np.concatenate([np.asarray(ma), np.asarray(mb)]))
    m = len(months)
    ia, ib = np.searchsorted(months, ma), np.searchsorted(months, mb)
    sa, ca = np.bincount(ia, weights=va, minlength=m), np.bincount(ia, minlength=m).astype(float)
    sb, cb = np.bincount(ib, weights=vb, minlength=m), np.bincount(ib, minlength=m).astype(float)
    g = rng(key)
    out, redraw = [], 0
    while len(out) < DRAWS:
        i = g.integers(0, m, size=m)
        na, nb = ca[i].sum(), cb[i].sum()
        if na == 0 or nb == 0:
            redraw += 1
            continue
        out.append(sa[i].sum() / na - sb[i].sum() / nb)
    d = np.asarray(out)
    return float(va.mean() - vb.mean()), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5)), redraw


def tail(rows, rf, bar):
    hit = [e for e in rows if f(e.get(rf)) is not None and f(e[rf]) >= bar]
    c, mo = len({e["company_key"] for e in hit}), len({e["r5_entry_month"] for e in hit})
    return {"trades": len(hit), "companies": c, "months": mo, "pass": len(hit) >= 3 and c >= 3 and mo >= 3}


def verdict(rows, key, rf="r5_r", pf="r5_pnl_adr"):
    r = [f(e[rf]) for e in rows]
    n = len(r)
    mean = float(np.mean(r)) if n else float("nan")
    lo, hi = block_ci(r, [e["r5_entry_month"] for e in rows], key) if n else (float("nan"), float("nan"))
    pn = [f(e.get(pf)) for e in rows if f(e.get(pf)) is not None]
    mp = float(np.mean(pn)) if pn else float("nan")
    t = tail(rows, rf, 3.0)
    if n >= N_FLOOR and lo > 0 and mp > 0 and t["pass"]:
        v = "PASS"
    elif n >= N_FLOOR and hi < 0:
        v = "FAIL"
    elif n >= N_FLOOR and lo > 0:
        v = "CAN'T TELL (positive, no tail)" if not t["pass"] else "CAN'T TELL (positive, ADR P&L not > 0)"
    else:
        v = "CAN'T TELL"
    return {"n": n, "mean_r": mean, "lo": lo, "hi": hi, "mean_pnl_adr": mp, "tail": t, "verdict": v}


def put(nums, pre, v):
    nums[f"{pre}:n"] = v["n"]
    for k in ("mean_r", "lo", "hi", "mean_pnl_adr"):
        nums[f"{pre}:{k}"] = v[k]
    for k in ("trades", "companies", "months"):
        nums[f"{pre}:tail_{k}"] = v["tail"][k]
    nums[f"{pre}:verdict"] = v["verdict"]


def read_v(d, lo, hi, na, nb, nu, ns):
    if ns and nu > 0.5 * ns:
        return "coverage-bound"
    if na < N_FLOOR or nb < N_FLOOR:
        return "CAN'T TELL"
    return "separates in HIS direction" if lo > 0 else "separates AGAINST him" if hi < 0 else "CAN'T TELL"


def put_read(nums, pre, r):
    for k, v in r.items():
        nums[f"{pre}:{k}"] = v


def groups():
    def num(e, c):
        return f(e.get(c))
    return {
        "read2": lambda e: None if num(e, "pause_count") is None else ("A" if num(e, "pause_count") <= 2 else "B"),
        "read2_ratio": lambda e: None if num(e, "pause_ratio") is None else ("A" if num(e, "pause_ratio") <= 0.20 else "B"),
        "read3": lambda e: {"present": "A", "absent": "B"}.get(e.get("news3_group")),
        "read4": lambda e: {"no_swing": "A", "swing": "B"}.get(e.get("swing_group")),
        "read4_any": lambda e: {"no_swing": "A", "swing": "B"}.get(e.get("swing_group_any")),
        "read5": lambda e: {"ge20": "A", "lt20": "B"}.get(e.get("dilution_bucket")),
        "read5_itm": lambda e: (None if e.get("dilution_bucket") not in ("ge20", "lt20") or num(e, "dilution_ratio_itm") is None
                                else ("A" if num(e, "dilution_ratio_itm") >= 0.20 else "B")),
    }


def main(src, dst):
    eps = load(src)
    for pop in POPS:
        sub = [e for e in eps if e["population"] == pop]
        checks = [("decision", sub, "r5")]
        if pop in READ_POPS:
            checks += [("decision_jump_removed", [e for e in sub if e.get("jump_unevidenced") != "1"], "r5"),
                       ("decision_mna", [e for e in sub if e.get("mna_flag") != "flagged"], "r5"),
                       ("decision_8k", [e for e in sub if e.get("earnings_flag") == "none"], "e5")]
        if pop == "P1":
            checks.append(("decision_cap_floor", [e for e in sub if f(e.get("cap")) is not None and f(e["cap"]) >= 250_000_000], "r5"))
        for col, rows, lab in checks:
            dec = rule_c(rows, "company_key", lab)
            bad = [k for k, v in dec.items() if v != next(e.get(col) for e in rows if (e["population"], e["ticker"], e["d0"]) == k)]
            if bad:
                print(f"RULE (c) MISMATCH in {col} ({pop}): {bad[:5]}")
                return 4
    nums = {}
    base = {}
    for pop in POPS:
        sub = [e for e in eps if e["population"] == pop]
        S = [e for e in sub if counted(e)]
        for era in ("pooled", "A", "B"):
            v = verdict(S if era == "pooled" else [e for e in S if e["era"] == era], f"base:{pop}:{era}")
            put(nums, f"base:{pop}:{era}", v)
            if era == "pooled":
                base[pop] = v
        for k in (1, 2):
            put(nums, f"slip{k}:{pop}", verdict(S, f"slip{k}:{pop}", f"r5_r_slip{k}", f"r5_pnl_adr_slip{k}"))
        ended = [e for e in sub if e.get("decision") == "admitted" and e.get("r5_status") == "ended_mid_walk"
                 and e.get("void_adjustment_event") != "1" and e.get("distribution_class") != "distribution"]
        b_rows = S + [{**e, "r5_r": e["r5_r_last_close"], "r5_pnl_adr": e.get("r5_pnl_adr_last_close", "")} for e in ended if f(e.get("r5_r_last_close")) is not None]
        c_rows = S + [{**e, "r5_r": e["r5_r_haircut"], "r5_pnl_adr": e.get("r5_pnl_adr_haircut", "")} for e in ended if f(e.get("r5_r_haircut")) is not None]
        vb = verdict(b_rows, f"three:{pop}:b") if len(b_rows) > len(S) else base[pop]
        vc = verdict(c_rows, f"three:{pop}:c") if len(c_rows) > len(S) else base[pop]
        put(nums, f"three:{pop}:b", vb)
        put(nums, f"three:{pop}:c", vc)
        nd = len(b_rows) - len(S)
        nums[f"three:{pop}:n_delisted"] = nd
        lab = base[pop]["verdict"]
        if vb["verdict"] != lab or vc["verdict"] != lab:
            lab = f"{lab}, depends on {nd} delisted episodes"
        nums[f"three:{pop}:label"] = lab
        if pop not in READ_POPS:
            continue
        bes = {"voids_in": [e for e in sub if e.get("decision") == "admitted" and e.get("r5_status") == "settled"],
               "jump_removed": [e for e in sub if counted(e, dec="decision_jump_removed")],
               "mna": [e for e in sub if counted(e, dec="decision_mna")]}
        if pop == "P1":
            bes["cap_floor"] = [e for e in sub if counted(e, dec="decision_cap_floor")]
        for nm, rows in bes.items():
            put(nums, f"{nm}:{pop}", verdict(rows, f"{nm}:{pop}"))
        e8 = [e for e in sub if counted(e, "e5", "decision_8k")]
        put(nums, f"8k:{pop}", verdict(e8, f"8k:{pop}", "e5_r", "e5_pnl_adr"))
        put(nums, f"8k_unknown:{pop}", verdict([e for e in S if e.get("earnings_flag") == "unknown"], f"8k_unknown:{pop}"))
        pr = [e for e in e8 if (e.get("e3_status") or "settled") == "settled" and f(e.get("e3_r")) is not None]
        dv = [f(e["e3_r"]) - f(e["e5_r"]) for e in pr]
        lo, hi = block_ci(dv, [e["r5_entry_month"] for e in pr], f"read1_8k:{pop}") if dv else (float("nan"), float("nan"))
        n = len(pr)
        put_read(nums, f"read1_8k:{pop}", {"n_a": n, "n_b": n, "n_unknown": len(e8) - n, "diff": float(np.mean(dv)) if dv else float("nan"),
                                           "lo": lo, "hi": hi, "redraws": 0,
                                           "verdict": "CAN'T TELL" if n < N_FLOOR else ("separates in HIS direction" if lo > 0 else
                                                                                       "separates AGAINST him" if hi < 0 else "CAN'T TELL")})
        if pop == "P1":
            nums["cap_floor:P1:rejected_small"] = sum(1 for e in sub if f(e.get("cap")) is not None and f(e["cap"]) < 250_000_000)
            nums["cap_floor:P1:rejected_unknown"] = sum(1 for e in sub if f(e.get("cap")) is None)
        if pop == "P2":
            for g in ("yes", "no"):
                put(nums, f"gone_{g}:{pop}", verdict([e for e in S if e.get("gone") == g], f"gone_{g}:{pop}"))
        if pop in READ_POPS:
            for other, nm in (("r3", "read1"), ("d3", "read1_d3")):
                pr = [e for e in S if (e.get(f"{other}_status") or "settled") == "settled" and f(e.get(f"{other}_r")) is not None]
                dv = [f(e[f"{other}_r"]) - f(e["r5_r"]) for e in pr]
                mean = float(np.mean(dv)) if dv else float("nan")
                lo, hi = block_ci(dv, [e["r5_entry_month"] for e in pr], f"{nm}:{pop}") if dv else (float("nan"), float("nan"))
                n = len(pr)
                v = "CAN'T TELL" if n < N_FLOOR else ("separates in HIS direction" if lo > 0 else "separates AGAINST him" if hi < 0 else "CAN'T TELL")
                put_read(nums, f"{nm}:{pop}", {"n_a": n, "n_b": n, "n_unknown": len(S) - n, "diff": mean, "lo": lo, "hi": hi, "redraws": 0, "verdict": v})
            for key, g in groups().items():
                A = [e for e in S if g(e) == "A"]
                B = [e for e in S if g(e) == "B"]
                U = [e for e in S if g(e) is None]
                d, lo, hi, red = diff_interval([f(e["r5_r"]) for e in A], [e["r5_entry_month"] for e in A],
                                               [f(e["r5_r"]) for e in B], [e["r5_entry_month"] for e in B], f"{key}:{pop}")
                put_read(nums, f"{key}:{pop}", {"n_a": len(A), "n_b": len(B), "n_unknown": len(U), "diff": d, "lo": lo, "hi": hi,
                                                 "redraws": red, "verdict": read_v(d, lo, hi, len(A), len(B), len(U), len(S))})
    cell = lambda v: "PASS" if v.startswith("PASS") else "FAIL" if v.startswith("FAIL") else "CAN'T TELL"
    nums["grid:cell"] = GRID[(cell(base["P1"]["verdict"]), cell(base["P2"]["verdict"]))]
    with open(dst, "w") as fh:
        json.dump(nums, fh, sort_keys=True)
    print(f"REDERIVED {len(nums)} numbers from {src}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
