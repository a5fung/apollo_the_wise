"""ONE factory for every Anthropic client in production — a transport adapter that keeps
every existing caller working when a new model release drops a request feature.

WHY (2026-09-23). The nightly resolver adopted claude-opus-5-5 for the opus tier (JUDGE_MODEL,
THEME_ADVISOR_MODEL). That release returns HTTP 400 for two things this codebase relies on:

    tool_choice: type "tool" and "any" are not supported for this model.
    "thinking.type.disabled" is not supported for this model.

Both judges force a tool through `judge_transport.invoke_forced_tool`, so every grade call
failed open — no verdict for OKTA or VICR at the 16:02 ET management pass. The operator's
standing rule is that a release is adopted automatically, every time, with no relitigation
("the update process needs to be automatic and needs to work"). So the request shape must
adapt to the model, in ONE place, rather than every call site learning each release's rules.

WHAT IT DOES. `make_async_anthropic(...)` / `make_anthropic(...)` return a REAL SDK client whose
`.messages.create` is wrapped:

  1. The request is sent exactly as the caller wrote it.
  2. If the API rejects it with a 400 whose message says a feature is "not supported for this
     model", the request is REWRITTEN and retried once per rejected feature, and the rewrite is
     REMEMBERED per model (module-level cache) so later calls go straight to the working form:
       * forced tool (`tool_choice` type "tool", or "any" with exactly one tool) → structured
         output: `output_config.format = {json_schema: <that tool's input_schema>}`, tools and
         tool_choice removed. The JSON text that comes back is parsed and the response is
         returned with a SYNTHESIZED `tool_use` block (the tool's name, `input` = the parsed
         dict, a synthetic id) and `stop_reason` mapped to "tool_use" — so every caller that
         extracts `tool_use.input` keeps working unchanged. `.usage`, `.model` and everything
         the cost meter reads are preserved (the real response is copied, only `content` and
         `stop_reason` change).
       * "any" with SEVERAL tools → the same, against a discriminated-union schema
         (`{"call": {"anyOf": [{"tool": <const name>, "input": <schema>}, ...]}}`); the chosen
         variant becomes the synthesized tool_use. See `_union_schema`.
       * `thinking: {"type": "disabled"}` rejected → the `thinking` param is dropped and
         `max_tokens` gets headroom, because on such a model thinking is always on and shares
         the output budget (see `thinking_headroom`).
  3. A truncated (`stop_reason == "max_tokens"`) rewritten response is returned UNTOUCHED, so
     every `is_truncated` fail-open path still fires. Unparseable structured output raises
     `StructuredOutputError` (a ValueError) — every caller's existing `except Exception`
     fail-open handles it exactly as it handled the 400.
  4. Each (model, rewrite) adoption is logged ONCE to mi_audit_log (best-effort, lazy import,
     never raises, no Telegram).

WHAT IT DOES NOT DO (THE LINE). No prompt, schema, threshold, grade logic or trading behaviour
changes here. It does not set `output_config.effort` when dropping a disabled-thinking param —
effort changes how much the model deliberates, which is a quality decision for the operator,
not a transport one.

TESTING NOTE. tests/conftest.py stubs the `anthropic` module as a MagicMock, so nothing in the
error path may reference `anthropic.BadRequestError` (`except <MagicMock>` raises TypeError).
Rejections are recognised by duck-typing: `.status_code == 400` plus the message text.
"""
from __future__ import annotations

import asyncio
import copy
import inspect
import json
import logging
import uuid
from typing import Any, Callable, Optional

from shared.llm_response import first_text, stop_reason

logger = logging.getLogger(__name__)

__all__ = [
    "make_async_anthropic",
    "make_anthropic",
    "StructuredOutputError",
    "REWRITE_FORCED_TOOL",
    "REWRITE_THINKING_DISABLED",
    "thinking_headroom",
    "adopted_rewrites",
    "reset_adaptations",
]

# ── Rewrite names (the per-model cache keys) ─────────────────────────────────
REWRITE_FORCED_TOOL = "forced_tool_to_structured_output"
REWRITE_THINKING_DISABLED = "drop_thinking_disabled"

