#!/usr/bin/env python3
"""#569 — THE TWO-AXIS STRUCTURE SPLIT, MEASURED: pre-gap extension × base duration/quietness.

READ-ONLY analysis over the existing capture-once caches (COST rule: $0, no LLM, no prod
pull — every input below was already captured for _expectedness_and_ranking.py). Nothing
here is wired into any grade, admission, sizing, or ordering path — THE LINE. Output is
evidence, never a rule change; promotion of either axis is fork S-3 (operator sign-off).

╔════════════════════════════════════════════════════════════════════════════════════════╗
║ PRE-REGISTERED DEFINITIONS — written 2026-08-19 BEFORE any outcome was joined.          ║
║ Every free parameter is fixed here with its derivation. Whatever the corpus shows is    ║
║ reported as-is; if alternatives are examined they are ALL reported and the PRIMARY is   ║
║ the one labelled PRIMARY here, regardless of which performs best.                       ║
╚════════════════════════════════════════════════════════════════════════════════════════╝

AXIS 1 — PRE-GAP EXTENSION (`ext_xadr_pregap`).
  Definition: median distance, in ADR20 units, of the D-1 CLOSE above each of SMA10/20/50
  (closes through D-1) that sits BELOW the D-1 close:
      median((pc - m) / pc / adr20_frac  for m in SMAs strictly below pc)
  This is the structure_model.md §4c extension formula with exactly ONE change: the
  reference price is the PRIOR CLOSE (the last pre-gap state), never the gap-day open.
  Reasoning (docs/methodology/ep_reference_mrna_2026-08-19.md §3): on the gap day,
  extension IS the event — MRNA sat ~19x ATR above its MA on the day the operator calls
  perfect, and only because the gap CREATED that extension; its pre-gap close was
  consolidating. The current encoder measures the event and scores it as a defect.
  No new parameters: SMA set, median-of-below, ADR20 normaliser, and the >=50-prior-closes
  gate are all inherited unchanged from the published §4c/probe definition.
  Unclassifiable: <50 prior closes -> excluded (recorded, never defaulted); every SMA
  at/above the prior close -> no-MA-below flag; for tests it takes the probe's PRIMARY
  "zero" convention (0.0 = least extended), with a sensitivity read excluding those rows.
  PRIMARY TEST (1 of 2): median split of ext_xadr_pregap (zero-fill), tail-first —
  share reaching >=8xADR (count stated) + P90 of tailx; median secondary; session-permuted
  p on the share statistic (house _tail_stats floors). Quartiles reported descriptively.

AXIS 2 — BASE DURATION × QUIETNESS (`base_days_raw40` PRIMARY; `base_days_adr6` variant).
  The base = the maximal trailing window ending D-1 in which the stock made NO MAJOR MOVE
  IN EITHER DIRECTION (operator correction 2026-08-19: duration × QUIETNESS, not duration
  × depth/tightness — "with a large base there's indication of neglect (at least there's
  no major movements up or down)"). Operationalised:
      base_days = the largest k <= 252 such that, over the last k H/L-complete prior
      sessions, (max(high) - min(low)) / max(high) <= CEILING.
  An up-move widens that band exactly as much as a down-move, so a stock in a major move
  in EITHER direction breaks containment quickly and scores a short base — the quietness
  correction is embedded in the containment criterion itself, not a separate score.
  PRIMARY CEILING = 0.40 (raw depth). Derivation: his MRNA annotations read 27%/34%
  (daily, 74d/101d) and 27/34/37% (weekly, 17/23/26w) — 40% admits every base he himself
  annotated (max 37%) with minimal headroom, and rejects a doubled or halved stock.
  SECONDARY VARIANT CEILING = 6 × ADR20 (as a fraction): MRNA's deepest annotated base
  37% ÷ its 6.92% ADR ≈ 5.3×, rounded up — the ADR-normalised twin, registered because
  every non-normalised effect this programme found so far was volatility in disguise.
  raw40 is PRIMARY because it is the direct transcription of the reference annotation;
  BOTH are reported in full regardless of which looks better.
  Companions recorded: base_depth (depth actually reached), base_censored (containment ran
  to the edge of available history <252 — base_days is then a LOWER BOUND), net
  displacement over the base in ADR units (descriptive only), lookback count (coverage).
  252-session cap: one trading year, 2x his longest annotated base (26w = 130 td).
  Unclassifiable: <20 H/L-complete prior sessions -> excluded, recorded.
  PRIMARY TEST (2 of 2): binary base_days_raw40 >= 74 vs < 74 — 74 = the SMALLEST base he
  annotated. Rows censored below 74 (quiet to the edge of <74 sessions of history) are
  UNDECIDABLE for the binary and excluded, never defaulted. Tail-first as above.
  Registered confound checks: Spearman base_days vs ADR20; the binary repeated inside ADR
  halves (a raw-% band mechanically anti-correlates with ADR).

CORPORA.
  PRIMARY: the 749 tier-A real-stock gap days 2026-03-03..07-15 (_552_cohort.psv, ETF-clean,
  78 tail winners) — per structure_model.md §6 an all-losing cohort cannot answer "does it
  separate winners", and this is the only cached population with winners in it.
  SECONDARY: the live alert corpus (_expct_alerts.tsv, live-source rows with outcomes) —
  the population the rank shadow actually records.
  Outcome unit (house): tailx = (max high D+1..D+20 - close_D) / close_D / ADR20; the
  cohort's tailx and ADR are the psv's own precomputed columns (same normalisation its
  winner flag was defined under); alert-corpus outcomes recomputed exactly as
  _expectedness_and_ranking.py::alert_outcome does.
  History depth caveat (stated before running): the cohort daily cache starts 2025-11-17,
  so early-cohort rows carry ~70 prior sessions — their base measurement is censored and
  the binary excludes the undecidable ones; the alert cache starts 2025-07-07 (~215+
  sessions, effectively uncensored for the 74-day question).

MULTIPLICITY LEDGER: exactly 2 PRIMARY tests (one per axis, cohort corpus, labelled
above). Everything else — the adr6 variant, the alert corpus, quartiles, the zero-fill
sensitivity, ADR-half splits, the censoring accounting — is SECONDARY/descriptive, and
every comparison attempted is printed. MRNA itself is n=1 and a REFERENCE, not evidence.

Implementation note: the axis computations are IMPORTED from
agents/market_intelligence/alert_rank_shadow.py (compute_pregap_extension,
compute_base_duration, compute_adr20_frac) — the same pure functions the shadow recorder
stores per-row, so what this probe measures is byte-identical to what the shadow records.

Output: docs/analysis/pregap_base_axes_2026-08-19.txt (capture once, read many).
"""
from __future__ import annotations

