#!/usr/bin/env python3
"""#327 — ENTRY-SIGNAL hypothesis test (operator 2026-06-18).

Does a parameterized coil-readiness signal — RMV + daily range + volume gates, plus a CONSECUTIVE-
DAY COUNT (the operator's "low RMV for 3 days") and optional contraction/dry-up TRENDS — time the
entry to the coil's apex, where expansion is imminent and the asymmetric bet pays (capture the
expansion, or a quick tight-stop loss)?

Design (advisor-hardened 2026-06-18) — a HYPOTHESIS TEST, not a grid beauty contest:
  • The question is "does the COUNT/TREND add over a SINGLE tight day?" → report CURVES
    (capture/stop/MFE vs N = 1,2,3,4), not the argmax cell.
  • Baselines are STOP-MATCHED — the #270-Step-0 trap was that an apparent RMV edge was a STOP
    artifact; every signal comparison here holds the stop FIXED so the count earns its keep only
    if it adds beyond the stop.
  • Per-cell N printed; cells below MIN_CELL fires are flagged (●) and must NOT be read.
  • Entry quality = capture-rate + UNCAPPED MFE/risk (the harvest buries good entries — see the
    anticipate arm's +2.2R MFE → −1.2R; #270-Step-0: win-rate is the clean signal). Harvested
    realized R is a SECONDARY column only.
  • ONE entry per fire, close-of-Nth tight day (pure anticipate); NO reenter, NO timing blend.
  • Survivorship: every fire is settled (capture / stop / open) incl. names that never expand.
9M cohort, re-anchored (gap_day → the 9M-day low). Reuses flag_detector._compute_rmv/_atr_14 +
the #327 cohort loaders. N≈77 → DIRECTIONAL; the forward shadow validates the chosen REGION, not a
tuned cell. Read-only, gate-safe. Usage: python scripts/_327_entry_signal.py
"""
import importlib.util
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), HERE / name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


r327 = _load("_327_replay.py")          # load_cohort/load_daily + consolidation_scan + idx_of_date
from agents.market_intelligence.flag_detector import _atr_14   # ATR for the stop-width variants
from agents.market_intelligence import anticipation as _ant   # SINGLE-SOURCE of the entry gate

# ── CONFIG — the knobs to set/sweep (operator) ───────────────────────────────
RMV_MAX = 30           # rmv_5d ≤ this = contracted
RANGE_MAX = 0.05       # daily (H−L)/C ≤ this
VOL_MAX = 1.0          # volume ≤ this × ADV20 (the quiet "rest")
COUNTS = (1, 2, 3, 4)  # consecutive tight-day counts to compare (the hypothesis axis)
STOPS = ("coiled_low", "atr_1.5x", "structural")  # stop widths (the #270-Step-0 dominant lever)
TARGET_R = 3.0         # "capture" = MFE reaches +TARGET_R before the stop (the expansion)
SCAN = 15              # trading days after the 9M anchor to look for the coil
WINDOW = 12            # forward bars to settle the bet
MIN_CELL = 10          # cells with fewer fires are flagged ● and not read


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else float("nan")


def _adv(vols, i, n=20):
    return sum(vols[max(0, i - n + 1):i + 1]) / min(i + 1, n)


def rmv_rows(bars):
    return [{"high_price": b["h"], "low_price": b["l"], "close": b["c"]} for b in bars]


def is_tight(bars, rr, vols, i, rmv_max=RMV_MAX, range_max=RANGE_MAX, vol_max=VOL_MAX):
    """Core feature gate: contracted RMV + tight range + quiet volume (thresholds parameterized so
    the robustness sweep can turn each knob). DELEGATES to anticipation.is_entry_tight — the ONE
    production source the live entry-watch shares, so the sweep and the shadow can't drift
    (tests/test_consolidation_entry_signal.py pins it). `rr` is this script's rmv_rows(bars), 1:1
    with anticipation.bars_to_rmv_rows."""
    return _ant.is_entry_tight(bars, rr, vols, i, rmv_max=rmv_max, range_max=range_max, vol_max=vol_max)