_UNSUPPORTED_MARKER = "not supported for this model"

# model id -> the rewrites that model has been observed to need. Module-level on purpose:
# the first rejected call pays the 400 + retry, every later call in the process goes straight
# to the working form.
_ADAPTATIONS: dict[str, set[str]] = {}
# (model, rewrite) pairs already written to mi_audit_log — once per process, no spam.
_ANNOUNCED: set[tuple[str, str]] = set()

# ── Thinking headroom ────────────────────────────────────────────────────────
# MEASURED 2026-09-23 on claude-opus-5-5: with max_tokens=400 a small-schema answer used ~176
# output tokens INCLUDING the always-on thinking — i.e. thinking cost roughly as much as the
# answer itself on a call whose answer was ~100 tokens. Thinking shares max_tokens with the
# answer, so a ceiling sized as a text-only budget (every entry in shared/output_ceilings.py
# for a thinking=DISABLED caller is exactly that) would cut the answer off. Rule: give thinking
# a budget equal to the answer's, with a floor for tiny ceilings (thinking has a fixed cost that
# does not shrink with the answer), capped at a level that stays under the SDK's non-streaming
# HTTP timeout. Never lowers a ceiling.
THINKING_HEADROOM_FLOOR = 1024
THINKING_MAX_TOKENS_CEILING = 16_000


def thinking_headroom(max_tokens: int) -> int:
    """`max_tokens` for a thinking-cannot-be-disabled model, from the caller's text budget."""
    try:
        mt = int(max_tokens)
    except (TypeError, ValueError):
        return THINKING_MAX_TOKENS_CEILING
    raised = max(mt * 2, mt + THINKING_HEADROOM_FLOOR)
    return max(mt, min(raised, THINKING_MAX_TOKENS_CEILING))


class StructuredOutputError(ValueError):
    """The rewritten (structured-output) call returned text that is not the JSON the schema
    promised. A ValueError so every caller's existing `except Exception` fail-open catches it
    exactly as it caught the original 400; `is_credit_error` ignores it (no status_code)."""


# ── Rejection recognition ────────────────────────────────────────────────────

def _rejection_rewrite(exc: BaseException, kw: dict) -> Optional[str]:
    """Which rewrite (if any) the API's rejection asks for, given what the request carried.
    None when the error is not a feature-unsupported 400, or the request has nothing to
    rewrite for it (then the caller sees the original error)."""
    if getattr(exc, "status_code", None) != 400:
        return None
    msg = str(getattr(exc, "message", "") or exc)
    if _UNSUPPORTED_MARKER not in msg:
        return None
    if "tool_choice" in msg and _forced_tool_target(kw) is not None:
        return REWRITE_FORCED_TOOL
    if "thinking" in msg and _thinking_is_disabled(kw):
        return REWRITE_THINKING_DISABLED
    return None


def _thinking_is_disabled(kw: dict) -> bool:
    th = kw.get("thinking")
    return isinstance(th, dict) and th.get("type") == "disabled"


def _forced_tool_target(kw: dict) -> Optional[list[dict]]:
    """The tool(s) a forced tool_choice pins the model to, or None when the request is not a
    forced-tool request (auto/none/absent, or the named tool is missing)."""
    tc = kw.get("tool_choice")
    tools = kw.get("tools")
    if not isinstance(tc, dict) or not isinstance(tools, list) or not tools:
        return None
    if tc.get("type") == "tool":
        named = [t for t in tools if isinstance(t, dict) and t.get("name") == tc.get("name")]
        return named or None
    if tc.get("type") == "any":
        return [t for t in tools if isinstance(t, dict) and t.get("name")] or None
    return None


# ── Schema shaping ───────────────────────────────────────────────────────────
# Structured outputs reject numeric/string/array constraints and require
# `additionalProperties: false` on every object (claude-api skill, tool-use-concepts § JSON
# Schema Limitations). The SDK's own `.parse()` strips these too; we do the same to a COPY of
# the tool schema — the caller's tool dict is never touched.
_STRIPPED_KEYWORDS = frozenset({
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "pattern", "minItems", "maxItems", "uniqueItems",
    "minProperties", "maxProperties",
})


