"""#479 slice 1 — materiality-driven evening brief (brief_composer) pins.

Pins, per the build card:
  - Monday renders full / Tue–Fri (and weekends) render delta
  - prior-trading-day resolution across a weekend
  - every threshold at its boundary (just-under emits nothing, just-over emits)
  - the RS-100 tie-order guard (no phantom rank jumps)
  - the rs_avg=0 prior guard (no manufactured +70 movers)
  - a true-zero-material night produces the short form
  - NO cited drill-down command is absent from agent.py's dispatch dict /
    routing cascade (the 7/20 orphaning failure this task corrects)
  - missing substrate renders an explicit "Δ skipped / fetch failed" line —
    silence is never ambiguous with "didn't run"
"""
import asyncio
import re
from datetime import date, timedelta

import pytest

from agents.market_intelligence.brief_composer import (
    BriefData,
    CITED_PHRASES,
    CITED_SLASH_COMMANDS,
    brief_mode,
    compose_evening_brief,
    compute_deep_jumps,
    compute_theme_movers,
    prior_trading_day,
    rank_leaders,
    sector_concentration,
)

THU = date(2026, 7, 23)  # a Thursday → delta day


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _hist(briefing_date=THU, labels=None, vixes=None, thresholds=None, nets=None, n=6):
    labels = labels or ["Correcting"] * n
    vixes = vixes if vixes is not None else [16.6] * n
    thresholds = thresholds or [75] * n
    nets = nets or [-1] * n
    return [
        {
            "regime_date": briefing_date - timedelta(days=i),
            "regime": labels[i],
            "vix": vixes[i],
            "ep_threshold": thresholds[i],
            "description": f"⚪ Regime\nNet score {nets[i]:+d} (3 bullish · 4 bearish)",
        }
        for i in range(n)
    ]


def _mk_rows(names, sector="Technology", start_rs=200.0):
    """Distinct descending scores → deterministic ranks equal to list order."""
    return [
        {"ticker": t, "rs_composite": start_rs - i, "sector": sector}
        for i, t in enumerate(names)
    ]


def _quiet_data(**over):
    prior_rows = _mk_rows([f"T{i:02d}" for i in range(30)])
    data = BriefData(
        briefing_date=THU,
        prior_trading_date=prior_trading_day(THU),
        regime={"regime": "Correcting", "vix": 16.6, "ep_threshold": 75},
        regime_history=_hist(),
        size_mult=0.75,
        crypto_pulse={"verdict": "IN LINE", "lead_4w": 1.2},
        crypto_pulse_prior={"verdict": "IN LINE", "lead_4w": 0.8},
        theme_scores=[{"name": "Copper Mining", "comp": 66.0, "stage": "Nascent"}],
        theme_prior={
            "Copper Mining": {
                "rs_avg": 66.5, "stage": "Nascent", "days_active": 3,
                "theme_date": THU - timedelta(days=1), "tickers": ["FCX"],
            }
        },
        theme_births_today=0,
        rs_leaders=list(prior_rows),      # identical day → pure shuffle-free
        rs_leaders_prior=prior_rows,
        themed_tickers_today={"FCX"},
        themed_tickers_prior={"FCX"},
        ep_outcomes=[{
            "ticker": "ZZZ", "score_tier": "MODERATE",
            "trade_status": "filtered", "pt_status": None, "skip_reason": "block:x",
        }],
        wick_today_count=0,
        undercut_today_count=0,
        flag_breaks_today=0,
        velocity_qual=14,
        recovery_qual=71,
        recovery_top="BMNR",
        cooldowns_active=17,
        cooldowns_new_today=3,
    )
    for k, v in over.items():
        setattr(data, k, v)
    return data


# ── Mode + calendar ────────────────────────────────────────────────────────────

