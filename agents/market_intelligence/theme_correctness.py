"""#655 — the signed theme-correctness test, run nightly.

SSoT: docs/architecture/theme_engine.md (#655 section) · the operator's sign-off is
docs/analysis/655_theme_correctness_test_2026-09-27.md's CORRECTED section (top of the file —
it wins over the draft below it). THE LINE: this module only READS mi_themes / mi_correlation_clusters
/ mi_stock_scores / mi_daily_closes and writes ONE mi_audit_log row a night. It never touches
mi_themes or any membership table, never Telegrams (only `notify_job_failure` on a load error,
same as every other nightly health check), and never calls an LLM. Nothing here is a gate —
raising a bar, lowering one, or acting on a flag is the operator's call (THE LINE).

FOUR SIGNED CHECKS (operator, 2026-09-27) — are the right stocks together:
  G1 MEMBER FIT   — >= 90% of judgeable member-pairs tie >= 0.35 to their own theme
                    (leave-one-out, market-adjusted, 60 sessions).
  G2 MISFILED     — <= 5% of judgeable member-pairs tied < 0.35 to their own theme AND
                    >= 0.35 (and >= own + 0.20) to a DIFFERENT live theme.
  G3 BEATS A RANDOM BASKET — >= 90% of themes have cohesion above a size-matched random
                    control's p95 (RS-composite x volatility tercile).
  G4 SHAPE        — themes under 3 members are <= 10% of the board.
Plus, no bar: the judgeable-theme share (themes with >= 1 judgeable member).

PLUS the STEP-2 naming-latency target: a genuinely NEW group (a re-mint excluded — see
`compute_theme_latency`) is named within a median 10 trading sessions of its first stored
correlation cluster (signed baseline 2026-09-27: 37 sessions, n=9, censored at 40; tighten to
5 once 10 holds).

DESIGN: every check is a PURE function over plain inputs (board rows / excess-return vectors /
scored-universe rows / cluster & theme history) — no DB, no mocks needed to test the maths. They
are ports of `scripts/probes/_655/grouping/grouping_test.py` (G1-G4; reused verbatim, not
re-derived — see `docs/analysis/655_theme_correctness_test_2026-09-27.md` for the numbers they
were signed against) and `scripts/probes/_655/critic_latency.py` (the re-mint exclusion). ONE
async function, `run_theme_correctness_check`, does the I/O: loads the live board exactly as the
engine defines it (`db.get_active_themes`), the closes and scored-universe rows the checks need,
and the theme/cluster history the latency read needs, then writes one `mi_audit_log` row
(event_type ``'theme_correctness_check'``) and never raises into its caller.

RNG NOTE (G3): the matched-control draws consume a `random.Random(seed)` in the EXACT call
sequence `scripts/probes/_655/grouping/grouping_test.py` consumed the global `random` module in
(same algorithm, so a local `Random(655)` reproduces it bit for bit) — `themes` and each theme's
own `tickers` list are NEVER re-sorted inside `compute_g3`; reordering silently changes which pool
member every subsequent draw consumes. `tests/test_655_theme_correctness.py`'s anchor test pins
this against the probe's captured output.
"""
from __future__ import annotations

import json
import logging
import asyncio
import random
import statistics
from collections import defaultdict
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np

from agents.market_intelligence import market_adjusted_correlation as mac

logger = logging.getLogger(__name__)

# ── Signed bars (operator, 2026-09-27) ─────────────────────────────────────────────────────────
# G1_BAR is theme_engine.ASSIGN_COMOVE_BAR kept as a literal, not imported: theme_engine.py pulls
# in `anthropic`/`shared.llm_client` at module scope, and these are pure math functions that must
# stay importable/testable without that weight. tests/test_655_theme_correctness.py pins the two
# equal so this can't drift silently.
G1_BAR = 0.35
G1_PASS_PCT = 90.0            # >= 90% of judgeable member-pairs tie >= G1_BAR
G2_MARGIN = 0.20
G2_FAIL_PCT = 5.0             # <= 5% of judgeable member-pairs misfiled
G3_PASS_PCT = 90.0            # >= 90% of themes beat the matched control's p95
G3_N_DRAWS = 500
G3_SEED = 655
G4_SMALL_MAX_PCT = 10.0       # <= 10% of the board may be under 3 members
G4_SMALL_MIN_MEMBERS = 3      # "under 3 members" — also rule B's line (theme_engine
#                               SMALL_FADING_RETIRE_MIN_MEMBERS, pinned equal in the tests)
# G4 "settled" (operator 2026-10-08, "Ok"): rule B's one-night wait holds a newly shrunk theme on
# the board for a night before retiring it, so G4 is ALSO reported without those held themes.
# get_active_themes' default window, which rule B's previous-night snapshot reads (pinned).
WAIT_PRIOR_WINDOW_DAYS = 7

