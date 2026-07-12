#!/usr/bin/env python3
"""ADR 0023 Card 2 — #306 STEP-2 winner-harvest sweep (read-only evidence lane).

Replays the CLOSED MAGNA53 cohort (fills 5/01–7/02) bar-by-bar through
`exit_logic.apply_daily_exit_step`, sweeping three exit axes and RANKING cells by
how much of each winner's peak they keep. NOTHING here changes live behavior — it
is a pure replay of known fills. Exit discipline = THE LINE; STEP-3 (whether to adopt
any parameterization) is operator fork F1 off this doc.
See docs/decisions/0023-exit-stop-mechanics.md (PART A).

Axes (COARSE by design — rank, don't fine-tune):
  A. peak-lock giveback : arm ∈ {+6%, +8%, +10%, +2R} × floor ∈ {40%, 50%, 60%}   (+ OFF)
                          → the NEW Card-1 `giveback_floor` hook
  B. trail mode         : sma  |  ema_10_20 (#396)  |  sma_10_20_handoff (Card 2)
  C. partial size       : None (⅓, current)  |  0.40  |  0.50   (`scale_fraction`)

Cohort split (by ACTUAL partial_taken): HARVEST set = partial-taken names (the winners
+ 2 round-trip-to-loss); CONTROL = same-day −1R losers (should be ~unaffected — a day-1
intraday stop can't be moved by any multi-day mechanic, so the sweep short-circuits them).

Data discipline (eval_alpaca_skills): daily bars = Polygon grouped/range aggs
adjusted=true; every run FINGERPRINTED (symbol-set·feed·adjustment·daily·range·US) and
CACHED to scripts/eval_data/306_bars_<fp>.csv so the run reproduces byte-for-byte.

Usage:
  # 1. (needs prod — POLYGON_API_KEY lives in apollo-market) fetch adjusted daily bars
  python scripts/_306_harvest_sweep.py --fetch-bars
  # 2. run the sweep off the cached cohort + bars CSVs → writes the analysis doc
  python scripts/_306_harvest_sweep.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

from agents.market_intelligence.broker.exit_logic import iter_exit_ladder, seed_exit_state  # noqa: E402

EVAL_DIR = REPO / "scripts" / "eval_data"
COHORT_CSV = EVAL_DIR / "306_cohort_2026-07-08.csv"
DOC_OUT = REPO / "docs" / "analysis" / "306_step2_sweep_2026-07-08.md"
PROD_HOST = "apollo@87.99.134.162"
BAR_BUFFER_DAYS = 21  # fetch a little past the actual close so a looser rule can play out

# ── Axis definitions (coarse grid) ──────────────────────────────────────────
A_ARMS = [
    ("gain", 0.06), ("gain", 0.08), ("gain", 0.10), ("r", 2.0),
]
A_FLOORS = [0.40, 0.50, 0.60]
B_TRAILS = ["sma", "ema_10_20", "sma_10_20_handoff"]
C_SCALES = [None, 0.40, 0.50]

BASELINE_CELL = {"a": None, "b": "sma", "c": None, "label": "BASELINE(sma·⅓·no-lock)"}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


# ── Cohort + bars I/O ────────────────────────────────────────────────────────
def load_cohort(path: Path = COHORT_CSV) -> list[dict]:
    out = []
    with path.open(newline="") as fh:
        for r in csv.DictReader(fh):
            out.append({
                "ticker": r["ticker"],
                "fill_date": r["fill_date"],
                "close_date": r["close_date"],
                "account_mode": r["account_mode"],
                "entry_price": _f(r["entry_price"]),
                "entry_shares": _f(r["entry_shares"]),
                "orig_stop": _f(r["orig_stop"]),
                "final_stop": _f(r["final_stop"]),
                "partial_taken": r["partial_taken"] in ("t", "true", "True", "1"),
                "actual_pnl": _f(r["actual_pnl"]),
                "peak_intraday": _f(r.get("peak_intraday")),
                "low_intraday": _f(r.get("low_intraday")),
                "n_running_closes": int(r["n_running_closes"] or 0),
            })
    return out


def compute_fingerprint(cohort: list[dict]) -> str:
    """symbol-set·feed·adjustment·timeframe·range·calendar → stable 8-char hash.
    adjustment=RAW (unadjusted): we replay recorded UNADJUSTED fills/stops, so bars must be
    on the same price basis — adjusted bars corrupt dividend names (deviates from ADR A1's
    RS-engine 'adjusted=true' convention, deliberately — see the doc's methodology note)."""
    syms = ",".join(sorted({t["ticker"] for t in cohort}))
    lo = min(t["fill_date"] for t in cohort)
    hi = max(t["close_date"] for t in cohort)
    key = f"{syms}·polygon·raw·daily·{lo}..{hi}·US"
    return hashlib.md5(key.encode()).hexdigest()[:8]


def bars_path(fp: str) -> Path:
    return EVAL_DIR / f"306_bars_{fp}.csv"


def _ranges(cohort: list[dict]) -> list[tuple[str, str, str]]:
    """(ticker, from, to) per trade — from fill_date to close_date + buffer (capped today)."""
    today = date.today()  # tz-ok: offline evidence script, calendar excluded from tz gate
    out = []
    for t in cohort:
        frm = t["fill_date"]
        to = min(_d(t["close_date"]) + timedelta(days=BAR_BUFFER_DAYS), today).isoformat()
        out.append((t["ticker"], frm, to))
    return out


def fetch_bars(cohort: list[dict]) -> Path:
    """Fetch adjusted daily bars for the cohort via inline python in apollo-market
    (POLYGON_API_KEY lives there) — mirrors scripts/_327_pull_minute.py. Read-only:
    Polygon aggs only, no DB write. Writes the fingerprinted CSV cache and returns its path."""
    fp = compute_fingerprint(cohort)
    out = bars_path(fp)
    pairs = _ranges(cohort)
    # pycode uses ONLY double quotes + json (double-quoted) so it can be single-quoted for ssh.
    # pycode MUST contain NO single quotes (it is wrapped in '...' for the ssh command);
    # dict keys use double quotes and values are lifted to locals before the f-string.
    pycode = (
        "import os,json,urllib.request,datetime as _dt\n"
        f"PAIRS={json.dumps(pairs)}\n"
        "KEY=os.environ[\"POLYGON_API_KEY\"]\n"
        "for t,f,to in PAIRS:\n"
        "    u=f\"https://api.polygon.io/v2/aggs/ticker/{t}/range/1/day/{f}/{to}?adjusted=false&sort=asc&limit=400&apiKey={KEY}\"\n"
        "    try:\n"
        "        rr=json.load(urllib.request.urlopen(u,timeout=30))\n"
        "    except Exception as e:\n"
        "        print(f\"ERR\\t{t}\\t{e}\");continue\n"
        "    for b in rr.get(\"results\",[]):\n"
        "        ds=_dt.datetime.fromtimestamp(b[\"t\"]/1000,_dt.timezone.utc).strftime(\"%Y-%m-%d\")\n"
        "        o=b[\"o\"];h=b[\"h\"];l=b[\"l\"];c=b[\"c\"];v=b[\"v\"]\n"
        "        print(f\"{t}\\t{ds}\\t{o}\\t{h}\\t{l}\\t{c}\\t{v}\")\n"
    )
    remote = "docker exec apollo-market python -c '" + pycode + "'"
    print(f"[fetch] {len(pairs)} tickers → {out.name} (fingerprint {fp})")
    res = subprocess.run(["ssh", PROD_HOST, remote], capture_output=True, text=True, timeout=600)
    if res.returncode != 0:
        print(res.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"fetch failed (rc={res.returncode})")
    rows, errs = [], []
    for ln in res.stdout.splitlines():
        p = ln.split("\t")
        if p and p[0] == "ERR":
            errs.append(ln)
            continue
        if len(p) == 7:
            rows.append(p)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "date", "o", "h", "l", "c", "v"])
        w.writerows(rows)
    print(f"[fetch] wrote {len(rows)} bar rows; {len(errs)} fetch errors")
    for e in errs:
        print("  " + e)
    return out


