#!/usr/bin/env python3
"""#684 ADDENDUM (2026-09-28) — re-run with ONE change: outcome measured from the price the live
system actually buys at (the opening-range high), not the gap-day close. PRE-REGISTRATION below,
written BEFORE any frame-B outcome number was computed. Imports study.py's functions; does not
call study.main() (that would overwrite results.tsv/outcomes.tsv/summary.json in place).

⚠ REGISTRATION CORRECTION, made before computing anything, from reading the live code (grep, not
inference): the task framing this addendum was commissioned under says the live entry is "a stop-buy
at the 09:30-09:45 ET opening-range high". The CODE says otherwise. `fetch_orb_bar_with_retry`
(agents/market_intelligence/broker/entry_pipeline.py:83) calls `alpaca.get_first_bar`
(agents/market_intelligence/broker/alpaca_client.py:839), whose own docstring is "Get the FIRST
1-MINUTE bar" — the live ORB high is the high of the single 09:30-09:31 candle, not a 15-minute
09:30-09:44 aggregate. `shadow_orb_tracker.py`'s 5-minute ORB is a SEPARATE telemetry-only shadow
experiment, also not live. CLAUDE.md's "ORB submission window ... minute < 45" describes how long
the stop-buy order (set at the SINGLE first-minute bar's high) stays open before the 10:00 cleanup
cancels it unfilled — it is not the width of the range. This file computes the frame EXACTLY as
specified in the task (09:30-09:44 aggregate high, from `orb.tsv` / `orb_minutes.tsv`) because that
is what was asked and it is the existing study's own "0945 opening range" definition (O945_orb_*
features already in features.tsv use the same 09:30-09:44 window) — but the result below is NOT an
exact match to the current live trigger price, which is set ~14 minutes earlier and off a single,
noisier bar. Flagged in the report; not silently "fixed" (THE LINE — no code read here decides
anything, this is measurement only, and the discrepancy is the operator's to weigh).

FILL DEFINITION: FILLED = the first 1-minute bar in [09:45, 10:00) ET whose HIGH >= the opening-range
high (09:30-09:44 max, from `orb.tsv`/`orb_minutes.tsv`, cross-checked: 0 of 670 rows differ by more
than $0.005 between the two independent pulls). >= not >, matching the live stop-limit semantics
("once last >= stop_price the order becomes a limit buy", order_manager.py:114-119 docstring) — a
touch counts. `touch_count` (how many of the up-to-15 bars in the window clear the level) is reported
per row so the >= choice is auditable; an exact-touch-only fill (high == orb high to the cent) is
counted separately in the report.

OUTCOME (RUN_B): (max high from the fill bar through session +15 - the opening-range high) /
adr_dollar_ep (the SAME 20-session pre-gap ADR$ denominator as frame A, `delayed_entry_shadow.
compute_ep_adr_dollar`, already in features.tsv). The "max high from the fill through session +15" is
computed WITHOUT touching mi_daily_closes for the gap day itself, by design: mi_daily_closes
(Polygon, the outcome table frame A uses) and mi_intraday_bars (Alpaca, what defines the live trigger)
are DIFFERENT feeds: a consolidated print reflected in the Polygon daily high but never printed on
the Alpaca feed mi_intraday_bars stores would mix sources and could put the day's "max" before the
fill, which is not a valid frame-B outcome. Fix (`orb_minutes.sql`, one query, LATERAL joins,
computed server-side from mi_intraday_bars alone): re-derive the 09:30-09:44 high independently
(orb2_high, cross-checked against orb.tsv), find the fill bar in [09:45,10:00), and take
max(high) from that bar's timestamp through 16:00 the SAME session, all from mi_intraday_bars. Only
sessions +1..+15 fall back to mi_daily_closes (as frame A already does) because there is no
same-session ambiguity there. RUNNER_B = RUN_B >= 5 (also >= 8). UNFILLED rows are NOT runners in
frame B (runnerB5 = runnerB8 = 0), not excluded — the task's own instruction.

READABLE-B POPULATION: a row needs (a) a 15-session forward outcome (frame A's own censoring — 667 of
670), (b) >= 12 of 15 possible 1-minute bars in [09:30,09:44) (the SAME coverage bar features.py uses
for O945_covered), and (c) >= 12 of 15 possible bars in [09:45,10:00). Short of any of these the row is
UNREADABLE — reported, not guessed. This is a DIFFERENT n than frame A's 667 (frame A needs only (a)),
so every comparison below is run TWICE: frame A's own test recomputed on the SAME readable-B rows
(isolates the entry-price effect) sits beside frame B, and the ORIGINAL published frame-A verdict
(all 667, from results.tsv) is carried as a third column for reference. A verdict is flagged CHANGED
only against the same-population frame-A column — a flip against the published column alone could be
a population artefact, not an entry-price effect.

SPLIT / DRAWS / PERMUTATION / PASS BAR: unchanged from study.py — same DISCOVERY (<=2026-08-14) /
HELD-OUT (08-15..09-03) split (block-membership only depends on scan_date, unaffected by this change),
the SAME 63 features (no add, no drop), tercile cuts taken from each run's OWN discovery rows (frame A'
and frame B each cut on their own label composition, both restricted to the readable-B rows), the same
week-block permutation (2,000 draws, seed 684 — reset to 684 independently for EACH of the two runs, so
both walk the identical draw of shuffles in DRAWS order), the same four-condition pass bar, the same
noise band (63 draws -> up to 3 discovery-only clears is noise; ~1-1.5 four-condition chance passes,
per study.py's post-run correction, carried forward unchanged).
"""
from __future__ import annotations

