"""Build a narrated MP4 from a video.yaml: title card, one section per clip, closing card, subtitles.

    python -m filmwright.demo.build_video <run-dir>/video.yaml

Directed effects come from `focus`, `callouts` and `spotlight` (anchored to the runner's events.json),
`explainer` scenes (HTML recorded to the narration's length) and `music`; see docs/film.md.
The film's resolution defaults to the best the clips support (4K from a 3× capture).
Narration runs on this machine through filmwright.core.voice (the `voice:` block: preset, described, cloned or
system voice; see docs/voice.md). Cards and on-screen section labels are rendered with Pillow (so an ffmpeg
without drawtext/libass still works). Clips can be Playwright .webm recordings, .mp4 or .gif:
  * real-time video: if the narration is longer than the clip, the last frame is held (never slowed down);
  * GIF (slideshow-style frames): stretched evenly to the narration.
Outputs <output>.mp4 (H.264 + AAC + soft English subtitles), <output>.srt and <output>-voiceover.m4a.
See templates/demo/video.example.yaml for every field.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageDraw, ImageFont

from filmwright.core.sfx import sfx_track
from filmwright.demo import cues as speech_cues
from filmwright.demo.effects import (
    aim_points,
    load_events,
    loading_cuts,
    moments,
    overlays,
    plan_camera,
    remap,
    sfx_cues,
    zoompan,
)
from filmwright.paths import FONTS

BG, FG, MUTED, ACCENT = (17, 20, 24), (236, 239, 242), (150, 158, 168), (34, 197, 94)
LEAD, TAIL = 0.6, 1.0     # seconds of quiet before / after each section's narration
FPS = 30



def load_yaml(path: Path) -> dict[str, Any]:
    """Parse a YAML file, turning syntax errors into one readable line."""
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
        sys.exit(f"{path.name} is not valid YAML{where}: {getattr(e, 'problem', e)}. "
                 "Tip: quote values that start with a quote, colon or brace, and write list indexes as .0 rather than [0] inside {…}.")
    if not isinstance(data, dict):
        sys.exit(f"{path.name} should be a YAML mapping at the top level")
    return data

# --- fonts ------------------------------------------------------------------------

def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """IBM Plex Sans, bundled with filmwright (SIL Open Font License), so cards look the same everywhere."""
    path = FONTS / ("IBMPlexSans-SemiBold.ttf" if bold else "IBMPlexSans-Regular.ttf")
    if path.exists():
        return ImageFont.truetype(str(path), size)
    for alt in ["/usr/share/fonts/truetype/dejavu/DejaVuSans" + ("-Bold" if bold else "") + ".ttf"]:
        if Path(alt).exists():
            return ImageFont.truetype(alt, size)
    return ImageFont.load_default(size)


def wrap(draw: ImageDraw.ImageDraw, text: str, f: Any, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=f) <= width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


# --- cards + labels ------------------------------------------------------------------

def title_card(cfg: dict[str, Any], w: int, h: int, out: Path) -> None:
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, max(6, w // 160), h], fill=ACCENT)
    x, y, width = int(w * 0.08), int(h * 0.26), int(w * 0.82)
    if cfg.get("eyebrow"):
        d.text((x, y), cfg["eyebrow"], font=font(int(h * 0.045), True), fill=ACCENT)
        y += int(h * 0.075)
    for line in wrap(d, cfg.get("title", ""), font(int(h * 0.1), True), width):
        d.text((x, y), line, font=font(int(h * 0.1), True), fill=FG)
        y += int(h * 0.125)
    for line in wrap(d, cfg.get("subtitle", ""), font(int(h * 0.045)), width):
        d.text((x, y), line, font=font(int(h * 0.045)), fill=MUTED)
        y += int(h * 0.062)
    if cfg.get("footer"):
        ff = font(int(h * 0.034))
        for k, line in enumerate(wrap(d, cfg["footer"], ff, int(w * 0.68))):
            d.text((x, int(h * 0.78) + k * int(h * 0.046)), line, font=ff, fill=MUTED)
    im.save(out)


def closing_card(cfg: dict[str, Any], w: int, h: int, out: Path) -> None:
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, max(6, w // 160), h], fill=ACCENT)
    x, y, width = int(w * 0.08), int(h * 0.2), int(w * 0.8)
    d.text((x, y), cfg.get("title", "What changed"), font=font(int(h * 0.095), True), fill=FG)
    y += int(h * 0.16)
    bf = font(int(h * 0.05))
    indent = d.textlength("•  ", font=bf)
    for bullet in cfg.get("bullets", []):
        for i, line in enumerate(wrap(d, bullet, bf, int(width - indent))):
            d.text((x if i == 0 else x + indent, y), ("•  " if i == 0 else "") + line, font=bf,
                   fill=FG if i == 0 else MUTED)
            y += int(h * 0.075)
    if cfg.get("footer"):
        ff = font(int(h * 0.032))
        for k, line in enumerate(wrap(d, cfg["footer"], ff, int(w * 0.68))):
            d.text((x, int(h * 0.82) + k * int(h * 0.044)), line, font=ff, fill=MUTED)
    im.save(out)


def label_png(text: str, w: int, h: int, out: Path, side: str = "left") -> None:
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = font(max(18, int(h * 0.04)), True)
    tw = d.textlength(text, font=f)
    bh = int(h * 0.085)
    x0, y0 = int(w * 0.02), h - bh - int(h * 0.045)
    if side == "right":
        x0 = int(w - w * 0.02 - tw - bh * 0.8)
    d.rounded_rectangle([x0, y0, x0 + tw + int(bh * 0.8), y0 + bh], radius=int(bh * 0.22), fill=(10, 12, 15, 225))
    d.rectangle([x0, y0 + int(bh * 0.13), x0 + 6, y0 + bh - int(bh * 0.13)], fill=ACCENT + (255,))
    d.text((x0 + int(bh * 0.42), y0 + int(bh * 0.18)), text, font=f, fill=FG + (255,))
    im.save(out)


# --- media helpers ---------------------------------------------------------------------

def run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        why = (f"killed by signal {-p.returncode}" + (" (out of memory?)" if p.returncode == -9 else "")
               if p.returncode < 0 else f"exit {p.returncode}")
        errors = [ln for ln in p.stderr.splitlines() if not ln.startswith(("frame=", "  ", "size="))]
        sys.exit(f"command failed ({why}): {' '.join(cmd[:6])}…\n" + "\n".join(errors[-25:]))


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        sys.exit(f"could not read the duration of {path}")


def voice_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """The narration voice: the `voice:` block (same fields as reel.yaml). An older `tts:` block is still read:
    engine qwen + mode custom/design/clone map to preset/described/clone, engine espeak-ng to system."""
    if isinstance(cfg.get("voice"), dict):
        return dict(cfg["voice"])
    old = dict(cfg.get("tts") or {})
    if not old:
        return {}
    if old.get("engine") in ("espeak-ng", "espeak") or "rate" in old:
        return {"type": "system", **({"system_voice": old["voice"]} if "voice" in old else {}),
                **({"rate": old["rate"]} if "rate" in old else {})}
    mode = old.get("mode", "custom")
    out: dict[str, Any] = {"type": {"custom": "preset", "design": "described", "clone": "clone"}.get(mode, "preset")}
    if mode == "design":
        out["description"] = old.get("instruct", "")
    elif old.get("instruct"):
        out["style"] = old["instruct"]
    for k_old, k_new in (("speaker", "speaker"), ("ref_audio", "sample"), ("ref_text", "sample_text"),
                         ("temperature", "temperature"), ("language", "language")):
        if k_old in old:
            out[k_new] = old[k_old]
    return out


def tts(text: str, out_wav: Path, voice: Any, work: Path) -> None:
    """Narrate one section into a 48 kHz stereo WAV."""
    src = work / (out_wav.stem + ".voice.wav")
    voice.say(text, src)
    # a peak limiter (latency-compensated, so nothing moves in time) lets the speech reach the target level
    af = f"volume={narration_gain(src):.2f}dB,alimiter=limit=0.84:attack=5:release=50:level=false:latency=true"
    run(["ffmpeg", "-y", "-i", str(src), "-af", af, "-ar", "48000", "-ac", "2", str(out_wav)])


def narration_gain(wav: Path) -> float:
    """dB that bring a section's narration to NARRATION_LUFS (the voices come out anywhere from about -28 to -18);
    one constant gain per section, at most +20 dB. tts() limits the peaks after it."""
    from filmwright.core.mix import lufs
    level = lufs(wav)
    return 0.0 if level <= -70 else min(NARRATION_LUFS - level, 20.0)


def fit_filter(w: int, h: int) -> str:
    return (f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x111418,setsar=1")


def encode(inputs: list[str], filt: str, total: float, out: Path) -> None:
    run(["ffmpeg", "-y", *inputs, "-filter_complex", filt, "-map", "[v]", "-map", "[a]",
         "-t", f"{total:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "17",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-flags:a", "+bitexact", "-b:a", "192k", "-ar", "48000", str(out)])


def dims(path: Path) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip().split(",")
    return int(out[0]), int(out[1])


def pick_size(cfg: dict[str, Any], root: Path) -> tuple[int, int]:
    """`size` wins, then `resolution`; otherwise the best the clips support (4K from a 3× capture)."""
    from filmwright.demo.recorder import RESOLUTIONS
    if cfg.get("size"):
        return int(cfg["size"]["width"]) // 2 * 2, int(cfg["size"]["height"]) // 2 * 2
    if cfg.get("resolution"):
        return RESOLUTIONS[str(cfg["resolution"]).lower()]
    widest = 0
    for s in cfg.get("sections", []):
        clip = (root / str(s.get("clip", ""))).expanduser()
        if s.get("clip") and clip.exists() and clip.suffix.lower() != ".gif":
            widest = max(widest, dims(clip)[0])
    for name in ("4k", "1440p", "1080p"):
        if widest >= RESOLUTIONS[name][0]:
            return RESOLUTIONS[name]
    return RESOLUTIONS["1080p"]


NARRATION_LUFS = -15.0     # where each section's narration is brought to (the film lands near -16 LUFS);
                           # music levels are relative to it


def music_plan(cfg: dict[str, Any]) -> dict[str, Any] | None:
    """The `music:` block, normalised. None means no music.
    mood: upbeat | calm | corporate | inspiring | playful | epic | sad | suspense | none (see docs/music.md)
    sync_to_scenes: true composes a score with a downbeat on every section start; false lays a quiet ambient bed.
    level: dB under the narration (default: -20 for a score, -26 for an ambient bed); level_lufs sets the absolute
    loudness instead.
    file: your own track instead (looped and faded)."""
    mus = cfg.get("music")
    if not mus:
        return None
    mus = {"mood": mus} if isinstance(mus, str) else dict(mus)
    if str(mus.get("mood", "calm")).lower() == "none" or mus.get("enabled") is False:
        return None
    mus.setdefault("mood", "calm")
    mus.setdefault("sync_to_scenes", True)
    if "level_lufs" not in mus:
        level = mus.get("level")
        if level is None:
            level = -20 if mus["sync_to_scenes"] and not mus.get("file") else -26
        mus["level_lufs"] = NARRATION_LUFS + float(level)
    return mus


def add_music(joined: Path, mus: dict[str, Any], root: Path, total: float, work: Path, cuts: list[float],
              stem_wav: Path | None = None) -> Path:
    """Mix music under the narration, ducking it further while someone speaks. `stem_wav` also gets the music
    exactly as it sits in the mix (levelled and ducked)."""
    wav = work / "music.wav"
    if mus.get("file"):
        src = (root / str(mus["file"])).expanduser()
        run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(src), "-t", f"{total:.2f}", "-af",
             f"afade=t=in:d=2,afade=t=out:st={max(0.0, total - 3):.2f}:d=3", "-ar", "48000", "-ac", "2", str(wav)])
    elif mus.get("sync_to_scenes", True):
        from filmwright.core.music import score
        score(wav, total, cuts, str(mus["mood"]))
    else:
        from filmwright.core.music import ambient
        ambient(wav, total, str(mus["mood"]))
    level = float(mus["level_lufs"])
    duck = "[m][v1]sidechaincompress=threshold=0.02:ratio=4:attack=80:release=900[md];" if mus.get("duck", True) \
        else "[m]anull[md];"
    out = work / "with_music.mp4"
    split, extra = "", []
    if stem_wav:
        duck = duck.replace("[md];", "[md0];")
        split = "[md0]asplit=2[md][ms];"
        extra = ["-map", "[ms]", "-t", f"{total:.3f}", "-ar", "48000", "-ac", "2", "-c:a", "pcm_f32le",
                 "-fflags", "+bitexact", "-flags:a", "+bitexact", str(stem_wav)]
    run(["ffmpeg", "-y", "-i", str(joined), "-i", str(wav), "-filter_complex",
         f"[0:a]asplit=2[v1][v2];[1:a]loudnorm=I={level}:TP=-9:LRA=11,aformat=sample_rates=48000:channel_layouts=stereo[m];"
         + duck + split + "[v2][md]amix=inputs=2:duration=first:normalize=0:dropout_transition=0[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-flags:a", "+bitexact", "-b:a", "192k", str(out),
         *extra])
    return out


def write_stems(out_base: Path, sections: list[tuple[Path, Path | None, float]], trans_d: float, work: Path) -> None:
    """<output>-narration.wav and (when there are effects) <output>-sfx.wav: each section's narration and effects cut
    and crossfaded exactly as the film's audio is, as 32-bit float 48 kHz stereo WAV. add_music() writes the music
    stem. Laid side by side in an editor, the three add up to the film's soundtrack."""
    ms = int(LEAD * 1000)
    kinds = {"narration": [(w, f"adelay={ms}|{ms},apad") for w, _, _ in sections]}
    if any(f for _, f, _ in sections):
        kinds["sfx"] = [(f, "apad") for _, f, _ in sections]
    for name, srcs in kinds.items():
        pieces = []
        for k, ((src, af), (_, _, total)) in enumerate(zip(srcs, sections)):
            piece = work / f"stem-{name}-{k:02d}.wav"
            inp = ["-i", str(src)] if src else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
            run(["ffmpeg", "-y", *inp, "-af", f"aresample=48000,aformat=channel_layouts=stereo,{af},atrim=0:{total:.3f}",
                 "-c:a", "pcm_f32le", str(piece)])
            pieces.append(piece)
        dst = out_base.parent / (out_base.name + f"-{name}.wav")
        f32 = ["-ar", "48000", "-ac", "2", "-c:a", "pcm_f32le", "-fflags", "+bitexact", "-flags:a", "+bitexact", str(dst)]
        if trans_d > 0 and len(pieces) > 1:
            graph, prev = "", "[0:a]"
            for k in range(1, len(pieces)):
                graph += f"{prev}[{k}:a]acrossfade=d={trans_d:.3f}:c1=tri:c2=tri[x{k}];"
                prev = f"[x{k}]"
            run(["ffmpeg", "-y", *sum([["-i", str(p_)] for p_ in pieces], []), "-filter_complex", graph.rstrip(";"),
                 "-map", prev, *f32])
        else:
            listing = work / f"stem-{name}.txt"
            listing.write_text("".join(f"file '{p_}'\n" for p_ in pieces))
            run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), *f32])


