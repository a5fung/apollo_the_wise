"""Debug: what yfinance lines are actually available for AGYS quarterly?

Run: docker exec apollo-market python -m scripts._debug_agys_yfinance_margins
"""
import yfinance as yf


def main():
    t = yf.Ticker("AGYS")
    qf = t.quarterly_financials

    if qf is None or qf.empty:
        print("EMPTY")
        return

    print(f"Columns (quarters, most-recent-first):")
    for c in qf.columns:
        print(f"  {c}")
    print()

    print(f"All available line items (index):")
    for line in qf.index:
        print(f"  {line}")
    print()

    # Try computing margins for q1 (most recent yfinance quarter)
    print("Computing margins for index 0 (latest yfinance quarter):")
    candidates = {
        "gross_margin_attempt_1": ("GrossProfit", "TotalRevenue"),
        "gross_margin_attempt_2": ("Gross Profit", "Total Revenue"),
        "op_margin_attempt_1": ("OperatingIncome", "TotalRevenue"),
        "op_margin_attempt_2": ("Operating Income", "Total Revenue"),
        "net_margin_attempt_1": ("NetIncome", "TotalRevenue"),
        "net_margin_attempt_2": ("Net Income", "Total Revenue"),
    }
    for name, (num_line, den_line) in candidates.items():
        if num_line in qf.index and den_line in qf.index:
            n = qf.loc[num_line].iloc[0]
            d = qf.loc[den_line].iloc[0]
            print(f"  {name}: num=${n} den=${d} ratio={n/d if d else None}")
        else:
            print(f"  {name}: lines not in index (num={num_line in qf.index}, den={den_line in qf.index})")


if __name__ == "__main__":
    main()