def test_monday_full_tue_fri_delta():
    assert brief_mode(date(2026, 7, 27)) == "full"     # Monday — weekly anchor
    for d in (date(2026, 7, 28), date(2026, 7, 29),
              date(2026, 7, 30), date(2026, 7, 31)):   # Tue–Fri
        assert brief_mode(d) == "delta"
    assert brief_mode(date(2026, 7, 25)) == "delta"    # weekend runs stay delta


def test_prior_trading_day_across_weekend():
    assert prior_trading_day(date(2026, 7, 28)) == date(2026, 7, 27)  # Tue → Mon
    assert prior_trading_day(date(2026, 7, 27)) == date(2026, 7, 24)  # Mon → Fri
    assert prior_trading_day(date(2026, 7, 26)) == date(2026, 7, 24)  # Sun → Fri
    assert prior_trading_day(date(2026, 7, 25)) == date(2026, 7, 24)  # Sat → Fri


def test_send_evening_briefing_mode_split_structural():
    """Monday = legacy full stack, other days = the composer — both paths wired."""
    import inspect
    from agents.market_intelligence import briefing

    src = inspect.getsource(briefing.send_evening_briefing)
    assert "brief_mode" in src
    assert "_compose_delta_brief" in src
    assert "_format_evening_briefing" in src


# ── True-zero night (short form) + state-line honesty ──────────────────────────

def test_true_zero_material_night_short_form():
    text = compose_evening_brief(_quiet_data())
    assert "✅ Nothing material tonight" in text
    assert "1️⃣" not in text and "⚡" not in text.split("\n")[1]
    assert "— no change —" in text
    # every check asserts it RAN
    assert "Regime CORRECTING (6th day)" in text
    assert "net -1" in text and "filter ≥75" in text and "size ≈0.75×" in text
    assert "Crypto IN LINE (unch, +1.2 vs QQQ 4wk)" in text
    assert "Themes: none moved ≥8 · 1 quiet · 0 seeded" in text
    assert "Top-10 sectors:" in text and "(Δ none)" in text and "no deep jumps" in text
    assert "Lenses: Rising 14 qual · Recovery 71 qual (top BMNR) · Rotation none ≥3wk" in text
    assert "EP: 0 HIGH · 1 MOD · no entries" in text
    assert "Detectors: quiet" in text
    assert "Unanchored" in text and "(±0)" in text and "Cooldowns 17 (+3)" in text
    assert "_Do your review. Pull up charts. Apply your judgment._" in text
    assert len(text) < 4096


def test_missing_substrate_is_explicit_never_silent():
    data = _quiet_data(
        regime_history=None,
        crypto_pulse={},
        theme_prior=None,
        rs_leaders_prior=None,
        themed_tickers_prior=None,
        ep_outcomes=None,
    )
    text = compose_evening_brief(data)
    assert "Regime: history fetch failed" in text
    assert "Crypto: pulse unavailable" in text
    assert "Δ skipped" in text                       # themes prior missing
    assert "no prior-day scores" in text             # leaders prior missing
    assert "EP: outcomes fetch failed" in text
    assert "(Δ?)" in text                            # unanchored delta unknown


# ── Theme thresholds (itemize ≥8 cap 5 · ⚡ ≥12 · rs_avg=0 guard) ──────────────

def _one_theme(comp, prior_rs, stage="Nascent", prior_stage="Nascent"):
    return dict(
        theme_scores=[{"name": "X Theme", "comp": comp, "stage": stage}],
        theme_prior={"X Theme": {
            "rs_avg": prior_rs, "stage": prior_stage, "days_active": 3,
            "theme_date": THU - timedelta(days=1), "tickers": [],
        }},
    )


def test_theme_itemize_boundary_just_under_emits_nothing():
    text = compose_evening_brief(_quiet_data(**_one_theme(77.9, 70.0)))  # Δ +7.9
    assert "✅ Nothing material tonight" in text
    assert "*THEME" not in text
    assert "Themes: none moved ≥8" in text