def run_of_tight(flags, lo, hi, n, contraction=None):
    """First index in (lo, hi] ending a run of n consecutive tight days. With contraction set, the
    run must ALSO be non-increasing in that per-day series (range or volume) — the 'winding' trend."""
    for i in range(lo, hi + 1):
        win = range(i - n + 1, i + 1)
        if win.start <= lo - 1:
            continue
        if not all(flags[j] for j in win):
            continue
        if contraction is not None and not all(
                contraction[j] <= contraction[j - 1] for j in win if j - 1 >= lo - 1):
            continue
        return i
    return None


def bet_outcome(bars, ai, end_idx, stop):
    """The asymmetric bet from a close-of-Nth entry under a fixed stop. DELEGATES to the production
    single-source anticipation.entry_bet_outcome (pinned by tests/test_consolidation_entry_settle.py)
    so the forward-shadow settlement and this sweep can't drift. `end_idx` is always the last index
    here (fires_for passes len(bars)-1), which the production fn reads to natively."""
    return _ant.entry_bet_outcome(bars, ai, stop, target_r=TARGET_R, window=WINDOW)


def stop_value(bars, rr, ai, run_lo, kind):
    entry = bars[ai]["c"]
    if kind == "coiled_low":
        return bars[ai]["l"]
    if kind == "atr_1.5x":
        atr = _atr_14(rr, ai)
        return (entry - 1.5 * atr) if atr else None
    if kind == "structural":                      # the base low over the coil so far
        return min(bars[j]["l"] for j in range(run_lo, ai + 1))
    return None


def fires_for(cohort, daily, n, stop_kind, use_trend=False,
              rmv_max=RMV_MAX, range_max=RANGE_MAX, vol_max=VOL_MAX):
    """One fire per name: the first N-consecutive-tight run after the 9M anchor (optionally with a
    range-CONTRACTION trend). Settle the bet under stop_kind. Returns list of (ticker, outcome, mfe_R)."""
    out = []
    for c in cohort:
        bars = daily.get(c["ticker"])
        if not bars:
            continue
        ai0 = r327.idx_of_date(bars, c["alert_date"])
        if ai0 is None:
            continue
        bo, _scan = r327.consolidation_scan(bars, ai0)
        hi = (bo["breakout_idx"] - 1) if bo else min(ai0 + SCAN, len(bars) - 1)
        lo = ai0 + 1
        if hi - lo < n:
            continue
        rr = rmv_rows(bars)
        vols = [b["v"] for b in bars]
        flags = {i: is_tight(bars, rr, vols, i, rmv_max, range_max, vol_max) for i in range(lo, hi + 1)}
        contraction = ({i: (bars[i]["h"] - bars[i]["l"]) / bars[i]["c"] for i in range(lo, hi + 1)}
                       if use_trend else None)
        ai = run_of_tight(flags, lo, hi, n, contraction)
        if ai is None or ai > len(bars) - 1 - 5:          # settleable: ≥5 fwd bars
            continue
        sv = stop_value(bars, rr, ai, ai - n + 1, stop_kind)
        res = bet_outcome(bars, ai, len(bars) - 1, sv)
        if res:
            out.append((c["ticker"], res[0], res[1]))
    return out


def cell(fires):
    if not fires:
        return "    ·    "
    n = len(fires)
    cap = sum(1 for _, o, _ in fires if o == "capture")
    stp = sum(1 for _, o, _ in fires if o == "stop")
    mfe = _median([r for _, _, r in fires])
    flag = "●" if n < MIN_CELL else " "
    return f"{flag}{cap*100//n:>2}%cap {stp*100//n:>2}%st mfe{mfe:+.1f} n{n:<2}"


def _cap(fires):
    """(capture%, median mfe_R, n) for a fire list."""
    if not fires:
        return (0, float("nan"), 0)
    n = len(fires)
    return (sum(1 for _, o, _ in fires if o == "capture") * 100 // n,
            _median([r for _, _, r in fires]), n)


