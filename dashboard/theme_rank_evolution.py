"""P25 — Theme Rank Evolution Dashboard (MVP).

Sister Streamlit app to Apollo. Reads mi_themes / mi_stock_scores via the
shared Postgres backend. Displays themes as rows, weeks as columns; cells
show theme rank, RS-avg, or member count. The visual narrative is:
themes moving up-and-to-the-right over weeks = the market's narrative arc.

This is the V1 viz that runs against RAW mi_themes with NO aggregation.
If fragmentation makes the chart unreadable, that's signal that the
canonical-ID layer (mi_theme_aliases or member-overlap matching) needs
to be built. If readable as-is, ship.

To run locally:
  pip install streamlit pandas plotly asyncpg
  streamlit run dashboard/theme_rank_evolution.py

Connection: reads DATABASE_URL env var. For local against the Hetzner
DB, tunnel first: `ssh -L 5432:localhost:5432 apollo@87.99.134.162`.

Production: separate sister app, read-only DB user, deferred per
project_market_intelligence_backlog P25 spec.
"""
import os
from datetime import date

import pandas as pd
import psycopg2
import streamlit as st


def _conn():
    """Read-only Postgres connection. Reads DATABASE_URL or constructs
    from POSTGRES_* env vars (matches the Apollo container setup)."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=os.environ.get("POSTGRES_DB", "apollo"),
        user=os.environ.get("POSTGRES_USER", "apollo"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
    )


@st.cache_data(ttl=300)
def load_theme_history(lookback_days: int = 90) -> pd.DataFrame:
    """Pull theme history from mi_themes. Each row is (theme_date, name,
    stage, score, rs_avg, ticker_count, pct_above_20sma, days_active)."""
    with _conn() as conn:
        df = pd.read_sql(
            f"""
            SELECT
                theme_date,
                name,
                stage,
                score,
                rs_avg,
                array_length(tickers, 1) AS ticker_count,
                pct_above_20sma,
                days_active,
                consecutive_accelerating,
                parent_theme
            FROM mi_themes
            WHERE theme_date >= CURRENT_DATE - INTERVAL '{lookback_days} days'
            ORDER BY theme_date, name
            """,
            conn,
        )
    return df


def compute_weekly_rank(df: pd.DataFrame, metric: str = "score") -> pd.DataFrame:
    """For each theme, compute weekly rank within the universe.
    Returns wide-form (rows = theme, cols = week-start-date)."""
    df = df.copy()
    df["week_start"] = pd.to_datetime(df["theme_date"]).dt.to_period("W").dt.start_time.dt.date
    # Take latest snapshot per (week, theme)
    df = df.sort_values(["week_start", "name", "theme_date"]).drop_duplicates(["week_start", "name"], keep="last")
    df["weekly_rank"] = df.groupby("week_start")[metric].rank(method="min", ascending=False)
    pivot = df.pivot(index="name", columns="week_start", values="weekly_rank")
    return pivot


def main() -> None:
    st.set_page_config(page_title="Theme Rank Evolution", layout="wide")
    st.title("📈 Apollo Theme Rank Evolution")
    st.caption("MVP — raw mi_themes, no canonicalization yet. If chart is unreadable due to renames, that confirms canonical-ID layer (P25 stage 2) is needed.")

    col1, col2, col3 = st.columns(3)
    with col1:
        lookback = st.slider("Lookback days", 30, 180, 90, step=15)
    with col2:
        metric = st.selectbox("Rank by", ["score", "rs_avg", "ticker_count", "days_active"])
    with col3:
        stage_filter = st.multiselect("Stages", ["Nascent", "Accelerating", "Mainstream", "Fading", "Retired"], default=["Accelerating", "Mainstream"])

    try:
        df = load_theme_history(lookback)
    except Exception as e:
        st.error(f"DB connection failed: {e}\n\nIf running locally, tunnel first: ssh -L 5432:localhost:5432 apollo@87.99.134.162")
        return

    if stage_filter:
        df = df[df["stage"].isin(stage_filter)]

    if df.empty:
        st.warning("No data for selected filters.")
        return

    st.subheader(f"Theme universe — {df['name'].nunique()} themes over {lookback}d")
    pivot = compute_weekly_rank(df, metric=metric)

    # Visual: heatmap-style rank table. Lower rank = better (1 = top).
    st.dataframe(pivot.fillna("—"), use_container_width=True)

    # Per-theme line chart
    st.subheader("Per-theme evolution")
    themes_chosen = st.multiselect("Themes to chart", sorted(df["name"].unique()), default=sorted(df["name"].unique())[:8])
    if themes_chosen:
        line_df = df[df["name"].isin(themes_chosen)].copy()
        line_df["theme_date"] = pd.to_datetime(line_df["theme_date"])
        chart_df = line_df.pivot(index="theme_date", columns="name", values=metric)
        st.line_chart(chart_df)

    # Raw data inspector
    with st.expander("Raw data"):
        st.dataframe(df, use_container_width=True)


if __name__ == "__main__":
    main()