LATENCY_LOOKBACK_SESSIONS = 40     # cluster lookback before a birth night (critic_latency.py)
LATENCY_WINDOW_DAYS = 30           # trailing window over which births are scored each night
LATENCY_MEDIAN_BAR_SESSIONS = 10   # signed target (tighten to 5 once 10 holds)
LATENCY_HISTORY_LOOKBACK_DAYS = 130  # mi_themes/cluster history the runner fetches each night —
# window_days(30) + lookback_sessions(40 sessions ~ 56 calendar days) + holiday/weekend margin.

RENAME_JACCARD_MIN = 0.4
RENAME_JACCARD_DAYS = 10


# ── shared helpers ──────────────────────────────────────────────────────────────────────────────

def _bar(rate: float | None, bar_pct: float, *, at_most: bool = False) -> dict[str, Any]:
    """The rate / bar / pass triple every signed read reports: a rate at or above the bar passes,
    or at or below it for an `at_most` bar; no rate (nothing judgeable) is neither pass nor fail."""
    return {"rate_pct": None if rate is None else round(rate, 1), "bar_pct": bar_pct,
            "pass_bar": None if rate is None else (rate <= bar_pct if at_most else rate >= bar_pct)}

def usable_set(excess: dict[str, np.ndarray]) -> set[str]:
    """Tickers with a real reading (>= BELONGING_MIN_OVERLAP_SESSIONS finite sessions)."""
    return {t for t, v in excess.items() if mac.usable(v, mac.BELONGING_MIN_OVERLAP_SESSIONS)}


def _theme_stages(themes: list[dict]) -> tuple[str, ...]:
    return tuple(sorted({(th.get("stage") or "").strip() for th in themes}))


def _member_homes(themes: list[dict]) -> dict[str, set[str]]:
    homes: dict[str, set[str]] = defaultdict(set)
    for th in themes:
        for m in th.get("tickers") or []:
            homes[m].add(th["name"])
    return homes


# ── G1 (member fit) + G2 (misfiled) ──────────────────────────────────────────────────────────────
@dataclass
class MemberRow:
    theme: str
    stage: str
    size: int
    ticker: str
    own: float | None
    best_other: float | None
    best_other_theme: str | None
    misfiled: bool
    era: str = "unknown"


def member_era(ticker: str, theme_name: str, history: dict[str, dict[date, set[str]]] | None,
              gate_live: date = date(2026, 9, 14)) -> str:
    """How `ticker` got into `theme_name` — REPORT-ONLY (does not affect G1/G2 pass/fail): a
    member admitted on/after `gate_live` was pair-tested at G1_BAR to get in, so G1 scoring it is
    partly the gate checking itself. `history`: {name: {date: set(tickers)}}, e.g. from
    scripts/probes/_655/grouping/theme_history.psv. Ports grouping_test.py's `era()` verbatim."""
    h = (history or {}).get(theme_name)
    if not h:
        return "unknown"
    dates = sorted(h)
    first_theme = dates[0]
    first_tk = next((d for d in dates if ticker in h[d]), None)
    if first_tk is None:
        return "unknown"
    if first_tk == first_theme:
        return "founder" if first_theme > date(2026, 5, 1) else "carried-pre-May"
    return "joined-09-14+" if first_tk >= gate_live else "joined-pre-09-14"


