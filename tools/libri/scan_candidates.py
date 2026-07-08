import os, re, sys, glob, collections

ROOT = r"C:/Users/Ashu/Documents/wakewordprod/.data/LibriSpeech"
subsets = sys.argv[1].split(",") if len(sys.argv) > 1 else ["dev-clean", "test-clean"]

CANDIDATES = ["something", "everything", "morning", "without", "children",
              "remember", "together", "himself", "general", "wonderful"]

word_utt = collections.Counter()
word_spk = collections.defaultdict(set)
total_utts = 0
total_spk = set()

for sub in subsets:
    base = os.path.join(ROOT, sub)
    for trans in glob.glob(os.path.join(base, "*", "*", "*.trans.txt")):
        with open(trans, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                uid, text = line.split(" ", 1)
                spk = uid.split("-")[0]
                total_utts += 1
                total_spk.add(spk)
                words = set(re.findall(r"[a-z']+", text.lower()))
                for w in words:
                    word_utt[w] += 1
                    word_spk[w].add(spk)

print(f"subsets={subsets} total_utts={total_utts} total_speakers={len(total_spk)}")
print(f"{'word':12s} {'utts':>6s} {'spk':>5s}  meets(>=800utt,>=150spk)")
rows = []
for w in CANDIDATES:
    u = word_utt[w]; s = len(word_spk[w])
    meets = "YES" if (u >= 800 and s >= 150) else ""
    rows.append((u, s, w, meets))
for u, s, w, m in sorted(rows, reverse=True):
    print(f"{w:12s} {u:6d} {s:5d}  {m}")