def test_theme_itemize_boundary_just_over_emits():
    text = compose_evening_brief(_quiet_data(**_one_theme(78.0, 70.0)))  # Δ +8.0
    assert "⚡ 1 material tonight" in text
    assert "*THEME BREAK*" in text
    assert "+8.0" in text


def test_theme_emphasis_boundary():
    text = compose_evening_brief(_quiet_data(**_one_theme(81.9, 70.0)))  # Δ +11.9
    assert "⚡`" not in text and "*THEME BREAK*" in text
    text = compose_evening_brief(_quiet_data(**_one_theme(82.0, 70.0)))  # Δ +12.0
    assert "⚡`" in text


def test_theme_rs_avg_zero_prior_guard():
    """A rs_avg=0 prior row manufactured a fake +70.6 'move' on 7/24 — the
    guard is an implementation requirement (design §1.2)."""
    scores = [{"name": "X", "comp": 70.6, "stage": "Nascent"}]
    assert compute_theme_movers(scores, {"X": {"rs_avg": 0}}) == []
    assert compute_theme_movers(scores, {"X": {"rs_avg": 0.0}}) == []
    assert compute_theme_movers(scores, {}) == []          # no prior ≠ a move
    movers = compute_theme_movers(scores, {"X": {"rs_avg": 60.0}})
    assert len(movers) == 1 and movers[0]["delta"] == 10.6


def test_theme_itemize_cap_top5_overflow_counted():
    scores, prior = [], {}
    for i in range(6):  # six movers ≥8, deltas 20..15
        scores.append({"name": f"TH{i}", "comp": 80.0 + (20 - i), "stage": "Nascent"})
        prior[f"TH{i}"] = {"rs_avg": 80.0, "stage": "Nascent", "days_active": 3,
                           "theme_date": THU - timedelta(days=1), "tickers": []}
    text = compose_evening_brief(_quiet_data(theme_scores=scores, theme_prior=prior))
    assert "THEMES — 6 moved ≥8, top 5:*" in text
    assert "_+1 more ≥8" in text
    assert text.count("`TH") == 5   # exactly five itemized


# ── VIX boundary ───────────────────────────────────────────────────────────────

def test_vix_boundary_just_under_no_material():
    # Δ displayed +2.6 → below the 2.7 p90 bar
    text = compose_evening_brief(_quiet_data(vix=None, regime_history=_hist(
        vixes=[15.9, 13.3, 13.3, 13.3, 13.3, 13.3])))
    assert "✅ Nothing material tonight" in text
    assert "*REGIME" not in text


def test_vix_boundary_just_over_fires():
    text = compose_evening_brief(_quiet_data(regime_history=_hist(
        vixes=[16.0, 13.3, 13.3, 13.3, 13.3, 13.3])))
    assert "⚡ 1 material tonight" in text
    assert "*REGIME — VIX 16.0 (+2.7 d/d)*" in text


# ── Regime flip block ──────────────────────────────────────────────────────────

def test_regime_flip_block_with_filter_and_chop_annotation():
    hist = _hist(
        labels=["Correcting", "Choppy", "Choppy", "Choppy", "Correcting", "Correcting"],
        thresholds=[75, 70, 70, 70, 75, 75],
        vixes=[16.7, 15.6, 15.6, 15.6, 15.6, 15.6],
        nets=[0, 1, 1, 1, 0, 0],
    )
    text = compose_evening_brief(_quiet_data(regime_history=hist))
    assert "⚡ 1 material tonight — regime flipped" in text
    assert "*REGIME: CHOPPY → CORRECTING*" in text
    assert "EP filter 70 → 75 (tightened)" in text
    assert "Net +1 → +0" in text
    assert "VIX 16.7 (+1.1)" in text
    assert "2nd flip this week — chop" in text
    assert "`/regime` full matrix" in text
    # regime state line replaced by the block
    assert "\nRegime CORRECTING" not in text


# ── Crypto thresholds ──────────────────────────────────────────────────────────