def compute_g1_g2(themes: list[dict], excess: dict[str, np.ndarray], *,
                  bar: float = G1_BAR, margin: float = G2_MARGIN,
                  history: dict[str, dict[date, set[str]]] | None = None) -> dict[str, Any]:
    """G1 (member fit) + G2 (misfiled), ported from grouping_test.py's G1/G2 blocks onto plain
    inputs. `themes`: [{"name","stage","tickers":[...]}] in the board's OWN order — never
    re-sorted here (order doesn't change G1/G2's own numbers, since they don't draw random
    controls, but keeping it order-preserving keeps this function honest about not re-deriving).
    `excess`: ticker -> market-adjusted return vector (mac.excess_returns), built by the caller
    over ITS OWN window (60 sessions strictly before the read date, same as the engine's own
    membership test)."""
    stages = _theme_stages(themes)
    baskets = {b.name: b for b in mac.build_baskets(themes, excess, stages=stages)}
    names = [th["name"] for th in themes]
    homes = _member_homes(themes)

    def tie(ticker: str, basket, exclude: str | None = None) -> float | None:
        vec = excess.get(ticker)
        if vec is None or basket is None:
            return None
        corr, _, _ = mac.correlate(vec, basket, exclude=exclude)
        return corr

    rows: list[MemberRow] = []
    for th in themes:
        name = th["name"]
        basket = baskets.get(name)
        tickers = th.get("tickers") or []
        for m in tickers:
            own = tie(m, basket, exclude=m)
            best, best_name = None, None
            for n in names:
                if n in homes.get(m, ()):
                    continue
                c = tie(m, baskets.get(n))
                if c is not None and (best is None or c > best):
                    best, best_name = c, n
            misfiled = bool(own is not None and own < bar and best is not None
                            and best >= bar and (best - own) >= margin)
            rows.append(MemberRow(
                theme=name, stage=th.get("stage") or "", size=len(tickers), ticker=m,
                own=own, best_other=best, best_other_theme=best_name, misfiled=misfiled,
                era=member_era(m, name, history)))

    judgeable = [r for r in rows if r.own is not None]
    n_judg = len(judgeable)
    g1_pass = sum(1 for r in judgeable if r.own >= bar)
    g1_rate = (100.0 * g1_pass / n_judg) if n_judg else None

    g2_flagged = [r for r in judgeable if r.misfiled]
    g2_rate = (100.0 * len(g2_flagged) / n_judg) if n_judg else None

    era_breakdown: dict[str, dict[str, Any]] = {}
    if history:
        for e in ("founder", "carried-pre-May", "joined-pre-09-14", "joined-09-14+", "unknown"):
            xs = [r for r in judgeable if r.era == e]
            if xs:
                era_breakdown[e] = {"n": len(xs),
                                    "pass": sum(1 for r in xs if r.own >= bar)}

    return {
        "rows": rows,
        "n_slots": len(rows),
        "n_judgeable": n_judg,
        "judgeable_share_pct": round(100.0 * n_judg / len(rows), 1) if rows else None,
        "g1": {"pass": g1_pass, "n": n_judg, **_bar(g1_rate, G1_PASS_PCT)},
        "g2": {"flagged": len(g2_flagged), "n": n_judg, **_bar(g2_rate, G2_FAIL_PCT, at_most=True),
              "list": [(r.ticker, r.theme, r.best_other_theme) for r in g2_flagged]},
        "era_breakdown": era_breakdown,
    }


