"""Trade-proposal send must survive a Telegram Markdown 400 (the SNX 6/25 trade #234 class).

A bare Markdown sendMessage 400s on an unescaped char in a dynamic field ("game_changer" → an
unclosed italic entity). A live-trade proposal that silently fails = a missed entry, so the send
now (1) sanitizes the catalyst underscore and (2) falls back to PLAIN TEXT — keeping the Confirm/Skip
buttons — before giving up. These pin both.
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
    assert posted == ["Markdown", None]  # tried Markdown, fell back to plain text (keeps buttons)


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
