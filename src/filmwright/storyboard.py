"""Storyboards: one panel per scene (a still, the narration line, its timing) for review before the full render.

    filmwright storyboard [dir]          -> out/storyboard/index.html and storyboard.pdf

Each pipeline's `board` step writes storyboard.json:

    {"groups": [{"heading": "...", "panels": [{"label", "start", "dur", "text", "on_screen", "image"}]}]}

and this module lays it out as a self-contained HTML page (images beside it in img/) and an A4 landscape PDF with a
sign-off box, so a team can approve the script, pacing and look before spending render time.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def timecode(seconds: float) -> str:
    s = max(0, int(round(float(seconds))))
    return f"{s // 60}:{s % 60:02d}"


def clip_frame(clip: Path, at: float, out: Path) -> Path | None:
    """One frame of a recording as PNG, or None when the clip can't be read."""
    out.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0.0, at):.2f}", "-i", str(clip), "-frames:v", "1",
                        "-vf", "scale=1920:-2", str(out)], capture_output=True)
    return out if p.returncode == 0 and out.exists() else None


def write_json(path: Path, groups: list[dict]) -> Path:
    path.write_text(json.dumps({"groups": groups}, indent=1, default=str))
    return path


CSS = """
:root{--ink:#16182a;--muted:#5d6280;--line:#dcdfee;--card:#ffffff;--bg:#f4f5fa;--accent:#6b4ef0}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
header{padding:28px 32px 8px}h1{margin:0 0 4px;font-size:26px}h2{margin:28px 32px 10px;font-size:18px}
.meta{color:var(--muted);display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:6px}.meta b{color:var(--ink);font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px;padding:0 32px}
.panel{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;break-inside:avoid}
.panel img,.panel .noimg{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:#1b1e33}
.panel .noimg{display:flex;align-items:center;justify-content:center;color:#a9aecb;font-size:13px}
.body{padding:10px 12px 12px}.top{display:flex;justify-content:space-between;gap:8px;font-size:12px;color:var(--muted)}
.num{font-weight:700;color:var(--accent)}.label{font-weight:600;color:var(--ink);margin:4px 0 2px}
.say{margin:4px 0 0}.say:before{content:"\\201C"}.say:after{content:"\\201D"}.screen{margin-top:6px;font-size:12px;color:var(--muted)}
.notes{margin-top:8px;border-top:1px dashed var(--line);padding-top:6px;min-height:34px;font-size:12px;color:var(--muted)}
.signoff{margin:28px 32px 36px;padding:14px 16px;border:1px solid var(--line);border-radius:10px;background:var(--card);display:grid;
 grid-template-columns:repeat(3,1fr);gap:18px;font-size:13px;color:var(--muted)}.signoff div{border-bottom:1px solid var(--ink);padding-top:22px}
@media (max-width:640px){header,h2{padding-left:16px;padding-right:16px;margin-left:0}.grid{padding:0 16px}.signoff{margin:24px 16px;grid-template-columns:1fr}}
@page{size:A4 landscape;margin:12mm}
@media print{body{background:#fff;font-size:10px}header{padding:0 0 6px}h1{font-size:20px}h2{margin:12px 0 6px;font-size:14px}
 .grid{padding:0;grid-template-columns:repeat(4,1fr);gap:8px}.body{padding:6px 8px 8px}.notes{min-height:16px;font-size:9px}
 .screen{font-size:9px}.signoff{break-inside:avoid;padding:8px 12px;font-size:10px}.signoff div{padding-top:14px}
 .signoff{margin:12px 0 0}.panel{border-color:#c9cde0}}
"""


def _thumb(src: Path, dest: Path, width: int = 960) -> None:
    from PIL import Image
    im = Image.open(src).convert("RGB")
    im.thumbnail((width, width), Image.LANCZOS)
    im.save(dest, "JPEG", quality=84)


