"""FIX 3 — is `_rs_rising` (newest>oldest) a defective reading of "RS is RISING"?

$0. Read-only prod capture (one pass, no LLM, no paid data) over the full theme era:
  scripts/probes/_fix3_boards_2026-08-26.tsv — mi_themes 2026-03-19..2026-08-26 (5,880 rows)
  scripts/probes/_fix3_rs_2026-08-26.tsv     — rs_composite for every themed ticker, 2026-03-01..

Method mirrors `_368_crypto_ai_consolidation_replay.py::part3_prune_backtest` (the backtest
that shipped the hold) so the numbers are directly comparable to the 77%/31% on that line.

Both directions are measured, per the task:
  TRUE-HOLD  — of the genuine ignitions the current test holds, how many does the new test
               still hold? (IREN + APLD 2026-07-22 are the verified case the hold exists for.)
  FALSE-HOLD — of the names the current test holds, how many are chop/collapse, and does the
               new test stop holding them?

EP exposure: a stricter test prunes MORE, and a pruned member of an Accelerating/Mainstream
theme loses the R4 +10 in-theme bonus. Counted explicitly, never estimated.
"""
from __future__ import annotations

import csv
import os
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
BOARDS_TSV = os.path.join(HERE, "_fix3_boards_2026-08-26.tsv")
RS_TSV = os.path.join(HERE, "_fix3_rs_2026-08-26.tsv")

PRUNE_RS_HARD = 25.0
PRUNE_RS_SOFT = 35.0
HOLD_WINDOW = 6
HOLD_MIN_POINTS = 4

# The verified TRUE-HOLD case the hold was built for (#368 / #531): IREN + APLD pruned from
# 'AI Compute & GPU Data Center Hosting Operators' on 2026-07-22 while both were igniting.
TRUE_HOLD_CASES = [("IREN", "2026-07-22"), ("APLD", "2026-07-22")]

# Recorded prod histories (newest-first) from docs/analysis/theme_mass_eviction_2026-08-26.md.
# These post-date the frozen export, so they are used as FIXTURES, not re-derived.
RECORDED = {
    "BLDR (08-25 false prune-while-rising flag)": [10.0, 13.8, 25.7, 29.4, 29.2, 5.9],
    "SO":  [22.1, 23.9, 24.4, 11.9, 19.9, 15.9],
    "EXC": [24.2, 22.9, 24.5, 13.3, 24.7, 14.6],
    "AEP": [21.0, 18.6, 15.8, 10.8, 22.8, 16.4],
    "CMS": [18.2, 17.7, 15.2, 9.8, 13.7, 10.5],
    "ATO": [28.4, 24.2, 22.5, 15.8, 21.4, 15.6],
    "FE":  [27.9, 25.6, 23.4, 14.3, 21.7, 17.3],
}


# ── candidate shape tests ────────────────────────────────────────────────────

def _slope(hist: list[float]) -> float:
    """Least-squares slope in RS points per session, on a newest-first list.

    x is reversed to chronological order so a positive slope means RISING.
    """
    n = len(hist)
    xs = list(range(n - 1, -1, -1))  # newest-first list -> chronological x
    mx = sum(xs) / n
    my = sum(hist) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, hist))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den if den else 0.0


def _median(vals: list[float]) -> float:
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def t_current(h):      # newest > oldest — the endpoint test in prod today
    return len(h) >= HOLD_MIN_POINTS and h[0] > h[-1]


def t_slope(h):        # trajectory: least-squares slope over the whole window
    return len(h) >= HOLD_MIN_POINTS and _slope(h) > 0


def t_slope_pos(h):    # slope > 0 AND today is not below the window's middle
    return len(h) >= HOLD_MIN_POINTS and _slope(h) > 0 and h[0] >= _median(h)


def t_halves(h):       # recent half's mean above the older half's mean
    if len(h) < HOLD_MIN_POINTS:
        return False
    k = len(h) // 2
    return (sum(h[:k]) / k) > (sum(h[k:]) / len(h[k:]))


def t_med(h):          # now above the MEDIAN of the window's earlier readings
    return len(h) >= HOLD_MIN_POINTS and h[0] > _median(h[1:])


def t_and_med(h):      # current test AND the robust reference — strictly narrows the hold
    return t_current(h) and h[0] > _median(h[1:])


def t_and_max(h):      # current test AND now at/above the window's earlier peak
    return t_current(h) and h[0] >= max(h[1:])


