#!/usr/bin/env python3
"""Write <series-dir>/<posts>/POSTING-PLAN.md for a finished series (and copy each episode's teaser GIF next to its post).

    python -m filmwright.series.series_plan <series-dir>

Reads series.yaml: brand, groups [{name, episodes: [first, last]}], notes [strings shown under "Before you post"],
platform_notes, posts (default posts/). Titles, lengths and file names come from the episode specs and the built files.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from filmwright.core.names import checked_slug
from filmwright.series import brandkit


def main() -> int:
    d = Path(sys.argv[1]).expanduser().resolve()
    cfg = yaml.safe_load((d / "series.yaml").read_text())
    name = cfg.get("brand") or "example"
    brand = brandkit.load_brand(d / str(name) if (d / str(name)).exists() else name)
    posts = d / cfg.get("posts", "posts")
    posts.mkdir(exist_ok=True)
    rows = []
    for f in sorted((d / cfg.get("specs", "specs")).glob("ep*.yaml")):
        s = yaml.safe_load(f.read_text())
        try:
            s["slug"] = checked_slug(s.get("slug"), f"{f.name}: slug")
        except ValueError as e:
            raise SystemExit(str(e)) from None
        ep_dir = Path(str(s["dir"])).expanduser()
        n = int(s["episode"])
        stem = f"{n:02d}-{s['slug']}"
        teaser = ep_dir / f"{s['slug']}-teaser.gif"
        if teaser.exists():
            shutil.copy(teaser, posts / f"{stem}-teaser.gif")
        mp4 = posts / f"{stem}.mp4"
        if not mp4.exists():
            continue
        dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)]).decode())
        rows.append((n, stem, " ".join(x for x in s["title"] if x), dur))
    total = sum(r[3] for r in rows)
    lines = [f"# {brand['name']}: {len(rows)}-part series, posting plan", "",
             f"{len(rows)} episodes, {int(total // 60)} minutes {int(total % 60)} seconds in total.",
             "Post in order. Every video ends with a \"Next up\" line and a strip of dots showing where it sits in the series.", ""]
    groups = cfg.get("groups") or [{"name": "Episodes", "episodes": [1, len(rows)]}]
    for g in groups:
        a, b = g["episodes"]
        lines += [f"## {g['name']}", "", "| # | Episode | Length | Video | Caption |", "|---|---|---|---|---|"]
        for n, stem, title, dur in rows:
            if a <= n <= b:
                lines.append(f"| {n} | {title} | {int(dur // 60)}:{int(dur % 60):02d} | `{stem}.mp4` | `{stem}.md` |")
        lines.append("")
    lines += ["Each episode also has `NN-name-poster.png` (cover image: the intro's title frame) and `NN-name-teaser.gif` (10-second loop).", "",
              "## Per post", "",
              "1. Upload `NN-name.mp4` (1080p, small burned-in captions, plays fine with the sound off).",
              "2. Paste the text from `NN-name.md` as the caption: episode number, next episode, hashtags.",
              "3. Use the poster as the cover image where the platform allows one.",
              f"4. Put {brand['site'].get('public_url', 'the link')} in the post on X, and in the first comment on LinkedIn and Reddit.", ""]
    if cfg.get("platform_notes"):
        lines += ["## Platform notes", ""] + [f"- {x}" for x in cfg["platform_notes"]] + [""]
    lines += ["## Before you post", "",
              "- Watch each one once on your phone, with and without sound.",
              "- The recordings show the live product on the day they were recorded; names and numbers on screen change later."]
    if brand.get("captions", {}).get("disclaimer"):
        lines.append(f"- Every caption keeps the line: \"{brand['captions']['disclaimer']}\" Keep it.")
    lines += [f"- {x}" for x in cfg.get("notes", [])]
    lines.append("")
    (posts / "POSTING-PLAN.md").write_text("\n".join(lines))
    print(f"{len(rows)} episodes, total {int(total // 60)}:{int(total % 60):02d} -> {posts / 'POSTING-PLAN.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
