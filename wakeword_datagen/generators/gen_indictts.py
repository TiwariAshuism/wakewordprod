#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI4Bharat Indic-TTS (MIT) wake-word generator -- the KEY Indian-accent engine.

Renders the "hey aura" phrase set through AI4Bharat's FastPitch + HiFi-GAN release
checkpoints (github.com/AI4Bharat/Indic-TTS, v1-checkpoints-release) to get
INDIAN-ACCENTED and Indian-language renderings. Our users are Indian, so this is the
most important accent source.

Two rendering paths:
  * `en`  model  -> Indian-accented ENGLISH. English text is fed verbatim; the model was
                    trained on Indian English speakers, so "hey aura" comes out accented.
  * `hi/ta/te/bn/mr/kn` monolingual models -> Indian-LANGUAGE renderings. These models only
                    accept their native script, so English phrases are transliterated to the
                    script with aksharamukha ('RomanReadable' -> native) before synthesis.
                    A few genuine native-script generic negatives are also rendered.

IMPORTANT (isolation): this runs ONLY inside the isolated venv
  wakeword_datagen/venvs/indictts  (coqui TTS 0.22 + torch-cpu),
never the repo's main env. Invoke it with that venv's python:
  venvs/indictts/Scripts/python.exe generators/gen_indictts.py

Output: 16 kHz mono s16 WAV into output/{positives,negatives} via genlib naming, so
tools/aura_data.py parses accent=field0, speaker=field1. Idempotent (skips existing).
A missing/failed model (download not finished, load error, OOV text) is logged and skipped;
the script degrades gracefully and never hangs.

Filename fields:
  accent (field0): 'in-en' for the English model, else the language code (hi/ta/...).
  speaker (field1): 'indictts-<voice>'  (voice = male/female).
  variant: 's<pct>'  speed variant produced with ffmpeg atempo.
