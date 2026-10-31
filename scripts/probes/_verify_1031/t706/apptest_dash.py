import sys, os, json
sys.path.insert(0, os.getcwd())
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("pages/Apollo_Trades.py", default_timeout=120)
at.run()
print("exception:", [e.value for e in at.exception])
print("tabs:", [t.label for t in at.tabs])
for i, df in enumerate(at.dataframe):
    d = df.value
    print(i, list(d.columns), len(d))
    cols = [c for c in d.columns if c in ("Ticker","Win/Loss %","Size %","Stop %","P&L","R")]
    print(d[cols].head(12).to_string() if cols else "")
for t in at.table:
    print("table", list(t.value.columns), len(t.value))
