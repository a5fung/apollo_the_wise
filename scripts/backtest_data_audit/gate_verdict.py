#!/usr/bin/env python3
"""STEP 0 gate verdict — reads the consoles `run_all.sh` saved and prints the G1..G10 table of docs/methodology/backtest_data_standard.md §2
with PASS / REFUSE / REPORT per gate. Exit 2 when any gate REFUSES, else 0. Pure text parsing; no data file is opened here, so a
missing console reads as 'not run' (REPORT), never as PASS.

  python3 scripts/backtest_data_audit/gate_verdict.py OUT_DIR --label A
"""
import argparse
import re
import sys
from pathlib import Path

UNKNOWN_SHARE_MAX = 0.02      # of admitted member-nights (security_type_check --max-unknown-share)
LIQUID_RATIO_MIN = 0.97       # liquid names per session vs the richer export
UNTYPED_LIQUID_TRIPWIRE = 0.05  # universe_check: share of liquid symbols with no type (report only)


def num(s):
    return int(s.replace(",", ""))


def read(out, name):
    p = Path(out) / f"{name}.console.txt"
    return p.read_text(errors="replace") if p.exists() else None


def first(pattern, text, flags=0):
    m = re.search(pattern, text or "", flags)
    return m


def step_rc(out):
    log = Path(out) / "run_all.log"
    rcs = {}
    if log.exists():
        for m in re.finditer(r"^\s+(\S+)\s+rc=(\d+)", log.read_text(), re.M):
            rcs[m.group(1)] = int(m.group(2))
    return rcs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--label", default="A")
    a = ap.parse_args()
    out, L = a.out, a.label
    rcs = step_rc(out)
    rows = []  # (gate, status, reading)

    def add(gate, status, reading):
        rows.append((gate, status, reading))

    # ---- crashed lenses: a gate whose lens did not finish is UNKNOWN, never PASS (an absent line must not read as 0) ---------
    for name, rc in sorted(rcs.items()):
        if rc not in (0, 3) and not name.startswith("selftest_"):
            add(f"X crashed lens {name}", "REFUSE", f"rc={rc}: its gate is unknown; read {name}.console.txt (a lens must exit 0, or 3 for its own refusal)")

    # ---- selftests -------------------------------------------------------------------------------------------------------
    st = [k for k in rcs if k.startswith("selftest_")]
    bad = [k for k in st if rcs[k] != 0]
    add("S0 selftests", "REFUSE" if (bad or not st) else "PASS",   # 10-23 critic fix: no selftest = no positive control = REFUSE
        f"{len(st) - len(bad)} of {len(st)} selftests pass" + (f"; failing: {', '.join(bad)}" if bad else ""))

    # ---- G1 integrity (universe console, primary section = first occurrence) -------------------------------------------------
    u = read(out, "universe")
    if u:
        bad1 = []
        for key, pat in [("dup keys", r"duplicate \(ticker,date\) keys: ([\d,]+) rows"),
                         ("ohlc", r"outside \[low,high\]: ([\d,]+) rows"),
                         ("nan", r"NaN in OHLCV: ([\d,]+) rows"),
                         ("weekend", r"weekend bars: ([\d,]+) rows")]:
            m = first(pat, u)
            if m is None:
                bad1.append(f"{key}=LINE MISSING")      # 10-23 critic fix: an absent line is not a zero
            elif num(m.group(1)) > 0:
                bad1.append(f"{key}={m.group(1)}")
        p = read(out, "price")
        mt = first(r"\[test_symbol\] tickers / rows: (\d+) / (\d+)", p)
        ts = f"; test symbols in the export: {mt.group(1)} tickers / {mt.group(2)} rows (universe excludes them)" if mt else ""
        add("G1 bar integrity", "REFUSE" if bad1 else "PASS", ("0 dup keys / 0 OHLC / 0 NaN / 0 weekend" if not bad1 else "; ".join(bad1)) + ts)
    else:
        add("G1 bar integrity", "REFUSE", "universe_check not run")

    # ---- G2 universe completeness ------------------------------------------------------------------------------------------
    lps = Path(out) / "universe" / "liquid_per_session_by_month.tsv"
    gone = first(r"KNOWN-GONE liquid names: ([\d,]+); missing or only partly in \S+: ([\d,]+) = ([\d.]+)%", u)
    if lps.exists():
        ratios = []
        for ln in lps.read_text().splitlines()[1:]:
            parts = ln.split("\t")
            try:
                ratios.append(float(parts[3]))
            except (IndexError, ValueError):
                pass
        if ratios:
            lo, hi = min(ratios), max(ratios)
            status = "PASS" if lo >= LIQUID_RATIO_MIN else "REFUSE"
            reading = f"liquid names per session, {L}/richer = {lo:.3f}..{hi:.3f} over {len(ratios)} months (PASS >= {LIQUID_RATIO_MIN})"
            if gone:
                reading += f"; known-gone names {gone.group(1)}, missing/partial {gone.group(2)} = {gone.group(3)}% (control level ~9%)"
            add("G2 universe completeness", status, reading)
        else:
            add("G2 universe completeness", "REPORT", "no monthly ratios")
    else:
        add("G2 universe completeness", "REPORT", "no richer export given: survivorship not measurable (pass the richer export as arg 3)")

    # ---- G3 duplicates --------------------------------------------------------------------------------------------------------
    d = read(out, "duplicate")
    mc = first(r"CONFIRMED strict pairs=(\d+)\s+matched days=([\d,]+)", d)
    ms = first(r"TEST 2 scaled twins.*?pairs=(\d+)", d)
    mp = first(r"persistent pairs \(>= 20 shared days\): (\d+)", u)
    if mc:
        conf, sc = int(mc.group(1)), (int(ms.group(1)) if ms else None)
        status = "PASS" if conf == 0 and (sc in (0, None)) else "REFUSE"
        add("G3 duplicate companies", status,
            f"confirmed strict pairs {conf} ({mc.group(2)} duplicate rows); scaled twins {sc if sc is not None else 'n/a'}; "
            f"universe_check persistent pairs (>= 20 days) {mp.group(1) if mp else 'n/a'} (PASS = 0 / 0 / 0)")
    else:
        add("G3 duplicate companies", "REFUSE", "duplicate_series_check not run, or its CONFIRMED line is missing")

    # ---- G4 identity ------------------------------------------------------------------------------------------------------------
    guard = Path(out) / "universe" / f"symbol_guard_{L}.tsv"
    mm = first(r"MISMATCH_different_series: (\d+) symbols = ([\d.]+)% of shared dollar volume; liquid \([^)]*\) (\d+)", u)
    reading = (f"breaks file {'written' if guard.exists() else 'MISSING'}: {guard}" if u else "universe_check not run")
    if mm:
        reading += f"; different company on the same symbol vs the richer export: {mm.group(1)} symbols, {mm.group(3)} liquid ({mm.group(2)}% of shared $vol) — recorded floor until FIGI-keyed"
    add("G4 identity", ("PASS" if guard.exists() else "REFUSE") if u else "REPORT", reading + " — pass it as --breaks to the runner")

    # ---- G5 corporate actions -------------------------------------------------------------------------------------------------
    p = read(out, "price")
    if p is not None:
        rc = rcs.get("price")
        ctr = re.findall(r"control (\S+): (\S+(?: \S+)*?)(?: \(|$)", p, re.M)
        disc = re.findall(r"DISCONTINUOUS: all / liquid: (\d+) / (\d+)", p)
        ctr_txt = "; ".join(f"{t}: {s.split(' as ')[0]}" for t, s in ctr) or "no control lines"
        ok_ctl = len(ctr) >= 3 and all("FLAGGED" in s_ for _, s_ in ctr)   # 10-23 critic fix: the spin-off controls must each be FLAGGED
        add("G5 corporate actions", "PASS" if (rc == 0 and ok_ctl) else "REFUSE",
            (f"lens crashed rc={rc}; " if rc not in (0, 3) else "") +
            f"controls — {ctr_txt}; discontinuous adjustment events (all/liquid): {', '.join('/'.join(x) for x in disc) or 'n/a'} → the RS/return exclusion list")
    else:
        add("G5 corporate actions", "REFUSE", "price_integrity_check not run")

    # ---- G6 security type -----------------------------------------------------------------------------------------------------
    s = read(out, "sectype")
    if s is not None:
        rc = rcs.get("sectype")
        mu = first(r"UNKNOWN type admitted[^:]*: ([\d,]+) tickers = ([\d.]+)% of admitted tickers; ([\d,]+) nights = ([\d.]+)% of admitted nights", s)
        mv = first(r"VERIFIED_NON_COMMON\s+(\d+)\s+([\d,]+)", s)
        mk = first(r"security type known for ([\d,]+) of ([\d,]+) liquid symbols \(([\d.]+)%\)", u)
        reading = (f"untyped admitted nights {mu.group(4)}% ({mu.group(3)} of nights; {mu.group(1)} tickers) — PASS <= {UNKNOWN_SHARE_MAX:.0%}" if mu else "no UNKNOWN line")
        if mv:
            reading += f"; hand-verified non-common: {mv.group(1)} tickers / {mv.group(2)} rows (count only — exclusion is the operator's fork)"
        if mk:
            untyped = 1 - float(mk.group(3)) / 100
            reading += f"; universe_check tripwire: {untyped:.1%} of {mk.group(2)} liquid symbols untyped ({'over' if untyped > UNTYPED_LIQUID_TRIPWIRE else 'under'} {UNTYPED_LIQUID_TRIPWIRE:.0%})"
        add("G6 security type", "PASS" if (rc == 0 and mu is not None) else "REFUSE", (f"lens crashed rc={rc}; " if rc not in (0, 3) else "") + reading)
    else:
        add("G6 security type", "REPORT", "security_type_check skipped (missing sidecar)")

    # ---- G7 pit lint ------------------------------------------------------------------------------------------------------------
    pl = read(out, "pit_lint")
    ml = first(r"(\d+) items: (\d+) confirmed, (\d+) suspected, (\d+) ruled out; (\d+) confirmed/suspected items have NO guarding test; anchors missing: (\d+)", pl)
    if ml:
        add("G7 point-in-time lint", "REFUSE" if int(ml.group(6)) > 0 else "PASS",
            f"{ml.group(1)} items ({ml.group(2)} confirmed, {ml.group(3)} suspected, {ml.group(4)} ruled out); {ml.group(5)} unguarded; anchors missing {ml.group(6)}")
    else:
        add("G7 point-in-time lint", "REPORT", f"pit_lint lint rc={rcs.get('pit_lint', 'not run')}")

    # ---- G8 sealed-trade dependence ---------------------------------------------------------------------------------------------
    t = read(out, "trade_impact")
    if t:
        ma = first(r"trades entered after the cutoff [^:]*: (\d+)", t)
        mh = first(r"trades whose hold runs past the last bar kept[^:]*: (\d+)", t)
        mn = first(r"trades n=([\d,]+)", t)
        if ma and mh:
            n_after, n_hold = int(ma.group(1)), int(mh.group(1))
            add("G8 sealed-trade dependence", "PASS" if n_after == 0 and n_hold == 0 else "REFUSE",
                f"of {mn.group(1) if mn else '?'} trades: {n_after} entered after the cutoff, {n_hold} holds run past the last kept bar (PASS = 0 / 0, else censor and print the count beside the headline)")
        else:
            add("G8 sealed-trade dependence", "REPORT", "trade_impact ran but the two lines were not found")
    else:
        add("G8 sealed-trade dependence", "REPORT", "no trade list given (TRADES=...) — run trade_impact.py on every list you quote")

    # ---- G9 calendar / early close ------------------------------------------------------------------------------------------
    c = read(out, "pit_calendar")
    mm9 = first(r"MINUTE TREE: on early-close days ([\d,]+) of ([\d,]+) minute bars \(([\d.]+)%\) are after-hours", c)
    mcal = re.findall(r"(\d{4}): (\d+) sessions \(NYSE (\d+)\) (ok|partial year|\S+)", c or "")
    offcal = [y for y, got, nyse, st in mcal if st not in ("ok", "partial year")]
    if c:
        add("G9 calendar + early close", "REFUSE" if offcal else "PASS",
            (f"sessions per year match NYSE ({len(mcal)} years)" if not offcal else f"session count off NYSE in {', '.join(offcal)}") +
            (f"; after-hours minute bars on early-close days: {mm9.group(1)} of {mm9.group(2)} ({mm9.group(3)}%) → print beside every fill statistic until F1 is fixed" if mm9 else "; minute tree not scanned (FAST=1 or no minutes dir)"))
    else:
        add("G9 calendar + early close", "REPORT", "pit_lint calendar not run")

    # ---- G10 overlap parity ----------------------------------------------------------------------------------------------------
    o = read(out, "pit_overlap")
    mo = first(r"universe members per night \(median over (\d+) nights\): era A ([\d,]+), era B ([\d,]+); in both ([\d,]+); only A ([\d,]+); only B ([\d,]+)", o)
    mv2 = first(r"vendor agreement on ([\d,]+) common ticker-days: ([^;]+;[^;]+)", o)
    if mo:
        both, b = num(mo.group(4)), num(mo.group(3))
        add("G10 overlap parity", "REPORT", f"members per night A {mo.group(2)} / B {mo.group(3)}, in both {mo.group(4)} = {both / b:.1%} of B (target >= 98% after the rebuild); only-A {mo.group(5)}, only-B {mo.group(6)}"
            + (f"; vendor: {mv2.group(2).strip()}" if mv2 else ""))
    else:
        add("G10 overlap parity", "REPORT", "overlap not run (needs the richer era dir)")

    # ---- W2 cost line (not a gate: the number every headline must carry) ----------------------------------------------------
    e = read(out, "pit_entries")
    mw = first(r"W2 .*?n ([\d,]+): stop width median ([\d.]+%).*?0\.1% of price per side = ([\d.]+) R median, ([\d.]+) R mean, ([\d.]+) R at P90", e)
    if mw:
        add("W2 exit-slippage cost", "REPORT", f"n {mw.group(1)} fills, median stop width {mw.group(2)}: 0.1% per exit leg = {mw.group(3)}R median / {mw.group(4)}R mean / {mw.group(5)}R at P90 — quote every R at 0 / 0.1 / 0.2%")

    # ---- print ----------------------------------------------------------------------------------------------------------------
    print(f"\nSTEP 0 DATA GATE — verdict for export label {L} (consoles in {out})")
    w = max(len(g) for g, _, _ in rows)
    for g, st_, rd in rows:
        print(f"  {g:<{w}}  {st_:<7} {rd}")
    # 10-23 critic fix: a REQUIRED gate left at REPORT (not run / line unreadable / no richer export for G2) refuses too.
    _req = ("S0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8")
    rows = [(g, "REFUSE" if (st_ == "REPORT" and g.split()[0] in _req) else st_, r) for g, st_, r in rows]
    refusals = [g for g, st_, _ in rows if st_ == "REFUSE"]
    if refusals:
        print(f"\nVERDICT: REFUSED by {len(refusals)} gate(s): {', '.join(refusals)} — no registered read opens an outcome on this export until each passes.")
        return 2
    # 10-23 critic fix: a REQUIRED gate that did not run or could not read its line is a refusal, never a pass.
    required = ("S0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8")
    unrun = [g for g, st_, _ in rows if st_ == "REPORT" and g.split()[0] in required]
    if unrun:
        print(f"\nVERDICT: REFUSED — required gate(s) not measured: {', '.join(unrun)} (a gate that did not run is not a pass).")
        return 2
    print("\nVERDICT: PASS — every required gate passed; REPORT lines go beside the read's headline, verbatim.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