def render_html(title: str, meta: dict[str, str], groups: list[dict], out_dir: Path) -> Path:
    """Write out_dir/index.html with the panels' images copied to out_dir/img/; returns the page."""
    out_dir.mkdir(parents=True, exist_ok=True)
    img_dir = out_dir / "img"
    if img_dir.exists():
        shutil.rmtree(img_dir)
    img_dir.mkdir()
    e = html.escape
    parts = [f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
             f"content=\"width=device-width,initial-scale=1\"><title>{e(title)} storyboard</title><style>{CSS}</style></head><body>",
             f"<header><h1>{e(title)}</h1><div class=\"meta\">"
             + "".join(f"<span>{e(k)} <b>{e(v)}</b></span>" for k, v in meta.items() if v) + "</div></header>"]
    n = 0
    for g in groups:
        if len(groups) > 1 or g.get("heading"):
            parts.append(f"<h2>{e(str(g.get('heading') or ''))}</h2>")
        parts.append("<div class=\"grid\">")
        for p in g["panels"]:
            n += 1
            src = Path(p["image"]) if p.get("image") else None
            if src and src.is_file():
                dest = img_dir / f"{n:03d}.jpg"
                _thumb(src, dest)
                img = f"<img src=\"img/{dest.name}\" alt=\"Panel {n}: {e(str(p.get('label') or ''))}\">"
            else:
                img = f"<div class=\"noimg\">{e(str(p.get('placeholder') or 'no picture yet: record the clip first'))}</div>"
            start, dur = float(p.get("start", 0)), float(p.get("dur", 0))
            parts.append(
                f"<div class=\"panel\">{img}<div class=\"body\"><div class=\"top\"><span class=\"num\">{n}</span>"
                f"<span>{timecode(start)}–{timecode(start + dur)} · {dur:.1f}s</span></div>"
                + (f"<div class=\"label\">{e(str(p['label']))}</div>" if p.get("label") else "")
                + (f"<p class=\"say\">{e(str(p['text']))}</p>" if p.get("text") else "")
                + (f"<div class=\"screen\">On screen: {e(str(p['on_screen']))}</div>" if p.get("on_screen") else "")
                + "<div class=\"notes\">Notes:</div></div></div>")
        parts.append("</div>")
    parts.append("<div class=\"signoff\"><span>Approved by<div></div></span><span>Role<div></div></span>"
                 "<span>Date<div></div></span></div></body></html>")
    page = out_dir / "index.html"
    page.write_text("".join(parts))
    return page


def to_pdf(page: Path, pdf: Path) -> Path:
    """Print the board to an A4 landscape PDF with headless Chromium."""
    from playwright.sync_api import sync_playwright

    from filmwright.demo.recorder import launch_kwargs  # the open-source Chromium `filmwright setup` installs
    with sync_playwright() as pw:
        b = pw.chromium.launch(**launch_kwargs())
        p = b.new_page()
        p.goto(page.resolve().as_uri())
        p.wait_for_load_state("networkidle")
        p.pdf(path=str(pdf), format="A4", landscape=True, print_background=True)
        b.close()
    return pdf


def build(title: str, meta: dict[str, str], groups: list[dict], out_dir: Path, pdf: bool = True) -> list[Path]:
    meta = {**meta, "Panels": str(sum(len(g["panels"]) for g in groups))}
    if len(groups) == 1:
        meta["Length"] = timecode(sum(float(p.get("dur", 0)) for p in groups[0]["panels"]))
    meta["Made"] = dt.date.today().isoformat()
    page = render_html(title, meta, groups, out_dir)
    out = [page]
    if pdf:
        out.append(to_pdf(page, out_dir / "storyboard.pdf"))
    return out


def demo_groups(film: dict, base: Path, work: Path) -> list[dict]:
    """Panels for a demo film from its video.yaml (no narration needed): timings are estimates from the length of
    each line; pictures are frames from the recordings that exist."""
    from filmwright.core.voice.qwen import speech_seconds
    from filmwright.demo.build_video import LEAD, TAIL
    panels, t = [], 0.0

    def add(label: str, text: str, minimum: float, image: Path | None = None, on_screen: str = "", placeholder: str = "") -> None:
        nonlocal t
        dur = max(minimum, (speech_seconds(text) + LEAD + TAIL) if text else 0.0)
        panels.append({"label": label, "start": round(t, 2), "dur": round(dur, 2), "text": text, "on_screen": on_screen,
                       "image": str(image) if image else "", "placeholder": placeholder})
        t += dur

    if film.get("title_card"):
        c = film["title_card"]
        add("Title card", str(film.get("intro") or ""), 4.0,
            on_screen=" · ".join(str(c[k]) for k in ("eyebrow", "title", "subtitle") if c.get(k)), placeholder="title card")
    for i, s in enumerate(film.get("sections") or []):
        text = str(s.get("text") or "")
        clip = (base / str(s.get("clip", ""))).expanduser() if s.get("clip") else None
        dur = max(float(s.get("min_seconds", 5)), speech_seconds(text) + LEAD + TAIL)
        img = clip_frame(clip, dur * .6, work / f"section-{i + 1:02d}.png") if clip and clip.is_file() else None
        add(str(s.get("label") or f"Section {i + 1}"), text, float(s.get("min_seconds", 5)), img)
    if film.get("closing_card"):
        c = film["closing_card"]
        add("Closing card", str(film.get("outro") or ""), 4.0,
            on_screen=" · ".join([str(c.get("title") or "")] + [str(b) for b in c.get("bullets") or []]).strip(" ·"),
            placeholder="closing card")
    return [{"heading": "", "panels": panels}]


def load_groups(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise SystemExit(f"{path} wasn't written; the pipeline's board step failed")
    return json.loads(path.read_text())["groups"]
