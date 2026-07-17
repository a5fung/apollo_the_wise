"""Trade-proposal send must survive a Telegram Markdown 400 (the SNX 6/25 trade #234 class).

A bare Markdown sendMessage 400s on an unescaped char in a dynamic field ("game_changer" → an
unclosed italic entity). A proposal that silently fails = a missed FYI, so the send (1) sanitizes
the catalyst underscore and (2) falls back to PLAIN TEXT before giving up. These pin both — plus
the #364 invariant: the proposal is a pure FYI, NO inline keyboard (the Confirm/Skip machinery
was removed 2026-07-03; F17 proved it structurally broken).
"""
import pytest

from agents.market_intelligence.broker import telegram_confirm

_ALERT = {"catalyst_quality": "game_changer", "gap_pct": 11.2}
_SPEC = {"ticker": "SNX", "entry_price": 295.19, "stop_loss_price": 282.16,
         "risk_dollars": 40, "shares": 3, "ep_score": 72, "equity": 5000, "regime": "Choppy"}


def _install_mocks(monkeypatch, post_fn):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123")

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json):
            return post_fn(json)

    monkeypatch.setattr(telegram_confirm.httpx, "AsyncClient", _Client)
    # theme lookup hits the DB — force its graceful skip path (it's try/except-wrapped)
    import agents.market_intelligence.catalyst_rubric_runtime as crr

    async def _boom(*a, **k):
        raise RuntimeError("no db in test")

    monkeypatch.setattr(crr, "get_theme_membership", _boom)


class _Resp:
    def __init__(self, fail=False):
        self._fail = fail

    def raise_for_status(self):
        if self._fail:
            raise Exception("400 Bad Request: can't parse entities")


@pytest.mark.asyncio
async def test_markdown_400_falls_back_to_plain_text(monkeypatch):
    posted = []  # parse_mode of each attempt

    def _post(payload):
        pm = payload.get("parse_mode")
        posted.append(pm)
        return _Resp(fail=(pm == "Markdown"))  # Markdown 400s; plain text (None) succeeds

    _install_mocks(monkeypatch, _post)
    ok = await telegram_confirm.send_trade_proposal(_ALERT, _SPEC, trade_id=234, live_real_enabled=False)
    assert ok is True                    # the proposal still reached the operator
    assert posted == ["Markdown", None]  # tried Markdown, fell back to plain text


@pytest.mark.asyncio
async def test_both_modes_fail_returns_false(monkeypatch):
    def _post(payload):
        return _Resp(fail=True)  # everything 400s

    _install_mocks(monkeypatch, _post)
    ok = await telegram_confirm.send_trade_proposal(_ALERT, _SPEC, trade_id=234, live_real_enabled=False)
    assert ok is False  # honest failure only when BOTH modes fail


@pytest.mark.asyncio
async def test_catalyst_underscore_sanitized(monkeypatch):
    sent = {}

    def _post(payload):
        sent["text"] = payload["text"]
        return _Resp(fail=False)

    _install_mocks(monkeypatch, _post)
    await telegram_confirm.send_trade_proposal(_ALERT, _SPEC, trade_id=234, live_real_enabled=False)
    assert "game changer" in sent["text"]      # sanitized form present
    assert "game_changer" not in sent["text"]  # the raw underscore that 400'd is gone


@pytest.mark.asyncio
async def test_staged_paper_keys_off_threaded_account_mode_not_global(monkeypatch):
    """#444 mode-label sweep: the STAGED-PAPER banner must key off the caller's
    THREADED account_mode, not the legacy global current_account_mode(). Without
    this fix a live-not-armed proposal (account_mode='live', live_real_enabled=
    False) rendered "PAPER TRADE PROPOSAL" whenever the legacy global happened
    to read 'paper' — silently dropping the "not armed" caveat for a live-money
    candidate. Here the global is forced to 'paper' while the threaded mode is
    'live' — the header must still show STAGED-PAPER."""
    import agents.market_intelligence.constants as constants
    monkeypatch.setattr(constants, "current_account_mode", lambda: "paper")

    sent = {}

    def _post(payload):
        sent["text"] = payload["text"]
        return _Resp(fail=False)

    _install_mocks(monkeypatch, _post)
    ok = await telegram_confirm.send_trade_proposal(
        _ALERT, _SPEC, trade_id=234, live_real_enabled=False, account_mode="live",
    )
    assert ok is True
    assert "STAGED-PAPER" in sent["text"]
    assert "📄 PAPER" not in sent["text"]


@pytest.mark.asyncio
async def test_proposal_header_uses_threaded_paper_mode_prefix(monkeypatch):
    """account_mode='paper' explicitly threaded → the else-branch header uses
    mode_prefix('paper') ("📄 PAPER "), not a STAGED-PAPER banner (paper never
    hits the live+not-armed condition) and not whatever the global default is."""
    import agents.market_intelligence.constants as constants
    monkeypatch.setattr(constants, "current_account_mode", lambda: "live")  # global says live

    sent = {}

    def _post(payload):
        sent["text"] = payload["text"]
        return _Resp(fail=False)

    _install_mocks(monkeypatch, _post)
    ok = await telegram_confirm.send_trade_proposal(
        _ALERT, _SPEC, trade_id=234, live_real_enabled=False, account_mode="paper",
    )
    assert ok is True
    assert "📄 PAPER" in sent["text"]
    assert "TRADE PROPOSAL" in sent["text"]
    assert "STAGED-PAPER" not in sent["text"]


@pytest.mark.asyncio
async def test_proposal_is_fyi_only_no_keyboard(monkeypatch):
    # #364 invariant (operator-decided 7/3, F17): the proposal is a pure FYI — NO
    # inline keyboard on ANY attempt. A reintroduced reply_markup would resurrect
    # a dead button whose callback machinery no longer exists (a press would be a
    # silent no-op at best, a wedge at worst). Pins its absence on both sends.
    payloads = []

    def _post(payload):
        payloads.append(payload)
        return _Resp(fail=(payload.get("parse_mode") == "Markdown"))  # Markdown 400s -> fallback fires

    _install_mocks(monkeypatch, _post)
    await telegram_confirm.send_trade_proposal(_ALERT, _SPEC, trade_id=234, live_real_enabled=False)
    assert len(payloads) == 2
    for p in payloads:
        assert "reply_markup" not in p, "#364: the proposal must carry no inline keyboard"
    assert not hasattr(telegram_confirm, "handle_callback"), (
        "#364: the confirm/skip callback machinery must stay removed"
    )
