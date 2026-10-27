"""`filmwright build`: turn reel.yaml into the inputs each pipeline reads, run it, then export and disclose.

Each pipeline keeps its own input file (demo: video.yaml; explainer: project.json; both: film.yaml). The reel's
shared choices (voice, presenter, music, captions, checks) override what those files say, so one reel.yaml decides
the film's look and sound while the pipeline files hold the content.
"""
from __future__ import annotations

import contextlib
import copy
import json
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

from filmwright import config as C


def _run(module: str, *args: str, cwd: Path) -> int:
    print(f"\n$ python -m {module} {' '.join(args)}")
    return subprocess.call([sys.executable, "-m", module, *args], cwd=str(cwd))


def _music_block(reel: dict) -> dict | None:
    m = reel["music"]
    if m.get("mood") == "none":
        return None
    block = {"mood": m["mood"], "sync_to_scenes": bool(m.get("sync_to_scenes", True))}
    if m.get("level") is not None:
        block["level"] = float(m["level"])           # dB under the narration; unset = the pipeline's default
    return block


def _presenter_block(reel: dict) -> dict | None:
    th = reel["talking_head"]
    if not th.get("enabled"):
        return None
    return {"style": th.get("character", "leo"), "position": th.get("corner", "bottom-right"), "height": th.get("height", 0.25)}


def voice_block(reel: dict) -> dict:
    v = {k: val for k, val in reel["voice"].items() if val not in ("", None)}
    v["type"] = C.effective_voice_type(reel)
    if v["type"] != reel["voice"]["type"]:
        print(f"note: voice.type {reel['voice']['type']} is not available on this machine; using the system voice "
              "(filmwright setup --voice preset installs the neural voices on Apple Silicon)")
    return v


@contextlib.contextmanager
def _serve(root: Path, serve: dict | None) -> Iterator[None]:
    """Optionally serve a local folder (demo.serve: {dir: app, port: 8765}) while the scenarios record."""
    if not serve:
        yield
        return
    port = int(serve.get("port", 8765))
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", port)) == 0:
            print(f"port {port} already serves something; using it")
            yield
            return
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1",
                             "--directory", str(root / serve.get("dir", "."))],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.1)
        print(f"serving {serve.get('dir', '.')} on http://127.0.0.1:{port}")
        yield
    finally:
        proc.terminate()


# --- demo --------------------------------------------------------------------------------------------

def _resolve_demo(reel: dict, root: Path) -> tuple[Path, Path]:
    src = root / reel["demo"]["video"]
    if not src.is_file():
        raise C.ConfigError(f"{src} not found (demo.video in reel.yaml)")
    film: dict[str, Any] = yaml.safe_load(src.read_text()) or {}
    film = copy.deepcopy(film)
    film.pop("tts", None)
    film["voice"] = voice_block(reel)
    mus = _music_block(reel)
    if mus:
        film["music"] = mus
    else:
        film.pop("music", None)
    pres = _presenter_block(reel)
    if pres:
        film["presenter"] = {**(film.get("presenter") if isinstance(film.get("presenter"), dict) else {}), **pres}
    else:
        film.pop("presenter", None)
    film["checks"] = reel["checks"]
    if "sound_effects" in reel.get("_explicit", []):          # else video.yaml's own `sfx` stands (subtle by default)
        own = film.get("sfx", True)
        film["sfx"] = False if reel["sound_effects"] == "off" else \
            {**(own if isinstance(own, dict) else {}), "sounds": reel["sound_effects"]}
    film["stems"] = "stems" in reel["outputs"]
    film.setdefault("output", f"out/{_stem(reel, root)}")
    resolved = src.with_name(f".{src.stem}.resolved.yaml")      # beside the original: its relative clip paths still work
    resolved.write_text("# written by filmwright build from reel.yaml + " + src.name + "; edit those instead\n"
                        + yaml.safe_dump(film, sort_keys=False, allow_unicode=True))
    out = Path(film["output"])
    return resolved, (out if out.is_absolute() else src.parent / out)


def build_demo(reel: dict, root: Path, only: str | None, skip_record: bool, allow_expired: bool = False) -> Path | None:
    scen = root / reel["demo"]["scenarios"]
    if not skip_record:
        if not scen.is_file():
            raise C.ConfigError(f"{scen} not found (demo.scenarios in reel.yaml)")
        with _serve(root, reel["demo"].get("serve")):
            args = [str(scen)] + (["--only", only] if only else []) + (["--allow-expired"] if allow_expired else [])
            rc = _run("filmwright.demo.run_scenarios", *args, cwd=root)
        if rc:
            print("Recording stopped: see the message above, or results.md for failed scenarios. Fix them, or build "
                  "from what was recorded with --skip-record.")
            return None
    resolved, out_base = _resolve_demo(reel, root)
    if _run("filmwright.demo.build_video", str(resolved), cwd=root):
        return None
    return out_base.with_suffix(".mp4")


