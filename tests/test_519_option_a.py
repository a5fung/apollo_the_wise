"""#519 option A — the paid chart-vision run (docs/analysis/519_paid_run_scoping_2026-09-24.md
§"Option A — outcomes declared BEFORE it runs"). Each test here is able to go RED:

  (a) no lookahead        — the daily frame ends before the alert date; the only alert-day
                             value used anywhere is the OPEN (never high/low/close).
  (b) anonymisation        — the render function receives/produces no ticker or date text, and
                             neither does the model-facing prompt (outside the book block, which
                             legitimately names real tickers from 2020-21 leaders/tops).
  (c) scorer boundaries    — synthetic reads reproduce every pre-registered decision-rule
                             boundary (3x / 1.5x / 2x leans, garbage >=3-of-12 and <=1-of-39,
                             stable 2-of-3).
  (d) population           — derived from the fixtures with the expected counts (30/9/21/4).
  (e) paid-run price gate  — `--paid` aborts before ANY `messages.create` call when the priced
                             estimate exceeds `--max-usd`.

READ-ONLY, $0: no DB, no network, no Anthropic call anywhere in this file (DB/API-touching
functions are either monkeypatched or exercised only at the source-text level).
"""
from __future__ import annotations

import asyncio
import inspect
import math
import re
import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