def load_bars(path: Path) -> dict[str, list[dict]]:
    by = {}
    with path.open(newline="") as fh:
        for r in csv.DictReader(fh):
            by.setdefault(r["ticker"], []).append({
                "date": r["date"], "date_obj": _d(r["date"]),
                "o": _f(r["o"]), "h": _f(r["h"]), "l": _f(r["l"]),
                "c": _f(r["c"]), "v": _f(r["v"]),
            })
    for t in by:
        by[t].sort(key=lambda b: b["date_obj"])
    return by


# ── The replay (pure) ────────────────────────────────────────────────────────
def _giveback_kwargs(cell: dict, entry: float, orig_stop: float) -> dict:
    a = cell["a"]
    if a is None:
        return dict(giveback_arm_gain=None, giveback_arm_r=None,
                    giveback_floor_frac=None, giveback_risk_per_share=None)
    kind, val, floor = a["kind"], a["val"], a["floor"]
    if kind == "gain":
        return dict(giveback_arm_gain=val, giveback_arm_r=None,
                    giveback_floor_frac=floor, giveback_risk_per_share=None)
    return dict(giveback_arm_gain=None, giveback_arm_r=val, giveback_floor_frac=floor,
                giveback_risk_per_share=max(entry - orig_stop, 0.0001))