def test_crypto_verdict_flip_material():
    text = compose_evening_brief(_quiet_data(
        crypto_pulse={"verdict": "LEADING", "lead_4w": 8.8},
        crypto_pulse_prior={"verdict": "IN LINE", "lead_4w": 2.1},
    ))
    assert "⚡ 1 material tonight" in text
    assert "*CRYPTO: IN LINE → LEADING* (+8.8 vs QQQ 4wk)" in text


def test_crypto_lead_jump_boundary():
    under = compose_evening_brief(_quiet_data(
        crypto_pulse={"verdict": "IN LINE", "lead_4w": 2.9},
        crypto_pulse_prior={"verdict": "IN LINE", "lead_4w": -3.0},
    ))  # Δ +5.9
    assert "✅ Nothing material tonight" in under
    over = compose_evening_brief(_quiet_data(
        crypto_pulse={"verdict": "IN LINE", "lead_4w": 3.0},
        crypto_pulse_prior={"verdict": "IN LINE", "lead_4w": -3.0},
    ))  # Δ +6.0
    assert "⚡ 1 material tonight" in over
    assert "4wk lead +3.0 (Δ+6.0 d/d)" in over


# ── Leader deep jumps + tie-order guard + sector concentration ─────────────────

def test_leader_deep_jump_boundary_25_vs_26():
    prior = _mk_rows([f"P{i:02d}" for i in range(30)])
    # climber from yesterday's #25 → NOT material (must be BEYOND #25)
    climber = dict(prior[24]); climber["rs_composite"] = 199.5
    assert compute_deep_jumps(prior[:9] + [climber], prior, 100) == []
    # climber from yesterday's #26 → material
    climber = dict(prior[25]); climber["rs_composite"] = 199.5
    jumps = compute_deep_jumps(prior[:9] + [climber], prior, 100)
    assert len(jumps) == 1
    assert jumps[0]["ticker"] == "P25" and jumps[0]["rank_prior"] == 26


def test_leader_jump_absent_from_prior_renders_beyond_depth():
    prior = _mk_rows([f"P{i:02d}" for i in range(30)])
    newcomer = {"ticker": "NEW", "rs_composite": 199.5, "sector": "Healthcare",
                "desc": "molecular diagnostics"}
    data = _quiet_data(rs_leaders=prior[:9] + [newcomer], rs_leaders_prior=prior)
    text = compose_evening_brief(data)
    assert "*LEADERS — 1 deep jump into top-10*" in text
    assert "#>100 → #2" in text
    assert "molecular diagnostics" in text
    assert 'other slots: shuffle only · "rs leaders"' in text


def test_tie_order_guard_no_phantom_jumps():
    """8+ names print RS 100 and DB tie-order is arbitrary — a reversed prior
    ordering of the SAME scores must produce zero jumps and zero sector delta."""
    names = [f"TIE{i:02d}" for i in range(12)]
    today = [{"ticker": n, "rs_composite": 100.0, "sector": "Technology"} for n in names]
    prior = list(reversed(today))
    assert compute_deep_jumps(today, prior, 100) == []
    assert rank_leaders(today) == rank_leaders(prior)
    text = compose_evening_brief(_quiet_data(
        rs_leaders=today, rs_leaders_prior=prior,
        themed_tickers_today=set(), themed_tickers_prior=set()))
    assert "(Δ none)" in text and "no deep jumps" in text


