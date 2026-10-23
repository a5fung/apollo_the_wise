"""#705 Track A prep (2026-10-22, outcome-free, $0): how often Qullamaggie's captions carry a GRADE, after de-duplicating YouTube's
rolling captions (qmlib.parse_vtt). Counts phrase hits per class across every fetched video, with the videos' date span. No ticker
matching and no outcome is read here; it sizes the label set before the extraction is designed."""
import glob, os, re, sys, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "_qm_streams"))
import qmlib
SUBS = "/Users/alvinfung/apollo_data/cb702/qm_streams/subs"
CLASSES = {
    "aplus":    r"\ba[ -]?plus\b|\ba\+",
    "best":     r"\b(best|perfect|textbook|beautiful) (setup|set up|chart|flag|base)\b",
    "bought":   r"\bi (bought|added|got in|took a (starter|position)|entered)\b|\bi'?m (long|in it)\b",
    "not_yet":  r"\b(needs?|need) (a )?(few |couple )?(more )?(days|weeks) to (tighten|set up|consolidate)\b|\b(needs?|need) to tighten\b|\bnot (quite )?ready\b|\btoo (loose|wide|extended)\b",
    "watch":    r"\b(on|in) my (watch ?list|radar)\b|\bwatching (it|this)\b",
}
hits = collections.Counter(); vids = collections.Counter(); dates = []
st = {}
for ln in open("/Users/alvinfung/apollo_data/cb702/qm_streams/video_status.tsv"):
    p = ln.rstrip("\n").split("\t")
    if p[0] != "id" and len(p) > 4: st[p[0]] = p[4]
files = sorted(glob.glob(f"{SUBS}/*.vtt"))
for f in files:
    vid = os.path.basename(f).split(".")[0]
    words = qmlib.parse_vtt(f)
    text = " ".join(w for _, w in words).lower()
    seen = False
    for k, rx in CLASSES.items():
        n = len(re.findall(rx, text))
        if n: hits[k] += n; vids[k] += 1; seen = True
    if st.get(vid): dates.append(st[vid])
print(f"videos with captions: {len(files)}; upload dates {min(dates)}..{max(dates)} (n with a date {len(dates)})")
for k in CLASSES:
    print(f"  {k:8s}: {hits[k]:5d} phrase hits in {vids[k]:3d} videos")