def replay(trade: dict, bars_by: dict[str, list[dict]], cell: dict) -> dict:
    """Replay one trade under one cell (MARGINAL-EFFECT model).

    An alt rule can only differ from what actually happened by triggering an EARLIER exit
    (a peak-lock / tighter trail / bigger scale raises the effective stop or takes profit
    sooner). So:
      - if the rule closes STRICTLY BEFORE the real close_date → use the replay pnl at that
        exit (the harvested outcome);
      - otherwise the trade rode to its real exit → anchor to `actual_pnl` (NOT a force-close
        at the last daily close, which fabricates pnl).
    This makes the BASELINE cell reproduce reality for every name it doesn't close early, so
    `marginal = alt_pnl − actual_pnl` isolates the rule's true harvest and is robust to the
    absolute-fidelity gaps (adjusted prices, backtest-pure-vs-live, daily granularity).
    Same-day / no-multiday-bar trades can't be moved by any multi-day mechanic → actual."""
    entry, shares = trade["entry_price"], trade["entry_shares"]
    orig_stop, fill, close_d = trade["orig_stop"], trade["fill_date"], trade["close_date"]
    actual = trade["actual_pnl"]
    fill_o, close_o = _d(fill), _d(close_d)
    hold_bars = [b for b in bars_by.get(trade["ticker"], [])
                 if fill_o < b["date_obj"] <= close_o]
    if not hold_bars:
        return {"alt_pnl": actual, "marginal": 0.0, "early": False,
                "exit_reason": "same_day_actual", "exit_date": close_d, "exit_price": None,
                "replayed": False, "peak_close": None, "n_bars": 0}

    gb = _giveback_kwargs(cell, entry, orig_stop)
    # #445: seed + carry live in the ONE driver; this consumer keeps only its
    # marginal-effect fold (early-exit vs rode-to-actual anchoring).
    state = seed_exit_state(alert_date=fill_o, entry_price=entry,
                            hard_stop=orig_stop, remaining_shares=shares)
    peak_close = max((b["c"] for b in hold_bars), default=entry)
    bars = ((b["date_obj"], {"l": b["l"], "c": b["c"]}) for b in hold_bars)
    for i, day, step in iter_exit_ladder(
            state, bars, trail_mode=cell["b"], scale_fraction=cell["c"], **gb):
        if step.closed and day < close_o:
            return {"alt_pnl": step.new_total_pnl, "marginal": step.new_total_pnl - actual,
                    "early": True, "exit_reason": step.close_reason,
                    "exit_date": hold_bars[i]["date"],
                    "exit_price": step.close_price, "replayed": True,
                    "peak_close": peak_close, "n_bars": i + 1}
        if step.closed:  # closed on/after the real exit day → it rode to the actual exit
            break
    # never triggered an earlier exit → the trade played out exactly as it actually did
    return {"alt_pnl": actual, "marginal": 0.0, "early": False,
            "exit_reason": "rode_to_actual", "exit_date": close_d, "exit_price": None,
            "replayed": True, "peak_close": peak_close, "n_bars": len(hold_bars)}


