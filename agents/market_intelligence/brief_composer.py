"""
#479 slice 1 — materiality-driven evening brief (Tue–Fri delta form).

Pure compose-time functions: (today rows, prior-trading-day rows) → brief text.
No DB, no I/O, no "now" reads — the caller (briefing.send_evening_briefing)
fetches everything and passes it in; tests construct BriefData directly.

Design + every measured distribution cited below:
    docs/analysis/479_materiality_brief_design_2026-07-26.md
Operator rulings folded in (2026-07-26):
  - Monday = FULL brief (weekly anchor, legacy layout); Tue–Fri = delta vs the
    PRIOR TRADING DAY (never vs Monday — drift would accumulate).
  - RISING / RECOVERY / ROTATION: aggregate-only lines, INLINE always (no
    drill-down command exists anywhere — verified; do not collapse them behind
    a hint that doesn't exist).
  - Leaders: SECTOR-CONCENTRATION line with day-over-day delta (supersedes the
    flat 10-ticker pin — name-level top-10 churn is measured noise, 3/10 names
    daily; sector concentration is the stable state variable). Deep jumps
    (beyond yesterday's #25 → top-10) stay the name-level exception.
  - Thresholds below are shipped-defaults to be tuned against real output.
  - 9M / sugar babies: NO line at all (strategy retired; /9m on demand).
  - v1.0 closeout line: retired.
  - "as long as all info is accessible via commands then simplifying brief is
    ok, make it clear how to dig deeper via command link" — every collapsed
    line carries its own verified drill-down hint (CITED_* below are pinned
    against the dispatch table in tests/test_brief_composer.py).

Display-composition only — no detector, safeguard, sizing, or entry logic is
read or changed here (THE LINE untouched).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from shared.dates import last_trading_day

# ── Materiality thresholds (shipped-defaults; distributions from the design doc §1) ──

# Theme |Δ rs_avg| day-over-day, 120d n=1,774 name-joined pairs (gap ≤4d, prior>0):
#   med 1.85 · p75 4.30 · p90 8.40 · p95 11.70 · p99 30.3
#   ≥8 → ~2.7/day (itemize, cap binds only on busy days) · ≥12 → 0–3/day (⚡ tier)
THEME_ITEMIZE_DELTA = 8.0     # ≈p90 — itemized, operator-ruled 2026-07-26
THEME_ITEMIZE_CAP = 5         # top-5 by |Δ| — overflow is counted, not shown
THEME_EMPHASIS_DELTA = 12.0   # ≈p95 — ⚡ emphasis tier
THEME_PRIOR_MAX_GAP_DAYS = 4  # themes legitimately skip days; a strict
                              # yesterday-join manufactures ~6.5 phantom births/day

# RS leaders, 45d dense window: 3.1 new top-10 names/day (churn = noise);
# entry from beyond yesterday's #25 ≈ 1.1/day (the "came out of nowhere" event).
LEADER_TOP_TIER = 10
LEADER_DEEP_JUMP_FROM = 25    # material only when yesterday's rank was beyond this

# VIX day-over-day |Δ|, 180d: avg 1.54 · p90 2.70 · max 21.64.
VIX_MATERIAL_DELTA = 2.7      # p90 — shown only when it fires; rides flip lines

# Crypto-vs-QQQ 4wk lead (shipped ±3 verdict bands in db.get_crypto_vs_market_pulse):
# verdict flips ~1 per 6 days; |Δ lead_4w| daily avg 2.70 · p90 5.86.
CRYPTO_LEAD_JUMP = 6.0        # ≈p90 — secondary materiality without a band flip

# Theme graduation: first time a theme reaches 7 days alive and still active
# (~0.8/day; only 55.6% of births survive to day 7 — survival IS the event,
# births are NOT: 4.2 births/day at median birth rs_avg 86.3, born-high is the norm).
THEME_GRADUATION_DAYS = 7

# Sector coverage asymmetry (verified 2026-07-26): mi_stock_scores carries sector
# for 100% of the top 20 and 99% of ranks 21–300, but only 16% beyond rank 300.
# Sector grouping is therefore sound for the LEADERS band only — do NOT reuse it
# for the recovery band (26% coverage; 3 of 69 recovery names had a sector 7/24).

# ── Reachability — every hint below is pinned against agent.py's dispatch ──────
# tests/test_brief_composer.py fails if any of these is absent from the dispatch
# dict / routing cascade (the 7/20 orphaning failure this task exists to correct).
CITED_SLASH_COMMANDS = frozenset({"/regime", "/themes", "/eps", "/detectors", "/wick", "/hud"})
CITED_PHRASES = frozenset({"rs leaders", "ep outcome", "show cooldowns", "pullback", "crypto"})

_NUM_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

_REGIME_EMOJI = {"Bull": "🟢", "Choppy": "🟡", "Correcting": "🔴", "Crisis": "🚨", "Unknown": "⚫"}

# Fixed mechanical abbreviations for FMP top-level sectors (structural, not prose).
_SECTOR_ABBREV = {
    "Healthcare": "Health", "Technology": "Tech", "Industrials": "Indust",
    "Energy": "Energy", "Consumer Defensive": "ConsDef", "Consumer Cyclical": "ConsCyc",
    "Financial Services": "Financl", "Basic Materials": "Materls", "Real Estate": "RE",
    "Communication Services": "Comms", "Utilities": "Utils",
}

_NET_SCORE_RE = re.compile(r"Net score\s*([+-]?\d+)")

_EP_ENTERED_STATES = {"filled", "closed", "order_placed", "pending_confirmation",
                      "confirmed", "submitting"}


# ── Calendar helpers (pure — no "now" reads; hygiene-gated frames stay intact) ─

def prior_trading_day(d: date) -> date:
    """Prior TRADING day strictly before `d` (weekend-aware; Monday → Friday).
    Holiday-blind by design — the composer resolves actual prior DATA dates
    from the tables (max prior row), so this is the calendar label, not the join key."""
    return last_trading_day(d - timedelta(days=1))


def brief_mode(d: date) -> str:
    """Monday = 'full' (weekly reference/anchor, operator-ruled 2026-07-26);
    every other day = 'delta' vs the prior trading day."""
    return "full" if d.weekday() == 0 else "delta"


# ── Deterministic ranking (the RS-100 tie-order guard) ─────────────────────────

def rank_leaders(rows: list[dict]) -> list[dict]:
    """Deterministically re-rank a leaders list: (-rs_composite, ticker).

    8+ names print RS 100 and `ORDER BY rs_composite DESC` breaks ties
    arbitrarily — two identical prod queries minutes apart returned different
    owners of rank 7 for the same date (design §1.3). Without this re-sort the
    day-over-day rank diff emits PHANTOM jumps. Ties break alphabetically on
    both days, so equal-score shuffles produce zero diff."""
    return sorted(rows, key=lambda r: (-(r.get("rs_composite") or 0.0), r.get("ticker") or ""))


def _esc(s: str) -> str:
    """Strip Markdown entity chars from free-text (theme names, descriptions,
    skip labels) rendered OUTSIDE backticks. One bare `_` flips the entity
    parity of the whole Telegram chunk (#477 class, 2026-07-16)."""
    return re.sub(r"[*_`\[\]]", "", s or "").strip()


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _parse_net(description: str | None) -> int | None:
    m = _NET_SCORE_RE.search(description or "")
    return int(m.group(1)) if m else None


def _sector_abbrev(sector: str | None) -> str:
    if not sector:
        return "?"
    return _SECTOR_ABBREV.get(sector, _esc(sector)[:7])


# ── Input container (tests construct this directly; briefing.py fills it) ──────

@dataclass
class BriefData:
    """None on any *optional* field means "the fetch FAILED / no substrate" —
    the corresponding line must say so explicitly. Silence must never be
    ambiguous with "didn't run" (design §4)."""
    briefing_date: date
    prior_trading_date: date | None = None

    # regime — regime_history is newest-first rows ≤ briefing_date
    # ({regime_date, regime, vix, ep_threshold, description}); regime is the
    # full latest row incl. breadth_history_5d for the cluster rule.
    regime: dict = field(default_factory=dict)
    regime_history: list[dict] | None = None
    size_mult: float | None = None

    # crypto pulse — {} means unavailable (db returns {} on failure and audits)
    crypto_pulse: dict = field(default_factory=dict)
    crypto_pulse_prior: dict = field(default_factory=dict)

    # themes — theme_scores: today's computed scores [{name, comp, stage}]
    # (live path: trimmed-mean comp, same value the scorecard renders);
    # theme_prior: name → {rs_avg, stage, days_active} last seen ≤4d back.
    theme_scores: list[dict] = field(default_factory=list)
    theme_prior: dict[str, dict] | None = None
    theme_births_today: int | None = None
    theme_days_active: dict[str, int] = field(default_factory=dict)

    # leaders — today rows (top ~30) and prior score-date rows (depth ~100),
    # each row {ticker, rs_composite, sector, desc?}. prior None = no substrate.
    rs_leaders: list[dict] = field(default_factory=list)
    rs_leaders_prior: list[dict] | None = None
    prior_leader_depth: int = 100

    # theme membership (for the unanchored standing count)
    themed_tickers_today: set = field(default_factory=set)
    themed_tickers_prior: set | None = None

    # EP recap — today's outcome rows (get_ep_outcomes filtered to today);
    # None = fetch failed.
    ep_outcomes: list[dict] | None = field(default_factory=list)

    # detectors (today counts; None = fetch failed)
    wick_today_count: int | None = 0
    wick_fill_rate_30d: float | None = None
    wick_settled_30d: int = 0
    undercut_today_count: int | None = 0
    flag_breaks_today: int | None = 0

    # lenses (aggregate-only, inline always — no command exists, design §1.6)
    velocity_qual: int | None = None
    recovery_qual: int | None = None
    recovery_top: str | None = None
    rotation_clusters: list[tuple] = field(default_factory=list)  # [(sector, n), ...]

    # cooldowns
    cooldowns_active: int | None = None
    cooldowns_new_today: int = 0

    # pre-rendered add-on blocks (caller-owned formatters)
    quality_block: str | None = None
    signal_quality_block: str | None = None
    is_friday: bool = False


# ── Per-class materiality computations (each returns (block_lines|None, ...)) ──

def _today_regime_row(data: BriefData) -> dict | None:
    """History row for the briefing date itself — None when the regime job
    hasn't written today (stale row must NOT silently masquerade as today's)."""
    hist = data.regime_history or []
    if hist and hist[0].get("regime_date") == data.briefing_date:
        return hist[0]
    return None


def _regime_streak(hist: list[dict]) -> int:
    """Consecutive days (incl. today) with the same label, newest-first rows."""
    if not hist:
        return 0
    label = hist[0].get("regime")
    n = 0
    for row in hist:
        if row.get("regime") != label:
            break
        n += 1
    return n


def _flips_this_week(hist: list[dict]) -> int:
    """Label transitions among the last 5 rows (a trading week), newest-first."""
    window = hist[:6]  # 6 rows → up to 5 adjacent transitions
    return sum(
        1 for a, b in zip(window, window[1:])
        if a.get("regime") != b.get("regime")
    )


def _cluster_state(regime: dict) -> tuple[bool, int, int]:
    """(fires, red_count, window) via the existing breadth cluster rule."""
    from agents.market_intelligence.breadth_color_rules import (
        cluster_fires, red_count_in_window, CLUSTER_WINDOW,
    )
    history = regime.get("breadth_history_5d") or []
    if len(history) >= CLUSTER_WINDOW and cluster_fires(history):
        return True, red_count_in_window(history), CLUSTER_WINDOW
    return False, 0, CLUSTER_WINDOW


def _regime_material(data: BriefData) -> tuple[list[str] | None, bool]:
    """Class 1: label flip · EP-filter change · VIX ≥ p90 · breadth-cluster fire.
    Returns (block lines or None, label_flipped)."""
    hist = data.regime_history or []
    today = _today_regime_row(data)
    prior = hist[1] if len(hist) > 1 else None
    if today is None or prior is None:
        return None, False  # honesty handled by the state line

    label_t, label_p = today.get("regime"), prior.get("regime")
    flipped = bool(label_t and label_p and label_t != label_p)
    thr_t, thr_p = today.get("ep_threshold"), prior.get("ep_threshold")
    thr_changed = thr_t is not None and thr_p is not None and thr_t != thr_p
    vix_t, vix_p = today.get("vix"), prior.get("vix")
    # Threshold compares the ROUNDED display value (what the operator sees):
    # a shown "+2.7" must fire and a shown "+2.6" must not — raw-float compares
    # would let binary representation decide the boundary.
    vix_delta = round(vix_t - vix_p, 1) if (vix_t is not None and vix_p is not None) else None
    vix_fires = vix_delta is not None and abs(vix_delta) >= VIX_MATERIAL_DELTA
    fires, red_n, window = _cluster_state(data.regime)

    if not (flipped or thr_changed or vix_fires or fires):
        return None, False

    emoji = _REGIME_EMOJI.get(label_t, "⚫")
    lines: list[str] = []
    if flipped:
        lines.append(f"{emoji} *REGIME: {_esc(label_p).upper()} → {_esc(label_t).upper()}*")
    elif thr_changed:
        lines.append(f"{emoji} *REGIME — EP filter {thr_p} → {thr_t}*")
    elif fires:
        lines.append(f"{emoji} *REGIME — breadth cluster {red_n}/{window} red*")
    else:
        lines.append(f"{emoji} *REGIME — VIX {vix_t:.1f} ({vix_delta:+.1f} d/d)*")

    # The trading-actionable consequence line (what the operator acts on).
    size_str = f" · size ≈{data.size_mult:.2f}×" if data.size_mult is not None else ""
    if thr_changed:
        direction = "tightened" if thr_t > thr_p else "loosened"
        lines.append(f"   EP filter {thr_p} → {thr_t} ({direction}){size_str}")
    else:
        lines.append(f"   EP filter ≥{thr_t} (unch){size_str}")

    net_t, net_p = _parse_net(today.get("description")), _parse_net(prior.get("description"))
    bits = []
    if net_t is not None:
        bits.append(f"Net {net_p:+d} → {net_t:+d}" if net_p is not None else f"Net {net_t:+d}")
    if vix_t is not None:
        bits.append(f"VIX {vix_t:.1f}" + (f" ({vix_delta:+.1f})" if vix_delta is not None else ""))
    if flipped:
        n_flips = _flips_this_week(hist)
        if n_flips >= 2:
            bits.append(f"{_ordinal(n_flips)} flip this week — chop")
    if bits:
        lines.append("   " + " · ".join(bits))
    if fires:
        lines.append(f"   ⚠️ Cluster {red_n}/{window} red — deterioration")
    lines.append("   `/regime` full matrix")
    return lines, flipped


def _crypto_material(data: BriefData) -> list[str] | None:
    """Class 1: crypto verdict band flip (±3 bands, shipped) or 4wk-lead jump ≥ p90."""
    t, p = data.crypto_pulse, data.crypto_pulse_prior
    if not t or not p:
        return None  # unavailable → state line says so
    v_t, v_p = t.get("verdict"), p.get("verdict")
    lead_t, lead_p = t.get("lead_4w"), p.get("lead_4w")
    lead_str = f" ({lead_t:+.1f} vs QQQ 4wk)" if lead_t is not None else ""
    if v_t and v_p and v_t != v_p:
        return [f"🪙 *CRYPTO: {_esc(v_p)} → {_esc(v_t)}*{lead_str}",
                "   _detail: \"crypto\"_"]
    if lead_t is not None and lead_p is not None:
        lead_delta = round(lead_t - lead_p, 1)  # display-precision boundary
        if abs(lead_delta) >= CRYPTO_LEAD_JUMP:
            return [f"🪙 *CRYPTO — 4wk lead {lead_t:+.1f} (Δ{lead_delta:+.1f} d/d)* — still {_esc(v_t or '?')}",
                    "   _detail: \"crypto\"_"]
    return None


def compute_theme_movers(
    theme_scores: list[dict], theme_prior: dict[str, dict],
) -> list[dict]:
    """Day-over-day theme moves with the rs_avg=0 artifact guard.

    prior must be > 0: a `rs_avg=0` prior row manufactured one fake +70.6
    "move" on 7/24 (design §1.2) — zero is a data artifact, not a level.
    Returns [{name, level, delta, stage, prior_stage}] sorted by |delta| desc."""
    movers = []
    for st in theme_scores:
        name = st.get("name")
        comp = st.get("comp")
        if name is None or comp is None:
            continue
        prior = theme_prior.get(name)
        if not prior:
            continue
        prior_rs = prior.get("rs_avg")
        if prior_rs is None or not prior_rs > 0:   # the rs_avg=0 guard
            continue
        # Rounded to the displayed precision so the ≥8/≥12 boundaries match
        # exactly what the operator reads on the line.
        delta = round(float(comp) - float(prior_rs), 1)
        if abs(delta) >= THEME_ITEMIZE_DELTA:
            movers.append({
                "name": name, "level": float(comp), "delta": delta,
                "stage": st.get("stage") or "", "prior_stage": prior.get("stage"),
            })
    movers.sort(key=lambda m: -abs(m["delta"]))
    return movers


def compute_theme_graduations(
    theme_scores: list[dict], theme_prior: dict[str, dict],
    theme_days_active: dict[str, int],
) -> list[str]:
    """First crossing of days_active ≥ 7 while still active (not Fading) —
    survival through the validation week is the material event (design §1.2;
    days_active increments per active day and freezes while Fading —
    theme_engine persist step, confirmed at build)."""
    grads = []
    for st in theme_scores:
        name = st.get("name")
        if not name or (st.get("stage") or "") == "Fading":
            continue
        today_days = theme_days_active.get(name)
        prior = theme_prior.get(name) or {}
        prior_days = prior.get("days_active")
        if (today_days is not None and prior_days is not None
                and prior_days < THEME_GRADUATION_DAYS <= today_days):
            grads.append(name)
    return grads


def _theme_material(data: BriefData) -> tuple[list[str] | None, dict]:
    """Class 2: |Δ rs_avg| ≥ 8 itemized (⚡ at ≥12, cap top-5) + graduations.
    Returns (block lines or None, counts-for-state/footer)."""
    counts: dict = {"movers": 0, "overflow": 0, "quiet": 0, "seeded": data.theme_births_today,
                    "grads": [], "prior_ok": data.theme_prior is not None and len(data.theme_prior) > 0}
    scores = data.theme_scores
    if not counts["prior_ok"]:
        return None, counts

    movers = compute_theme_movers(scores, data.theme_prior)
    grads = compute_theme_graduations(scores, data.theme_prior, data.theme_days_active)
    counts["grads"] = grads
    counts["movers"] = len(movers)
    seeded = data.theme_births_today or 0
    counts["quiet"] = max(0, len(scores) - len(movers) - seeded)

    if not movers and not grads:
        return None, counts

    shown = movers[:THEME_ITEMIZE_CAP]
    counts["overflow"] = len(movers) - len(shown)

    lines: list[str] = []
    if len(movers) == 1:
        lines.append("📊 *THEME BREAK*")
    elif movers:
        # Operator 2026-07-28: "all of it is very confusing". The old header read
        # "N moved ≥8, top 5:" which implied a LEADERBOARD of the best themes.
        # It is neither: "moved ≥8" counts moves in EITHER direction, and "top 5"
        # means the five BIGGEST MOVES, not the five strongest. On a red day that
        # renders five collapsing themes under a heading that looks like a ranking.
        # Say what it is.
        cap_note = (f" — biggest {THEME_ITEMIZE_CAP}:" if len(movers) > THEME_ITEMIZE_CAP
                    else ":")
        lines.append(
            f"📊 *THEMES — {len(movers)} moved ≥{THEME_ITEMIZE_DELTA:.0f} pts"
            f"{cap_note}*"
        )
    else:
        lines.append("📊 *THEMES*")

    # "now #1" annotation: newly top by level vs prior board's top name.
    top_today = max(scores, key=lambda s: s.get("comp") or 0)["name"] if scores else None
    prior_vals = {n: p.get("rs_avg") for n, p in (data.theme_prior or {}).items()
                  if p.get("rs_avg") and p.get("rs_avg") > 0}
    top_prior = max(prior_vals, key=prior_vals.get) if prior_vals else None

    width = min(22, max((len(m["name"]) for m in shown), default=0))
    for m in shown:
        mark = "⚡" if abs(m["delta"]) >= THEME_EMPHASIS_DELTA else ""
        name = _esc(m["name"])
        name = (name[: width - 1] + "…") if len(name) > width else name
        suffix = ""
        if m["prior_stage"] is not None and m["stage"] and m["stage"] != m["prior_stage"]:
            suffix += f"  {_esc(m['stage'])}"   # stage flip rides the qualified mover
        if m["name"] == top_today and top_today != top_prior:
            suffix += "  ← now #1"
        # Label the two numbers and show where it CAME FROM. The bare
        # "25 -31.0" gave no clue that 25 is the theme's RS now and -31 is the
        # move, nor that it stood at 56 yesterday — so a big faller read as a
        # weak leaderboard entry (operator 2026-07-28).
        _arrow = "▼" if m["delta"] < 0 else "▲"
        _was = m["level"] - m["delta"]
        lines.append(
            f"{mark}`{name:<{width}} RS {m['level']:>3.0f}  {_arrow}{abs(m['delta']):.0f}"
            f"  (was {_was:.0f})`{suffix}"
        )

    for g in grads:
        lines.append(f"🎓 Graduated: {_esc(g)} — survived validation week")

    seeded_n = data.theme_births_today if data.theme_births_today is not None else "?"
    lines.append(
        f"   _+{counts['overflow']} more ≥{THEME_ITEMIZE_DELTA:.0f} · {counts['quiet']} quiet · "
        f"{seeded_n} seeded · {len(grads)} grad · `/themes`_"
    )
    return lines, counts


def compute_deep_jumps(
    leaders_today: list[dict], leaders_prior: list[dict], prior_depth: int,
) -> list[dict]:
    """Entries into the top-10 from beyond yesterday's #25 (~1.1/day; design §1.3).
    Both lists are re-ranked deterministically first (the tie-order guard)."""
    today_ranked = rank_leaders(leaders_today)[:LEADER_TOP_TIER]
    prior_ranked = rank_leaders(leaders_prior)
    prior_rank = {r.get("ticker"): i + 1 for i, r in enumerate(prior_ranked)}
    jumps = []
    for i, row in enumerate(today_ranked):
        tk = row.get("ticker")
        p = prior_rank.get(tk)
        if p is None or p > LEADER_DEEP_JUMP_FROM:
            jumps.append({
                "ticker": tk, "rs": row.get("rs_composite"),
                "rank_now": i + 1, "rank_prior": p,   # None = beyond prior_depth
                "desc": row.get("desc") or row.get("sector") or "",
            })
    return jumps


def _leaders_material(data: BriefData) -> tuple[list[str] | None, list[dict]]:
    """Class 3: deep jumps itemized with rank path. Shuffle-only days emit nothing
    here — the always-present sector-concentration state line asserts the check."""
    if data.rs_leaders_prior is None or not data.rs_leaders:
        return None, []
    jumps = compute_deep_jumps(data.rs_leaders, data.rs_leaders_prior, data.prior_leader_depth)
    if not jumps:
        return None, []
    s = "s" if len(jumps) != 1 else ""
    lines = [f"🚀 *LEADERS — {len(jumps)} deep jump{s} into top-10*"]
    for j in jumps[:5]:
        old = f"#{j['rank_prior']}" if j["rank_prior"] is not None else f"#>{data.prior_leader_depth}"
        rs = f"{j['rs']:.0f}" if j["rs"] is not None else "?"
        desc = f"  {_esc(j['desc'])}" if j["desc"] else ""
        lines.append(f"`{j['ticker']:<5} RS {rs:>3}   {old} → #{j['rank_now']}`{desc}")
    lines.append("   _other slots: shuffle only · \"rs leaders\"_")
    return lines, jumps


def sector_concentration(leaders_today: list[dict]) -> Counter:
    """Sector → count over the deterministically-ranked top-10. Sound HERE only:
    sector coverage is 100% for the top 20 / 99% to rank 300, but 16% beyond —
    never reuse this for the recovery band (26% coverage, design §1.6)."""
    top = rank_leaders(leaders_today)[:LEADER_TOP_TIER]
    return Counter(_sector_abbrev(r.get("sector")) for r in top)


def _leaders_state_line(data: BriefData, jumps: list[dict]) -> str:
    """The ALWAYS-present sector-concentration line (operator 2026-07-26,
    supersedes the flat ticker pin): which sectors own the top tier, counts,
    day-over-day entered/dropped. Structural, never prose."""
    if not data.rs_leaders:
        return "Top-10: no scores for today — diff skipped · \"rs leaders\""
    today_c = sector_concentration(data.rs_leaders)
    parts = []
    if data.rs_leaders_prior is None:
        for sec, n in today_c.most_common():
            parts.append(f"{sec} {n}")
        return ("Top-10 sectors: " + " · ".join(parts)
                + " (no prior-day scores — Δ skipped) · \"rs leaders\"")
    prior_c = sector_concentration(data.rs_leaders_prior)
    for sec, n in today_c.most_common():
        d = n - prior_c.get(sec, 0)
        delta_note = f" ({d:+d})" if abs(d) >= 2 else ""
        parts.append(f"{sec} {n}{delta_note}")
    entered = [s for s in today_c if s not in prior_c]
    dropped = [s for s in prior_c if s not in today_c]
    delta_bits = [f"+{s}" for s in entered] + [f"−{s}" for s in dropped]
    delta_str = f" (Δ {' '.join(delta_bits)})" if delta_bits else " (Δ none)"
    tail = "" if jumps else " · no deep jumps"
    return "Top-10 sectors: " + " · ".join(parts) + delta_str + tail + " · \"rs leaders\""


def _ep_bucket(row: dict) -> str:
    st, pt = row.get("trade_status"), row.get("pt_status")
    if st == "traded" and pt in _EP_ENTERED_STATES:
        return "entered"
    return "other"


def _ep_material(data: BriefData) -> tuple[list[str] | None, dict]:
    """Class 4: HIGHs that produced an entry, or anomalous terminal states
    (no terminal state at all / infra:* skip). Detection is old news by evening
    — HIGHs alert in real time intraday (design §1.5)."""
    counts = {"high": 0, "moderate": 0, "entered": 0, "ok": data.ep_outcomes is not None}
    if data.ep_outcomes is None:
        return None, counts
    high = [o for o in data.ep_outcomes if o.get("score_tier") == "HIGH"]
    moderate = [o for o in data.ep_outcomes if o.get("score_tier") == "MODERATE"]
    counts["high"], counts["moderate"] = len(high), len(moderate)
    entered = [o for o in data.ep_outcomes if _ep_bucket(o) == "entered"]
    anomalies = [o for o in high
                 if o.get("trade_status") == "no_attempt"
                 or str(o.get("skip_reason") or "").startswith("infra:")]
    counts["entered"] = len(entered)
    if not entered and not anomalies:
        return None, counts

    if entered:
        head = f"🔥 *EP — {len(entered)} entered*"
    else:
        head = "🔥 *EP — terminal-state anomalies*"
    lines = [head]
    for o in entered[:5]:
        price = o.get("last_entry_price")
        fwd = o.get("fwd_1d_pct")
        p_str = f"@${float(price):.2f}" if price else "entered"
        f_str = f" {float(fwd):+.1f}%" if fwd is not None else ""
        lines.append(f"`{o['ticker']}` {p_str}{f_str}")
    if anomalies:
        from agents.market_intelligence.broker.skip_reasons import humanize
        for o in anomalies[:5]:
            label = ("no terminal state" if o.get("trade_status") == "no_attempt"
                     else _esc(humanize(o.get("skip_reason"))))
            lines.append(f"`{o['ticker']}` ⚠️ {label}")
    lines.append(f"   _{counts['high']} HIGH · {counts['moderate']} MODERATE today · "
                 f"`/eps` · history: \"ep outcome\"_")
    return lines, counts


def compute_unanchored(leaders: list[dict], themed_tickers: set) -> list[str]:
    """RS 80+ leaders in no theme (same-date membership) — parity with the
    legacy _format_unanchored_section filter (ETF prefix + index skips)."""
    return [
        s["ticker"] for s in leaders
        if (s.get("rs_composite") or 0) >= 80
        and s.get("ticker") not in themed_tickers
        and not str(s.get("ticker") or "").startswith("X")
        and s.get("ticker") not in ("SPY", "QQQ", "IWM")
    ]


# ── State block (one line per quiet area — every line asserts the check RAN) ──

def _regime_state_line(data: BriefData) -> str:
    hist = data.regime_history or []
    today = _today_regime_row(data)
    if data.regime_history is None:
        return "Regime: history fetch failed — `/regime`"
    if today is None:
        last = hist[0].get("regime_date") if hist else None
        last_s = f" (last row {last})" if last else ""
        return f"Regime: no row for today{last_s} — `/regime`"
    prior = hist[1] if len(hist) > 1 else None
    label = today.get("regime") or "Unknown"
    bits = [f"Regime {_esc(label).upper()} ({_ordinal(_regime_streak(hist))} day)"]
    net = _parse_net(today.get("description"))
    if net is not None:
        bits.append(f"net {net:+d}")
    vix = today.get("vix")
    if vix is not None:
        p_vix = prior.get("vix") if prior else None
        d_str = f" ({vix - p_vix:+.1f})" if p_vix is not None else ""
        bits.append(f"VIX {vix:.1f}{d_str}")
    thr = today.get("ep_threshold")
    if thr is not None:
        bits.append(f"filter ≥{thr}")
    if data.size_mult is not None:
        bits.append(f"size ≈{data.size_mult:.2f}×")
    return " · ".join(bits) + " · `/regime`"


def _crypto_state_line(data: BriefData) -> str:
    t = data.crypto_pulse
    if not t:
        return "Crypto: pulse unavailable — \"crypto\""
    v = _esc(t.get("verdict") or "MIXED")
    lead = t.get("lead_4w")
    p = data.crypto_pulse_prior
    unch = " unch," if (p and p.get("verdict") == t.get("verdict")) else ""
    lead_s = f"{unch} {lead:+.1f} vs QQQ 4wk" if lead is not None else f"{unch} lead n/a"
    return f"Crypto {v} ({lead_s.strip()}) · \"crypto\""


def _theme_state_line(data: BriefData, counts: dict) -> str:
    n_active = len(data.theme_scores)
    if not counts["prior_ok"]:
        return (f"Themes: no prior snapshot ≤{THEME_PRIOR_MAX_GAP_DAYS}d — Δ skipped · "
                f"{n_active} active · `/themes`")
    seeded = counts["seeded"] if counts["seeded"] is not None else "?"
    return (f"Themes: none moved ≥{THEME_ITEMIZE_DELTA:.0f} · {counts['quiet']} quiet · "
            f"{seeded} seeded · {len(counts['grads'])} grad · `/themes`")


def _lenses_state_line(data: BriefData) -> str:
    # Aggregate-only, INLINE always — no drill-down command exists (design §1.6);
    # collapsing these behind a nonexistent hint would orphan them.
    rising = (f"{data.velocity_qual} qual" if data.velocity_qual is not None
              else "fetch failed")
    if data.recovery_qual is None:
        recov = "fetch failed"
    else:
        top = f" (top {data.recovery_top})" if data.recovery_top else ""
        recov = f"{data.recovery_qual} qual{top}"
    if data.rotation_clusters:
        sec, n = data.rotation_clusters[0]
        rot = f"{_sector_abbrev(sec)} ({n}) turning"
    else:
        rot = "none ≥3wk"
    return f"Lenses: Rising {rising} · Recovery {recov} · Rotation {rot}"


def _ep_state_line(counts: dict) -> str:
    if not counts["ok"]:
        return "EP: outcomes fetch failed — `/eps`"
    return (f"EP: {counts['high']} HIGH · {counts['moderate']} MOD · "
            f"no entries · `/eps`")


def _detectors_state_line(data: BriefData) -> str:
    def _c(v):
        return "?" if v is None else v
    wick, flags, unr = data.wick_today_count, data.flag_breaks_today, data.undercut_today_count
    if wick == 0 and flags == 0 and unr == 0:
        body = "quiet"
    else:
        bits = []
        if wick != 0:
            bits.append(f"{_c(wick)} wick")
        if flags != 0:
            bits.append(f"{_c(flags)} flag-break")
        if unr != 0:
            bits.append(f"{_c(unr)} U&R")
        body = " · ".join(bits)
    line = f"Detectors: {body} · `/detectors`"
    if data.is_friday and data.wick_fill_rate_30d is not None and data.wick_settled_30d:
        line += (f" · 30d wick fill {data.wick_fill_rate_30d * 100:.0f}% "
                 f"({data.wick_settled_30d} settled) · `/wick`")
    return line


def _standing_state_line(data: BriefData) -> str:
    un_today = len(compute_unanchored(data.rs_leaders, data.themed_tickers_today))
    if data.themed_tickers_prior is None or data.rs_leaders_prior is None:
        un_str = f"Unanchored {un_today} (Δ?)"
    else:
        prior_top = rank_leaders(data.rs_leaders_prior)[:30]
        un_prior = len(compute_unanchored(prior_top, data.themed_tickers_prior))
        d = un_today - un_prior
        un_str = f"Unanchored {un_today} ({d:+d})" if d else f"Unanchored {un_today} (±0)"
    if data.cooldowns_active is None:
        cd_str = "Cooldowns ? (fetch failed)"
    else:
        cd_str = f"Cooldowns {data.cooldowns_active} (+{data.cooldowns_new_today})"
    return f"{un_str} · {cd_str} · \"show cooldowns\""


# ── Assembly ───────────────────────────────────────────────────────────────────

def compose_evening_brief(data: BriefData) -> str:
    """The Tue–Fri delta brief: materiality blocks (fixed class precedence,
    design §3 — never re-ordered by a per-day score) + the checked-everything
    state block. Target shape: design §4 (quiet ~650 chars) / §5 (busy ~950)."""
    regime_block, regime_flipped = _regime_material(data)
    crypto_block = _crypto_material(data)
    theme_block, theme_counts = _theme_material(data)
    leaders_block, jumps = _leaders_material(data)
    ep_block, ep_counts = _ep_material(data)

    # Fixed class precedence: regime-state → themes → leaders → recap (design §3).
    blocks = [b for b in (regime_block, crypto_block, theme_block, leaders_block, ep_block) if b]

    out: list[str] = [f"*Apollo Evening Brief — {data.briefing_date.isoformat()}*"]
    if blocks:
        suffix = " — regime flipped" if regime_flipped else ""
        out.append(f"⚡ {len(blocks)} material tonight{suffix}")
    else:
        out.append("✅ Nothing material tonight")

    if data.quality_block:
        out.append("")
        out.append(data.quality_block)

    for i, block in enumerate(blocks):
        out.append("")
        out.append(f"{_NUM_EMOJI[i]} {block[0]}")
        out.extend(block[1:])

    # State block — one line per quiet area, fixed order (regime · crypto ·
    # themes · leaders · lenses · EP · detectors · standing). Proves every
    # check ran; a material area's info lives in its block instead.
    out.append("")
    out.append("— no change —")
    if regime_block is None:
        out.append(_regime_state_line(data))
    if crypto_block is None:
        out.append(_crypto_state_line(data))
    if theme_block is None:
        out.append(_theme_state_line(data, theme_counts))
    out.append(_leaders_state_line(data, jumps))
    out.append(_lenses_state_line(data))
    if ep_block is None:
        out.append(_ep_state_line(ep_counts))
    out.append(_detectors_state_line(data))
    out.append(_standing_state_line(data))

    if data.is_friday and data.signal_quality_block:
        out.append("")
        out.append(data.signal_quality_block)

    out.append("")
    out.append("_detail: `/hud` · \"ep outcome\" · \"pullback\"_")
    out.append("_Do your review. Pull up charts. Apply your judgment._")
    return "\n".join(out)