def t_anchor(h):
    """The NARROW repair: newest>oldest, but reject when the whole "rise" rests on
    the single OLDEST reading — i.e. today is below EVERY intermediate reading."""
    if not t_current(h):
        return False
    mid = h[1:-1]
    return (not mid) or h[0] >= min(mid)


TESTS = [
    ("current  (newest>oldest)", t_current),
    ("anchor   (not a lone-oldest rise)", t_anchor),
    ("slope    (OLS > 0)", t_slope),
    ("slope+pos(OLS>0 & now>=median)", t_slope_pos),
    ("halves   (recent mean>older)", t_halves),
    ("med      (now>median of earlier)", t_med),
    ("and-med  (current AND now>median)", t_and_med),
    ("and-max  (current AND now>=peak)", t_and_max),
]


# ── loaders (same shape as the #368 harness) ─────────────────────────────────

def load_boards():
    boards: dict[str, list[dict]] = defaultdict(list)
    with open(BOARDS_TSV) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            rs = float(row["rs_avg"])
            boards[row["theme_date"]].append({
                "name": row["name"], "stage": row["stage"],
                "rs_avg": None if rs < 0 else rs, "source": row["source"],
                "tickers": [t for t in (row["tickers"] or "").split(",") if t],
            })
    return dict(boards)


def load_rs():
    rs: dict[str, dict[str, float]] = defaultdict(dict)
    sessions: set[str] = set()
    with open(RS_TSV) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            rs[row["ticker"]][row["score_date"]] = float(row["rs_composite"])
            sessions.add(row["score_date"])
    return dict(rs), sorted(sessions)


def hist_newest_first(rs, sessions, ticker, d, n):
    out = []
    for s in reversed([s for s in sessions if s <= d]):
        v = rs.get(ticker, {}).get(s)
        if v is not None:
            out.append(v)
        if len(out) >= n:
            break
    return out


def outcome(rs, sessions, tk, d):
    """The #368/#531 scoring rule verbatim: peak RS over the next 10 sessions."""
    later = [s for s in sessions if s > d][:10]
    if len(later) < 10:
        return None
    vals = [v for v in (rs.get(tk, {}).get(s) for s in later) if v is not None]
    if not vals:
        return None
    peak = max(vals)
    return "recovered" if peak >= 50 else ("dead" if peak < 25 else "limbo")


def collect_exits(boards, rs, sessions):
    """Prune-shaped member exits, mass-evictions excluded — the #368 part-3 population."""
    days = sorted(boards)
    exits = []
    for i in range(1, len(days)):
        d0, d1 = days[i - 1], days[i]
        prev = {t["name"]: t for t in boards[d0] if t["stage"] != "Retired"}
        cur = {t["name"]: t for t in boards[d1] if t["stage"] != "Retired"}
        for name, t0 in prev.items():
            t1 = cur.get(name)
            if t1 is None:
                continue
            gone = set(t0["tickers"]) - set(t1["tickers"])
            if len(gone) >= 3 and len(gone) * 2 >= len(t0["tickers"]):
                continue  # #214 mass eviction — a validation strip, not a prune
            for tk in gone:
                v = rs.get(tk, {}).get(d1)
                if v is None or v >= PRUNE_RS_SOFT:
                    continue
                exits.append({
                    "date": d1, "theme": name, "ticker": tk, "rs": v,
                    "stage": t0["stage"],
                    "hist": hist_newest_first(rs, sessions, tk, d1, HOLD_WINDOW),
                })
    return exits


def rate(rows, rs, sessions):
    sc = [o for o in (outcome(rs, sessions, r["ticker"], r["date"]) for r in rows) if o]
    c = Counter(sc)
    pct = (100.0 * c["recovered"] / len(sc)) if sc else 0.0
    return len(sc), pct, dict(c)