# --- explainer / both ----------------------------------------------------------------------------------

PIPELINE_OUTPUTS = ("4k", "hd", "stems")  # what the animated pipelines make themselves; the rest come from export


def _settings(reel: dict, root: Path, native: tuple[str, ...] = PIPELINE_OUTPUTS) -> Path:
    """The reel's shared choices as the JSON the animated pipelines deep-merge over their own config."""
    m = reel["music"]
    music = {"mood": m["mood"], "sync_to_scenes": bool(m.get("sync_to_scenes", True))}
    if m.get("level") is not None:
        music["level"] = float(m["level"])
    music["sound_effects"] = reel["sound_effects"]
    outs = [o for o in reel["outputs"] if o in native]
    if not any(o in ("4k", "hd") for o in outs):
        outs.append("hd")                                              # always keep a master to export from
    s: dict[str, Any] = {"voice": voice_block(reel), "music": music, "talking_head": dict(reel["talking_head"]),
                         "captions": dict(reel["captions"]), "outputs": outs, "checks": dict(reel["checks"])}
    if "brand" in reel.get("_explicit", []):
        s["brand"] = reel["brand"]
    if reel.get("title") and "title" in reel.get("_explicit", []):
        s["title"] = reel["title"]
    out = root / ".filmwright" / "settings.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(s, indent=2))
    return out


def _pipeline(module: str, target: Path, settings: Path, steps: list[list[str]], cwd: Path) -> bool:
    for step in steps:
        if _run(module, str(target), *step, "--settings", str(settings), cwd=cwd):
            return False
    return True


def _newest_masters(folder: Path, pattern: str) -> list[Path]:
    """One master per film: the 4K file when there is one, else HD."""
    found: dict[str, Path] = {}
    for p in sorted(folder.glob(pattern)):
        stem = p.stem.removesuffix("-4k").removesuffix("-hd")
        if p.stem.endswith("-4k") or stem not in found:
            found[stem] = p
    return list(found.values())


def build_explainer(reel: dict, root: Path, only: str | None) -> list[tuple[Path, list[Path]]]:
    proj = (root / reel["explainer"]["project"]).resolve()
    fmt = reel["explainer"]["format"]
    if fmt == "story":
        if not (proj / "stories.json").is_file():
            raise C.ConfigError(f"{proj / 'stories.json'} not found (explainer.project in reel.yaml)")
        which = only or "all"
        ok = _pipeline("filmwright.explainer.story", proj, _settings(reel, root),
                       [["tts", which], ["render", which], ["verify", which]], root)
        if not ok:
            return []
        masters = _newest_masters(proj, "*/*-[4h][kd].mp4")
    else:
        if not (proj / "montage.json").is_file():
            raise C.ConfigError(f"{proj / 'montage.json'} not found (explainer.project in reel.yaml)")
        native = ("4k", "hd", "vertical", "square", "stems")
        ok = _pipeline("filmwright.explainer.montage", proj, _settings(reel, root, native),
                       [["tts"], ["render"], ["verify"]], root)
        if not ok:
            return []
        masters = _newest_masters(proj, "*-[4h][kd].mp4")
        return [(m, sorted(m.parent.glob(m.stem.removesuffix("-4k").removesuffix("-hd") + "-*.mp4"))) for m in masters]
    return [(m, sorted(m.parent.glob(m.stem.removesuffix("-4k").removesuffix("-hd") + "-[4h][kd].mp4"))) for m in masters]


def build_both(reel: dict, root: Path) -> list[tuple[Path, list[Path]]]:
    spec = (root / reel["both"]["film"]).resolve()
    if not spec.is_file():
        raise C.ConfigError(f"{spec} not found (both.film in reel.yaml)")
    film = yaml.safe_load(spec.read_text()) or {}
    missing = [s["clip"] for s in film.get("segments", []) if s.get("clip") and not (spec.parent / s["clip"]).is_file()]
    if missing:
        raise C.ConfigError("recordings not found: " + ", ".join(missing)
                            + ". Record them first (a demo run writes videos/<scenario>.mp4) and point film.yaml at them.")
    if not _pipeline("filmwright.hybrid.film", spec, _settings(reel, root), [["tts"], ["render"], ["verify"]], root):
        return []
    masters = _newest_masters(spec.parent, "*-[4h][kd].mp4")
    return [(m, sorted(m.parent.glob(m.stem.removesuffix("-4k").removesuffix("-hd") + "-[4h][kd].mp4"))) for m in masters]


# --- shared finishing ----------------------------------------------------------------------------------

def _stem(reel: dict, root: Path) -> str:
    from filmwright.core.names import file_safe
    return file_safe(reel.get("title")) or file_safe(root.name) or "film"