REPO = Path(__file__).resolve().parents[1]
for _p in (str(REPO), str(REPO / "scripts" / "probes")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _519_option_a as mod  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════════════
# (d) POPULATION
# ══════════════════════════════════════════════════════════════════════════════════════

def test_population_counts_match_the_pre_registration():
    pop = mod.load_population()
    assert len(pop) == 64, f"expected 64 rows (30+9+21+4), got {len(pop)}"
    by_pop: dict[str, int] = {}
    for p, tk, d, v in pop:
        by_pop[p] = by_pop.get(p, 0) + 1
    assert by_pop == {"REAL_EP": 30, "APPROVED": 9, "BAD_CHART": 21, "OTHER_REJECTED": 4}


def test_data_defect_and_pointed_at_are_excluded():
    pop = mod.load_population()
    keys = {(tk, d) for _, tk, d, _ in pop}
    # VEEE 2026-07-08 is the DATA_DEFECT member (NO_SETUP_ON_THIS_DATE) — must never score.
    assert ("VEEE", "2026-07-08") not in keys
    # every POINTED_AT date is excluded too (it is a flag, never a label).
    from tests.fixtures.must_not_trade_charts import POINTED_AT_DATES
    for t, d, _v in POINTED_AT_DATES:
        assert (t, d) not in keys or any(
            p == "OTHER_REJECTED" and tk == t and dd == d for p, tk, dd, _ in pop
        ), f"{t}/{d} is a POINTED_AT date and must not enter scoring as itself"


def test_population_has_no_duplicate_ticker_date_rows_within_a_group():
    pop = mod.load_population()
    seen: dict[str, set] = {}
    for p, tk, d, _v in pop:
        seen.setdefault(p, set())
        assert (tk, d) not in seen[p], f"{p} lists {tk}/{d} twice"
        seen[p].add((tk, d))


def test_real_ep_excludes_the_excluded_members():
    """The 3 `excluded=True` `must_not_miss_eps` members (a data anomaly, not a tradeable EP)
    must not appear — mirrors `test_577_must_not_miss_eps.py`'s own rule."""
    from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS
    pop = mod.load_population()
    ep_keys = {(tk, d) for p, tk, d, _ in pop if p == "REAL_EP"}
    excluded = [(m.ticker, m.alert_date) for m in MUST_NOT_MISS if getattr(m, "excluded", False)]
    assert excluded, "fixture no longer marks any member excluded — this test is vacuous"
    for tk, d in excluded:
        assert (tk, d) not in ep_keys


# ══════════════════════════════════════════════════════════════════════════════════════
# (a) NO LOOKAHEAD
# ══════════════════════════════════════════════════════════════════════════════════════

def test_alert_day_query_asks_the_db_for_only_the_open_price():
    """`fetch_row_bars`'s alert-day query must never ask for high/low/close — the contract is
    'the only alert-day value used is the OPEN'. BEHAVIOURAL: runs the real function against a
    fake pool/connection and inspects the SQL it actually SENDS (a runtime-captured string, not
    `inspect.getsource` — this must catch a future edit that adds a column, without pinning the
    function's source text itself)."""
    captured: dict = {}

    class _FakeConn:
        async def fetchrow(self, query, *args):
            captured["query"] = query
            captured["args"] = args
            return {"open_price": 12.34}

    class _FakeAcquire:
        async def __aenter__(self):
            return _FakeConn()

        async def __aexit__(self, *a):
            return False

    class _FakePool:
        def acquire(self, *a, **k):
            return _FakeAcquire()

    async def fake_get_pool():
        return _FakePool()

    async def fake_get_prior_daily_ohlcv(ticker, alert_date, lookback=None):
        return []

    import agents.market_intelligence.db as db_mod
    orig_pool, orig_prior = db_mod.get_pool, db_mod.get_prior_daily_ohlcv
    db_mod.get_pool = fake_get_pool
    db_mod.get_prior_daily_ohlcv = fake_get_prior_daily_ohlcv
    try:
        prior, open_px = asyncio.run(mod.fetch_row_bars("XYZ", date(2026, 6, 3)))
    finally:
        db_mod.get_pool, db_mod.get_prior_daily_ohlcv = orig_pool, orig_prior

    assert open_px == 12.34
    q = captured["query"]
    m = re.search(r"SELECT\s+(.+?)\s+FROM", q, re.S | re.I)
    assert m, f"could not find a SELECT clause in the captured query: {q!r}"
    select_list = {c.strip() for c in m.group(1).split(",")}
    assert select_list == {"open_price"}, (
        f"alert-day query's SELECT list is {select_list} — it must select ONLY open_price "
        f"(never high/low/close): {q!r}")
    assert captured["args"] == ("XYZ", date(2026, 6, 3))


def test_prepare_row_asserts_no_lookahead_bar():
    """A DB contract violation (a bar dated on/after the alert date reaching `prepare_row`) must
    raise loudly rather than silently render a leaked bar."""
    ad = date(2026, 6, 3)
    leaked = [
        {"date": date(2026, 5, 1), "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5,
         "volume": 1000.0},
        {"date": ad, "open": 12.0, "high": 13.0, "low": 11.0, "close": 12.5, "volume": 1000.0},
    ]

    async def fake_fetch(ticker, alert_date):
        return leaked, 12.0

    orig = mod.fetch_row_bars
    mod.fetch_row_bars = fake_fetch
    try:
        with pytest.raises(AssertionError, match="lookahead"):
            asyncio.run(mod.prepare_row("FAKE", ad.isoformat()))
    finally:
        mod.fetch_row_bars = orig


def test_render_function_takes_no_ticker_or_date_parameter():
    """Structural anonymisation: the render function's signature cannot accept an identity —
    the strongest form of 'it never leaks a ticker/date' is that it is never given one."""
    sig = inspect.signature(mod.render_point_in_time_charts)
    names = set(sig.parameters)
    for bad in ("ticker", "date", "alert_date", "ticker_symbol", "symbol"):
        assert bad not in names, f"render_point_in_time_charts accepts {bad!r} — anonymisation is no longer structural"


# ══════════════════════════════════════════════════════════════════════════════════════
# (b) ANONYMISATION
# ══════════════════════════════════════════════════════════════════════════════════════

_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _synthetic_ohlcv_df(n: int = 260, start_price: float = 50.0):
    import pandas as pd
    idx = pd.bdate_range("2019-01-02", periods=n)  # a REAL calendar range on purpose —
    # the point of this test is that _build_fig must never let it reach the canvas.
    close = start_price + pd.Series(range(n)).apply(lambda i: (i % 17) - 8).cumsum() * 0.3 + 40
    df = pd.DataFrame({
        "Open": close.values, "High": (close + 1).values, "Low": (close - 1).values,
        "Close": close.values, "Volume": [1000 + 10 * i for i in range(n)],
    }, index=idx)
    return df


def test_daily_fig_carries_no_date_text_and_no_visible_ticks():
    df = _synthetic_ohlcv_df()
    mas = {10: df["Close"].rolling(10).mean(), 20: df["Close"].rolling(20).mean()}
    fig = mod._build_fig(df, mas, mod.DAILY_WINDOW_SESSIONS, open_line=float(df["Close"].iloc[-1]) + 5)
    assert fig is not None
    all_text = [t.get_text() for t in fig.texts]
    for ax in fig.axes:
        all_text += [t.get_text() for t in ax.texts]
        all_text += [t.get_text() for t in ax.get_xticklabels()]
        assert ax.get_xticks().size == 0 or all(lbl.get_text() == "" for lbl in ax.get_xticklabels())
        assert ax.get_title() == ""
    joined = " ".join(all_text)
    assert not _ISO_DATE_RE.search(joined), f"a date leaked into the chart text: {all_text!r}"
    assert "2019" not in joined and "2020" not in joined
    # only allowed text is the empty suptitle and the "today's open" label
    assert set(t for t in all_text if t) <= {"today's open"}
    import matplotlib.pyplot as plt
    plt.close(fig)


def test_weekly_fig_carries_no_date_text_either():
    df = _synthetic_ohlcv_df(n=400)
    weekly = df.resample("W-FRI").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
    mas = {10: weekly["Close"].rolling(10).mean()}
    fig = mod._build_fig(weekly, mas, mod.WEEKLY_WINDOW_WEEKS, open_line=None)
    assert fig is not None
    all_text = [t.get_text() for t in fig.texts]
    for ax in fig.axes:
        all_text += [t.get_text() for t in ax.texts]
        assert all(lbl.get_text() == "" for lbl in ax.get_xticklabels())
    joined = " ".join(all_text)
    assert not _ISO_DATE_RE.search(joined)
    import matplotlib.pyplot as plt
    plt.close(fig)


def _fake_pngs():
    return b"\x89PNG-daily-fake", b"\x89PNG-weekly-fake"


def test_arm2_stock_chart_suffix_is_byte_identical_to_arm1():
    """Arm 2's content minus its book prefix must be EXACTLY arm 1's content — the only
    difference between the two requests is the (cached) book block, per the pre-registration."""
    daily_png, weekly_png = _fake_pngs()
    book_blocks = [{"type": "text", "text": "intro"},
                  {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                               "data": "AAAA"}},
                  {"type": "text", "text": "annotation", "cache_control": {"type": "ephemeral"}}]
    plain = mod.build_user_content("plain", daily_png, weekly_png, None)
    books = mod.build_user_content("books", daily_png, weekly_png, book_blocks)
    assert books[:len(book_blocks)] == book_blocks
    assert books[len(book_blocks):] == plain


