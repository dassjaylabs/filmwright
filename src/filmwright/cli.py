"""filmwright: narrated product films, made on your own machine.

    filmwright new [DIR]        ask what to make, write DIR/reel.yaml and starter files
    filmwright storyboard [DIR] one panel per scene (picture, line, timing) to approve before building
    filmwright build [DIR]      make the film described by DIR/reel.yaml
    filmwright doctor           what this machine can run, and what is missing
    filmwright setup [...]      install the tools a film needs (ffmpeg, Chromium, voices...)
    filmwright options          every choice reel.yaml accepts
    filmwright voice ...        preview voices; `voice clone ...` records a consented cloned voice
    filmwright music ...        render a mood track on its own
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from filmwright import __version__, paths
from filmwright import config as C


def _mod(module: str, *args: str, cwd: str | None = None) -> int:
    """Run a filmwright module in a child process (pipelines are long-running and keep their own state)."""
    return subprocess.call([sys.executable, "-m", module, *args], cwd=cwd)


# --- new -------------------------------------------------------------------------------------------

def _bool(s: str | None) -> bool | None:
    if s is None:
        return None
    if s.lower() in ("y", "yes", "true", "1", "on"):
        return True
    if s.lower() in ("n", "no", "false", "0", "off"):
        return False
    raise argparse.ArgumentTypeError(f"expected yes or no, got {s!r}")


def cmd_new(a: argparse.Namespace) -> int:
    from filmwright import scaffold, wizard

    d = Path(a.dir).expanduser()
    if (d / "reel.yaml").exists() and not a.force:
        print(f"{d / 'reel.yaml'} already exists (use --force to replace it).", file=sys.stderr)
        return 1
    preset = {
        "mode": a.mode, "format": a.format, "title": a.title, "voice": a.voice, "speaker": a.speaker, "voice_name": a.voice_name,
        "voice_description": a.voice_description, "voice_sample": a.voice_sample,
        "talking_head": _bool(a.talking_head), "character": a.character, "music": a.music, "sound_effects": a.sound_effects,
        "captions": _bool(a.captions), "outputs": a.outputs.split(",") if a.outputs else None,
        "disclosure": a.disclosure, "brand": a.brand,
    }
    interactive = sys.stdin.isatty() and not a.yes
    try:
        cfg = wizard.run(preset, interactive)
    except C.ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    d.mkdir(parents=True, exist_ok=True)
    (d / "reel.yaml").write_text(C.dump(cfg))
    made = scaffold.starter_files(cfg, d)
    print(f"\nWrote {d / 'reel.yaml'}\n{wizard.summary(cfg)}")
    for p in made:
        print(f"  + {p.relative_to(d)}")
    print("\nNext:")
    for step in scaffold.next_steps(cfg, d):
        print(f"  {step}")
    return 0


# --- build -----------------------------------------------------------------------------------------

def cmd_build(a: argparse.Namespace) -> int:
    from filmwright import build

    try:
        cfg = C.load(a.dir)
    except C.ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return build.run(cfg, only=a.only, skip_record=a.skip_record, allow_expired=a.allow_expired)


def cmd_storyboard(a: argparse.Namespace) -> int:
    from filmwright import build

    try:
        cfg = C.load(a.dir)
    except C.ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return build.storyboard(cfg, only=a.only, pdf=not a.no_pdf)


# --- doctor / setup / options ----------------------------------------------------------------------

def cmd_doctor(a: argparse.Namespace) -> int:
    caps = C.capabilities()
    ok = lambda b: "OK     " if b else "MISSING"
    print(f"filmwright {__version__}  ·  Python {sys.version.split()[0]}  ·  {sys.platform}")
    print(f"  {ok(caps.ffmpeg)}  ffmpeg (encoding)")
    print(f"  {ok(caps.playwright)}  Playwright (recording and rendering)")
    print(f"  {ok(caps.espeak)}  espeak-ng (system voice)")
    print(f"  {ok(caps.apple_silicon)}  Apple Silicon (neural voices)")
    print(f"  {ok(caps.mlx)}  mlx-audio (preset, described and cloned voices)")
    for n in caps.notes:
        print(f"  note: {n}")
    return _setup(["--check"])


def _setup(args: list[str]) -> int:
    script = paths.TOOLS / "setup.sh"
    if not script.is_file():
        print(f"setup script missing: {script}", file=sys.stderr)
        return 1
    env = dict(os.environ, PYTHON=sys.executable)
    return subprocess.call(["bash", str(script), *args], env=env)


def cmd_setup(a: argparse.Namespace) -> int:
    args = ["--check"] if a.check else []
    if a.voice:
        args.append(f"--voice={a.voice}")
    return _setup(args)


def cmd_options(a: argparse.Namespace) -> int:
    from filmwright.wizard import CHOICE_HELP

    print("mode:")
    for k, v in CHOICE_HELP["mode"].items():
        print(f"  {k:<10} {v.split(': ', 1)[1]}")
    print("explainer.format:", ", ".join(C.EXPLAINER_FORMATS))
    print("voice.type:")
    for k, v in CHOICE_HELP["voice"].items():
        print(f"  {k:<10} {v.split(': ', 1)[1]}")
    print("voice.speaker (preset):", ", ".join(C.PRESET_SPEAKERS))
    from filmwright.core.voice.library import voices
    print("voice.name (library):")
    for k, v in voices().items():
        print(f"  {k:<10} {v['label'].split(': ', 1)[1]}")
    print("talking_head.character:", ", ".join(C.CHARACTERS))
    print("talking_head.corner:", ", ".join(C.CORNERS))
    print("music.mood:")
    for k, v in CHOICE_HELP["music"].items():
        print(f"  {k:<10} {v.split(': ', 1)[1] if ': ' in v else v}")
    print("sound_effects:")
    for k, v in CHOICE_HELP["sound_effects"].items():
        print(f"  {k:<10} {v.split(': ', 1)[1] if ': ' in v else v}")
    print("outputs:", ", ".join(C.OUTPUTS))
    print("disclosure:", ", ".join(C.DISCLOSURE))
    print("checks.tool_names:", ", ".join(C.CHECK_LEVELS))
    return 0


# --- passthroughs ----------------------------------------------------------------------------------

def cmd_voice(a: argparse.Namespace, rest: list[str]) -> int:
    """filmwright voice preview|speakers ...   and   filmwright voice clone passage|record|consent|... """
    if rest and rest[0] == "clone":
        return _mod("filmwright.core.voice.clone", *rest[1:])
    return _mod("filmwright.core.voice", *rest)


def cmd_music(a: argparse.Namespace, rest: list[str]) -> int:
    return _mod("filmwright.core.music", *rest)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="filmwright", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"filmwright {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="ask what to make and write reel.yaml + starter files")
    n.add_argument("dir", nargs="?", default=".")
    n.add_argument("--mode", choices=C.MODES)
    n.add_argument("--format", choices=C.EXPLAINER_FORMATS, help="explainer format")
    n.add_argument("--title")
    n.add_argument("--voice", choices=C.VOICE_TYPES)
    n.add_argument("--speaker", help="preset speaker name")
    n.add_argument("--voice-name", help="library voice name (filmwright options lists them)")
    n.add_argument("--voice-description", help="described voice, in words")
    n.add_argument("--voice-sample", help="cloned voice: path to the sample recording")
    n.add_argument("--talking-head", metavar="yes|no")
    n.add_argument("--character", choices=C.CHARACTERS)
    n.add_argument("--music", choices=C.MOODS)
    n.add_argument("--sound-effects", choices=C.SOUND_EFFECTS, help="subtle (default), full or off")
    n.add_argument("--captions", metavar="yes|no", help="burn captions into the video")
    n.add_argument("--outputs", help=f"comma list of {', '.join(C.OUTPUTS)}")
    n.add_argument("--disclosure", choices=C.DISCLOSURE)
    n.add_argument("--brand", help="bundled brand name or path to a brand folder")
    n.add_argument("--yes", "-y", action="store_true", help="don't ask; use defaults for anything not given")
    n.add_argument("--force", action="store_true", help="replace an existing reel.yaml")

    b = sub.add_parser("build", help="make the film described by reel.yaml")
    b.add_argument("dir", nargs="?", default=".")
    b.add_argument("--only", help="demo: rerun only these scenarios (S01,S02); explainer: only these stories (1,3)")
    b.add_argument("--skip-record", action="store_true", help="demo/both: reuse existing recordings")
    b.add_argument("--allow-expired", action="store_true", help="demo: record even if the saved session's token has expired")

    sb = sub.add_parser("storyboard", help="one panel per scene to approve before building (HTML + PDF)")
    sb.add_argument("dir", nargs="?", default=".")
    sb.add_argument("--only", help="explainer stories: only these (1,3)")
    sb.add_argument("--no-pdf", action="store_true", help="the HTML page only")

    sub.add_parser("doctor", help="what this machine can run")
    s = sub.add_parser("setup", help="install what films need")
    s.add_argument("--check", action="store_true", help="report only, change nothing")
    s.add_argument("--voice", choices=("preset", "library", "described", "clone", "all"), help="also install the neural voice models")
    sub.add_parser("options", help="every choice reel.yaml accepts")
    sub.add_parser("voice", help="voice preview and cloning tools (filmwright voice --help)", add_help=False)
    sub.add_parser("music", help="render a mood track (filmwright music --help)", add_help=False)

    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("voice", "music"):
        a = argparse.Namespace(cmd=argv[0])
        return (cmd_voice if argv[0] == "voice" else cmd_music)(a, argv[1:])
    a = ap.parse_args(argv)
    return {"new": cmd_new, "build": cmd_build, "storyboard": cmd_storyboard, "doctor": cmd_doctor, "setup": cmd_setup, "options": cmd_options}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
