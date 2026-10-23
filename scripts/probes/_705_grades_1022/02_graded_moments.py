"""#705 Track A (2026-10-22, outcome-free, $0): Qullamaggie's GRADED moments. Every ticker-matched caption moment
(stream_moments.tsv + the 2016-2022 extension, de-duplicated on video + ticker + time) whose surrounding caption window carries a grade:
  best    — best / perfect / textbook / beautiful setup|chart|flag|base, or "A plus";
  bought  — I bought / added / got in / took a starter|position / entered; I'm long / in it;
  not_yet — needs (a few / more) days|weeks; needs to tighten; not (quite) ready; too loose / wide / extended.
A window can carry several (flagged 'mixed'). No outcome is read. Writes graded_moments.tsv and the frame manifest for the graded
(video, ticker) pairs that have no frame yet (one frame per pair, at the first graded moment)."""
import re, csv, collections
QM = "/Users/alvinfung/apollo_data/cb702/qm_streams"
C = {"best": r"\b(best|perfect|textbook|beautiful) (setup|set up|chart|flag|base)s?\b|\ba[ -]?plus\b",
     "bought": r"\bi (bought|added|got in|took a (starter|position)|entered)\b|\bi'?m (long|in it)\b",
     "not_yet": r"\bneeds? (a )?(few |couple )?(more )?(days|weeks)\b|\bneeds? to tighten\b|\bnot (quite )?ready\b|\btoo (loose|wide|extended)\b"}
rows, seen = [], set()
for f in (f"{QM}/stream_moments.tsv", f"{QM}/ext_2016_2022/stream_moments_ext.tsv"):
    for r in csv.DictReader(open(f, encoding="utf-8"), delimiter="\t"):
        k = (r["video"], r["ticker"], r["t"])
        if k in seen: continue
        seen.add(k)
        w = ((r.get("window") or "") + " " + (r.get("quote") or "")).lower()
        g = [c for c, rx in C.items() if re.search(rx, w)]
        if g: rows.append({**{x: r[x] for x in ("video", "upload_date", "t", "ts", "ticker", "tier", "via")}, "grades": ",".join(g),
                           "quote": (r.get("quote") or "")[:220].replace("\t", " ")})
cnt = collections.Counter(r["grades"] for r in rows)
pairs = {}
for r in sorted(rows, key=lambda r: (r["video"], r["ticker"], float(r["t"]))):
    pairs.setdefault((r["video"], r["ticker"]), r)
with open(f"{QM}/vision/graded_moments.tsv", "w") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter="\t"); w.writeheader(); w.writerows(rows)
framed = set()
for m in ("batch1_manifest.tsv", "p4b_manifest.tsv"):
    for r in csv.DictReader(open(f"{QM}/vision/{m}", encoding="utf-8"), delimiter="\t"): framed.add((r["vid"], r["ticker"]))
todo = [r for k, r in pairs.items() if k not in framed]
with open(f"{QM}/vision/grades_manifest.tsv", "w") as fh:
    fh.write("order\tbase\tticker\tref_date\tvid\tts\tkind\tframe_id\n")
    for i, r in enumerate(todo):
        d = r["upload_date"]; d = f"{d[:4]}-{d[4:6]}-{d[6:]}" if "-" not in d else d
        fh.write(f"{i}\t{r['ticker']}|{d}\t{r['ticker']}\t{d}\t{r['video']}\t{r['ts']}\t{r['grades']}\tg_{i:04d}\n")
print(f"moments scanned {len(seen):,}; graded {len(rows):,}; by grade {dict(cnt.most_common(8))}")
print(f"graded (video, ticker) pairs {len(pairs):,}; already framed {len(pairs) - len(todo)}; frames to cut {len(todo):,}; "
      f"videos {len({r['video'] for r in todo})}")