# Keys whose VALUES are maps of name -> schema: the names are the caller's (a property may
# legitimately be called "pattern" or "maximum") and must never be treated as keywords.
_NAME_MAP_KEYS = frozenset({"properties", "$defs", "definitions", "patternProperties"})


def _sanitize_schema(node: Any) -> Any:
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k in _NAME_MAP_KEYS and isinstance(v, dict):
                out[k] = {name: _sanitize_schema(sub) for name, sub in v.items()}
                continue
            if k in _STRIPPED_KEYWORDS:
                continue
            out[k] = _sanitize_schema(v)
        # Only an object that DECLARES properties gets additionalProperties:false — pinning it
        # on a bare {"type": "object"} would let the model emit nothing but {}.
        if "properties" in out:
            out.setdefault("additionalProperties", False)
        return out
    if isinstance(node, list):
        return [_sanitize_schema(v) for v in node]
    return node


def _single_schema(tool: dict) -> dict:
    return _sanitize_schema(tool.get("input_schema") or {"type": "object", "properties": {}})


_UNION_KEY = "call"


def _union_schema(tools: list[dict]) -> dict:
    """`tool_choice: any` over several tools → "exactly one of these" as a discriminated union:
    a wrapper object whose single `call` property is an anyOf of one variant per tool, each
    variant pinning `tool` to that tool's name (const) and `input` to its schema. `anyOf` and
    `const` are in the structured-outputs supported list."""
    variants = []
    for t in tools:
        variants.append({
            "type": "object",
            "description": t.get("description") or "",
            "properties": {
                "tool": {"const": t["name"]},
                "input": _single_schema(t),
            },
            "required": ["tool", "input"],
            "additionalProperties": False,
        })
    return {
        "type": "object",
        "properties": {_UNION_KEY: {"anyOf": variants}},
        "required": [_UNION_KEY],
        "additionalProperties": False,
    }


# ── Rewrites ─────────────────────────────────────────────────────────────────

def _apply_forced_tool_rewrite(kw: dict) -> tuple[dict, Optional[dict]]:
    """(new_kwargs, plan). plan = {"tools": [...], "union": bool} describing how to turn the
    JSON text back into a tool_use block; None when the request has no forced tool (kwargs
    returned unchanged)."""
    targets = _forced_tool_target(kw)
    if targets is None:
        return kw, None
    new = dict(kw)
    new.pop("tools", None)
    new.pop("tool_choice", None)
    union = len(targets) > 1
    schema = _union_schema(targets) if union else _single_schema(targets[0])
    oc = dict(new.get("output_config") or {})
    oc["format"] = {"type": "json_schema", "schema": schema}
    new["output_config"] = oc
    return new, {"tools": targets, "union": union}


def _apply_thinking_rewrite(kw: dict) -> dict:
    if not _thinking_is_disabled(kw):
        return kw
    new = dict(kw)
    new.pop("thinking", None)
    if "max_tokens" in new:
        new["max_tokens"] = thinking_headroom(new["max_tokens"])
    return new


def _prepare(kw: dict) -> tuple[dict, Optional[dict], set[str]]:
    """Apply every rewrite already known for this request's model. Returns
    (kwargs_to_send, forced_tool_plan, rewrites_applied)."""
    model = kw.get("model")
    known = _ADAPTATIONS.get(model, set()) if isinstance(model, str) else set()
    plan = None
    applied: set[str] = set()
    out = kw
    if REWRITE_THINKING_DISABLED in known and _thinking_is_disabled(out):
        out = _apply_thinking_rewrite(out)
        applied.add(REWRITE_THINKING_DISABLED)
    if REWRITE_FORCED_TOOL in known and _forced_tool_target(out) is not None:
        out, plan = _apply_forced_tool_rewrite(out)
        applied.add(REWRITE_FORCED_TOOL)
    return out, plan, applied


