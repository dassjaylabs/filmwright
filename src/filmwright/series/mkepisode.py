#!/usr/bin/env python3
"""Build one episode of a numbered demo series from a short spec.

    python -m filmwright.series.mkepisode gen    spec.yaml      write scenarios.yaml, video.yaml and the branded intro/outro
    python -m filmwright.series.mkepisode record spec.yaml [--only S01,S02]   run the scenarios and record them
    python -m filmwright.series.mkepisode build  spec.yaml      narrate and build the film (4K master + .srt)
    python -m filmwright.series.mkepisode social spec.yaml      1080p cut with burned-in captions + the post caption file

Spec fields (YAML):
  dir, slug, episode, of, title: [HEAD1, HEAD2], tagline, next (title of the next episode or ""),
  cast: [manager, builder, marketer, you] (any of manager, lead, consultant, you, builder, marketer, reviewer, host,
        analyst, reader, in the order the narration names them; or {look, name} for your own label),
  tile: trend|flag, intro_text, outro_text, outro_line, redact: [extra selectors],
  after_intro: [raw video.yaml sections], scenarios: [...scenario-dsl...], sections: [{clip: S01, label, text, focus, callouts, spotlight}],
  caption, hashtags: for the social post.
  brand: <name or folder>  (optional: otherwise series.yaml's brand, else the bundled example) selects a brand.yaml: palette,
  logo, wordmark, site to record, sign-in, what to blur, host, effect switches, outro line, caption disclaimer.
  voice: the narration voice (same fields as reel.yaml's `voice:`); music: {mood: ...}. See docs/series.md.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from filmwright.core.names import checked_slug
from filmwright.paths import TEMPLATES
from filmwright.series import brandkit

SCENES = TEMPLATES / "brand-scenes"
PY = sys.executable
VOICE = {"type": "preset", "speaker": "ryan",
         "style": "Natural, relaxed and conversational, like a friendly colleague explaining something. Even pace, no dramatic emphasis."}
CAST_NAMES = {"manager": "Manager", "lead": "Lead", "consultant": "Consultant", "you": "You", "builder": "Builder",
              "marketer": "Marketer", "reviewer": "Reviewer", "host": "Host", "analyst": "Analyst", "reader": "Reader"}
DEFAULT_CAST = ["manager", "builder", "marketer", "you"]
SCENES_DIR = SCENES / "scenes"


def find_series_dir(spec_path: Path) -> Path | None:
    for d in (spec_path.parent, spec_path.parent.parent):
        if (d / "series.yaml").exists():
            return d
    return None


def load(spec_path: Path) -> dict:
    spec = yaml.safe_load(spec_path.read_text())
    try:
        spec["slug"] = checked_slug(spec.get("slug"), f"{spec_path.name}: slug")
    except ValueError as e:
        raise SystemExit(str(e)) from None
    spec["_dir"] = Path(str(spec["dir"])).expanduser()
    spec["_series"] = find_series_dir(spec_path.resolve())
    name = spec.get("brand")
    if not name and spec["_series"]:
        name = yaml.safe_load((spec["_series"] / "series.yaml").read_text()).get("brand")
    if name and spec["_series"] and not Path(str(name)).expanduser().is_absolute() and (spec["_series"] / str(name)).exists():
        name = spec["_series"] / str(name)                # a brand folder next to series.yaml
    spec["_brand"] = brandkit.load_brand(name or "example")
    return spec


def effects(brand: dict) -> dict:
    return {"sfx": True, "jingle": False, "verified_badges": False, "callouts": True, **(brand.get("effects") or {})}


def brand_params(brand: dict) -> dict:
    """What the scenes need to know about the brand (PARAMS.brand). A native brand adds nothing that changes the artwork."""
    out = {"name": brand["name"], "wordmark": brand.get("wordmark"), "fonts": brand.get("fonts"),
           "wordmark_css": brand.get("wordmark_css", ""), "wordmark_accent_weight": brand.get("wordmark_accent_weight")}
    out["logo_radius"] = brand.get("logo_radius", 0.22)
    return {k: v for k, v in out.items() if v not in (None, "")}


def scene_file(template: Path, params: dict, dest: Path, brand: dict | None = None) -> None:
    """Copy a scene template into the run folder with its PARAMS filled in and its helper paths flattened."""
    text = template.read_text()
    m0 = re.search(r"/\*PARAMS\*/(.*?)/\*END\*/", text, flags=re.S)
    try:                                              # the template's own defaults fill in anything the spec leaves out
        params = {**json.loads(m0.group(1)), **params} if m0 else params
    except ValueError:
        pass
    if brand:
        params = {**params, "brand": brand_params(brand), "themeColor": brandkit.theme_color(brand, params.get("theme"))}
    text, n = re.subn(r"/\*PARAMS\*/.*?/\*END\*/", lambda m: "/*PARAMS*/" + json.dumps(params) + "/*END*/", text, count=1, flags=re.S)
    if not n:
        raise SystemExit(f"{template.name} has no /*PARAMS*/.../*END*/ block")
    for h in ("runtime.js", "characters.js", "logo.png"):
        text = text.replace(f'"../{h}"', f'"{h}"')
    dest.write_text(brandkit.recolor(text, brand) if brand else text)


def intro_params(spec: dict) -> tuple[dict, int]:
    cast = [{"look": k, "name": CAST_NAMES.get(k, k.title())} if isinstance(k, str) else k
            for k in spec.get("cast", DEFAULT_CAST)]
    n = len(cast)
    t_head = 1.0 + 1.1 * (n - 1) + 1.4 + 0.35
    h1, h2 = (list(spec["title"]) + [""])[:2]
    return ({"cast": cast, "head1": h1, "head2": h2, "tagline": spec["tagline"], "episode": spec.get("episode"),
             "of": spec.get("of"), "theme": default_theme(spec), "tile": spec.get("tile", "trend")},
            math.ceil(t_head + 1.0 + 1.4))


def default_theme(spec: dict) -> str:
    themes = spec["_brand"]["themes"]
    return spec.get("theme") or ("main" if "main" in themes else next(iter(themes)))


def outro_params(spec: dict) -> dict:
    b = spec["_brand"]
    return {"title": " ".join(x for x in spec["title"] if x), "tagline": spec.get("outro_line", (b.get("outro") or {}).get("tagline", "")),
            "url": b["site"].get("public_url", ""), "next": spec.get("next") or "", "episode": spec.get("episode"), "of": spec.get("of"),
            "theme": default_theme(spec), "footer": (b.get("outro") or {}).get("footer", "")}


def gen(spec: dict) -> None:
    d: Path = spec["_dir"]
    brand = spec["_brand"]
    fx = effects(brand)
    (d / "explainers").mkdir(parents=True, exist_ok=True)
    ex = d / "explainers"
    for f in ("characters.js",):
        shutil.copy(SCENES / f, ex / f)
    (ex / "runtime.js").write_text(brandkit.recolor((SCENES / "runtime.js").read_text(), brand))
    logo = brand["_dir"] / brand.get("logo", "logo.png")
    shutil.copy(logo if logo.exists() else SCENES / "logo.png", ex / "logo.png")
    vertical = bool(spec.get("vertical"))
    ip, intro_min = intro_params(spec)
    scene_file(SCENES / "intro.html", ip, ex / "intro.html", brand)
    scene_file(SCENES / "outro.html", outro_params(spec), ex / "outro.html", brand)
    extra = []
    for i, e in enumerate(spec.get("explainers", [])):          # feature explainer scenes, between the intro and the clips
        tpl = SCENES_DIR / f"{e['template']}.html"
        if not tpl.exists():
            raise SystemExit(f"unknown explainer template '{e['template']}' (see templates/brand-scenes/scenes/)")
        params = {**e.get("params", {}), "theme": default_theme(spec)}
        name = f"scene{i + 1}-{e['template']}.html"
        scene_file(tpl, params, ex / name, brand)
        extra.append({"explainer": f"explainers/{name}", "label": e.get("label", "The idea"), "presenter": False,
                      "min_seconds": e.get("min_seconds", 10), "text": e["text"]})
    # the signed-in session: the series folder's live copy (series_build refreshes it), if the app needs one
    if not (d / "auth.json").exists():
        src = spec["_series"] / ".session" / "auth.json" if spec["_series"] else None
        if src and src.exists():
            shutil.copy(src, d / "auth.json")
            (d / "auth.json").chmod(0o600)
    site, auth = brand["site"], brand.get("auth") or {}
    vp = {"width": 430, "height": 764} if vertical else {"width": 1440, "height": 810}
    scen = {
        "name": " ".join(x for x in spec["title"] if x), "base_url": site["base_url"], "allow_hosts": site["allow_hosts"],
        "auth": {"storage_state": "auth.json", "token_js": auth.get("token_js", "")} if auth.get("mode", "none") != "none" else {},
        "viewport": vp,
        "recording": {"resolution": "1440p" if vertical else "4k", "pace": 1.0, "cursor": True,
                      "redact": list(brand.get("redact") or []) + spec.get("redact", [])},
        "slow_mo": 100, "default_timeout": 30, "scenarios": spec["scenarios"],
    }
    mode = "Read-only: scenarios must not change data." if site.get("read_only", True) else "Writes are allowed only in the sandbox the brand names."
    (d / "scenarios.yaml").write_text(f"# Generated by filmwright.series.mkepisode from the episode spec (brand: {brand['name']}). {mode}\n"
                                      + yaml.safe_dump(scen, sort_keys=False, width=110, allow_unicode=True))
    n_cast = len(spec.get("cast", DEFAULT_CAST))
    t_pattern = round(1.0 + 1.1 * (n_cast - 1) + 1.4 + 0.05, 2)
    secs = [{"explainer": "explainers/intro.html", "label": "Intro", "label_seconds": 0, "min_seconds": intro_min, "text": spec["intro_text"], "presenter": True}]
    jingle = fx["jingle"] and spec.get("jingle", True)
    if jingle:
        secs[0]["cues"] = [[0.0, "jingle_in"], [t_pattern, "sparkle"]]
    for e in extra:
        e["label_seconds"] = 0
    secs.extend(extra)
    secs.extend(spec.get("after_intro", []))          # raw extra scenes (e.g. a legacy real-time explainer)
    for sec in spec["sections"]:
        item = {"clip": f"videos/{sec['clip']}.mp4", "label": sec["label"], "text": sec["text"]}
        if not fx["verified_badges"]:
            item["verified"] = False                        # no "backend verified" badges over passing api steps
        if sec.get("auto_focus") == "add":
            item["auto_focus"] = "add"                      # explicit `focus` entries AND the automatic ones
        elif "focus" not in sec and sec.get("auto_focus", True):
            item["auto_focus"] = True                       # zoom in on the clip's real actions (see effects.auto_focus_specs)
            for k in ("auto_focus_max", "auto_focus_zoom", "auto_focus_hold", "auto_focus_skip"):
                if k in sec:
                    item[k] = sec[k]
        for k in ("focus", "callouts", "spotlight", "cuts", "fit", "phrases"):
            if k in sec and (fx["callouts"] or k not in ("callouts", "phrases")):
                item[k] = sec[k]
        secs.append(item)
    first_clip = next((x for x in secs if "clip" in x), None)
    if first_clip is not None and (extra or spec.get("after_intro")):
        first_clip["transition"] = "zoomin"            # the explainer zooms into the real screen
    outro = {"explainer": "explainers/outro.html", "label": "Outro", "label_seconds": 0, "presenter": bool(spec.get("host_outro", True)),
             "min_seconds": 9, "text": spec["outro_text"]}
    if jingle:
        outro["cues"] = [[0.3, "jingle_out"]]
    secs.append(outro)
    host = brand.get("host") or {}
    preset = host.get("preset", "leo")
    style: object = preset
    over = {k: host[k] for k in ("shirt", "shirt2", "skin", "hair") if host.get(k)}
    if over:
        style = {"preset": preset, **over}
    video = {"output": spec["slug"] + ("-vertical" if vertical else ""),
             "music": spec.get("music") or brand.get("music") or {"mood": "calm"},
             "presenter": {"style": style, "height": 0.13 if vertical else 0.25}, "sfx": bool(fx["sfx"]),
             "transition": {"type": "smoothleft", "duration": 0.6},
             "voice": {**VOICE, **(brand.get("voice") or {}), **(spec.get("voice") or {})}, "sections": secs}
    if host.get("enabled") is False:
        video.pop("presenter")
    if vertical:
        video["size"] = {"width": 1080, "height": 1920}
    (d / "video.yaml").write_text(yaml.safe_dump(video, sort_keys=False, width=110, allow_unicode=True))
    warn = f" (SITE NOT SET: fill {brand['_dir'] / 'brand.yaml'} before recording)" if "TODO" in str(site.get("base_url")) else ""
    print(f"generated {d} (intro {intro_min}s{', vertical' if vertical else ''}){warn}")


def run(cmd: list[str], cwd: Path) -> int:
    return subprocess.run(cmd, cwd=cwd).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["gen", "record", "build", "social"])
    ap.add_argument("spec", type=Path)
    ap.add_argument("--only")
    a = ap.parse_args()
    spec = load(a.spec)
    d: Path = spec["_dir"]
    if a.cmd == "gen":
        gen(spec)
        return 0
    brand = spec["_brand"]
    if a.cmd == "record":
        if "TODO" in str(brand["site"].get("base_url")) or "TODO" in str(brand["site"].get("allow_hosts")):
            raise SystemExit(f"{brand['_dir'] / 'brand.yaml'} still has TODO in site: set base_url and allow_hosts to a test environment.")
        cmd = [PY, "-m", "filmwright.demo.run_scenarios", str(d / "scenarios.yaml")]
        return run(cmd + (["--only", a.only] if a.only else []), d)
    if a.cmd == "build":
        return run([PY, "-m", "filmwright.demo.build_video", str(d / "video.yaml")], d)
    if a.cmd == "social":
        if spec.get("posts_dir"):
            posts = Path(spec["posts_dir"]).expanduser()
        elif spec["_series"]:
            posts = spec["_series"] / (yaml.safe_load((spec["_series"] / "series.yaml").read_text()).get("posts") or "posts")
        else:
            posts = d.parent / "posts"
        posts.mkdir(parents=True, exist_ok=True)
        vert = bool(spec.get("vertical"))
        stem = f"{int(spec['episode']):02d}-{spec['slug']}" + ("-vertical" if vert else "")
        base = spec["slug"] + ("-vertical" if vert else "")
        rc = run([PY, "-m", "filmwright.core.export.social", "--video", str(d / f"{base}.mp4"),
                  "--srt", str(d / f"{base}.srt"), "--out", str(posts / f"{stem}.mp4")] + (["--vertical"] if vert else []), d)
        # cover image: the intro's finished title frame (logo, headline, characters), not an arbitrary mid-clip frame
        master = d / f"{base}.mp4"
        try:
            ends = subprocess.run(["ffprobe", "-v", "error", "-show_chapters", "-of", "csv=p=0", "-show_entries", "chapter=end_time", str(master)],
                                  capture_output=True, text=True).stdout.split()
            at = max(1.0, float(ends[0].split(",")[0]) - 0.8)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", str(master), "-frames:v", "1", "-vf",
                            "scale=1920:-2" if not vert else "scale=1080:-2", str(posts / f"{stem}-poster.png")], check=True)
        except Exception as e:                                  # the film's own poster stays as a fallback
            print(f"cover image: {e}")
        cap = [f"# Episode {spec['episode']} of {spec['of']}: {' '.join(x for x in spec['title'] if x)}", "",
               spec.get("caption", "").strip(), "", " ".join(spec.get("hashtags", [])), "",
               (brand.get("captions") or {}).get("disclaimer", "")]
        (posts / f"{stem}.md").write_text("\n".join(x for x in cap if x is not None).rstrip() + "\n")
        try:                                                  # optional lint of the caption (checks: tool_names in docs/film.md)
            from filmwright.core.textcheck import check
            check([str(posts / f"{stem}.md")], "warn")
        except ImportError:
            pass
        return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