def peak_close_potential(trade: dict, rep: dict) -> float:
    """$ a close-based rule could keep at best = (peak daily close − entry) × shares, ≥0."""
    pc = rep.get("peak_close")
    if pc is None:  # same-day → use intraday peak if present, else actual upside 0
        pc = trade.get("peak_intraday") or trade["entry_price"]
    return max(0.0, (pc - trade["entry_price"]) * trade["entry_shares"])


# ── Grid + metrics ───────────────────────────────────────────────────────────
def _clbl(c):
    return "⅓" if c is None else f"{c:g}"


def _arm_label(kind: str, val: float) -> str:
    """Axis-A arm label: gain arms as '+8%', R arms as '+2R'."""
    return f"+{int(val*100)}%" if kind == "gain" else f"+{val:g}R"


def build_grid() -> list[dict]:
    # Anchor baseline FIRST (off·sma·⅓ = today's live rules), then the no-lock B×C cells so
    # Axis B/C standalone effects are visible (with a loose-floor lock on, the lock's stop
    # dominates the trail and masks B). Then the full armed A×B×C grid.
    cells = [dict(BASELINE_CELL)]
    for b in B_TRAILS:
        for c in C_SCALES:
            if b == "sma" and c is None:
                continue  # == the baseline anchor already added
            cells.append({"a": None, "b": b, "c": c, "label": f"no-lock·{b}·{_clbl(c)}"})
    for kind, val in A_ARMS:
        for floor in A_FLOORS:
            for b in B_TRAILS:
                for c in C_SCALES:
                    arm_lbl = _arm_label(kind, val)
                    cells.append({
                        "a": {"kind": kind, "val": val, "floor": floor},
                        "b": b, "c": c,
                        "label": f"lock {arm_lbl}/{int(floor*100)}%·{b}·{_clbl(c)}",
                    })
    return cells


def sweep(cohort: list[dict], bars_by: dict[str, list[dict]]) -> dict:
    harvest = [t for t in cohort if t["partial_taken"]]
    control = [t for t in cohort if not t["partial_taken"]]
    grid = build_grid()
    actual_harvest = sum(t["actual_pnl"] for t in harvest)
    results = []
    for cell in grid:
        h_reps = [(t, replay(t, bars_by, cell)) for t in harvest]
        c_reps = [(t, replay(t, bars_by, cell)) for t in control]
        kept = sum(r["alt_pnl"] for _, r in h_reps)
        marginal = sum(r["marginal"] for _, r in h_reps)  # extra $ vs what actually happened
        n_early = sum(1 for _, r in h_reps if r["early"])
        denom = sum(peak_close_potential(t, r) for t, r in h_reps)
        cap = (kept / denom) if denom > 0 else 0.0
        ctrl_delta = sum(r["marginal"] for _, r in c_reps)
        results.append({"cell": cell, "kept": kept, "marginal": marginal, "capture": cap,
                        "n_early": n_early, "ctrl_delta": ctrl_delta, "h_reps": h_reps})
    return {"harvest": harvest, "control": control, "results": results,
            "actual_harvest": actual_harvest}


