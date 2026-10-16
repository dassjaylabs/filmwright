"""Design the bundled narrator voices (voice.type: library) with Qwen3-TTS VoiceDesign.

    python scripts/build_voice_library.py                # re-render every voice from its stored seed
    python scripts/build_voice_library.py --search 6     # try seeds 1-6 per voice and keep the most natural
    python scripts/build_voice_library.py --only nora

Each voice in src/filmwright/assets/voices/library.json has a description. This renders it into a short reference
clip (the clip every film then clones), checks the clip and a few test lines with the read-back and pace checks,
and stores the clip, its seed and its SHA-256. Needs Apple Silicon with `filmwright setup --voice described`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from filmwright.core.voice import qwen as Q  # noqa: E402
from filmwright.core.voice.library import LIBRARY_DIR, MANIFEST, REF_TEXT  # noqa: E402

TEST_LINES = [
    "Meet the new dashboard. Everything your team needs is on one screen.",
    "Click New Task, give it a name, and pick who it's for.",
    "It takes about a minute to set up, and it's free to try.",
]
TARGET = 1.0          # spoken length / speech_seconds(): 1.0 is the expected normal pace


def wav_pace(path: Path, text: str) -> float:
    import wave

    import numpy as np
    with wave.open(str(path)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32767
        rate = w.getframerate()
    return Q.spoken_seconds(x, rate) / Q.speech_seconds(text)


def trial(desc: str, seed: int, work: Path) -> tuple[float, Path]:
    """Design the voice with `seed`; return (badness, reference clip). Lower badness is better."""
    v = Q.QwenVoice("design", instruct=desc, seed=seed, cache=work / f"cache-{seed}", log=lambda *a: None)
    v._designed_reference()
    ref = Path(v.ref_audio)
    paces = []
    for i, line in enumerate(TEST_LINES):
        out = work / f"s{seed}-{i}.wav"
        v.say(line, out)
        paces.append(wav_pace(out, line))
    failed = len(v.report) + len(v.slow)
    v.close()
    badness = failed * 10 + sum(abs(p - TARGET) for p in paces) / len(paces)
    print(f"    seed {seed}: paces {', '.join(f'{p:.2f}' for p in paces)}, failed lines {failed} -> {badness:.2f}", flush=True)
    return badness, ref


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--search", type=int, default=0, help="try seeds 1..N per voice and keep the best")
    ap.add_argument("--only", help="comma-separated voice names")
    a = ap.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    only = set(a.only.split(",")) if a.only else None
    with tempfile.TemporaryDirectory(prefix="filmwright-library-") as tmp:
        for name, v in manifest["voices"].items():
            if only and name not in only:
                continue
            print(f"{name}: {v['description']}", flush=True)
            seeds = range(1, a.search + 1) if a.search else [int(v["seed"])]
            results = [(*trial(v["description"], s, Path(tmp)), s) for s in seeds]
            badness, ref, seed = min(results, key=lambda r: r[0])
            dest = LIBRARY_DIR / f"{name}.wav"
            shutil.copyfile(ref, dest)
            v.update(seed=seed, sha256=Q.sha256(dest), seconds=round(Q.wav_seconds(dest), 2))
            print(f"  kept seed {seed} ({badness:.2f}) -> {dest.relative_to(ROOT)}", flush=True)
    manifest["text"] = REF_TEXT
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