def test_sector_concentration_counts_and_dropout():
    prior_secs = ["Healthcare"] * 3 + ["Technology"] * 3 + ["Energy"] * 2 + ["Financial Services"] * 2
    today_secs = ["Healthcare"] * 5 + ["Technology"] * 3 + ["Energy"] * 2
    prior = [{"ticker": f"P{i}", "rs_composite": 200.0 - i, "sector": s}
             for i, s in enumerate(prior_secs)]
    today = [{"ticker": f"C{i}", "rs_composite": 200.0 - i, "sector": s}
             for i, s in enumerate(today_secs)]
    counts = sector_concentration(today)
    assert counts["Health"] == 5 and counts["Tech"] == 3
    text = compose_evening_brief(_quiet_data(
        rs_leaders=today, rs_leaders_prior=prior,
        themed_tickers_today=set(), themed_tickers_prior=set()))
    assert "Health 5 (+2)" in text          # |Δcount| ≥ 2 annotated
    assert "(Δ −Financl)" in text           # dropped sector is the informative absence
    assert '"rs leaders"' in text


# ── EP recap exceptions ────────────────────────────────────────────────────────

def test_ep_entry_makes_material_block():
    outcomes = [
        {"ticker": "ABC", "score_tier": "HIGH", "trade_status": "traded",
         "pt_status": "filled", "last_entry_price": 12.34, "fwd_1d_pct": 2.1},
        {"ticker": "DEF", "score_tier": "MODERATE", "trade_status": "filtered",
         "pt_status": None, "skip_reason": "block:x"},
    ]
    text = compose_evening_brief(_quiet_data(ep_outcomes=outcomes))
    assert "*EP — 1 entered*" in text
    assert "`ABC` @$12.34 +2.1%" in text
    assert "1 HIGH · 1 MODERATE today" in text
    assert "\nEP:" not in text              # state line replaced by the block


def test_ep_anomalous_terminal_state_makes_material_block():
    outcomes = [{"ticker": "GHI", "score_tier": "HIGH",
                 "trade_status": "no_attempt", "pt_status": None, "skip_reason": None}]
    text = compose_evening_brief(_quiet_data(ep_outcomes=outcomes))
    assert "*EP — terminal-state anomalies*" in text
    assert "`GHI` ⚠️ no terminal state" in text


# ── Busy-night composite (class precedence + citations + size cap) ─────────────

def _busy_data():
    prior = _mk_rows([f"P{i:02d}" for i in range(30)], sector="Industrials")
    newcomer = {"ticker": "CDNA", "rs_composite": 199.5, "sector": "Healthcare",
                "desc": "molecular diagnostics"}
    scores, tprior = [], {}
    for i, (name, comp, prior_rs) in enumerate([
        ("Semi Wafer Foundry", 60.0, 72.1),       # -12.1 ⚡
        ("Immunology Biologics", 84.0, 95.5),     # -11.5
        ("Protein Degradation", 83.0, 94.5),      # -11.5
        ("Digital Ad Platforms", 98.0, 87.1),     # +10.9 → now #1
    ]):
        scores.append({"name": name, "comp": comp, "stage": "Fading" if i == 0 else "Nascent"})
        tprior[name] = {"rs_avg": prior_rs, "stage": "Accelerating" if i == 0 else "Nascent",
                        "days_active": 5, "theme_date": THU - timedelta(days=1), "tickers": []}
    hist = _hist(
        labels=["Correcting", "Choppy", "Choppy", "Choppy", "Correcting", "Correcting"],
        thresholds=[75, 70, 70, 70, 75, 75],
        vixes=[16.7, 15.6, 15.6, 15.6, 15.6, 15.6],
        nets=[0, 1, 1, 1, 0, 0],
    )
    return _quiet_data(
        regime_history=hist,
        crypto_pulse={"verdict": "LEADING", "lead_4w": 8.8},
        crypto_pulse_prior={"verdict": "IN LINE", "lead_4w": 2.1},
        theme_scores=scores,
        theme_prior=tprior,
        theme_births_today=9,
        rs_leaders=prior[:9] + [newcomer],
        rs_leaders_prior=prior,
        ep_outcomes=[{"ticker": "ABC", "score_tier": "HIGH", "trade_status": "traded",
                      "pt_status": "filled", "last_entry_price": 12.34, "fwd_1d_pct": 2.1}],
        wick_today_count=1,
        wick_fill_rate_30d=0.62,
        wick_settled_30d=13,
        is_friday=True,
        signal_quality_block="*SIGNAL QUALITY (30d)*\n  RS Top 20: avg +1.0% vs SPY +0.5% (alpha +0.5%)",
    )


