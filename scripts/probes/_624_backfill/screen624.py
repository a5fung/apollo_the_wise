"""#624 backfill — the screen: rule P15 (imported) at the post-open ticks, first qualifying tick, the
MAX_ENRICH_PER_TICK mirror, one cap read per (ticker, D). Outcome-blind: nothing here walks or reads an outcome.

digest(): per (ticker, D) the tick readings (price under both 09:30 modes, acting volume under every C1 cut-off)
plus the W4 / W6 data diagnostics — computed once from the minute capture so the screen never holds the bars.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, time

import lib624 as L

K_SET = (15, 14, 16, 10, 20, 0)
MODES = ("open930", "close929")


def digest(t: str, d: date, bars: list[tuple]) -> dict:
    out = {"n": len(bars), "px": {m: {} for m in MODES}, "vol": {k: {} for k in K_SET}}
    for T in L.TICKS:
        Ts = T.strftime("%H:%M")
        for m in MODES:
            out["px"][m][Ts] = L.tick_price(bars, T, m)
        for k in K_SET:
            out["vol"][k][Ts] = L.tick_volume(bars, T, k)
    b930 = next((b for b in bars if b[0] == 570), None)
    out["has930"] = b930 is not None
    out["o930"] = b930[1] if b930 else None
    out["entry_cov_0931_1000"] = sum(1 for b in bars if 571 <= b[0] < 600)
    out["mods_0930_1000"] = [b[0] for b in bars if 570 <= b[0] < 600]
    out["vol_0400_0940"] = sum(b[5] for b in bars if 240 <= b[0] < 580)
    out["hi_0400_0955"] = max((b[2] for b in bars if 240 <= b[0] < 596), default=None)
    out["vol_full"] = sum(b[5] for b in bars)
    out["vol_rth"] = sum(b[5] for b in bars if 570 <= b[0] < 960)
    out["rth_hi"] = max((b[2] for b in bars if 570 <= b[0] < 960), default=None)
    out["rth_lo"] = min((b[3] for b in bars if 570 <= b[0] < 960), default=None)
    return out


def tick_readings(dg: dict, *, k: int, mode930: str):
    for T in L.TICKS:
        Ts = T.strftime("%H:%M")
        yield T, dg["px"][mode930][Ts], dg["vol"][k][Ts]


def screen(day_rows: dict[date, list[dict]], digests: dict, daily: dict, splits, refs: dict | None, *, k: int,
           mode930: str, cap_basis: str, sect: dict) -> dict:
    """day_rows: D -> prefilter-passing cand rows (dicts with t, d, pc, ...). refs None = list-builder mode
    (returns the free-term survivors needing a reference read). Returns signals + per-key dispositions + counts."""
    signals, disp, need_ref = [], {}, set()
    cnt = Counter()
    for d in sorted(day_rows):
        passing = defaultdict(list)          # T -> [(gap, t, info)]
        for r in day_rows[d]:
            t = r["t"]
            dg = digests.get((t, d))
            if dg is None:
                disp[(t, d)] = "not_pulled"; cnt["not_pulled"] += 1; continue
            if dg["n"] == 0:
                disp[(t, d)] = "no_minute_bars"; cnt["no_minute_bars"] += 1; continue
            pc_adj = r["pc"]
            fp, fd = L.fac_prior(splits, t, d), L.fac_day(splits, t, d)
            pc_raw = pc_adj * fp
            hist = L.vol_history(daily.get(t), d)
            any_pass = False
            for T, px, vol in tick_readings(dg, k=k, mode930=mode930):
                g = L.gap_pct(px, pc_adj)
                v = L.free_terms(t, g, pc_raw, vol, hist)
                if v.meets_free_terms:
                    any_pass = True
                    passing[T].append((g, t, {"t": t, "d": d, "T": T, "gap": g, "px_adj": px, "px_raw": px * fd,
                                              "pc_adj": pc_adj, "pc_raw": pc_raw, "vol_adj": vol, "vol_raw": vol / fd,
                                              "pct": v.vol_percentile, "hist_n": v.vol_history_n, "fac_prior": fp,
                                              "fac_day": fd, "typed_today": sect.get(t) or "untyped_today"}))
            if not any_pass:
                disp[(t, d)] = "never_passed_free_terms"; cnt["never_passed_free_terms"] += 1
            elif refs is None or (t, d) not in refs:
                need_ref.add((t, d))
        if refs is None:
            continue
        evaluated = set()
        for T in L.TICKS:
            todo = []
            for g, t, info in passing.get(T, []):
                if t in evaluated:
                    continue
                ref = refs.get((t, d))
                if ref is None:
                    disp[(t, d)] = "ref_not_read"; evaluated.add(t); cnt["ref_not_read"] += 1; continue
                ty = L.common_type(ref)
                if ty is not None and ty not in L.STOCK_TYPES:
                    disp[(t, d)] = f"non_common:{ty}"; evaluated.add(t); cnt["non_common"] += 1; continue
                todo.append((g, t, info, ref, ty))
            todo.sort(key=lambda x: -(x[0] or 0.0))
            if len(todo) > L.LL.MAX_ENRICH_PER_TICK:
                cnt["tick_capped_rolls"] += len(todo) - L.LL.MAX_ENRICH_PER_TICK
                cnt["tick_capped_ticks"] += 1
                todo = todo[:L.LL.MAX_ENRICH_PER_TICK]
            for g, t, info, ref, ty in todo:
                evaluated.add(t)
                sh = L.shares_of(ref)
                base = info["pc_raw"] if cap_basis == "pc" else info["px_raw"]
                if sh is None or not base:
                    disp[(t, d)] = "cap_unavailable" + ("" if ref.get("http") == 200 else f":http{ref.get('http')}")
                    cnt["cap_unavailable"] += 1
                    continue
                cap = sh * base
                if cap >= L.LL.LANE_MAX_MARKET_CAP:
                    disp[(t, d)] = "rejected_cap"; cnt["rejected_cap"] += 1; continue
                rec = dict(info, shares=sh, cap=cap, cap_basis=cap_basis, poly_type=ty,
                           ref_http=ref.get("http"), delisted_utc=(ref.get("r") or {}).get("delisted_utc"))
                signals.append(rec)
                disp[(t, d)] = f"signal@{T.strftime('%H:%M')}"
                cnt["signal"] += 1
        for g_list in passing.values():
            for g, t, info in g_list:
                if (t, d) not in disp:
                    disp[(t, d)] = "rolled_never_read"; cnt["rolled_never_read"] += 1
    return {"signals": signals, "disp": disp, "need_ref": need_ref, "counts": cnt}