import csv
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

from _tail_stats import MIN_N_SHARE, p90, perm_p_stat, share_ge, share_stat  # noqa: E402

from agents.market_intelligence.alert_rank_shadow import (  # noqa: E402
    compute_adr20_frac,
    compute_base_duration,
    compute_pregap_extension,
)

OUT = REPO / "docs/analysis/pregap_base_axes_2026-08-19.txt"

BINARY_BASE_DAYS = 74  # the smallest base he annotated (74d · 27%) — pre-registered above

L: list[str] = []


def w(s: str = ""):
    L.append(s)


# ══════════════════════════════════════════ loads ══════════════════════════════════════

def load_bars(path: Path, sep: str = "|"):
    bars: dict[str, list[tuple]] = defaultdict(list)
    with open(path) as f:
        for row in csv.reader(f, delimiter=sep):
            if len(row) < 7:
                continue
            t, d = row[0], row[1]
            try:
                o, h, lo, c, v = (float(x) for x in row[2:7])
            except ValueError:
                continue
            bars[t].append((d, o, h, lo, c, v))
    for t in bars:
        bars[t].sort()
    return bars


ALERT_BARS = load_bars(HERE / "_533n_daily.tsv")
COHORT_BARS = load_bars(HERE / "_expct_cohort_daily.tsv")

COHORT = []
with open(HERE / "_552_cohort.psv") as f:
    for row in csv.reader(f, delimiter="|"):
        if len(row) < 12:
            continue
        COHORT.append(dict(
            ticker=row[0], date=row[1], gap=float(row[2]), pc=float(row[5]),
            adr=float(row[7]) / 100.0,  # psv column is in percent
            tailx=float(row[9]), winner=row[10] == "1"))