def main():
    boards = load_boards()
    rs, sessions = load_rs()
    exits = collect_exits(boards, rs, sessions)

    print("=" * 92)
    print("FIX 3 — `_rs_rising`: endpoint test vs shape tests, both directions")
    print(f"frozen prod export 2026-06-01..2026-08-04 · {len(exits)} prune-shaped member exits")
    print("=" * 92)

    print("\n1. RECORDED CASES (fixtures from the 08-26 analysis; newest-first)")
    hdr = f"  {'case':<44}" + "".join(f"{lbl.split()[0]:>10}" for lbl, _ in TESTS)
    print(hdr)
    for label, h in RECORDED.items():
        row = f"  {label:<44}"
        for _, fn in TESTS:
            row += f"{('HOLD' if fn(h) else 'prune'):>10}"
        print(row + f"   slope={_slope(h):+.2f}")

    print("\n2. HOLD POPULATION + FORWARD RECOVERY (peak RS>=50 within 10 sessions)")
    print(f"  {'test':<32}{'held':>6}{'scored':>8}{'recovered%':>12}"
          f"{'control N':>11}{'control%':>10}")
    per_test = {}
    for label, fn in TESTS:
        held = [e for e in exits if fn(e["hist"])]
        ctrl = [e for e in exits if not fn(e["hist"])]
        n_h, p_h, _ = rate(held, rs, sessions)
        n_c, p_c, _ = rate(ctrl, rs, sessions)
        per_test[label] = held
        print(f"  {label:<32}{len(held):>6}{n_h:>8}{p_h:>11.0f}%{n_c:>11}{p_c:>9.0f}%")

    base = per_test["current  (newest>oldest)"]
    base_keys = {(e["ticker"], e["date"]) for e in base}

    print("\n3. BOTH DIRECTIONS vs the current test")
    for label, fn in TESTS[1:]:
        held = per_test[label]
        keys = {(e["ticker"], e["date"]) for e in held}
        kept = [e for e in base if (e["ticker"], e["date"]) in keys]
        dropped = [e for e in base if (e["ticker"], e["date"]) not in keys]
        added = [e for e in held if (e["ticker"], e["date"]) not in base_keys]
        n_k, p_k, d_k = rate(kept, rs, sessions)
        n_d, p_d, d_d = rate(dropped, rs, sessions)
        print(f"\n  --- {label}")
        print(f"    STILL HELD  {len(kept):>3} of {len(base)}  "
              f"(scored {n_k}: {p_k:.0f}% recovered  {d_k})")
        print(f"    NO LONGER   {len(dropped):>3}          "
              f"(scored {n_d}: {p_d:.0f}% recovered  {d_d})")
        print(f"    newly held  {len(added):>3}")
        # TRUE-HOLD DoD
        for tk, d in TRUE_HOLD_CASES:
            hit = [e for e in base if e["ticker"] == tk and e["date"] == d]
            if hit:
                print(f"    DoD {tk} {d}: current=HOLD  new="
                      f"{'HOLD' if fn(hit[0]['hist']) else 'PRUNE  <-- TRUE-HOLD BROKEN'}"
                      f"   hist={[round(v,1) for v in hit[0]['hist']]}")
            else:
                print(f"    DoD {tk} {d}: not a prune-shaped exit in the frozen board export")
        # EP exposure: newly-pruned members of Accelerating/Mainstream themes
        exposed = [e for e in dropped if e["stage"] in ("Accelerating", "Mainstream")]
        print(f"    EP EXPOSURE newly-pruned from an Accelerating/Mainstream theme: "
              f"{len(exposed)} over {len(sorted(boards))} board-days"
              + (f"  {[(e['ticker'], e['date']) for e in exposed]}" if exposed else ""))

    print("\n4. THE NO-LONGER-HELD NAMES (current test's false holds), slope-test view")
    dropped = [e for e in base if not t_slope(e["hist"])]
    if not dropped:
        print("    none — on the EXIT population the slope test is a strict superset of the "
              "current test (it holds every name the current test held, plus 6).")
    for e in sorted(dropped, key=lambda x: x["date"]):
        o = outcome(rs, sessions, e["ticker"], e["date"]) or "unscored"
        print(f"    {e['date']}  {e['ticker']:<6} RS{e['rs']:5.1f}  slope={_slope(e['hist']):+6.2f}"
              f"  hist={[round(v,1) for v in e['hist']]}  -> {o}")

    # ── 5. The population the change actually ACTS on ────────────────────────
    # The exit population only contains names that LEFT. Going forward the hold
    # is evaluated on every prune CANDIDATE, whether or not it ends up leaving —
    # so the disagreement class must be counted there. Replays the engine's own
    # candidacy gate (`_rescore_existing_theme`) over every live theme member.
    print("\n5. EVERY PRUNE-CANDIDATE EVALUATION (the population the hold acts on)")
    days = sorted(boards)
    cand = []
    for d in days:
        for t in boards[d]:
            if t["stage"] == "Retired":
                continue
            for tk in t["tickers"]:
                v = rs.get(tk, {}).get(d)
                if v is None:
                    continue
                h = hist_newest_first(rs, sessions, tk, d, HOLD_WINDOW)
                if v < PRUNE_RS_HARD:
                    is_cand = True
                elif v < PRUNE_RS_SOFT:
                    is_cand = len(h) >= 3 and all(x < PRUNE_RS_SOFT for x in h[:3])
                else:
                    is_cand = False
                if is_cand:
                    cand.append({"date": d, "theme": t["name"], "ticker": tk,
                                 "rs": v, "stage": t["stage"], "hist": h})
    print(f"  prune-candidate evaluations: {len(cand)}  "
          f"({len({c['ticker'] for c in cand})} distinct tickers, {len(days)} board-days)")
    for label, fn in TESTS:
        held = [c for c in cand if fn(c["hist"])]
        n, p, _ = rate(held, rs, sessions)
        print(f"    {label:<32} holds {len(held):>4} / {len(cand)}  "
              f"(scored {n}: {p:.0f}% recovered)")

    for label, fn in TESTS[1:]:
        stops = [c for c in cand if t_current(c["hist"]) and not fn(c["hist"])]
        adds = [c for c in cand if fn(c["hist"]) and not t_current(c["hist"])]
        n_s, p_s, d_s = rate(stops, rs, sessions)
        n_a, p_a, d_a = rate(adds, rs, sessions)
        exposed = [c for c in stops if c["stage"] in ("Accelerating", "Mainstream")]
        print(f"\n  --- {label}")
        print(f"    STOPS HOLDING (current=HOLD, new=prune): {len(stops):>4}  "
              f"scored {n_s}: {p_s:.0f}% recovered  {d_s}")
        print(f"    NEWLY HOLDS   (current=prune, new=HOLD): {len(adds):>4}  "
              f"scored {n_a}: {p_a:.0f}% recovered  {d_a}")
        print(f"    EP EXPOSURE — of the stops, members of an Accelerating/Mainstream "
              f"theme: {len(exposed)}")
        if label.startswith("anchor"):
            for c in sorted(stops, key=lambda x: x["date"]):
                o = outcome(rs, sessions, c["ticker"], c["date"]) or "unscored"
                mark = " <-- EP EXPOSURE" if c["stage"] in ("Accelerating", "Mainstream") else ""
                print(f"      {c['date']}  {c['ticker']:<6} RS{c['rs']:5.1f} [{c['stage'][:4]}] "
                      f"hist={[round(v,1) for v in c['hist']]} -> {o}{mark}")
        if False and label.startswith("and-med"):
            for c in sorted(stops, key=lambda x: x["date"])[:40]:
                o = outcome(rs, sessions, c["ticker"], c["date"]) or "unscored"
                print(f"      {c['date']}  {c['ticker']:<6} RS{c['rs']:5.1f} "
                      f"hist={[round(v,1) for v in c['hist']]} -> {o}")

    # ── 6. Episode view — one row per contiguous candidate run, not per day ──
    # A sub-floor name is a candidate on many consecutive days, so the per-day
    # view double-counts one episode and its forward windows overlap. Collapse
    # each (theme, ticker) run of consecutive candidate days to its FIRST day.
    print("\n6. EPISODE VIEW (one row per contiguous candidate run — no double-counting)")
    idx = {d: i for i, d in enumerate(days)}
    seen: dict[tuple[str, str], int] = {}
    episodes = []
    for c in sorted(cand, key=lambda x: (x["theme"], x["ticker"], x["date"])):
        k = (c["theme"], c["ticker"])
        i = idx[c["date"]]
        if k in seen and i == seen[k] + 1:
            seen[k] = i
            continue
        seen[k] = i
        episodes.append(c)
    print(f"  episodes: {len(episodes)}")
    for label, fn in TESTS:
        held = [e for e in episodes if fn(e["hist"])]
        n, p, _ = rate(held, rs, sessions)
        stops = [e for e in episodes if t_current(e["hist"]) and not fn(e["hist"])]
        n_s, p_s, _ = rate(stops, rs, sessions)
        adds = [e for e in episodes if fn(e["hist"]) and not t_current(e["hist"])]
        n_a, p_a, _ = rate(adds, rs, sessions)
        print(f"    {label:<32} holds {len(held):>3} (scored {n:>3}: {p:>3.0f}% rec) | "
              f"stops {len(stops):>3} (scored {n_s:>2}: {p_s:>3.0f}% rec) | "
              f"adds {len(adds):>3} (scored {n_a:>2}: {p_a:>3.0f}% rec)")


if __name__ == "__main__":
    main()