# ── G3 (cohesion vs a size-matched random control) ───────────────────────────────────────────────
def compute_g3(themes: list[dict], excess: dict[str, np.ndarray], usable: set[str],
              scores: dict[str, dict[str, Any]], sector: dict[str, str], *,
              n_draws: int = G3_N_DRAWS, seed: int = G3_SEED) -> dict[str, Any]:
    """G3 — theme cohesion vs 500 size-matched random draws (RS-composite x volatility tercile),
    ported from grouping_test.py's C1 control (draw()/feats()/tert()/coh_fast()/the fast
    pairwise-correlation matrix), verbatim maths. `themes` and every theme's `tickers` order is
    NEVER re-sorted here — see the module docstring's RNG note. `scores`: {ticker: {"rs": float |
    None, "sector": str | None}} for the scored universe (mi_stock_scores). C2 (the same-sector
    control) is intentionally NOT scored or reported — it isn't barred (2026-09-27) — but its
    `draw()` calls still run, to consume the SAME amount of RNG state the probe consumed, so every
    theme after the first draws from the identical stream position."""
    board = {m for th in themes for m in (th.get("tickers") or [])}
    uni = [t for t in scores if t in usable and scores[t].get("rs") is not None]
    if not uni:
        return {"n_board": len(themes), "n_judgeable": 0, "pass": 0, **_bar(None, G3_PASS_PCT),
                "themes": [], "fail_list": []}

    _vol_cache: dict[str, float] = {}

    def vol(t: str) -> float | None:
        if t not in usable:
            return None
        if t not in _vol_cache:
            _vol_cache[t] = float(np.nanstd(excess[t]))
        return _vol_cache[t]

    rs_cut = np.percentile([scores[t]["rs"] for t in uni], [33.3, 66.7])
    vol_cut = np.percentile([v for v in (vol(t) for t in uni) if v is not None], [33.3, 66.7])

    def tert(x: float, cuts) -> int:
        return 0 if x <= cuts[0] else (1 if x <= cuts[1] else 2)

    def feats(t: str):
        rs = scores.get(t, {}).get("rs")
        v = vol(t)
        return (tert(rs, rs_cut) if rs is not None else None,
                tert(v, vol_cut) if v is not None else None, sector.get(t))

    cell1: dict[tuple, list[str]] = defaultdict(list)
    cell2: dict[tuple, list[str]] = defaultdict(list)
    for t in uni:
        a, b, s = feats(t)
        cell1[(a, b)].append(t)
        cell2[(a, b, s)].append(t)

    def draw(rng: random.Random, members: list[str], with_sector: bool) -> list[str]:
        out: list[str] = []
        excl = set(members)
        for m in members:
            a, b, s = feats(m)
            if a is None:
                a = 2  # unscored board member: treat as top RS tercile (board names are strength-selected)
            pool: list[str] = []
            if with_sector and s:
                pool = [x for x in cell2.get((a, b, s), []) if x not in excl]
                if len(pool) < 5:
                    pool = [x for (aa, bb, ss), xs in cell2.items() if aa == a and ss == s
                           for x in xs if x not in excl]
            if len(pool) < 5:
                pool = [x for x in cell1.get((a, b), []) if x not in excl]
            if not pool:
                # no match at all (thin cell + nothing left after exclusions) — cannot draw a
                # control for this member; the caller sees a shorter basket, coh_fast handles it.
                continue
            x = rng.choice(pool)
            out.append(x)
            excl.add(x)
        return out

    allt = sorted(set(uni) | {t for t in board if t in usable})
    idx = {t: i for i, t in enumerate(allt)}
    M = np.vstack([excess[t] for t in allt])
    fin = np.isfinite(M)
    Mc = np.where(fin, M, np.nan)
    means = np.nanmean(Mc, axis=1, keepdims=True)
    sds = np.nanstd(Mc, axis=1, keepdims=True)
    # a halted/frozen ticker (zero variance) would divide-by-zero into inf/nan and silently
    # corrupt every cohesion figure it touches — guard it to a flat (uncorrelated) row instead.
    sds_ok = np.isfinite(sds) & (sds > 1e-12)
    Zs = np.where(fin & sds_ok, (Mc - means) / np.where(sds_ok, sds, 1.0), 0.0)
    denom = np.maximum(fin.astype(float) @ fin.T.astype(float), 1)
    C = (Zs @ Zs.T) / denom

    def coh_fast(members: list[str]) -> float | None:
        ii = [idx[m] for m in members if m in idx]
        if len(ii) < 2:
            return None
        sub = C[np.ix_(ii, ii)]
        k = len(ii)
        v = float((sub.sum() - np.trace(sub)) / (k * (k - 1)))
        return v if np.isfinite(v) else None

    rng = random.Random(seed)
    trows: list[dict[str, Any]] = []
    for th in themes:
        ms = [m for m in (th.get("tickers") or []) if m in usable]
        c = coh_fast(ms)
        if c is None:
            # matches grouping_test.py exactly: an unjudgeable theme (< 2 usable members) is
            # skipped WITHOUT drawing — the RNG stream never advances for it.
            trows.append({"name": th["name"], "stage": th.get("stage"), "size": len(th.get("tickers") or []),
                         "cohesion": None, "c1_p95": None, "pass_g3": None})
            continue
        c1 = [coh_fast(draw(rng, ms, False)) for _ in range(n_draws)]
        c1 = [x for x in c1 if x is not None]
        c1_p95 = float(np.percentile(c1, 95)) if c1 else None
        for _ in range(n_draws):
            draw(rng, ms, True)  # C2 — RNG-consumed for stream parity, not scored (not barred)
        trows.append({"name": th["name"], "stage": th.get("stage"), "size": len(th.get("tickers") or []),
                     "cohesion": c, "c1_p95": c1_p95,
                     "pass_g3": (c1_p95 is not None and c > c1_p95)})

    judgeable = [r for r in trows if r["cohesion"] is not None]
    passed = sum(1 for r in judgeable if r["pass_g3"])
    rate = (100.0 * passed / len(judgeable)) if judgeable else None
    return {
        "n_board": len(themes), "n_judgeable": len(judgeable),
        "pass": passed, **_bar(rate, G3_PASS_PCT),
        "fail_list": [r["name"] for r in judgeable if not r["pass_g3"]],
        "themes": trows,
    }


# ── G4 (shape) ────────────────────────────────────────────────────────────────────────────────────
def _g4_share(themes: list[dict], small_max_pct: float) -> dict[str, Any]:
    n = len(themes)
    small = [th["name"] for th in themes if len(th.get("tickers") or []) < G4_SMALL_MIN_MEMBERS]
    rate = 100.0 * len(small) / n if n else None
    return {"n_board": n, "small": len(small), **_bar(rate, small_max_pct, at_most=True), "list": small}


