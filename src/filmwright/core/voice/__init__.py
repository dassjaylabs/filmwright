"""Narration voices.

    from filmwright.core.voice import make_voice
    voice = make_voice({"type": "preset", "speaker": "ryan"}, root=project_dir)
    seconds = voice.say("Hello there.", out_wav)
    voice.close()

`cfg` is the `voice:` block of reel.yaml:

    type         preset | library | described | clone | system  (default: preset)
    speaker      preset: a built-in speaker name                 (default: ryan)
    name         library: a ready-made narrator (nora, james, olivia, ...; see library.json)
    description  described: the voice in words, e.g. "Calm, friendly narrator in her thirties"
    sample       clone: path to the consented sample (relative to `root`)
    style        delivery instruction for preset voices          (default: natural and conversational)
    temperature  0.3-1.0, lower is steadier                      (default: 0.65)
    language     english, chinese, japanese, korean, german, french, spanish, italian, portuguese, russian
    seed, verify advanced: generation seed, read-back check on/off
    system_voice, rate   system: espeak-ng voice name and words per minute

preset, library, described and clone run Qwen3-TTS on Apple Silicon. When that isn't possible on this machine, preset,
library and described fall back to the system voice with a clear message. A cloned voice never falls back silently: it
raises, because a different voice is not what was asked for. Clone mode always requires a consent record.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .consent import ConsentError, verify_consent, write_consent
from .espeak import EspeakVoice
from .qwen import (
    DEFAULT_SPEAKER,
    DEFAULT_STYLE,
    DEFAULT_TEMPERATURE,
    PRESET_SPEAKERS,
    QwenVoice,
    VoiceUnavailable,
    mlx_status,
)

VOICE_TYPES = ("preset", "library", "described", "clone", "system")

__all__ = ["make_voice", "Voice", "VOICE_TYPES", "PRESET_SPEAKERS", "ConsentError", "VoiceUnavailable",
           "verify_consent", "write_consent", "mlx_status", "QwenVoice", "EspeakVoice"]


class Voice(Protocol):
    kind: str                                  # preset | described | clone | system (used for disclosure)
    report: list[tuple[str, float]]

    @property
    def name(self) -> str: ...
    def say(self, text: str, out_wav: Path) -> float: ...
    def close(self) -> None: ...


def make_voice(cfg: dict[str, Any] | None, root: Path | None = None, cache: Path | None = None,
               log: Any = print) -> Voice:
    """Build the narration voice described by a reel.yaml `voice:` block."""
    cfg = dict(cfg or {})
    root = Path(root or Path.cwd())
    kind = str(cfg.get("type") or "preset").lower()
    if kind not in VOICE_TYPES:
        raise ValueError(f"voice.type must be one of {', '.join(VOICE_TYPES)} (got {kind!r})")
    cache = cache if cache is not None else root / ".tts-cache"

    def system() -> EspeakVoice:
        return EspeakVoice(str(cfg.get("system_voice") or "en-us"), int(cfg.get("rate") or 165), log=log)

    if kind == "system":
        return system()

    common = {"language": str(cfg.get("language") or "english"), "seed": int(cfg.get("seed", 7)),
              "temperature": float(cfg.get("temperature", DEFAULT_TEMPERATURE)),
              "verify": bool(cfg.get("verify", True)), "cache": cache, "log": log}
    if kind == "clone":
        sample = cfg.get("sample")
        if not sample:
            raise ValueError("voice.type clone needs voice.sample (see docs/voice.md)")
        path = Path(str(sample)).expanduser()
        path = path if path.is_absolute() else root / path
        verify_consent(path)                    # before anything else, on every machine
        reason = mlx_status()
        if reason:
            raise VoiceUnavailable(f"a cloned voice can't run here: {reason}. Use voice.type preset or system on this machine.")
        return QwenVoice("clone", ref_audio=path, ref_text=cfg.get("sample_text"), **common)

    if kind == "library":
        from .library import reference
        clip, text, entry = reference(str(cfg.get("name") or ""))     # an unknown name or altered clip stops here
        reason = mlx_status()
        if reason:
            log(f"note: {reason}. Narrating with the system voice (espeak-ng) instead.")
            return system()
        # a bundled synthetic voice: cloned from its checksum-verified clip (no consent record needed)
        return QwenVoice("design", instruct=entry["description"], ref_audio=clip, ref_text=text, label=f"library voice {cfg['name']}",
                         **common)

    desc = str(cfg.get("description") or "").strip()
    if kind == "described" and not desc:
        raise ValueError("voice.type described needs voice.description, the voice in words")
    reason = mlx_status()
    if reason:
        log(f"note: {reason}. Narrating with the system voice (espeak-ng) instead. "
            "Set voice.type: system to silence this note.")
        return system()
    if kind == "described":
        return QwenVoice("design", instruct=desc, **common)
    return QwenVoice("custom", speaker=str(cfg.get("speaker") or DEFAULT_SPEAKER),
                     instruct=str(cfg.get("style") or DEFAULT_STYLE), **common)
