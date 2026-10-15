#!/usr/bin/env python3
"""Web-ready versions of every episode in a series, from the 4K masters.

    python -m filmwright.core.export.web <series-dir> [--episodes 2-19]

For each episode it writes into <series-dir>/<web>/ (default web/):
  NN-slug-720p.mp4   H.264 High, ~0.7 Mbit/s, faststart: the default for a <video> tag (5-8 MB for ~75 s)
  NN-slug-480p.mp4   the same at 480p for phones
  NN-slug-poster.jpg the intro's finished title frame
  NN-slug.en.vtt     captions as a toggleable WebVTT track (NOT burned in)
and manifest.json + preview.html (open it from disk to try the files in a browser).
Already-encoded files newer than the master are skipped, so it is safe to re-run.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from filmwright.core.names import checked_slug


def sh(*a: str) -> str:
    p = subprocess.run(a, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-400:])
    return p.stdout.strip()


def vtt(srt: str) -> str:
    out = ["WEBVTT", ""]
    for block in re.split(r"\n\s*\n", srt.strip()):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        for i, ln in enumerate(lines):
            if "-->" in ln:
                out += [ln.replace(",", "."), " ".join(lines[i + 1:]), ""]
                break
    return "\n".join(out)


def fresh(f: Path, master: Path) -> bool:
    return f.exists() and f.stat().st_mtime > master.stat().st_mtime


def web_renditions(m: Path, srt: Path | None, out: Path, stem: str, poster_at: float | None = None) -> dict[str, str]:
    """720p + 480p MP4 (faststart), a JPEG poster and a WebVTT caption track for one film. Returns {role: file name}.
    The poster is taken at `poster_at` seconds, else at the end of the first chapter, else 3 s in."""
    out.mkdir(parents=True, exist_ok=True)
    common = ["-hide_banner", "-loglevel", "error", "-y", "-i", str(m), "-map", "0:v:0", "-map", "0:a:0", "-sn", "-dn", "-map_chapters", "-1"]
    aac = ["-c:a", "aac", "-b:a", "96k", "-ac", "2", "-ar", "48000"]
    for h, crf, tag in ((720, 27, "720p"), (480, 29, "480p")):
        if fresh(out / f"{stem}-{tag}.mp4", m):
            continue
        sh("ffmpeg", *common, "-vf", f"scale=-2:{h}:flags=lanczos", "-c:v", "libx264", "-preset", "slow", "-profile:v", "high", "-crf", str(crf),
           "-maxrate", "2500k" if h == 720 else "1200k", "-bufsize", "5000k" if h == 720 else "2400k", "-pix_fmt", "yuv420p", "-g", "60",
           *aac, "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact", "-bsf:v", "filter_units=remove_types=6",
           "-metadata:s:v:0", "encoder=", "-metadata:s:a:0", "encoder=", "-movflags", "+faststart", str(out / f"{stem}-{tag}.mp4"))
    if poster_at is None:
        ends = [float(ln.split(",")[0]) for ln in sh("ffprobe", "-v", "error", "-show_chapters", "-of", "csv=p=0", "-show_entries",
                                                     "chapter=end_time", str(m)).splitlines() if ln.strip()]
        poster_at = max(1.0, ends[0] - 0.8) if ends else 3.0
    tmp_png = out / f".{stem}-poster.png"
    sh("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{poster_at:.2f}", "-i", str(m), "-frames:v", "1", "-vf", "scale=1280:-2", str(tmp_png))
    from PIL import Image
    Image.open(tmp_png).convert("RGB").save(out / f"{stem}-poster.jpg", quality=88)      # Pillow writes no encoder comment
    tmp_png.unlink()
    files = {"mp4_720": f"{stem}-720p.mp4", "mp4_480": f"{stem}-480p.mp4", "poster": f"{stem}-poster.jpg"}
    if srt and srt.exists():
        (out / f"{stem}.en.vtt").write_text(vtt(srt.read_text()))
        files["captions_en"] = f"{stem}.en.vtt"
    return files


def one(spec_path: Path, out: Path) -> dict:
    s = yaml.safe_load(spec_path.read_text())
    d = Path(str(s["dir"])).expanduser()
    n, slug = int(s["episode"]), checked_slug(s.get("slug"), f"{spec_path.name}: slug")
    stem, m = f"{n:02d}-{slug}", d / f"{slug}.mp4"
    files = web_renditions(m, d / f"{slug}.srt", out, stem)
    dur = float(sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out / f"{stem}-720p.mp4")))
    return {"episode": n, "slug": slug, "title": " ".join(x for x in s["title"] if x), "tagline": s["tagline"], "seconds": round(dur), "next": s.get("next") or None,
            "files": files, "bytes": {k: (out / v).stat().st_size for k, v in files.items()}}


PREVIEW = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Series preview</title>
<style>body{margin:0;background:#0f1222;color:#f4f5fb;font-family:system-ui,sans-serif}header,main{max-width:1100px;margin:auto;padding:24px 20px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:18px}article{background:#171a30;border:1px solid #343a6b;border-radius:14px;overflow:hidden}
video{width:100%;display:block;aspect-ratio:16/9;background:#000}.m{padding:12px 14px}.m h2{font-size:16px;margin:0}.m small{color:#a9aecb}</style></head><body>
<header><h1>Series preview</h1><p>720p MP4, poster, toggleable captions. Nothing downloads until you press play.</p></header><main><div class="grid" id="g"></div></main>
<script>Promise.resolve(__ROWS__).then(rows=>{const g=document.getElementById("g");rows.forEach(r=>{const f=r.files,a=document.createElement("article");
a.innerHTML='<video controls preload="none" playsinline poster="'+f.poster+'"><source src="'+f.mp4_720+'" type="video/mp4"><track kind="captions" src="'+f.captions_en+'" srclang="en" label="English"></video><div class="m"><h2>'+r.episode+' · '+r.title+'</h2><small>'+Math.floor(r.seconds/60)+':'+String(r.seconds%60).padStart(2,"0")+' · '+(r.bytes.mp4_720/1048576).toFixed(1)+' MB</small></div>';g.appendChild(a)})});</script></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("series_dir", type=Path)
    ap.add_argument("--episodes")
    a = ap.parse_args()
    d = a.series_dir.expanduser().resolve()
    cfg = yaml.safe_load((d / "series.yaml").read_text())
    out = d / cfg.get("web", "web")
    out.mkdir(exist_ok=True)
    specs = sorted((d / cfg.get("specs", "specs")).glob("ep*.yaml"))
    if a.episodes:
        want = set()
        for part in a.episodes.split(","):
            x, _, y = part.partition("-")
            want.update(range(int(x), int(y or x) + 1))
        specs = [p for p in specs if int(yaml.safe_load(p.read_text())["episode"]) in want]
    with ThreadPoolExecutor(max_workers=4) as ex:
        rows = sorted(ex.map(lambda p: one(p, out), specs), key=lambda r: r["episode"])
    (out / "manifest.json").write_text(json.dumps(rows, indent=2))
    (out / "preview.html").write_text(PREVIEW.replace("__ROWS__", json.dumps(rows)))
    tot = {k: sum(r["bytes"][k] for r in rows) / 1048576 for k in rows[0]["bytes"]} if rows else {}
    print(f"{len(rows)} episodes -> {out}: " + ", ".join(f"{k} {v:.0f} MB" for k, v in tot.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