def compute_g4(themes: list[dict], *, waiting: AbstractSet[str] = frozenset(),
               small_max_pct: float = G4_SMALL_MAX_PCT) -> dict[str, Any]:
    """Themes under 3 members, share of the board. Ported from grouping_test.py's G4 shape read
    (the only bar of its several G4 reads that was signed 2026-09-27 — shard/dual-homed/homeless
    are informational in the probe and are NOT reproduced here). The top-level figure is the
    signed bar, unchanged; `settled` is the same read with the themes in `waiting` (rule B's held
    themes, `waiting_night_names`) dropped from the board, reported beside it — never instead."""
    out = _g4_share(themes, small_max_pct)
    out["settled"] = _g4_share([th for th in themes if th["name"] not in waiting], small_max_pct)
    out["settled"]["waiting"] = sorted(th["name"] for th in themes if th["name"] in waiting)
    return out


def waiting_night_names(board: list[dict], history: list[dict]) -> set[str]:
    """PURE: board themes rule B is holding tonight — weak Fading (stage 'Fading', rs_avg None)
    under G4_SMALL_MIN_MEMBERS, but NOT under it on the previous persisted night (or with no such
    night), so the engine keeps them one more night instead of retiring them. `board`: rows with
    name/stage/rs_avg/tickers/theme_date; `history`: mi_themes rows {"date","name","stage",
    "tickers"}. The previous night mirrors rule B's snapshot (`get_active_themes` read by
    theme_engine._prior_member_counts): the latest row dated before the board row within
    WAIT_PRIOR_WINDOW_DAYS of it, and none at all when that row is a Retired tombstone (the
    snapshot drops such names). Not mirrored: a same-day manual engine rerun, where the engine
    sees tonight's first-pass row and holds every candidate."""
    window = timedelta(days=WAIT_PRIOR_WINDOW_DAYS)
    weak = {th["name"]: th["theme_date"] for th in board
            if th.get("stage") == "Fading" and th.get("rs_avg") is None
            and len(th.get("tickers") or []) < G4_SMALL_MIN_MEMBERS
            and type(th.get("theme_date")) is date}
    latest: dict[str, dict] = {}
    for r in history:
        td = weak.get(r["name"])
        if td is not None and td - window <= r["date"] < td and (
                r["name"] not in latest or r["date"] > latest[r["name"]]["date"]):
            latest[r["name"]] = r
    return {name for name in weak
            if name not in latest or latest[name].get("stage") == "Retired"
            or len(latest[name].get("tickers") or []) >= G4_SMALL_MIN_MEMBERS}


# ── Step-2 naming latency (re-mint exclusion per critic_latency.py) ────────────────────────────────
def _find(parent: dict[str, str], x: str) -> str:
    while parent.get(x, x) != x:
        x = parent[x]
    return x


def _union(parent: dict[str, str], a: str, b: str) -> None:
    parent[_find(parent, a)] = _find(parent, b)


