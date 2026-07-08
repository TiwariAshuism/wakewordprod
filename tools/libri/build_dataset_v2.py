import os, sys, glob, json, random, collections
import torch, torchaudio
import numpy as np
import soundfile as sf
from torchaudio.pipelines import MMS_FA as bundle

random.seed(1234)

ROOT = r"C:/Users/Ashu/Documents/wakewordprod/.data/LibriSpeech"
OUTROOT = r"C:/Users/Ashu/Documents/wakewordprod/dataset"
SR = 16000
WIN = SR  # 1.0 s window (samples)

TARGET = sys.argv[1]
SUBSETS = sys.argv[2].split(",") if len(sys.argv) > 2 else ["train-clean-100"]
MAX_POS = int(sys.argv[3]) if len(sys.argv) > 3 else 2500
MAX_NEG = int(sys.argv[4]) if len(sys.argv) > 4 else 7500
MAX_UTTS = int(sys.argv[5]) if len(sys.argv) > 5 else 3000  # cap aligned utterances (CPU budget)

outdir = os.path.join(OUTROOT, f"libri_{TARGET}")
posdir = os.path.join(outdir, "positives")
negdir = os.path.join(outdir, "negatives")
os.makedirs(posdir, exist_ok=True)
os.makedirs(negdir, exist_ok=True)

device = torch.device("cpu")
torch.set_num_threads(os.cpu_count() or 4)
model = bundle.get_model().to(device).eval()
tokenizer = bundle.get_tokenizer()
aligner = bundle.get_aligner()
DICT = bundle.get_dict()

def norm_word(w):
    return "".join(ch for ch in w.lower() if ch in DICT and ch != "*")

# ---- generic phonetic hard-negative test: words that share strong orthographic
#      (proxy for phonetic) overlap with the target: common prefix/suffix/3-gram ----
def _ngrams(s, n=3):
    return {s[i:i+n] for i in range(len(s) - n + 1)} if len(s) >= n else {s}
TGT_NG = _ngrams(TARGET)
def hard_neg(w):
    if w == TARGET or len(w) < 3:
        return False
    # shared prefix >=3
    p = 0
    for a, b in zip(w, TARGET):
        if a == b: p += 1
        else: break
    if p >= 3:
        return True
    # shared suffix >=3
    s = 0
    for a, b in zip(reversed(w), reversed(TARGET)):
        if a == b: s += 1
        else: break
    if s >= 3:
        return True
    # shared 3-gram (core cluster overlap)
    if _ngrams(w) & TGT_NG:
        return True
    return False

