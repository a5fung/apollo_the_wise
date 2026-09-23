"""Every market-data request must name its feed (2026-08-06).

`get_latest_trade` omitted `feed=`, so alpaca-py defaulted to IEX — roughly 2-3% of consolidated
volume — while the account pays for SIP. That call feeds the #500 price-aware entry guard
(order_manager.py: "has price already run past the ORB high?"), so an entry decision was being
made off a partial tape.

Found while investigating the INSM [6098] rejection. It did NOT cause that one — the SIP tape
showed the same 128.96 prints at submit — but it is a real defect regardless, and the class is
worth a gate: three other requests in that module pass get_data_feed() and this one silently did
not, which is exactly the kind of omission nothing surfaces.
"""
import ast
import pathlib

SRC = pathlib.Path("agents/market_intelligence/broker/alpaca_client.py").read_text()
TREE = ast.parse(SRC)

# Request classes that accept a `feed` argument and therefore MUST be given one.
_FEED_BEARING = {
    "StockLatestTradeRequest",
    "StockLatestQuoteRequest",
    "StockBarsRequest",
    "StockSnapshotRequest",
}


def _feed_bearing_calls():
    for node in ast.walk(TREE):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in _FEED_BEARING):
            yield node


def test_every_market_data_request_names_its_feed():
    """A request without feed= silently uses IEX. The account is on SIP; the difference is the
    whole tape versus a sliver of it, and nothing in logs or tests would show the gap."""
    missing = []
    for call in _feed_bearing_calls():
        if not any(kw.arg == "feed" for kw in call.keywords):
            missing.append(f"{call.func.id} at line {call.lineno}")
    assert not missing, (
        "these market-data requests do not pass feed=, so alpaca-py defaults them to IEX "
        "(~2-3% of volume) while the account is on SIP:\n  " + "\n  ".join(missing))


def test_the_feed_comes_from_the_shared_resolver_not_a_literal():
    """A hardcoded 'sip' would drift from ALPACA_DATA_FEED the moment the env changes, and would
    break the paper/dev path that legitimately runs on IEX."""
    for call in _feed_bearing_calls():
        for kw in call.keywords:
            if kw.arg == "feed":
                src = ast.get_source_segment(SRC, kw.value)
                assert "get_data_feed" in src, (
                    f"{call.func.id} line {call.lineno} passes feed={src!r} — use "
                    f"get_data_feed() so it follows ALPACA_DATA_FEED")


def test_get_latest_trade_specifically_is_covered():
    """Named because it is the one that was wrong, and because it feeds an ENTRY decision."""
    fn = next(n for n in ast.walk(TREE)
              if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
              and n.name == "get_latest_trade")
    src = ast.get_source_segment(SRC, fn)
    assert "feed=get_data_feed()" in src