def compute_theme_latency(
    history: list[dict[str, Any]],
    renames: list[tuple[str, str]],
    cluster_by_date: dict[date, dict[str, set[str]]],
    session_dates: list[date],
    run_date: date,
    *,
    lookback_sessions: int = LATENCY_LOOKBACK_SESSIONS,
    window_days: int = LATENCY_WINDOW_DAYS,
    median_bar_sessions: int = LATENCY_MEDIAN_BAR_SESSIONS,
    jaccard_min: float = RENAME_JACCARD_MIN,
    jaccard_days: int = RENAME_JACCARD_DAYS,
) -> dict[str, Any]:
    """STEP 2 — sessions from the first pre-birth correlation cluster covering >= half a theme's
    founders to the night it is born, ported from scripts/probes/_655/critic_latency.py. A birth
    is a RE-MINT (excluded from the signed median) when >= half its founders were already sitting
    in ONE live theme on ANY board night between first sighting and birth (`held_between` — the
    critic's correction over a narrower same-night-only check; confirmed against
    scripts/probes/_655/critic_latency_out.txt's "n 9 median lead 37" read, the figure the
    2026-09-27 sign-off baselines against).

    `history`: every {"date","name","stage","tickers"} row (ALL stages, including Retired — the
    Retired rows matter for the board reconstruction below) over a window wide enough to see each
    birth's true first appearance, e.g. LATENCY_HISTORY_LOOKBACK_DAYS back from `run_date`.
    `renames`: (old_name, new_name) edges, e.g. from mi_theme_renames — an EXPLICIT rename lineage.
    `cluster_by_date`: date -> cluster_hash -> set(tickers), e.g. from mi_correlation_clusters.
    `session_dates`: ascending trading days (from SPY closes) spanning the same window — NOT
    trimmed to 60 like the G1-G3 window; latency needs a longer look-back.
    """
    names: dict[str, list[dict]] = defaultdict(list)
    for r in history:
        names[r["name"]].append(r)
    for n in names:
        names[n].sort(key=lambda r: r["date"])

    parent: dict[str, str] = {}
    for old, new in renames:
        if old in names and new in names:
            _union(parent, new, old)

    by_date_bucket: dict[date, list[dict]] = defaultdict(list)
    for rs in names.values():
        for r in rs:
            by_date_bucket[r["date"]].append(r)
    by_date: dict[date, list[tuple[str, list[str], str]]] = {
        d: [(r["name"], r["tickers"], r["stage"]) for r in rs
            if r.get("tickers") and r["stage"] != "Retired"]
        for d, rs in by_date_bucket.items()}

    first_row: dict[str, dict] = {}
    for n, rs in names.items():
        live = [r for r in rs if r["stage"] != "Retired" and r.get("tickers")]
        if live:
            first_row[n] = live[0]

    # Jaccard fallback: an un-logged rename/continuation within `jaccard_days` sharing >=
    # jaccard_min of its founders (critic_latency.py's own heuristic — mi_theme_renames only
    # covers renames logged since 2026-09-02; this catches the rest).
    for n, fr in first_row.items():
        d0, F = fr["date"], set(fr["tickers"])
        recent: dict[str, list[str]] = {}
        for k in range(1, jaccard_days + 1):
            for nm, tk, _ in by_date.get(d0 - timedelta(days=k), []):
                if nm != n and nm not in recent:
                    recent[nm] = tk
        best, bj = None, 0.0
        for nm, tk in recent.items():
            s = set(tk)
            u = F | s
            j = len(F & s) / len(u) if u else 0.0
            if j > bj:
                best, bj = nm, j
        if best and bj >= jaccard_min:
            _union(parent, n, best)

    groups: dict[str, list[str]] = defaultdict(list)
    for n in first_row:
        groups[_find(parent, n)].append(n)

    births: list[dict] = []
    for _root, ns_ in groups.items():
        fr = min((first_row[n] for n in ns_), key=lambda r: r["date"])
        if len(fr.get("tickers") or []) >= 2:
            births.append(fr)

    sidx = {d: i for i, d in enumerate(session_dates)}

    def leads(founders: set[str], birth_date: date) -> list[tuple[int, date]]:
        if birth_date not in sidx:
            return []
        i0 = sidx[birth_date]
        hits: list[tuple[int, date]] = []
        for d in sorted(cluster_by_date):
            if d not in sidx or not (i0 - lookback_sessions <= sidx[d] < i0):
                continue
            for tk in cluster_by_date[d].values():
                if founders and len(tk & founders) / len(founders) >= 0.5:
                    hits.append((i0 - sidx[d], d))
                    break
        return hits

    bdates = sorted({r["date"] for r in history})
    _board_cache: dict[date, list[dict]] = {}

    def board_at(d: date) -> list[dict]:
        """Replays get_active_themes' own rule (latest row per name within 7 days, stage !=
        Retired) as of a historical date `d`."""
        if d in _board_cache:
            return _board_cache[d]
        latest: dict[str, dict] = {}
        for k in range(0, 8):
            for r in by_date_bucket.get(d - timedelta(days=k), []):
                if r["name"] not in latest or r["date"] > latest[r["name"]]["date"]:
                    latest[r["name"]] = r
        out = [r for r in latest.values() if r["stage"] != "Retired" and r.get("tickers")]
        _board_cache[d] = out
        return out

    def held_between(founders: set[str], d0: date, d1: date):
        for d in bdates:
            if d0 <= d < d1:
                for r in board_at(d):
                    if founders and len(founders & set(r["tickers"])) / len(founders) >= 0.5:
                        return d, r["name"], r["stage"]
        return None

    window_start = run_date - timedelta(days=window_days)
    window_births = [b for b in births if window_start < b["date"] <= run_date]

    per_birth = []
    for b in window_births:
        founders = set(b["tickers"])
        hits = leads(founders, b["date"])
        if not hits:
            per_birth.append({"name": b["name"], "date": b["date"], "lag": None,
                              "first_sighting": None, "remint": None, "censored": False})
            continue
        lag, first_sighting = max(hits)
        held = held_between(founders, first_sighting, b["date"])
        per_birth.append({
            "name": b["name"], "date": b["date"], "lag": lag,
            "first_sighting": first_sighting, "remint": held is not None,
            "remint_theme": held[1] if held else None,
            "censored": lag >= lookback_sessions - 1,
        })

    tonight = [p for p in per_birth if p["date"] == run_date]
    measured = [p for p in per_birth if p["lag"] is not None]
    new_measured = [p for p in measured if not p["remint"]]
    lags = [p["lag"] for p in new_measured]
    median = statistics.median(lags) if lags else None
    return {
        "window_days": window_days, "window_births": len(window_births),
        "with_precluster": len(measured), "remints": sum(1 for p in measured if p["remint"]),
        "new_n": len(new_measured),
        "median_sessions": median,
        "over_10": sum(1 for x in lags if x > 10),
        "censored_at_cap": sum(1 for p in new_measured if p["censored"]),
        "bar_sessions": median_bar_sessions,
        "pass_bar": (median <= median_bar_sessions) if median is not None else None,
        "tonight_births": [
            {"name": p["name"], "lag": p["lag"], "remint": p["remint"]} for p in tonight
        ],
    }