import random
from collections import Counter, defaultdict
from pathlib import Path

from study import (
    DRAWS,
    LABELLED,
    N_PERM,
    SEED,
    add_outcomes,
    auc,
    diff_stat,
    fav_mask,
    load_daily,
    load_features,
    perm_p,
    rate,
    tercile_cuts,
)

HERE = Path(__file__).resolve().parent
FILL_COVERAGE_BARS = 12  # same bar as features.py's O945_covered


def fnum(x: str | None) -> float | None:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except ValueError:
        return None


def load_psv(path: Path) -> list[dict]:
    rows: list[dict] = []
    header: list[str] | None = None
    with path.open() as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("(") or line.startswith("Output format") or line.startswith("Field separator"):
                continue
            parts = line.split("|")
            if header is None:
                header = parts
                continue
            rows.append(dict(zip(header, parts)))
    return rows


def add_frame_b(rows: list[dict], daily: dict) -> None:
    orbm = {(r["ticker"], r["scan_date"]): r for r in load_psv(HERE / "orb_minutes.tsv")}
    n_no_orbm_row = 0
    for r in rows:
        k = (r["ticker"], r["scan_date"])
        om = orbm.get(k)
        if om is None:
            n_no_orbm_row += 1
            om = {}
        n0930 = int(fnum(om.get("n0930")) or 0)
        n0945 = int(fnum(om.get("n0945")) or 0)
        has_outcome_window = r.get("runner5") is not None  # frame A's own 15-session censoring
        r["n0930_bars"] = n0930
        r["n0945_bars"] = n0945
        r["orb_readable"] = int(has_outcome_window and n0930 >= FILL_COVERAGE_BARS and n0945 >= FILL_COVERAGE_BARS)
        r["orb2_high"] = fnum(om.get("orb2_high"))
        r["fill_hhmm"] = (om.get("fill_hhmm") or None) if r["orb_readable"] else None
        r["touch_count"] = int(fnum(om.get("touch_count")) or 0)
        r["exact_touch"] = None
        r["filled"] = None
        r["run_xadr_B"] = None
        r["runnerB5"] = None
        r["runnerB8"] = None
        if not r["orb_readable"]:
            continue
        r["filled"] = int(bool(r["fill_hhmm"]))
        if not r["filled"]:
            r["runnerB5"] = 0
            r["runnerB8"] = 0
            continue
        post_fill_max = fnum(om.get("post_fill_max_high"))
        r["exact_touch"] = int(post_fill_max is not None and r["orb2_high"] is not None and abs(post_fill_max - r["orb2_high"]) < 1e-9 and r["touch_count"] == 1)
        bars = daily.get(r["ticker"], [])
        dates = [b[0] for b in bars]
        d = r["scan_date"]
        if d not in dates or post_fill_max is None or r.get("adr_dollar_ep") is None or r["orb2_high"] is None:
            continue  # readable + filled but the daily join failed -> leave run_xadr_B/runnerB5 as None (rare; counted below)
        i0 = dates.index(d)
        fwd = bars[i0 + 1:i0 + 16]
        if len(fwd) < 15:
            continue
        mx = max([post_fill_max] + [b[2] for b in fwd])
        r["run_xadr_B"] = (mx - r["orb2_high"]) / r["adr_dollar_ep"]
        r["runnerB5"] = int(r["run_xadr_B"] >= 5)
        r["runnerB8"] = int(r["run_xadr_B"] >= 8)
    return n_no_orbm_row