# ── Guardrails ───────────────────────────────────────────────────────────────
def _is_baseline(cell: dict) -> bool:
    return cell.get("a") is None


def _cell_by(results: list[dict], pred) -> dict | None:
    for r in results:
        if pred(r["cell"]):
            return r
    return None


def baseline_fidelity(sw: dict) -> list[dict]:
    """The BASELINE cell (sma·⅓·no-lock = today's live rules) should RIDE TO THE ACTUAL exit
    on every name (marginal 0). Where the backtest-pure sma triggers an EARLIER exit than the
    live path actually did, the baseline shows a spurious marginal — that name's harness
    reconstruction diverges from live and its sweep deltas deserve a skeptical eye. This is
    the credibility gate: few/small baseline divergences = the marginal metric is trustworthy."""
    base = _cell_by(sw["results"], _is_baseline)
    rows = []
    for t, r in base["h_reps"]:
        rows.append({"ticker": t["ticker"], "actual": t["actual_pnl"],
                     "replay": r["alt_pnl"], "resid": r["marginal"], "early": r["early"],
                     "reason": r["exit_reason"], "replayed": r["replayed"]})
    return rows


def named_cases(sw: dict, best: dict, names=("SMCI", "PURR", "CRSR", "IBM", "GOOGL", "BW", "RCAT")) -> list[dict]:
    best_map = {t["ticker"]: r for t, r in best["h_reps"]}
    tmap = {t["ticker"]: t for t in sw["harvest"]}
    rows = []
    for n in names:
        if n not in tmap:
            continue
        t, r = tmap[n], best_map[n]
        rows.append({
            "ticker": n, "entry": t["entry_price"], "peak_intra": t["peak_intraday"],
            "actual": t["actual_pnl"], "best": r["alt_pnl"], "marginal": r["marginal"],
            "best_exit": r["exit_reason"], "best_date": r["exit_date"],
        })
    return rows


def plateau_neighbors(sw: dict, best: dict) -> list[dict]:
    """The best cell must sit on a PLATEAU, not a spike: report the marginal-$ of cells sharing
    its trail+scale but at adjacent arm/floor. A collapse next door = artifact, reject."""
    bc = best["cell"]["a"]
    if bc is None:
        return []
    out = []
    for r in sw["results"]:
        c = r["cell"]
        if c.get("a") is None:
            continue
        if c["b"] == best["cell"]["b"] and c["c"] == best["cell"]["c"] \
           and c["a"]["kind"] == bc["kind"]:
            out.append({"arm": c["a"]["val"], "floor": c["a"]["floor"],
                        "marginal": r["marginal"], "capture": r["capture"],
                        "is_best": r is best})
    out.sort(key=lambda x: (x["arm"], x["floor"]))
    return out


def clipped_runners(sw: dict, best: dict, names=("BW", "CRSR", "RCAT", "IBM")) -> list[dict]:
    """Did the winning cell CLIP the biggest runners (exit far below the actual realized)?
    A lock that harvests round-trippers but shreds the true runners is a net fail (guardrail 4)."""
    best_map = {t["ticker"]: r for t, r in best["h_reps"]}
    tmap = {t["ticker"]: t for t in sw["harvest"]}
    rows = []
    for n in names:
        if n not in tmap:
            continue
        t, r = tmap[n], best_map[n]
        rows.append({"ticker": n, "actual": t["actual_pnl"], "best": r["alt_pnl"],
                     "clip": r["alt_pnl"] - t["actual_pnl"], "exit": r["exit_reason"]})
    return rows


# ── Doc ──────────────────────────────────────────────────────────────────────
def _fmt(x, d=0):
    return "—" if x is None else f"{x:,.{d}f}"


