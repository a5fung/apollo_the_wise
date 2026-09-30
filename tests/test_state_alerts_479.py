"""#479 — themes-first state-change message (operator-specified 2026-08-12).

Pins:
  - the DERIVED group-deterioration rule (>= _CLUSTER_MIN_NAMES co-deteriorating
    members AND binomial tail <= _CLUSTER_MAX_CHANCE vs the day's base rate):
    singletons (the DDOG case) NEVER surface; whole-group drops do; a red tape
    that lifts the day's base rate suppresses what chance explains;
  - the message keeps new themes / stage-ups / graduations, and COLLAPSES
    per-name RS drops, MA breaks and composition churn into the suppressed
    dict (persisted to mi_audit_log — collapse, never delete: the 7/20 lesson);
  - every on-demand footer citation is reachable in the LIVE routing
    (dispatch/phrase list), so no pointer orphans its signal;
  - promote_shadow_themes folds NEW graduations into a passed changelog
    (one message) and still sends standalone when no changelog is given.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.state_alerts import (
    _CLUSTER_MAX_CHANCE,
    _CLUSTER_MIN_NAMES,
    _binom_tail,
    compute_rs_clusters,
    format_state_alerts,
)


# ── the derived rule ──────────────────────────────────────────────────────────

def test_binom_tail_exact_values():
    # P(X>=1 | n=2, p=0.5) = 0.75 ; P(X>=2 | n=2, p=0.5) = 0.25
    assert _binom_tail(2, 0.5, 1) == pytest.approx(0.75)
    assert _binom_tail(2, 0.5, 2) == pytest.approx(0.25)
    # boundaries
    assert _binom_tail(5, 0.0, 1) == 0.0
    assert _binom_tail(5, 0.3, 0) == 1.0


def _theme(name, tickers, stage="Mainstream"):
    return {"name": name, "stage": stage, "tickers": tickers}


def test_singleton_ddog_never_clusters():
    """One name down inside a healthy theme = stock story, not theme story."""
    themes = [_theme("Software", ["DDOG", "TEAM", "SNOW", "NOW", "CRM",
                                  "MDB", "NET", "PANW", "FTNT", "OKTA"])]
    prior = {tk: 90.0 for tk in themes[0]["tickers"]}
    today = dict(prior)
    today["DDOG"] = 58.0  # -32, the operator's example
    assert compute_rs_clusters(themes, today, prior) == []


def test_whole_group_drop_fires_and_names_the_theme():
    themes = [
        _theme("REITs", ["AVB", "ELS", "EQR", "UDR"]),
        _theme("Healthy", ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF",
                           "GGG", "HHH", "III", "JJJ", "KKK", "LLL"]),
    ]
    prior = {tk: 90.0 for t in themes for tk in t["tickers"]}
    today = dict(prior)
    for tk in themes[0]["tickers"]:
        today[tk] = 60.0  # 4/4 down 30, base rate 4/16 = 0.25
    out = compute_rs_clusters(themes, today, prior)
    assert [a["theme"] for a in out] == ["REITs"]
    a = out[0]
    assert a["type"] == "theme_rs_deterioration"
    assert len(a["names"]) == 4 and a["n_members"] == 4
    assert a["chance"] <= _CLUSTER_MAX_CHANCE
    # names sorted by drop desc, each carrying prior→now
    assert a["names"][0]["drop"] == 30


def test_market_wide_carnage_is_explained_by_chance():
    """Same 3-of-6 hit, but EVERYTHING deteriorated that day — the binomial
    gate must suppress what the day's base rate explains (kills a mutant that
    drops the chance term)."""
    theme_tks = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    other = [f"Z{i:02d}" for i in range(40)]
    themes = [_theme("Six", theme_tks), _theme("Rest", other)]
    prior = {tk: 90.0 for t in themes for tk in t["tickers"]}
    today = dict(prior)
    for tk in theme_tks[:3]:
        today[tk] = 60.0
    for tk in other:               # base rate ~43/46 — a red tape
        today[tk] = 60.0
    assert compute_rs_clusters(themes, today, prior) == []


def test_two_names_below_min_never_fire():
    """x=2 with a microscopic base rate still can't fire: a pair isn't a group
    (kills a mutant that lowers _CLUSTER_MIN_NAMES)."""
    themes = [_theme("Pair", ["AAA", "BBB"]),
              _theme("Rest", [f"Z{i:03d}" for i in range(200)])]
    prior = {tk: 90.0 for t in themes for tk in t["tickers"]}
    today = dict(prior)
    today["AAA"] = today["BBB"] = 60.0   # base rate 2/202 → tail ≈ 9e-5
    assert _CLUSTER_MIN_NAMES >= 3
    assert compute_rs_clusters(themes, today, prior) == []


# ── the message ───────────────────────────────────────────────────────────────

_CLUSTER_ALERT = {
    "type": "theme_rs_deterioration", "theme": "P&C Insurance", "stage": "Mainstream",
    "n_members": 11, "chance": 0.001,
    "names": [{"ticker": t, "rs_prior": 90, "rs_now": 60, "drop": 30}
              for t in ["HIG", "TRV", "ALL", "ORI", "CB", "THG"]],
}


def _full_inputs():
    alerts = [
        {"type": "rs_deterioration", "ticker": "DDOG", "rs_now": 58, "rs_prior": 86, "drop": 28},
        {"type": "ma_break", "ticker": "ATEX", "ma": "50MA", "rs": 63, "vol_ratio": 2.7},
        {"type": "theme_transition", "theme": "InsurTech", "from_stage": "Nascent", "to_stage": "Mainstream"},
        {"type": "theme_transition", "theme": "Copper", "from_stage": "Accelerating", "to_stage": "Mainstream"},
        {"type": "theme_composition", "theme": "Cloud Data", "added": ["MDB"], "removed": []},
        _CLUSTER_ALERT,
    ]
    changelog = [
        {"type": "theme_new", "theme": "Uranium Supply", "tickers": ["UEC", "UUUU"]},
        {"type": "theme_retired", "theme": "Department Stores"},
        {"type": "theme_graduated", "theme": "Grid Buildout"},
    ]
    today_themes = [_theme("InsurTech", ["LMND"]), _theme("Copper", ["FCX"]),
                    _theme("Cloud Data", ["MDB"]), _theme("P&C Insurance", ["HIG"])]
    return alerts, changelog, today_themes


def test_message_keeps_theme_signal_and_collapses_the_rest():
    alerts, changelog, today_themes = _full_inputs()
    text, suppressed = format_state_alerts(alerts, changelog, {}, today_themes)
    assert text is not None
    # KEEP (the purpose of the message)
    assert "Uranium Supply" in text and "🆕" in text
    assert "InsurTech: Nascent → Mainstream" in text and "⚡" in text
    assert "🎓" in text and "Grid Buildout" in text
    assert "P&C Insurance: 6/11 members" in text and "HIG" in text
    assert "🔻 *Stage down*: Copper (Accelerating → Mainstream)" in text
    assert "🪦 *Retired*: Department Stores" in text
    # COLLAPSED — never in the message
    assert "DDOG" not in text
    assert "ATEX" not in text
    assert "MDB" not in text
    # ... but never deleted: routed to the suppressed dict for the audit rows
    assert suppressed["rs_names"][0]["ticker"] == "DDOG"
    assert suppressed["ma_breaks"][0]["ticker"] == "ATEX"
    assert suppressed["composition"][0]["theme"] == "Cloud Data"
    # formatting: bullets + drill-down footer at the end
    assert "\n• " in text
    assert text.splitlines()[-1].startswith("_on demand:")
    # no pipe tables ever (Telegram cannot render them)
    assert "|" not in text


def test_only_collapsed_content_sends_nothing_but_keeps_detail():
    alerts = [
        {"type": "rs_deterioration", "ticker": "DDOG", "rs_now": 58, "rs_prior": 86, "drop": 28},
        {"type": "ma_break", "ticker": "ATEX", "ma": "50MA", "rs": 63, "vol_ratio": 2.7},
    ]
    text, suppressed = format_state_alerts(alerts, [], {}, [])
    assert text is None
    assert len(suppressed["rs_names"]) == 1 and len(suppressed["ma_breaks"]) == 1


def test_markdown_entities_stripped_from_theme_names():
    changelog = [{"type": "theme_new", "theme": "Under_scored *Theme*", "tickers": ["AAA"]}]
    text, _ = format_state_alerts([], changelog, {}, [])
    assert "Under_scored" not in text and "*Theme*" not in text
    assert "Underscored Theme" in text


# ── on-demand reachability (the 7/20 orphaning guard) ─────────────────────────

def test_footer_citations_are_reachable_in_live_routing():
    import inspect
    from agents.market_intelligence.agent import MarketIntelligenceAgent

    # `/themes` must exist in the slash dispatch dict
    slash_src = inspect.getsource(MarketIntelligenceAgent._handle_slash_command)
    assert '"/themes":' in slash_src
    # "audit log ..." phrases must reach _handle_audit_log (phrase route) and the
    # handler must map the collapsed event types
    exec_src = inspect.getsource(MarketIntelligenceAgent.execute_task)
    assert '"audit log"' in exec_src and '"show logs"' in exec_src
    handler_src = inspect.getsource(MarketIntelligenceAgent._handle_audit_log)
    assert '"rs_deterioration"' in handler_src      # "audit log deterioration"
    assert '"ma_break"' in handler_src              # "audit log ma breaks"
    assert '"theme_composition_churn"' in handler_src  # "audit log churn"


def test_audit_log_phrases_route_to_the_handler():
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

    for phrase in ("audit log deterioration", "audit log ma breaks",
                   "audit log churn", "show logs"):
        req = AgentRequest(task=phrase, user_id=1, conversation_id="t")
        out = asyncio.run(agent.execute_task(req))
        assert out == {"handler": "_handle_audit_log"}, phrase


# ── sender: suppressed detail persisted; graduation folded at promote ────────

@pytest.mark.asyncio
async def test_send_state_alerts_persists_suppressed_detail(monkeypatch):
    from agents.market_intelligence import state_alerts as sa
    from agents.market_intelligence import briefing as _brief

    sent = AsyncMock(return_value=True)
    logged = AsyncMock()
    monkeypatch.setattr(_brief, "send_telegram_message", sent)
    monkeypatch.setattr(sa, "log_audit_event", logged)

    alerts, changelog, today_themes = _full_inputs()
    await sa.send_state_alerts(alerts, changelog, today_themes, [])

    assert sent.await_count == 1
    events = {c.args[0] for c in logged.await_args_list}
    assert {"rs_deterioration", "ma_break", "theme_composition_churn"} <= events
    # the rs row itemizes the collapsed names (this IS the on-demand surface)
    rs_call = next(c for c in logged.await_args_list if c.args[0] == "rs_deterioration")
    assert "DDOG 86→58" in rs_call.kwargs["summary"]


@pytest.mark.asyncio
async def test_promote_folds_graduation_into_changelog(monkeypatch):
    from agents.market_intelligence import theme_engine as te
    from agents.market_intelligence import theme_ecosystems as eco
    from agents.market_intelligence import briefing as _brief
    from agents.market_intelligence import db as dbmod
    from tests.conftest import make_mock_pool

    monkeypatch.setattr(te, "get_theme_birth_gate_mode", AsyncMock(return_value="off"))
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(side_effect=[[], [], []])
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    monkeypatch.setattr(te, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(te, "_canonicalize_theme_names", AsyncMock(return_value=0))
    monkeypatch.setattr(te, "log_audit_event", AsyncMock())
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(_brief, "send_telegram_message", sent)
    monkeypatch.setattr(eco, "ensure_theme_ecosystems", AsyncMock(return_value=[]))
    monkeypatch.setattr(dbmod, "get_shadow_theme_candidates", AsyncMock(return_value=[
        {"name": "Quantum Networking", "tickers": ["QX", "QY", "QZ"],
         "thesis": "t", "source": "rs_slope_synthesis"},
    ]))

    changelog: list[dict] = []
    n = await te.promote_shadow_themes(_dt.date(2026, 8, 12), changelog=changelog)
    assert n == 1
    assert {"type": "theme_graduated", "theme": "Quantum Networking"} in changelog
    # no standalone 🎓 ping when the changelog carries it
    assert not any("🎓" in str(c.args[0]) for c in sent.await_args_list)