def audio_chain(total: float, sfx_idx: int | None = None) -> str:
    ms = int(LEAD * 1000)
    base = f"[1:a]adelay={ms}|{ms},apad,atrim=0:{total:.3f}"
    if sfx_idx is None:
        return base + "[a]"
    return (base + f"[na];[{sfx_idx}:a]apad,atrim=0:{total:.3f}[sa];"
            "[na][sa]amix=inputs=2:normalize=0:duration=first[a]")


def presenter_overlay(idx: int, src: str, dst: str, cfg: dict[str, Any], w: int, h: int) -> str:
    """Overlay the presenter movie (input `idx`, with alpha) in a bottom corner."""
    ph = int(h * float(cfg.get("height", 0.21)))
    margin = int(w * 0.015)
    x = f"{margin}" if str(cfg.get("position", "bottom-right")) == "bottom-left" else f"W-w-{margin}"
    return (f"[{idx}:v]format=rgba,scale=-1:{ph}:flags=lanczos[pr{dst}];"
            f"[{src}][pr{dst}]overlay={x}:H-h:eof_action=pass[{dst}];")


def chapters_file(chapters: list[tuple[float, float, str]], path: Path) -> Path:
    lines = [";FFMETADATA1"]
    for a, b, title in chapters:
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(a * 1000)}", f"END={int(b * 1000)}",
                  "title=" + title.replace("\n", " ")]
    path.write_text("\n".join(lines) + "\n")
    return path





