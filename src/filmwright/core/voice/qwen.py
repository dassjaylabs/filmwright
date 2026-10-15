"""Neural narration with Qwen3-TTS on Apple Silicon (MLX). Three ways to pick the voice:

  custom  one of the model's preset speakers (ryan, aiden, serena, ...), with an optional style
          instruction. This is what `voice.type: preset` uses (default speaker "ryan").
  design  a voice described in words ("warm, clear narrator in her thirties"): `voice.type: described`.
  clone   a voice cloned from a consented sample: `voice.type: clone`. It refuses to run without a valid
          consent record for the sample (see consent.py).

How generation works:
- Each sentence is generated separately and seeded, so a re-render sounds the same.
- Every sentence gets a length sanity check.
- With verify on, Whisper reads each sentence back.
- A garbled, truncated, runaway or drawn-out sentence (spoken much slower than normal speech) is regenerated
  with the next seed, up to three tries, and the best attempt is kept. Sentences that never read back cleanly,
  or stayed drawn out, are listed by close().
- Results are cached per sentence group, so re-building after a small text edit costs little.
- Design mode renders the description once into a reference clip, then clones that clip for every sentence.
  Generating each sentence from the description would give a slightly different voice each time.
"""

from __future__ import annotations

import difflib
import gc
import hashlib
import json
import os
import platform
import re
import shutil
import tempfile
import time
import unicodedata
import wave
from pathlib import Path
from typing import Any

from filmwright.paths import cache_dir

from .consent import verify_consent

MODELS = {
    "clone": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16",
    "design": "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16",
    "custom": "mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-bf16",
}
WHISPER = "mlx-community/whisper-large-v3-turbo-asr-fp16"   # the plain -turbo repo has no processor
WHISPER_LANG = {"english": "en", "chinese": "zh", "japanese": "ja", "korean": "ko", "german": "de",
                "french": "fr", "spanish": "es", "italian": "it", "portuguese": "pt", "russian": "ru"}
SENTENCE_GAP = 0.28         # seconds of silence between sentences
MIN_SCORE = 0.8             # read-back similarity below which a sentence is regenerated
ATTEMPTS = 3
MAX_PACE = 1.25            # spoken length / speech_seconds() above which a take counts as drawn out
DESIGN_REF_TEXT = ("Hi there. In this short walkthrough, I'll show you what changed, why it matters, "
                   "and how it looks on screen. It only takes a few minutes, so let's get started.")
DEFAULT_SPEAKER = "ryan"     # native-English male preset
DEFAULT_STYLE = ("Natural, relaxed and conversational, like a friendly colleague explaining something. "
                 "Even pace, no dramatic emphasis.")
DEFAULT_TEMPERATURE = 0.65   # lower = flatter, steadier delivery
PRESET_SPEAKERS = ("ryan", "aiden", "serena", "vivian", "dylan", "eric", "uncle_fu", "ono_anna", "sohee")


class VoiceUnavailable(RuntimeError):
    """The neural voice can't run on this machine (not Apple Silicon, or mlx-audio missing)."""


def mlx_status() -> str | None:
    """None when Qwen3-TTS can run here, else the reason it can't."""
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return "the neural voices run on MLX, which needs an Apple Silicon Mac"
    try:
        import mlx_audio  # noqa: F401
    except ImportError:
        return "mlx-audio isn't installed (run: filmwright setup --voice preset)"
    return None


def require_mlx() -> None:
    reason = mlx_status()
    if reason:
        raise VoiceUnavailable(reason)


def free_memory() -> None:
    gc.collect()
    try:
        import mlx.core as mx
        (getattr(mx, "clear_cache", None) or mx.metal.clear_cache)()
    except Exception:
        pass


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?:])\s+", text.strip()) if s.strip()]


def words(text: str) -> list[str]:
    """Lower-cased words of any script, for comparing a line with what Whisper heard. Letters and digits are kept;
    punctuation, symbols and accent marks are not ("crème" and "creme" compare equal)."""
    text = unicodedata.normalize("NFKD", text).casefold().replace("-", " ")
    return "".join(c if unicodedata.category(c)[0] in "LN" or c in "' " else "" if unicodedata.category(c) == "Mn"
                   else " " for c in text).split()


# Scripts written without spaces between words: their length is counted in characters, not words.
_UNSPACED = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f]")


def speech_seconds(text: str) -> float:
    """A rough spoken length: about 155 words a minute, or 6 characters a second for Chinese and Japanese."""
    unspaced = len(_UNSPACED.findall(text))
    return max(1.0, len(words(_UNSPACED.sub(" ", text))) / 2.6 + unspaced / 6.0)