def test_prompt_never_carries_a_population_ticker_or_date_outside_the_book_block():
    """Scan every population (ticker, date) against the model-facing TEXT of the request,
    scoped OUTSIDE the book block (the book legitimately names real 2020-21 tickers — e.g.
    TraderLion #10 is RARE, which also happens to be a labelled BAD_CHART ticker — and its
    annotations are prose that may contain year numbers; those are not the leak this test
    guards against)."""
    daily_png, weekly_png = _fake_pngs()
    book_blocks, n_images = mod.load_book_content()
    assert n_images == mod.EXPECTED_BOOK_IMAGES

    pop = mod.load_population()
    tickers = {tk for _, tk, _, _ in pop}
    for arm, bb in (("plain", None), ("books", book_blocks)):
        content = mod.build_user_content(arm, daily_png, weekly_png, bb)
        suffix = content[len(bb):] if bb else content
        text_parts = [b["text"] for b in suffix if b.get("type") == "text"]
        joined = " ".join(text_parts)
        assert not _ISO_DATE_RE.search(joined), f"{arm}: an ISO date leaked outside the book block: {joined!r}"
        for tk in tickers:
            # whole-token match only (avoid false hits like "OK" inside "book")
            assert not re.search(rf"\b{re.escape(tk)}\b", joined), (
                f"{arm}: ticker {tk!r} leaked into the non-book request text: {joined!r}")
    # the system text (identical both arms) is likewise clean
    assert not _ISO_DATE_RE.search(mod.SYSTEM_TEXT)
    for tk in tickers:
        assert not re.search(rf"\b{re.escape(tk)}\b", mod.SYSTEM_TEXT)


def test_book_content_matches_every_image_to_an_annotation():
    blocks, n_images = mod.load_book_content()
    assert n_images == 24
    n_image_blocks = sum(1 for b in blocks if b.get("type") == "image")
    n_text_blocks = sum(1 for b in blocks if b.get("type") == "text")
    assert n_image_blocks == 24
    assert n_text_blocks == 25  # the intro + one annotation per image
    assert blocks[-1].get("cache_control") == {"type": "ephemeral"}
    assert sum(1 for b in blocks if "cache_control" in b) == 1


