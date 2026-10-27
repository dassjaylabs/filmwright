"""reel.yaml: load, fill in defaults, validate, and check what this machine can run."""
from __future__ import annotations

import copy
import platform
import shutil
import sys
from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import yaml

MODES = ("demo", "explainer", "both")
VOICE_TYPES = ("preset", "library", "described", "clone", "system")
PRESET_SPEAKERS = ("ryan", "aiden", "serena", "vivian", "dylan", "eric", "uncle_fu", "ono_anna", "sohee")
CHARACTERS = ("leo", "leo-light", "leo-stubble", "sam", "ana", "lee", "maya", "raj", "kit", "jo")
CORNERS = ("bottom-right", "bottom-left")
MOODS = ("upbeat", "calm", "corporate", "inspiring", "playful", "epic", "sad", "suspense", "none")
OUTPUTS = ("4k", "hd", "vertical", "square", "web", "gif", "stems")
VIDEO_OUTPUTS = OUTPUTS[:-1]                 # stems come alongside a video, never instead of one
DISCLOSURE = ("none", "metadata", "end-card")
SOUND_EFFECTS = ("subtle", "full", "off")    # subtle: interface sounds only, no whooshes or risers
CHECK_LEVELS = ("off", "warn", "block")
EXPLAINER_FORMATS = ("story", "montage")

DEFAULTS: dict[str, Any] = {
    "mode": "demo",
    "title": "",
    "brand": "example",
    "voice": {"type": "preset", "speaker": "ryan", "name": "", "description": "", "sample": "", "style": "", "language": "English"},
    "talking_head": {"enabled": False, "character": "leo", "corner": "bottom-right"},
    "music": {"mood": "upbeat", "sync_to_scenes": True, "level": None},
    "sound_effects": "subtle",
    "captions": {"burn_in": True, "scale": 1.0},    # scale 1.4 for a cut meant to be watched on a phone
    "outputs": ["4k", "hd"],
    "disclosure": "metadata",
    "checks": {"tool_names": "warn"},
    "demo": {"scenarios": "scenarios.yaml", "video": "video.yaml", "serve": None},
    "explainer": {"format": "story", "project": "explainer"},
    "both": {"film": "film.yaml"},
}


class ConfigError(ValueError):
    pass


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _one_of(errors: list[str], where: str, value: Any, allowed: tuple) -> None:
    if value not in allowed:
        errors.append(f"{where}: {value!r} is not one of {', '.join(allowed)}")


def validate(cfg: dict) -> list[str]:
    e: list[str] = []
    _one_of(e, "mode", cfg["mode"], MODES)
    v = cfg["voice"]
    _one_of(e, "voice.type", v.get("type"), VOICE_TYPES)
    if v.get("type") == "described" and not str(v.get("description") or "").strip():
        e.append("voice.description: a described voice needs a description, e.g. \"Calm, friendly narrator in her thirties\"")
    if v.get("type") == "library":
        from filmwright.core.voice.library import names
        if v.get("name") not in names():
            e.append(f"voice.name: a library voice needs a name, one of: {', '.join(names())}")
    if v.get("type") == "clone" and not v.get("sample"):
        e.append("voice.sample: a cloned voice needs a sample recording (filmwright voice record) and a consent record")
    th = cfg["talking_head"]
    if th.get("enabled"):
        _one_of(e, "talking_head.character", th.get("character"), CHARACTERS)
        _one_of(e, "talking_head.corner", th.get("corner"), CORNERS)
    _one_of(e, "music.mood", cfg["music"].get("mood"), MOODS)
    try:
        cs = float((cfg.get("captions") or {}).get("scale", 1) or 1)
        if not 0.5 <= cs <= 3:
            e.append(f"captions.scale: {cs} is out of range (0.5 to 3; 1.4 reads well on a phone)")
    except (TypeError, ValueError):
        e.append("captions.scale: must be a number (1 is the default, 1.4 reads well on a phone)")
    outs = cfg["outputs"]
    if not isinstance(outs, list) or not outs:
        e.append("outputs: a list such as [4k, hd]")
    else:
        for o in outs:
            _one_of(e, "outputs", o, OUTPUTS)
        if not any(o in VIDEO_OUTPUTS for o in outs):
            e.append("outputs: stems come with a video; add one of " + ", ".join(VIDEO_OUTPUTS))
    _one_of(e, "disclosure", cfg["disclosure"], DISCLOSURE)
    _one_of(e, "sound_effects", cfg["sound_effects"], SOUND_EFFECTS)
    _one_of(e, "checks.tool_names", cfg["checks"].get("tool_names"), CHECK_LEVELS)
    if cfg["mode"] == "explainer":
        _one_of(e, "explainer.format", cfg["explainer"].get("format"), EXPLAINER_FORMATS)
    return e


def load(path: str | Path) -> dict:
    p = Path(path).expanduser()
    if p.is_dir():
        p = p / "reel.yaml"
    if not p.is_file():
        raise ConfigError(f"{p} not found. Create one with: filmwright new")
    raw = yaml.safe_load(p.read_text()) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{p}: expected a mapping at the top level")
    unknown = sorted(set(raw) - set(DEFAULTS))
    cfg = _merge(DEFAULTS, raw)
    cfg["_path"] = str(p.resolve())
    cfg["_dir"] = str(p.resolve().parent)
    cfg["_explicit"] = sorted(raw)                     # keys the file actually sets (the rest are defaults)
    errors = validate(cfg) + [f"{k}: unknown key" for k in unknown]
    if errors:
        raise ConfigError(f"{p}:\n  " + "\n  ".join(errors))
    return cfg


def dump(cfg: dict) -> str:
    clean = {k: v for k, v in cfg.items() if not k.startswith("_")}
    return yaml.safe_dump(clean, sort_keys=False, allow_unicode=True)


# --- what this machine can do -------------------------------------------------------------------

@dataclass
class Capabilities:
    apple_silicon: bool
    mlx: bool
    ffmpeg: bool
    espeak: bool
    playwright: bool
    notes: list[str] = field(default_factory=list)

    @property
    def neural_voice(self) -> bool:
        return self.apple_silicon and self.mlx


def capabilities() -> Capabilities:
    apple = sys.platform == "darwin" and platform.machine() == "arm64"
    c = Capabilities(
        apple_silicon=apple,
        mlx=apple and find_spec("mlx_audio") is not None,
        ffmpeg=shutil.which("ffmpeg") is not None,
        espeak=(shutil.which("espeak-ng") or shutil.which("espeak")) is not None,
        playwright=find_spec("playwright") is not None,
    )
    if not apple:
        c.notes.append("Neural voices (preset, described, clone) need Apple Silicon; this machine uses the system voice.")
    elif not c.mlx:
        c.notes.append("Neural voices are not installed yet: filmwright setup --voice preset")
    if not c.ffmpeg:
        c.notes.append("ffmpeg is missing: filmwright setup")
    return c


def effective_voice_type(cfg: dict, caps: Capabilities | None = None) -> str:
    """The voice that will actually be used: neural types fall back to the system voice where unsupported."""
    caps = caps or capabilities()
    t = cfg["voice"]["type"]
    if t == "clone" and not caps.neural_voice:
        raise ConfigError("voice.type clone needs Apple Silicon with the voice models installed "
                          "(filmwright setup --voice clone). A cloned voice never falls back to another voice.")
    if t != "system" and not caps.neural_voice:
        return "system"
    return t
