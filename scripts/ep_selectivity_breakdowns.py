"""EP Selectivity Phase 1 — per-dimension outcome breakdowns (Block 2).

Reads:
  analysis/2026-05-16/ep_cohort_alerts_60d.csv
  analysis/2026-05-16/ep_cohort_skipped_60d.csv

Writes:
  analysis/2026-05-16/breakdowns.md  (markdown tables for ADR §3)

Outcome convention:
  For ENTERED trades (trade_id IS NOT NULL): use total_pnl direction.
    win = total_pnl > 0
  For UNENTERED HIGH/MODERATE alerts: use ret_5d from missed_outcomes
    (gap-day open → +5 close).
    win = ret_5d > 0.05  (5% above gap-day open)
  When both present (entered AND unentered), prefer entered (we
  actually took the trade).
  When neither present: drop from outcome bucket (alert too recent for
  forward returns) and report n_pending separately.
"""
from __future__ import annotations

import csv
import logging
import statistics
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path("analysis/2026-05-16")
ALERTS_CSV = DATA_DIR / "ep_cohort_alerts_60d.csv"
SKIPPED_CSV = DATA_DIR / "ep_cohort_skipped_60d.csv"
OUT_MD = DATA_DIR / "breakdowns.md"


def load_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(v: str | None) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def derive_outcome(row: dict) -> tuple[str | None, float | None, str]:
    """Returns (outcome_state, return_pct, source).

    outcome_state ∈ {"win", "loss", "pending"}
    return_pct: -1.0 = -100%, 0.10 = +10%. None when pending.
    source ∈ {"trade", "missed", "scan", "none"}
    """
    # 1) If entered, use trade total_pnl direction
    trade_id = row.get("trade_id", "")
    trade_status = row.get("trade_status", "")
    if trade_id and trade_status == "closed":
        pnl = num(row.get("total_pnl"))
        entry_px = num(row.get("entry_price"))
        shares = num(row.get("entry_shares"))
        if pnl is not None and entry_px and shares:
            position_value = entry_px * shares
            ret = pnl / position_value if position_value else 0.0
            return ("win" if pnl > 0 else "loss"), ret, "trade"
        if pnl is not None:
            return ("win" if pnl > 0 else "loss"), None, "trade"

    # 2) Unentered HIGH/MODERATE: 5d forward from gap-day open
    ret_5d = num(row.get("ret_5d"))
    if ret_5d is not None:
        return ("win" if ret_5d > 0.05 else "loss"), ret_5d, "missed"

    # 3) Fallback: scan_outcomes 5d (baseline_close-relative).
    #    NOTE: mi_ep_scan_outcomes.fwd_5d_pct is stored in PERCENTAGE
    #    points (e.g. 5.0 = 5%), not decimal — verified 2026-05-16
    #    via histogram (range -3.4 to 124.97). Normalize to decimal
    #    for the unified outcome pipeline so it compares to ret_5d
    #    (which is decimal-fraction per missed_outcomes.py:310).
    fwd_5d_raw = num(row.get("fwd_5d_pct"))
    if fwd_5d_raw is not None:
        fwd_5d = fwd_5d_raw / 100.0
        return ("win" if fwd_5d > 0.05 else "loss"), fwd_5d, "scan"

    return "pending", None, "none"


def fmt_pct(v: float | None) -> str:
    return f"{v * 100:+.1f}%" if v is not None else "—"


