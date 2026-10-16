"""`filmwright new`: ask what kind of film to make and write reel.yaml.

Every question has a matching flag, so the same choices can be scripted:
    filmwright new my-film --mode explainer --voice preset --talking-head no --music sad --outputs 4k,hd --yes
"""
from __future__ import annotations

import sys
from typing import Any

from filmwright import config as C

CHOICE_HELP = {
    "mode": {
        "demo": "Demo walkthrough: record your real product in a browser, narrated, with zooms on each action",
        "explainer": "Animated explainer: characters, whiteboard sketches and motion graphics, no screen recording",
        "both": "Both: animated scenes and screen recordings in one narrated film",
    },
    "format": {
        "story": "Story: one character, one use case, about 40 seconds",
        "montage": "Montage: many features in about a minute",
    },
    "voice": {
        "preset": "Preset voice: a built-in narrator (no recording needed)",
        "described": "Described voice: describe the voice in words and one is designed for you",
        "clone": "Cloned voice: your own voice from a short recording (needs the speaker's consent)",
        "system": "System voice: works on any machine, robotic, no download",
    },
    "music": {
        "upbeat": "Upbeat: bright, driving, on the beat",
        "calm": "Calm: soft and unobtrusive",
        "corporate": "Corporate: steady, confident, clean",
        "inspiring": "Inspiring: builds and lifts",
        "playful": "Playful: bouncy and light",
        "epic": "Epic: big, cinematic swells",
        "sad": "Sad: slow, minor key, reflective",
        "suspense": "Suspense: tense pulses, unresolved",
        "none": "No music",
    },
    "sound_effects": {
        "subtle": "Subtle: quiet clicks and pops that follow the action (recommended)",
        "full": "Full: also whooshes and risers on zooms and scene changes",
        "off": "No sound effects",
    },
    "disclosure": {
        "metadata": "Note the synthetic voice in the file's metadata (recommended)",
        "end-card": "Also show a short closing card saying the voice is synthetic",
        "none": "No disclosure",
    },
}


def _ask(prompt: str, options: dict[str, str], default: str) -> str:
    keys = list(options)
    print(f"\n{prompt}")
    for i, k in enumerate(keys, 1):
        mark = " (default)" if k == default else ""
        print(f"  {i}. {options[k]}{mark}")
    while True:
        raw = input(f"Choose 1-{len(keys)} [{keys.index(default) + 1}]: ").strip()
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(keys):
            return keys[int(raw) - 1]
        if raw in keys:
            return raw
        print("  Please type one of the numbers.")