# ── orchestrator (pure) ────────────────────────────────────────────────────────────────────────────
def build_correctness_report(
    themes: list[dict], excess: dict[str, np.ndarray], scores: dict[str, dict[str, Any]],
    sector: dict[str, str], *, history: dict[str, dict[date, set[str]]] | None = None,
    latency: dict[str, Any] | None = None, waiting: AbstractSet[str] = frozenset(),
) -> dict[str, Any]:
    """Runs G1-G4 and folds in an already-computed `latency` dict (kept separate because latency
    needs different inputs — full theme/cluster history, not just tonight's board/excess). Never
    raises: a KeyError/ValueError inside any one check is caught by the caller
    (`run_theme_correctness_check`), not here — kept pure and loud for tests."""
    usable = usable_set(excess)
    g1g2 = compute_g1_g2(themes, excess, history=history)
    g3 = compute_g3(themes, excess, usable, scores, sector)
    g4 = compute_g4(themes, waiting=waiting)
    all_pass = [g1g2["g1"]["pass_bar"], g1g2["g2"]["pass_bar"], g3["pass_bar"], g4["pass_bar"]]
    if latency is not None:
        all_pass.append(latency.get("pass_bar"))
    return {
        "n_board": len(themes),
        "g1": g1g2["g1"], "g2": g1g2["g2"], "g3": g3, "g4": g4,
        "judgeable_share_pct": g1g2["judgeable_share_pct"],
        "era_breakdown": g1g2["era_breakdown"],
        "latency": latency,
        "all_signed_bars_pass": all(v for v in all_pass if v is not None) if any(
            v is not None for v in all_pass) else None,
    }


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, date):
        return o.isoformat()
    if isinstance(o, set):
        return sorted(o)
    raise TypeError(f"not JSON serializable: {type(o)}")