def finish(reel: dict, master: Path, already: list[Path], out_dir: Path, stem: str) -> list[Path]:
    """Deliver the requested outputs of one film, then apply the disclosure setting to every video.

    `already` lists files the pipeline made itself (copied as they are); everything else comes from the master."""
    import shutil

    from filmwright.core import disclosure
    from filmwright.core.export import render_outputs

    out_dir.mkdir(parents=True, exist_ok=True)
    made: list[Path] = []
    done = set()
    for p in already:
        kind = p.stem.rsplit("-", 1)[-1]
        if kind in reel["outputs"]:
            dst = out_dir / f"{stem}-{kind}.mp4"
            shutil.copyfile(p, dst)
            made.append(dst)
            done.add(kind)
    srt = master.with_name(stem + ".srt") if master.with_name(stem + ".srt").is_file() else master.with_suffix(".srt")
    if srt.is_file():
        shutil.copyfile(srt, out_dir / f"{stem}.srt")
    from filmwright.core.mix import STEM_NAMES
    for name in STEM_NAMES:
        (out_dir / f"{stem}-{name}.wav").unlink(missing_ok=True)    # stems from an earlier build of this film
    if "stems" in reel["outputs"]:
        for name in STEM_NAMES:
            src = master.with_name(f"{stem}-{name}.wav")
            if src.is_file():
                dst = out_dir / src.name
                shutil.copyfile(src, dst)
                made.append(dst)
    rest = [o for o in reel["outputs"] if o not in done and o != "stems"]
    if rest:
        burn = bool(reel["captions"]["burn_in"]) and reel["mode"] == "demo"     # animated films burn captions in already
        made += render_outputs(master, srt if srt.is_file() else None, rest, out_dir, stem, burn_captions=burn)
    vtype = C.effective_voice_type(reel)
    if reel["disclosure"] != "none":
        for p in made:
            if p.suffix == ".mp4":
                disclosure.apply(p, reel["disclosure"], vtype)
    return made


def run(reel: dict, only: str | None = None, skip_record: bool = False, allow_expired: bool = False) -> int:
    root = Path(reel["_dir"])
    try:
        C.effective_voice_type(reel)                    # a cloned voice that can't run stops here, before any recording
        if reel["mode"] == "demo":
            m = build_demo(reel, root, only, skip_record, allow_expired)
            films = [(m, [])] if m else []
        elif reel["mode"] == "explainer":
            films = build_explainer(reel, root, only)
        else:
            films = build_both(reel, root)
    except C.ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if not films:
        return 1
    delivered: list[Path] = []
    final = root / "out" / "final"
    for master, already in films:
        stem = master.stem.removesuffix("-4k").removesuffix("-hd")
        delivered += finish(reel, master, already, final, stem)
    print("\nDelivered:")
    for p in delivered:
        print(f"  {p.relative_to(root) if p.is_relative_to(root) else p}")
    (final / "manifest.json").write_text(json.dumps([str(p.relative_to(root)) for p in delivered], indent=2))
    return 0


# --- storyboard ----------------------------------------------------------------------------------------

def storyboard(reel: dict, only: str | None = None, pdf: bool = True) -> int:
    """One panel per scene, for sign-off before the full render: out/storyboard/index.html (+ storyboard.pdf).
    Animated films narrate first (cached, so the real build reuses it) to get real timings and pictures."""
    from filmwright import storyboard as SB
    root = Path(reel["_dir"])
    v = reel["voice"]
    voice = {"preset": v.get("speaker"), "library": v.get("name"), "described": "described", "clone": "cloned",
             "system": "system"}.get(v["type"], "")
    meta = {"Film": reel["mode"] + (f" ({reel['explainer']['format']})" if reel["mode"] == "explainer" else ""),
            "Voice": f"{v['type']} · {voice}" if voice and voice != v["type"] else v["type"],
            "Music": reel["music"]["mood"], "Sound effects": reel["sound_effects"]}
    try:
        C.effective_voice_type(reel)
        if reel["mode"] == "demo":
            resolved, _ = _resolve_demo(reel, root)
            film = yaml.safe_load(resolved.read_text()) or {}
            groups = SB.demo_groups(film, resolved.parent, root / "out" / "storyboard" / ".frames")
            meta["Timing"] = "estimated from the script"
        else:
            if reel["mode"] == "explainer":
                target = (root / reel["explainer"]["project"]).resolve()
                story = reel["explainer"]["format"] == "story"
                module = "filmwright.explainer.story" if story else "filmwright.explainer.montage"
                steps = [["tts", only or "all"], ["board", only or "all"]] if story else [["tts"], ["board"]]
                folder = target
            else:
                target = (root / reel["both"]["film"]).resolve()
                module, steps, folder = "filmwright.hybrid.film", [["tts"], ["board"]], target.parent
            if not _pipeline(module, target, _settings(reel, root), steps, root):
                return 1
            groups = SB.load_groups(folder / "storyboard.json")
    except C.ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    title = reel.get("title") or root.name
    out = SB.build(title, meta, groups, root / "out" / "storyboard", pdf=pdf)
    print("\nStoryboard:")
    for p in out:
        print(f"  {p.relative_to(root) if p.is_relative_to(root) else p}")
    return 0
