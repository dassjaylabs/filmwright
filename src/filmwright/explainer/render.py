"""Shared machinery for animated films: frame-exact page rendering, narration, music, mix, captions, encode.

Every animated template is an HTML page that exposes ``window.renderAt(t)``, ``window.TOTAL``, ``window.SFX``
(``[[seconds, sound], ...]``) and sets ``window.READY = true``. Frames are captured by seeking, never by playing,
so a re-render is identical to the last one. The story, montage and hybrid pipelines all build on this module.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import mimetypes
import os
import shutil
import subprocess
import sys
import wave
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from filmwright import paths

FPS = int(os.environ.get("FPS", "60"))
WORKERS = int(os.environ.get("WORKERS", "5"))
BPM = 120
BEAT = 60 / BPM
MUSIC_DB_UNDER = -20.0     # the score's level under the narration, before ducking (music.level overrides it)
FONT = paths.FONT_SEMIBOLD
SIZES = {"4k": (3840, 2160, "15"), "hd": (1920, 1080, "16")}

# No encoder or tool tags in finished files.
CLEAN = ["-map_metadata", "-1", "-map_chapters", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
         "-bsf:v", "filter_units=remove_types=6", "-metadata:s:v:0", "encoder=", "-metadata:s:a:0", "encoder=",
         "-metadata:s:v:0", "handler_name=", "-metadata:s:a:0", "handler_name="]


def ffm(*a: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *a], check=True)


def probe_seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as f:
        return f.getnframes() / f.getframerate()


def srt_time(x: float) -> str:
    h, r = divmod(x, 3600)
    m, s = divmod(r, 60)
    ms = int(round((s - int(s)) * 1000))
    if ms == 1000:
        s, ms = int(s) + 1, 0
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"


def write_srt(beats: list[dict], out: Path) -> Path:
    out.write_text("".join(f"{i + 1}\n{srt_time(b['start'])} --> {srt_time(b['start'] + b['dur'])}\n{b['text']}\n\n"
                           for i, b in enumerate(beats) if b.get("text")))
    return out


def deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in (extra or {}).items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def data_url(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


# ---------------------------------------------------------------------------------------------------- brand
DEFAULT_BRAND = {"wordmark": "ACME TASKS", "tagline": "Plan less. Do more.",
                 "colors": {"bg": "#0f1222", "accent": "#7c5cff", "alt": "#22c55e", "warm": "#ff8a4c", "ink": "#f4f5fb"}}


def load_brand(spec: Any, root: Path) -> dict:
    """The page brand: {wordmark, tagline, url, colors{bg, accent, alt, warm, ink}, logo (data URL)}.

    `spec` is a dict in that shape, or the name/path of a brand folder holding brand.yaml (the shared brand kit
    used by every film type). Missing fields fall back to the fictional example brand."""
    if not spec:
        return dict(DEFAULT_BRAND)
    if isinstance(spec, dict):
        b = deep_merge(DEFAULT_BRAND, spec)
        logo = b.get("logo")
        if logo and not str(logo).startswith("data:"):
            p = Path(str(logo)).expanduser()
            p = p if p.is_absolute() else root / p
            b["logo"] = data_url(p) if p.is_file() else None
        return b
    import yaml
    d = paths.brand_dir(spec) if not (root / str(spec) / "brand.yaml").is_file() else (root / str(spec)).resolve()
    y = yaml.safe_load((d / "brand.yaml").read_text()) or {}
    wm = y.get("wordmark") or {}
    word = (wm.get("pre", "") + wm.get("accent", "")) if isinstance(wm, dict) else str(wm or y.get("name", ""))
    cols, themes = y.get("colors") or {}, y.get("themes") or {}
    b = {"wordmark": (word or y.get("name") or DEFAULT_BRAND["wordmark"]).strip().upper(),
         "tagline": (y.get("outro") or {}).get("tagline") or y.get("tagline") or DEFAULT_BRAND["tagline"],
         "url": (y.get("site") or {}).get("public_url") or "",
         "colors": {"bg": cols.get("bg", "#0f1222"), "accent": cols.get("accent", "#7c5cff"),
                    "alt": themes.get("alt") or cols.get("alt") or "#22c55e",
                    "warm": themes.get("warm") or cols.get("warm") or "#ff8a4c", "ink": cols.get("ink", "#f4f5fb")}}
    if y.get("logo") and (d / y["logo"]).is_file():
        b["logo"] = data_url(d / y["logo"])
    return b


# ---------------------------------------------------------------------------------------------------- voice
class Narrator:
    """Narration per sentence through filmwright.core.voice, cached by (voice settings, text)."""

    def __init__(self, cfg: dict | None, root: Path, cache: Path | None = None):
        self.cfg = dict(cfg or {"type": "preset"})
        self.root = root
        self.cache = cache or root / ".tts-cache"
        self.cache.mkdir(parents=True, exist_ok=True)
        self._voice = None

    @property
    def report(self) -> list:
        """Sentences that never read back cleanly (the voice prints them again when it closes)."""
        return list(getattr(self._voice, "report", None) or [])

    def _key(self, text: str) -> str:
        return hashlib.sha1(json.dumps([self.cfg, text], sort_keys=True).encode()).hexdigest()[:16]

    def say(self, text: str, out_wav: Path) -> float:
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        hit = self.cache / f"{self._key(text)}.wav"
        if not hit.exists():
            if self._voice is None:
                from filmwright.core.voice import make_voice
                self._voice = make_voice(self.cfg, root=self.root, cache=self.cache)
            self._voice.say(text, hit)
        shutil.copyfile(hit, out_wav)
        return wav_seconds(out_wav)

    def close(self) -> None:
        if self._voice is not None and hasattr(self._voice, "close"):
            self._voice.close()


def snap_beats(raw: list[dict], tempo: float, first: float, gap: float, extra_gap: dict | None = None,
               min_hold: dict | None = None) -> list[dict]:
    """Place narration beats on the timeline: every scene starts on the music's beat.

    `min_hold` gives a scene a minimum length on screen (its animation needs the time) without stretching the
    narration: `dur` stays the spoken length, used for captions."""
    t, out = first, []
    for b in raw:
        t += (extra_gap or {}).get(b["key"], 0)
        t = math.ceil(t / BEAT - 1e-6) * BEAT
        d = b["dur"] / tempo
        out.append({**b, "start": round(t, 3), "dur": round(d, 3)})
        t += max(d, (min_hold or {}).get(b["key"], 0)) + gap
    return out


# ---------------------------------------------------------------------------------------------------- pages
def page_open(pw: Any, template: Path, init: dict, size: tuple[int, int] = (1920, 1080), dpr: float = 1):
    """Open a template page with `init` assigned onto window before it loads; returns (browser, page)."""
    from filmwright.demo.recorder import launch_kwargs  # the open-source Chromium `filmwright setup` installs
    b = pw.chromium.launch(**launch_kwargs())
    p = b.new_page(viewport={"width": size[0], "height": size[1]}, device_scale_factor=dpr)
    p.add_init_script("".join(f"window.{k} = {json.dumps(v)};" for k, v in init.items()))
    p.goto(template.as_uri())
    p.wait_for_function("window.READY === true", timeout=120000)
    return b, p


def page_info(template: Path, init: dict, size: tuple[int, int] = (1920, 1080)) -> tuple[float, list]:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b, p = page_open(pw, template, init, size)
        total, sfx = p.evaluate("window.TOTAL"), p.evaluate("window.SFX || []")
        b.close()
    return float(total), sfx


def stills(template: Path, init: dict, times: list[float], folder: Path, size: tuple[int, int] = (1920, 1080),
           dpr: float = 1) -> list[Path]:
    from playwright.sync_api import sync_playwright
    folder.mkdir(parents=True, exist_ok=True)
    for f in folder.glob("t*.png"):
        f.unlink()
    out, errs = [], []
    with sync_playwright() as pw:
        b, p = page_open(pw, template, init, size, dpr)
        p.on("pageerror", lambda e: errs.append(str(e)))
        for t in sorted(times):
            p.evaluate(f"renderAt({t})")          # renderAt must return nothing: a returned object is serialised and hangs
            f = folder / f"t{t:06.2f}.png"
            p.screenshot(path=str(f))
            out.append(f)
        b.close()
    if errs:
        print("PAGE ERRORS:", errs[:3], file=sys.stderr)
    return out


def board_panels(beats: list[dict], total: float, images: list[Path], labels: dict[str, str] | None = None,
                 on_screen: dict[str, str] | None = None) -> list[dict]:
    """Storyboard panels for beats on a timeline: each lasts until the next one starts (the last until `total`)."""
    out = []
    for i, (b, img) in enumerate(zip(beats, images)):
        start = 0.0 if i == 0 else b["start"]                  # the first scene is on screen from the first frame
        end = beats[i + 1]["start"] if i + 1 < len(beats) else total
        out.append({"label": (labels or {}).get(b["key"], b["key"].replace("_", " ").capitalize()),
                    "start": round(start, 2), "dur": round(end - start, 2), "text": b.get("text", ""),
                    "on_screen": (on_screen or {}).get(b["key"], ""), "image": str(img)})
    return out


def contact_sheet(rows: list[list[Path]], out: Path, w: int = 384) -> Path:
    from PIL import Image
    h = round(w * 9 / 16)
    cols = max(len(r) for r in rows)
    s = Image.new("RGB", (cols * w, len(rows) * h), "black")
    for r, fs in enumerate(rows):
        for i, f in enumerate(fs):
            s.paste(Image.open(f).convert("RGB").resize((w, h)), (i * w, r * h))
    s.save(out)
    return out


def _chunk(args: tuple) -> str:
    template, init, size, dpr, fps, f0, f1, out = args
    from playwright.sync_api import sync_playwright
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
                           "-c:v", "libx264", "-preset", "medium", "-crf", "10", "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    with sync_playwright() as pw:
        b, p = page_open(pw, Path(template), init, size, dpr)
        for i in range(f0, f1):
            p.evaluate(f"renderAt({i / fps})")
            ff.stdin.write(p.screenshot(type="jpeg", quality=93))
        b.close()
    ff.stdin.close()
    ff.wait()
    return out


def render_frames(template: Path, init: dict, total: float, out_mp4: Path, size: tuple[int, int] = (1920, 1080),
                  fps: int | None = None, workers: int | None = None, dpr: float = 2) -> Path:
    """Render every frame (at 2x the page size, i.e. 4K for a 1920x1080 page) in parallel chunks."""
    fps, workers = fps or FPS, workers or WORKERS
    n = math.ceil(total * fps)
    workers = max(1, min(workers, n // max(1, fps) or 1))
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    edges = [round(n * i / workers) for i in range(workers + 1)]
    jobs = [(str(template), init, size, dpr, fps, edges[i], edges[i + 1], str(out_mp4.parent / f"chunk{i}.mp4")) for i in range(workers)]
    if workers == 1:
        parts = [_chunk(jobs[0])]
    else:
        with ProcessPoolExecutor(workers) as ex:
            parts = list(ex.map(_chunk, jobs))
    lst = out_mp4.parent / "chunks.txt"
    lst.write_text("".join(f"file '{x}'\n" for x in parts))
    ffm("-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out_mp4))
    for x in parts:
        Path(x).unlink(missing_ok=True)
    return out_mp4


# ---------------------------------------------------------------------------------------------------- audio
def narration_track(beats: list[dict], wavs: dict[str, Path], total: float, tempo: float, out: Path) -> Path:
    """Place each beat's narration at its start time, sped up by `tempo`."""
    inputs, filt, used = [], [], []
    for b in beats:
        w = wavs.get(b["key"])
        if not w or not Path(w).exists():
            continue
        i = len(used)
        inputs += ["-i", str(w)]
        ms = int(b["start"] * 1000)
        filt.append(f"[{i}]aresample=48000,atempo={tempo},adelay={ms}|{ms}[v{i}]")
        used.append(b)
    if not used:
        ffm("-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", f"{total:.3f}", str(out))
        return out
    filt.append("".join(f"[v{i}]" for i in range(len(used))) + f"amix=inputs={len(used)}:normalize=0,apad=whole_dur={total}[vo]")
    ffm(*inputs, "-filter_complex", ";".join(filt), "-map", "[vo]", "-ac", "1", "-t", f"{total:.3f}", str(out))
    return out


