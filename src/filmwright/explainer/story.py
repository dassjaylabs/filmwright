"""Story films: one short, fully animated, character-led film per use case.

    python -m filmwright.explainer.story <project-dir> <command> [args] [--settings settings.json]

Commands
  init                      write project.json and stories.json from the bundled example
  tts      [n,..|all]       write the narration per story and voice it (cached per sentence)
  stills   <n> [t,..]       PNG stills for review (default: one per beat plus the payoff)
  sheet    [n,..|all]       a contact sheet of the default stills, one row per story
  board    [n,..|all]       storyboard.json for `filmwright storyboard`: one panel per beat (run tts first)
  render   [n,..|all]       frames, music, mix, captions, final 4K + HD files
  recaption [n,..|all]      redo only the final encode (caption changes), from the kept frames and mix
  verify   [n,..|all]       duration, resolution, loudness, stray tags, optional text check

`--settings` deep-merges a JSON file over project.json (filmwright build uses it to pass the reel.yaml voice,
music, talking head, captions, outputs and brand). Environment: FPS (default 60), WORKERS (default 5).
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from filmwright import paths
from filmwright.core.names import file_safe
from filmwright.explainer import render as R

TEMPLATE = paths.TEMPLATES / "story" / "story.html"
EXAMPLE = paths.TEMPLATES / "story" / "example"
TEMPO, FIRST, GAP = 1.06, 0.6, 0.28
EXTRA_GAP = {"setup": 0.2, "result": 0.1, "before": 0.2, "after": 0.1}
# seconds each scene's animation needs on screen, however short its sentence
MIN_HOLD = {"meet": 2.4, "ping": 3.0, "pile": 3.6, "cost": 3.8, "workaround": 4.4, "setup": 5.6, "before": 5.0, "after": 5.6}
DEFAULT_WALLS = [["#EEF1FF", "#DCE2FA"], ["#F3EFFF", "#E3DAFF"], ["#FFF6E9", "#FBE6C6"], ["#ECFAF4", "#D2F0E3"],
                 ["#FFF1EC", "#FADBD0"], ["#EEF6FF", "#D5E7FF"]]
SHAPES = {"A": ["meet", "pile", "cost", "workaround", "setup", "result"],
          "B": ["ping", "pile", "cost", "workaround", "setup", "result"],
          "C": ["meet", "before", "after", "result"]}


class Project:
    def __init__(self, root: Path, settings: Path | None = None):
        self.root = root.resolve()
        cfg = json.loads((self.root / "project.json").read_text())
        if settings:
            cfg = R.deep_merge(cfg, json.loads(Path(settings).read_text()))
        self.cfg = cfg
        self.stories = {s["n"]: s for s in json.loads((self.root / "stories.json").read_text())}
        self._brand = None

    @property
    def brand(self) -> dict:
        if self._brand is None:
            spec = self.cfg.get("brand")
            b = R.load_brand(spec, self.root)
            if not spec:
                b["wordmark"] = self.cfg["product"].upper()
            for k in ("wordmark", "tagline", "url"):        # project.json values win over the brand kit
                if self.cfg.get(k):
                    b[k] = self.cfg[k]
            self._brand = b
        return self._brand

    def outdir(self, c: dict) -> Path:
        return self.root / f"{c['n']:02d}-{self.slug(c)}"

    def arch(self, c: dict) -> str:
        shapes = self.cfg.get("archetypes", "ABC")
        return c.get("arch") or shapes[(c["n"] - 1) % len(shapes)]

    def slug(self, c: dict) -> str:
        return file_safe(c.get("slug"), lower=False) or f"story-{c['n']}"

    def stem(self, c: dict) -> str:
        prefix = file_safe(self.cfg.get("file_prefix"), lower=False) or file_safe(self.cfg["product"]) or "film"
        return f"{prefix}-{self.slug(c)}"

    def page_config(self, c: dict) -> dict:
        walls = self.cfg.get("walls", DEFAULT_WALLS)
        group = self.cfg.get("stories_per_palette", 3)
        return dict(c, arch=self.arch(c), wall=c.get("wall") or walls[((c["n"] - 1) // group) % len(walls)],
                    product=self.cfg["product"], brand=self.brand)

    def lines(self, c: dict) -> dict:
        """Narration per beat. Any beat can be overridden with "lines": {key: text} in the story."""
        name, pron, poss, prod = c["name"], c["pron"], c["poss"], self.cfg["product"]
        action, stakes = c["action"], c["stakes"]
        setup = c.get("setupLine") or f"So {name} sets up {prod}. It brings everything into one place and keeps it up to date."
        work = c.get("workaroundLine") or f"And the usual workaround? Not good enough when {stakes}."
        result = c.get("resultLine") or f"Now {pron.lower()} {action}, and it's done in seconds."
        a = self.arch(c)
        if a == "B":
            out = {"ping": f"It's three o'clock, and {name}'s manager needs {c.get('need', 'an answer')} by five.",
                   "pile": c["problem"], "cost": c["cost"], "workaround": work, "setup": setup,
                   "result": c.get("resultLine") or f"{pron} {action}, and it's done in minutes, with hours to spare."}
        elif a == "C":
            old = c["cost"].rstrip(".")
            out = {"meet": f"Meet {name}. {pron} {c['roleLine']}",
                   "before": f"The old way: {old[0].lower() + old[1:]}. Not good enough when {stakes}.",
                   "after": c.get("afterLine") or f"The {prod} way: {poss} work lives in one place, and it stays up to date.",
                   "result": result}
        else:
            out = {"meet": f"Meet {name}. {pron} {c['roleLine']}", "pile": c["problem"], "cost": c["cost"],
                   "workaround": work, "setup": setup, "result": result}
        out.update(c.get("lines", {}))
        return {k: out[k] for k in SHAPES[a] if k in out}

    # ------------------------------------------------------------------------------------------ steps
    def tts(self, ns: list[int]) -> None:
        nar = R.Narrator(self.cfg.get("voice"), self.root)
        try:
            for n in ns:
                c = self.stories[n]
                d = self.outdir(c)
                (d / "vo").mkdir(parents=True, exist_ok=True)
                out = []
                for key, text in self.lines(c).items():
                    dur = nar.say(text, d / "vo" / f"{key}.wav")
                    out.append({"key": key, "text": text, "dur": round(dur, 3)})
                (d / "beats.json").write_text(json.dumps(out, indent=1))
                print(f"{n:02d} {c['name']:10s} shape {self.arch(c)}  speech {sum(b['dur'] for b in out):5.1f}s", flush=True)
            for line in nar.report:
                print("WEAK (listen to this sentence):", line, flush=True)
        finally:
            nar.close()

    def beats(self, c: dict) -> list[dict]:
        f = self.outdir(c) / "beats.json"
        if not f.exists():
            raise SystemExit(f"no narration for story {c['n']} yet: run `tts {c['n']}` first")
        return R.snap_beats(json.loads(f.read_text()), float(self.cfg.get("tempo", TEMPO)), FIRST, GAP, EXTRA_GAP, MIN_HOLD)

    def init(self, c: dict) -> dict:
        return {"UC": self.page_config(c), "BEATS": self.beats(c)}

    def default_times(self, c: dict) -> list[float]:
        bs = self.beats(c)
        ts = [bt["start"] + bt["dur"] * .7 for bt in bs]
        res = next(bt for bt in bs if bt["key"] == "result")
        return [round(t, 2) for t in ts + [res["start"] + 6.8]]

    def stills(self, n: int, times: list[float] | None = None) -> list[Path]:
        c = self.stories[n]
        return R.stills(TEMPLATE, self.init(c), times or self.default_times(c), self.outdir(c) / "stills")

    def sheet(self, ns: list[int]) -> Path:
        out = R.contact_sheet([self.stills(n) for n in ns], self.root / "contact-sheet.png")
        print(out)
        return out

    def board(self, ns: list[int]) -> Path:
        from filmwright.storyboard import write_json
        groups = []
        for n in ns:
            c = self.stories[n]
            init = self.init(c)
            bs = init["BEATS"]
            total, _ = R.page_info(TEMPLATE, init)
            images = R.stills(TEMPLATE, init, [round(b["start"] + b["dur"] * .7, 2) for b in bs], self.outdir(c) / "stills")
            groups.append({"heading": f"Story {n}: {self.slug(c).replace('-', ' ')} (shape {self.arch(c)}, {total:.0f}s)",
                           "panels": R.board_panels(bs, total, images)})
        return write_json(self.root / "storyboard.json", groups)

    def render(self, n: int) -> list[Path]:
        c = self.stories[n]
        d = self.outdir(c)
        B = d / "build"
        B.mkdir(parents=True, exist_ok=True)
        init = self.init(c)
        total, sfx = R.page_info(TEMPLATE, init)
        print(f"{n:02d} {self.slug(c)}: {total:.2f}s, shape {self.arch(c)}", flush=True)
        R.render_frames(TEMPLATE, init, total, B / "frames.mp4")
        bs = init["BEATS"]
        vo = R.narration_track(bs, {b["key"]: d / "vo" / f"{b['key']}.wav" for b in bs}, total,
                               float(self.cfg.get("tempo", TEMPO)), B / "vo.wav")
        R.soundtrack(B, total, [b["start"] for b in bs[1:]], sfx, self.cfg.get("music"), vo,
                     stems="stems" in (self.cfg.get("outputs") or []))
        (B / "total.txt").write_text(f"{total}")
        made = R.finish(B / "frames.mp4", B / "mix.wav", bs, total, d, self.stem(c), self.cfg, vo)
        print(f"{n:02d} done: {', '.join(f.name for f in made)}", flush=True)
        return made

    def recaption(self, n: int) -> list[Path]:
        c = self.stories[n]
        d = self.outdir(c)
        total = float((d / "build" / "total.txt").read_text())
        return R.finish(d / "build" / "frames.mp4", d / "build" / "mix.wav", self.beats(c), total, d, self.stem(c), self.cfg,
                        d / "build" / "vo.wav")

    def verify(self, ns: list[int]) -> int:
        bad = 0
        for n in ns:
            c = self.stories[n]
            d = self.outdir(c)
            wanted = [o for o in ("4k", "hd") if o in (self.cfg.get("outputs") or ["4k", "hd"])] or ["hd"]
            bad += R.verify([d / f"{self.stem(c)}-{o}.mp4" for o in wanted], d / f"{self.stem(c)}.srt", self.cfg.get("checks"))
        print("all good" if not bad else f"{bad} file(s) need a look")
        return bad


def init_project(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name in ("project.json", "stories.json"):
        if not (root / name).exists():
            shutil.copyfile(EXAMPLE / name, root / name)
    print("edit", root / "project.json", "and", root / "stories.json")


def pick(arg: str | None, stories: dict) -> list[int]:
    return sorted(stories) if arg in (None, "all") else [int(x) for x in arg.split(",")]


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
    root, cmd = Path(argv[0]).expanduser(), argv[1]
    arg = argv[2] if len(argv) > 2 else None
    if cmd == "init":
        init_project(root)
        return 0
    p = Project(root, settings)
    if cmd == "tts":
        p.tts(pick(arg, p.stories))
    elif cmd == "stills":
        times = [float(x) for x in argv[3].split(",")] if len(argv) > 3 else None
        for f in p.stills(int(arg), times):
            print(f)
    elif cmd == "sheet":
        p.sheet(pick(arg, p.stories))
    elif cmd == "board":
        print(p.board(pick(arg, p.stories)))
    elif cmd == "render":
        for n in pick(arg, p.stories):
            p.render(n)
    elif cmd == "recaption":
        for n in pick(arg, p.stories):
            p.recaption(n)
            print(f"{n:02d} recaptioned", flush=True)
    elif cmd == "verify":
        return 1 if p.verify(pick(arg, p.stories)) else 0
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