ALERTS = []
with open(HERE / "_expct_alerts.tsv") as f:
    for row in csv.reader(f, delimiter="|"):
        if len(row) < 15:
            continue
        ALERTS.append(dict(ticker=row[0], date=row[1], source=row[9]))


# ═══════════════════════════ per-row axis computation ══════════════════════════════════

def axes_for(bars_by_ticker, ticker: str, d: str):
    """Compute both pre-registered axes from the daily cache, strictly PRE-GAP (< d)."""
    seq = bars_by_ticker.get(ticker, [])
    prior = [b for b in seq if b[0] < d]
    prior_closes = [b[4] for b in prior if b[4] > 0]
    prior_hl = [(b[2], b[3], b[4]) for b in prior if b[2] > 0 and b[3] > 0 and b[4] > 0]
    adrf = compute_adr20_frac(prior_hl)
    ext, no_ma_below = compute_pregap_extension(prior_closes, adrf)
    base = compute_base_duration(prior_hl, adrf)
    return dict(
        n_prior_closes=len(prior_closes), adrf=adrf,
        ext=ext, no_ma_below=no_ma_below, **base,
    )


def alert_outcome(t: str, d: str):
    """Byte-matched to _expectedness_and_ranking.py::alert_outcome."""
    seq = ALERT_BARS.get(t, [])
    idx = next((i for i, b in enumerate(seq) if b[0] == d), None)
    if idx is None or idx < 20:
        return None
    adr = st.mean((b[2] - b[3]) / b[4] for b in seq[idx - 20:idx] if b[4] > 0)
    if adr <= 0:
        return None
    c0 = seq[idx][4]
    fwd = seq[idx + 1: idx + 21]
    if len(fwd) < 5:
        return None
    mx = max(b[2] for b in fwd)
    return dict(tailx=(mx - c0) / c0 / adr, nfwd=len(fwd))


# ═══════════════════════════════ reporting helpers ═════════════════════════════════════

def tail_line(name, rows):
    vals = [r["tailx"] for r in rows]
    sess = {r["date"] for r in rows}
    if not vals:
        return f"  {name:<40} n=  0"
    n8, s8 = share_ge(vals, 8.0)
    med = round(st.median(vals), 2)
    p9 = round(p90(vals), 2) if len(vals) >= 20 else None
    wins = sum(1 for r in rows if r.get("winner"))
    return (f"  {name:<40} n={len(vals):>3} ({len(sess):>2}s)  reach>=8xADR "
            f"{n8:>2} = {('%.1f%%' % s8) if s8 is not None and len(vals) >= MIN_N_SHARE else 'N<10'}"
            f"  P90={('%+.2fx' % p9) if p9 is not None else '  N<20'}  med={med:+.2f}x"
            + (f"  winners={wins}" if any("winner" in r for r in rows) else ""))


def compare(label, rows_a, name_a, rows_b, name_b, primary=False):
    w(f"  -- {label} --" + ("   << PRIMARY (pre-registered)" if primary else ""))
    w(tail_line(name_a, rows_a))
    w(tail_line(name_b, rows_b))
    va = [r["tailx"] for r in rows_a]
    vb = [r["tailx"] for r in rows_b]
    sa = [r["date"] for r in rows_a]
    sb = [r["date"] for r in rows_b]
    p_share = perm_p_stat(va, vb, sa, sb, share_stat(8.0))
    p_p90 = perm_p_stat(va, vb, sa, sb, lambda v: (p90(v) or 0.0)) if min(len(va), len(vb)) >= 20 else None
    w(f"    perm p (session-shuffled): share>=8xADR "
      f"{('p=%.4f' % p_share) if p_share is not None else 'N too thin'} · P90 "
      f"{('p=%.4f' % p_p90) if p_p90 is not None else 'N too thin'}")
    w()