# ── the nightly I/O runner ──────────────────────────────────────────────────────────────────────
async def run_theme_correctness_check(conn: Any = None) -> dict[str, Any]:
    """Nightly (#655): loads the live board exactly as the engine defines it, the closes and
    scored-universe rows G1-G3 need, and the theme/cluster history the latency read needs;
    computes the four signed grouping bars + the naming-latency read; writes ONE mi_audit_log row
    (event_type 'theme_correctness_check'). Never raises — a failed load writes an error row and
    pages through `notify_job_failure`, same contract as `run_delayed_entry_population_check`
    (#327). Read-only: no write ever touches mi_themes or any membership table."""
    from agents.market_intelligence.db import get_pool as _gp, get_active_themes, log_audit_event as _log
    from agents.market_intelligence import ep_theme_belonging as etb
    from core.notifications import notify_job_failure
    from shared.dates import et_today

    async def _run(c: Any) -> dict[str, Any]:
        out: dict[str, Any] = {"errors": [], "report": None}
        today = et_today()
        try:
            board_rows = await get_active_themes(stale_after_days=7)
            themes = [{"name": r["name"], "stage": r["stage"], "tickers": list(r["tickers"] or [])}
                     for r in board_rows]
            board_tickers = {t for th in themes for t in th["tickers"]}

            closes_lookback_days = max(mac.CALENDAR_DAYS_FOR_LOOKBACK,
                                       LATENCY_WINDOW_DAYS + LATENCY_LOOKBACK_SESSIONS + 30)
            scores_row = await c.fetchrow(
                "SELECT MAX(score_date) AS d FROM mi_stock_scores WHERE score_date <= $1", today)
            score_date = scores_row["d"] if scores_row else None
            scores_rows = []
            if score_date is not None:
                scores_rows = await c.fetch(
                    "SELECT ticker, rs_composite, sector FROM mi_stock_scores WHERE score_date = $1",
                    score_date)
            scores = {r["ticker"]: {"rs": r["rs_composite"], "sector": r["sector"]} for r in scores_rows}
            sector = {t: v["sector"] for t, v in scores.items() if v["sector"]}
            universe_tickers = set(scores.keys())

            all_tickers = board_tickers | universe_tickers | {mac.MARKET_TICKER}
            closes, _n_close_rows = await etb.fetch_closes(
                all_tickers, today - timedelta(days=closes_lookback_days), today)
            sessions = mac.session_index(closes.get(mac.MARKET_TICKER, {}), today,
                                        mac.BELONGING_LOOKBACK_SESSIONS)
            if len(sessions) < 2:
                raise RuntimeError(f"no {mac.MARKET_TICKER} closes before {today} — nothing to score")
            market = mac.log_returns(closes.get(mac.MARKET_TICKER, {}), sessions)
            excess = mac.excess_returns(closes, sessions, market)

            all_spy_sessions = sorted(d for d in closes.get(mac.MARKET_TICKER, {}) if d < today)

            history_since = today - timedelta(days=LATENCY_HISTORY_LOOKBACK_DAYS)
            hist_rows = await c.fetch(
                "SELECT theme_date, name, stage, tickers FROM mi_themes WHERE theme_date >= $1 "
                "ORDER BY theme_date, id", history_since)
            history = [{"date": r["theme_date"], "name": r["name"], "stage": r["stage"],
                       "tickers": list(r["tickers"] or [])} for r in hist_rows]
            rename_rows = await c.fetch("SELECT old_name, new_name FROM mi_theme_renames")
            renames = [(r["old_name"], r["new_name"]) for r in rename_rows]
            cluster_rows = await c.fetch(
                "SELECT cluster_date, cluster_hash, ticker FROM mi_correlation_clusters "
                "WHERE cluster_date >= $1", history_since)
            cluster_by_date: dict[date, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
            for r in cluster_rows:
                cluster_by_date[r["cluster_date"]][r["cluster_hash"]].add(r["ticker"])

            theme_history_by_name: dict[str, dict[date, set[str]]] = defaultdict(dict)
            for r in history:
                theme_history_by_name[r["name"]][r["date"]] = set(r["tickers"])

            waiting = waiting_night_names(board_rows, history)

            def _compute() -> dict[str, Any]:
                latency = compute_theme_latency(history, renames, cluster_by_date, all_spy_sessions, today)
                return build_correctness_report(themes, excess, scores, sector,
                                                history=theme_history_by_name, latency=latency,
                                                waiting=waiting)
            # ~4 s of NumPy/Python work: off the event loop so the scheduler's other jobs keep running.
            report = await asyncio.to_thread(_compute)
            out["report"] = report
        except Exception as e:
            logger.error("theme_correctness_check: load/compute failed: %s", e, exc_info=True)
            out["errors"].append(str(e))
            try:
                await _log("theme_correctness_check", f"error: {e}",
                          json.dumps({"status": "error", "error": str(e)}), conn=c)
            except Exception as log_e:
                logger.error("theme_correctness_check: error-row write failed: %s", log_e, exc_info=True)
            await notify_job_failure("theme_correctness_check", str(e))
            return out

        report = out["report"]
        try:
            summary = (
                f"G1 {report['g1']['pass']}/{report['g1']['n']} "
                f"({report['g1']['rate_pct']}% bar {report['g1']['bar_pct']}%) · "
                f"G2 {report['g2']['flagged']}/{report['g2']['n']} "
                f"({report['g2']['rate_pct']}% bar<= {report['g2']['bar_pct']}%) · "
                f"G3 {report['g3']['pass']}/{report['g3']['n_judgeable']} "
                f"({report['g3']['rate_pct']}% bar {report['g3']['bar_pct']}%) · "
                f"G4 {report['g4']['small']}/{report['g4']['n_board']} small "
                f"({report['g4']['rate_pct']}% bar<= {report['g4']['bar_pct']}%; settled "
                f"{report['g4']['settled']['small']}/{report['g4']['settled']['n_board']} "
                f"{report['g4']['settled']['rate_pct']}%) · "
                f"latency median {report['latency']['median_sessions'] if report['latency'] else None} "
                f"sessions (n={report['latency']['new_n'] if report['latency'] else None})"
            )
            await _log("theme_correctness_check", summary,
                      json.dumps(report, default=_json_default), conn=c)
        except Exception as e:
            logger.error("theme_correctness_check: audit-row write failed: %s", e, exc_info=True)
            out["errors"].append(f"audit_write: {e}")
        return out

    if conn is not None:
        return await _run(conn)
    pool = await _gp()
    async with pool.acquire() as c:
        return await _run(c)
