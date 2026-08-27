"""FIX 2 (2026-08-26) — `theme_count_active` counted NAMES, not themes.

The old query was:

    SELECT COUNT(DISTINCT name) FROM mi_themes
    WHERE stage != 'Retired' AND theme_date >= CURRENT_DATE - INTERVAL '7 days'

which counts every distinct name seen ANYWHERE in the 7-day window. It never takes the
latest row per name, so a theme that was renamed, merged away or retired keeps counting off
its older non-Retired rows for a further 7 days. `db.get_active_themes` — the reader the
theme engine and the EP scan actually use — fixed exactly this for itself on 2026-06-09
(the #214 RETIRED-GAP fix); this metric never got the same fix.

Measured on prod, read-only: on 2026-08-26 the metric read **166** while the live active set
was **104**. It also read as CLIMBING (159 -> 166 across the week) while the real theme count
FELL 114 -> 104. `theme_count_active` fired L2 on four of the last six nights on that
artifact. The gap gets structurally worse now that deliberate renames exist (FIX 1), because
a rename adds a name without adding a theme.

The SQL is pinned as TEXT (the `test_530_prior_desc_lookup_sql_filters_empty_tickers`
precedent) because these queries are unreachable without a live Postgres: a semantic test
would need a DB, and the load-bearing part is a query SHAPE that a future edit could quietly
drop.
"""
import ast
import inspect
import re
import textwrap

from agents.market_intelligence import db, system_audit


def _sql_of(fn) -> str:
    """The function's CODE with its docstring removed, whitespace-normalised.

    The docstring quotes the old buggy query verbatim (deliberately — the evidence belongs
    next to the code), so a naive source scan would match the very string these tests exist
    to prove is gone."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    node = tree.body[0]
    if (node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)):
        node.body = node.body[1:]
    return " ".join(ast.unparse(tree).split())


METRIC_SQL = _sql_of(system_audit._today_active_themes)
ACTIVE_THEMES_SQL = _sql_of(db.get_active_themes)


def test_FAILS_WITHOUT_FIX_the_metric_no_longer_counts_distinct_names():
    """The whole defect in one line. `COUNT(DISTINCT name)` over a 7-day window is a count
    of NAMES SEEN, not of themes that exist."""
    assert "COUNT(DISTINCT name)" not in METRIC_SQL


def test_metric_takes_the_latest_row_per_name_before_judging_stage():
    """The ORDER of the two operations is the entire fix: latest row per name FIRST, then
    drop the Retired ones. Pre-filtering by stage is what let a retired theme resurrect off
    an older non-Retired snapshot."""
    assert "DISTINCT ON (name)" in METRIC_SQL
    assert "ORDER BY name, theme_date DESC" in METRIC_SQL
    latest = METRIC_SQL.index("DISTINCT ON (name)")
    stage_filter = METRIC_SQL.rindex("stage != 'Retired'")
    assert stage_filter > latest, "stage must be filtered AFTER latest-row-per-name"


def test_metric_mirrors_get_active_themes_shape():
    """It must measure what `get_active_themes` returns, since that is the set the engine
    and the EP in-theme bonus actually read."""
    for clause in ("DISTINCT ON (name)", "ORDER BY name, theme_date DESC",
                   "stage != 'Retired'"):
        assert clause in ACTIVE_THEMES_SQL, f"{clause} missing from get_active_themes"
        assert clause in METRIC_SQL, f"{clause} missing from the metric"


def test_both_use_the_same_seven_day_horizon():
    assert "INTERVAL '7 days'" in METRIC_SQL
    assert "get_active_themes(stale_after_days: int = 7)" in " ".join(
        inspect.signature(db.get_active_themes).parameters
    ) or db.get_active_themes.__defaults__ == (7,)


def test_anchor_is_deliberately_left_matching_get_active_themes():
    """Both use bare CURRENT_DATE (UTC, per the container). ET-anchoring only the metric
    would put it on a different day from the reader it reports on. Stated in the metric's
    docstring; pinned here so a well-meant tz "fix" has to argue with a test."""
    assert "CURRENT_DATE" in METRIC_SQL
    assert "CURRENT_DATE" in ACTIVE_THEMES_SQL
    assert "America/New_York" not in METRIC_SQL


def test_the_drill_query_was_fixed_too():
    """An operator drilling into a theme_count_active alarm must be handed the real active
    set, not a reproduction of the metric's own bug (the old drill grouped by name+stage
    over every row, listing a theme once per stage it ever wore and showing retired themes
    as live)."""
    spec = next(m for m in system_audit._ALL_METRICS if m.name == "theme_count_active")
    drill = " ".join(spec.drill_sql.split())
    assert "DISTINCT ON (name)" in drill
    assert "GROUP BY name, stage" not in drill
    assert re.search(r"INTERVAL '7 days'", drill)


def test_metric_is_still_registered_with_its_code_pointer():
    spec = next(m for m in system_audit._ALL_METRICS if m.name == "theme_count_active")
    assert spec.fetch_today is system_audit._today_active_themes
    assert "db.py::get_active_themes" in " ".join(spec.code_pointers)


def test_the_documented_prod_numbers_are_recorded_in_the_docstring():
    """The before/after is the evidence for a metric-definition change; keep it attached to
    the code rather than only in a report."""
    doc = system_audit._today_active_themes.__doc__ or ""
    assert "166" in doc and "104" in doc
