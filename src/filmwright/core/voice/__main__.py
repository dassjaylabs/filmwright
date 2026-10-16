"""Hear a narration voice before building a film.

    python -m filmwright.core.voice preview --play                          # preset speaker ryan
    python -m filmwright.core.voice preview --type preset --speaker aiden --style "Warm and upbeat" --play
    python -m filmwright.core.voice preview --type library --name olivia --play
    python -m filmwright.core.voice preview --type described --description "Calm, friendly narrator in her thirties" --play
    python -m filmwright.core.voice preview --type clone --sample voice/sample.wav --play
    python -m filmwright.core.voice preview --type system --play
    python -m filmwright.core.voice speakers
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import VOICE_TYPES, ConsentError, VoiceUnavailable, make_voice
from .qwen import MODELS, require_mlx

PREVIEW_TEXT = ("Here's a quick preview of the narration voice. If it sounds right, "
                "we'll use it for the whole film.")


def play(path: Path) -> None:
    if shutil.which("ffplay"):           # ships with ffmpeg
        subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)])
    elif shutil.which("afplay"):
        subprocess.run(["afplay", str(path)])
    else:
        print("no audio player found (ffplay ships with ffmpeg); open the file to listen")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m filmwright.core.voice", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pv = sub.add_parser("preview", help="speak one short paragraph in the chosen voice")
    pv.add_argument("--type", choices=VOICE_TYPES, default="preset")
    pv.add_argument("--speaker")
    pv.add_argument("--name", help="library voice name")
    pv.add_argument("--style")
    pv.add_argument("--description")
    pv.add_argument("--sample", type=Path)
    pv.add_argument("--language", default="english")
    pv.add_argument("--seed", type=int, default=7)
    pv.add_argument("--text", default=PREVIEW_TEXT)
    pv.add_argument("--out", type=Path, help="default: ./voice-preview-<type>.wav")
    pv.add_argument("--play", action="store_true", help="play it when done")
    sub.add_parser("speakers", help="list the preset speakers the installed model has")
    args = ap.parse_args(argv)

    if args.cmd == "speakers":
        try:
            require_mlx()
        except VoiceUnavailable as e:
            sys.exit(str(e))
        from mlx_audio.tts.utils import load_model
        print(", ".join(sorted(load_model(MODELS["custom"]).get_supported_speakers())))
        return 0

    cfg = {k: v for k, v in {"type": args.type, "speaker": args.speaker, "name": args.name, "style": args.style,
                             "description": args.description, "sample": str(args.sample) if args.sample else None,
                             "language": args.language, "seed": args.seed}.items() if v is not None}
    try:
        voice = make_voice(cfg, root=Path.cwd(), cache=None)
    except (ConsentError, VoiceUnavailable, ValueError, RuntimeError) as e:
        sys.exit(str(e))
    out = args.out or Path.cwd() / f"voice-preview-{args.type}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    t = time.time()
    secs = voice.say(args.text, out)
    voice.close()
    print(f"{out} ({secs:.1f}s audio, {voice.name}, {time.time() - t:.0f}s)")
    if args.play:
        play(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
