import sys, os
sys.path.insert(0, os.getcwd())
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("pages/Apollo_Trades.py", default_timeout=120)
at.run()
d = at.dataframe[6].value
cl = d[d["Status"].astype(str).str.lower().str.contains("clos")]
op = d[~d["Status"].astype(str).str.lower().str.contains("clos")]
print("rows", len(d), "closed", len(cl), "open", len(op))
print("closed with blank Win/Loss %:", int((cl["Win/Loss %"]=="—").sum()))
print("closed with Size/Stop populated (should be none):", int((cl["Size %"]!="—").sum()), int((cl["Stop %"]!="—").sum()))
print(op[["Ticker","Status","Entry","Stop","Sh","R","P&L","Win/Loss %","Size %","Stop %"]].to_string())
# any markdown/metric mention of open positions block
for m in at.markdown:
    v = str(m.value)
    if "IRON" in v or "open position" in v.lower() or "Size" in v: print("MD:", v[:200].replace("\n"," "))
for s in at.subheader: print("SUB:", s.value)