def quartile_table(rows, key, title):
    vals = sorted(r[key] for r in rows)
    if len(vals) < 40:
        w(f"  {title}: n={len(vals)} too thin for quartiles")
        return
    qs = [vals[len(vals) // 4], vals[len(vals) // 2], vals[3 * len(vals) // 4]]
    w(f"  {title} (cuts at {qs[0]:.2f} / {qs[1]:.2f} / {qs[2]:.2f}):")
    for qi in range(4):
        lo = qs[qi - 1] if qi > 0 else None
        hi = qs[qi] if qi < 3 else None
        bucket = [r for r in rows
                  if (lo is None or r[key] > lo) and (hi is None or r[key] <= hi)]
        if qi == 0:
            bucket = [r for r in rows if r[key] <= qs[0]]
        w(tail_line(f"  Q{qi + 1}" + (" (lowest)" if qi == 0 else " (highest)" if qi == 3 else ""), bucket))


def spearman(xs, ys):
    def rank(v):
        s = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(s):
            j = i
            while j + 1 < len(s) and v[s[j + 1]] == v[s[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[s[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(xs), rank(ys)
    mx, my = st.mean(rx), st.mean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (vx * vy) if vx > 0 and vy > 0 else None


# ═══════════════════════════════════════ main ══════════════════════════════════════════

def run_population(rows, bars, label):
    """rows: dicts with ticker/date/tailx (+winner for cohort). Computes axes, prints
    coverage, runs the pre-registered tests."""
    w("=" * 98)
    w(f"POPULATION: {label} — n={len(rows)} rows, {len({r['date'] for r in rows})} sessions")
    w("=" * 98)
    for r in rows:
        r.update(axes_for(bars, r["ticker"], r["date"]))

    # ── coverage, stated per axis before any outcome table ──
    n = len(rows)
    ext_ok = [r for r in rows if r["n_prior_closes"] >= 50 and r["adrf"]]
    ext_val = [r for r in ext_ok if r["ext"] is not None]
    ext_nomabelow = [r for r in ext_ok if r["ext"] is None and r["no_ma_below"]]
    base_ok = [r for r in rows if r["base_days_raw40"] is not None]
    cens = [r for r in base_ok if r["base_censored_raw40"]]
    w(f"  COVERAGE axis1 (pre-gap extension): {len(ext_ok)}/{n} have >=50 prior closes + ADR20"
      f" ({len(ext_val)} with an MA below the prior close, {len(ext_nomabelow)} no-MA-below -> 0.0 by the zero convention)")
    w(f"  COVERAGE axis2 (base duration):     {len(base_ok)}/{n} have >=20 H/L prior sessions"
      f" ({len(cens)} censored at the history edge — base_days is a lower bound there)")
    w()

    # ══ AXIS 1 — pre-gap extension ══
    w("AXIS 1 — PRE-GAP EXTENSION (D-1 close vs its own SMAs, ADR units)")
    pool = [dict(r, extz=(r["ext"] if r["ext"] is not None else 0.0)) for r in ext_ok]
    med = st.median([r["extz"] for r in pool]) if pool else None
    lo = [r for r in pool if r["extz"] <= med]
    hi = [r for r in pool if r["extz"] > med]
    compare(f"median split at {med:.2f} xADR (zero-fill convention)",
            lo, "LESS pre-gap-extended (<=med)", hi, "MORE pre-gap-extended (>med)",
            primary=(label.startswith("PRIMARY")))
    quartile_table(pool, "extz", "quartiles of pre-gap extension (descriptive)")
    w()
    # sensitivity: excluding the no-MA-below zero-fills
    pool_x = [r for r in pool if r["ext"] is not None]
    if len(pool_x) >= 40:
        medx = st.median([r["extz"] for r in pool_x])
        compare(f"sensitivity — no-MA-below rows EXCLUDED, median split at {medx:.2f}",
                [r for r in pool_x if r["extz"] <= medx], "LESS extended",
                [r for r in pool_x if r["extz"] > medx], "MORE extended")

    # ══ AXIS 2 — base duration × quietness ══
    w("AXIS 2 — BASE DURATION x QUIETNESS (trailing containment, ceiling 40% raw)")
    # undecidable = quiet to the edge of <74 sessions of history: the true base_days is
    # "at least lookback" and the lookback can't reach the line — excluded, never defaulted
    undecidable = [r for r in base_ok
                   if r["base_censored_raw40"] and r["base_days_raw40"] < BINARY_BASE_DAYS]
    decidable = [r for r in base_ok
                 if not (r["base_censored_raw40"] and r["base_days_raw40"] < BINARY_BASE_DAYS)]
    long_b = [r for r in decidable if r["base_days_raw40"] >= BINARY_BASE_DAYS]
    short_b = [r for r in decidable if r["base_days_raw40"] < BINARY_BASE_DAYS]
    w(f"  binary decidability: {len(decidable)}/{len(base_ok)} decidable at the {BINARY_BASE_DAYS}d line"
      f" ({len(undecidable)} censored-below-{BINARY_BASE_DAYS} excluded, never defaulted)")
    compare(f"base >= {BINARY_BASE_DAYS}d (his smallest annotated base) vs shorter",
            long_b, f"LONG base (>={BINARY_BASE_DAYS}d quiet)", short_b, f"shorter base (<{BINARY_BASE_DAYS}d)",
            primary=(label.startswith("PRIMARY")))
    quartile_table(base_ok, "base_days_raw40", "quartiles of base_days raw40 (descriptive; censoring above)")
    w()
    # adr6 variant — registered secondary
    adr_ok = [r for r in rows if r["base_days_adr6"] is not None]
    dec6 = [r for r in adr_ok
            if not (r["base_censored_adr6"] and r["base_days_adr6"] < BINARY_BASE_DAYS)]
    l6 = [r for r in dec6 if r["base_days_adr6"] >= BINARY_BASE_DAYS]
    s6 = [r for r in dec6 if r["base_days_adr6"] < BINARY_BASE_DAYS]
    compare(f"SECONDARY variant — 6xADR20 ceiling, same {BINARY_BASE_DAYS}d line",
            l6, "LONG base (adr6)", s6, "shorter base (adr6)")

    # ── registered confound checks ──
    conf = [r for r in base_ok if r["adrf"]]
    if len(conf) >= 40:
        rho = spearman([r["base_days_raw40"] for r in conf], [r["adrf"] for r in conf])
        w(f"  CONFOUND: Spearman(base_days_raw40, ADR20) = {rho:+.3f} on n={len(conf)}")
        adrs = sorted(r["adrf"] for r in conf)
        madr = adrs[len(adrs) // 2]
        for half, name in ((
            [r for r in conf if r["adrf"] <= madr], "low-ADR half"),
            ([r for r in conf if r["adrf"] > madr], "high-ADR half"),
        ):
            dech = [r for r in half
                    if not (r["base_censored_raw40"] and r["base_days_raw40"] < BINARY_BASE_DAYS)]
            lb = [r for r in dech if r["base_days_raw40"] >= BINARY_BASE_DAYS]
            sb = [r for r in dech if r["base_days_raw40"] < BINARY_BASE_DAYS]
            compare(f"binary repeated inside the {name}", lb, f"LONG base ({name})", sb, f"shorter ({name})")
    # descriptive: net displacement of long-base rows (the "went nowhere" reading)
    disp = [r["base_net_disp_xadr"] for r in base_ok if r["base_net_disp_xadr"] is not None]
    if disp:
        w(f"  descriptive: net displacement over the base, median {st.median(disp):.1f} xADR"
          f" (p25 {sorted(disp)[len(disp) // 4]:.1f} / p75 {sorted(disp)[3 * len(disp) // 4]:.1f})")
    w()
    return rows


def main():
    w("#569 TWO-AXIS STRUCTURE SPLIT — corpus measurement (pre-registered; see module docstring)")
    w(f"binary line = {BINARY_BASE_DAYS} sessions · ceilings raw 40% / 6xADR20 · outcome = house tailx,")
    w("tail-first: share >=8xADR + P90, median secondary. MRNA is n=1 reference, NOT evidence.")
    w()

    # PRIMARY corpus — the 749 tier-A gap days with the 78 tail winners
    run_population(COHORT, COHORT_BARS, "PRIMARY — 749 tier-A gap days (_552_cohort.psv)")

    # SECONDARY corpus — live alerts with outcomes
    live = []
    for a in ALERTS:
        if a["source"] != "live":
            continue
        o = alert_outcome(a["ticker"], a["date"])
        if o is None:
            continue
        live.append(dict(ticker=a["ticker"], date=a["date"], tailx=o["tailx"]))
    run_population(live, ALERT_BARS, "SECONDARY — live alert corpus with outcomes")

    OUT.write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\n[capture] -> {OUT}")


if __name__ == "__main__":
    main()
