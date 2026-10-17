"""Hybrid films ("both"): animated scenes and real recordings in one narrated film.

    python -m filmwright.hybrid.film <film.yaml> <command> [args] [--settings settings.json]

Commands
  init            write an example film.yaml (fictional brand) next to the given path
  tts             voice each segment's `say` line (cached per sentence)
  stills [t,..]   PNG stills of the animated layer for review (recordings show as black windows)
  render          animated layer, recordings composited into their windows, score, mix, captions, 4K + HD
  verify          duration, resolution, loudness, stray tags, optional text check

film.yaml (see docs/hybrid.md):

    title: Acme Tasks in one minute
    file_prefix: acme-tasks-tour
    brand: {wordmark: ACME TASKS, tagline: Plan less. Do more., colors: {accent: "#7c5cff"}}
    segments:
      - {scene: title, headline: Meet Acme Tasks, sub: Plan less. Do more., say: "..."}
      - {clip: recordings/inbox.mp4, trim: [1.0, 9.0], label: acme-tasks.example, zoom: {at: 1.5, scale: 1.5, x: .7, y: .3}, say: "..."}
      - {scene: steps, title: How it works, items: [...], say: "..."}
      - {scene: stat, value: 11, suffix: " h", label: saved every week, say: "..."}
      - {scene: outro, cta: Try it free, say: "..."}

`--settings` deep-merges a JSON file over film.yaml (voice, music, talking_head, captions, outputs, brand).
"""
from __future__ import annotations

import json
import shutil
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
FRAME = {"x": 200, "y": 150, "w": 1520, "h": 855}     # where a recording sits on the 1920x1080 page


def smooth(p: str) -> str:
    """ffmpeg expression: smoothstep of an expression already clipped to 0..1"""
    return f"(({p})*({p})*(3-2*({p})))"


def zoom_expr(z: dict) -> str:
    """Zoom factor over segment-local time t: ease in to `scale`, hold, ease back out."""
    at, ramp, hold, s = float(z.get("at", 1.0)), float(z.get("ramp", .6)), float(z.get("hold", 2.0)), float(z.get("scale", 1.5))
    p_in = f"clip((t-{at})/{ramp},0,1)"
    p_out = f"clip((t-{at + ramp + hold})/{ramp},0,1)"
    return f"(1+{s - 1}*({smooth(p_in)}-{smooth(p_out)}))"


class Film:
    def __init__(self, spec: Path, settings: Path | None = None):
        self.spec = spec.resolve()
        self.root = self.spec.parent
        cfg = yaml.safe_load(self.spec.read_text()) or {}
        if settings:
            cfg = R.deep_merge(cfg, json.loads(Path(settings).read_text()))
        self.cfg = cfg
        self.segs = [self._norm(s, i) for i, s in enumerate(cfg.get("segments") or [])]
        if not self.segs:
            raise SystemExit(f"{spec}: no segments")
        self.build = self.root / "build"

    def _norm(self, s: dict, i: int) -> dict:
        s = dict(s)
        if "clip" in s:
            s["kind"] = "clip"
            p = Path(str(s["clip"])).expanduser()
            s["path"] = p if p.is_absolute() else self.root / p
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
            h = max(MIN_HOLD.get(s["kind"], 2.0), float(s.get("seconds", 0)))
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
        return {"FILM": {"brand": self.brand(), "segments": segs, "frame": FRAME}}

    def stills(self, times: list[float] | None = None) -> list[Path]:
        _, segs, _ = self.timeline()
        times = times or [round(s["start"] + s["dur"] * .7, 2) for s in segs]
        return R.stills(TEMPLATE, self.page(), times, self.root / "stills")

    def composite(self, frames: Path, segs: list[dict], total: float, out: Path) -> Path:
        """Put each recording into its window: trimmed, fitted, optionally zoomed, frozen on its last frame if
        the narration runs longer, faded in and out with the window."""
        k = 2   # the page renders at 2x (1920x1080 -> 3840x2160)
        fx, fy, fw, fh = FRAME["x"] * k, FRAME["y"] * k, FRAME["w"] * k, FRAME["h"] * k
        ins, chain, cur = ["-i", str(frames)], [], "[0:v]"
        n = 0
        for seg, s in zip(segs, self.segs):
            if s["kind"] != "clip":
                continue
            n += 1
            a = float((s.get("trim") or [s.get("start", 0)])[0])
            d = seg["dur"]
            ins += ["-ss", f"{a:.3f}", "-i", str(s["path"])]
            fit = (f"scale={fw}:{fh}:force_original_aspect_ratio=decrease:flags=lanczos,"
                   f"pad={fw}:{fh}:(ow-iw)/2:(oh-ih)/2:color=black")
            zoom = ""
            if s.get("zoom"):
                z = s["zoom"]
                Z = zoom_expr(z)
                zx, zy = float(z.get("x", .5)), float(z.get("y", .5))
                zoom = (f",scale=w='trunc({fw}*{Z}/2)*2':h='trunc({fh}*{Z}/2)*2':eval=frame:flags=bicubic,"
                        f"crop={fw}:{fh}:x='(trunc({fw}*{Z}/2)*2-{fw})*{zx}':y='(trunc({fh}*{Z}/2)*2-{fh})*{zy}'")
            usable = self.clip_seconds(s)
            chain.append(f"[{n}:v]trim=0:{min(usable, d):.3f},setpts=PTS-STARTPTS,fps={R.FPS},{fit}{zoom},"
                         f"tpad=stop_mode=clone:stop_duration={max(0.0, d - usable) + .1:.3f},trim=0:{d:.3f},format=yuva420p,"
                         f"fade=t=in:st=0:d=0.45:alpha=1,fade=t=out:st={max(0.0, d - .3):.3f}:d=0.3:alpha=1,"
                         f"setpts=PTS+{seg['start']:.3f}/TB[c{n}]")
            chain.append(f"{cur}[c{n}]overlay=x={fx}:y={fy}:eof_action=pass:enable='between(t,{seg['start']:.3f},{seg['start'] + d:.3f})'[o{n}]")
            cur = f"[o{n}]"
        if not n:
            shutil.copyfile(frames, out)
            return out
        R.ffm(*ins, "-filter_complex", ";".join(chain), "-map", cur, "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "10",
              "-pix_fmt", "yuv420p", "-t", f"{total:.3f}", str(out))
        return out

    def render(self) -> list[Path]:
        self.build.mkdir(parents=True, exist_ok=True)
        beats, segs, total = self.timeline()
        for s in self.segs:
            if s["kind"] == "clip" and not s["path"].is_file():
                raise SystemExit(f"recording not found: {s['path']}")
        init = {"FILM": {"brand": self.brand(), "segments": segs, "frame": FRAME}}
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
    elif cmd == "render":
        f.render()
    elif cmd == "verify":
        return 1 if f.verify() else 0
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

