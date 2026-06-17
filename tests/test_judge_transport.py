"""Shared forced-tool judge transport (judge_transport.invoke_forced_tool) — the envelope both
the grade judge (load-bearing) and the management judge (shadow) now share. Pins the FAIL-OPEN
contract directly on the shared code (previously only covered transitively via grade_holistic)."""
import asyncio
import base64

from agents.market_intelligence.judge_transport import _user_content, invoke_forced_tool

_TOOL = {"name": "t", "input_schema": {"type": "object", "properties": {}}}


def _run(coro):
    return asyncio.run(coro)


class _Block:
    type = "tool_use"

    def __init__(self, inp):
        self.input = inp


class _Resp:
    def __init__(self, inp):
        self.content = [_Block(inp)]


def _client(behavior):
    class _Messages:
        async def create(self, **kw):
            if behavior == "ok":
                return _Resp({"verdict": "HOLD"})
            if behavior == "raise":
                raise RuntimeError("api boom")
            if behavior == "no_tool":
                r = _Resp({}); r.content = [type("B", (), {"type": "text"})()]; return r
            if behavior == "slow":
                await asyncio.sleep(1.0)
                return _Resp({"verdict": "HOLD"})

    return type("C", (), {"messages": _Messages()})()


def _identity(d):
    return d


def _kw(**over):
    base = dict(tool=_TOOL, tool_name="t", normalize=_identity, label="test judge",
                timeout=5.0, model="m")
    base.update(over)
    return base


def test_none_client_fails_open():
    assert _run(invoke_forced_tool(None, "p", **_kw())) is None


def test_happy_path_returns_normalized():
    assert _run(invoke_forced_tool(_client("ok"), "p", **_kw())) == {"verdict": "HOLD"}


def test_api_error_fails_open():
    assert _run(invoke_forced_tool(_client("raise"), "p", **_kw())) is None


def test_no_tool_block_fails_open():
    # StopIteration from next(...) is swallowed by the fail-open except → None, not a crash.
    assert _run(invoke_forced_tool(_client("no_tool"), "p", **_kw())) is None


def test_timeout_fails_open():
    assert _run(invoke_forced_tool(_client("slow"), "p", **_kw(timeout=0.05))) is None


def test_normalize_none_propagates():
    assert _run(invoke_forced_tool(_client("ok"), "p", **_kw(normalize=lambda d: None))) is None


def test_semaphore_is_respected():
    sem = asyncio.Semaphore(1)
    assert _run(invoke_forced_tool(_client("ok"), "p", **_kw(semaphore=sem))) == {"verdict": "HOLD"}
    assert sem._value == 1  # released


# ── multimodal content shaping (#267 chart-vision) ──

def test_user_content_text_only_is_plain_string():
    # No image → byte-identical to the pre-vision path (the load-bearing grade
    # judge must be unchanged when it sends no chart).
    assert _user_content("hello", None) == "hello"
    assert _user_content("hello", b"") == "hello"  # empty bytes also = text-only


def test_user_content_with_image_is_multimodal_block():
    png = b"\x89PNG\r\n\x1a\nFAKE"
    content = _user_content("grade this", png)
    assert isinstance(content, list) and len(content) == 2
    assert content[0] == {"type": "text", "text": "grade this"}
    img = content[1]
    assert img["type"] == "image"
    assert img["source"]["type"] == "base64"
    assert img["source"]["media_type"] == "image/png"
    # round-trips back to the original PNG bytes
    assert base64.standard_b64decode(img["source"]["data"]) == png
