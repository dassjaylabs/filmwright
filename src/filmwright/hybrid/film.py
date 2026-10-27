"""Hybrid films ("both"): animated scenes and real recordings in one narrated film.

    python -m filmwright.hybrid.film <film.yaml> <command> [args] [--settings settings.json]

Commands
  init            write an example film.yaml (fictional brand) next to the given path
  tts             voice each segment's `say` line (cached per sentence)
  stills [t,..]   PNG stills of the animated layer for review (recordings show as black windows)
  board           storyboard.json for `filmwright storyboard`: one panel per segment, recordings shown as a frame
  render          animated layer, recordings composited into their windows, score, mix, captions, 4K + HD
  sheet [out]     a frame sheet of the rendered film: two frames per segment with its timing and narration
  verify          duration, resolution, loudness, stray tags, optional text check

film.yaml (see docs/hybrid.md):

    title: Acme Tasks in one minute
    file_prefix: acme-tasks-tour
    brand: {wordmark: ACME TASKS, tagline: Plan less. Do more., colors: {accent: "#7c5cff"}}
    frame: default                  # or wide (phone cuts), or {x, y, w, h} on the 1920x1080 page
    holds: 1.0                      # scale every scene's minimum time on screen (0.75 = brisker)
    segments:
      - {scene: title, headline: Meet Acme Tasks, sub: Plan less. Do more., say: "..."}
      - {clip: recordings/inbox.mp4, trim: [1.0, 9.0], label: acme-tasks.example, zoom: {at: 1.5, scale: 1.5, x: .7, y: .3}, say: "..."}
      - {clip: recordings/list.mp4, trim: [0, 6], pan: {zoom: 2.5, y: .2, stops: [.22, .85]}, say: "..."}
      - {clip: recordings/table.mp4, cam: [[0, 1], [.6, 2.4, .3, .4], [1.8, 2.4], [2.9, 2.4, .8, .4], [4, 2.4]], say: "..."}
      - {scene: steps, title: How it works, items: [...], say: "..."}
      - {scene: stat, value: 11, suffix: " h", label: saved every week, say: "..."}
      - {scene: outro, cta: Try it free, say: "..."}

A clip takes one of three cameras: `zoom` (one push in and out), `pan` (push in, then visit a few stops with a
full second on each: the phone-readable close-up), or `cam` (explicit keyframes `[second, zoom, x, y]`, eased).

`--settings` deep-merges a JSON file over film.yaml (voice, music, talking_head, captions, outputs, brand).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from filmwright import paths
from filmwright.core.names import file_safe
from filmwright.explainer import render as R

TEMPLATE = paths.TEMPLATES / "hybrid" / "scenes.html"
EXAMPLE = paths.TEMPLATES / "hybrid" / "example" / "film.yaml"
SCENES = ("title", "statement", "headline", "steps", "stat", "chart", "device", "ui", "outro")
TEMPO, FIRST, GAP, TAIL = 1.0, 0.4, 0.5, 0.6
MIN_HOLD = {"title": 3.2, "statement": 2.6, "headline": 2.8, "steps": 3.6, "stat": 3.0, "chart": 4.0, "device": 3.6,
            "ui": 5.0, "outro": 4.2, "clip": 2.0}
# Where a recording sits on the 1920x1080 page. `wide` is 5% wider and higher up, clear of the captions: for cuts
# meant to be watched on a phone, where the camera (`pan` / `cam`) does the work of making the app readable.
FRAMES = {"default": {"x": 200, "y": 150, "w": 1520, "h": 855}, "wide": {"x": 160, "y": 84, "w": 1600, "h": 900}}
FRAME = FRAMES["default"]
# Camera paths: a stop stays still for at least CAM_HOLD seconds (a viewer needs a second to read a row), a move
# between stops takes about CAM_MOVE seconds, a push in or out CAM_RAMP.
CAM_HOLD, CAM_MOVE, CAM_RAMP = 1.0, 1.1, 0.6


def smooth(p: str) -> str:
    """ffmpeg expression: smoothstep of an expression already clipped to 0..1"""
    return f"(({p})*({p})*(3-2*({p})))"


def zoom_expr(z: dict) -> str:
    """Zoom factor over segment-local time t: ease in to `scale`, hold, ease back out."""
    at, ramp, hold, s = float(z.get("at", 1.0)), float(z.get("ramp", .6)), float(z.get("hold", 2.0)), float(z.get("scale", 1.5))
    p_in = f"clip((t-{at})/{ramp},0,1)"
    p_out = f"clip((t-{at + ramp + hold})/{ramp},0,1)"
    return f"(1+{s - 1}*({smooth(p_in)}-{smooth(p_out)}))"


def cam_rows(cam: list) -> list[list[float]]:
    """Normalise `cam:` keyframes to [second, zoom, x, y] rows (x, y are fractions of the picture, 0.5 the centre).
    A row may be a list with trailing values left out, or a dict {t, z, x, y}; missing values carry over."""
    rows: list[list[float]] = []
    z, cx, cy = 1.0, .5, .5
    for k in cam:
        if isinstance(k, dict):
            t, z, cx, cy = float(k["t"]), float(k.get("z", z)), float(k.get("x", cx)), float(k.get("y", cy))
        else:
            k = list(k)
            t = float(k[0])
            z = float(k[1]) if len(k) > 1 and k[1] is not None else z
            cx = float(k[2]) if len(k) > 2 and k[2] is not None else cx
            cy = float(k[3]) if len(k) > 3 and k[3] is not None else cy
        if z < 1:
            raise SystemExit(f"cam: zoom must be at least 1 (got {z})")
        if rows and t <= rows[-1][0]:
            raise SystemExit(f"cam: keyframe times must increase ({t} after {rows[-1][0]})")
        rows.append([t, z, cx, cy])
    if not rows:
        raise SystemExit("cam: needs at least one keyframe")
    return rows


def pan_rows(p: dict) -> list[list[float]]:
    """The `pan:` shorthand as `cam:` rows: push in to `zoom` at `at` seconds, then visit each stop (an x, or
    [x, y]) with a hold of at least CAM_HOLD seconds on every stop and a move of `move` seconds between them;
    `out: true` eases back to the wide shot at the end. `at: 0` starts pushed in (the wide shot never shows)."""
    z, y = float(p.get("zoom", 2.5)), float(p.get("y", .5))
    at, ramp = float(p.get("at", .4)), float(p.get("ramp", CAM_RAMP))
    hold, move = max(CAM_HOLD, float(p.get("hold", CAM_HOLD))), float(p.get("move", CAM_MOVE))
    stops = [[float(s), y] if not isinstance(s, (list, tuple)) else [float(s[0]), float(s[1]) if len(s) > 1 else y]
             for s in (p.get("stops") or [[.5, y]])]
    if at > 0:
        rows, t = [[0.0, 1.0, *stops[0]], [at + ramp, z, *stops[0]]], at + ramp
    else:
        rows, t = [[0.0, z, *stops[0]]], 0.0
    for s in stops[1:]:
        t += hold
        rows.append([round(t, 3), z, *rows[-1][2:]])
        t += move
        rows.append([round(t, 3), z, *s])
    t += hold
    rows.append([round(t, 3), z, *rows[-1][2:]])
    if p.get("out"):
        t += ramp
        rows.append([round(t, 3), 1.0, .5, .5])
    return rows


def probe_size(path: Path) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip().split(",")
    return int(out[0]), int(out[1])


def camera_filter(rows: list[list[float]], fw: int, fh: int, src: tuple[int, int], fps: int) -> str:
    """ffmpeg filters that run a `cam` path over a recording and leave it fw x fh. A recording with the window's
    aspect is cropped and scaled straight from its own pixels (a 2.5x push still reads from full resolution);
    any other is fitted into the window first."""
    from filmwright.demo.effects import zoompan
    iw, ih = src
    if abs(iw / ih - fw / fh) < .01:
        return zoompan([(t, z, x * iw, y * ih) for t, z, x, y in rows], fw, fh, fps)
    fit = (f"scale={fw}:{fh}:force_original_aspect_ratio=decrease:flags=lanczos,"
           f"pad={fw}:{fh}:(ow-iw)/2:(oh-ih)/2:color=black")
    return fit + "," + zoompan([(t, z, x * fw, y * fh) for t, z, x, y in rows], fw, fh, fps)


class Film:
    def __init__(self, spec: Path, settings: Path | None = None):
        self.spec = spec.resolve()
        self.root = self.spec.parent
        cfg = yaml.safe_load(self.spec.read_text()) or {}
        if settings:
            cfg = R.deep_merge(cfg, json.loads(Path(settings).read_text()))
        self.cfg = cfg
        self.frame = self._frame(cfg.get("frame"))
        self.hold_scale = float(cfg.get("holds", 1) or 1)
        if not 0.3 <= self.hold_scale <= 3:
            raise SystemExit(f"holds: {self.hold_scale} is out of range (0.3 to 3)")
        self.segs = [self._norm(s, i) for i, s in enumerate(cfg.get("segments") or [])]
        if not self.segs:
            raise SystemExit(f"{spec}: no segments")
        self.build = self.root / "build"

    @staticmethod
    def _frame(spec) -> dict:
        if not spec:
            return dict(FRAME)
        if isinstance(spec, str):
            if spec not in FRAMES:
                raise SystemExit(f"frame: {spec!r} is not one of {', '.join(FRAMES)}")
            return dict(FRAMES[spec])
        if not isinstance(spec, dict) or set(spec) != {"x", "y", "w", "h"}:
            raise SystemExit("frame: give a preset name (default, wide) or {x, y, w, h} in page pixels")
        f = {k: int(spec[k]) for k in ("x", "y", "w", "h")}
        if f["x"] < 0 or f["y"] < 0 or f["x"] + f["w"] > 1920 or f["y"] + f["h"] > 1080 or f["w"] < 320 or f["h"] < 180:
            raise SystemExit("frame: the window must sit inside the 1920x1080 page")
        return f

    def _norm(self, s: dict, i: int) -> dict:
        s = dict(s)
        if "clip" in s:
            s["kind"] = "clip"
            p = Path(str(s["clip"])).expanduser()
            s["path"] = p if p.is_absolute() else self.root / p
            if sum(bool(s.get(k)) for k in ("zoom", "pan", "cam")) > 1:
                raise SystemExit(f"segment {i + 1}: give one camera, zoom, pan or cam")
            if s.get("pan"):
                s["cam"] = pan_rows(dict(s.pop("pan")))
            if s.get("cam"):
                s["cam"] = cam_rows(s["cam"])
                s["seconds"] = max(float(s.get("seconds", 0)), s["cam"][-1][0])   # the path sets a minimum time on screen
        else:
            s["kind"] = str(s.get("scene", "statement"))
            if s["kind"] not in SCENES:
                raise SystemExit(f"segment {i + 1}: unknown scene {s['kind']!r} (choose from {', '.join(SCENES)} or give `clip:`)")
            for k in ("image", "phone_image"):              # device screens: screenshots next to film.yaml
                if s.get(k) and "://" not in str(s[k]):
                    img = Path(str(s[k])).expanduser()
                    img = img if img.is_absolute() else self.root / img
                    if not img.is_file():
                        raise SystemExit(f"segment {i + 1}: {k} {s[k]!r} not found")
                    s[k] = img.resolve().as_uri()
        s["key"] = f"s{i + 1:02d}"
        return s

    @property
    def stem(self) -> str:
        return file_safe(self.cfg.get("file_prefix"), lower=False) or file_safe(self.spec.stem, lower=False) or "film"

    def brand(self) -> dict:
        spec = self.cfg.get("brand")
        b = R.load_brand(spec, self.root)
        for k in ("wordmark", "tagline", "url"):
            if self.cfg.get(k):
                b[k] = self.cfg[k]
        return b

    def clip_seconds(self, s: dict) -> float:
        if s.get("trim"):
            a, b = s["trim"]
            return float(b) - float(a)
        return R.probe_seconds(s["path"]) - float(s.get("start", 0))

    # ------------------------------------------------------------------------------------------ steps
    def tts(self) -> None:
        nar = R.Narrator(self.cfg.get("voice"), self.root)
        out = []
        try:
            for s in self.segs:
                text = str(s.get("say") or "").strip()
                dur = nar.say(text, self.root / "vo" / f"{s['key']}.wav") if text else 0.0
                out.append({"key": s["key"], "text": text, "dur": round(dur, 3)})
                print(f"{s['key']} {s['kind']:9s} {dur:5.2f}s  {text}", flush=True)
        finally:
            nar.close()
        (self.root / "beats.json").write_text(json.dumps(out, indent=1))

    def timeline(self) -> tuple[list[dict], list[dict], float]:
        """(beats for narration and captions, page segments with start/dur, total seconds)"""
        f = self.root / "beats.json"
        if not f.exists():
            raise SystemExit("no narration yet: run `tts` first")
        raw = json.loads(f.read_text())
        hold = {}
        for s in self.segs:
            h = max(MIN_HOLD.get(s["kind"], 2.0) * self.hold_scale, float(s.get("seconds", 0)))
            if s["kind"] == "clip" and s.get("fit") == "clip":
                h = max(h, self.clip_seconds(s))
            hold[s["key"]] = h + .3
        beats = R.snap_beats(raw, float(self.cfg.get("tempo", TEMPO)), FIRST, GAP, None, hold)
        segs = []
        for i, (s, b) in enumerate(zip(self.segs, beats)):
            nxt = beats[i + 1]["start"] if i + 1 < len(beats) else b["start"] + max(b["dur"], hold[s["key"]]) + TAIL
            page = {k: v for k, v in s.items() if k not in ("path", "say", "clip", "scene") and isinstance(v, (str, int, float, list, dict, bool))}
            start = 0.0 if i == 0 else b["start"]          # the first scene is on screen from the first frame
            page.update(kind=s["kind"], start=start, dur=round(nxt - start, 3))
            segs.append(page)
        last = segs[-1]
        return beats, segs, last["start"] + last["dur"] + .6

    def page(self) -> dict:
        _, segs, _ = self.timeline()
        return {"FILM": {"brand": self.brand(), "segments": segs, "frame": self.frame}}

    def stills(self, times: list[float] | None = None) -> list[Path]:
        _, segs, _ = self.timeline()
        times = times or [round(s["start"] + s["dur"] * .7, 2) for s in segs]
        return R.stills(TEMPLATE, self.page(), times, self.root / "stills")

    def board(self) -> Path:
        from filmwright.storyboard import clip_frame, write_json
        beats, segs, total = self.timeline()
        images = self.stills([round(s["start"] + s["dur"] * .7, 2) for s in segs])
        labels, screen = {}, {}
        for i, (s, page) in enumerate(zip(self.segs, segs)):
            labels[s["key"]] = str(s.get("label") or s["kind"]).capitalize()
            screen[s["key"]] = " · ".join(str(x) for k in ("headline", "title", "sub", "cta") if (x := s.get(k)))
            if s.get("items"):
                screen[s["key"]] = (screen[s["key"]] + " · " if screen[s["key"]] else "") + ", ".join(map(str, s["items"]))
            if s["kind"] == "clip" and s.get("path"):          # the recording itself, not the empty window around it
                at = float((s.get("trim") or [s.get("start", 0)])[0]) + min(page["dur"], self.clip_seconds(s)) * .6
                images[i] = clip_frame(Path(s["path"]), at, self.root / "stills" / f"clip-{s['key']}.png") or images[i]
        for b, page in zip(beats, segs):
            b["start"] = page["start"]                         # the panel covers the whole segment
        return write_json(self.root / "storyboard.json",
                          [{"heading": "", "panels": R.board_panels(beats, total - .6, images, labels, screen)}])

    def composite(self, frames: Path, segs: list[dict], total: float, out: Path) -> Path:
        """Put each recording into its window: trimmed, its last frame held if the segment runs longer, fitted,
        its camera (zoom or cam path) applied, faded in and out with the window. The last frame is held *before*
        the camera runs, so a pan can carry on over a recording that has ended."""
        k = 2   # the page renders at 2x (1920x1080 -> 3840x2160)
        fx, fy, fw, fh = (self.frame[c] * k for c in ("x", "y", "w", "h"))
        ins, chain, cur = ["-i", str(frames)], [], "[0:v]"
        n = 0
        for seg, s in zip(segs, self.segs):
            if s["kind"] != "clip":
                continue
            n += 1
            a = float((s.get("trim") or [s.get("start", 0)])[0])
            d = seg["dur"]
            ins += ["-ss", f"{a:.3f}", "-i", str(s["path"])]
            if s.get("cam"):
                look = camera_filter(s["cam"], fw, fh, probe_size(s["path"]), R.FPS)
            else:
                look = (f"scale={fw}:{fh}:force_original_aspect_ratio=decrease:flags=lanczos,"
                        f"pad={fw}:{fh}:(ow-iw)/2:(oh-ih)/2:color=black")
                if s.get("zoom"):
                    z = s["zoom"]
                    Z = zoom_expr(z)
                    zx, zy = float(z.get("x", .5)), float(z.get("y", .5))
                    look += (f",scale=w='trunc({fw}*{Z}/2)*2':h='trunc({fh}*{Z}/2)*2':eval=frame:flags=bicubic,"
                             f"crop={fw}:{fh}:x='(trunc({fw}*{Z}/2)*2-{fw})*{zx}':y='(trunc({fh}*{Z}/2)*2-{fh})*{zy}'")
            usable = self.clip_seconds(s)
            chain.append(f"[{n}:v]trim=0:{min(usable, d):.3f},setpts=PTS-STARTPTS,fps={R.FPS},"
                         f"tpad=stop_mode=clone:stop_duration={max(0.0, d - usable) + .1:.3f},trim=0:{d:.3f},{look},format=yuva420p,"
                         f"fade=t=in:st=0:d=0.45:alpha=1,fade=t=out:st={max(0.0, d - .3):.3f}:d=0.3:alpha=1,"
                         f"setpts=PTS+{seg['start']:.3f}/TB[c{n}]")
            chain.append(f"{cur}[c{n}]overlay=x={fx}:y={fy}:eof_action=pass:enable='between(t,{seg['start']:.3f},{seg['start'] + d:.3f})'[o{n}]")
            cur = f"[o{n}]"
        if not n:
            shutil.copyfile(frames, out)
            return out
        graph = out.with_name("composite_graph.txt")       # a cam path is a long expression: the graph goes in a file
        graph.write_text(";\n".join(chain))
        R.ffm(*ins, "-filter_complex_script", str(graph), "-map", cur, "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "10",
              "-pix_fmt", "yuv420p", "-t", f"{total:.3f}", str(out))
        return out

    def render(self) -> list[Path]:
        self.build.mkdir(parents=True, exist_ok=True)
        beats, segs, total = self.timeline()
        for s in self.segs:
            if s["kind"] == "clip" and not s["path"].is_file():
                raise SystemExit(f"recording not found: {s['path']}")
        init = {"FILM": {"brand": self.brand(), "segments": segs, "frame": self.frame}}
        total, sfx = R.page_info(TEMPLATE, init)
        print(f"hybrid: {total:.2f}s, {len(segs)} segments ({sum(s['kind'] == 'clip' for s in self.segs)} recordings)", flush=True)
        R.render_frames(TEMPLATE, init, total, self.build / "frames.mp4")
        self.composite(self.build / "frames.mp4", segs, total, self.build / "composite.mp4")
        vo = R.narration_track(beats, {b["key"]: self.root / "vo" / f"{b['key']}.wav" for b in beats if b.get("text")}, total,
                               float(self.cfg.get("tempo", TEMPO)), self.build / "vo.wav")
        R.soundtrack(self.build, total, [s["start"] for s in segs[1:]], sfx, self.cfg.get("music"), vo,
                     stems="stems" in (self.cfg.get("outputs") or []))
        made = R.finish(self.build / "composite.mp4", self.build / "mix.wav", [b for b in beats if b.get("text")], total,
                        self.root, self.stem, self.cfg, vo)
        print("done:", ", ".join(f.name for f in made), flush=True)
        return made

    def sheet(self, out: Path | None = None) -> Path:
        """A frame sheet of the rendered film for review: two frames per segment (one near its start, one at
        62% through), each with the segment's kind, timing and narration. Frame 1 is marked as the thumbnail."""
        import textwrap

        from PIL import Image, ImageDraw, ImageFont
        _, segs, total = self.timeline()
        mp4 = self.root / f"{self.stem}-hd.mp4"
        if not mp4.is_file():
            mp4 = self.root / f"{self.stem}-4k.mp4"
        if not mp4.is_file():
            raise SystemExit(f"no film yet: run `render` first ({self.stem}-hd.mp4)")
        accent = (self.brand().get("colors") or {}).get("accent", "#7c5cff")
        W, FW, FH, COLS, PH = 1920, 448, 252, 4, 252 + 150
        panels = []
        for i, (seg, s) in enumerate(zip(segs, self.segs)):
            times = [0.0, seg["dur"] * .62] if i == 0 else [seg["start"] + .9, seg["start"] + seg["dur"] * .62]
            for j, t in enumerate(times):
                panels.append({"n": f"{i + 1}.{j + 1}", "t": min(t, total - .05), "kind": seg["kind"],
                               "label": "Thumbnail (frame 1)" if (i == 0 and j == 0) else "",
                               "say": s.get("say", "") if j == 0 else "", "seg": f"{seg['start']:.1f}–{seg['start'] + seg['dur']:.1f} s"})
        rows = (len(panels) + COLS - 1) // COLS
        img = Image.new("RGB", (W, 150 + rows * (PH + 24) + 40), "#0d1117")
        d = ImageDraw.Draw(img)

        def font(f: Path, size: int):
            return ImageFont.truetype(str(f), size)
        d.text((40, 36), f"Frame sheet · {self.cfg.get('title') or self.stem}", font=font(paths.FONT_SEMIBOLD, 40), fill="#eef2f7")
        d.text((40, 92), f"{mp4.name} · {total:.0f} s · {len(segs)} segments", font=font(paths.FONT_REGULAR, 20), fill="#8fa0b5")
        tmp = self.build / "sheet_tmp.png"
        tmp.parent.mkdir(exist_ok=True)
        for k, p in enumerate(panels):
            x, y = 40 + (k % COLS) * (FW + 24), 150 + (k // COLS) * (PH + 24)
            d.rounded_rectangle([x - 8, y - 8, x + FW + 8, y + PH], radius=12, fill="#161b22")
            R.ffm("-ss", f"{p['t']:.2f}", "-i", str(mp4), "-frames:v", "1", "-vf", f"scale={FW}:-1", str(tmp))
            img.paste(Image.open(tmp).convert("RGB"), (x, y))
            d.text((x, y + FH + 10), f"{p['n']}  {p['kind']}", font=font(paths.FONT_SEMIBOLD, 18), fill=accent)
            d.text((x + FW, y + FH + 12), f"{p['seg']}  ·  frame @ {p['t']:.1f} s", font=font(paths.FONT_REGULAR, 15), fill="#8fa0b5", anchor="ra")
            body = " · ".join(t for t in [p["label"], f"VO: {p['say']}" if p["say"] else ""] if t) or "(continues)"
            yy = y + FH + 38
            for line in textwrap.wrap(body, 52)[:6]:
                d.text((x, yy), line, font=font(paths.FONT_REGULAR, 16), fill="#eef2f7" if (p["say"] or p["label"]) else "#8fa0b5")
                yy += 21
        tmp.unlink(missing_ok=True)
        out = out or self.root / f"{self.stem}-sheet.png"
        img.save(out)
        return out

    def verify(self) -> int:
        names = [o for o in (self.cfg.get("outputs") or ["4k", "hd"]) if o in ("4k", "hd")] or ["hd"]
        bad = R.verify([self.root / f"{self.stem}-{n}.mp4" for n in names], self.root / f"{self.stem}.srt", self.cfg.get("checks"))
        print("all good" if not bad else f"{bad} file(s) need a look")
        return bad


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    settings = None
    if "--settings" in argv:
        i = argv.index("--settings")
        settings = Path(argv[i + 1])
        del argv[i:i + 2]
    if len(argv) < 2:
        print(__doc__)
        return 2
    spec, cmd = Path(argv[0]).expanduser(), argv[1]
    if cmd == "init":
        spec.parent.mkdir(parents=True, exist_ok=True)
        if not spec.exists():
            shutil.copyfile(EXAMPLE, spec)
        print("edit", spec)
        return 0
    f = Film(spec, settings)
    if cmd == "tts":
        f.tts()
    elif cmd == "stills":
        times = [float(x) for x in argv[2].split(",")] if len(argv) > 2 else None
        for p in f.stills(times):
            print(p)
    elif cmd == "board":
        print(f.board())
    elif cmd == "render":
        f.render()
    elif cmd == "sheet":
        print(f.sheet(Path(argv[2]) if len(argv) > 2 else None))
    elif cmd == "verify":
        return 1 if f.verify() else 0
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