def test_book_content_fails_loudly_on_a_missing_annotation(tmp_path):
    (tmp_path / "docs" / "methodology" / "operator_shared_charts" /
     "2026-09-23_traderlion_2020_leaders").mkdir(parents=True)
    (tmp_path / "docs" / "methodology" / "operator_shared_charts" /
     "2026-09-23_boik_monster_stock_lessons_2020_2021").mkdir(parents=True)
    md1 = tmp_path / "docs" / "methodology" / "traderlion_2020_leaders_2026-09-23.md"
    md2 = tmp_path / "docs" / "methodology" / "boik_monster_stock_lessons_2026-09-23.md"
    md1.write_text("# t\n\n### 01 AAA\n- some words\n")
    md2.write_text("# t\n")
    img_dir = tmp_path / "docs" / "methodology" / "operator_shared_charts" / "2026-09-23_traderlion_2020_leaders"
    (img_dir / "01_AAA.jpg").write_bytes(b"\xff\xd8\xff")
    (img_dir / "02_BBB.jpg").write_bytes(b"\xff\xd8\xff")  # no annotation for this one
    with pytest.raises(RuntimeError, match="no annotation"):
        mod.load_book_content(repo=tmp_path)


# ══════════════════════════════════════════════════════════════════════════════════════
# (c) SCORER BOUNDARIES
# ══════════════════════════════════════════════════════════════════════════════════════

def _pop(n_condemned=21, n_worked=39, n_other=4):
    """A synthetic population shaped like the real one: n_condemned BAD_CHART (split 30 real-EP
    + 9 approved for n_worked=39), n_other OTHER_REJECTED."""
    pop = []
    n_ep = round(n_worked * 30 / 39)
    n_app = n_worked - n_ep
    for i in range(n_ep):
        pop.append(("REAL_EP", f"EP{i}", f"2026-01-{(i % 28) + 1:02d}", "REAL_EP"))
    for i in range(n_app):
        pop.append(("APPROVED", f"AP{i}", f"2026-02-{(i % 28) + 1:02d}", "GOOD_CHART"))
    for i in range(n_condemned):
        pop.append(("BAD_CHART", f"BC{i}", f"2026-03-{(i % 28) + 1:02d}", "BAD_CHART"))
    for i in range(n_other):
        pop.append(("OTHER_REJECTED", f"OR{i}", f"2026-04-{(i % 28) + 1:02d}", "WRONG_DAY"))
    return pop


def _calls_for(pop, rating_fn):
    """rating_fn(pop, ticker, date, arm, replicate) -> rating|None."""
    calls = []
    for p, tk, d, _v in pop:
        for arm in mod.ARMS:
            for r in range(mod.REPLICATES):
                rating = rating_fn(p, tk, d, arm, r)
                calls.append({"arm": arm, "ticker": tk, "date": d, "replicate": r,
                             "rating": rating, "reason": "x"})
    return calls


def test_lean_ratio_boundaries():
    assert mod._lean_ratio(0.5, None) is None
    assert mod._lean_ratio(0.0, 0.0) is None
    assert math.isinf(mod._lean_ratio(0.5, 0.0))
    assert mod._lean_ratio(0.6, 0.2) == pytest.approx(3.0)
    assert mod._lean_ratio(0.3, 0.2) == pytest.approx(1.5)


def test_modal_rating_requires_a_majority():
    assert mod.modal_rating(["bad", "bad", "ok"]) == "bad"
    assert mod.modal_rating(["bad", "ok", "good"]) is None       # 1-1-1: reads nothing
    assert mod.modal_rating(["bad", None, "bad"]) == "bad"       # 2 of 2 valid, still a majority
    assert mod.modal_rating(["bad", None, "ok"]) is None         # 1 of 2 valid: no majority
    assert mod.modal_rating([None, None, None]) is None


def test_all_three_agree_and_garbage_all_three():
    assert mod.all_three_agree(["bad", "bad", "bad"])
    assert not mod.all_three_agree(["bad", "bad", "ok"])
    assert not mod.all_three_agree(["bad", "bad", None])
    assert mod.garbage_all_three(["garbage", "garbage", "garbage"])
    assert not mod.garbage_all_three(["garbage", "garbage", "bad"])
    assert not mod.garbage_all_three(["garbage", "garbage", None])


