"""Pull AGYS raw quarterly revenue from yfinance, compute YoY directly.
No transforms — raw to compare against AGYS IR / 8-K.

Run: docker exec apollo-market python -m scripts._verify_agys_yfinance_raw
"""
import yfinance as yf


def main():
    t = yf.Ticker("AGYS")

    print("=== AGYS quarterly_financials ===")
    qf = t.quarterly_financials
    print(qf.columns.tolist() if not qf.empty else "EMPTY")
    print()

    if not qf.empty:
        print("=== Revenue rows ===")
        # Try common revenue line names
        for line in ["TotalRevenue", "Revenue", "OperatingRevenue"]:
            if line in qf.index:
                series = qf.loc[line]
                print(f"\n{line}:")
                for col, val in series.items():
                    print(f"  {col}: {val}")

    print("\n=== Income statement (annual) ===")
    af = t.financials
    if not af.empty and "TotalRevenue" in af.index:
        rev = af.loc["TotalRevenue"]
        print("Annual TotalRevenue:")
        for col, val in rev.items():
            print(f"  {col}: {val}")

    print("\n=== Computed YoY (latest vs same quarter year ago) ===")
    if not qf.empty and "TotalRevenue" in qf.index:
        series = qf.loc["TotalRevenue"]
        # quarterly_financials returns most-recent-first; index 0 is latest
        values = list(series.items())
        if len(values) >= 5:
            latest = values[0]
            year_ago = values[4]  # 4 quarters back
            if latest[1] and year_ago[1]:
                yoy_pct = (latest[1] - year_ago[1]) / year_ago[1] * 100
                print(f"  Latest:    {latest[0]}: ${latest[1]:,.0f}")
                print(f"  Year ago:  {year_ago[0]}: ${year_ago[1]:,.0f}")
                print(f"  YoY:       {yoy_pct:.2f}%")
            else:
                print("  Missing values for YoY calc")
        else:
            print(f"  Only {len(values)} quarters available; need 5+ for YoY")

    print("\n=== info dict (selected fields) ===")
    info = t.info
    for k in ["revenueGrowth", "earningsGrowth", "quarterlyRevenueGrowth",
              "quarterlyEarningsGrowth", "totalRevenue"]:
        if k in info:
            print(f"  {k}: {info[k]}")


if __name__ == "__main__":
    main()
