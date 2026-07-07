"""Generate a MODEST proof-of-concept set of wake-word clips with
ai4bharat/indic-parler-tts (CPU, slow). Idempotent, hard wall-clock deadline.

Filename grammar (parsed by tools/aura_data.py):
  positives/{accent}_{engine-voice}_tts_{slug}_{variant}.wav      -> label 1
  negatives/neg_{accent}_{engine-voice}_tts_{slug}_{variant}.wav  -> label 0
field0 = accent, field1 = engine-voice ("speaker").
"""
import os, sys, time, subprocess, io
import numpy as np
import torch

BASE = os.path.dirname(os.path.abspath(__file__))
POS_DIR = os.path.join(BASE, "output", "positives")
NEG_DIR = os.path.join(BASE, "output", "negatives")
os.makedirs(POS_DIR, exist_ok=True)
os.makedirs(NEG_DIR, exist_ok=True)

DEADLINE_S = float(os.environ.get("GEN_DEADLINE_S", "2400"))  # gen-loop budget (excl. model load)
MODEL_ID = os.environ.get("PARLER_MODEL", "parler-tts/parler-tts-mini-v1")
ENGINE = os.environ.get("PARLER_ENGINE", "parlermini")

# ---- Voices: (accent_field, voice_name, description) ----
# Names are parler-tts-mini-v1's recommended consistent speakers (reproducible timbre).
VOICES = [
    ("en-f",  "lea",   "Lea speaks in a clear, expressive female voice at a moderate pace. The recording is very high quality, with her voice sounding clean and close up with no background noise."),
    ("en-m",  "gary",  "Gary speaks in a calm, measured male voice at a moderate pace. Very high quality audio, close to the microphone with no background noise."),
    ("en-f2", "jenna", "Jenna speaks in a bright, cheerful female voice at a slightly fast pace. The audio is clear and studio quality with no noise."),
    ("en-m2", "mike",  "Mike speaks in a deep, warm and confident male voice at a moderate pace. The recording is very clean and close up with no background noise."),
]

# ---- Phrases: (label, slug, text) ----
POSITIVES = [
    ("hey-aura",  "hey aura"),
    ("hai-aura",  "hai aura"),
    ("heyy-aura", "heyy aura"),
]
HARD_NEG = [
    ("hey-dora",   "hey Dora"),
    ("hey-cora",   "hey Cora"),
    ("hey-nora",   "hey Nora"),
    ("hey-laura",  "hey Laura"),
    ("hey-aurora", "hey Aurora"),
    ("aura",       "aura"),
]
GEN_NEG = [
    ("hello",       "hello"),
    ("okay-google", "okay google"),
    ("good-morning","good morning"),
]

def build_jobs():
    """Interleave pos/neg and voices so an early cutoff still yields a spread."""
    jobs = []  # (label, accent, voice, slug, text)
    # positives: all 4 voices x 3 phrases = 12
    for slug, text in POSITIVES:
        for acc, voc, _ in VOICES:
            jobs.append((1, acc, voc, slug, text))
    # hard negatives: all 4 voices x first 3 confusables, 2 voices x rest -> keep modest
    for i, (slug, text) in enumerate(HARD_NEG):
        vs = VOICES if i < 3 else VOICES[:2]
        for acc, voc, _ in vs:
            jobs.append((0, acc, voc, slug, text))
    # generic negatives: 2 voices each
    for slug, text in GEN_NEG:
        for acc, voc, _ in VOICES[:2]:
            jobs.append((0, acc, voc, slug, text))
    # interleave pos and neg
    pos = [j for j in jobs if j[0] == 1]
    neg = [j for j in jobs if j[0] == 0]
    out, i, j = [], 0, 0
    while i < len(pos) or j < len(neg):
        if i < len(pos): out.append(pos[i]); i += 1
        if j < len(neg): out.append(neg[j]); j += 1
        if j < len(neg): out.append(neg[j]); j += 1  # ~2 neg per pos
    return out

def path_for(label, accent, voice, slug):
    fn = f"{accent}_{ENGINE}-{voice}_tts_{slug}_v0.wav"
    if label == 0:
        fn = "neg_" + fn
        return os.path.join(NEG_DIR, fn)
    return os.path.join(POS_DIR, fn)

def write_16k(audio_f32, src_sr, out_path):
    """Pipe float32 mono PCM to ffmpeg -> 16k mono s16 WAV."""
    a = np.asarray(audio_f32, dtype=np.float32).squeeze()
    peak = float(np.max(np.abs(a))) if a.size else 0.0
    if peak > 1.0:
        a = a / peak
    raw = a.tobytes()
    tmp = out_path + ".tmp.wav"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "f32le", "-ar", str(src_sr), "-ac", "1", "-i", "pipe:0",
           "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", tmp]
    p = subprocess.run(cmd, input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0 or not os.path.exists(tmp):
        sys.stderr.write("ffmpeg failed: " + p.stderr.decode("utf-8", "ignore") + "\n")
        return False
    os.replace(tmp, out_path)
    return True

def main():
    from parler_tts import ParlerTTSForConditionalGeneration
    from transformers import AutoTokenizer
    torch.set_num_threads(os.cpu_count() or 4)
    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] loading model {MODEL_ID} ...", flush=True)
    model = ParlerTTSForConditionalGeneration.from_pretrained(MODEL_ID)
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    desc_tok = AutoTokenizer.from_pretrained(model.config.text_encoder._name_or_path)
    model.eval()
    sr = model.config.sampling_rate
    print(f"[{time.strftime('%H:%M:%S')}] model loaded in {time.time()-t0:.0f}s, sr={sr}", flush=True)

    desc_map = {voc: desc for _, voc, desc in VOICES}
    jobs = build_jobs()
    print(f"planned {len(jobs)} jobs; deadline {DEADLINE_S:.0f}s", flush=True)

    made_pos = made_neg = skipped = failed = 0
    loop_start = time.time()
    for k, (label, accent, voice, slug, text) in enumerate(jobs):
        out_path = path_for(label, accent, voice, slug)
        if os.path.exists(out_path):
            skipped += 1
            continue
        if time.time() - loop_start > DEADLINE_S:
            print(f"[{time.strftime('%H:%M:%S')}] DEADLINE reached after {k} jobs; stopping cleanly", flush=True)
            break
        desc = desc_map[voice]
        try:
            d = desc_tok(desc, return_tensors="pt")
            p = tok(text, return_tensors="pt")
            ts = time.time()
            with torch.no_grad():
                gen = model.generate(
                    input_ids=d.input_ids, attention_mask=d.attention_mask,
                    prompt_input_ids=p.input_ids, prompt_attention_mask=p.attention_mask,
                    do_sample=True, temperature=1.0)
            audio = gen.cpu().numpy().squeeze()
            ok = write_16k(audio, sr, out_path)
            dt = time.time() - ts
            if ok:
                if label == 1: made_pos += 1
                else: made_neg += 1
                print(f"[{time.strftime('%H:%M:%S')}] ({k+1}/{len(jobs)}) {os.path.basename(out_path)} {dt:.0f}s", flush=True)
            else:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"ERROR on {slug}/{voice}: {e}", flush=True)

    print(f"DONE pos_made={made_pos} neg_made={made_neg} skipped={skipped} failed={failed} "
          f"elapsed={time.time()-t0:.0f}s", flush=True)

if __name__ == "__main__":
    main()