def crosstab(rows: list[dict], bucket_fn, label: str) -> str:
    """Group rows by bucket_fn(row), compute n / win_rate / avg_ret / median_ret.

    Returns a markdown table. Pending (no outcome yet) rows reported
    separately at the bottom.
    """
    buckets: dict[str, list[tuple[str, float | None]]] = defaultdict(list)
    pending: dict[str, int] = defaultdict(int)
    for r in rows:
        bk = bucket_fn(r)
        if bk is None:
            continue
        outcome, ret, _src = derive_outcome(r)
        if outcome == "pending":
            pending[bk] += 1
        else:
            buckets[bk].append((outcome, ret))

    lines = [f"### {label}", ""]
    lines.append("| Bucket | N | Win rate | Avg ret | Median ret | Pending |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    # sort by N desc for readability
    order = sorted(buckets.keys(), key=lambda k: (-len(buckets[k]), k))
    for bk in order:
        items = buckets[bk]
        n = len(items)
        wins = sum(1 for o, _ in items if o == "win")
        rets = [r for _, r in items if r is not None]
        wr = wins / n if n else 0.0
        avg = statistics.mean(rets) if rets else None
        med = statistics.median(rets) if rets else None
        lines.append(
            f"| {bk} | {n} | {wr * 100:.1f}% | {fmt_pct(avg)} | "
            f"{fmt_pct(med)} | {pending.get(bk, 0)} |"
        )
    lines.append("")
    return "\n".join(lines)


# ── Bucket functions ────────────────────────────────────────────────────────

def b_gap_size(r):
    g = num(r.get("gap_pct"))
    if g is None:
        return None
    if g >= 25:
        return "25%+"
    if g >= 15:
        return "15-25%"
    if g >= 10:
        return "10-15%"
    if g >= 8:
        return "8-10%"
    return "<8%"


def b_catalyst_quality(r):
    return r.get("catalyst_quality") or "(null)"


def b_pm_rvol(r):
    v = num(r.get("pm_rvol"))
    if v is None:
        return "(no pm_rvol)"
    if v >= 10:
        return "10x+"
    if v >= 5:
        return "5-10x"
    if v >= 2:
        return "2-5x"
    if v >= 1:
        return "1-2x"
    return "<1x"


def b_score_tier(r):
    return r.get("score_tier") or "(null)"


def b_ep_score_band(r):
    s = num(r.get("ep_score"))
    if s is None:
        return None
    if s >= 80:
        return "HIGH-high (80+)"
    if s >= 70:
        return "HIGH-mid (70-79)"
    if s >= 60:
        return "HIGH-low (60-69)"
    if s >= 50:
        return "MOD-high (50-59)"
    return "MOD-low (<50)"


def b_alert_time(r):
    ts = r.get("detected_at", "")
    if not ts or "T" not in ts and " " not in ts:
        return "(no detected_at)"
    # detected_at is UTC; subtract 4h crude (DST-imprecise, fine for buckets)
    # Format e.g. "2026-05-15 11:32:14.123456+00:00"
    try:
        hhmm = ts.split(" ")[1][:5]
        hh, mm = int(hhmm[:2]), int(hhmm[3:5])
        et_hh = (hh - 4) % 24
    except (IndexError, ValueError):
        return "(unparseable)"
    et_min = et_hh * 60 + mm
    if et_min < 9 * 60 + 30:
        return "pre-market"
    if et_min < 9 * 60 + 45:
        return "9:30-9:44"
    if et_min < 10 * 60:
        return "9:45-9:59"
    if et_min < 11 * 60:
        return "10:00-10:59"
    return "11:00+"


def b_entry_attempt(r):
    ea = r.get("entry_attempt") or ""
    if not ea:
        return None
    return f"attempt {ea}"


def b_theme(r):
    return "in-theme" if r.get("theme_name") else "uncovered"


def b_theme_stage(r):
    return r.get("theme_stage") or "(uncovered)"


def b_flag_stage(r):
    return r.get("flag_stage") or "(no flag)"


def b_filter_reason(r):
    """Top-level filter taxonomy for the SKIPPED cohort. Collapses to
    a small set of prefixes — raw reasons are too granular (e.g.
    'pre-mkt volume 1,294 < 25,000 shares' is one of hundreds)."""
    fr = (r.get("skip_reason") or r.get("filter_reason") or "").lower()
    if not fr:
        return "(no reason)"
    if "outside top-20" in fr:
        return "outside_top20"
    if "pre-mkt volume" in fr or "premkt volume" in fr or "pm volume" in fr:
        return "pm_shares_floor"
    if "already up" in fr or "extension" in fr:
        return "extension_gate"
    if "low rel volume" in fr or "low volume" in fr or "rel_vol" in fr:
        return "rel_vol_low"
    if "score " in fr and ("< 50" in fr or "< bar" in fr):
        return "score_below_50"  # "< bar" = separation side since the #533 rescale
    if "ep cooldown" in fr or "cooldown" in fr:
        return "cooldown"
    if "routine catalyst" in fr:
        return "routine_catalyst"
    if "m&a" in fr or "m and a" in fr or "buyout" in fr:
        return "ma_filter"
    if "duplicate" in fr or "already scored" in fr:
        return "duplicate_scan"
    if "atr" in fr:
        return "atr_high"
    if "mcap" in fr:
        return "mcap_low"
    if "adv" in fr:
        return "adv_low"
    if "quality filter" in fr:
        return "quality_filter"
    return f"other:{fr[:30]}"


def b_skip_category(r):
    return r.get("skip_category") or "(no category)"


def b_traded_vs_not(r):
    return "traded" if r.get("trade_id") else "alerted-only"


def b_shadow_5m_paired(r):
    """5-min ORB shadow C1 dimension.

    Buckets every alert by whether it has a 5-min ORB shadow row, and
    if so whether the 5-min run was a fill or no_entry / cancelled.
    """
    ss = r.get("shadow_5m_status")
    if not ss:
        return "(no shadow row)"
    return f"5m: {ss}"


# Per-source breakdown of skipped cohort (to surface "which filter shed
# the most winners")
def crosstab_skipped_by_category() -> str:
    rows = load_rows(SKIPPED_CSV)
    return crosstab(rows, b_skip_category, "Skipped — by category (which filters shed?)")


def crosstab_skipped_by_filter_reason() -> str:
    rows = load_rows(SKIPPED_CSV)
    return crosstab(rows, b_filter_reason, "Skipped — by skip_reason top-level")


def main() -> None:
    rows = load_rows(ALERTS_CSV)
    logger.info("loaded %d alerts cohort rows", len(rows))

    sections = [
        "# EP Selectivity Phase 1 — Per-Dimension Breakdowns",
        "",
        f"_Generated from `{ALERTS_CSV.name}` ({len(rows)} alerts) and "
        f"`{SKIPPED_CSV.name}`._",
        "",
        "## Outcome definitions",
        "",
        "- ENTERED rows: outcome = sign of `total_pnl`; return = "
        "`pnl / (entry_price × entry_shares)`",
        "- UNENTERED rows: outcome = `ret_5d > 5%` (gap-day open → +5 close)",
        "- Fallback: `mi_ep_scan_outcomes.fwd_5d_pct` "
        "(baseline_close-relative)",
        "- Pending = alert too recent for 5d forward",
        "",
        "## §A — Existing entry filters (alert-side dimensions)",
        "",
        crosstab(rows, b_gap_size, "A1 — Gap size"),
        crosstab(rows, b_pm_rvol, "A2 — Pre-market RVOL@T"),
        crosstab(rows, b_alert_time, "A15 — Alert time (ET, approx)"),
        "",
        "## §B — Existing scoring",
        "",
        crosstab(rows, b_score_tier, "B10 — Score tier"),
        crosstab(rows, b_ep_score_band, "B10 — EP score band"),
        crosstab(rows, b_catalyst_quality, "B2 — Catalyst quality grade"),
        "",
        "## §C — Entry mechanics",
        "",
        crosstab(rows, b_entry_attempt, "C2 — Entry attempt (1 vs 2)"),
        crosstab(rows, b_shadow_5m_paired, "C1 — 5-min ORB shadow paired status"),
        "",
        "## §E — Setup context",
        "",
        crosstab(rows, b_theme, "E1 — Theme membership"),
        crosstab(rows, b_theme_stage, "E1 — Theme stage"),
        crosstab(rows, b_flag_stage, "E3 — Continuation flag stage"),
        "",
        "## Cohort partition: traded vs alerted-only",
        "",
        crosstab(rows, b_traded_vs_not, "Traded vs alerted-only"),
        "",
        "## §E5 — Missed-EP outcomes (filter-rejected forward returns)",
        "",
        crosstab_skipped_by_category(),
        crosstab_skipped_by_filter_reason(),
    ]

    OUT_MD.write_text("\n".join(sections), encoding="utf-8")
    logger.info("wrote %s", OUT_MD)


if __name__ == "__main__":
    main()