def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?:])\s+", text) if s.strip()]


def srt_time(x: float) -> str:
    h, rem = divmod(x, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")


# --- main --------------------------------------------------------------------------------

def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    cfg_path = Path(sys.argv[1]).expanduser().resolve()
    cfg = load_yaml(cfg_path)
    check_mode = str((cfg.get("checks") or {}).get("tool_names", "warn"))
    if not text_check([cfg_path], check_mode):
        return 1
    root = cfg_path.parent
    w, h = pick_size(cfg, root)
    print(f"film: {w}x{h}")
    out_base = Path(str(cfg.get("output", root / "walkthrough"))).expanduser()
    if not out_base.is_absolute():
        out_base = root / out_base
    from filmwright.core.voice import make_voice  # imported here: neural voices load heavy libraries
    voice = make_voice(voice_config(cfg), root=root)   # relative sample paths and the voice cache live in the run folder

    pres = cfg.get("presenter")
    pres_cfg: dict[str, Any] = dict(pres) if isinstance(pres, dict) else {}
    pres_cfg.setdefault("style", pres_cfg.get("character", "leo"))       # reel.yaml says `character` and `corner`
    pres_cfg.setdefault("position", pres_cfg.get("corner", "bottom-right"))
    presenter_on = bool(pres) and pres_cfg.get("enabled", True) is not False
    sfx = cfg.get("sfx", True)
    sfx_on, sfx_level = bool(sfx), float(sfx.get("level", 0.5)) if isinstance(sfx, dict) else 0.5
    sfx_sounds = str(sfx.get("sounds", "subtle")) if isinstance(sfx, dict) else "subtle"   # reel.yaml sound_effects
    trans = cfg.get("transition") or {}
    trans_type = str(trans.get("type", "cut"))
    trans_d = float(trans.get("duration", 0.6)) if trans_type != "cut" else 0.0
    keep_fades = trans_type in ("cut", "fade")      # a crossfade looks wrong on top of fades to black
    if trans_type == "fade":
        trans_type, trans_d = "cut", 0.0            # "fade" is the classic cut with fades to black

    parts: list[dict[str, Any]] = []
    if cfg.get("title_card"):
        parts.append({"card": "title", "text": cfg.get("intro", "")})
    for sec in cfg.get("sections", []):
        parts.append(sec)
    if cfg.get("closing_card"):
        parts.append({"card": "closing", "text": cfg.get("outro", "")})

    work = Path(tempfile.mkdtemp(prefix="filmwright-"))
    pool = None
    if presenter_on:
        from filmwright.presenter.presenter import PresenterPool
        pool = PresenterPool(workers=int(pres_cfg.get("workers", 4)))

    # --- pass 1: narration, timing, camera; presenter sections render in the background ----------
    plans: list[dict[str, Any]] = []
    for i, part in enumerate(parts):
        text = (part.get("text") or "").strip()
        wav = work / f"p{i:02d}.wav"
        if text:
            print(f"narrating section {i + 1}/{len(parts)} …", flush=True)
            tts(text, wav, voice, work)
            a = duration(wav)
            words = speech_cues.word_times(text, sentences(text), wav)           # when each word is spoken
            part = speech_cues.anchor_words(part, words, LEAD) if words else part   # `word: "export"` anchors on callouts etc.
        else:  # silent section
            run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "0.1", str(wav)])
            a = 0.0
            words = []
        voiced = LEAD + a + TAIL if text else 0.0
        plan: dict[str, Any] = {"i": i, "part": part, "text": text, "wav": wav, "a": a, "camera": [], "meta": None,
                                "frame": (w, h), "presenter": False, "words": words}
        if "card" in part:
            plan.update(kind="card", total=max(voiced, 4.0))
        else:
            if part.get("explainer"):              # an HTML animation, recorded to fit the narration
                from filmwright.demo.recorder import record_html
                html = (root / str(part["explainer"])).expanduser()
                if not html.exists():
                    sys.exit(f"explainer not found: {html}")
                want = max(voiced, float(part.get("min_seconds", 5)))
                for _attempt in range(3):          # a stalled screen capture (CPU busy with presenter renders) stretches the clip
                    clip = record_html(html, work / f"p{i:02d}_explainer.mp4", want,
                                       resolution="4k" if w >= 3840 else "1440p" if w >= 2560 else "1080p",
                                       viewport={"width": 430, "height": 764} if h > w else None)
                    if duration(clip) <= want * 1.25 + 1.0:
                        break
                    print(f"  explainer recorded {duration(clip):.1f}s for a {want:.1f}s scene (capture stalled); re-recording")
            else:
                clip = (root / part["clip"]).expanduser()
            if not clip.exists():
                sys.exit(f"clip not found: {clip}")
            c = duration(clip)
            is_gif = clip.suffix.lower() == ".gif"
            meta = load_events(clip) if not is_gif else None
            cuts = (loading_cuts(meta) if part.get("cut_loading", True) else []) + \
                [tuple(map(float, x)) for x in part.get("cuts", [])]
            cuts = sorted((max(0.0, a0), min(c, b0)) for a0, b0 in cuts if b0 > a0)
            cut_total = sum(b0 - a0 for a0, b0 in cuts)
            if cuts:
                c -= cut_total
                meta = remap(meta, cuts)
                print(f"  cut {cut_total:.1f}s of page loading")
            fit = part.get("fit", "auto")
            if fit == "auto":
                fit = "stretch" if is_gif else "hold"
            total = max(voiced, c)
            frame = dims(clip) if not is_gif else (w, h)
            same_aspect = abs(frame[0] / frame[1] - w / h) < 0.01
            camera = plan_camera(part, meta, frame) if same_aspect and not is_gif else []
            plan.update(kind="clip", clip=clip, c=c, is_gif=is_gif, meta=meta, cuts=cuts, fit=fit, total=total,
                        frame=frame, same_aspect=same_aspect, camera=camera)
            plan["push"] = [] if (camera or is_gif or not same_aspect or part.get("push") is False) else \
                [(0.0, 1.0, frame[0] * 0.5, frame[1] * 0.5), (total, float(part.get("push_to", 1.035)), frame[0] * 0.52, frame[1] * 0.45)]
        plan["pres_side"] = str(pres_cfg.get("position", "bottom-right"))
        if pool and part.get("presenter", True) is not False:
            height = float(pres_cfg.get("height", 0.25))     # default host size: 25% of the frame height
            # Steps whose target would sit under the presenter: it steps aside for them, as it does for zooms.
            # If one corner would hide it for much of the section, it moves to the other corner instead.
            def overlaps(side: str, plan: dict[str, Any] = plan, height: float = height) -> list[tuple[float, float]]:
                if not plan.get("meta"):
                    return []
                from filmwright.presenter.presenter import body_rect
                x0, y0, x1, y1 = body_rect(plan["frame"], {"position": side, "height": height, "margin": 0.015})
                f = plan["frame"][0] / plan["meta"]["viewport"]["width"]
                out = []
                for e in plan["meta"]["events"]:
                    bx = e.get("box")
                    if bx and bx[0] * f < x1 and (bx[0] + bx[2]) * f > x0 and bx[1] * f < y1 and (bx[1] + bx[3]) * f > y0:
                        out.append((e["t"] - 0.5, e["end"] + 1.0))
                return out
            def hidden_seconds(spans: list[tuple[float, float]]) -> float:
                total, cur = 0.0, None
                for a, b in sorted(spans):
                    if cur and a <= cur[1]:
                        cur[1] = max(cur[1], b)
                    else:
                        if cur:
                            total += cur[1] - cur[0]
                        cur = [a, b]
                return total + (cur[1] - cur[0] if cur else 0.0)
            side = plan["pres_side"]
            hide = overlaps(side)
            if pres_cfg.get("auto_side", True) and hidden_seconds(hide) > 0.35 * plan["total"]:
                other = "bottom-left" if side == "bottom-right" else "bottom-right"
                alt = overlaps(other)
                if hidden_seconds(alt) + 2.0 < hidden_seconds(hide):
                    side, hide = other, alt
                    print(f"  presenter moves to the {other.split('-')[1]} for this section")
            plan["pres_side"] = side
            placement = {"position": side, "height": height, "margin": 0.015}
            if hide:
                print(f"  presenter steps aside for {len(hide)} step(s) under it")
            pool.submit(i, wav=wav if text else None, text=text, seconds=plan["total"], lead=LEAD, voice_seconds=a,
                        camera=plan["camera"], frame=plan["frame"], out_mov=work / f"p{i:02d}_presenter.mov",
                        style=pres_cfg.get("style", "leo"), first=(i == 0), last=(i == len(parts) - 1),
                        kind=plan["kind"], work=work, placement=placement, hide=hide,
                        points=aim_points(part, plan.get("meta"), plan["frame"]) if plan["kind"] == "clip" else None,
                        words=plan.get("words"))
            plan["presenter"] = True
        plans.append(plan)
        print(f"section {i + 1}/{len(parts)}: voice {a:.1f}s, segment {plan['total']:.1f}s")
    if hasattr(voice, "close"):
        voice.close()   # frees the model and lists any sentence that never read back cleanly

    # --- pass 2: encode each section --------------------------------------------------------------
    starts = []
    acc = 0.0
    for plan in plans:
        starts.append(acc)
        acc += plan["total"] - trans_d
    segs, narrs, cues, chapters = [], [], [], []
    stem_src: list[tuple[Path, Path | None, float]] = []   # each section's narration, effects (or none) and length, for stems
    last_i = len(plans) - 1
    for plan, t0 in zip(plans, starts):
        i, part, total, text, wav, a = plan["i"], plan["part"], plan["total"], plan["text"], plan["wav"], plan["a"]
        part_sfx = None
        seg = work / f"p{i:02d}.mp4"
        fade_in = "fade=t=in:st=0:d=0.4," if (keep_fades or i == 0) else ""
        fade_out = f"fade=t=out:st={total - 0.4:.3f}:d=0.4," if (keep_fades or i == last_i) else ""
        pres_mov = None
        if plan["presenter"]:
            pres_mov, source = pool.result(i)
            print(f"  presenter: {source} lip-sync")
        if plan["kind"] == "card":
            png = work / f"p{i:02d}.png"
            (title_card if part["card"] == "title" else closing_card)(
                cfg["title_card" if part["card"] == "title" else "closing_card"], w, h, png)
            inputs = ["-loop", "1", "-framerate", str(FPS), "-i", str(png), "-i", str(wav)]
            chain, src, nxt = "[0:v]format=yuv420p[c0];", "c0", 2
            if pres_mov:
                inputs += ["-i", str(pres_mov)]
                chain += presenter_overlay(nxt, src, "c1", {**pres_cfg, "position": plan["pres_side"]}, w, h)
                src, nxt = "c1", nxt + 1
            filt = chain + f"[{src}]{fade_in}{fade_out}format=yuv420p[v];" + audio_chain(total)
            encode(inputs, filt, total, seg)
            chapters.append((t0, t0 + total, (cfg.get("title_card") or {}).get("title", "Intro") if part["card"] == "title"
                             else (cfg.get("closing_card") or {}).get("title", "Closing")))
        else:
            clip, c, is_gif, meta, cuts, fit = plan["clip"], plan["c"], plan["is_gif"], plan["meta"], plan["cuts"], plan["fit"]
            frame, same_aspect, camera = plan["frame"], plan["same_aspect"], plan["camera"]
            if fit == "stretch":
                timing = f"setpts=PTS*{total / c:.5f},"
            else:  # hold: real-time clip, freeze the last frame for any extra narration
                timing = f"tpad=stop_mode=clone:stop_duration={max(0.0, total - c) + 0.5:.3f},"
            inputs = (["-ignore_loop", "1"] if is_gif else []) + ["-i", str(clip), "-i", str(wav)]
            nxt = 2
            keep = ""
            if cuts:
                expr = "+".join(f"between(t,{a0:.3f},{b0:.3f})" for a0, b0 in cuts)
                keep = f"fps={FPS},select='not({expr})',setpts=N/({FPS}*TB),"
            chain = f"[0:v]{keep}{timing}fps={FPS}[s0];"
            src = "s0"
            ovs = (overlays(part, meta, frame, work, f"p{i:02d}") + moments(part, meta, frame, work, f"p{i:02d}", FPS)) \
                if same_aspect else []
            for k, (png, a0, b0) in enumerate(ovs):
                inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{total + 1:.2f}", "-i", str(png)]
                chain += (f"[{nxt}:v]format=rgba,fade=t=in:st={a0:.2f}:d=0.3:alpha=1,"
                          f"fade=t=out:st={b0 - 0.3:.2f}:d=0.3:alpha=1[ov{k}];"
                          f"[{src}][ov{k}]overlay=0:0:enable='between(t,{a0:.2f},{b0:.2f})'[s{k + 1}];")
                src, nxt = f"s{k + 1}", nxt + 1
            if camera:
                chain += f"[{src}]{zoompan(camera, w, h, FPS)},format=yuv420p[g];"
                print(f"  camera: {sum(1 for kf in camera if kf[1] > 1) // 2} zoom(s)")
            elif plan.get("push") and not part.get("explainer"):
                chain += f"[{src}]{zoompan(plan['push'], w, h, FPS)},format=yuv420p[g];"
            else:
                chain += f"[{src}]{fit_filter(w, h)},format=yuv420p[g];"
            src = "g"
            if pres_mov:
                inputs += ["-i", str(pres_mov)]
                chain += presenter_overlay(nxt, src, "gp", {**pres_cfg, "position": plan["pres_side"]}, w, h)
                src, nxt = "gp", nxt + 1
            if part.get("label"):
                lbl = work / f"p{i:02d}_label.png"
                label_png(part["label"], w, h, lbl, side="right" if plan["pres_side"] == "bottom-left" else "left")
                inputs += ["-loop", "1", "-i", str(lbl)]
                chain += f"[{src}][{nxt}:v]overlay=0:0:enable='lt(t,{float(part.get('label_seconds', 4)):.1f})',format=yuv420p[o];"
                src, nxt = "o", nxt + 1
            sfx_idx = None
            if sfx_on and part.get("sfx", True) is not False:
                cues_sfx = sfx_cues(part, meta, camera) + [(a0 + 0.05, "pop") for _, a0, _ in ovs] + ([(0.0, "swish")] if i > 0 else [])
                if cues_sfx:
                    sfx_wav = sfx_track(cues_sfx, total, work / f"p{i:02d}_sfx.wav", sfx_level, sounds=sfx_sounds)
                    part_sfx = sfx_wav
                    inputs += ["-i", str(sfx_wav)]
                    sfx_idx, nxt = nxt, nxt + 1
            filt = chain + f"[{src}]{fade_in}{fade_out}format=yuv420p[v];" + audio_chain(total, sfx_idx)
            encode(inputs, filt, total, seg)
            if part.get("label"):
                chapters.append((t0, t0 + total, str(part["label"])))
        segs.append(seg)
        narr = work / f"p{i:02d}.narr.wav"
        narr_len = total - (trans_d if plan is not plans[-1] else 0.0)
        run(["ffmpeg", "-y", "-i", str(wav), "-af", f"adelay={int(LEAD * 1000)}|{int(LEAD * 1000)},apad,atrim=0:{narr_len:.3f}",
             "-ar", "48000", "-ac", "2", str(narr)])
        narrs.append(narr)
        stem_src.append((wav, part_sfx, total))
        if text:
            ss = sentences(text)
            chars = sum(len(x) for x in ss) or 1
            cur = t0 + LEAD
            for sen in ss:
                d = a * len(sen) / chars
                cues.append((cur, cur + d, sen))
                cur += d
    if pool:
        pool.close()

    # --- join, music, subtitles, chapters, poster, teaser -----------------------------------------
    joined = work / "joined.mp4"
    if trans_d > 0 and len(segs) > 1:
        lens = [duration(s_) for s_ in segs]
        # Each section's AAC audio decodes with up to 1024 samples of end padding; trimmed to the section's planned
        # length first (to the millisecond, as encode() cut it), or every crossfade would push the narration later
        # than the picture and the captions.
        af = "".join(f"[{k}:a]atrim=0:{plans[k]['total']:.3f},asetpts=PTS-STARTPTS[t{k}];" for k in range(len(segs)))
        vf, pv, pa, off = "", "[0:v]", "[t0]", 0.0
        for k in range(1, len(segs)):
            off += lens[k - 1] - trans_d
            tt = str(parts[k].get("transition", trans_type)) if k < len(parts) else trans_type   # per-section override on the incoming section
            vf += f"{pv}[{k}:v]xfade=transition={tt}:duration={trans_d:.3f}:offset={off:.3f}[v{k}];"
            af += f"{pa}[t{k}]acrossfade=d={trans_d:.3f}:c1=tri:c2=tri[a{k}];"
            pv, pa = f"[v{k}]", f"[a{k}]"
        print(f"transitions: {trans_type}, {trans_d:.1f}s, between {len(segs)} sections")
        run(["ffmpeg", "-y", *sum([["-i", str(s_)] for s_ in segs], []), "-filter_complex", (vf + af).rstrip(";"),   # ffmpeg 5 rejects a trailing ';'
             "-map", pv, "-map", pa, "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-flags:a", "+bitexact", "-b:a", "192k", str(joined)])
    else:
        # Picture: stream-copied. Sound: re-joined from each section trimmed to its length, because a stream copy keeps
        # every section's AAC priming and padding and the narration would drift behind the picture section by section.
        listing = work / "concat.txt"
        listing.write_text("".join(f"file '{p_}'\n" for p_ in segs))
        af = "".join(f"[{k + 1}:a]atrim=0:{plans[k]['total']:.3f},asetpts=PTS-STARTPTS[t{k}];" for k in range(len(segs)))
        af += "".join(f"[t{k}]" for k in range(len(segs))) + f"concat=n={len(segs)}:v=0:a=1[a]"
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), *sum([["-i", str(s_)] for s_ in segs], []),
             "-filter_complex", af, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-flags:a", "+bitexact",
             "-b:a", "192k", str(joined)])
    total_len = duration(joined)
    out_base.parent.mkdir(parents=True, exist_ok=True)
    m4a = out_base.parent / (out_base.name + "-voiceover.m4a")   # narration only: no sound effects, no music
    nlist = work / "narration.txt"
    nlist.write_text("".join(f"file '{p_}'\n" for p_ in narrs))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(nlist), "-c:a", "aac", "-flags:a", "+bitexact", "-b:a", "192k", "-fflags", "+bitexact", "-metadata:s:a:0", "encoder=", str(m4a)])
    stems = bool(cfg.get("stems"))
    from filmwright.core.mix import STEM_NAMES
    for name in STEM_NAMES:                           # never deliver a stem left over from an earlier build
        (out_base.parent / f"{out_base.name}-{name}.wav").unlink(missing_ok=True)
    if stems:
        write_stems(out_base, stem_src, trans_d, work)
    mus = music_plan(cfg)
    if mus:
        joined = add_music(joined, mus, root, total_len, work, [round(t, 3) for t in starts],
                           stem_wav=out_base.parent / (out_base.name + "-music.wav") if stems else None)
        kind = mus.get("file") or (f"{mus['mood']} score on the section cuts" if mus["sync_to_scenes"] else f"{mus['mood']} ambient bed")
        print(f"music: {kind}, {mus['level_lufs']:.0f} LUFS, ducked under the voice")
    srt = out_base.with_suffix(".srt")
    srt.write_text("".join(f"{n}\n{srt_time(a0)} --> {srt_time(b0)}\n{txt}\n\n" for n, (a0, b0, txt) in enumerate(cues, 1)))
    mp4 = out_base.with_suffix(".mp4")
    title = (cfg.get("title_card") or {}).get("title", "Walkthrough")
    chap = chapters_file([(max(0.0, a0), min(total_len, b0), t_) for a0, b0, t_ in chapters], work / "chapters.txt")
    run(["ffmpeg", "-y", "-i", str(joined), "-i", str(srt), "-i", str(chap), "-map", "0", "-map", "1", "-map_chapters", "2",
         "-c", "copy", "-c:s", "mov_text", "-bsf:v", "filter_units=remove_types=6", "-fflags", "+bitexact",
         "-flags:v", "+bitexact", "-flags:a", "+bitexact", "-metadata:s:v:0", "encoder=", "-metadata:s:a:0", "encoder=",
         "-metadata:s:s:0", "language=eng", "-metadata", f"title={title}",
         "-movflags", "+faststart", str(mp4)])   # no encoder/tool tags, no encoder-settings SEI; NOT -map_metadata -1 (it wipes chapter titles)
    from filmwright.core.tags import strip_encoder_tags
    strip_encoder_tags(mp4)
    # poster + teaser: the first zoom moment of the first clip, else a little into the first clip
    first_clip = next((p_ for p_ in plans if p_["kind"] == "clip"), None)
    if first_clip and cfg.get("poster", True) is not False:
        zoom_in = next((kf[0] for kf in first_clip["camera"] if kf[1] > 1.0), None)
        at = starts[first_clip["i"]] + ((zoom_in + 1.0) if zoom_in is not None else min(3.0, first_clip["total"] / 2))
        poster = out_base.parent / (out_base.name + "-poster.png")
        run(["ffmpeg", "-y", "-ss", f"{at:.2f}", "-i", str(mp4), "-frames:v", "1", "-vf", "scale=1920:-2", str(poster)])
        teaser_cfg = cfg.get("teaser", True)
        if teaser_cfg is not False:
            tc = teaser_cfg if isinstance(teaser_cfg, dict) else {}
            secs, width = float(tc.get("seconds", 10)), int(tc.get("width", 640))
            gif = out_base.parent / (out_base.name + "-teaser.gif")
            run(["ffmpeg", "-y", "-ss", f"{max(0.0, at - 2.0):.2f}", "-t", f"{secs:.1f}", "-i", str(mp4), "-vf",
                 f"fps=12,scale={width}:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=5",
                 "-loop", "0", str(gif)])
            print(f"poster + {secs:.0f}s teaser GIF")
    shutil.rmtree(work, ignore_errors=True)
    print(f"\n{mp4} ({duration(mp4):.0f}s, {len(chapters)} chapters)\n{srt}\n{m4a}")
    return 0 if text_check([cfg_path, srt, mp4, m4a], check_mode) else 1


def text_check(paths: list[Path], mode: str) -> bool:
    """Optional lint of the film's text and file metadata (filmwright.core.textcheck): `checks: {tool_names: off|warn|block}`.
    Returns False only when mode is `block` and something was flagged."""
    if mode == "off":
        return True
    try:
        from filmwright.core.textcheck import check
    except ImportError:
        return True
    try:
        check([p for p in paths if Path(p).exists()], mode)
    except Exception as e:                             # block mode raises with the findings
        print(f"film text check failed:\n{e}", file=sys.stderr)
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