def test_stable_bar_is_ceil_two_thirds():
    assert mod.stable_bar(64) == 43
    assert mod.stable_bar(3) == 2
    assert mod.stable_bar(9) == 6


def _first_keys(pop, pops, n):
    """The first `n` (ticker, date) keys among rows whose pop group is in `pops`, in population
    order — a precise count regardless of how each group's own per-row index is labelled (EP and
    APPROVED tickers both start their own numbering at 0, so an idx-threshold compared across
    both groups does NOT give a clean combined count; picking explicit keys does)."""
    keys = [(tk, d) for p, tk, d, _v in pop if p in pops]
    assert n <= len(keys)
    return set(keys[:n])


def _bad_set_rating_fn(bad_keys):
    def fn(p, tk, d, arm, r):
        return "bad" if (tk, d) in bad_keys else "ok"
    return fn


def test_line3_boundary_at_1_5_and_3_0():
    """21 condemned, 39 worked. Rig EXACT integer bad-counts on each side so the ratio lands
    exactly (not approximately, via float rounding) at the tested boundary, holding line 4
    undefined (not_extended is empty, so USEFUL_SUPPORT is structurally unreachable here) so
    line 3 alone decides NO_LEAN vs WEAK."""
    pop = _pop()
    worked_pops = {"REAL_EP", "APPROVED"}

    def rating_fn(n_bad_condemned, n_bad_worked):
        bad = _first_keys(pop, {"BAD_CHART"}, n_bad_condemned) | _first_keys(pop, worked_pops, n_bad_worked)
        return _bad_set_rating_fn(bad)

    # condemned 6/21 (0.2857), worked 10/39 (0.2564) -> ratio 1.114 < 1.5
    calls = _calls_for(pop, rating_fn(6, 10))
    s = mod.score_run(calls, pop, frozenset())
    assert s["plain"]["line3_lean"] < 1.5
    assert s["plain"]["decision"] == "NO_LEAN"

    # condemned 21/21 (1.0), worked 26/39 (0.6667) -> ratio EXACTLY 1.5
    calls = _calls_for(pop, rating_fn(21, 26))
    s = mod.score_run(calls, pop, frozenset())
    assert s["plain"]["line3_lean"] == pytest.approx(1.5, abs=1e-9)
    assert s["plain"]["decision"] != "NO_LEAN"

    # condemned 15/21 (0.7143), worked 13/39 (0.3333) -> ratio 2.143, in [1.5, 3.0)
    calls = _calls_for(pop, rating_fn(15, 13))
    s = mod.score_run(calls, pop, frozenset())
    assert 1.5 <= s["plain"]["line3_lean"] < 3.0
    assert s["plain"]["decision"] == "WEAK"  # line4 is None (not_extended empty) -> never USEFUL

    # condemned 21/21 (1.0), worked 13/39 (0.3333) -> ratio EXACTLY 3.0
    calls = _calls_for(pop, rating_fn(21, 13))
    s = mod.score_run(calls, pop, frozenset())
    assert s["plain"]["line3_lean"] == pytest.approx(3.0, abs=1e-9)


def test_line4_and_line8_boundaries_feed_the_decision():
    """Line 4 (>=2x on the 12) and line 8 (garbage >=3/12 and <=1/39) are independent bars —
    pin each boundary directly against `score_arm` rather than the whole decision function.
    EXACT integer counts (12-subset / 39-worked), not rate-rounding, so the boundary lands
    precisely."""
    pop = _pop()
    not_extended = frozenset((f"BC{i}", f"2026-03-{(i % 28) + 1:02d}") for i in range(12))

    def make_calls(n_worked_bad, n_twelve_bad):
        bad = (_first_keys(pop, {"REAL_EP", "APPROVED"}, n_worked_bad)
              | set(list(not_extended)[:n_twelve_bad]))
        return _calls_for(pop, _bad_set_rating_fn(bad))

    # 8/12 (0.6667) vs 13/39 (0.3333) -> ratio EXACTLY 2.0
    calls = make_calls(n_worked_bad=13, n_twelve_bad=8)
    s = mod.score_run(calls, pop, not_extended)["plain"]
    assert s["line4_lean_on_the_12"]["ratio"] == pytest.approx(2.0, abs=1e-9)

    # 7/12 (0.5833) vs 13/39 (0.3333) -> ratio 1.75, clearly under 2.0
    calls = make_calls(n_worked_bad=13, n_twelve_bad=7)
    s = mod.score_run(calls, pop, not_extended)["plain"]
    assert s["line4_lean_on_the_12"]["ratio"] < 2.0


