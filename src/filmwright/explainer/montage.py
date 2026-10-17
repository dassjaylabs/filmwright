"""Feature montage: many features of one product in about a minute, natively laid out for 16:9, 9:16 and 1:1.

    python -m filmwright.explainer.montage <project-dir> <command> [args] [--settings settings.json]

Commands
  init                 write montage.json from the bundled example
  tts                  voice the narration (intro, one line per feature, close); cached per sentence
  stills [t,..] [--aspect 9x16|1x1]   PNG stills for review (default: one per scene)
  board                               storyboard.json for `filmwright storyboard`: one panel per scene
  render               the 16:9 film (4K + HD as requested), then 9:16 and 1:1 when `outputs` asks for
                       vertical / square; all three share one soundtrack, so their timing is identical
  verify               duration, resolution, loudness, stray tags, optional text check

Everything that changes per film lives in montage.json: product, brand, headline, features (title, label, art,
points, narration line), close line, call to action and footnote. `--settings` deep-merges a JSON file over it.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from filmwright import paths
from filmwright.core.names import file_safe
from filmwright.explainer import render as R

TEMPLATE = paths.TEMPLATES / "montage" / "montage.html"
EXAMPLE = paths.TEMPLATES / "montage" / "example" / "montage.json"
TEMPO, FIRST, GAP = 1.03, 0.5, 0.42
EXTRA_GAP = {"close": 0.45}
ARTS = ("calendar", "chat", "chart", "checklist", "bell", "people", "flow", "lock")
ASPECTS = {"16x9": (1920, 1080), "9x16": (1080, 1920), "1x1": (1080, 1080)}
NATIVE = {"vertical": "9x16", "square": "1x1"}


class Montage:
    def __init__(self, root: Path, settings: Path | None = None):
        self.root = root.resolve()
        cfg = json.loads((self.root / "montage.json").read_text())
        if settings:
            cfg = R.deep_merge(cfg, json.loads(Path(settings).read_text()))
        self.cfg = cfg
        self.build = self.root / "build"

    @property
    def stem(self) -> str:
        return (file_safe(self.cfg.get("file_prefix"), lower=False)
                or (file_safe(self.cfg["product"]) or "film") + "-montage")

    def brand(self) -> dict:
        spec = self.cfg.get("brand")
        b = R.load_brand(spec, self.root)
        if not spec:
            b["wordmark"] = self.cfg["product"].upper()
        for k in ("wordmark", "tagline", "url"):
            if self.cfg.get(k):
                b[k] = self.cfg[k]
        return b

    def features(self) -> list[dict]:
        out = []
        for i, f in enumerate(self.cfg["features"]):
            f = dict(f)
            f.setdefault("key", f"f{i + 1}")
            f.setdefault("art", ARTS[i % len(ARTS)])
            out.append(f)
        return out

    def lines(self) -> list[tuple[str, str]]:
        return [("intro", self.cfg["intro"])] + [(f["key"], f["line"]) for f in self.features()] + [("close", self.cfg["close"])]

    def page(self, aspect: str = "16x9") -> dict:
        mc = {k: self.cfg.get(k) for k in ("headline", "cta", "footnote")}
        mc.update(brand=self.brand(), features=self.features())
        return {"MC": mc, "BEATS": self.beats(), "ASPECT": aspect}

    def tts(self) -> None:
        nar = R.Narrator(self.cfg.get("voice"), self.root)
        out = []
        try:
            for key, text in self.lines():
                dur = nar.say(text, self.root / "vo" / f"{key}.wav")
                out.append({"key": key, "text": text, "dur": round(dur, 3)})
                print(f"{key:12s} {dur:5.2f}s  {text}", flush=True)
        finally:
            nar.close()
        (self.root / "beats.json").write_text(json.dumps(out, indent=1))
        print("total speech", round(sum(b["dur"] for b in out), 2), "s")

    def beats(self) -> list[dict]:
        f = self.root / "beats.json"
        if not f.exists():
            raise SystemExit("no narration yet: run `tts` first")
        hold = {f["key"]: 3.6 for f in self.features()}
        hold["intro"] = 4.0
        return R.snap_beats(json.loads(f.read_text()), float(self.cfg.get("tempo", TEMPO)), FIRST, GAP, EXTRA_GAP, hold)

    def stills(self, times: list[float] | None = None, aspect: str = "16x9") -> list[Path]:
        bs = self.beats()
        times = times or [round(b["start"] + max(b["dur"], 3.6) * .8, 2) for b in bs]
        return R.stills(TEMPLATE, self.page(aspect), times, self.root / "stills" / aspect, ASPECTS[aspect])

    def board(self) -> Path:
        from filmwright.storyboard import write_json
        bs, page = self.beats(), self.page()
        total, _ = R.page_info(TEMPLATE, page)
        images = self.stills([round(b["start"] + max(b["dur"], 3.6) * .8, 2) for b in bs])
        labels = {"intro": "Intro", "close": "Close", **{f["key"]: f.get("title", f["key"]) for f in self.features()}}
        return write_json(self.root / "storyboard.json", [{"heading": "", "panels": R.board_panels(bs, total, images, labels)}])

    def render(self) -> list[Path]:
        self.build.mkdir(parents=True, exist_ok=True)
        init = self.page("16x9")
        total, sfx = R.page_info(TEMPLATE, init)
        bs = init["BEATS"]
        print(f"montage: {total:.2f}s, {len(bs) - 2} features", flush=True)
        R.render_frames(TEMPLATE, init, total, self.build / "frames.mp4")
        vo = R.narration_track(bs, {b["key"]: self.root / "vo" / f"{b['key']}.wav" for b in bs}, total,
                               float(self.cfg.get("tempo", TEMPO)), self.build / "vo.wav")
        R.soundtrack(self.build, total, [b["start"] - .35 for b in bs[1:]], sfx, self.cfg.get("music"), vo,
                     stems="stems" in (self.cfg.get("outputs") or []))
        (self.build / "total.txt").write_text(f"{total}")
        made = R.finish(self.build / "frames.mp4", self.build / "mix.wav", bs, total, self.root, self.stem, self.cfg, vo)
        burn = (self.cfg.get("captions") or {}).get("burn_in", True) is not False
        for out, aspect in NATIVE.items():
            if out not in (self.cfg.get("outputs") or []):
                continue
            w, h = ASPECTS[aspect]
            frames = self.build / f"frames-{aspect}.mp4"
            R.render_frames(TEMPLATE, self.page(aspect), total, frames, (w, h))
            f = self.root / f"{self.stem}-{out}.mp4"
            R.encode(frames, self.build / "mix.wav", bs, total, f, w, h, "17", burn)
            made.append(f)
        print("done:", ", ".join(f.name for f in made), flush=True)
        return made

    def verify(self) -> int:
        names = [o for o in (self.cfg.get("outputs") or ["4k", "hd"]) if o in ("4k", "hd", "vertical", "square")] or ["hd"]
        bad = R.verify([self.root / f"{self.stem}-{n}.mp4" for n in names], self.root / f"{self.stem}.srt", self.cfg.get("checks"))
        print("all good" if not bad else f"{bad} file(s) need a look")
        return bad


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = {}
    for flag in ("--settings", "--aspect"):
        if flag in argv:
            i = argv.index(flag)
            opts[flag] = argv[i + 1]
            del argv[i:i + 2]
    if len(argv) < 2:
        print(__doc__)
        return 2
    root, cmd = Path(argv[0]).expanduser(), argv[1]
    if cmd == "init":
        root.mkdir(parents=True, exist_ok=True)
        if not (root / "montage.json").exists():
            shutil.copyfile(EXAMPLE, root / "montage.json")
        print("edit", root / "montage.json")
        return 0
    m = Montage(root, Path(opts["--settings"]) if "--settings" in opts else None)
    if cmd == "tts":
        m.tts()
    elif cmd == "stills":
        times = [float(x) for x in argv[2].split(",")] if len(argv) > 2 else None
        for f in m.stills(times, opts.get("--aspect", "16x9")):
            print(f)
    elif cmd == "board":
        print(m.board())
    elif cmd == "render":
        m.render()
    elif cmd == "verify":
        return 1 if m.verify() else 0
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