def robustness(cohort, daily, stop="coiled_low"):
    """One knob at a time (others at default), fixed stop: does the N-count effect (N=3 beats N=1)
    survive, or is it a lone spike at one threshold? Δ = N3−N1 capture% (stop-matched)."""
    print(f"\n4. ROBUSTNESS SWEEP — does the N-count effect survive turning each knob? "
          f"(stop={stop}; cells = cap%/mfe-R/n; ●=n<{MIN_CELL}; Δ=N3−N1 cap%)")

    def line(label, **kw):
        cells, caps = [], {}
        for n in (1, 2, 3):
            cap, mfe, k = _cap(fires_for(cohort, daily, n, stop, **kw))
            caps[n] = cap
            flag = "●" if k < MIN_CELL else " "
            cells.append(f"{flag}N{n}:{cap:>2}%/{mfe:+.1f}/n{k:<2}")
        print(f"   {label:<14}" + " ".join(cells) + f"  Δ{caps[3]-caps[1]:+d}pp")

    print("   -- vary RMV_MAX (range≤5%, vol≤1.0×) --")
    for r in (20, 30, 40):
        line(f"rmv≤{r}", rmv_max=r, range_max=0.05, vol_max=1.0)
    print("   -- vary RANGE_MAX (rmv≤30, vol≤1.0×) --")
    for p in (0.04, 0.05, 0.07):
        line(f"range≤{p:.0%}", rmv_max=30, range_max=p, vol_max=1.0)
    print("   -- vary VOL_MAX (rmv≤30, range≤5%) --")
    for v in (0.7, 1.0):
        line(f"vol≤{v}×", rmv_max=30, range_max=0.05, vol_max=v)
    print("   ROBUST if Δ stays POSITIVE across the knobs (N=3 beats N=1 broadly); FRAGILE if it "
          "only appears at one setting.")


def main():
    cohort = r327.load_cohort()
    daily = r327.load_daily()
    print("#327 — ENTRY-SIGNAL hypothesis test (9M cohort; RMV+range+vol gate × consecutive-count "
          "× stop)\n")
    print(f"CONFIG: tight = rmv_5d≤{RMV_MAX} & range≤{RANGE_MAX:.0%} & vol≤{VOL_MAX}×ADV20  | "
          f"capture = MFE hits +{TARGET_R:.0f}R before stop | window {WINDOW}d | ● = n<{MIN_CELL} (don't read)\n")

    # ── 1. THE COUNT CURVE, STOP-MATCHED (the hypothesis: does N add over N=1 at a FIXED stop?) ──
    print("1. COUNT CURVE — capture% / stop% / median uncapped MFE-R / n, by consecutive-count N "
          "(rows) × stop (cols, FIXED per col):")
    print(f"   {'N':<4}" + "".join(f"{s:<24}" for s in STOPS))
    grid = {}
    for n in COUNTS:
        cells = []
        for s in STOPS:
            f = fires_for(cohort, daily, n, s)
            grid[(n, s)] = f
            cells.append(cell(f).ljust(24))
        print(f"   {n:<4}" + "".join(cells))
    print("   READ DOWN each column (stop fixed): does capture% / MFE-R RISE with N? "
          "monotone-up = the count adds; flat/noisy = it doesn't (the #270-Step-0 caution).")

    # ── 2. STOP at fixed N (the dominant lever per #270-Step-0 — for context, not the headline) ──
    print("\n2. STOP CURVE at N=2 (context — the prior finding was the STOP dominates):")
    for s in STOPS:
        f = grid.get((2, s)) or fires_for(cohort, daily, 2, s)
        print(f"   {s:<14}{cell(f)}")

    # ── 3. TREND GATE — does requiring a CONTRACTING range across the run beat flat-tight? ──
    print(f"\n3. TREND GATE — flat-tight vs range-CONTRACTING run (N=3, stop=structural), stop-matched:")
    flat = fires_for(cohort, daily, 3, "structural", use_trend=False)
    trend = fires_for(cohort, daily, 3, "structural", use_trend=True)
    print(f"   flat-tight       {cell(flat)}")
    print(f"   +contracting     {cell(trend)}")
    print("   (does the winding-tighter trend lift capture% / MFE-R over flat-tight at the SAME N+stop?)")

    robustness(cohort, daily)

    print("\nGUARDRAIL: N≈77 in-sample, multi-knob → DIRECTIONAL. The deliverable is the SHAPE of the "
          "curves (does count/trend add, at matched stop) + a robust REGION, NOT a tuned cell; the "
          "forward shadow validates. ● cells (<{}) are noise.".format(MIN_CELL))


if __name__ == "__main__":
    main()