def _remember(model: Any, rewrite: str, exc: BaseException) -> None:
    if not isinstance(model, str):
        return
    _ADAPTATIONS.setdefault(model, set()).add(rewrite)
    key = (model, rewrite)
    if key in _ANNOUNCED:
        return
    _ANNOUNCED.add(key)
    summary = f"{model}: {rewrite}"
    detail = f"API rejection: {str(getattr(exc, 'message', '') or exc)[:300]}"
    logger.warning("llm_client: adopted request rewrite for %s — %s (%s)", model, rewrite, detail)
    _audit_best_effort("llm_request_rewrite_adopted", summary, detail)


def _audit_best_effort(event: str, summary: str, detail: str) -> None:
    """mi_audit_log row via the existing log_audit_event pattern (lazy import, as
    core/job_audit.py does). Fire-and-forget when a loop is running; logger-only otherwise.
    Never raises — an audit failure must not touch the call that triggered it."""
    try:
        from agents.market_intelligence.db import log_audit_event  # lazy: shared/ → agents/
    except Exception:  # loud-ok: the orchestrator container may not carry the DB layer
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _write():
        try:
            await log_audit_event(event, summary, detail)
        except Exception as e:  # loud-ok: never propagate from a background audit write
            logger.warning("llm_client: audit row failed: %s", e)

    try:
        loop.create_task(_write())
    except Exception as e:  # loud-ok
        logger.warning("llm_client: could not schedule audit row: %s", e)


# ── Response synthesis ───────────────────────────────────────────────────────

class _SynthesizedToolUse:
    """Fallback block object when the real SDK type is unavailable (tests stub `anthropic`).
    Same attribute surface every caller reads: type / id / name / input."""
    type = "tool_use"

    def __init__(self, id: str, name: str, input: dict):
        self.id = id
        self.name = name
        self.input = input

    def model_dump(self, *a, **k):
        return {"type": "tool_use", "id": self.id, "name": self.name, "input": self.input}

    def __repr__(self):
        return f"SynthesizedToolUse(name={self.name!r}, id={self.id!r})"


def _tool_use_block(name: str, inp: dict):
    block_id = f"toolu_synth_{uuid.uuid4().hex[:24]}"
    try:
        from anthropic.types import ToolUseBlock  # real SDK type → serialises on the next turn
        if isinstance(ToolUseBlock, type) and hasattr(ToolUseBlock, "model_validate"):
            return ToolUseBlock(type="tool_use", id=block_id, name=name, input=inp)
    except Exception:  # loud-ok: stubbed/absent SDK → plain object with the same surface
        pass
    return _SynthesizedToolUse(block_id, name, inp)


def _block_type(b: Any) -> str:
    return str(b.get("type") if isinstance(b, dict) else getattr(b, "type", "") or "")


def _synthesize(resp: Any, plan: dict) -> Any:
    """Turn the structured-output JSON text into the tool_use block the caller was going to
    read. Truncated responses pass through untouched (the caller's is_truncated check owns
    them); anything else that cannot be parsed raises StructuredOutputError."""
    if stop_reason(resp) == "max_tokens":
        return resp
    text = first_text(resp)
    if not text:
        raise StructuredOutputError(
            f"structured output returned no text block (blocks={[_block_type(b) for b in getattr(resp, 'content', [])]})")
    try:
        data = json.loads(text)
    except ValueError as e:
        raise StructuredOutputError(f"structured output is not JSON: {e}: {text[:200]!r}") from e
    tools = plan["tools"]
    if plan["union"]:
        call = data.get(_UNION_KEY) if isinstance(data, dict) else None
        if not isinstance(call, dict) or "tool" not in call:
            raise StructuredOutputError(f"union output missing {_UNION_KEY!r}/tool: {text[:200]!r}")
        name = call.get("tool")
        if name not in {t["name"] for t in tools}:
            raise StructuredOutputError(f"union output named an unknown tool {name!r}")
        inp = call.get("input")
    else:
        name = tools[0]["name"]
        inp = data
    if not isinstance(inp, dict):
        raise StructuredOutputError(f"structured output is not an object: {text[:200]!r}")

    blocks = list(getattr(resp, "content", None) or [])
    new_content: list = []
    replaced = False
    for b in blocks:
        if not replaced and _block_type(b) == "text":
            new_content.append(_tool_use_block(name, inp))
            replaced = True
        elif _block_type(b) == "text":
            continue  # never leave the raw JSON beside the block — silent-stop readers scan text
        else:
            new_content.append(b)  # thinking blocks stay (signed; callers replay content)
    if not replaced:
        new_content.append(_tool_use_block(name, inp))

    if hasattr(resp, "model_copy"):
        return resp.model_copy(update={"content": new_content, "stop_reason": "tool_use"})
    out = copy.copy(resp)
    out.content = new_content
    out.stop_reason = "tool_use"
    return out