def per_feature(col, kind, fav, when, name, disc, held, best_week, best_two, rng, label_key, rate8_key):
    dr = [r for r in disc if r.get(col) is not None]
    hr = [r for r in held if r.get(col) is not None]
    if len(dr) < 30:
        return {"feature": col, "when": when, "name": name, "verdict": "no data", "n_disc": len(dr)}
    cut = tercile_cuts([r[col] for r in dr]) if kind == "cont" else None
    fm = fav_mask(dr, col, kind, fav, cut)
    labels = [int(r[label_key]) for r in dr]
    weeks = [r["iso_week"] for r in dr]
    d_obs = diff_stat(labels, fm)
    n_fav = sum(fm)
    r_fav = rate([l for l, f in zip(labels, fm) if f])
    r_rest = rate([l for l, f in zip(labels, fm) if not f])
    pv = perm_p(labels, fm, weeks, d_obs, rng) if d_obs is not None else None
    a = auc([r[col] for r in dr], labels, fav if kind != "ord" else "HIGHER") if kind != "bool" else auc([float(f) for f in fm], labels, "HIGHER")
    hm = fav_mask(hr, col, kind, fav, cut)
    hl = [int(r[label_key]) for r in hr]
    h_fav = [l for l, f in zip(hl, hm) if f]
    h_rest = [l for l, f in zip(hl, hm) if not f]
    h_d = diff_stat(hl, hm)
    h_ok = sum(hl) >= 3 and len(h_fav) >= 8 and len(h_rest) >= 8
    h_sign = ("+" if h_d > 0 else "-" if h_d < 0 else "0") if h_d is not None else "—"
    dw = [i for i, r in enumerate(dr) if r["iso_week"] != best_week]
    d_w = diff_stat([labels[i] for i in dw], [fm[i] for i in dw])
    p_w = perm_p([labels[i] for i in dw], [fm[i] for i in dw], [weeks[i] for i in dw], d_w, rng) if d_w is not None else None
    dn = [i for i, r in enumerate(dr) if r["ticker"] not in best_two]
    d_n = diff_stat([labels[i] for i in dn], [fm[i] for i in dn])
    p_n = perm_p([labels[i] for i in dn], [fm[i] for i in dn], [weeks[i] for i in dn], d_n, rng) if d_n is not None else None
    all_scored = disc + held
    lab_rows = [r for r in all_scored if (r["ticker"], r["scan_date"]) in LABELLED and r.get(col) is not None]
    lab_fav = sum(f for f in fav_mask(lab_rows, col, kind, fav, cut) if f)
    if d_obs is None or pv is None:
        verdict = "no data"
    elif d_obs < 0:
        verdict = "fail (wrong way)" + (f", p={1 - pv:.3f} the other way" if (1 - pv) < 0.05 else "")
    elif pv >= 0.05:
        verdict = "can't tell (discovery p >= 0.05)"
    elif not h_ok:
        verdict = "can't tell (held-out too thin)"
    elif h_d is None or h_d <= 0:
        verdict = "can't tell (held-out sign against)"
    elif not (d_w is not None and d_w > 0 and p_w is not None and p_w < 0.05):
        verdict = "can't tell (does not survive dropping the best week)"
    elif not (d_n is not None and d_n > 0 and p_n is not None and p_n < 0.05):
        verdict = "can't tell (does not survive dropping the best two names)"
    else:
        verdict = "PASS"
    if lab_rows and lab_fav <= 1 and verdict == "PASS":
        verdict += " ⚠ labelled-EP conflict"
    return {"feature": col, "when": when, "name": name, "n_disc": len(dr), "n_fav": n_fav, "rate_fav": r_fav,
            "n_rest": len(dr) - n_fav, "rate_rest": r_rest, "diff": d_obs, "auc": a, "p_disc": pv,
            "held_n_fav": len(h_fav), "held_rate_fav": rate(h_fav), "held_n_rest": len(h_rest), "held_rate_rest": rate(h_rest),
            "held_sign": h_sign, "held_ok": h_ok, "drop_week_diff": d_w, "drop_week_p": p_w,
            "drop_two_diff": d_n, "drop_two_p": p_n, "labelled_in_fav": lab_fav, "labelled_n": len(lab_rows), "verdict": verdict}


