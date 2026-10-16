"""Soft sound effects, synthesised (no samples, nothing to license): a click for clicks, a whoosh for zooms, a chime
for success toasts, a pop for labels appearing, a tick for counters, a swish for light transitions, a riser and an
impact for scene changes, and a short sting in and out. Pipelines place them with sfx_track() on a track that
sits well under the narration (about 25 dB for a walkthrough).

    python -m filmwright.core.sfx out.wav whoosh       # render one sound to listen to
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

RATE = 48000


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / RATE
    return np.minimum(t / max(attack, 1e-4), 1.0) * np.exp(-t / decay)


def click() -> np.ndarray:
    n = int(0.09 * RATE)
    noise = np.random.default_rng(1).normal(size=n)
    # a short, bright tick: noise through a crude high-pass (difference) with a fast decay
    hp = np.diff(noise, prepend=0.0)
    return 0.6 * hp / np.abs(hp).max() * _env(n, 0.001, 0.012)


def whoosh() -> np.ndarray:
    n = int(0.55 * RATE)
    noise = np.random.default_rng(2).normal(size=n)
    # smooth the noise more over time: a sweep from bright to dark, with a soft swell
    out = np.zeros(n)
    acc = 0.0
    for i in range(n):
        k = 0.02 + 0.3 * (i / n)
        acc += (noise[i] - acc) * (1 - k)
        out[i] = acc
    t = np.arange(n) / RATE
    swell = np.sin(np.pi * np.minimum(t / 0.55, 1.0)) ** 2
    return 0.5 * out / np.abs(out).max() * swell


def chime() -> np.ndarray:
    n = int(1.2 * RATE)
    t = np.arange(n) / RATE
    tone = np.zeros(n)
    for f, delay in ((659.25, 0.0), (987.77, 0.11)):   # E5 then B5
        tt = np.clip(t - delay, 0, None)
        tone += (np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(4 * np.pi * f * tt)) * np.exp(-tt / 0.45) * (t >= delay)
    return 0.35 * tone / np.abs(tone).max()


def _bell(f: float, dur: float, amp: float = 1.0) -> np.ndarray:
    n = int(dur * RATE)
    t = np.arange(n) / RATE
    tone = (np.sin(2 * np.pi * f * t) * np.exp(-t / 0.5) + 0.35 * np.sin(2 * np.pi * 2.01 * f * t) * np.exp(-t / 0.3)
            + 0.12 * np.sin(2 * np.pi * 3.99 * f * t) * np.exp(-t / 0.18))
    return amp * tone * np.minimum(t / 0.004, 1.0)


def _place(notes: list[tuple[float, float, float]], seconds: float) -> np.ndarray:
    out = np.zeros(int(seconds * RATE))
    for f, at, amp in notes:
        b = _bell(f, seconds - at, amp)
        i = int(at * RATE)
        out[i:i + len(b)] += b[:len(out) - i]
    return out / np.abs(out).max()


def jingle_in() -> np.ndarray:
    """A short brand sting: a bright rising C major arpeggio over a soft pad. About 1.8 s."""
    n = int(1.8 * RATE)
    t = np.arange(n) / RATE
    pad = 0.18 * (np.sin(2 * np.pi * 196.0 * t) + 0.5 * np.sin(2 * np.pi * 293.66 * t)) * np.exp(-t / 0.9) * np.minimum(t / 0.15, 1.0)
    notes = _place([(523.25, 0.0, 0.8), (659.25, 0.12, 0.8), (783.99, 0.24, 0.8), (1046.5, 0.38, 1.0)], 1.8)
    return 0.45 * (0.8 * notes + pad / max(np.abs(pad).max(), 1e-6) * 0.35)


def jingle_out() -> np.ndarray:
    """The matching sign-off: three falling notes, then a resolved chord. About 2.2 s."""
    notes = _place([(783.99, 0.0, 0.8), (659.25, 0.14, 0.8), (523.25, 0.28, 0.8),
                    (523.25, 0.55, 0.7), (659.25, 0.55, 0.7), (783.99, 0.55, 0.7)], 2.2)
    return 0.45 * notes


def sparkle() -> np.ndarray:
    """Three quick high bells: the moment the pattern lights up."""
    return 0.4 * _place([(1318.5, 0.0, 0.7), (1975.5, 0.07, 0.7), (1568.0, 0.14, 0.8)], 1.2)


def _fade_out(x: np.ndarray, seconds: float) -> np.ndarray:
    """Raised-cosine fade to exactly zero over the last `seconds`, so a sound never ends on a click."""
    m = min(len(x), max(2, int(seconds * RATE)))
    x[-m:] *= 0.5 * (1 + np.cos(np.pi * np.arange(m) / (m - 1)))
    return x


def pop() -> np.ndarray:
    """A soft, rounded pop with a quick pitch drop: a label or callout appearing. About 0.12 s."""
    n = int(0.12 * RATE)
    t = np.arange(n) / RATE
    freq = 200.0 + 460.0 * np.exp(-t / 0.022)            # ~660 Hz falling to ~200 Hz in the first ~60 ms
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    tone = np.sin(phase) + 0.18 * np.sin(2 * phase)      # a little second harmonic keeps it round, not a beep
    out = tone * _env(n, 0.003, 0.035)
    out = _fade_out(out, 0.02)
    return 0.35 * out / np.abs(out).max()


def tick() -> np.ndarray:
    """A very quiet, bright tick for counters. About 0.04 s; quiet through its brevity, not a low peak."""
    n = int(0.04 * RATE)
    t = np.arange(n) / RATE
    tone = sum(a * np.sin(2 * np.pi * f * t) for f, a in ((3100.0, 1.0), (4700.0, 0.6), (6900.0, 0.35)))
    out = tone * _env(n, 0.0004, 0.0045)
    out = _fade_out(out, 0.008)
    return 0.3 * out / np.abs(out).max()


def swish() -> np.ndarray:
    """A soft, airy transition: band-passed noise whose centre rises while it swells and fades. About 0.35 s,
    shorter and quieter than the whoosh."""
    n = int(0.35 * RATE)
    noise = np.random.default_rng(4).normal(size=n)
    t = np.arange(n) / RATE
    centre = 1000.0 + 2800.0 * (t / 0.35) ** 1.5           # sweep up from ~1 kHz to ~3.8 kHz
    f = 2 * np.sin(np.pi * centre / RATE)                  # state-variable band-pass, damping 0.5: broad but not hissy
    out = np.zeros(n)
    low = band = 0.0
    for i in range(n):
        low += f[i] * band
        high = noise[i] - low - 0.5 * band
        band += f[i] * high
        out[i] = band
    swell = np.sin(np.pi * t / 0.35) ** 2
    out = _fade_out(out * swell, 0.03)
    return 0.3 * out / np.abs(out).max()


def riser() -> np.ndarray:
    """Noise and a rising sweep that build over about 0.9 s into a scene change."""
    n = int(0.9 * RATE)
    t = np.arange(n) / RATE
    noise = np.diff(np.random.default_rng(5).normal(size=n), prepend=0.0)
    sweep = np.sin(2 * np.pi * np.cumsum(300 + 1700 * (t / t[-1]) ** 2) / RATE)
    out = (noise * 0.35 + sweep * 0.12) * (t / t[-1]) ** 2.2
    return 0.45 * out / np.abs(out).max()


def impact() -> np.ndarray:
    """A low boom with a soft crash: lands on a cut. About 1.6 s."""
    n = int(1.6 * RATE)
    t = np.arange(n) / RATE
    boom = np.sin(2 * np.pi * np.cumsum(38 + 50 * np.exp(-t * 12)) / RATE) * np.exp(-t * 4) * 0.7
    crash = np.diff(np.random.default_rng(6).normal(size=n), prepend=0.0) * np.exp(-t * 2.6) * 0.16
    out = _fade_out(boom + crash, 0.05)
    return 0.5 * out / np.abs(out).max()


# `sound_effects` in reel.yaml: which sounds a film gets. "subtle" (the default) keeps the quiet interface sounds and
# drops the transition sounds (whoosh, swish, riser, impact), which compete with the narration.
TRANSITION_SOUNDS = frozenset({"whoosh", "swish", "riser", "impact"})
EFFECT_SETS = ("subtle", "full", "off")


def allowed(name: str, sounds: str = "subtle") -> bool:
    """Whether a cue named `name` plays under the `sounds` setting."""
    if sounds == "off":
        return False
    return sounds == "full" or name not in TRANSITION_SOUNDS


SOUNDS = {"click": click, "riser": riser, "impact": impact, "whoosh": whoosh, "chime": chime, "jingle_in": jingle_in, "jingle_out": jingle_out, "sparkle": sparkle,
          "pop": pop, "tick": tick, "swish": swish}


def sfx_track(cues: list[tuple[float, str]], seconds: float, out_wav: Path, level: float = 0.5,
              sounds: str = "subtle") -> Path:
    """Place sounds at times (seconds) on a stereo track of `seconds`; returns the WAV path. `sounds` is the
    reel's `sound_effects` setting: "subtle" leaves out the transition sounds, "off" leaves out everything."""
    n = int(seconds * RATE) + RATE
    mix = np.zeros(n)
    cache = {}
    for t, name in cues:
        if name not in SOUNDS or t < 0 or not allowed(name, sounds):
            continue
        s = cache.setdefault(name, SOUNDS[name]())
        i = int(t * RATE)
        m = min(len(s), n - i)
        if m > 0:
            mix[i:i + m] += s[:m]
    mix = np.clip(mix * level, -1, 1)
    stereo = np.stack([mix, mix], axis=1)
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((stereo * 32767).astype("<i2").tobytes())
    return out_wav


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m filmwright.core.sfx")
    ap.add_argument("out", type=Path)
    ap.add_argument("sound", choices=list(SOUNDS))
    a = ap.parse_args(argv)
    seconds = len(SOUNDS[a.sound]()) / RATE + 0.2
    print(sfx_track([(0.1, a.sound)], seconds, a.out, sounds="full"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