def soundtrack(build: Path, total: float, cuts: list[float], sfx_cues: list, music: dict | None, vo_wav: Path | None,
               out: Path | None = None, stems: bool = False) -> Path:
    """Score (mood from `music`), effects and narration, mixed and loudness-normalised. With `stems`, the parts are
    also written to build/stems/ as they sit in the mix (see core.mix)."""
    music = dict(music or {})
    mood = str(music.get("mood", "upbeat"))
    mus = None
    if mood != "none":
        from filmwright.core.music import score
        mus = score(build / "music.wav", total, sorted(set(c for c in cuts if c > 0)), mood=mood, bpm=music.get("bpm"),
                    snap=bool(music.get("snap", False)))
    fx = None
    sounds = "off" if music.get("sfx", True) is False else str(music.get("sound_effects", "subtle"))
    if sfx_cues and sounds != "off":
        from filmwright.core.sfx import sfx_track
        fx = sfx_track([(float(t), str(n)) for t, n in sfx_cues], total, build / "sfx.wav", level=0.42, sounds=sounds)
    from filmwright.core.mix import mix
    return mix(vo_wav, out or build / "mix.wav", mus, fx, music_db_under=float(music.get("level", MUSIC_DB_UNDER)),
               sfx_db=float(music.get("sfx_db", -3)), seconds=total, stems_dir=build / "stems" if stems else None)