# ── The adapted create (sync + async share one state machine) ───────────────

def _next_rewrite(exc: BaseException, kw: dict, applied: set[str]) -> Optional[str]:
    rewrite = _rejection_rewrite(exc, kw)
    if rewrite is None or rewrite in applied:
        return None
    return rewrite


def _rewrite(kw: dict, rewrite: str) -> tuple[dict, Optional[dict]]:
    if rewrite == REWRITE_FORCED_TOOL:
        return _apply_forced_tool_rewrite(kw)
    return _apply_thinking_rewrite(kw), None


async def _create_async(inner_create: Callable, kw: dict):
    send, plan, applied = _prepare(kw)
    while True:
        try:
            resp = await inner_create(**send)
            break
        except Exception as e:
            rewrite = _next_rewrite(e, send, applied)
            if rewrite is None:
                raise
            _remember(kw.get("model"), rewrite, e)
            send, new_plan = _rewrite(send, rewrite)
            plan = new_plan or plan
            applied.add(rewrite)
    return _synthesize(resp, plan) if plan else resp


def _create_sync(inner_create: Callable, kw: dict):
    send, plan, applied = _prepare(kw)
    while True:
        try:
            resp = inner_create(**send)
            break
        except Exception as e:
            rewrite = _next_rewrite(e, send, applied)
            if rewrite is None:
                raise
            _remember(kw.get("model"), rewrite, e)
            send, new_plan = _rewrite(send, rewrite)
            plan = new_plan or plan
            applied.add(rewrite)
    return _synthesize(resp, plan) if plan else resp


class _AsyncMessagesAdapter:
    """Wraps the SDK's AsyncMessages resource: `create` adapts, everything else delegates."""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    async def create(self, **kwargs):
        return await _create_async(self._inner.create, kwargs)


class _SyncMessagesAdapter:
    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def create(self, **kwargs):
        return _create_sync(self._inner.create, kwargs)


def _wrap(client, adapter_cls):
    inner = client.messages
    if isinstance(inner, (_AsyncMessagesAdapter, _SyncMessagesAdapter)):
        return client
    # `messages` is a functools.cached_property on the SDK client (verified on anthropic 1.x):
    # a non-data descriptor, so instance assignment sticks and the client stays the real type.
    client.messages = adapter_cls(inner)
    return client


def make_async_anthropic(**client_kwargs):
    """The ONLY sanctioned way to build an `anthropic.AsyncAnthropic` in production
    (tests/test_llm_client_factory_population.py fails on any direct construction)."""
    import anthropic
    return _wrap(anthropic.AsyncAnthropic(**client_kwargs), _AsyncMessagesAdapter)


def make_anthropic(**client_kwargs):
    """Sync twin of make_async_anthropic."""
    import anthropic
    return _wrap(anthropic.Anthropic(**client_kwargs), _SyncMessagesAdapter)


def wrap_client(client):
    """Adapt an already-built client (sync or async) — for probes/tests that hand in a fake."""
    inner = client.messages
    is_async = inspect.iscoroutinefunction(getattr(inner, "create", None))
    return _wrap(client, _AsyncMessagesAdapter if is_async else _SyncMessagesAdapter)


# ── Canary: can THIS model serve every request shape production sends? ──────
# Run THROUGH the adapter (a factory client), so it proves the adapted transport works, not the
# raw API. Used by the nightly refresh before a release is adopted
# (model_resolution.refresh_model_resolution) and by scripts/probes/_model_compat_canary.py.
# Four checks mirror the four shapes in production: a forced single tool (both judges,
# catalyst classifiers, theme tools), thinking explicitly disabled (theme_engine /
# theme_synthesis / ecosystem_discovery), a plain text call, and "any" over TWO tools
# (theme_assignment / theme_split's assign-or-consult loops).