def _yes(prompt: str, default: bool) -> bool:
    raw = input(f"\n{prompt} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
    return default if not raw else raw.startswith("y")


def _text(prompt: str, default: str = "") -> str:
    raw = input(f"\n{prompt}{f' [{default}]' if default else ''}: ").strip()
    return raw or default


def _multi(prompt: str, options: tuple[str, ...], default: list[str]) -> list[str]:
    raw = input(f"\n{prompt} ({', '.join(options)}) [{','.join(default)}]: ").strip()
    if not raw:
        return default
    picked = [p.strip().lower() for p in raw.replace(" ", ",").split(",") if p.strip()]
    bad = [p for p in picked if p not in options]
    if bad:
        print(f"  Ignoring unknown: {', '.join(bad)}")
    return [p for p in picked if p in options] or default


def run(preset: dict[str, Any], interactive: bool) -> dict:
    """Return a reel config. `preset` holds answers already given as flags; the rest are asked (or defaulted)."""
    caps = C.capabilities()
    cfg = C._merge(C.DEFAULTS, {})

    def pick(key, ask):
        if key in preset and preset[key] is not None:
            return preset[key]
        return ask() if interactive else None

    mode = pick("mode", lambda: _ask("What are you making?", CHOICE_HELP["mode"], "demo"))
    cfg["mode"] = mode or cfg["mode"]
    if cfg["mode"] == "explainer":
        fmt = pick("format", lambda: _ask("Which explainer format?", CHOICE_HELP["format"], "story"))
        cfg["explainer"]["format"] = fmt or "story"

    title = pick("title", lambda: _text("Film title", "My product in two minutes"))
    cfg["title"] = title or ""

    voice_opts = dict(CHOICE_HELP["voice"])
    if not caps.neural_voice:
        note = " [not available on this machine yet]"
        for k in ("preset", "described", "clone"):
            voice_opts[k] += note
    vt = pick("voice", lambda: _ask("Narration voice?", voice_opts, "preset" if caps.neural_voice else "system"))
    cfg["voice"]["type"] = vt or ("preset" if caps.neural_voice else "system")
    if cfg["voice"]["type"] == "described":
        d = pick("voice_description", lambda: _text("Describe the voice", "Warm, friendly narrator in her thirties, clear American accent"))
        cfg["voice"]["description"] = d or "Warm, friendly narrator, clear accent"
    if cfg["voice"]["type"] == "clone":
        cfg["voice"]["sample"] = pick("voice_sample", lambda: _text("Path to the voice sample (or leave the default and record one later)",
                                                                    "voice/sample.wav")) or "voice/sample.wav"
    if cfg["voice"]["type"] == "preset":
        sp = pick("speaker", lambda: _text(f"Preset speaker ({', '.join(C.PRESET_SPEAKERS[:2])} are native English)", "ryan"))
        cfg["voice"]["speaker"] = sp or "ryan"

    th = pick("talking_head", lambda: _yes("Add an animated talking-head presenter?", False))
    cfg["talking_head"]["enabled"] = bool(th)
    if cfg["talking_head"]["enabled"]:
        ch = pick("character", lambda: _text(f"Presenter character ({', '.join(C.CHARACTERS)})", "leo"))
        cfg["talking_head"]["character"] = ch or "leo"

    mood = pick("music", lambda: _ask("Music?", CHOICE_HELP["music"], "upbeat"))
    cfg["music"]["mood"] = mood or "upbeat"

    fx = pick("sound_effects", lambda: _ask("Sound effects?", CHOICE_HELP["sound_effects"], "subtle"))
    cfg["sound_effects"] = fx or "subtle"

    burn = pick("captions", lambda: _yes("Burn small captions into the video? (an .srt is always written)", True))
    cfg["captions"]["burn_in"] = True if burn is None else bool(burn)

    outs = pick("outputs", lambda: _multi("Outputs", C.OUTPUTS, ["4k", "hd"]))
    cfg["outputs"] = outs or ["4k", "hd"]

    disc = pick("disclosure", lambda: _ask("Disclose the synthetic voice?", CHOICE_HELP["disclosure"], "metadata"))
    cfg["disclosure"] = disc or "metadata"
    if "brand" in preset and preset["brand"]:
        cfg["brand"] = preset["brand"]

    errors = C.validate(cfg)
    if errors:
        raise C.ConfigError("\n  ".join(errors))
    return cfg


def summary(cfg: dict) -> str:
    v = cfg["voice"]
    voice = {"preset": f"preset ({v.get('speaker')})", "described": f"described ({v.get('description')})",
             "clone": f"cloned from {v.get('sample')}", "system": "system"}[v["type"]]
    th = cfg["talking_head"]
    lines = [
        f"  mode          {cfg['mode']}" + (f" ({cfg['explainer']['format']})" if cfg["mode"] == "explainer" else ""),
        f"  voice         {voice}",
        f"  talking head  {th['character'] + ', ' + th['corner'] if th['enabled'] else 'no'}",
        f"  music         {cfg['music']['mood']}",
        f"  sound effects {cfg['sound_effects']}",
        f"  captions      {'burned in + .srt' if cfg['captions']['burn_in'] else '.srt only'}",
        f"  outputs       {', '.join(cfg['outputs'])}",
        f"  disclosure    {cfg['disclosure']}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(C.dump(run({}, sys.stdin.isatty())))