def test_line8_garbage_filter_met_and_not_met():
    pop = _pop()
    not_extended = frozenset((f"BC{i}", f"2026-03-{(i % 28) + 1:02d}") for i in range(12))

    def fn_met(p, tk, d, arm, r):
        # 3 of the 12 read garbage all-3; 1 of the 39 worked reads garbage all-3.
        idx = int(tk[2:])
        if p == "BAD_CHART" and (tk, d) in not_extended and idx < 3:
            return "garbage"
        if p in ("REAL_EP",) and idx == 0:
            return "garbage"
        return "ok"

    calls = _calls_for(pop, fn_met)
    s = mod.score_run(calls, pop, not_extended)["plain"]
    assert s["line8_garbage_filter"]["of_12"] == 3
    assert s["line8_garbage_filter"]["of_39"] == 1
    assert s["line8_garbage_filter"]["met"] is True

    def fn_not_met_low(p, tk, d, arm, r):
        idx = int(tk[2:])
        if p == "BAD_CHART" and (tk, d) in not_extended and idx < 2:  # only 2 of 12
            return "garbage"
        return "ok"

    calls = _calls_for(pop, fn_not_met_low)
    s = mod.score_run(calls, pop, not_extended)["plain"]
    assert s["line8_garbage_filter"]["of_12"] == 2
    assert s["line8_garbage_filter"]["met"] is False

    def fn_not_met_high(p, tk, d, arm, r):
        idx = int(tk[2:])
        if p == "BAD_CHART" and (tk, d) in not_extended and idx < 3:
            return "garbage"
        if p in ("REAL_EP",) and idx in (0, 1):  # 2 of 39
            return "garbage"
        return "ok"

    calls = _calls_for(pop, fn_not_met_high)
    s = mod.score_run(calls, pop, not_extended)["plain"]
    assert s["line8_garbage_filter"]["of_39"] == 2
    assert s["line8_garbage_filter"]["met"] is False


def test_line6_stable_boundary_42_vs_43_of_64():
    pop = _pop()  # 21 + 39 + 4 = 64

    def make_stable_calls(n_stable):
        keys = [(tk, d) for _, tk, d, _ in pop]
        stable_keys = set(keys[:n_stable])

        def fn(p, tk, d, arm, r):
            if (tk, d) in stable_keys:
                return "ok"          # all 3 replicates identical
            return "bad" if r == 0 else "ok"   # replicate 0 differs -> not all-3-agree
        return _calls_for(pop, fn)

    calls = _calls_for(pop, lambda p, tk, d, arm, r: "ok")  # all identical -> fully stable
    for _, tk, d, _v in pop[:22]:  # break agreement on 22 of 64 -> 42 stable
        for c in calls:
            if c["ticker"] == tk and c["date"] == d and c["replicate"] == 0:
                c["rating"] = "bad"
    s = mod.score_run(calls, pop, frozenset())["plain"]
    assert s["line6_stable"]["of"] == 64
    assert s["line6_stable"]["n"] == 42
    assert s["line6_stable"]["bar"] == 43
    assert s["line6_stable"]["met"] is False

    calls2 = mod.score_run.__wrapped__ if False else None  # no-op, keep linter quiet
    calls = _calls_for(pop, lambda p, tk, d, arm, r: "ok")
    for _, tk, d, _v in pop[:21]:  # break agreement on 21 of 64 -> 43 stable
        for c in calls:
            if c["ticker"] == tk and c["date"] == d and c["replicate"] == 0:
                c["rating"] = "bad"
    s = mod.score_run(calls, pop, frozenset())["plain"]
    assert s["line6_stable"]["n"] == 43
    assert s["line6_stable"]["met"] is True