CANARY_TOOL: dict = {
    "name": "canary_echo",
    "description": "Echo one word back.",
    "input_schema": {
        "type": "object",
        "properties": {"word": {"type": "string", "description": "the word to echo"}},
        "required": ["word"],
    },
}
CANARY_TOOL_B: dict = {
    "name": "canary_count",
    "description": "Report how many letters a word has.",
    "input_schema": {
        "type": "object",
        "properties": {"letters": {"type": "integer", "description": "letter count"}},
        "required": ["letters"],
    },
}
CANARY_MAX_TOKENS = 512


class CanaryResult:
    __slots__ = ("check", "ok", "detail")

    def __init__(self, check: str, ok: bool, detail: str = ""):
        self.check, self.ok, self.detail = check, ok, detail

    def __repr__(self):
        return f"CanaryResult({self.check!r}, ok={self.ok}, {self.detail!r})"


def _has_tool_use(resp: Any, names: set[str]) -> bool:
    for b in getattr(resp, "content", None) or []:
        if _block_type(b) == "tool_use" and getattr(b, "name", None) in names \
                and isinstance(getattr(b, "input", None), dict):
            return True
    return False


async def run_canary(client, model: str, *, max_tokens: int = CANARY_MAX_TOKENS) -> list[CanaryResult]:
    """Every production request shape against `model`, via an adapted async client.
    Never raises — each failure is a CanaryResult(ok=False) carrying the exact error."""
    prompt_tool = [{"role": "user", "content": "Call the canary_echo tool with the word pong."}]
    prompt_text = [{"role": "user", "content": "Reply with the single word: pong"}]
    prompt_two = [{"role": "user", "content":
                   "The word is pong. Use whichever tool fits best; you must call exactly one."}]
    checks = [
        ("forced_tool",
         dict(model=model, max_tokens=max_tokens, tools=[CANARY_TOOL],
              tool_choice={"type": "tool", "name": CANARY_TOOL["name"]}, messages=prompt_tool),
         lambda r: _has_tool_use(r, {CANARY_TOOL["name"]})),
        ("thinking_disabled",
         dict(model=model, max_tokens=max_tokens, thinking={"type": "disabled"}, messages=prompt_text),
         lambda r: bool(first_text(r).strip())),
        ("plain",
         dict(model=model, max_tokens=max_tokens, messages=prompt_text),
         lambda r: bool(first_text(r).strip())),
        ("any_of_two_tools",
         dict(model=model, max_tokens=max_tokens, tools=[CANARY_TOOL, CANARY_TOOL_B],
              tool_choice={"type": "any"}, messages=prompt_two),
         lambda r: _has_tool_use(r, {CANARY_TOOL["name"], CANARY_TOOL_B["name"]})),
    ]
    out: list[CanaryResult] = []
    for name, kw, verify in checks:
        try:
            resp = await client.messages.create(**kw)
        except Exception as e:  # loud-ok: the canary REPORTS failures, it never raises
            out.append(CanaryResult(name, False, f"{type(e).__name__}: {str(e)[:300]}"))
            continue
        if stop_reason(resp) == "max_tokens":
            out.append(CanaryResult(name, False, f"truncated at max_tokens={kw['max_tokens']}"))
        elif verify(resp):
            out.append(CanaryResult(name, True, f"stop_reason={stop_reason(resp)} rewrites={sorted(adopted_rewrites(model))}"))
        else:
            out.append(CanaryResult(name, False,
                                    f"unexpected response shape: blocks={[_block_type(b) for b in getattr(resp, 'content', None) or []]} stop_reason={stop_reason(resp)}"))
    return out


# ── Introspection (tests, probe, canary) ─────────────────────────────────────

def adopted_rewrites(model: str) -> frozenset[str]:
    return frozenset(_ADAPTATIONS.get(model, set()))


def reset_adaptations() -> None:
    _ADAPTATIONS.clear()
    _ANNOUNCED.clear()