def test_busy_night_class_precedence_and_annotations():
    text = compose_evening_brief(_busy_data())
    assert "⚡ 5 material tonight — regime flipped" in text
    # fixed class precedence: regime → crypto → themes → leaders → EP recap
    order = [text.index("*REGIME:"), text.index("*CRYPTO:"),
             text.index("*THEMES"), text.index("*LEADERS"), text.index("*EP —")]
    assert order == sorted(order)
    assert "1️⃣" in text and "5️⃣" in text
    assert "⚡`Semi Wafer Foundry" in text          # ≥12 emphasis
    assert "Fading" in text                         # stage FLIP annotation rides the mover
    assert "← now #1" in text                       # newly-#1 annotation
    assert "9 seeded" in text
    assert "#>100 → #2" in text
    assert "30d wick fill 62% (13 settled)" in text  # Friday wick telemetry
    assert "*SIGNAL QUALITY (30d)*" in text          # Friday block appended
    assert "Top-10 sectors:" in text                 # concentration line ALWAYS present
    assert len(text) < 4096


# ── Reachability: every cited command exists (the 7/20 orphan-fix pin) ─────────

def test_output_citations_subset_of_verified_sets():
    """Every `/command` and "phrase" the composer EMITS must come from the
    pinned CITED_* sets — a new hint can't sneak in unverified."""
    for text in (compose_evening_brief(_quiet_data()),
                 compose_evening_brief(_busy_data())):
        for cmd in set(re.findall(r"`(/[a-z_]+)`", text)):
            assert cmd in CITED_SLASH_COMMANDS, f"unverified command cited: {cmd}"
        for phrase in set(re.findall(r'"([a-z ]+)"', text)):
            assert phrase in CITED_PHRASES, f"unverified phrase cited: {phrase}"


def test_cited_slash_commands_exist_in_dispatch_dict():
    import inspect
    from agents.market_intelligence.agent import MarketIntelligenceAgent

    src = inspect.getsource(MarketIntelligenceAgent._handle_slash_command)
    for cmd in CITED_SLASH_COMMANDS:
        assert f'"{cmd}":' in src, f"cited command {cmd} missing from dispatch dict"


@pytest.fixture(scope="module")
def routed():
    """Recorder harness over the REAL routing cascade (mirrors
    test_execute_task_routing) — cited phrases must land on their handlers."""
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from shared.models import AgentRequest

    agent = MarketIntelligenceAgent()

    def _recorder(name):
        async def _rec(*args, **kwargs):
            return {"handler": name}
        return _rec

    for attr in dir(agent):
        if attr.startswith("_handle_") and callable(getattr(agent, attr)):
            setattr(agent, attr, _recorder(attr))

    def _route(task: str) -> dict:
        req = AgentRequest(task=task, user_id=1, conversation_id="t")
        return asyncio.run(agent.execute_task(req))

    return _route


# phrase → the handler that serves the collapsed signal's drill-down
PHRASE_HANDLERS = {
    "rs leaders": "_handle_rs_query",          # top-20, sector-grouped + commentary
    "ep outcome": "_handle_ep_outcomes",
    "show cooldowns": "_handle_cooldown_query",
    "pullback": "_handle_pullback_query",
    "crypto": "_handle_crypto_query",
}


def test_cited_phrases_route_to_their_handlers(routed):
    assert set(PHRASE_HANDLERS) == set(CITED_PHRASES)
    for phrase, handler in PHRASE_HANDLERS.items():
        result = routed(phrase)
        assert result["handler"] == handler, (
            f'cited phrase "{phrase}" routed to {result["handler"]}, '
            f"expected {handler} — the brief would orphan this signal"
        )
