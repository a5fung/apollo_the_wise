import json
import r4_common as C
import v1_replay as R
C.assert_pins()
out = C.OUTD / "parity"; out.mkdir(exist_ok=True)
res = R.run_parity(out)
print(json.dumps(res, default=str)[:1500])
json.dump(res, open(C.OUTD / "stage1a_parity_r4.json", "w"), default=str, indent=1)