"""
import argparse
import json
import os
import sys
import tempfile
import traceback

import numpy as np
import soundfile as sf

# coqui TTS prints the (native-script) tokenized text during .tts(); force UTF-8 stdio so
# that internal print() does not raise UnicodeEncodeError on the Windows cp1252 console.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import genlib  # noqa: E402

ENGINE = "indictts"
HERE = os.path.dirname(os.path.abspath(__file__))
CKPT_ROOT = os.path.join(HERE, "..", "models", "indictts", "checkpoints")

# Desired languages in priority order. en first (guaranteed value), then the 6 Indic langs
# the task asks for. Only those whose checkpoint dir actually exists are used.
DESIRED_LANGS = ["en", "hi", "ta", "te", "bn", "mr", "kn"]
SPEAKERS = ["male", "female"]
SPEEDS = [0.9, 1.0, 1.1]

# aksharamukha target script per language (for romanized-English -> native transliteration).
SCRIPT = {
    "hi": "Devanagari", "mr": "Devanagari", "bn": "Bengali",
    "ta": "Tamil", "te": "Telugu", "kn": "Kannada",
}

# A few GENUINE Indian-language generic negatives (common words), given in roman and
# transliterated to each script -> real native-language speech that is NOT the wake word.
NATIVE_NEG_ROMAN = ["namaste", "dhanyavaad", "shukriya", "theek hai", "accha", "kaise ho"]


def available_langs():
    langs = []
    for lang in DESIRED_LANGS:
        d = os.path.join(CKPT_ROOT, lang, "fastpitch", "best_model.pth")
        v = os.path.join(CKPT_ROOT, lang, "hifigan", "best_model.pth")
        if os.path.exists(d) and os.path.exists(v):
            langs.append(lang)
    return langs


def patch_config(lang):
    """AI4Bharat configs bake in a wrong relative speakers_file path; rewrite to absolute."""
    base = os.path.abspath(os.path.join(CKPT_ROOT, lang, "fastpitch"))
    cfgp = os.path.join(base, "config.json")
    spk = os.path.join(base, "speakers.pth")
    c = json.load(open(cfgp, encoding="utf-8"))
    if os.path.exists(spk):
        c["speakers_file"] = spk
        c.setdefault("model_args", {})["speakers_file"] = spk
    for k in ("speaker_encoder_config_path", "speaker_encoder_model_path"):
        if "model_args" in c:
            c["model_args"][k] = ""
    json.dump(c, open(cfgp, "w", encoding="utf-8"))


def load_model(lang):
    from TTS.utils.synthesizer import Synthesizer
    base = os.path.abspath(os.path.join(CKPT_ROOT, lang))
    spk = os.path.join(base, "fastpitch", "speakers.pth")
    return Synthesizer(
        tts_checkpoint=os.path.join(base, "fastpitch", "best_model.pth"),
        tts_config_path=os.path.join(base, "fastpitch", "config.json"),
        tts_speakers_file=spk if os.path.exists(spk) else None,
        tts_languages_file=None,
        vocoder_checkpoint=os.path.join(base, "hifigan", "best_model.pth"),
        vocoder_config=os.path.join(base, "hifigan", "config.json"),
        encoder_checkpoint="", encoder_config="", use_cuda=False,
    )


def model_speakers(model):
    try:
        return list(model.tts_model.speaker_manager.name_to_id.keys())
    except Exception:
        return []


_XLIT = None


def translit(text, lang):
    """Romanized English -> native script for a monolingual Indic model."""
    global _XLIT
    if _XLIT is None:
        from aksharamukha import transliterate as ak
        _XLIT = ak
    out = _XLIT.process("RomanReadable", SCRIPT[lang], text)
    # Drop Grantha superscript aspiration digits Tamil adds (OOV for the TTS vocab).
    for ch in ("²", "³", "⁴"):
        out = out.replace(ch, "")
    return out.strip()


def synth_base(model, text, speaker):
    """Return float32 mono waveform at model.output_sample_rate, or None on failure."""
    wav = model.tts(text, speaker_name=speaker, style_wav="")
    wav = np.asarray(wav, dtype=np.float32)
    if wav.size < 400:
        return None
    return wav


def write_variants(base_wav, sr, accent, voice, phrase_slug, negative, made_ref):
    """Write all speed variants of one base waveform (idempotent). Returns (made, skipped)."""
    made = skipped = 0
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        sf.write(tmp, base_wav, sr, subtype="PCM_16")
        for spd in SPEEDS:
            variant = f"s{int(round(spd * 100))}"
            out = genlib.out_path(accent, ENGINE, voice, phrase_slug, variant, negative)
            if os.path.exists(out):
                skipped += 1
                continue
            ok = (genlib.ffmpeg_to_16k(tmp, out) if abs(spd - 1.0) < 1e-6
                  else genlib.ffmpeg_atempo(tmp, out, spd))
            if ok:
                made += 1
            # else: silently dropped (ffmpeg failure logged by counting as neither)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return made, skipped


def generate(limit=None):
    genlib.ensure_dirs()
    langs = available_langs()
    if not langs:
        return {"engine": ENGINE, "available": False, "made": 0, "skipped": 0,
                "reason": "no checkpoints found (downloads unfinished?)", "langs": []}
    p = genlib.load_phrases()
    positives = list(p["positives"])
    negatives = genlib.neg_phrases(p)  # hard_negatives + generic_negatives

    report = {"engine": ENGINE, "available": True, "langs": [], "made": 0,
              "skipped": 0, "failed": 0, "pos": 0, "neg": 0}
    total_new = 0

    for lang in langs:
        is_en = (lang == "en")
        accent = "in-en" if is_en else lang
        try:
            patch_config(lang)
            model = load_model(lang)
        except Exception as e:
            report["langs"].append({"lang": lang, "status": f"load-failed: {str(e)[:80]}"})
            print(f"[indictts] {lang}: LOAD FAILED: {e}")
            traceback.print_exc()
            continue
        sr = model.output_sample_rate
        spk_avail = set(model_speakers(model))
        voices = [s for s in SPEAKERS if s in spk_avail] or (list(spk_avail)[:2])
        lmade = lskip = lfail = 0

        # Build job list: (negative, phrase_english_for_slug, text_to_synth)
        jobs = []
        for ph in positives:
            jobs.append((False, ph, ph if is_en else None))
        for ph in negatives:
            jobs.append((True, ph, ph if is_en else None))
        if not is_en:
            # genuine native-script generic negatives
            for ph in NATIVE_NEG_ROMAN:
                jobs.append((True, ph, None))

        for negative, ph_slug, en_text in jobs:
            if limit and total_new >= limit:
                break
            # resolve synth text
            try:
                text = en_text if en_text is not None else translit(ph_slug, lang)
            except Exception as e:
                lfail += 1
                print(f"[indictts] {lang}: translit failed '{ph_slug}': {e}")
                continue
            if not text:
                lfail += 1
                continue
            for voice in voices:
                if limit and total_new >= limit:
                    break
                # quick idempotency check: if all speed variants exist, skip synth entirely
                need = [s for s in SPEEDS
                        if not os.path.exists(genlib.out_path(
                            accent, ENGINE, voice, ph_slug, f"s{int(round(s*100))}", negative))]
                if not need:
                    lskip += len(SPEEDS)
                    continue
                try:
                    base = synth_base(model, text, voice)
                except Exception as e:
                    lfail += 1
                    print(f"[indictts] {lang}/{voice}: synth failed '{ph_slug}': {str(e)[:80]}")
                    continue
                if base is None:
                    lfail += 1
                    continue
                m, s = write_variants(base, sr, accent, voice, ph_slug, negative, None)
                lmade += m
                lskip += s
                total_new += m
                if negative:
                    report["neg"] += m
                else:
                    report["pos"] += m
        del model
        report["made"] += lmade
        report["skipped"] += lskip
        report["failed"] += lfail
        report["langs"].append({"lang": lang, "accent": accent, "voices": voices,
                                 "made": lmade, "skipped": lskip, "failed": lfail})
        print(f"[indictts] {lang} ({accent}) voices={voices} made={lmade} "
              f"skipped={lskip} failed={lfail}")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="cap NEW clips this run")
    args = ap.parse_args()
    rep = generate(limit=args.limit)
    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
