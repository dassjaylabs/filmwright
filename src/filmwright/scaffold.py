"""Starter files for `filmwright new`: the inputs each mode reads, copied from the bundled templates."""
from __future__ import annotations

import shutil
from pathlib import Path

from filmwright import paths

# mode -> [(template path relative to paths.TEMPLATES, destination relative to the project folder)]
STARTERS: dict[str, list[tuple[str, str]]] = {
    "demo": [("demo/scenarios.example.yaml", "scenarios.yaml"), ("demo/video.example.yaml", "video.yaml")],
    "explainer:story": [("story/example/project.json", "explainer/project.json"),
                        ("story/example/stories.json", "explainer/stories.json")],
    "explainer:montage": [("montage/example/montage.json", "explainer/montage.json")],
    "both": [("hybrid/example/film.yaml", "film.yaml")],
}


def _key(cfg: dict) -> str:
    return f"explainer:{cfg['explainer']['format']}" if cfg["mode"] == "explainer" else cfg["mode"]


def starter_files(cfg: dict, dest: Path) -> list[Path]:
    made = []
    for src_rel, dst_rel in STARTERS[_key(cfg)]:
        src, dst = paths.TEMPLATES / src_rel, dest / dst_rel
        if not src.is_file():
            raise FileNotFoundError(f"bundled starter template missing: {src}")
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        made.append(dst)
    if cfg["voice"]["type"] == "clone":
        (dest / "voice").mkdir(exist_ok=True)
    return made


def next_steps(cfg: dict, dest: Path) -> list[str]:
    steps: list[str] = []
    if cfg["voice"]["type"] == "clone":
        steps += [
            "filmwright voice clone passage                          # the text to read aloud",
            'filmwright voice clone record --speaker "<full name>"   # records, then asks the speaker to consent',
            "filmwright voice clone preview --play                   # hear the cloned voice",
        ]
    elif cfg["voice"]["type"] in ("preset", "library", "described"):
        steps.append(f"filmwright setup --voice {cfg['voice']['type']}       # one-time voice model download (Apple Silicon)")
    mode = cfg["mode"]
    if mode == "demo":
        steps += ["edit scenarios.yaml (what to click) and video.yaml (what to say)   docs/demo.md",
                  f"filmwright build {dest}"]
    elif mode == "explainer":
        steps += ["edit explainer/ (product, stories, narration)   docs/explainer.md", f"filmwright build {dest}"]
    else:
        steps += ["edit film.yaml (animated scenes and recorded clips, in order)   docs/hybrid.md", f"filmwright build {dest}"]
    return steps
