import os, re, sys, glob, collections

ROOT = sys.argv[1] if len(sys.argv) > 1 else r"C:/Users/Ashu/Documents/wakewordprod/.data/LibriSpeech"
subsets = sys.argv[2].split(",") if len(sys.argv) > 2 else ["dev-clean"]

CANDIDATES = ["something", "children", "morning", "before", "himself", "captain"]

word_utt = collections.Counter()      # word -> number of utterances containing it
word_spk = collections.defaultdict(set)  # word -> set of speakers
total_utts = 0

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
                words = set(re.findall(r"[a-z']+", text.lower()))
                for w in words:
                    word_utt[w] += 1
                    word_spk[w].add(spk)

print(f"total_utts={total_utts} subsets={subsets}")
print("=== Candidate stats (>=2 syllable distinctive words) ===")
for w in CANDIDATES:
    print(f"  {w:12s} utts={word_utt[w]:5d} speakers={len(word_spk[w]):3d}")

print("=== Top multi-char words meeting >=200 utts & >=25 spk ===")
rows = []
for w, c in word_utt.items():
    ns = len(word_spk[w])
    if len(w) >= 5 and c >= 200 and ns >= 25:
        rows.append((c, ns, w))
rows.sort(reverse=True)
for c, ns, w in rows[:40]:
    print(f"  {w:14s} utts={c:5d} speakers={ns:3d}")
