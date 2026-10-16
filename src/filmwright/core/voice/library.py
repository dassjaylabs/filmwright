"""Ready-made narrator voices: `voice: {type: library, name: nora}`.

Each one was designed once from a description with Qwen3-TTS VoiceDesign (scripts/build_voice_library.py) and ships
as a short reference clip in assets/voices, listed with its description, seed and SHA-256 in library.json. A film
clones the clip with the Base model, so every machine gets the same voice and the VoiceDesign model isn't needed.

The clips are synthetic, so they don't need a consent record. Only these bundled, checksum-verified files get that
exemption: a library voice is picked by name, never by path, and a clip that doesn't match its checksum is refused.
A recording of a real person always goes through `voice.type: clone` and its consent check.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from filmwright.paths import ASSETS

from .qwen import DESIGN_REF_TEXT, sha256

LIBRARY_DIR = ASSETS / "voices"
MANIFEST = LIBRARY_DIR / "library.json"
REF_TEXT = DESIGN_REF_TEXT


class LibraryError(ValueError):
    pass


def voices() -> dict[str, dict]:
    """name -> {label, description, seed, sha256, ...}, in the library's order."""
    return dict(json.loads(MANIFEST.read_text())["voices"])


def names() -> list[str]:
    return list(voices())


def reference(name: str) -> tuple[Path, str, dict]:
    """The bundled clip for `name`, the words spoken in it, and its manifest entry. Raises LibraryError for an
    unknown name or a clip that is missing or doesn't match its checksum."""
    lib = voices()
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", name) or name not in lib:
        raise LibraryError(f"voice.name {name!r} isn't in the voice library; choose one of: {', '.join(lib)}")
    entry = lib[name]
    clip = LIBRARY_DIR / f"{name}.wav"
    if not clip.is_file() or not entry.get("sha256") or sha256(clip) != entry["sha256"]:
        raise LibraryError(f"the library clip for {name!r} is missing or was modified ({clip}); reinstall filmwright")
    return clip, json.loads(MANIFEST.read_text()).get("text") or REF_TEXT, entry