# ---------------------------------------------------------------------------------------------------- captions + encode
def caption_images(beats: list[dict], W: int, H: int, folder: Path, scale: float = 1.0) -> list[tuple]:
    """Small burned-in captions: ~1.6% of frame height (times `scale`; 1.4 reads on a phone), near-white text
    with a soft outline on a dark strip, centred, 1.75% above the bottom edge, one line wherever it fits (70%
    of the width)."""
    from PIL import Image, ImageDraw, ImageFont
    folder.mkdir(parents=True, exist_ok=True)
    fs = max(14, round(min(W, H) * .016 * (1 if W >= H else 1.15) * float(scale or 1)))
    font = ImageFont.truetype(str(FONT), fs)
    maxw, padx, pady, gap = W * (.7 if W >= H else .86), round(fs * .55), round(fs * .28), round(fs * .25)
    stroke = max(1, round(min(W, H) / 1080))
    out = []
    for i, bt in enumerate(beats):
        if not bt.get("text"):
            continue
        rows, cur = [], ""
        for w in bt["text"].split():
            t = (cur + " " + w).strip()
            if font.getlength(t) <= maxw or not cur:
                cur = t
            else:
                rows.append(cur)
                cur = w
        rows.append(cur)
        lw = max(font.getlength(r) for r in rows)
        asc, desc = font.getmetrics()
        lh = asc + desc
        bw, bh = int(lw + 2 * padx), int(len(rows) * lh + (len(rows) - 1) * gap + 2 * pady)
        im = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        dr = ImageDraw.Draw(im)
        dr.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=round(fs * .45), fill=(10, 12, 24, 165))
        for k, r in enumerate(rows):
            dr.text(((bw - font.getlength(r)) / 2, pady + k * (lh + gap)), r, font=font, fill=(242, 244, 250, 255),
                    stroke_width=stroke, stroke_fill=(10, 12, 24, 120))
        png = folder / f"cap{i}_{W}x{H}.png"
        im.save(png)
        out.append((png, (W - bw) // 2, H - bh - round(H * .0175), bt["start"], bt["start"] + bt["dur"]))
    return out


def encode(frames: Path, mix_wav: Path, beats: list[dict], total: float, out: Path, W: int, H: int, crf: str,
           burn: bool = True, tune: str = "animation", caption_scale: float = 1.0) -> Path:
    caps = caption_images(beats, W, H, frames.parent / "captions", caption_scale) if burn else []
    ins = ["-i", str(frames), "-i", str(mix_wav)]
    chain = [f"[0:v]scale={W}:{H}:flags=lanczos[b0]"]
    for k, (png, x, y, t0, t1) in enumerate(caps):
        ins += ["-i", str(png)]
        chain.append(f"[b{k}][{k + 2}:v]overlay=x={x}:y={y}:enable='between(t,{t0:.3f},{t1:.3f})'[b{k + 1}]")
    chain.append(f"[b{len(caps)}]format=yuv420p[v]")
    ffm(*ins, "-filter_complex", ";".join(chain), "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", crf,
        "-tune", tune, "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", *CLEAN,
        "-t", f"{total:.3f}", str(out))
    return out


def finish(frames: Path, mix_wav: Path, beats: list[dict], total: float, folder: Path, stem: str, settings: dict,
           vo_wav: Path | None = None) -> list[Path]:
    """4K + HD masters (as requested in `outputs`), the .srt, and the optional talking-head overlay."""
    outputs = settings.get("outputs") or ["4k", "hd"]
    caps = settings.get("captions") or {}
    burn = caps.get("burn_in", True) is not False
    cap_scale = float(caps.get("scale") or 1)
    write_srt(beats, folder / f"{stem}.srt")
    made = []
    wanted = [o for o in ("4k", "hd") if o in outputs] or ["hd"]
    th = settings.get("talking_head") or {}
    for name in wanted:
        W, H, crf = SIZES[name]
        f = folder / f"{stem}-{name}.mp4"
        encode(frames, mix_wav, beats, total, f, W, H, crf, burn, caption_scale=cap_scale)
        if th.get("enabled"):
            from filmwright.presenter import overlay_on_video
            tmp = f.with_name(f.stem + ".host.mp4")
            overlay_on_video(f, vo_wav, tmp, th.get("character", "leo"), th.get("corner", "bottom-right"))
            tmp.replace(f)
        made.append(f)
    from filmwright.core.tags import strip_encoder_tags
    for f in made:
        strip_encoder_tags(f)
    if "stems" in outputs:
        made += copy_stems(mix_wav.parent / "stems", folder, stem)
    return made


def copy_stems(src: Path, folder: Path, stem: str) -> list[Path]:
    """<stem>-narration.wav, -music.wav, -sfx.wav beside the film (the parts the film has)."""
    from filmwright.core.mix import STEM_NAMES
    out = []
    for name in STEM_NAMES:
        f, dst = src / f"{name}.wav", folder / f"{stem}-{name}.wav"
        dst.unlink(missing_ok=True)                   # a part this film no longer has must not linger beside it
        if f.is_file():
            shutil.copyfile(f, dst)
            out.append(dst)
    return out


def verify(files: list[Path], srt: Path | None = None, checks: dict | None = None) -> int:
    """Lengths, resolution, loudness, stray encoder tags, and the optional film-text check. Returns the problem count."""
    bad = 0
    for f in files:
        if not f.exists():
            print(f"{f.name}: MISSING")
            bad += 1
            continue

        def q(*a: str, f: Path = f) -> str:
            return subprocess.run(["ffprobe", "-v", "error", *a, str(f)], capture_output=True, text=True).stdout.strip()
        dur = float(q("-show_entries", "format=duration", "-of", "csv=p=0") or 0)
        res = q("-select_streams", "v", "-show_entries", "stream=width,height", "-of", "csv=p=0").rstrip(",")
        lufs = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(f), "-map", "0:a", "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
                              capture_output=True, text=True).stderr
        lufs = next((ln.split()[1] for ln in lufs.splitlines() if ln.strip().startswith("I:")), "?")
        tags = q("-show_entries", "format_tags:stream_tags", "-of", "json").lower()
        tagged = any(k in tags for k in ("lavf", "lavc", "x264", "ffmpeg"))
        bad += tagged
        print(f"{f.name}: {dur:5.1f}s {res} {lufs} LUFS {'tags!' if tagged else 'clean'}")
    mode = str((checks or {}).get("tool_names", "warn"))
    if srt and srt.exists() and mode != "off":
        try:
            from filmwright.core.textcheck import check
            found = check([srt], mode="warn")
            print(f"{srt.name}: text check {'ok' if not found else f'{len(found)} note(s)'}")
        except ImportError:
            pass
    return bad
