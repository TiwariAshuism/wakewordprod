#!/usr/bin/env python3
"""Generate a CycloneDX-lite SBOM (Stage 7 §15/§18 supply-chain requirement / gap-analysis
§5). Enumerates AURA's third-party components with pinned versions from
gradle/libs.versions.toml + tools/versions.txt and known licenses. Emitted per CI run.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")


def load_catalog():
    try:
        import tomllib
    except ImportError:  # py<3.11
        return {}
    path = os.path.join(ROOT, "gradle", "libs.versions.toml")
    with open(path, "rb") as f:
        return tomllib.load(f).get("versions", {})


def load_versions_txt():
    out = {}
    path = os.path.join(ROOT, "tools", "versions.txt")
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


# name -> (kind, license, purl-group). Version filled from catalogs where available.
KNOWN = {
    "onnxruntime-android": ("native-runtime", "MIT", "pkg:maven/com.microsoft.onnxruntime"),
    "oboe": ("native-audio", "Apache-2.0", "pkg:maven/com.google.oboe"),
    "kotlinx-coroutines": ("library", "Apache-2.0", "pkg:maven/org.jetbrains.kotlinx"),
    "androidx-core-ktx": ("library", "Apache-2.0", "pkg:maven/androidx.core"),
    "GoogleTest": ("test", "BSD-3-Clause", "pkg:github/google/googletest"),
    "Silero-VAD": ("model", "MIT", "pkg:github/snakers4/silero-vad"),
    "KissFFT(placeholder: core/features/Fft.h)": ("dsp", "BSD-3-Clause", "n/a"),
    "SpeechCommands-v2": ("dataset", "CC-BY-4.0", "pkg:other/speech_commands_v0.02"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "sbom.json"))
    args = ap.parse_args()

    cat = load_catalog()
    ver = load_versions_txt()

    components = []

    def add(name, version, kind, lic, purl):
        components.append({
            "type": "library" if kind in ("library", "test", "dsp") else "application",
            "name": name, "version": version or "unpinned", "kind": kind,
            "licenses": [{"license": {"id": lic}}], "purl": purl,
        })

    # native + libraries from the Gradle catalog
    add("com.microsoft.onnxruntime:onnxruntime-android", cat.get("onnxruntime"),
        *KNOWN["onnxruntime-android"])
    add("com.google.oboe:oboe", cat.get("oboe"), *KNOWN["oboe"])
    add("org.jetbrains.kotlinx:kotlinx-coroutines", cat.get("coroutines"),
        *KNOWN["kotlinx-coroutines"])
    add("androidx.core:core-ktx", cat.get("coreKtx"), *KNOWN["androidx-core-ktx"])
    add("googletest", ver.get("GOOGLETEST"), *KNOWN["GoogleTest"])
    # vendored / bundled
    add("silero-vad (silero_vad.onnx)", "master", *KNOWN["Silero-VAD"])
    add("fft (self-contained radix-2, placeholder for KissFFT)", "n/a",
        *KNOWN["KissFFT(placeholder: core/features/Fft.h)"])
    # data + placeholder model
    add("Google Speech Commands v2 (placeholder training data)", "v0.02",
        *KNOWN["SpeechCommands-v2"])

    # toolchain (for reproducibility, not shipped)
    toolchain = {k: ver.get(k) for k in ("JDK", "GRADLE", "AGP", "KOTLIN", "NDK", "CMAKE")}

    sbom = {
        "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
        "metadata": {
            "component": {"type": "application", "name": "aura", "version": "0.1.0"},
            "toolchain": toolchain,
            "note": "SBOM is generated from gradle/libs.versions.toml + tools/versions.txt. "
                    "Oboe + ONNX Runtime are consumed as pinned Prefab AARs (not vendored). "
                    "The KWS model is a PLACEHOLDER trained on Speech Commands, not shipped.",
        },
        "components": components,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(sbom, f, indent=2)
    print(f"wrote {args.out} ({len(components)} components)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
