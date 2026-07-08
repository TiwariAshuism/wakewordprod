import os, re, sys, glob, json, random, collections
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
SUBSETS = sys.argv[2].split(",") if len(sys.argv) > 2 else ["dev-clean"]
MAX_POS = int(sys.argv[3]) if len(sys.argv) > 3 else 800
MAX_NEG = int(sys.argv[4]) if len(sys.argv) > 4 else 2400
MAX_UTTS = int(sys.argv[5]) if len(sys.argv) > 5 else 100000  # cap aligned utterances

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

# collect utterances that contain the target word
utts = []  # (flac_path, spk, [orig words], text)
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
                    utts.append((os.path.join(d, uid + ".flac"), spk, words))

random.shuffle(utts)
print(f"utterances containing '{TARGET}': {len(utts)} (across {len(set(u[1] for u in utts))} speakers)")

def hard_neg(w):
    # phoneme/rhyme overlap with "little" /'lIt.@l/:
    #   - contains lit / itt / ttl / tle  (core rime cluster)
    #   - /l/ onset + high-front vowel: starts 'li'
    #   - syllabic-/l/ coda: ends 'le' (table, gentle, people, uncle...)
    #   - geminate t/l: contains 'tt' or 'll'
    if w == TARGET or len(w) < 3:
        return False
    if any(s in w for s in ("lit", "itt", "ttl", "tle")):
        return True
    if w.startswith("li"):
        return True
    if len(w) >= 4 and w.endswith("le"):
        return True
    if "tt" in w or "ll" in w:
        return True
    return False

def load_wav(path):
    data, sr = sf.read(path, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    wav = torch.from_numpy(data).unsqueeze(0)  # [1, T]
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

pos_count = 0
neg_pool = []  # (clip, spk, word, is_hard)
pos_speakers = set()
neg_word_ctr = collections.Counter()
per_neg_word_cap = 60  # limit repeats of any single negative word for diversity

n_aligned = 0
for i, (flac, spk, words) in enumerate(utts):
    if pos_count >= MAX_POS and len(neg_pool) >= MAX_NEG * 3:
        break
    if n_aligned >= MAX_UTTS:
        break
    if not os.path.exists(flac):
        continue
    try:
        wav = load_wav(flac)
        with torch.inference_mode():
            emission, _ = model(wav.to(device))
        token_spans = aligner(emission[0], tokenizer(words))
    except Exception as e:
        continue
    n_aligned += 1
    num_frames = emission.size(1)
    ratio = wav.size(1) / num_frames

    for wi, (w, spans) in enumerate(zip(words, token_spans)):
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
                continue  # skip tiny stopwords for clearer negatives
            if neg_word_ctr[w] >= per_neg_word_cap:
                continue
            clip = span_to_clip(wav, x0, x1)
            neg_pool.append((clip, spk, w, hard_neg(w)))
            neg_word_ctr[w] += 1

    if (i + 1) % 50 == 0:
        print(f"  processed {i+1}/{len(utts)} aligned={n_aligned} pos={pos_count} negpool={len(neg_pool)}")

# select negatives: prioritize hard negatives + diversity across speakers/words
random.shuffle(neg_pool)
hard = [n for n in neg_pool if n[3]]
soft = [n for n in neg_pool if not n[3]]
selected = hard[:MAX_NEG // 3] + soft
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
    "utterances_with_target": len(utts),
    "utterances_aligned": n_aligned,
    "positives": pos_count,
    "negatives": len(selected),
    "pos_speakers": len(pos_speakers),
    "neg_speakers": len(neg_speakers),
    "all_speakers": len(pos_speakers | neg_speakers),
    "sample_rate": SR,
    "channels": 1,
    "hard_negatives_included": len(hard[:MAX_NEG // 3]),
    "distinct_neg_words": len(neg_word_used),
    "top_neg_words": neg_word_used.most_common(15),
}
with open(os.path.join(outdir, "summary.json"), "w") as f:
    json.dump(summary, f, indent=2)
print(json.dumps(summary, indent=2))