def run_pass(scored, label_key, rate8_key, rng_seed):
    disc = [r for r in scored if r["block"] == "DISCOVERY"]
    held = [r for r in scored if r["block"] == "HELD-OUT"]
    wk = Counter(r["iso_week"] for r in disc if r[label_key])
    best_week = wk.most_common(1)[0][0] if wk else None
    key_for_two = "run_xadr_B" if label_key == "runnerB5" else "run_xadr"
    best_two = [r["ticker"] for r in sorted(disc, key=lambda r: -(r[key_for_two] or -1))[:2]]
    rng = random.Random(rng_seed)
    results = []
    for col, kind, fav, when, name in DRAWS:
        results.append(per_feature(col, kind, fav, when, name, disc, held, best_week, best_two, rng, label_key, rate8_key))
    return results, disc, held, best_week, best_two


def fmt_rate(r):
    if r is None or "n_fav" not in r:
        return "n/a"
    return f"{r['n_fav']}/{100*r['rate_fav']:.1f}% vs {r['n_rest']}/{100*r['rate_rest']:.1f}%"


def main() -> None:
    rows = load_features()
    daily = load_daily()
    add_outcomes(rows, daily)  # frame A, unchanged (reused, not recomputed)
    for r in rows:  # same derivation study.main() does inline (not in load_features) -- replicated here
        if r.get("ALERT_expct_scheduled") in ("scheduled", "unscheduled"):
            r["ALERT_expct_unscheduled"] = 1.0 if r["ALERT_expct_scheduled"] == "unscheduled" else 0.0
        else:
            r["ALERT_expct_unscheduled"] = None
    n_no_orbm_row = add_frame_b(rows, daily)

    out: list[str] = []
    p = out.append

    scored_A = [r for r in rows if r["runner5"] is not None]
    readable = [r for r in scored_A if r["orb_readable"]]
    unreadable = [r for r in scored_A if not r["orb_readable"]]
    filled = [r for r in readable if r["filled"]]
    unfilled = [r for r in readable if r["filled"] == 0]

    p(f"#684 ADDENDUM RESULTS — {len(scored_A)} rows with a frame-A 15-session outcome; "
      f"{len(readable)} ORB-readable (>= {FILL_COVERAGE_BARS}/15 bars both [09:30,09:44) and [09:45,10:00)); "
      f"{len(unreadable)} unreadable ({n_no_orbm_row} had no orb_minutes.tsv row at all)")
    p(f"unreadable by alerted: alerted {sum(1 for r in unreadable if r['alerted'])} of {sum(1 for r in scored_A if r['alerted'])} alerted rows; "
      f"rejected {sum(1 for r in unreadable if not r['alerted'])} of {sum(1 for r in scored_A if not r['alerted'])} rejected rows")
    p("")
    p(f"FILL RATE (readable rows only, n={len(readable)}): filled {len(filled)} ({100*len(filled)/len(readable):.1f}%), "
      f"unfilled {len(unfilled)} ({100*len(unfilled)/len(readable):.1f}%)")
    p(f"  alerted readable: n {sum(1 for r in readable if r['alerted'])}, filled {sum(1 for r in readable if r['alerted'] and r['filled'])} "
      f"({100*rate([r['filled'] for r in readable if r['alerted']]):.1f}%)")
    p(f"  rejected readable: n {sum(1 for r in readable if not r['alerted'])}, filled {sum(1 for r in readable if not r['alerted'] and r['filled'])} "
      f"({100*rate([r['filled'] for r in readable if not r['alerted']]):.1f}%)")
    exact = sum(1 for r in filled if r["exact_touch"])
    p(f"  exact-touch-only fills (high == ORB high to the cent, single touching bar): {exact} of {len(filled)} filled rows")
    p("")

    # runner composition, frame A (published, all 667) vs frame A on readable-B vs frame B
    p("RUNNER COMPOSITION:")
    p(f"  frame A, published (all {len(scored_A)}): runners>=5 {sum(r['runner5'] for r in scored_A)} "
      f"({100*rate([r['runner5'] for r in scored_A]):.1f}%)  >=8 {sum(r['runner8'] for r in scored_A)}")
    p(f"  frame A, on readable-B population ({len(readable)}): runners>=5 {sum(r['runner5'] for r in readable)} "
      f"({100*rate([r['runner5'] for r in readable]):.1f}%)  >=8 {sum(r['runner8'] for r in readable)}")
    rb_ok = [r for r in readable if r["runnerB5"] is not None]
    p(f"  frame B, on readable-B population ({len(rb_ok)} with a computed RUN_B of {len(readable)} readable — "
      f"{len(readable)-len(rb_ok)} filled but the forward-daily join was incomplete, listed below): "
      f"runners>=5 {sum(r['runnerB5'] for r in rb_ok)} ({100*rate([r['runnerB5'] for r in rb_ok]):.1f}%)  >=8 {sum(r['runnerB8'] for r in rb_ok)}")
    incomplete = [r for r in filled if r["runnerB5"] is None]
    if incomplete:
        p(f"    incomplete rows: " + ", ".join(f"{r['ticker']} {r['scan_date']}" for r in incomplete))
    p("")

    # frame-A runners that were never fillable at the live entry
    frameA_runners_readable = [r for r in readable if r["runner5"]]
    never_fillable = [r for r in frameA_runners_readable if r["filled"] == 0]
    frameA_runners_unreadable = [r for r in unreadable if r["runner5"]]
    p(f"FRAME-A RUNNERS AND LIVE FILLABILITY: {sum(r['runner5'] for r in scored_A)} frame-A runners total. "
      f"Of the {len(frameA_runners_readable)} that are ORB-readable, {len(never_fillable)} were NEVER fillable "
      f"(no 09:45-10:00 bar reached the opening-range high) — they ran on the gap day / later without ever "
      f"triggering the live stop-buy order. {len(frameA_runners_unreadable)} frame-A runners are ORB-unreadable "
      f"(fillability unknown): " + ", ".join(f"{r['ticker']} {r['scan_date']}" for r in frameA_runners_unreadable))
    if never_fillable:
        p("  never-fillable frame-A runners: " + ", ".join(f"{r['ticker']} {r['scan_date']} (run_xadr={r['run_xadr']:.1f}, alerted={bool(r['alerted'])})" for r in never_fillable))
    p("")

    # the two study passes
    results_Aprime, discA, heldA, bwA, btA = run_pass(readable, "runner5", "runner8", SEED)
    results_B, discB, heldB, bwB, btB = run_pass(rb_ok, "runnerB5", "runnerB8", SEED)
    p(f"frame A' (readable-B pop) best week = {bwA}, best two = {btA}")
    p(f"frame B best week = {bwB}, best two (by run_xadr_B) = {btB}")
    p("")

    # published frame-A verdicts, for the third reference column
    published = {}
    with (HERE / "results.tsv").open() as fh:
        cols = fh.readline().rstrip("\n").split("\t")
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            rr = dict(zip(cols, parts))
            published[rr["feature"]] = rr.get("verdict", "")

    p("PER-FEATURE (readable-B population; rates = share >= 5 ADR in each frame):")
    p("feature | when | n | frame A' (readable-B) fav/rest | frame A' verdict | frame B fav/rest | frame B verdict | published frame-A verdict (all 667) | CHANGED vs A'?")
    n_changed = 0
    change_rows = []
    for ra, rb in zip(results_Aprime, results_B):
        col = ra["feature"]
        va = ra.get("verdict", "no data")
        vb = rb.get("verdict", "no data")
        va_s = va.split(",")[0].split(" (")[0].strip()
        vb_s = vb.split(",")[0].split(" (")[0].strip()
        changed = va_s != vb_s
        if changed:
            n_changed += 1
            change_rows.append((col, va, vb))
        p(f"{col} | {ra['when']} | {ra.get('n_disc','-')} | {fmt_rate(ra)} | {va} | {fmt_rate(rb)} | {vb} | {published.get(col,'?')} | {'CHANGED' if changed else ''}")
    p("")
    p(f"verdicts changed between frame A' (readable-B) and frame B: {n_changed} of {len(results_Aprime)}")
    for col, va, vb in change_rows:
        p(f"  CHANGED: {col} — frame A' [{va}] -> frame B [{vb}]")
    p("")

    # timing composition: alerts first passing 09:45-09:55 vs inside the window vs rejected, in frame B
    pop = {(r["ticker"], r["scan_date"]): r for r in load_psv(HERE / "pop.tsv")}
    def bucket(hhmm):
        if not hhmm:
            return None
        if hhmm < "09:30":
            return "pre0930"
        if hhmm < "09:45":
            return "0930-0944"
        return "0945+"
    for r in rb_ok:
        pr = pop.get((r["ticker"], r["scan_date"]), {})
        r["first_pass_bucket"] = bucket(pr.get("first_pass_time"))
    p("TIMING COMPOSITION, frame B (alerted, readable-B rows with a computed RUN_B only):")
    for buck, label in (("pre0930", "first passed before the open"), ("0930-0944", "first passed 09:30-09:44 (inside the order window)"), ("0945+", "first passed 09:45+ (after the order window closed)")):
        g = [r for r in rb_ok if r["alerted"] and r["first_pass_bucket"] == buck]
        if g:
            p(f"  {label}: n {len(g)}, runnerB5 {sum(r['runnerB5'] for r in g)} ({100*rate([r['runnerB5'] for r in g]):.1f}%), "
              f"filled {sum(r['filled'] for r in g)}/{len(g)}")
    g_rej = [r for r in rb_ok if not r["alerted"]]
    p(f"  rejected rows (readable-B, has RUN_B): n {len(g_rej)}, runnerB5 {sum(r['runnerB5'] for r in g_rej)} ({100*rate([r['runnerB5'] for r in g_rej]):.1f}%)")
    p("")

    # labelled EPs: orb readability + fill status
    p("LABELLED EPs — ORB readability / fill / frame-B outcome:")
    idx = {(r["ticker"], r["scan_date"]): r for r in rows}
    for t, d in LABELLED:
        r = idx.get((t, d))
        if r is None:
            p(f"  {t} {d}: not in population")
            continue
        if not r["orb_readable"]:
            p(f"  {t} {d}: ORB-unreadable (n0930={r['n0930_bars']}, n0945={r['n0945_bars']})")
        elif not r["filled"]:
            p(f"  {t} {d}: readable, NEVER FILLED (order would have been cancelled unfilled at 10:00)")
        else:
            rb = r["run_xadr_B"]
            p(f"  {t} {d}: filled at {r['fill_hhmm']}, run_xadr (frame A, from close) = {r['run_xadr']:.2f}, "
              f"run_xadr_B (frame B, from ORB fill) = {rb:.2f}" if rb is not None else f"  {t} {d}: filled at {r['fill_hhmm']}, run_xadr_B incomplete")
    p("")

    text = "\n".join(out) + "\n"
    (HERE / "orb_results_out.txt").write_text(text)
    print(text)

    # write orb_results.tsv (frame B) and orb_results_A.tsv (frame A' on the same population)
    keys = ["feature", "when", "name", "n_disc", "n_fav", "rate_fav", "n_rest", "rate_rest", "diff", "auc", "p_disc",
            "held_n_fav", "held_rate_fav", "held_n_rest", "held_rate_rest", "held_sign", "held_ok",
            "drop_week_diff", "drop_week_p", "drop_two_diff", "drop_two_p", "labelled_in_fav", "labelled_n", "verdict"]
    for fname, res in (("orb_results.tsv", results_B), ("orb_results_A.tsv", results_Aprime)):
        with (HERE / fname).open("w") as fh:
            fh.write("\t".join(keys) + "\n")
            for r in res:
                fh.write("\t".join("" if r.get(k) is None else (f"{r[k]:.4f}" if isinstance(r.get(k), float) else str(r[k])) for k in keys) + "\n")

    with (HERE / "orb_outcomes.tsv").open("w") as fh:
        fh.write("ticker\tscan_date\tblock\talerted\torb_readable\tfilled\tfill_hhmm\ttouch_count\trun_xadr\trunner5\trun_xadr_B\trunnerB5\trunnerB8\n")
        for r in scored_A:
            rb_s = "" if r.get("run_xadr_B") is None else f"{r['run_xadr_B']:.3f}"
            fh.write(f"{r['ticker']}\t{r['scan_date']}\t{r['block']}\t{int(r['alerted'])}\t{r['orb_readable']}\t{r.get('filled')}\t{r.get('fill_hhmm') or ''}\t"
                      f"{r.get('touch_count')}\t{r['run_xadr']:.3f}\t{r['runner5']}\t"
                      f"{rb_s}\t{r.get('runnerB5')}\t{r.get('runnerB8')}\n")


if __name__ == "__main__":
    main()