def load_wav(path):
    data, sr = sf.read(path, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    wav = torch.from_numpy(data).unsqueeze(0)
    if sr != SR:
        wav = torchaudio.functional.resample(wav, sr, SR)
    return wav

def span_to_clip(wav, x0, x1):
    T = wav.size(1)
    center = int(round((x0 + x1) / 2))
    start = center - WIN // 2
    end = start + WIN
    if start < 0:
        start, end = 0, WIN
    if end > T:
        end = T
        start = max(0, end - WIN)
    clip = wav[0, start:end].numpy().astype(np.float32)
    if clip.shape[0] < WIN:
        clip = np.pad(clip, (0, WIN - clip.shape[0]))
    return clip

def save(path, clip):
    sf.write(path, clip, SR, subtype="PCM_16")

# ---- collect utterances containing target, grouped by speaker ----
by_spk = collections.defaultdict(list)  # spk -> [(flac, words)]
n_total = 0
for sub in SUBSETS:
    base = os.path.join(ROOT, sub)
    for trans in glob.glob(os.path.join(base, "*", "*", "*.trans.txt")):
        d = os.path.dirname(trans)
        with open(trans, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                uid, text = line.split(" ", 1)
                words = [norm_word(w) for w in text.split()]
                words = [w for w in words if w]
                if TARGET in words:
                    spk = uid.split("-")[0]
                    by_spk[spk].append((os.path.join(d, uid + ".flac"), words))
                    n_total += 1

for spk in by_spk:
    random.shuffle(by_spk[spk])
print(f"utterances containing '{TARGET}': {n_total} across {len(by_spk)} speakers")

# ---- round-robin across speakers so aligned utts cover MAX speakers first ----
order = []
spk_lists = {s: list(v) for s, v in by_spk.items()}
spk_keys = list(spk_lists.keys())
random.shuffle(spk_keys)
while len(order) < MAX_UTTS and any(spk_lists.values()):
    for s in spk_keys:
        if spk_lists[s]:
            flac, words = spk_lists[s].pop()
            order.append((flac, s, words))
            if len(order) >= MAX_UTTS:
                break
print(f"aligning {len(order)} utterances (cap MAX_UTTS={MAX_UTTS})")

pos_count = 0
neg_pool = []          # (clip, spk, word, is_hard)
pos_speakers = set()
neg_word_ctr = collections.Counter()
per_neg_word_cap = 120

n_aligned = 0
for i, (flac, spk, words) in enumerate(order):
    if not os.path.exists(flac):
        continue
    try:
        wav = load_wav(flac)
        with torch.inference_mode():
            emission, _ = model(wav.to(device))
        token_spans = aligner(emission[0], tokenizer(words))
    except Exception:
        continue
    n_aligned += 1
    num_frames = emission.size(1)
    ratio = wav.size(1) / num_frames

    for w, spans in zip(words, token_spans):
        if not spans:
            continue
        x0 = ratio * spans[0].start
        x1 = ratio * spans[-1].end
        if w == TARGET:
            if pos_count < MAX_POS:
                clip = span_to_clip(wav, x0, x1)
                fn = os.path.join(posdir, f"spk{spk}_libri_{TARGET}_{pos_count}.wav")
                save(fn, clip)
                pos_count += 1
                pos_speakers.add(spk)
        else:
            if len(w) < 3:
                continue
            if neg_word_ctr[w] >= per_neg_word_cap:
                continue
            clip = span_to_clip(wav, x0, x1)
            neg_pool.append((clip, spk, w, hard_neg(w)))
            neg_word_ctr[w] += 1

    if (i + 1) % 100 == 0:
        print(f"  {i+1}/{len(order)} aligned={n_aligned} pos={pos_count} negpool={len(neg_pool)} posSpk={len(pos_speakers)}")

# ---- select negatives: guarantee hard-neg share + speaker/word diversity ----
random.shuffle(neg_pool)
hard = [n for n in neg_pool if n[3]]
soft = [n for n in neg_pool if not n[3]]
n_hard_target = min(len(hard), MAX_NEG // 3)
selected = hard[:n_hard_target] + soft
selected = selected[:MAX_NEG]
random.shuffle(selected)

neg_speakers = set()
neg_word_used = collections.Counter()
for j, (clip, spk, w, ish) in enumerate(selected):
    fn = os.path.join(negdir, f"neg_spk{spk}_libri_{w}_{j}.wav")
    save(fn, clip)
    neg_speakers.add(spk)
    neg_word_used[w] += 1

summary = {
    "target": TARGET,
    "subsets": SUBSETS,
    "utterances_with_target": n_total,
    "utterances_aligned": n_aligned,
    "max_utts_cap": MAX_UTTS,
    "cap_hit_utts": n_aligned >= MAX_UTTS or n_total > MAX_UTTS,
    "positives": pos_count,
    "cap_hit_pos": pos_count >= MAX_POS,
    "negatives": len(selected),
    "cap_hit_neg": len(selected) >= MAX_NEG,
    "pos_speakers": len(pos_speakers),
    "neg_speakers": len(neg_speakers),
    "all_speakers": len(pos_speakers | neg_speakers),
    "sample_rate": SR,
    "channels": 1,
    "hard_negatives_included": n_hard_target,
    "distinct_neg_words": len(neg_word_used),
    "top_neg_words": neg_word_used.most_common(15),
}
with open(os.path.join(outdir, "summary.json"), "w") as f:
    json.dump(summary, f, indent=2)
print(json.dumps(summary, indent=2))