def spoken_seconds(audio: Any, rate: int) -> float:
    """Length from the first to the last sound, leaving out leading and trailing silence (10 ms windows quieter
    than 2% of the loudest)."""
    import numpy as np
    x = np.asarray(audio, dtype=np.float32)
    win = max(1, rate // 100)
    k = len(x) // win
    if k == 0:
        return 0.0
    env = np.sqrt(np.mean(x[:k * win].reshape(k, win) ** 2, axis=1))
    loud = np.flatnonzero(env > 0.02 * env.max()) if env.max() > 0 else []
    return (loud[-1] - loud[0] + 1) * win / rate if len(loud) else 0.0


def match_score(expected: str, heard: str) -> float:
    """Character-level similarity with spaces removed. Word-level scoring over-penalises short sentences:
    a product name heard as two words would cost a six-word sentence a quarter of its score.
    A line with nothing comparable left (or nothing heard) scores 0, never a free 1.0."""
    a, b = "".join(words(expected)), "".join(words(heard))
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def write_wav(path: Path, audio: Any, rate: int) -> None:
    import numpy as np
    pcm = (np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Transcriber:
    """Whisper on MLX, loaded on first use."""

    def __init__(self, language: str | None = "en"):   # None = let Whisper detect it
        self.language = language
        self.model = None

    def __call__(self, wav: Path) -> str:
        if self.model is None:
            from mlx_audio.stt.utils import load_model
            self.model = load_model(WHISPER)
        return (self.model.generate(str(wav), language=self.language, task="transcribe").text or "").strip()

    def close(self) -> None:
        self.model = None
        free_memory()


class QwenVoice:
    """A Qwen3-TTS voice. Use make_voice() rather than constructing this directly."""

    def __init__(self, mode: str = "custom", *, ref_audio: Path | None = None, ref_text: str | None = None,
                 instruct: str | None = None, speaker: str | None = None, language: str = "english",
                 seed: int = 7, temperature: float = DEFAULT_TEMPERATURE, verify: bool = True,
                 cache: Path | None = None, log: Any = print):
        if mode not in MODELS:
            raise ValueError(f"mode must be one of {', '.join(MODELS)} (got {mode!r})")
        if mode == "custom" and not speaker:
            raise ValueError("a preset voice needs a speaker (list them: python -m filmwright.core.voice speakers)")
        if mode == "design" and not instruct:
            raise ValueError("a described voice needs a description of the voice")
        if mode == "clone":
            if not ref_audio:
                raise ValueError("a cloned voice needs voice.sample, the path of the consented sample")
            ref_audio = Path(ref_audio).expanduser()
            verify_consent(ref_audio)                       # mandatory; raises ConsentError
            if not ref_text:
                txt = ref_audio.with_suffix(".txt")
                if not txt.exists():
                    raise ValueError(f"{txt} is missing: it holds the words spoken in the sample "
                                     "(python -m filmwright.core.voice.clone prepare writes it)")
                ref_text = txt.read_text().strip()
        require_mlx()
        self.mode, self.instruct, self.speaker = mode, instruct, speaker
        self.kind = {"custom": "preset", "design": "described", "clone": "clone"}[mode]
        self.language, self.seed, self.temperature, self.verify = language, seed, temperature, verify
        self.cache, self.log = cache, log
        self.ref_audio, self.ref_text = ref_audio, ref_text
        self.model: Any = None
        self._loaded = ""
        self.whisper = Transcriber(WHISPER_LANG.get(language, "en" if language == "auto" else None))
        self.report: list[tuple[str, float]] = []   # (sentence, best score) for sentences that never read back cleanly
        self.slow: list[tuple[str, float]] = []     # (sentence, pace) for sentences that stayed drawn out

    @property
    def name(self) -> str:
        return {"custom": f"preset speaker {self.speaker}", "design": "described voice", "clone": "cloned voice"}[self.mode]

    # --- models -------------------------------------------------------------------------

    def _load(self, mode: str) -> Any:
        if self.model is not None and self._loaded == mode:
            return self.model
        self.model = None
        free_memory()
        from mlx_audio.tts.utils import load_model
        t = time.time()
        self.log(f"loading {MODELS[mode]} ...")
        self.model, self._loaded = load_model(MODELS[mode]), mode
        self.log(f"  loaded in {time.time() - t:.0f}s")
        return self.model

    def _designed_reference(self) -> None:
        """Design mode: render the description once into a reference clip, then clone that."""
        key = hashlib.sha256(json.dumps([self.instruct, self.seed, self.language]).encode()).hexdigest()[:10]
        folder = cache_dir() / "voices"
        folder.mkdir(parents=True, exist_ok=True)
        wav = folder / f"designed-{key}.wav"
        if not wav.exists():
            self.log(f"designing the voice: {self.instruct!r}")
            self._render(DESIGN_REF_TEXT, wav, mode="design")
            (folder / f"designed-{key}.json").write_text(
                json.dumps({"description": self.instruct, "seed": self.seed, "text": DESIGN_REF_TEXT}, indent=2))
        self.ref_audio, self.ref_text = wav, DESIGN_REF_TEXT

    def _generate(self, text: str, mode: str, seed: int) -> Any:
        import mlx.core as mx
        import numpy as np
        model = self._load(mode)
        mx.random.seed(seed)
        kw: dict[str, Any] = {"text": text, "lang_code": self.language, "temperature": self.temperature,
                              "split_pattern": "\n", "max_tokens": max(120, len(text) * 2)}
        if mode == "clone":
            kw.update(ref_audio=str(self.ref_audio), ref_text=self.ref_text)
        elif mode == "design":
            kw.update(instruct=self.instruct)
        else:
            kw.update(voice=self.speaker, instruct=self.instruct)
        parts = [np.asarray(r.audio, dtype=np.float32) for r in model.generate(**kw)]
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)

    def _render(self, text: str, out: Path, mode: str) -> None:
        """One sentence (or the design reference) with length check, read-back and retries."""
        rate = 24000
        expected = speech_seconds(text)
        best: tuple[tuple, float, float, Any] | None = None
        for attempt in range(ATTEMPTS):
            audio = self._generate(text, mode, self.seed + attempt * 1000)
            rate = self.model.sample_rate
            secs = len(audio) / rate
            pace = spoken_seconds(audio, rate) / expected
            score = 1.0
            if not (0.4 * expected <= secs <= 2.5 * expected + 1.0):
                score = 0.0                                     # truncated or runaway
            elif self.verify:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    write_wav(Path(tmp.name), audio, rate)
                    score = match_score(text, self.whisper(Path(tmp.name)))
                os.unlink(tmp.name)
            # a take that reads back wins; among those, one at a normal pace; then the least drawn out
            rank = (score >= MIN_SCORE, pace <= MAX_PACE, -max(pace, MAX_PACE), score)
            if best is None or rank > best[0]:
                best = (rank, score, pace, audio)
            if score >= MIN_SCORE and pace <= MAX_PACE:
                break
        assert best is not None
        _, score, pace, audio = best
        if score < MIN_SCORE:
            self.report.append((text, score))
        elif pace > MAX_PACE:
            self.slow.append((text, pace))
        write_wav(out, audio, rate)

    # --- public -------------------------------------------------------------------------

    def cache_key(self, text: str) -> str:
        ref = sha256(self.ref_audio) if self.mode == "clone" and self.ref_audio else ""
        return hashlib.sha256(json.dumps([MODELS[self.mode], self.mode, self.instruct, self.speaker,
                                          self.language, self.seed, self.temperature, self.verify, MAX_PACE, ref,
                                          self.ref_text if self.mode == "clone" else "", text]).encode()).hexdigest()[:16]

    def say(self, text: str, out_wav: Path) -> float:
        """Speak `text` (any number of sentences) into a 24 kHz mono WAV; returns its length in seconds."""
        out_wav = Path(out_wav)
        cached = self.cache / f"{self.cache_key(text)}.wav" if self.cache else None
        if cached and cached.exists():
            shutil.copyfile(cached, out_wav)
            return wav_seconds(out_wav)
        if self.mode == "design" and self.ref_audio is None:
            self._designed_reference()
        mode = "custom" if self.mode == "custom" else "clone"
        import numpy as np
        pieces, rate = [], 24000
        with tempfile.TemporaryDirectory(prefix="filmwright-voice-") as tmp:
            for i, sen in enumerate(sentences(text)):
                wav = Path(tmp) / f"s{i:03d}.wav"
                self._render(sen, wav, mode)
                with wave.open(str(wav)) as w:
                    rate = w.getframerate()
                    pieces.append(np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32767)
                pieces.append(np.zeros(int(SENTENCE_GAP * rate), dtype=np.float32))
        write_wav(out_wav, np.concatenate(pieces[:-1]) if pieces else np.zeros(rate // 10), rate)
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(out_wav, cached)
        return wav_seconds(out_wav)

    synth = say   # older name

    def close(self) -> None:
        self.model = None
        self.whisper.close()
        if self.report:
            self.log(f"\n{len(self.report)} sentence(s) never read back cleanly; listen to them "
                     "(rephrasing or spelling out an abbreviation usually helps):")
            for sen, score in self.report:
                self.log(f"  {score:.2f}  {sen}")
        if self.slow:
            self.log(f"\n{len(self.slow)} sentence(s) still sound drawn out after {ATTEMPTS} tries; listen to them "
                     "(a calmer `voice.style`, or splitting a long sentence, usually helps):")
            for sen, pace in self.slow:
                self.log(f"  {pace:.2f}x  {sen}")