def test_na_rows_are_excluded_from_every_line():
    pop = _pop(n_condemned=3, n_worked=3, n_other=0)
    na_keys = frozenset({(pop[0][1], pop[0][2])})
    calls = _calls_for(pop, lambda p, tk, d, arm, r: "bad")
    s = mod.score_run(calls, pop, frozenset(), na_keys)["plain"]
    total_scored = s["n_condemned"] + s["n_worked"]
    assert total_scored == len(pop) - 1  # the na row dropped out


# ══════════════════════════════════════════════════════════════════════════════════════
# (e) PAID-RUN PRICE GATE
# ══════════════════════════════════════════════════════════════════════════════════════

class _FakeCountTokensResp:
    def __init__(self, n):
        self.input_tokens = n


def test_paid_run_aborts_before_any_create_call_when_price_exceeds_max_usd(tmp_path, monkeypatch):
    small_pop = [
        ("REAL_EP", "AAA", "2026-01-05", "REAL_EP"),
        ("BAD_CHART", "BBB", "2026-01-06", "BAD_CHART"),
    ]
    monkeypatch.setattr(mod, "load_population", lambda: small_pop)

    async def fake_prepare_all_rows(population):
        return {(tk, d): {"ticker": tk, "date": d, "daily_png": b"FAKE-DAILY",
                          "weekly_png": None, "render_failed": False, "na_scoring": False,
                          "anchor75": False, "clean_n": 100}
               for _, tk, d, _ in population}
    monkeypatch.setattr(mod, "prepare_all_rows", fake_prepare_all_rows)

    client = AsyncMock()
    # an enormous input-token count guarantees the priced estimate blows any reasonable budget
    client.messages.count_tokens = AsyncMock(return_value=_FakeCountTokensResp(50_000_000))
    client.messages.create = AsyncMock()

    async def fake_mean_output_tokens(model):
        return 500.0, 20

    result = asyncio.run(mod.run_paid(
        client, tmp_path / "out", max_usd=20.0, resume=False,
        mean_output_tokens_fn=fake_mean_output_tokens))

    assert result is None, "run_paid must return None (no scorecard) on an aborted price gate"
    client.messages.create.assert_not_called()
    assert not (tmp_path / "out" / "calls.jsonl").exists(), (
        "no calls.jsonl should be created when the run aborts before any call")


def test_price_whole_run_is_pure_and_scales_with_calls():
    price = mod.price_whole_run(
        n_dates=64, replicates=3, arm1_input_tokens=3000, arm2_input_tokens_total=20000,
        out_mean_tokens=200.0, model=mod.MODEL)
    assert price["n_calls_total"] == 64 * 3 * 2
    assert price["total_usd"] > 0
    # arm2 with a nonzero book segment must cost MORE than an identical arm1-only run scaled x2
    # (cache write premium on the first call), but the marginal (non-book) cost must be smaller
    # per call than paying full price for the whole arm-2 request every time.
    naive_arm2_full_price_every_call = (
        price["n_calls_per_arm"] * price["arm2_input_tokens_total"]
        * mod.pricing_for(mod.MODEL)["input"] / 1e6)
    assert price["arm2_cost_usd"] < naive_arm2_full_price_every_call + 1e-9


def test_price_whole_run_zero_calls_is_zero_cost():
    price = mod.price_whole_run(n_dates=0, replicates=3, arm1_input_tokens=1000,
                                arm2_input_tokens_total=5000, out_mean_tokens=100.0,
                                model=mod.MODEL)
    assert price["total_usd"] == 0.0


# ══════════════════════════════════════════════════════════════════════════════════════
# misc plumbing
# ══════════════════════════════════════════════════════════════════════════════════════

def test_redact_for_json_strips_image_bytes_but_keeps_structure():
    kw = mod.build_request_kwargs(mod.MODEL, "plain", b"\x89PNGDATA" * 100, None, None,
                                  max_tokens=2048)
    red = mod.redact_for_json(kw)
    s = str(red)
    assert "PNGDATA" not in s
    assert "omitted" in s
    assert red["model"] == mod.MODEL
    assert red["system"] == mod.SYSTEM_TEXT


def test_output_config_schema_is_the_pre_registered_four_words():
    schema = mod.RATING_SCHEMA
    assert schema["properties"]["rating"]["enum"] == ["garbage", "bad", "ok", "good"]
    assert schema["properties"]["reason"]["type"] == "string"
    assert schema.get("additionalProperties") is False