def write_doc(sw: dict, fp: str) -> None:
    # Rank by MARGINAL (extra $ vs what actually happened) — the robust treatment effect.
    results = sorted(sw["results"], key=lambda r: r["marginal"], reverse=True)
    base = _cell_by(sw["results"], _is_baseline)
    best = results[0]
    actual_h = sw["actual_harvest"]
    L = []
    L.append("# ADR 0023 Card 2 — #306 STEP-2 winner-harvest sweep\n")
    L.append(f"**2026-07-08 · read-only replay · bars fingerprint `{fp}` "
             f"(Polygon daily, UNADJUSTED) · #438/#306.**  \n")
    L.append(f"Cohort: {len(sw['harvest'])} partial-taken (HARVEST) + {len(sw['control'])} "
             f"same-day losers (CONTROL) = {len(sw['harvest'])+len(sw['control'])} closed trades, "
             "fills 5/01–7/02, all `paper`. Replay drives `exit_logic.apply_daily_exit_step` "
             "bar-by-bar from each real fill; NOTHING here changes live behavior. STEP-3 "
             "(adopt a parameterization or none) = operator fork **F1**.\n")

    # Method note
    L.append("\n## Method — the MARGINAL model (why the numbers are trustworthy)\n")
    L.append("An alt rule can only differ from reality by triggering an **earlier** exit. So a "
             "trade that never triggers earlier is anchored to its **actual realized $** (not a "
             "force-close), and each cell's signal is `marginal = Σ(alt − actual)` over the "
             "harvest set — the extra $ the rule would have kept vs what happened. The baseline "
             "cell then reproduces reality by construction, so systematic replay error (daily "
             "granularity, backtest-pure semantics) cancels in the marginal.  \n")
    L.append("Bars are **UNADJUSTED** — we replay recorded unadjusted fills/stops, so the bar "
             "basis must match (adjusted bars corrupted dividend names — IBM flipped sign in the "
             "first pass). This deliberately deviates from ADR A1's `adjusted=true` (the "
             "RS-engine convention, wrong for fill-replay).\n")

    # Guardrail 0 — baseline fidelity
    fid = baseline_fidelity(sw)
    diverged = [f for f in fid if f["early"]]
    L.append("\n## Guardrail 0 — baseline fidelity (credibility gate)\n")
    L.append(f"Baseline (`sma·⅓·no-lock` = today's rules) should RIDE to each actual exit "
             f"(marginal 0). Actual harvest total = **${_fmt(actual_h)}**. Names where the "
             "backtest-pure sma diverges (exits earlier than live did):\n")
    L.append("| ticker | actual $ | baseline replay $ | baseline marginal $ | exit |")
    L.append("|---|--:|--:|--:|---|")
    for f in fid:
        flag = " ⚠" if f["early"] else ""
        L.append(f"| {f['ticker']}{flag} | {_fmt(f['actual'])} | {_fmt(f['replay'])} | "
                 f"{_fmt(f['resid'])} | {f['reason']} |")
    L.append(f"\n> {len(diverged)} of {len(fid)} harvest names diverge at baseline "
             + ("(their non-baseline deltas carry extra reconstruction noise — flagged)."
                if diverged else "— clean; the marginal metric is trustworthy."))

    # Ranked cells
    L.append("\n## Ranked cells (by MARGINAL $ vs actual, over the HARVEST set)\n")
    L.append(f"Baseline marginal = **${_fmt(base['marginal'])}** (≈0 = faithful). Top 15 by "
             "extra-$-harvested:\n")
    L.append("| # | cell | marginal $ | kept $ | capture | #early | ctrl Δ$ |")
    L.append("|--:|---|--:|--:|--:|--:|--:|")
    L.append(f"| — | {base['cell']['label']} | {_fmt(base['marginal'])} | {_fmt(base['kept'])} | "
             f"{base['capture']*100:.0f}% | {base['n_early']} | {_fmt(base['ctrl_delta'])} |")
    for i, r in enumerate(results[:15], 1):
        L.append(f"| {i} | {r['cell']['label']} | {_fmt(r['marginal'])} | {_fmt(r['kept'])} | "
                 f"{r['capture']*100:.0f}% | {r['n_early']} | {_fmt(r['ctrl_delta'])} |")

    # Axis A isolation at b=sma, c=None
    L.append("\n## Axis A isolated (trail `sma`, partial `⅓`) — the pure peak-lock marginal $\n")
    L.append("| arm | floor 40% | floor 50% | floor 60% |")
    L.append("|---|--:|--:|--:|")
    iso = {r["cell"]["label"]: r for r in sw["results"]}
    for kind, val in A_ARMS:
        arm_lbl = _arm_label(kind, val)
        cells_row = []
        for floor in A_FLOORS:
            lbl = f"lock {arm_lbl}/{int(floor*100)}%·sma·⅓"
            r = iso.get(lbl)
            cells_row.append(f"{_fmt(r['marginal'])}" if r else "—")
        L.append(f"| {arm_lbl} | " + " | ".join(cells_row) + " |")

    # Axis B/C standalone (no lock) — is the trail/partial choice worth anything on its own?
    L.append("\n## Axis B / C standalone (NO lock) — marginal $ vs actual\n")
    L.append("With a loose-floor lock ON, its stop dominates the trail, so B is masked in the "
             "armed grid above. Here with NO lock, the trail/partial choice stands alone:\n")
    L.append("| trail \\ partial | ⅓ | 0.40 | 0.50 |")
    L.append("|---|--:|--:|--:|")
    for b in B_TRAILS:
        row = []
        for c in C_SCALES:
            lbl = "BASELINE(sma·⅓·no-lock)" if (b == "sma" and c is None) else f"no-lock·{b}·{_clbl(c)}"
            r = iso.get(lbl)
            row.append(_fmt(r["marginal"]) if r else "—")
        L.append(f"| {b} | " + " | ".join(row) + " |")
    L.append("\n> If these hover near the baseline's noise floor, B/C add little standalone — "
             "the peak-lock (Axis A) is the load-bearing mechanism.")

    # Best cell breakdown
    lock_effect = best["marginal"] - base["marginal"]
    L.append(f"\n## Best cell — `{best['cell']['label']}`  "
             f"(marginal +${_fmt(best['marginal'])}, {best['n_early']} early exits)\n")
    L.append(f"Baseline reconstruction noise = ${_fmt(base['marginal'])} (Guardrail 0); "
             f"**lock-attributable effect = best − baseline = +${_fmt(lock_effect)}**.\n")

    L.append("\n### Guardrail 1 — plateau (not a spike)\n")
    L.append("| arm | floor | marginal $ | |")
    L.append("|---|--:|--:|:--:|")
    for n in plateau_neighbors(sw, best):
        arm = _arm_label(best["cell"]["a"]["kind"], n["arm"])
        L.append(f"| {arm} | {int(n['floor']*100)}% | {_fmt(n['marginal'])} | "
                 f"{'◄ best' if n['is_best'] else ''} |")

    L.append("\n### Guardrail 4 — the big runners not clipped\n")
    L.append("The lock must not shred the true runners (a negative clip = harvested EARLY, "
             "below the actual exit). NB: a clip on a Guardrail-0-flagged name (⚠) is "
             "backtest-pure-vs-live reconstruction divergence, NOT the lock — check the exit "
             "date matches the baseline's:\n")
    fid_early = {f["ticker"] for f in diverged}  # reuse the divergent set computed above
    L.append("| ticker | actual $ | best-cell $ | clip $ | best exit | note |")
    L.append("|---|--:|--:|--:|---|---|")
    for c in clipped_runners(sw, best):
        note = "⚠ baseline-divergent (recon noise)" if c["ticker"] in fid_early else ""
        L.append(f"| {c['ticker']} | {_fmt(c['actual'])} | {_fmt(c['best'])} | "
                 f"{_fmt(c['clip'])} | {c['exit']} | {note} |")

    L.append("\n### Guardrail 3 — mechanism vs the named round-trippers\n")
    L.append("| ticker | entry | peak(intra) | actual $ | best-cell $ | marginal $ | best exit |")
    L.append("|---|--:|--:|--:|--:|--:|---|")
    for c in named_cases(sw, best):
        L.append(f"| {c['ticker']} | {_fmt(c['entry'],2)} | {_fmt(c['peak_intra'],2)} | "
                 f"{_fmt(c['actual'])} | {_fmt(c['best'])} | {_fmt(c['marginal'])} | "
                 f"{c['best_exit']} @ {c['best_date']} |")

    # Control
    ctrl_ok = all(abs(r["ctrl_delta"]) < 1.0 for r in sw["results"])
    L.append("\n## Control cohort (same-day losers) — invariance check\n")
    L.append(("Every cell's control marginal ≈0 (all |Δ|<$1) ✓ — losers untouched, as expected. "
              if ctrl_ok else "⚠ Some cells move the control cohort — investigate. ")
             + "A day-1 intraday stop can't be moved by a multi-day mechanic.\n")

    # Decision sheet
    L.append("\n## STEP-3 decision sheet (operator fork F1)\n")
    L.append(f"- **Ranked winner**: `{best['cell']['label']}` — **+${_fmt(lock_effect)} "
             f"lock-attributable** (best ${_fmt(best['marginal'])} − baseline noise "
             f"${_fmt(base['marginal'])}) over {len(sw['harvest'])} harvest names "
             f"({best['n_early']} exited earlier); capture {base['capture']*100:.0f}%→"
             f"{best['capture']*100:.0f}%; the losers are untouched.\n")
    L.append("- **The mechanism the round-trippers name** = the peak-lock floor (Axis A): SMCI "
             "(+11.7%→−$639) and CRSR/RCAT (gave back most of a big run) are where the marginal "
             "concentrates; GOOGL/BW (clean runners) must stay ~uncut (Guardrail 4).\n")
    L.append("- **Coarse grid — RANK not tune** (N=%d harvest names is direction-setting, not a "
             "fit). Bars UNADJUSTED; %d baseline-divergent name(s) flagged.\n"
             % (len(sw["harvest"]), len(diverged)))
    L.append("- Fork **F1**: adopt a parameterization, or none. Any live flip → CHANGE_PROCESS "
             "+ #151 paper exercise + the `harvest_rule_flipped` audit + the standing "
             "`harvest_rule_effectiveness` review (ADR §A5). Exit discipline = THE LINE.\n")
    L.append(f"\n_Reproduce: `python scripts/_306_harvest_sweep.py` off "
             f"`scripts/eval_data/306_bars_{fp}.csv` + `{COHORT_CSV.name}`._\n")

    DOC_OUT.parent.mkdir(parents=True, exist_ok=True)
    DOC_OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"[doc] wrote {DOC_OUT.relative_to(REPO)} — best cell: {best['cell']['label']} "
          f"(+${best['marginal']:,.0f} marginal, {best['n_early']} early)")


def main():
    ap = argparse.ArgumentParser(description="ADR 0023 Card 2 — #306 harvest sweep")
    ap.add_argument("--fetch-bars", action="store_true",
                    help="fetch UNADJUSTED daily bars from prod (apollo-market) → fingerprinted CSV")
    args = ap.parse_args()
    cohort = load_cohort()
    fp = compute_fingerprint(cohort)
    bp = bars_path(fp)
    if args.fetch_bars:
        bp = fetch_bars(cohort)
        return
    if not bp.exists():
        raise SystemExit(f"missing bars cache {bp.name} — run `--fetch-bars` first (needs prod)")
    bars_by = load_bars(bp)
    sw = sweep(cohort, bars_by)
    write_doc(sw, fp)


if __name__ == "__main__":
    main()
